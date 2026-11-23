"""Chat REST endpoints for messages, attachments, read-state and unread summaries."""

from __future__ import annotations

import os
import uuid
from typing import Annotated, Literal

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    Path,
    Query,
    Response,
    UploadFile,
    status,
)

from app.adapters.repository import (
    ChatRepository,
    StoredAttachment,
    StoredMessage,
    get_chat_repository,
)
from app.adapters.social_client import SocialClient, get_social_client
from app.api.dependencies import get_current_user, require_conversation_access
from app.api.schemas import (
    Attachment,
    Message,
    MessagePage,
    PublicUser,
    ReadState,
    ReadStateUpdate,
    StoredAudioContent,
    StoredFileContent,
    TextContent,
    UnreadSummary,
    format_utc_z,
)
from app.domain.exceptions import DomainError
from app.domain.models import validate_attachment
from app.settings import Settings, get_settings

router = APIRouter(prefix="/api/v1/conversations/{conversation_id}", tags=["Chat"])


def to_attachment_schema(att: StoredAttachment) -> Attachment:
    return Attachment(
        id=att.id,
        kind=att.kind,  # type: ignore[arg-type]
        file_name=att.file_name,
        media_type=att.media_type,
        byte_size=att.byte_size,
        duration_ms=att.duration_ms,
    )


def to_message_schema(m: StoredMessage) -> Message:
    sender = PublicUser(
        id=m.sender_id,
        username=f"user_{str(m.sender_id)[:8]}",
    )
    if m.content_type == "text":
        content = TextContent(type="text", text=m.text_content or "")
    elif m.content_type == "audio" and m.attachment:
        content = StoredAudioContent(type="audio", attachment=to_attachment_schema(m.attachment))
    elif m.content_type == "file" and m.attachment:
        content = StoredFileContent(type="file", attachment=to_attachment_schema(m.attachment))
    else:
        content = TextContent(type="text", text=m.text_content or "")

    return Message(
        id=m.id,
        conversation_id=m.conversation_id,
        seq=m.seq,
        sender=sender,
        created_at=format_utc_z(m.created_at),
        client_message_id=m.client_message_id,
        content=content,
    )


@router.post(
    "/attachments",
    status_code=status.HTTP_201_CREATED,
    response_model=Attachment,
    summary="Upload a pending attachment",
)
async def upload_attachment(
    conversation_id: Annotated[uuid.UUID, Path(...)],
    kind: Annotated[Literal["audio", "file"], Form(...)],
    file: Annotated[UploadFile, File(...)],
    caller: Annotated[tuple[uuid.UUID, str], Depends(get_current_user)],
    settings: Annotated[Settings, Depends(get_settings)],
    social: Annotated[SocialClient, Depends(get_social_client)],
    repo: Annotated[ChatRepository, Depends(get_chat_repository)],
) -> Attachment:
    user_id, _ = caller
    await require_conversation_access(conversation_id, user_id, social, require_send=True)

    if kind not in ("audio", "file"):
        raise DomainError(f"Invalid attachment kind: {kind}", code="VALIDATION_ERROR")

    content = await file.read()
    validate_attachment(kind=kind, byte_size=len(content))

    att_id = uuid.uuid4()
    conv_dir = os.path.join(settings.attachment_root, str(conversation_id))
    os.makedirs(conv_dir, exist_ok=True)
    file_path = os.path.join(conv_dir, str(att_id))
    with open(file_path, "wb") as f:
        f.write(content)

    from datetime import UTC, datetime

    now = datetime.now(UTC)
    stored_att = StoredAttachment(
        id=att_id,
        conversation_id=conversation_id,
        uploader_id=user_id,
        kind=kind,
        file_name=file.filename or "attachment",
        media_type=file.content_type or "application/octet-stream",
        byte_size=len(content),
        duration_ms=None,
        file_path=file_path,
        bound_to_message_id=None,
        created_at=now,
    )
    await repo.save_attachment(stored_att)
    return to_attachment_schema(stored_att)


@router.get(
    "/attachments/{attachment_id}/content",
    summary="Download attachment content",
)
async def get_attachment_content(
    conversation_id: Annotated[uuid.UUID, Path(...)],
    attachment_id: Annotated[uuid.UUID, Path(...)],
    caller: Annotated[tuple[uuid.UUID, str], Depends(get_current_user)],
    social: Annotated[SocialClient, Depends(get_social_client)],
    repo: Annotated[ChatRepository, Depends(get_chat_repository)],
) -> Response:
    user_id, _ = caller
    await require_conversation_access(conversation_id, user_id, social, require_send=False)

    att = await repo.get_attachment(conversation_id, attachment_id, user_id)
    if os.path.exists(att.file_path):
        with open(att.file_path, "rb") as f:
            data = f.read()
    else:
        data = b""

    disposition = "inline" if att.kind == "audio" else "attachment"
    headers = {
        "Cache-Control": "private, no-store",
        "Content-Disposition": f'{disposition}; filename="{att.file_name}"',
    }
    return Response(
        content=data,
        media_type=att.media_type or "application/octet-stream",
        headers=headers,
    )


