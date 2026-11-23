"""Unified error handling and standard ErrorResponse formatter for Chat service."""

from __future__ import annotations

import logging
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.domain.exceptions import (
    AttachmentInUseError,
    AttachmentKindMismatchError,
    AttachmentNotFoundError,
    ChatUnavailableError,
    ClientMessageIdConflictError,
    ConversationNotFoundError,
    DomainError,
    FriendshipRequiredError,
    InvalidAttachmentError,
    InvalidRangeError,
    ReadAheadError,
    ServiceForbiddenError,
    SocialUnavailableError,
    SummaryUnavailableError,
    UnauthenticatedError,
    UnsupportedMediaTypeError,
    UploadTooLargeError,
)

logger = logging.getLogger("webchat.chat")

DOMAIN_ERROR_MAP: dict[type[DomainError], tuple[int, str]] = {
    ConversationNotFoundError: (404, "CONVERSATION_NOT_FOUND"),
    AttachmentNotFoundError: (404, "ATTACHMENT_NOT_FOUND"),
    InvalidAttachmentError: (422, "INVALID_ATTACHMENT"),
    UploadTooLargeError: (413, "UPLOAD_TOO_LARGE"),
    UnsupportedMediaTypeError: (415, "UNSUPPORTED_MEDIA_TYPE"),
    InvalidRangeError: (422, "INVALID_RANGE"),
    ReadAheadError: (422, "READ_AHEAD"),
    SummaryUnavailableError: (503, "SUMMARY_UNAVAILABLE"),
    FriendshipRequiredError: (403, "FRIENDSHIP_REQUIRED"),
    SocialUnavailableError: (503, "SOCIAL_UNAVAILABLE"),
    ChatUnavailableError: (503, "CHAT_UNAVAILABLE"),
    ClientMessageIdConflictError: (409, "CLIENT_MESSAGE_ID_CONFLICT"),
    AttachmentKindMismatchError: (422, "ATTACHMENT_KIND_MISMATCH"),
    AttachmentInUseError: (409, "ATTACHMENT_IN_USE"),
    UnauthenticatedError: (401, "UNAUTHENTICATED"),
    ServiceForbiddenError: (403, "SERVICE_FORBIDDEN"),
}

STATUS_CODE_FALLBACK: dict[int, tuple[str, str]] = {
    400: ("VALIDATION_ERROR", "Bad request."),
    401: ("UNAUTHENTICATED", "Authentication required."),
    403: ("ACTION_FORBIDDEN", "Forbidden."),
    404: ("CONVERSATION_NOT_FOUND", "Resource not found."),
    405: ("ACTION_FORBIDDEN", "Method not allowed."),
    409: ("CLIENT_MESSAGE_ID_CONFLICT", "Conflict."),
    413: ("UPLOAD_TOO_LARGE", "Payload too large."),
    415: ("UNSUPPORTED_MEDIA_TYPE", "Unsupported media type."),
    422: ("VALIDATION_ERROR", "Validation error."),
    503: ("CHAT_UNAVAILABLE", "Chat service unavailable."),
}


def get_request_id(request: Request | None) -> str:
    """Extract a canonical UUID string from request.state, header, or generate new UUID."""
    if request is not None:
        state_id = getattr(request.state, "request_id", None)
        if isinstance(state_id, str) and state_id:
            return state_id
        raw_header = request.headers.get("x-request-id")
        if raw_header:
            try:
                return str(uuid.UUID(raw_header))
            except (ValueError, AttributeError):
                pass
    return str(uuid.uuid4())


def create_error_response(
    request: Request | None,
    status_code: int,
    code: str,
    message: str,
    fields: list[dict[str, str]] | None = None,
    related_id: str | None = None,
) -> JSONResponse:
    """Format an OpenAPI-compliant ErrorResponse JSON with zero extraneous keys."""
    request_id = get_request_id(request)

    error_payload: dict[str, Any] = {
        "code": code,
        "message": message,
    }
    if fields is not None and len(fields) > 0:
        error_payload["fields"] = fields
    if related_id is not None:
        error_payload["related_id"] = related_id

    body = {
        "request_id": request_id,
        "error": error_payload,
    }
    return JSONResponse(
        status_code=status_code,
        content=body,
        headers={"x-request-id": request_id},
        media_type="application/json",
    )


