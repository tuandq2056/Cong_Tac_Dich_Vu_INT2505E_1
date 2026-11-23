"""User lookup and profile endpoints for Identity service."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path

from app.adapters.repository import UserRepository, get_repository
from app.api.dependencies import get_current_user
from app.api.schemas import PublicUserResponse
from app.domain.exceptions import UserNotFoundError
from app.domain.models import User, normalize_username
from app.settings import Settings, get_settings

router = APIRouter(prefix="/api/v1/users", tags=["Identity"])


@router.get(
    "/me",
    response_model=PublicUserResponse,
    summary="The authenticated user",
)
async def get_me(
    current_user: Annotated[User, Depends(get_current_user)],
) -> PublicUserResponse:
    return PublicUserResponse(
        id=current_user.id,
        username=current_user.username,
    )


@router.get(
    "/by-username/{username}",
    response_model=PublicUserResponse,
    summary="Exact username lookup, case-insensitive",
)
async def get_user_by_username(
    username: Annotated[str, Path(min_length=3, max_length=32)],
    current_user: Annotated[User, Depends(get_current_user)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> PublicUserResponse:
    # Normalize input username
    normalized_name = normalize_username(username)
    repo: UserRepository = await get_repository()
    found = await repo.get_by_username(normalized_name)
    if found is None:
        raise UserNotFoundError(f"User '{username}' not found.")

    user, _ = found
    return PublicUserResponse(
        id=user.id,
        username=user.username,
    )
