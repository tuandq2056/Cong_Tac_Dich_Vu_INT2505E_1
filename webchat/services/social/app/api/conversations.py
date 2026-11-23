"""Conversation endpoints (direct and group) for Social service."""

from __future__ import annotations

import hashlib
import json
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Response, status

from app.adapters.identity_client import IdentityClient, get_identity_client
from app.adapters.repository import (
    SocialRepository,
    StoredConversation,
    get_social_repository,
)
from app.api.dependencies import get_current_user_id
from app.api.friends import enrich_user
from app.api.schemas import (
    ConversationPage,
    DirectConversationResponse,
    GroupConversationResponse,
    GroupCreate,
    UserPage,
    format_utc_z,
)
from app.domain.exceptions import DomainError
from app.settings import Settings, get_settings

router = APIRouter(prefix="/api/v1/conversations", tags=["Social"])


def compute_request_hash(data: dict) -> str:
    serialized = json.dumps(data, sort_keys=True)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


async def to_conversation_response(
    conv: StoredConversation,
    peer_id: uuid.UUID | None,
    id_client: IdentityClient,
) -> DirectConversationResponse | GroupConversationResponse:
    if conv.type == "direct":
        peer_user = await enrich_user(peer_id or conv.id, id_client)
        return DirectConversationResponse(
            id=conv.id,
            type="direct",
            peer=peer_user,
            created_at=format_utc_z(conv.created_at),
        )
    creator_user = (
        await enrich_user(conv.created_by, id_client)
        if conv.created_by
        else await enrich_user(conv.id, id_client)
    )
    return GroupConversationResponse(
        id=conv.id,
        type="group",
        name=conv.name or "Group",
        created_by=creator_user,
        member_count=conv.member_count,
        created_at=format_utc_z(conv.created_at),
    )


@router.put(
    "/direct/{friend_id}",
    response_model=DirectConversationResponse,
    summary="Get or create a direct conversation",
)
async def put_direct_conversation(
    friend_id: uuid.UUID,
    response: Response,
    caller_id: Annotated[uuid.UUID, Depends(get_current_user_id)],
    settings: Annotated[Settings, Depends(get_settings)],
    repo: Annotated[SocialRepository, Depends(get_social_repository)],
) -> DirectConversationResponse:
    id_client = get_identity_client(settings)
    conv, peer_id, is_created = await repo.get_or_create_direct_conversation(
        user_a=caller_id, user_b=friend_id
    )
    response.status_code = status.HTTP_201_CREATED if is_created else status.HTTP_200_OK
    peer_user = await enrich_user(peer_id, id_client)
    return DirectConversationResponse(
        id=conv.id,
        type="direct",
        peer=peer_user,
        created_at=format_utc_z(conv.created_at),
    )


@router.post(
    "/groups",
    response_model=GroupConversationResponse,
    summary="Create a group conversation",
)
async def create_group_conversation(
    payload: GroupCreate,
    response: Response,
    caller_id: Annotated[uuid.UUID, Depends(get_current_user_id)],
    settings: Annotated[Settings, Depends(get_settings)],
    repo: Annotated[SocialRepository, Depends(get_social_repository)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> GroupConversationResponse:
    if not idempotency_key:
        raise DomainError("Missing required Idempotency-Key header.", code="VALIDATION_ERROR")

    # Hash the payload
    req_hash = compute_request_hash(
        {"name": payload.name, "member_ids": [str(m) for m in payload.member_ids]}
    )

    id_client = get_identity_client(settings)
    status_code, body = await repo.create_group_conversation(
        creator_id=caller_id,
        idempotency_key=idempotency_key,
        name=payload.name,
        member_ids=payload.member_ids,
        request_hash=req_hash,
    )
    response.status_code = status_code
    creator_user = await enrich_user(caller_id, id_client)

    return GroupConversationResponse(
        id=uuid.UUID(body["id"]),
        type="group",
        name=body["name"],
        created_by=creator_user,
        member_count=body["member_count"],
        created_at=body["created_at"],
    )


@router.get(
    "",
    response_model=ConversationPage,
    summary="List conversations",
)
async def list_conversations(
    caller_id: Annotated[uuid.UUID, Depends(get_current_user_id)],
    settings: Annotated[Settings, Depends(get_settings)],
    repo: Annotated[SocialRepository, Depends(get_social_repository)],
) -> ConversationPage:
    id_client = get_identity_client(settings)
    pairs = await repo.list_conversations_for_user(caller_id)
    items = [await to_conversation_response(c, p, id_client) for c, p in pairs]
    return ConversationPage(items=items, next_cursor=None)


@router.get(
    "/{conversation_id}",
    response_model=DirectConversationResponse | GroupConversationResponse,
    summary="Get conversation details",
)
async def get_conversation(
    conversation_id: uuid.UUID,
    caller_id: Annotated[uuid.UUID, Depends(get_current_user_id)],
    settings: Annotated[Settings, Depends(get_settings)],
    repo: Annotated[SocialRepository, Depends(get_social_repository)],
) -> DirectConversationResponse | GroupConversationResponse:
    id_client = get_identity_client(settings)
    conv, peer_id = await repo.get_conversation(conv_id=conversation_id, requester_id=caller_id)
    return await to_conversation_response(conv, peer_id, id_client)


@router.get(
    "/{conversation_id}/members",
    response_model=UserPage,
    summary="List members of a conversation",
)
async def list_members(
    conversation_id: uuid.UUID,
    caller_id: Annotated[uuid.UUID, Depends(get_current_user_id)],
    settings: Annotated[Settings, Depends(get_settings)],
    repo: Annotated[SocialRepository, Depends(get_social_repository)],
) -> UserPage:
    id_client = get_identity_client(settings)
    member_ids = await repo.get_conversation_members(
        conv_id=conversation_id, requester_id=caller_id
    )
    items = [await enrich_user(m, id_client) for m in member_ids]
    return UserPage(items=items, next_cursor=None)
