"""Comprehensive API and WebSocket tests for Chat service."""

from __future__ import annotations

import io
import time
import uuid
from pathlib import Path
from typing import Any
from unittest.mock import patch

import httpx
import jwt
import pytest
import yaml
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator

from app.adapters.repository import MemoryChatRepository, set_chat_repository
from app.adapters.social_client import SocialClient, set_social_client
from app.main import create_app
from app.settings import get_settings


def make_user_token(user_id: uuid.UUID, username: str) -> str:
    settings = get_settings()
    now = int(time.time())
    payload = {
        "sub": str(user_id),
        "username": username,
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "iat": now,
        "exp": now + 3600,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


@pytest.fixture(autouse=True)
def clean_memory_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    monkeypatch.setattr(get_settings(), "attachment_root", str(tmp_path))
    repo = MemoryChatRepository()
    set_chat_repository(repo)
    yield
    set_chat_repository(None)
    set_social_client(None)


@pytest.fixture
def social_responses() -> dict[str, httpx.Response]:
    responses: dict[str, httpx.Response] = {}
    settings = get_settings()

    def permissions(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        token = request.headers["Authorization"].removeprefix("Bearer ")
        claims = jwt.decode(
            token,
            settings.service_jwt_secret,
            algorithms=["HS256"],
            audience=settings.social_internal_audience,
        )
        assert claims["sub"] == "chat"
        return responses.get(request.url.path, httpx.Response(404))

    set_social_client(SocialClient(settings, transport=httpx.MockTransport(permissions)))
    return responses


def permission_path(room: uuid.UUID, user: uuid.UUID) -> str:
    return f"/internal/v1/conversations/{room}/members/{user}/permissions"


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


def test_chat_rest_lifecycle(client: TestClient, social_responses: dict) -> None:
    user_a = uuid.uuid4()
    outsider = uuid.uuid4()
    conv_id = uuid.uuid4()

    token_a = make_user_token(user_a, "alice")
    token_out = make_user_token(outsider, "outsider")

    headers_a = {"Authorization": f"Bearer {token_a}"}
    headers_out = {"Authorization": f"Bearer {token_out}"}

    social_responses[permission_path(conv_id, user_a)] = httpx.Response(
        200, json={"can_read": True, "can_send": True}
    )

    # 1. Initial message history is empty
    res_history = client.get(
        f"/api/v1/conversations/{conv_id}/messages",
        headers=headers_a,
    )
    assert res_history.status_code == 200
    assert res_history.json()["items"] == []
    assert res_history.json()["has_more"] is False

    # 2. Initial read-state
    res_rs = client.get(
        f"/api/v1/conversations/{conv_id}/read-state",
        headers=headers_a,
    )
    assert res_rs.status_code == 200
    assert res_rs.json()["last_read_seq"] == 0
    assert res_rs.json()["latest_seq"] == 0

    # 3. Upload Audio Attachment
    audio_bytes = b"RIFF....WAVEfmt ...."
    res_audio = client.post(
        f"/api/v1/conversations/{conv_id}/attachments",
        headers=headers_a,
        data={"kind": "audio"},
        files={"file": ("voice.wav", io.BytesIO(audio_bytes), "audio/wav")},
    )
    assert res_audio.status_code == 201
    audio_id = res_audio.json()["id"]

    # 4. Upload File Attachment
    file_bytes = b"Hello, this is a plain text file attachment."
    res_file = client.post(
        f"/api/v1/conversations/{conv_id}/attachments",
        headers=headers_a,
        data={"kind": "file"},
        files={"file": ("readme.txt", io.BytesIO(file_bytes), "text/plain")},
    )
    assert res_file.status_code == 201

    # 5. Download pending audio attachment by uploader
    res_dl = client.get(
        f"/api/v1/conversations/{conv_id}/attachments/{audio_id}/content",
        headers=headers_a,
    )
    assert res_dl.status_code == 200
    assert res_dl.content == audio_bytes

    # 6. Download pending attachment by outsider (404)
    res_dl_out = client.get(
        f"/api/v1/conversations/{conv_id}/attachments/{audio_id}/content",
        headers=headers_out,
    )
    assert res_dl_out.status_code == 404

    # 7. Read ahead check (through_seq > latest_seq (0) -> 422 READ_AHEAD)
    res_read_ahead = client.put(
        f"/api/v1/conversations/{conv_id}/read-state",
        json={"through_seq": 5},
        headers=headers_a,
    )
    assert res_read_ahead.status_code == 422
    assert res_read_ahead.json()["error"]["code"] == "READ_AHEAD"

    # 8. Read state advancement (through_seq=0 is valid)
    res_adv = client.put(
        f"/api/v1/conversations/{conv_id}/read-state",
        json={"through_seq": 0},
        headers=headers_a,
    )
    assert res_adv.status_code == 200

    # 9. Unread summary on empty
    res_summary = client.post(
        f"/api/v1/conversations/{conv_id}/unread-summary",
        headers=headers_a,
    )
    assert res_summary.status_code == 200
    assert res_summary.json()["status"] == "empty"
    assert res_summary.json()["summary"] is None

    # 10. Search messages
    res_search = client.get(
        f"/api/v1/conversations/{conv_id}/messages/search?q=test",
        headers=headers_a,
    )
    assert res_search.status_code == 200
    assert res_search.json()["items"] == []

    # 11. Search validation failure on empty query
    res_search_empty = client.get(
        f"/api/v1/conversations/{conv_id}/messages/search?q=",
        headers=headers_a,
    )
    assert res_search_empty.status_code == 422


CONTRACT = yaml.safe_load(
    (Path(__file__).resolve().parents[3] / "contracts/asyncapi.yaml").read_text(encoding="utf8")
)


def validate_frame(frame: dict, name: str) -> None:
    schema = {"$ref": f"#/components/schemas/{name}", "components": CONTRACT["components"]}
    Draft202012Validator(schema, format_checker=Draft202012Validator.FORMAT_CHECKER).validate(frame)


def test_chat_websocket_workflow(client: TestClient, social_responses: dict) -> None:
    user = uuid.uuid4()
    room = uuid.uuid4()
    other_room = uuid.uuid4()
    path = permission_path(room, user)
    allowed = httpx.Response(200, json={"can_read": True, "can_send": True})
    social_responses[path] = allowed
    token = make_user_token(user, "alice")

    with client.websocket_connect("/ws/v1/chat") as ws:

        def command(schema: str, event: str, reply: str, **fields: Any) -> dict:
            request_id = str(uuid.uuid4())
            frame = {"type": event, "request_id": request_id, **fields}
            validate_frame(frame, schema)
            ws.send_json(frame)
            result = ws.receive_json()
            validate_frame(result, reply)
            assert result["request_id"] == request_id
            return result

        ready = command(
            "SessionAuthenticate", "session.authenticate", "SessionReady", access_token=token
        )
        assert ready["user_id"] == str(user)
        fields = dict(
            conversation_id=str(room),
            client_message_id=str(uuid.uuid4()),
            content={"type": "text", "text": "Hello WebSocket world!"},
        )
        error = command("MessageSend", "message.send", "ErrorFrame", **fields)
        assert error["code"] == "NOT_SUBSCRIBED"
        sub = command(
            "ConversationSubscribe",
            "conversation.subscribe",
            "ConversationSubscribed",
            conversation_id=str(room),
        )
        assert sub["latest_seq"] == 0

        social_responses[path] = httpx.Response(503)
        error = command("MessageSend", "message.send", "ErrorFrame", **fields)
        assert (error["code"], error["retryable"]) == ("SOCIAL_UNAVAILABLE", True)
        social_responses[path] = httpx.Response(200, json={"can_read": True, "can_send": False})
        error = command("MessageSend", "message.send", "ErrorFrame", **fields)
        assert error["code"] == "FRIENDSHIP_REQUIRED"

        social_responses[path] = allowed
        with patch.object(
            MemoryChatRepository, "send_message", side_effect=OSError("write failed")
        ):
            error = command("MessageSend", "message.send", "ErrorFrame", **fields)
            assert (error["code"], error["retryable"]) == ("CHAT_UNAVAILABLE", True)
        ack = command("MessageSend", "message.send", "MessageAck", **fields)
        message = ack["message"]
        assert not ack["replayed"]
        assert message["seq"] == 1
        assert message["sender"] == {"id": str(user), "username": "alice"}
        assert message["client_message_id"] == fields["client_message_id"]
        assert message["content"] == fields["content"]
        created = ws.receive_json()
        validate_frame(created, "MessageCreated")
        assert created["message"] == message
        replay = command("MessageSend", "message.send", "MessageAck", **fields)
        assert replay["replayed"] and replay["message"] == message

        denied = command(
            "ConversationSubscribe",
            "conversation.subscribe",
            "ErrorFrame",
            conversation_id=str(other_room),
        )
        assert denied["code"] == "CONVERSATION_NOT_FOUND"
        social_responses[permission_path(other_room, user)] = allowed
        command(
            "ConversationSubscribe",
            "conversation.subscribe",
            "ConversationSubscribed",
            conversation_id=str(other_room),
        )
        fields["conversation_id"] = str(other_room)
        conflict = command("MessageSend", "message.send", "ErrorFrame", **fields)
        assert conflict["code"] == "CLIENT_MESSAGE_ID_CONFLICT"
        command(
            "ConversationUnsubscribe",
            "conversation.unsubscribe",
            "ConversationUnsubscribed",
            conversation_id=str(room),
        )

    history = client.get(
        f"/api/v1/conversations/{room}/messages", headers={"Authorization": f"Bearer {token}"}
    )
    assert history.json()["items"] == [message]


def test_asyncapi_payload_examples() -> None:
    for name, definition in CONTRACT["components"]["messages"].items():
        for example in definition.get("examples", []):
            validate_frame(example["payload"], name)
