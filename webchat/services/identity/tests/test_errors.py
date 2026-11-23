import uuid

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field

from app.api.errors import register_error_handlers
from app.domain.exceptions import (
    UsernameTakenError,
    UserNotFoundError,
)


class SamplePayload(BaseModel):
    username: str = Field(min_length=3, max_length=32)
    age: int


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
        raise UsernameTakenError("Username already in use.")

    @app.get("/test/user-not-found")
    def test_user_not_found() -> None:
        raise UserNotFoundError("User not found.")

    @app.get("/test/crash")
    def test_crash() -> None:
        raise RuntimeError("Simulated database crash")

    return app


def test_validation_error_format(test_app: FastAPI) -> None:
    client = TestClient(test_app)
    # Send invalid body: username too short, age missing
    resp = client.post("/test/validate", json={"username": "a"})

    assert resp.status_code == 422
    data = resp.json()

    # Must contain request_id as valid UUID
    assert "request_id" in data
    uuid.UUID(data["request_id"])

    # Error envelope verification
    err = data["error"]
    assert err["code"] == "VALIDATION_ERROR"
    assert err["message"] == "Request validation failed."
    assert isinstance(err["fields"], list)
    assert len(err["fields"]) >= 1

    field_names = [f["field"] for f in err["fields"]]
    assert "username" in field_names or "age" in field_names
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
    assert data["error"]["code"] == "USERNAME_TAKEN"
    assert data["error"]["message"] == "Username already in use."


def test_user_not_found_domain_mapping(test_app: FastAPI) -> None:
    client = TestClient(test_app)
    resp = client.get("/test/user-not-found")

    assert resp.status_code == 404
    data = resp.json()
    assert "request_id" in data
    assert data["error"]["code"] == "USER_NOT_FOUND"
    assert data["error"]["message"] == "User not found."


def test_zero_bare_500_on_crash(test_app: FastAPI) -> None:
    client = TestClient(test_app, raise_server_exceptions=False)
    resp = client.get("/test/crash")

    # Zero Bare 500: Returns 503 strictly in ErrorResponse schema
    assert resp.status_code == 503
    data = resp.json()
    assert "request_id" in data
    uuid.UUID(data["request_id"])
    assert "error" in data
    assert "code" in data["error"]
    assert data["error"]["code"] == "IDENTITY_UNAVAILABLE"
    assert "message" in data["error"]
    # Ensures traceback is NOT leaked in JSON response body
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
