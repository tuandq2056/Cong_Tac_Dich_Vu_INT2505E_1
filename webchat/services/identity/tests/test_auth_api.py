"""Comprehensive API tests for Identity service endpoints."""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.adapters.repository import MemoryUserRepository, set_repository
from app.adapters.security import create_access_token
from app.main import create_app
from app.settings import get_settings


@pytest.fixture(autouse=True)
def clean_memory_repo() -> Any:
    repo = MemoryUserRepository()
    set_repository(repo)
    yield
    set_repository(None)


@pytest.fixture
def client() -> TestClient:
    app = create_app()
    return TestClient(app)


def test_register_and_login_flow(client: TestClient) -> None:
    # 1. Register Alice
    reg_resp = client.post(
        "/api/v1/auth/register",
        json={"username": "alice", "password": "password123"},
    )
    assert reg_resp.status_code == 201, reg_resp.text
    data = reg_resp.json()
    assert data["username"] == "alice"
    assert "id" in data
    assert data["created_at"].endswith("Z")
    user_id = data["id"]

    # 2. Case-insensitive collision check
    coll_resp = client.post(
        "/api/v1/auth/register",
        json={"username": "ALICE", "password": "password456"},
    )
    assert coll_resp.status_code == 409
    assert coll_resp.json()["error"]["code"] == "USERNAME_TAKEN"

    # 3. Validation failure
    val_resp = client.post(
        "/api/v1/auth/register",
        json={"username": "a!", "password": "short"},
    )
    assert val_resp.status_code == 422
    assert val_resp.json()["error"]["code"] == "VALIDATION_ERROR"

    # 4. Login Success
    login_resp = client.post(
        "/api/v1/auth/login",
        json={"username": "ALICE", "password": "password123"},
    )
    assert login_resp.status_code == 200
    login_data = login_resp.json()
    token = login_data["access_token"]
    assert login_data["token_type"] == "bearer"
    assert login_data["expires_in"] == 3600
    assert login_data["user"]["id"] == user_id

    # 5. Login Failure
    wrong_pwd_resp = client.post(
        "/api/v1/auth/login",
        json={"username": "alice", "password": "wrongpassword"},
    )
    assert wrong_pwd_resp.status_code == 401
    assert wrong_pwd_resp.json()["error"]["code"] == "INVALID_CREDENTIALS"

    # 6. /users/me with token
    me_resp = client.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert me_resp.status_code == 200
    assert me_resp.json()["username"] == "alice"

    # 7. /users/me without token
    no_auth_resp = client.get("/api/v1/users/me")
    assert no_auth_resp.status_code == 401
    assert no_auth_resp.json()["error"]["code"] == "UNAUTHENTICATED"

    # 8. /users/by-username/{username} lookup
    by_user_resp = client.get(
        "/api/v1/users/by-username/ALICE",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert by_user_resp.status_code == 200
    assert by_user_resp.json()["id"] == user_id

    # 9. Lookup not found
    not_found_resp = client.get(
        "/api/v1/users/by-username/nonexistent_user",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert not_found_resp.status_code == 404
    assert not_found_resp.json()["error"]["code"] == "USER_NOT_FOUND"


def test_internal_user_lookup(client: TestClient) -> None:
    settings = get_settings()

    # Register user first
    reg_resp = client.post(
        "/api/v1/auth/register",
        json={"username": "bob_internal", "password": "password123"},
    )
    user_id = reg_resp.json()["id"]

    # Mint service token
    import time

    import jwt

    now = int(time.time())
    service_token = jwt.encode(
        {"sub": "social", "aud": settings.internal_audience, "iat": now, "exp": now + 3600},
        settings.service_jwt_secret,
        algorithm="HS256",
    )

    # Valid internal call
    internal_resp = client.get(
        f"/internal/v1/users/{user_id}",
        headers={"Authorization": f"Bearer {service_token}"},
    )
    assert internal_resp.status_code == 200
    assert internal_resp.json()["username"] == "bob_internal"

    # Browser token passed to internal route must be rejected
    browser_token = create_access_token(uuid.UUID(user_id), "bob_internal", settings)
    forbidden_resp = client.get(
        f"/internal/v1/users/{user_id}",
        headers={"Authorization": f"Bearer {browser_token}"},
    )
    assert forbidden_resp.status_code in (401, 403)
