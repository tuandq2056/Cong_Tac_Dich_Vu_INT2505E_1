"""WebSocket chat connection handler conforming to AsyncAPI 3.0 specification."""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.adapters.repository import (
    ChatRepository,
    get_chat_repository,
)
from app.adapters.security import verify_user_token
from app.adapters.social_client import SocialClient, get_social_client
from app.api.schemas import format_utc_z
from app.domain.exceptions import (
    ClientMessageIdConflictError,
    DomainError,
    UnauthenticatedError,
)
from app.domain.models import validate_text_content
from app.settings import Settings, get_settings

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


@router.websocket("/ws/v1/chat")
async def chat_websocket(
    websocket: WebSocket,
) -> None:
    await websocket.accept()
    settings: Settings = get_settings()
    repo: ChatRepository = await get_chat_repository()
    social: SocialClient = get_social_client()

    user_id: uuid.UUID | None = None
    username: str = ""

    # Phase 1: Wait for session.authenticate frame within 5 seconds (AsyncAPI spec)
    try:
        raw_msg = await asyncio.wait_for(websocket.receive_text(), timeout=5.0)
        auth_data = json.loads(raw_msg)
        if auth_data.get("type") != "session.authenticate" or not auth_data.get("token"):
            await websocket.close(code=4401, reason="Authentication failed.")
            return

        token = auth_data["token"]
        claims = verify_user_token(token, settings)
        user_id = uuid.UUID(claims["sub"])
        username = claims.get("username", f"user_{str(user_id)[:8]}")

        now = datetime.now(UTC)
        await websocket.send_text(
            json.dumps(
                {
                    "type": "session.ready",
                    "user_id": str(user_id),
                    "server_time": format_utc_z(now),
                }
            )
        )
    except TimeoutError:
        logger.info("WS auth timed out after 5 seconds")
        await websocket.close(code=4408, reason="Authentication timeout.")
        return
    except (UnauthenticatedError, Exception) as exc:
        logger.info("WS auth failed: %s", exc)
        await websocket.close(code=4401, reason="Invalid authentication token.")
        return

    # Phase 2: Session active loop
    try:
        while True:
            text_data = await websocket.receive_text()
            frame = json.loads(text_data)
            frame_type = frame.get("type")

            if frame_type == "conversation.subscribe":
                raw_conv_id = frame.get("conversation_id")
                if not raw_conv_id:
                    continue
                conv_id = uuid.UUID(raw_conv_id)
                can_read, _ = await social.check_permissions(conv_id, user_id)
                if not can_read:
                    await websocket.send_text(
                        json.dumps(
                            {
                                "type": "error",
                                "code": "CONVERSATION_NOT_FOUND",
                                "message": "Conversation not found or access denied.",
                            }
                        )
                    )
                    continue

                manager.subscribe(conv_id, websocket)
                latest_seq = await repo.get_latest_seq(conv_id)
                await websocket.send_text(
                    json.dumps(
                        {
                            "type": "conversation.subscribed",
                            "conversation_id": str(conv_id),
                            "latest_seq": latest_seq,
                        }
                    )
                )

            elif frame_type == "conversation.unsubscribe":
                raw_conv_id = frame.get("conversation_id")
                if raw_conv_id:
                    conv_id = uuid.UUID(raw_conv_id)
                    manager.unsubscribe(conv_id, websocket)
                    await websocket.send_text(
                        json.dumps(
                            {
                                "type": "conversation.unsubscribed",
                                "conversation_id": str(conv_id),
                            }
                        )
                    )

            elif frame_type == "message.send":
                raw_conv_id = frame.get("conversation_id")
                raw_client_msg_id = frame.get("client_message_id")
                content = frame.get("content", {})

                if not raw_conv_id or not raw_client_msg_id or not content:
                    await websocket.send_text(
                        json.dumps(
                            {
                                "type": "error",
                                "code": "VALIDATION_ERROR",
                                "message": "Invalid message.send frame.",
                            }
                        )
                    )
                    continue

                conv_id = uuid.UUID(raw_conv_id)
                client_msg_id = uuid.UUID(raw_client_msg_id)

                can_read, can_send = await social.check_permissions(conv_id, user_id)
                if not can_send:
                    await websocket.send_text(
                        json.dumps(
                            {
                                "type": "error",
                                "code": "ACTION_FORBIDDEN",
                                "message": "You cannot send messages in this conversation.",
                            }
                        )
                    )
                    continue

                content_type = content.get("type", "text")
                msg_text = content.get("text")
                att_id = (
                    uuid.UUID(content["attachment_id"]) if content.get("attachment_id") else None
                )

                if content_type == "text":
                    try:
                        validate_text_content(msg_text or "")
                    except DomainError as de:
                        await websocket.send_text(
                            json.dumps(
                                {
                                    "type": "error",
                                    "code": de.code or "VALIDATION_ERROR",
                                    "message": de.message,
                                }
                            )
                        )
                        continue

                try:
                    stored_msg, is_replayed = await repo.send_message(
                        conv_id=conv_id,
                        sender_id=user_id,
                        client_message_id=client_msg_id,
                        content_type=content_type,
                        text_content=msg_text,
                        attachment_id=att_id,
                    )
                except ClientMessageIdConflictError:
                    await websocket.send_text(
                        json.dumps(
                            {
                                "type": "error",
                                "code": "CLIENT_MESSAGE_ID_CONFLICT",
                                "message": (
                                    "Client message ID was already used with different payload."
                                ),
                            }
                        )
                    )
                    continue

                # 1. ACK back to sender
                await websocket.send_text(
                    json.dumps(
                        {
                            "type": "message.ack",
                            "conversation_id": str(conv_id),
                            "client_message_id": str(client_msg_id),
                            "message_id": str(stored_msg.id),
                            "seq": stored_msg.seq,
                            "created_at": format_utc_z(stored_msg.created_at),
                            "replayed": is_replayed,
                        }
                    )
                )

                # 2. If newly created, broadcast message.created to all conversation subscribers
                if not is_replayed:
                    event_payload = {
                        "type": "message.created",
                        "conversation_id": str(conv_id),
                        "message": {
                            "id": str(stored_msg.id),
                            "seq": stored_msg.seq,
                            "conversation_id": str(conv_id),
                            "sender": {
                                "id": str(user_id),
                                "username": username,
                            },
                            "content": content,
                            "created_at": format_utc_z(stored_msg.created_at),
                            "client_message_id": str(client_msg_id),
                        },
                    }
                    await manager.broadcast_to_conversation(conv_id, event_payload)

    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as exc:
        logger.error("WebSocket unhandled exception: %s", exc)
        manager.disconnect(websocket)
