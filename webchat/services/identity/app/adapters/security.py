"""Security, hashing and JWT token management for Identity service."""

from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt

from app.domain.exceptions import (
    ServiceForbiddenError,
    UnauthenticatedError,
)
from app.settings import Settings


def hash_password(password: str) -> str:
    """Hash password using PBKDF2-HMAC-SHA256 with random 16-byte salt and 100,000 iterations."""
    salt = secrets.token_bytes(16)
    key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 100_000)
    return f"pbkdf2:sha256:100000${salt.hex()}${key.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    """Verify password against stored PBKDF2 hash using constant-time comparison."""
    try:
        parts = stored_hash.split("$")
        if len(parts) != 3 or not parts[0].startswith("pbkdf2:sha256"):
            return False
        iterations = int(parts[0].split(":")[2])
        salt = bytes.fromhex(parts[1])
        expected_hex = parts[2]
        computed = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
        return hmac.compare_digest(computed.hex(), expected_hex)
    except Exception:
        return False


def create_access_token(
    user_id: uuid.UUID,
    username: str,
    settings: Settings,
    expires_in_seconds: int = 3600,
) -> str:
    """Generate a signed browser JWT token conforming to ADR 0003."""
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "username": username,
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=expires_in_seconds)).timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def verify_user_token(token: str, settings: Settings) -> dict[str, Any]:
    """Verify and decode a browser token (aud=webchat).

    Raises UnauthenticatedError on any validation or expiration failure.
    """
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
    """Verify and decode a service token (aud=identity-internal).

    Raises UnauthenticatedError or ServiceForbiddenError.
    """
    try:
        # First check if someone passed a browser token with wrong audience
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
