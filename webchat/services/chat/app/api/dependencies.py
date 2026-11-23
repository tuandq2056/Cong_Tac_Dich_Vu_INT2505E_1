"""Dependencies for Chat service routes."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import Depends, Header

from app.adapters.security import verify_user_token
from app.adapters.social_client import SocialClient
from app.domain.exceptions import (
    ConversationNotFoundError,
    FriendshipRequiredError,
    UnauthenticatedError,
)
from app.settings import Settings, get_settings


async def get_current_user(
    settings: Annotated[Settings, Depends(get_settings)],
    authorization: Annotated[str | None, Header()] = None,
) -> tuple[uuid.UUID, str]:
    """Extract and verify user ID and username from Bearer token (aud=webchat)."""
    if not authorization or not authorization.startswith("Bearer "):
        raise UnauthenticatedError("Missing or invalid Authorization header.")

    token = authorization[len("Bearer ") :].strip()
    payload = verify_user_token(token, settings)

    user_id_str = payload.get("sub")
    username = payload.get("username", "")
    if not user_id_str:
        raise UnauthenticatedError("Token missing subject claim.")

    try:
        return uuid.UUID(user_id_str), username
    except ValueError as exc:
        raise UnauthenticatedError("Invalid user ID in token claim.") from exc


async def require_conversation_access(
    conv_id: uuid.UUID,
    user_id: uuid.UUID,
    social_client: SocialClient,
    require_send: bool = False,
) -> None:
    can_read, can_send = await social_client.check_permissions(conv_id, user_id)
    if not can_read:
        raise ConversationNotFoundError("Conversation not found or access denied.")
    if require_send and not can_send:
        raise FriendshipRequiredError("Action forbidden: you cannot send in this conversation.")
