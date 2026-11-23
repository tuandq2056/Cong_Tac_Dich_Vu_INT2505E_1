"""Chat domain models and business invariants. Framework-free."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from .exceptions import (
    DomainError,
    InvalidAttachmentError,
    ReadAheadError,
    UploadTooLargeError,
)

MAX_TEXT_CODEPOINTS = 4000
MAX_AUDIO_BYTES = 10 * 1024 * 1024  # 10 MiB
MAX_AUDIO_DURATION_MS = 300 * 1000  # 300 seconds
MAX_FILE_BYTES = 25 * 1024 * 1024  # 25 MiB
MAX_SUMMARY_MESSAGES = 100


def validate_text_content(text: str) -> None:
    if not isinstance(text, str):
        raise DomainError("Message text must be a string.", code="VALIDATION_ERROR")
    if len(text) == 0:
        raise DomainError("Message text cannot be empty.", code="VALIDATION_ERROR")
    if len(text) > MAX_TEXT_CODEPOINTS:
        raise DomainError(
            f"Message text cannot exceed {MAX_TEXT_CODEPOINTS} code points.",
            code="MESSAGE_TOO_LONG",
        )


def clamp_read_state(current_last_read_seq: int, through_seq: int, latest_seq: int) -> int:
    """Read-state only moves forward (ADR 0006).

    through_seq > latest_seq is 422 READ_AHEAD.
    last_read_seq = GREATEST(old, through_seq).
    """
    if through_seq > latest_seq:
        raise ReadAheadError(
            f"through_seq ({through_seq}) cannot exceed latest_seq ({latest_seq})."
        )
    return max(current_last_read_seq, through_seq)


def validate_attachment(
    kind: Literal["audio", "file"],
    byte_size: int,
    duration_ms: int | None = None,
) -> None:
    if byte_size <= 0:
        raise InvalidAttachmentError("Attachment cannot be empty.")

    if kind == "audio":
        if byte_size > MAX_AUDIO_BYTES:
            raise UploadTooLargeError(f"Audio exceeds maximum size of {MAX_AUDIO_BYTES} bytes.")
        if duration_ms is not None and duration_ms > MAX_AUDIO_DURATION_MS:
            raise InvalidAttachmentError(
                f"Audio duration exceeds maximum {MAX_AUDIO_DURATION_MS // 1000} seconds."
            )
    elif kind == "file":
        if byte_size > MAX_FILE_BYTES:
            raise UploadTooLargeError(f"File exceeds maximum size of {MAX_FILE_BYTES} bytes.")
    else:
        raise InvalidAttachmentError(f"Unknown attachment kind: {kind}")


@dataclass(frozen=True)
class SummaryCandidateMessage:
    id: uuid.UUID
    conversation_id: uuid.UUID
    seq: int
    sender_id: uuid.UUID
    content_type: str  # "text", "audio", "file"
    text: str | None
    created_at: datetime


def filter_messages_for_summary(
    messages: list[SummaryCandidateMessage],
    reader_id: uuid.UUID,
    max_count: int = MAX_SUMMARY_MESSAGES,
) -> tuple[list[SummaryCandidateMessage], int]:
    """Filter messages for LLM unread summary (ADR 0006).

    - Exclude messages sent by the reader.
    - Exclude non-text messages (audio, file).
    - Sort ascending by seq.
    - Limit to newest max_count messages.
    - Return (selected_messages, omitted_count).
    """
    # Filter text from other users
    eligible = [
        msg
        for msg in messages
        if msg.sender_id != reader_id and msg.content_type == "text" and msg.text
    ]

    # Sort ascending by seq
    eligible.sort(key=lambda m: m.seq)

    total_eligible = len(eligible)
    if total_eligible <= max_count:
        return eligible, 0

    # Newest max_count messages
    omitted = total_eligible - max_count
    selected = eligible[omitted:]
    return selected, omitted
