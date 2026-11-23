"""Comprehensive API tests for Social service endpoints."""

from __future__ import annotations

import time
import uuid
from typing import Any

import jwt
import pytest
from fastapi.testclient import TestClient

from app.adapters.identity_client import (
    IdentityClient,
    get_identity_client,
    set_identity_client,
)
from app.adapters.repository import MemorySocialRepository, set_social_repository
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


def make_service_token(sub: str = "chat") -> str:
    settings = get_settings()
    now = int(time.time())
    payload = {
        "sub": sub,
        "aud": settings.internal_audience,
        "iat": now,
        "exp": now + 3600,
    }
    return jwt.encode(payload, settings.service_jwt_secret, algorithm="HS256")


@pytest.fixture(autouse=True)
def clean_memory_repo() -> Any:
    repo = MemorySocialRepository()
    set_social_repository(repo)
    settings = get_settings()
    id_client = IdentityClient(settings)
    set_identity_client(id_client)
    yield
    set_social_repository(None)
    set_identity_client(None)


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


def test_social_friend_and_conversation_lifecycle(client: TestClient) -> None:
    user_a = uuid.uuid4()
    user_b = uuid.uuid4()
    user_c = uuid.uuid4()
    outsider = uuid.uuid4()

    token_a = make_user_token(user_a, "alice")
    token_b = make_user_token(user_b, "bob")
    token_c = make_user_token(user_c, "charlie")
    token_out = make_user_token(outsider, "outsider")

    headers_a = {"Authorization": f"Bearer {token_a}"}
    headers_b = {"Authorization": f"Bearer {token_b}"}
    headers_c = {"Authorization": f"Bearer {token_c}"}
    headers_out = {"Authorization": f"Bearer {token_out}"}

    from datetime import UTC, datetime

    id_client = get_identity_client()
    now = datetime.now(UTC)
    id_client.set_user_cache(user_a, "alice", now)
    id_client.set_user_cache(user_b, "bob", now)
    id_client.set_user_cache(user_c, "charlie", now)
    id_client.set_user_cache(outsider, "outsider", now)

    # 1. Self invite error
    res_self = client.post(
        "/api/v1/friend-requests",
        json={"recipient_id": str(user_a)},
        headers=headers_a,
    )
    assert res_self.status_code == 422
    assert res_self.json()["error"]["code"] == "SELF_INVITE"

    # 2. Send request A -> B
    res_ab = client.post(
        "/api/v1/friend-requests",
        json={"recipient_id": str(user_b)},
        headers=headers_a,
    )
    assert res_ab.status_code == 201
    ab_id = res_ab.json()["id"]

    # 3. Idempotent resend A -> B
    res_ab_resend = client.post(
        "/api/v1/friend-requests",
        json={"recipient_id": str(user_b)},
        headers=headers_a,
    )
    assert res_ab_resend.status_code == 200
    assert res_ab_resend.json()["id"] == ab_id

    # 4. Reverse request B -> A conflict
    res_ba = client.post(
        "/api/v1/friend-requests",
        json={"recipient_id": str(user_a)},
        headers=headers_b,
    )
    assert res_ba.status_code == 409
    assert res_ba.json()["error"]["code"] == "INCOMING_REQUEST_EXISTS"

    # 5. List incoming requests for B
    res_list_b = client.get(
        "/api/v1/friend-requests?direction=incoming&status=pending",
        headers=headers_b,
    )
    assert res_list_b.status_code == 200
    assert len(res_list_b.json()["items"]) == 1

    # 6. Accept by B
    res_accept = client.patch(
        f"/api/v1/friend-requests/{ab_id}",
        json={"status": "accepted"},
        headers=headers_b,
    )
    assert res_accept.status_code == 200
    assert res_accept.json()["status"] == "accepted"

    # 7. Replay accept by B
    res_accept_replay = client.patch(
        f"/api/v1/friend-requests/{ab_id}",
        json={"status": "accepted"},
        headers=headers_b,
    )
    assert res_accept_replay.status_code == 200

    # 8. Cancel already accepted request conflict
    res_cancel_conflict = client.patch(
        f"/api/v1/friend-requests/{ab_id}",
        json={"status": "cancelled"},
        headers=headers_a,
    )
    assert res_cancel_conflict.status_code == 409
    assert res_cancel_conflict.json()["error"]["code"] == "REQUEST_CLOSED"

    # 9. List friends for A and B
    res_friends_a = client.get("/api/v1/friends", headers=headers_a)
    assert res_friends_a.status_code == 200
    assert len(res_friends_a.json()["items"]) == 1

    # Connect A and C as friends too
    res_ac = client.post(
        "/api/v1/friend-requests",
        json={"recipient_id": str(user_c)},
        headers=headers_a,
    )
    client.patch(
        f"/api/v1/friend-requests/{res_ac.json()['id']}",
        json={"status": "accepted"},
        headers=headers_c,
    )

    # 10. Direct conversation A -> B
    res_dir = client.put(f"/api/v1/conversations/direct/{user_b}", headers=headers_a)
    assert res_dir.status_code == 201
    direct_id = res_dir.json()["id"]

    # 11. Replay direct B -> A
    res_dir_replay = client.put(f"/api/v1/conversations/direct/{user_a}", headers=headers_b)
    assert res_dir_replay.status_code == 200
    assert res_dir_replay.json()["id"] == direct_id

    # 12. Direct conversation with outsider (not friend)
    res_dir_fail = client.put(f"/api/v1/conversations/direct/{outsider}", headers=headers_a)
    assert res_dir_fail.status_code == 403
    assert res_dir_fail.json()["error"]["code"] == "FRIENDSHIP_REQUIRED"

    # 13. Direct conversation self
    res_dir_self = client.put(f"/api/v1/conversations/direct/{user_a}", headers=headers_a)
    assert res_dir_self.status_code == 422
    assert res_dir_self.json()["error"]["code"] == "SELF_CONVERSATION"

    # 14. Create Group conversation
    idemp_key = str(uuid.uuid4())
    group_payload = {
        "name": "Dev Team",
        "member_ids": [str(user_b), str(user_c)],
    }
    res_grp = client.post(
        "/api/v1/conversations/groups",
        json=group_payload,
        headers={**headers_a, "Idempotency-Key": idemp_key},
    )
    assert res_grp.status_code == 201
    group_id = res_grp.json()["id"]
    assert res_grp.json()["member_count"] == 3

    # 15. Replay Group creation
    res_grp_replay = client.post(
        "/api/v1/conversations/groups",
        json=group_payload,
        headers={**headers_a, "Idempotency-Key": idemp_key},
    )
    assert res_grp_replay.status_code == 200
    assert res_grp_replay.json()["id"] == group_id

    # 16. Idempotency conflict
    res_grp_conflict = client.post(
        "/api/v1/conversations/groups",
        json={"name": "Different Name", "member_ids": [str(user_b), str(user_c)]},
        headers={**headers_a, "Idempotency-Key": idemp_key},
    )
    assert res_grp_conflict.status_code == 409
    assert res_grp_conflict.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"

    # 17. List conversations for A
    res_convs = client.get("/api/v1/conversations", headers=headers_a)
    assert res_convs.status_code == 200
    assert len(res_convs.json()["items"]) == 2

    # 18. Get group conversation details
    res_grp_det = client.get(f"/api/v1/conversations/{group_id}", headers=headers_a)
    assert res_grp_det.status_code == 200
    assert res_grp_det.json()["name"] == "Dev Team"

    # 19. List members
    res_mem = client.get(f"/api/v1/conversations/{group_id}/members", headers=headers_a)
    assert res_mem.status_code == 200
    assert len(res_mem.json()["items"]) == 3

    # 20. Outsider isolation (404)
    res_out = client.get(f"/api/v1/conversations/{group_id}", headers=headers_out)
    assert res_out.status_code == 404
    assert res_out.json()["error"]["code"] == "CONVERSATION_NOT_FOUND"

    # 21. Internal permissions check
    service_tok = make_service_token("chat")
    perm_mem = client.get(
        f"/internal/v1/conversations/{group_id}/members/{user_a}/permissions",
        headers={"Authorization": f"Bearer {service_tok}"},
    )
    assert perm_mem.status_code == 200
    assert perm_mem.json() == {"can_read": True, "can_send": True}

    perm_out = client.get(
        f"/internal/v1/conversations/{group_id}/members/{outsider}/permissions",
        headers={"Authorization": f"Bearer {service_tok}"},
    )
    assert perm_out.status_code == 200
    assert perm_out.json() == {"can_read": False, "can_send": False}

    # 22. Remove friend C
    res_del = client.delete(f"/api/v1/friends/{user_c}", headers=headers_a)
    assert res_del.status_code == 204
