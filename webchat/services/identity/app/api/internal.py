"""Internal service-to-service endpoints for Identity service."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Path

from app.adapters.repository import UserRepository, get_repository
from app.api.dependencies import verify_internal_service
from app.api.schemas import PublicUserResponse, format_utc_z
from app.domain.exceptions import UserNotFoundError
from app.settings import Settings, get_settings

router = APIRouter(prefix="/internal/v1/users", tags=["Internal"])


@router.get(
    "/{user_id}",
    response_model=PublicUserResponse,
    summary="Internal lookup by user id",
)
async def internal_get_user(
    user_id: Annotated[uuid.UUID, Path(...)],
    caller: Annotated[str, Depends(verify_internal_service)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> PublicUserResponse:
    repo: UserRepository = await get_repository()
    found = await repo.get_by_id(user_id)
    if found is None:
        raise UserNotFoundError(f"User with ID '{user_id}' not found.")

    user, _ = found
    return PublicUserResponse(
        id=user.id,
        username=user.username,
        created_at=format_utc_z(user.created_at),
    )
