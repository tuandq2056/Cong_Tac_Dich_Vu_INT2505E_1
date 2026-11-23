import uuid

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field

from app.api.errors import register_error_handlers
from app.domain.exceptions import (
    AlreadyFriendsError,
    IncomingRequestExistsError,
)


class SamplePayload(BaseModel):
    name: str = Field(min_length=3, max_length=32)
    member_count: int


@pytest.fixture
def test_app() -> FastAPI:
    app = FastAPI()
    register_error_handlers(app)

    @app.post("/test/validate")
    def test_validate(payload: SamplePayload) -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/test/http-error")
    def test_http_error() -> None:
        raise HTTPException(status_code=401, detail="UNAUTHENTICATED")

    @app.get("/test/domain-error")
    def test_domain_error() -> None:
        raise AlreadyFriendsError("Users are already friends.")

    @app.get("/test/domain-error-related")
    def test_domain_error_related() -> None:
        raise IncomingRequestExistsError(
            related_id="550e8400-e29b-41d4-a716-446655440000",
            message="An incoming friend request from this user already exists.",
        )

    @app.get("/test/crash")
    def test_crash() -> None:
        raise RuntimeError("Simulated social store crash")

    return app


def test_validation_error_format(test_app: FastAPI) -> None:
    client = TestClient(test_app)
    resp = client.post("/test/validate", json={"name": "a"})

    assert resp.status_code == 422
    data = resp.json()

    assert "request_id" in data
    uuid.UUID(data["request_id"])

    err = data["error"]
    assert err["code"] == "VALIDATION_ERROR"
    assert err["message"] == "Request validation failed."
    assert isinstance(err["fields"], list)
    assert len(err["fields"]) >= 1

    for item in err["fields"]:
        assert "field" in item
        assert "reason" in item


def test_http_exception_envelope(test_app: FastAPI) -> None:
    client = TestClient(test_app)
    resp = client.get("/test/http-error")

    assert resp.status_code == 401
    data = resp.json()
    assert "request_id" in data
    assert data["error"]["code"] == "UNAUTHENTICATED"


def test_domain_exception_mapping(test_app: FastAPI) -> None:
    client = TestClient(test_app)
    resp = client.get("/test/domain-error")

    assert resp.status_code == 409
    data = resp.json()
    assert "request_id" in data
    assert data["error"]["code"] == "ALREADY_FRIENDS"
    assert data["error"]["message"] == "Users are already friends."


def test_domain_exception_with_related_id(test_app: FastAPI) -> None:
    client = TestClient(test_app)
    resp = client.get("/test/domain-error-related")

    assert resp.status_code == 409
    data = resp.json()
    assert "request_id" in data
    assert data["error"]["code"] == "INCOMING_REQUEST_EXISTS"
    assert data["error"]["related_id"] == "550e8400-e29b-41d4-a716-446655440000"


def test_zero_bare_500_on_crash(test_app: FastAPI) -> None:
    client = TestClient(test_app, raise_server_exceptions=False)
    resp = client.get("/test/crash")

    assert resp.status_code == 503
    data = resp.json()
    assert "request_id" in data
    uuid.UUID(data["request_id"])
    assert "error" in data
    assert data["error"]["code"] == "SOCIAL_UNAVAILABLE"
    assert "message" in data["error"]
    assert "traceback" not in data
    assert "RuntimeError" not in str(data)


def test_request_id_propagation(test_app: FastAPI) -> None:
    client = TestClient(test_app)
    client_req_id = "550e8400-e29b-41d4-a716-446655440000"
    resp = client.get("/test/http-error", headers={"X-Request-Id": client_req_id})

    assert resp.headers.get("x-request-id") == client_req_id
    assert resp.json()["request_id"] == client_req_id


def test_nginx_hex_request_id_normalization(test_app: FastAPI) -> None:
    client = TestClient(test_app)
    nginx_hex_id = "c7d8bf24623a6c1db05a76c8c430e3bb"
    expected_uuid = "c7d8bf24-623a-6c1d-b05a-76c8c430e3bb"
    resp = client.get("/test/http-error", headers={"X-Request-Id": nginx_hex_id})

    assert resp.headers.get("x-request-id") == expected_uuid
    assert resp.json()["request_id"] == expected_uuid
