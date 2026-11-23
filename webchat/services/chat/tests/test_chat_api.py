"""Comprehensive API and WebSocket tests for Chat service."""

from __future__ import annotations

import io
import time
import uuid
from typing import Any

import jwt
import pytest
from fastapi.testclient import TestClient

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
def clean_memory_repo() -> Any:
    repo = MemoryChatRepository()
    set_chat_repository(repo)
    social = SocialClient(get_settings())
    set_social_client(social)
    yield
    set_chat_repository(None)
    set_social_client(None)


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


def test_chat_rest_lifecycle(client: TestClient) -> None:
    user_a = uuid.uuid4()
    outsider = uuid.uuid4()
    conv_id = uuid.uuid4()

    token_a = make_user_token(user_a, "alice")
    token_out = make_user_token(outsider, "outsider")

    headers_a = {"Authorization": f"Bearer {token_a}"}
    headers_out = {"Authorization": f"Bearer {token_out}"}

    # Seed permission: user_a has read/send in conv_id
    from app.adapters.social_client import get_social_client

    social = get_social_client()
    social.set_permission(conv_id, user_a, can_read=True, can_send=True)
    social.set_permission(conv_id, outsider, can_read=False, can_send=False)

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


def test_chat_websocket_workflow(client: TestClient) -> None:
    user_a = uuid.uuid4()
    conv_id = uuid.uuid4()
    token_a = make_user_token(user_a, "alice")

    from app.adapters.social_client import get_social_client

    social = get_social_client()
    social.set_permission(conv_id, user_a, can_read=True, can_send=True)

    with client.websocket_connect("/ws/v1/chat") as ws:
        # 1. Authenticate
        ws.send_json({"type": "session.authenticate", "token": token_a})
        auth_ack = ws.receive_json()
        assert auth_ack["type"] == "session.ready"
        assert auth_ack["user_id"] == str(user_a)

        # 2. Subscribe
        ws.send_json({"type": "conversation.subscribe", "conversation_id": str(conv_id)})
        sub_ack = ws.receive_json()
        assert sub_ack["type"] == "conversation.subscribed"
        assert sub_ack["conversation_id"] == str(conv_id)
        assert sub_ack["latest_seq"] == 0

        # 3. Send message
        client_msg_id = str(uuid.uuid4())
        ws.send_json(
            {
                "type": "message.send",
                "conversation_id": str(conv_id),
                "client_message_id": client_msg_id,
                "content": {"type": "text", "text": "Hello WebSocket world!"},
            }
        )

        ack = ws.receive_json()
        assert ack["type"] == "message.ack"
        assert ack["seq"] == 1
        assert ack["replayed"] is False

        # Also receive broadcast message.created
        created_event = ws.receive_json()
        assert created_event["type"] == "message.created"
        assert created_event["message"]["seq"] == 1
        assert created_event["message"]["content"]["text"] == "Hello WebSocket world!"

        # 4. Replay message.send (idempotent)
        ws.send_json(
            {
                "type": "message.send",
                "conversation_id": str(conv_id),
                "client_message_id": client_msg_id,
                "content": {"type": "text", "text": "Hello WebSocket world!"},
            }
        )
        replay_ack = ws.receive_json()
        assert replay_ack["type"] == "message.ack"
        assert replay_ack["seq"] == 1
        assert replay_ack["replayed"] is True

        # 5. Unsubscribe
        ws.send_json({"type": "conversation.unsubscribe", "conversation_id": str(conv_id)})
        unsub_ack = ws.receive_json()
        assert unsub_ack["type"] == "conversation.unsubscribed"
