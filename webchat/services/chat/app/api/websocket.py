"""WebSocket chat connection handler conforming to AsyncAPI 3.0 specification."""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError

from app.adapters.repository import ChatRepository, get_chat_repository
from app.adapters.security import verify_user_token
from app.adapters.social_client import SocialClient, get_social_client
from app.api.chat import to_message_schema
from app.api.dependencies import require_conversation_access
from app.api.schemas import TextContent, format_utc_z
from app.domain.exceptions import DomainError, UnauthenticatedError
from app.settings import get_settings

logger = logging.getLogger("webchat.chat.ws")

router = APIRouter(tags=["Chat WebSocket"])


class ConnectionManager:
    def __init__(self) -> None:
        # conv_id -> set of WebSocket
        self._subscriptions: dict[uuid.UUID, set[WebSocket]] = {}
        # ws -> set of conv_id
        self._socket_convs: dict[WebSocket, set[uuid.UUID]] = {}

    def subscribe(self, conv_id: uuid.UUID, ws: WebSocket) -> None:
        if conv_id not in self._subscriptions:
            self._subscriptions[conv_id] = set()
        self._subscriptions[conv_id].add(ws)

        if ws not in self._socket_convs:
            self._socket_convs[ws] = set()
        self._socket_convs[ws].add(conv_id)

    def is_subscribed(self, conv_id: uuid.UUID, ws: WebSocket) -> bool:
        return conv_id in self._socket_convs.get(ws, ())

    def unsubscribe(self, conv_id: uuid.UUID, ws: WebSocket) -> None:
        if conv_id in self._subscriptions:
            self._subscriptions[conv_id].discard(ws)
            if not self._subscriptions[conv_id]:
                del self._subscriptions[conv_id]
        if ws in self._socket_convs:
            self._socket_convs[ws].discard(conv_id)

    def disconnect(self, ws: WebSocket) -> None:
        convs = self._socket_convs.pop(ws, set())
        for cid in convs:
            if cid in self._subscriptions:
                self._subscriptions[cid].discard(ws)
                if not self._subscriptions[cid]:
                    del self._subscriptions[cid]

    async def broadcast_to_conversation(self, conv_id: uuid.UUID, payload: dict[str, Any]) -> None:
        sockets = list(self._subscriptions.get(conv_id, set()))
        if not sockets:
            return

        text_data = json.dumps(payload)
        for s in sockets:
            try:
                await s.send_text(text_data)
            except Exception:
                pass


manager = ConnectionManager()


