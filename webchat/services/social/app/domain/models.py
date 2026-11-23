"""Social domain models and business invariants. Framework-free."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from .exceptions import (
    DomainError,
    InvalidMembersError,
    RequestClosedError,
    SelfConversationError,
    SelfInviteError,
)


class FriendRequestStatus(StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    DECLINED = "declined"
    CANCELLED = "cancelled"


def canonical_pair(user_a: uuid.UUID, user_b: uuid.UUID) -> tuple[uuid.UUID, uuid.UUID]:
    """Sort pair canonically so A-B and B-A produce the exact same tuple."""
    if user_a == user_b:
        raise SelfConversationError()
    return (user_a, user_b) if str(user_a) < str(user_b) else (user_b, user_a)


def validate_friend_request_actors(sender_id: uuid.UUID, recipient_id: uuid.UUID) -> None:
    if sender_id == recipient_id:
        raise SelfInviteError()


def validate_friend_request_transition(
    current_status: FriendRequestStatus,
    new_status: FriendRequestStatus,
) -> FriendRequestStatus:
    if current_status != FriendRequestStatus.PENDING:
        raise RequestClosedError()
    if new_status == FriendRequestStatus.PENDING:
        raise DomainError("Cannot transition back to pending state.", code="INVALID_TRANSITION")
    return new_status


def validate_group_name(name: str) -> str:
    """Group name must be 1-80 code points and have visible characters after strip."""
    if not isinstance(name, str):
        raise DomainError("Group name must be a string.", code="INVALID_GROUP_NAME")
    stripped = name.strip()
    if not stripped:
        raise DomainError("Group name must contain visible characters.", code="INVALID_GROUP_NAME")
    if len(name) > 80:
        raise DomainError("Group name cannot exceed 80 code points.", code="INVALID_GROUP_NAME")
    return stripped


def validate_group_members(creator_id: uuid.UUID, member_ids: list[uuid.UUID]) -> list[uuid.UUID]:
    """Validate group members: 3-50 members total including creator, unique IDs."""
    unique_others = set(member_ids)
    if creator_id in unique_others:
        unique_others.remove(creator_id)

    # 2 to 49 unique friends + creator = 3 to 50 members total
    if len(unique_others) < 2 or len(unique_others) > 49:
        raise InvalidMembersError(
            "A group must have between 3 and 50 members including the creator."
        )

    # Return sorted canonical member list with creator
    all_members = [creator_id] + sorted(list(unique_others), key=str)
    return all_members


@dataclass(frozen=True)
class DirectConversation:
    id: uuid.UUID
    user_a_id: uuid.UUID
    user_b_id: uuid.UUID
    created_at: datetime


@dataclass(frozen=True)
class GroupConversation:
    id: uuid.UUID
    name: str
    created_by: uuid.UUID
    member_count: int
    created_at: datetime
