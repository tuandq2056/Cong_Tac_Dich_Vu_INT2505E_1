"""Security and JWT token verification for Chat service."""

from __future__ import annotations

from typing import Any

import jwt

from app.domain.exceptions import UnauthenticatedError
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