class Command(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: uuid.UUID


class Authenticate(Command):
    type: Literal["session.authenticate"]
    access_token: str


class Subscription(Command):
    type: Literal["conversation.subscribe", "conversation.unsubscribe"]
    conversation_id: uuid.UUID


class SentAttachment(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["audio", "file"]
    attachment_id: uuid.UUID


class Send(Command):
    type: Literal["message.send"]
    conversation_id: uuid.UUID
    client_message_id: uuid.UUID
    content: Annotated[TextContent | SentAttachment, Field(discriminator="type")]


commands = TypeAdapter(Annotated[Authenticate | Subscription | Send, Field(discriminator="type")])


async def receive_frame(ws: WebSocket) -> dict[str, Any]:
    packet = await ws.receive()
    if packet["type"] == "websocket.disconnect":
        raise WebSocketDisconnect(packet["code"])
    raw = packet.get("text")
    if raw is None or len(raw.encode("utf-8")) > 32768:
        code = 1003 if raw is None else 1009
        await ws.close(code=code)
        raise WebSocketDisconnect(code)
    try:
        frame = json.loads(raw)
    except ValueError as exc:
        raise DomainError("Expected a JSON object.", "INVALID_FRAME") from exc
    if not isinstance(frame, dict):
        raise DomainError("Expected a JSON object.", "INVALID_FRAME")
    return frame


async def handle_command(
    ws: WebSocket,
    command: Authenticate | Subscription | Send,
    user_id: uuid.UUID,
    username: str,
    repo: ChatRepository,
    social: SocialClient,
) -> None:
    request_id = str(command.request_id)
    if isinstance(command, Authenticate):
        raise DomainError("Session already authenticated.", "ALREADY_AUTHENTICATED")

    room = command.conversation_id
    if isinstance(command, Subscription):
        response = {"request_id": request_id, "conversation_id": str(room)}
        if command.type == "conversation.unsubscribe":
            manager.unsubscribe(room, ws)
            await ws.send_json({"type": "conversation.unsubscribed", **response})
            return

        await require_conversation_access(room, user_id, social)
        manager.subscribe(room, ws)
        try:
            latest = await repo.get_latest_seq(room)
        except Exception:
            manager.unsubscribe(room, ws)
            raise
        await ws.send_json({"type": "conversation.subscribed", **response, "latest_seq": latest})
        return

    if not manager.is_subscribed(room, ws):
        raise DomainError("Subscribe before sending.", "NOT_SUBSCRIBED")
    await require_conversation_access(room, user_id, social, require_send=True)
    content = command.content
    stored, replayed = await repo.send_message(
        conv_id=room,
        sender_id=user_id,
        sender_username=username,
        client_message_id=command.client_message_id,
        content_type=content.type,
        text_content=content.text if isinstance(content, TextContent) else None,
        attachment_id=content.attachment_id if isinstance(content, SentAttachment) else None,
    )
    message = to_message_schema(stored).model_dump(mode="json", exclude_none=True)
    try:
        await ws.send_json(
            {
                "type": "message.ack",
                "request_id": request_id,
                "message": message,
                "replayed": replayed,
            }
        )
    finally:
        if not replayed:
            await manager.broadcast_to_conversation(
                room, {"type": "message.created", "message": message}
            )


async def send_error(ws: WebSocket, request_id: str | None, error: DomainError) -> None:
    await ws.send_json(
        {
            "type": "error",
            "request_id": request_id,
            "code": error.code,
            "message": error.message,
            "retryable": error.code in {"SOCIAL_UNAVAILABLE", "CHAT_UNAVAILABLE"},
        }
    )


@router.websocket("/ws/v1/chat")
async def chat_websocket(websocket: WebSocket) -> None:
    await websocket.accept()
    try:
        try:
            frame = await asyncio.wait_for(receive_frame(websocket), timeout=5)
            auth = Authenticate.model_validate(frame)
            claims = verify_user_token(auth.access_token, get_settings())
            user_id = uuid.UUID(claims["sub"])
            username = claims.get("username")
            if not isinstance(username, str) or not username:
                raise UnauthenticatedError()
            expiry = datetime.fromtimestamp(claims["exp"], UTC)
        except TimeoutError:
            await websocket.close(code=4408)
            return
        except (DomainError, ValueError, TypeError, OverflowError):
            await websocket.close(code=4401)
            return
        await websocket.send_json(
            {
                "type": "session.ready",
                "request_id": str(auth.request_id),
                "session_id": str(uuid.uuid4()),
                "user_id": str(user_id),
                "expires_at": format_utc_z(expiry),
            }
        )

        repo = await get_chat_repository()
        social = get_social_client()
        while True:
            request_id = None
            try:
                remaining = (expiry - datetime.now(UTC)).total_seconds()
                try:
                    frame = await asyncio.wait_for(receive_frame(websocket), timeout=remaining)
                except TimeoutError:
                    await websocket.close(code=4401)
                    return
                raw_id = frame.get("request_id")
                if isinstance(raw_id, str):
                    try:
                        request_id = str(uuid.UUID(raw_id))
                    except ValueError:
                        pass
                command = commands.validate_python(frame)
                await handle_command(websocket, command, user_id, username, repo, social)
            except ValidationError:
                await send_error(
                    websocket, request_id, DomainError("Invalid command.", "VALIDATION_ERROR")
                )
            except DomainError as exc:
                await send_error(websocket, request_id, exc)
            except WebSocketDisconnect:
                raise
            except Exception:
                logger.exception("Chat command failed")
                await send_error(
                    websocket, request_id, DomainError("Storage unavailable.", "CHAT_UNAVAILABLE")
                )
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(websocket)
