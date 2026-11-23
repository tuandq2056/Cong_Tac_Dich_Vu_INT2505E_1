"""Dependencies for Identity HTTP routes."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import Depends, Header

from app.adapters.repository import UserRepository, get_repository
from app.adapters.security import verify_service_token, verify_user_token
from app.domain.exceptions import UnauthenticatedError
from app.domain.models import User
from app.settings import Settings, get_settings


async def get_current_user(
    settings: Annotated[Settings, Depends(get_settings)],
    repo: Annotated[UserRepository, Depends(get_repository)],
    authorization: Annotated[str | None, Header()] = None,
) -> User:
    """Extract and verify user from Bearer token (aud=webchat)."""
    if not authorization or not authorization.startswith("Bearer "):
        raise UnauthenticatedError("Missing or invalid Authorization header.")

    token = authorization[len("Bearer ") :].strip()
    payload = verify_user_token(token, settings)

    user_id_str = payload.get("sub")
    if not user_id_str:
        raise UnauthenticatedError("Token missing subject claim.")

    try:
        user_id = uuid.UUID(user_id_str)
    except ValueError as exc:
        raise UnauthenticatedError("Invalid user ID in token claim.") from exc

    found = await repo.get_by_id(user_id)
    if found is None:
        raise UnauthenticatedError("User corresponding to token subject not found.")

    user, _ = found
    return user


async def verify_internal_service(
    settings: Annotated[Settings, Depends(get_settings)],
    authorization: Annotated[str | None, Header()] = None,
) -> str:
    """Verify that caller has valid service token with aud=identity-internal.

    Returns the caller service name (from sub claim).
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise UnauthenticatedError("Missing or invalid Authorization header.")

    token = authorization[len("Bearer ") :].strip()
    payload = verify_service_token(token, settings)
    return str(payload.get("sub", ""))
