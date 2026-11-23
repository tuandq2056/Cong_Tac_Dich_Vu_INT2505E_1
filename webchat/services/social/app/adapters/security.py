"""Security and JWT token verification for Social service."""

from __future__ import annotations

from typing import Any

import jwt

from app.domain.exceptions import ServiceForbiddenError, UnauthenticatedError
from app.settings import Settings


def verify_user_token(token: str, settings: Settings) -> dict[str, Any]:
    """Verify browser JWT token (aud=webchat)."""
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=["HS256"],
            issuer=settings.jwt_issuer,
            audience=settings.jwt_audience,
            options={"require": ["exp", "iat", "sub", "aud", "iss"]},
        )
        return payload
    except jwt.PyJWTError as exc:
        raise UnauthenticatedError("Invalid or expired authentication token.") from exc


def verify_service_token(token: str, settings: Settings) -> dict[str, Any]:
    """Verify service JWT token (aud=social-internal)."""
    try:
        unverified = jwt.decode(token, options={"verify_signature": False})
        if unverified.get("aud") == settings.jwt_audience:
            raise ServiceForbiddenError("Browser token cannot be used for internal endpoints.")
    except jwt.PyJWTError:
        pass

    try:
        payload = jwt.decode(
            token,
            settings.service_jwt_secret,
            algorithms=["HS256"],
            audience=settings.internal_audience,
            options={"require": ["exp", "iat", "sub", "aud"]},
        )
        return payload
    except jwt.PyJWTError as exc:
        raise UnauthenticatedError("Invalid or expired service token.") from exc
