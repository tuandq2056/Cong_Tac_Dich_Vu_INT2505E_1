"""Pydantic wire format schemas for Chat service (OpenAPI-compliant)."""

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


class Attachment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    kind: Literal["audio", "file"]
    file_name: str
    media_type: str
    byte_size: int
    duration_ms: int | None = None


class TextContent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["text"] = "text"
    text: Annotated[str, Field(min_length=1, max_length=4000)]


class StoredAudioContent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["audio"] = "audio"
    attachment: Attachment


class StoredFileContent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["file"] = "file"
    attachment: Attachment


class Message(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    conversation_id: uuid.UUID
    seq: int
    sender: PublicUser
    created_at: str
    client_message_id: uuid.UUID
    content: TextContent | StoredAudioContent | StoredFileContent


class MessagePage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[Message]
    has_more: bool


class ReadState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    last_read_seq: int
    latest_seq: int
    unread_text_count: int


class ReadStateUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    through_seq: int


class UnreadSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["ready", "empty"]
    summary: str | None
    source_count: int
    omitted_count: int
    last_read_seq: int
    snapshot_seq: int
    source_from_seq: int | None
    source_to_seq: int | None
