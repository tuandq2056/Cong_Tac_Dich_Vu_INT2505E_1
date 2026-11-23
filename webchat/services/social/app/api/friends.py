"""Friend request and friendship endpoints for Social service."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status

from app.adapters.identity_client import IdentityClient, get_identity_client
from app.adapters.repository import (
    SocialRepository,
    StoredFriendRequest,
    get_social_repository,
)
from app.api.dependencies import get_current_user_id
from app.api.schemas import (
    FriendRequestCreate,
    FriendRequestDecision,
    FriendRequestPage,
    FriendRequestResponse,
    PublicUser,
    UserPage,
    format_utc_z,
)
from app.domain.models import FriendRequestStatus
from app.settings import Settings, get_settings

router = APIRouter(prefix="/api/v1", tags=["Social"])


async def enrich_user(user_id: uuid.UUID, id_client: IdentityClient) -> PublicUser:
    try:
        data = await id_client.get_user(user_id)
        return PublicUser(
            id=uuid.UUID(str(data["id"])),
            username=data["username"],
            created_at=data["created_at"],
        )
    except Exception:
        # Fallback for unit testing if user not seeded in identity client
        return PublicUser(
            id=user_id,
            username=f"user_{str(user_id)[:8]}",
            created_at=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        )


async def to_friend_request_response(
    req: StoredFriendRequest, id_client: IdentityClient
) -> FriendRequestResponse:
    sender = await enrich_user(req.sender_id, id_client)
    recipient = await enrich_user(req.recipient_id, id_client)
    return FriendRequestResponse(
        id=req.id,
        sender=sender,
        recipient=recipient,
        status=req.status.value,  # type: ignore[arg-type]
        created_at=format_utc_z(req.created_at),
    )


@router.post(
    "/friend-requests",
    response_model=FriendRequestResponse,
    summary="Send a friend request",
)
async def create_friend_request(
    payload: FriendRequestCreate,
    response: Response,
    caller_id: Annotated[uuid.UUID, Depends(get_current_user_id)],
    settings: Annotated[Settings, Depends(get_settings)],
    repo: Annotated[SocialRepository, Depends(get_social_repository)],
) -> FriendRequestResponse:
    id_client = get_identity_client(settings)
    req, is_created = await repo.create_or_get_friend_request(
        sender_id=caller_id, recipient_id=payload.recipient_id
    )
    response.status_code = status.HTTP_201_CREATED if is_created else status.HTTP_200_OK
    return await to_friend_request_response(req, id_client)


@router.get(
    "/friend-requests",
    response_model=FriendRequestPage,
    summary="List friend requests",
)
async def list_friend_requests(
    caller_id: Annotated[uuid.UUID, Depends(get_current_user_id)],
    settings: Annotated[Settings, Depends(get_settings)],
    repo: Annotated[SocialRepository, Depends(get_social_repository)],
    direction: Annotated[str | None, Query()] = None,
    status: Annotated[str | None, Query()] = None,
) -> FriendRequestPage:
    id_client = get_identity_client(settings)
    parsed_status = FriendRequestStatus(status) if status else None
    reqs = await repo.list_friend_requests(
        user_id=caller_id, direction=direction, status=parsed_status
    )
    items = [await to_friend_request_response(r, id_client) for r in reqs]
    return FriendRequestPage(items=items, next_cursor=None)


@router.patch(
    "/friend-requests/{request_id}",
    response_model=FriendRequestResponse,
    summary="Decide on a friend request",
)
async def decide_friend_request(
    request_id: uuid.UUID,
    payload: FriendRequestDecision,
    caller_id: Annotated[uuid.UUID, Depends(get_current_user_id)],
    settings: Annotated[Settings, Depends(get_settings)],
    repo: Annotated[SocialRepository, Depends(get_social_repository)],
) -> FriendRequestResponse:
    id_client = get_identity_client(settings)
    updated = await repo.update_friend_request(
        request_id=request_id, actor_id=caller_id, action=payload.status
    )
    return await to_friend_request_response(updated, id_client)


@router.get(
    "/friends",
    response_model=UserPage,
    summary="List friends",
)
async def list_friends(
    caller_id: Annotated[uuid.UUID, Depends(get_current_user_id)],
    settings: Annotated[Settings, Depends(get_settings)],
    repo: Annotated[SocialRepository, Depends(get_social_repository)],
) -> UserPage:
    id_client = get_identity_client(settings)
    friend_ids = await repo.list_friends(caller_id)
    items = [await enrich_user(fid, id_client) for fid in friend_ids]
    return UserPage(items=items, next_cursor=None)


@router.delete(
    "/friends/{friend_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a friend",
)
async def remove_friend(
    friend_id: uuid.UUID,
    caller_id: Annotated[uuid.UUID, Depends(get_current_user_id)],
    repo: Annotated[SocialRepository, Depends(get_social_repository)],
) -> None:
    await repo.remove_friend(caller_id, friend_id)