async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    """Map FastAPI RequestValidationError to 422 VALIDATION_ERROR with field details."""
    fields: list[dict[str, str]] = []
    for err in exc.errors():
        loc = err.get("loc", ())
        parts = [str(p) for p in loc if p != "body"]
        field_name = ".".join(parts) if parts else "body"
        msg = str(err.get("msg", "Invalid value"))
        if msg.startswith("Value error, "):
            msg = msg[len("Value error, "):]
        fields.append({"field": field_name, "reason": msg})

    return create_error_response(
        request=request,
        status_code=422,
        code="VALIDATION_ERROR",
        message="Request validation failed.",
        fields=fields,
    )


async def http_exception_handler(
    request: Request,
    exc: StarletteHTTPException,
) -> JSONResponse:
    """Map Starlette/FastAPI HTTPExceptions to OpenAPI ErrorResponse."""
    status_code = exc.status_code
    code: str | None = None
    message: str | None = None
    fields: list[dict[str, str]] | None = None
    related_id: str | None = None

    if isinstance(exc.detail, dict):
        raw_code = exc.detail.get("code")
        if isinstance(raw_code, str):
            code = raw_code
        raw_msg = exc.detail.get("message")
        if isinstance(raw_msg, str):
            message = raw_msg
        raw_fields = exc.detail.get("fields")
        if isinstance(raw_fields, list):
            fields = raw_fields
        raw_related = exc.detail.get("related_id")
        if isinstance(raw_related, str):
            related_id = raw_related
    elif isinstance(exc.detail, str):
        message = exc.detail
        if exc.detail.isupper() and ("_" in exc.detail or exc.detail in ("UNAUTHENTICATED",)):
            code = exc.detail

    if code is None or message is None:
        fb_code, fb_msg = STATUS_CODE_FALLBACK.get(
            status_code, ("CHAT_UNAVAILABLE", "An error occurred.")
        )
        if code is None:
            code = fb_code
        if message is None:
            message = fb_msg

    return create_error_response(
        request=request,
        status_code=status_code,
        code=code,
        message=message,
        fields=fields,
        related_id=related_id,
    )


async def domain_exception_handler(
    request: Request,
    exc: DomainError,
) -> JSONResponse:
    """Map domain exceptions to standard ErrorResponse."""
    status_code, default_code = DOMAIN_ERROR_MAP.get(
        type(exc), (400, "VALIDATION_ERROR")
    )
    code = exc.code or default_code
    related_id = getattr(exc, "related_id", None)
    return create_error_response(
        request=request,
        status_code=status_code,
        code=code,
        message=exc.message or str(exc),
        related_id=related_id,
    )


async def unhandled_exception_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    """Catch-all handler: logs traceback with request_id and returns 503 Zero Bare 500."""
    request_id = get_request_id(request)
    logger.exception(
        "Unhandled exception processing request %s: %s",
        request_id,
        exc,
        extra={"request_id": request_id},
    )
    return create_error_response(
        request=request,
        status_code=503,
        code="CHAT_UNAVAILABLE",
        message="Chat service is temporarily unavailable.",
    )


def register_error_handlers(app: FastAPI) -> None:
    """Register request_id middleware and all standard exception handlers."""

    @app.middleware("http")
    async def request_id_middleware(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        req_id = get_request_id(request)
        request.state.request_id = req_id
        response = await call_next(request)
        response.headers["x-request-id"] = req_id
        return response

    app.add_exception_handler(RequestValidationError, validation_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(DomainError, domain_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, unhandled_exception_handler)
    app.add_exception_handler(500, unhandled_exception_handler)
