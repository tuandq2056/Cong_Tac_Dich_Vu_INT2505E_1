import uuid

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field

from app.api.errors import register_error_handlers
from app.domain.exceptions import (
    ConversationNotFoundError,
    UploadTooLargeError,
)


class SamplePayload(BaseModel):
    message_text: str = Field(min_length=1, max_length=5000)
    seq: int


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
        raise ConversationNotFoundError("Conversation not found.")

    @app.get("/test/domain-upload-large")
    def test_domain_upload_large() -> None:
        raise UploadTooLargeError("Attachment exceeds maximum allowed upload size.")

    @app.get("/test/crash")
    def test_crash() -> None:
        raise RuntimeError("Simulated chat database crash")

    return app


def test_validation_error_format(test_app: FastAPI) -> None:
    client = TestClient(test_app)
    resp = client.post("/test/validate", json={"message_text": ""})

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

    assert resp.status_code == 404
    data = resp.json()
    assert "request_id" in data
    assert data["error"]["code"] == "CONVERSATION_NOT_FOUND"
    assert data["error"]["message"] == "Conversation not found."


def test_domain_exception_upload_too_large(test_app: FastAPI) -> None:
    client = TestClient(test_app)
    resp = client.get("/test/domain-upload-large")

    assert resp.status_code == 413
    data = resp.json()
    assert "request_id" in data
    assert data["error"]["code"] == "UPLOAD_TOO_LARGE"
    assert data["error"]["message"] == "Attachment exceeds maximum allowed upload size."


def test_zero_bare_500_on_crash(test_app: FastAPI) -> None:
    client = TestClient(test_app, raise_server_exceptions=False)
    resp = client.get("/test/crash")

    assert resp.status_code == 503
    data = resp.json()
    assert "request_id" in data
    uuid.UUID(data["request_id"])
    assert "error" in data
    assert data["error"]["code"] == "CHAT_UNAVAILABLE"
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
