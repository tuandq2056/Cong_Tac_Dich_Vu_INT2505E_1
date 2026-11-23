"""Pydantic wire format schemas for Social service (OpenAPI-compliant)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


def format_utc_z(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


class PublicUser(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    username: str
    created_at: str


class FriendRequestCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    recipient_id: uuid.UUID


class FriendRequestDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["accepted", "declined", "cancelled"]


class FriendRequestResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    sender: PublicUser
    recipient: PublicUser
    status: Literal["pending", "accepted", "declined", "cancelled"]
    created_at: str


class FriendRequestPage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[FriendRequestResponse]
    next_cursor: str | None = None


class UserPage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[PublicUser]
    next_cursor: str | None = None


class DirectConversationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    type: Literal["direct"] = "direct"
    peer: PublicUser
    created_at: str


class GroupConversationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    type: Literal["group"] = "group"
    name: str
    created_by: PublicUser
    member_count: int
    created_at: str


class GroupCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Annotated[str, Field(min_length=1, max_length=80)]
    member_ids: Annotated[list[uuid.UUID], Field(min_length=2, max_length=49)]


class ConversationPage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[DirectConversationResponse | GroupConversationResponse]
    next_cursor: str | None = None


class PermissionsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    can_read: bool
    can_send: bool