@router.get(
    "/messages",
    response_model=MessagePage,
    summary="List messages in conversation",
)
async def list_messages(
    conversation_id: Annotated[uuid.UUID, Path(...)],
    caller: Annotated[tuple[uuid.UUID, str], Depends(get_current_user)],
    social: Annotated[SocialClient, Depends(get_social_client)],
    repo: Annotated[ChatRepository, Depends(get_chat_repository)],
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
    before_seq: Annotated[int | None, Query(ge=1)] = None,
    after_seq: Annotated[int | None, Query(ge=0)] = None,
    through_seq: Annotated[int | None, Query(ge=0)] = None,
) -> MessagePage:
    user_id, _ = caller
    await require_conversation_access(conversation_id, user_id, social, require_send=False)

    msgs, has_more = await repo.list_messages(
        conv_id=conversation_id,
        limit=limit,
        before_seq=before_seq,
        after_seq=after_seq,
        through_seq=through_seq,
    )
    items = [to_message_schema(m) for m in msgs]
    return MessagePage(items=items, has_more=has_more)


@router.get(
    "/messages/search",
    response_model=MessagePage,
    summary="Search messages by text content",
)
async def search_messages(
    conversation_id: Annotated[uuid.UUID, Path(...)],
    caller: Annotated[tuple[uuid.UUID, str], Depends(get_current_user)],
    social: Annotated[SocialClient, Depends(get_social_client)],
    repo: Annotated[ChatRepository, Depends(get_chat_repository)],
    q: Annotated[str, Query(min_length=1)] = "",
) -> MessagePage:
    user_id, _ = caller
    await require_conversation_access(conversation_id, user_id, social, require_send=False)

    msgs = await repo.search_messages(conversation_id, q)
    items = [to_message_schema(m) for m in msgs]
    return MessagePage(items=items, has_more=False)


@router.get(
    "/read-state",
    response_model=ReadState,
    summary="Get user's read state",
)
async def get_read_state(
    conversation_id: Annotated[uuid.UUID, Path(...)],
    caller: Annotated[tuple[uuid.UUID, str], Depends(get_current_user)],
    social: Annotated[SocialClient, Depends(get_social_client)],
    repo: Annotated[ChatRepository, Depends(get_chat_repository)],
) -> ReadState:
    user_id, _ = caller
    await require_conversation_access(conversation_id, user_id, social, require_send=False)

    last_read, latest, unread = await repo.get_read_state(conversation_id, user_id)
    return ReadState(
        last_read_seq=last_read,
        latest_seq=latest,
        unread_text_count=unread,
    )


@router.put(
    "/read-state",
    response_model=ReadState,
    summary="Advance user's read state monotonically",
)
async def update_read_state(
    conversation_id: Annotated[uuid.UUID, Path(...)],
    payload: ReadStateUpdate,
    caller: Annotated[tuple[uuid.UUID, str], Depends(get_current_user)],
    social: Annotated[SocialClient, Depends(get_social_client)],
    repo: Annotated[ChatRepository, Depends(get_chat_repository)],
) -> ReadState:
    user_id, _ = caller
    await require_conversation_access(conversation_id, user_id, social, require_send=False)

    last_read, latest, unread = await repo.update_read_state(
        conv_id=conversation_id, user_id=user_id, through_seq=payload.through_seq
    )
    return ReadState(
        last_read_seq=last_read,
        latest_seq=latest,
        unread_text_count=unread,
    )


@router.post(
    "/unread-summary",
    response_model=UnreadSummary,
    summary="Generate unread message summary snapshot",
)
async def get_unread_summary(
    conversation_id: Annotated[uuid.UUID, Path(...)],
    caller: Annotated[tuple[uuid.UUID, str], Depends(get_current_user)],
    social: Annotated[SocialClient, Depends(get_social_client)],
    repo: Annotated[ChatRepository, Depends(get_chat_repository)],
) -> UnreadSummary:
    user_id, _ = caller
    await require_conversation_access(conversation_id, user_id, social, require_send=False)

    data = await repo.get_unread_summary(conversation_id, user_id)
    return UnreadSummary(**data)
