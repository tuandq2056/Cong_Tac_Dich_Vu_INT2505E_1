"""Internal service-to-service endpoints for Social service."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends

from app.adapters.repository import SocialRepository, get_social_repository
from app.api.dependencies import verify_internal_service
from app.api.schemas import PermissionsResponse

router = APIRouter(prefix="/internal/v1/conversations", tags=["Internal"])


@router.get(
    "/{conversation_id}/members/{user_id}/permissions",
    response_model=PermissionsResponse,
    summary="Internal check for member conversation permissions",
)
async def get_permissions(
    conversation_id: uuid.UUID,
    user_id: uuid.UUID,
    caller: Annotated[str, Depends(verify_internal_service)],
    repo: Annotated[SocialRepository, Depends(get_social_repository)],
) -> PermissionsResponse:
    can_read, can_send = await repo.get_member_permissions(conv_id=conversation_id, user_id=user_id)
    return PermissionsResponse(can_read=can_read, can_send=can_send)
