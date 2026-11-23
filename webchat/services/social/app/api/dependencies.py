"""Dependencies for Social service routes."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import Depends, Header

from app.adapters.security import verify_service_token, verify_user_token
from app.domain.exceptions import UnauthenticatedError
from app.settings import Settings, get_settings


async def get_current_user_id(
    settings: Annotated[Settings, Depends(get_settings)],
    authorization: Annotated[str | None, Header()] = None,
) -> uuid.UUID:
    """Extract and verify user ID from browser Bearer token (aud=webchat)."""
    if not authorization or not authorization.startswith("Bearer "):
        raise UnauthenticatedError("Missing or invalid Authorization header.")

    token = authorization[len("Bearer ") :].strip()
    payload = verify_user_token(token, settings)

    user_id_str = payload.get("sub")
    if not user_id_str:
        raise UnauthenticatedError("Token missing subject claim.")

    try:
        return uuid.UUID(user_id_str)
    except ValueError as exc:
        raise UnauthenticatedError("Invalid user ID in token claim.") from exc


async def verify_internal_service(
    settings: Annotated[Settings, Depends(get_settings)],
    authorization: Annotated[str | None, Header()] = None,
) -> str:
    """Verify service Bearer token with aud=social-internal."""
    if not authorization or not authorization.startswith("Bearer "):
        raise UnauthenticatedError("Missing or invalid Authorization header.")

    token = authorization[len("Bearer ") :].strip()
    payload = verify_service_token(token, settings)
    return str(payload.get("sub", ""))
