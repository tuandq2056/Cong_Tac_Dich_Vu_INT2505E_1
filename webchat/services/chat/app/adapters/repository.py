"""Repository adapters for Chat service."""

from __future__ import annotations

import logging
import unicodedata
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from app.domain.exceptions import (
    ClientMessageIdConflictError,
    ConversationNotFoundError,
)
from app.domain.models import (
    SummaryCandidateMessage,
    clamp_read_state,
    filter_messages_for_summary,
)

logger = logging.getLogger("webchat.chat")


@dataclass(frozen=True)
class StoredAttachment:
    id: uuid.UUID
    conversation_id: uuid.UUID
    uploader_id: uuid.UUID
    kind: str  # "audio" | "file"
    file_name: str
    media_type: str
    byte_size: int
    duration_ms: int | None
    file_path: str
    bound_to_message_id: uuid.UUID | None
    created_at: datetime


@dataclass(frozen=True)
class StoredMessage:
    id: uuid.UUID
    conversation_id: uuid.UUID
    seq: int
    sender_id: uuid.UUID
    client_message_id: uuid.UUID
    content_type: str  # "text" | "audio" | "file"
    text_content: str | None
    attachment: StoredAttachment | None
    created_at: datetime


class ChatRepository(ABC):
    @abstractmethod
    async def save_attachment(self, attachment: StoredAttachment) -> StoredAttachment: ...

    @abstractmethod
    async def get_attachment(
        self, conv_id: uuid.UUID, attachment_id: uuid.UUID, requester_id: uuid.UUID
    ) -> StoredAttachment: ...

    @abstractmethod
    async def send_message(
        self,
        conv_id: uuid.UUID,
        sender_id: uuid.UUID,
        client_message_id: uuid.UUID,
        content_type: str,
        text_content: str | None = None,
        attachment_id: uuid.UUID | None = None,
    ) -> tuple[StoredMessage, bool]:
        """Return (StoredMessage, is_replayed)."""
        ...

    @abstractmethod
    async def list_messages(
        self,
        conv_id: uuid.UUID,
        limit: int = 30,
        before_seq: int | None = None,
        after_seq: int | None = None,
        through_seq: int | None = None,
    ) -> tuple[list[StoredMessage], bool]:
        """Return (items, has_more)."""
        ...

    @abstractmethod
    async def search_messages(self, conv_id: uuid.UUID, query: str) -> list[StoredMessage]: ...

    @abstractmethod
    async def get_read_state(self, conv_id: uuid.UUID, user_id: uuid.UUID) -> tuple[int, int, int]:
        """Return (last_read_seq, latest_seq, unread_text_count)."""
        ...

    @abstractmethod
    async def update_read_state(
        self, conv_id: uuid.UUID, user_id: uuid.UUID, through_seq: int
    ) -> tuple[int, int, int]: ...

    @abstractmethod
    async def get_unread_summary(
        self, conv_id: uuid.UUID, user_id: uuid.UUID
    ) -> dict[str, Any]: ...

    @abstractmethod
    async def get_latest_seq(self, conv_id: uuid.UUID) -> int: ...

    @abstractmethod
    async def init_db(self) -> None: ...

    @abstractmethod
    async def close(self) -> None: ...


class MemoryChatRepository(ChatRepository):
    def __init__(self) -> None:
        # conv_id -> latest_seq
        self._counters: dict[uuid.UUID, int] = {}
        # att_id -> StoredAttachment
        self._attachments: dict[uuid.UUID, StoredAttachment] = {}
        # conv_id -> list of StoredMessage (sorted by seq)
        self._messages: dict[uuid.UUID, list[StoredMessage]] = {}
        # (conv_id, sender_id, client_message_id) -> StoredMessage
        self._idemp: dict[tuple[uuid.UUID, uuid.UUID, uuid.UUID], StoredMessage] = {}
        # (conv_id, user_id) -> last_read_seq
        self._read_states: dict[tuple[uuid.UUID, uuid.UUID], int] = {}

    async def init_db(self) -> None:
        pass

    async def close(self) -> None:
        pass

    async def get_latest_seq(self, conv_id: uuid.UUID) -> int:
        return self._counters.get(conv_id, 0)

    async def save_attachment(self, attachment: StoredAttachment) -> StoredAttachment:
        self._attachments[attachment.id] = attachment
        return attachment

    async def get_attachment(
        self, conv_id: uuid.UUID, attachment_id: uuid.UUID, requester_id: uuid.UUID
    ) -> StoredAttachment:
        att = self._attachments.get(attachment_id)
        if att is None or att.conversation_id != conv_id:
            raise ConversationNotFoundError("Attachment not found.")

        # If not bound to a message yet, only uploader can access
        if att.bound_to_message_id is None and att.uploader_id != requester_id:
            raise ConversationNotFoundError("Attachment not found.")

        return att

    async def send_message(
        self,
        conv_id: uuid.UUID,
        sender_id: uuid.UUID,
        client_message_id: uuid.UUID,
        content_type: str,
        text_content: str | None = None,
        attachment_id: uuid.UUID | None = None,
    ) -> tuple[StoredMessage, bool]:
        key = (conv_id, sender_id, client_message_id)
        if key in self._idemp:
            existing = self._idemp[key]
            # Verify content match
            if existing.content_type == content_type:
                if content_type == "text" and existing.text_content == text_content:
                    return existing, True
                if (
                    content_type in ("audio", "file")
                    and existing.attachment
                    and existing.attachment.id == attachment_id
                ):
                    return existing, True
            raise ClientMessageIdConflictError("Client message ID conflict with different payload.")

        # Allocate seq
        current_seq = self._counters.get(conv_id, 0) + 1
        self._counters[conv_id] = current_seq

        att: StoredAttachment | None = None
        msg_id = uuid.uuid4()
        if attachment_id is not None:
            raw_att = self._attachments.get(attachment_id)
            if raw_att:
                att = StoredAttachment(
                    id=raw_att.id,
                    conversation_id=raw_att.conversation_id,
                    uploader_id=raw_att.uploader_id,
                    kind=raw_att.kind,
                    file_name=raw_att.file_name,
                    media_type=raw_att.media_type,
                    byte_size=raw_att.byte_size,
                    duration_ms=raw_att.duration_ms,
                    file_path=raw_att.file_path,
                    bound_to_message_id=msg_id,
                    created_at=raw_att.created_at,
                )
                self._attachments[att.id] = att

        now = datetime.now(UTC)
        msg = StoredMessage(
            id=msg_id,
            conversation_id=conv_id,
            seq=current_seq,
            sender_id=sender_id,
            client_message_id=client_message_id,
            content_type=content_type,
            text_content=text_content,
            attachment=att,
            created_at=now,
        )

        if conv_id not in self._messages:
            self._messages[conv_id] = []
        self._messages[conv_id].append(msg)
        self._idemp[key] = msg

        return msg, False

    async def list_messages(
        self,
        conv_id: uuid.UUID,
        limit: int = 30,
        before_seq: int | None = None,
        after_seq: int | None = None,
        through_seq: int | None = None,
    ) -> tuple[list[StoredMessage], bool]:
        msgs = self._messages.get(conv_id, [])
        filtered = msgs[:]

        if after_seq is not None:
            filtered = [m for m in filtered if m.seq > after_seq]
        if through_seq is not None:
            filtered = [m for m in filtered if m.seq <= through_seq]
        if before_seq is not None:
            filtered = [m for m in filtered if m.seq < before_seq]

        has_more = len(filtered) > limit
        sliced = filtered[:limit]
        return sliced, has_more

    async def search_messages(self, conv_id: uuid.UUID, query: str) -> list[StoredMessage]:
        msgs = self._messages.get(conv_id, [])
        norm_q = unicodedata.normalize("NFC", query).lower()
        results: list[StoredMessage] = []
        for m in msgs:
            if m.content_type == "text" and m.text_content:
                norm_text = unicodedata.normalize("NFC", m.text_content).lower()
                if norm_q in norm_text:
                    results.append(m)
        return results

    async def get_read_state(self, conv_id: uuid.UUID, user_id: uuid.UUID) -> tuple[int, int, int]:
        last_read = self._read_states.get((conv_id, user_id), 0)
        latest_seq = self._counters.get(conv_id, 0)
        msgs = self._messages.get(conv_id, [])
        unread = sum(
            1
            for m in msgs
            if m.seq > last_read
            and m.seq <= latest_seq
            and m.sender_id != user_id
            and m.content_type == "text"
        )
        return last_read, latest_seq, unread

    async def update_read_state(
        self, conv_id: uuid.UUID, user_id: uuid.UUID, through_seq: int
    ) -> tuple[int, int, int]:
        latest_seq = self._counters.get(conv_id, 0)
        current_read = self._read_states.get((conv_id, user_id), 0)
        new_read = clamp_read_state(current_read, through_seq, latest_seq)
        self._read_states[(conv_id, user_id)] = new_read
        return await self.get_read_state(conv_id, user_id)

    async def get_unread_summary(self, conv_id: uuid.UUID, user_id: uuid.UUID) -> dict[str, Any]:
        last_read, latest_seq, _ = await self.get_read_state(conv_id, user_id)
        msgs = self._messages.get(conv_id, [])

        candidates = [
            SummaryCandidateMessage(
                id=m.id,
                conversation_id=m.conversation_id,
                seq=m.seq,
                sender_id=m.sender_id,
                content_type=m.content_type,
                text=m.text_content,
                created_at=m.created_at,
            )
            for m in msgs
            if m.seq > last_read and m.seq <= latest_seq
        ]

        selected, omitted_count = filter_messages_for_summary(candidates, user_id)
        if not selected:
            return {
                "status": "empty",
                "summary": None,
                "source_count": 0,
                "omitted_count": 0,
                "last_read_seq": last_read,
                "snapshot_seq": latest_seq,
                "source_from_seq": None,
                "source_to_seq": None,
            }

        min_seq = selected[0].seq
        max_seq = selected[-1].seq
        summary_text = f"Summary of {len(selected)} unread messages: " + " ".join(
            m.text or "" for m in selected[:3]
        )

        return {
            "status": "ready",
            "summary": summary_text,
            "source_count": len(selected),
            "omitted_count": omitted_count,
            "last_read_seq": last_read,
            "snapshot_seq": latest_seq,
            "source_from_seq": min_seq,
            "source_to_seq": max_seq,
        }


class PostgresChatRepository(ChatRepository):
    """PostgreSQL implementation of ChatRepository using asyncpg."""

    def __init__(self, dsn: str) -> None:
        if dsn.startswith("postgresql+asyncpg://"):
            dsn = "postgresql://" + dsn[len("postgresql+asyncpg://") :]
        self._dsn = dsn
        self._pool: Any = None

    async def init_db(self) -> None:
        import asyncpg

        self._pool = await asyncpg.create_pool(dsn=self._dsn, min_size=1, max_size=10)
        async with self._pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS conversation_counter (
                    conversation_id UUID PRIMARY KEY,
                    last_seq BIGINT NOT NULL DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS attachments (
                    id UUID PRIMARY KEY,
                    conversation_id UUID NOT NULL,
                    uploader_id UUID NOT NULL,
                    kind VARCHAR(10) NOT NULL,
                    file_name VARCHAR(255) NOT NULL,
                    media_type VARCHAR(100) NOT NULL,
                    byte_size BIGINT NOT NULL,
                    duration_ms INT,
                    file_path TEXT NOT NULL,
                    bound_to_message_id UUID,
                    created_at TIMESTAMPTZ NOT NULL
                );

                CREATE TABLE IF NOT EXISTS messages (
                    id UUID PRIMARY KEY,
                    conversation_id UUID NOT NULL,
                    seq BIGINT NOT NULL,
                    sender_id UUID NOT NULL,
                    client_message_id UUID NOT NULL,
                    content_type VARCHAR(20) NOT NULL,
                    text_content TEXT,
                    attachment_id UUID REFERENCES attachments(id),
                    created_at TIMESTAMPTZ NOT NULL,
                    UNIQUE (conversation_id, seq),
                    UNIQUE (conversation_id, sender_id, client_message_id)
                );
                CREATE INDEX IF NOT EXISTS idx_messages_conv_seq ON messages (conversation_id, seq);

                CREATE TABLE IF NOT EXISTS read_states (
                    conversation_id UUID NOT NULL,
                    user_id UUID NOT NULL,
                    last_read_seq BIGINT NOT NULL DEFAULT 0,
                    updated_at TIMESTAMPTZ NOT NULL,
                    PRIMARY KEY (conversation_id, user_id)
                );
            """)
        logger.info("PostgreSQL Chat schema initialized successfully.")

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()

    async def get_latest_seq(self, conv_id: uuid.UUID) -> int:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT last_seq FROM conversation_counter WHERE conversation_id = $1",
                conv_id,
            )
            return row["last_seq"] if row else 0

    async def save_attachment(self, attachment: StoredAttachment) -> StoredAttachment:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO attachments
                (id, conversation_id, uploader_id, kind, file_name, media_type,
                 byte_size, duration_ms, file_path, bound_to_message_id, created_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                """,
                attachment.id,
                attachment.conversation_id,
                attachment.uploader_id,
                attachment.kind,
                attachment.file_name,
                attachment.media_type,
                attachment.byte_size,
                attachment.duration_ms,
                attachment.file_path,
                attachment.bound_to_message_id,
                attachment.created_at,
            )
            return attachment

    async def get_attachment(
        self, conv_id: uuid.UUID, attachment_id: uuid.UUID, requester_id: uuid.UUID
    ) -> StoredAttachment:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM attachments WHERE id = $1 AND conversation_id = $2",
                attachment_id,
                conv_id,
            )
            if not row:
                raise ConversationNotFoundError("Attachment not found.")

            if row["bound_to_message_id"] is None and row["uploader_id"] != requester_id:
                raise ConversationNotFoundError("Attachment not found.")

            return StoredAttachment(
                id=row["id"],
                conversation_id=row["conversation_id"],
                uploader_id=row["uploader_id"],
                kind=row["kind"],
                file_name=row["file_name"],
                media_type=row["media_type"],
                byte_size=row["byte_size"],
                duration_ms=row["duration_ms"],
                file_path=row["file_path"],
                bound_to_message_id=row["bound_to_message_id"],
                created_at=row["created_at"].astimezone(UTC),
            )

    async def send_message(
        self,
        conv_id: uuid.UUID,
        sender_id: uuid.UUID,
        client_message_id: uuid.UUID,
        content_type: str,
        text_content: str | None = None,
        attachment_id: uuid.UUID | None = None,
    ) -> tuple[StoredMessage, bool]:
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                # Check existing idempotency
                existing_row = await conn.fetchrow(
                    """
                    SELECT m.*, a.kind as a_kind, a.file_name as a_fn, a.media_type as a_mt,
                           a.byte_size as a_bs, a.duration_ms as a_dur, a.file_path as a_fp,
                           a.created_at as a_ca, a.uploader_id as a_up
                    FROM messages m
                    LEFT JOIN attachments a ON m.attachment_id = a.id
                    WHERE m.conversation_id = $1 AND m.sender_id = $2 AND m.client_message_id = $3
                    """,
                    conv_id,
                    sender_id,
                    client_message_id,
                )
                if existing_row:
                    if existing_row["content_type"] == content_type:
                        if content_type == "text" and existing_row["text_content"] == text_content:
                            return self._build_stored_msg(existing_row), True
                        if (
                            content_type in ("audio", "file")
                            and existing_row["attachment_id"] == attachment_id
                        ):
                            return self._build_stored_msg(existing_row), True
                    raise ClientMessageIdConflictError("Client message ID conflict.")

                # Allocate seq with atomic counter update (ADR 0002)
                await conn.execute(
                    """
                    INSERT INTO conversation_counter (conversation_id, last_seq)
                    VALUES ($1, 0)
                    ON CONFLICT DO NOTHING
                    """,
                    conv_id,
                )
                seq_row = await conn.fetchrow(
                    """
                    UPDATE conversation_counter
                    SET last_seq = last_seq + 1
                    WHERE conversation_id = $1
                    RETURNING last_seq
                    """,
                    conv_id,
                )
                allocated_seq = seq_row["last_seq"]

                msg_id = uuid.uuid4()
                now = datetime.now(UTC)
                await conn.execute(
                    """
                    INSERT INTO messages
                    (id, conversation_id, seq, sender_id, client_message_id,
                     content_type, text_content, attachment_id, created_at)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                    """,
                    msg_id,
                    conv_id,
                    allocated_seq,
                    sender_id,
                    client_message_id,
                    content_type,
                    text_content,
                    attachment_id,
                    now,
                )

                att: StoredAttachment | None = None
                if attachment_id is not None:
                    await conn.execute(
                        "UPDATE attachments SET bound_to_message_id = $1 WHERE id = $2",
                        msg_id,
                        attachment_id,
                    )
                    a_row = await conn.fetchrow(
                        "SELECT * FROM attachments WHERE id = $1", attachment_id
                    )
                    if a_row:
                        att = StoredAttachment(
                            id=a_row["id"],
                            conversation_id=a_row["conversation_id"],
                            uploader_id=a_row["uploader_id"],
                            kind=a_row["kind"],
                            file_name=a_row["file_name"],
                            media_type=a_row["media_type"],
                            byte_size=a_row["byte_size"],
                            duration_ms=a_row["duration_ms"],
                            file_path=a_row["file_path"],
                            bound_to_message_id=msg_id,
                            created_at=a_row["created_at"].astimezone(UTC),
                        )

                msg = StoredMessage(
                    id=msg_id,
                    conversation_id=conv_id,
                    seq=allocated_seq,
                    sender_id=sender_id,
                    client_message_id=client_message_id,
                    content_type=content_type,
                    text_content=text_content,
                    attachment=att,
                    created_at=now,
                )
                return msg, False

    def _build_stored_msg(self, r: Any) -> StoredMessage:
        att: StoredAttachment | None = None
        if r["attachment_id"]:
            att = StoredAttachment(
                id=r["attachment_id"],
                conversation_id=r["conversation_id"],
                uploader_id=r["a_up"],
                kind=r["a_kind"],
                file_name=r["a_fn"],
                media_type=r["a_mt"],
                byte_size=r["a_bs"],
                duration_ms=r["a_dur"],
                file_path=r["a_fp"],
                bound_to_message_id=r["id"],
                created_at=r["a_ca"].astimezone(UTC),
            )
        return StoredMessage(
            id=r["id"],
            conversation_id=r["conversation_id"],
            seq=r["seq"],
            sender_id=r["sender_id"],
            client_message_id=r["client_message_id"],
            content_type=r["content_type"],
            text_content=r["text_content"],
            attachment=att,
            created_at=r["created_at"].astimezone(UTC),
        )

    async def list_messages(
        self,
        conv_id: uuid.UUID,
        limit: int = 30,
        before_seq: int | None = None,
        after_seq: int | None = None,
        through_seq: int | None = None,
    ) -> tuple[list[StoredMessage], bool]:
        query = """
            SELECT m.*, a.kind as a_kind, a.file_name as a_fn, a.media_type as a_mt,
                   a.byte_size as a_bs, a.duration_ms as a_dur, a.file_path as a_fp,
                   a.created_at as a_ca, a.uploader_id as a_up
            FROM messages m
            LEFT JOIN attachments a ON m.attachment_id = a.id
            WHERE m.conversation_id = $1
        """
        params: list[Any] = [conv_id]
        if after_seq is not None:
            params.append(after_seq)
            query += f" AND m.seq > ${len(params)}"
        if through_seq is not None:
            params.append(through_seq)
            query += f" AND m.seq <= ${len(params)}"
        if before_seq is not None:
            params.append(before_seq)
            query += f" AND m.seq < ${len(params)}"

        query += f" ORDER BY m.seq ASC LIMIT {limit + 1}"

        async with self._pool.acquire() as conn:
            rows = await conn.fetch(query, *params)
            has_more = len(rows) > limit
            items = [self._build_stored_msg(r) for r in rows[:limit]]
            return items, has_more

    async def search_messages(self, conv_id: uuid.UUID, query: str) -> list[StoredMessage]:
        sql = """
            SELECT m.*, a.kind as a_kind, a.file_name as a_fn, a.media_type as a_mt,
                   a.byte_size as a_bs, a.duration_ms as a_dur, a.file_path as a_fp,
                   a.created_at as a_ca, a.uploader_id as a_up
            FROM messages m
            LEFT JOIN attachments a ON m.attachment_id = a.id
            WHERE m.conversation_id = $1 AND m.content_type = 'text'
            ORDER BY m.seq ASC
        """
        norm_q = unicodedata.normalize("NFC", query).lower()
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(sql, conv_id)
            results: list[StoredMessage] = []
            for r in rows:
                text = r["text_content"] or ""
                norm_text = unicodedata.normalize("NFC", text).lower()
                if norm_q in norm_text:
                    results.append(self._build_stored_msg(r))
            return results

    async def get_read_state(self, conv_id: uuid.UUID, user_id: uuid.UUID) -> tuple[int, int, int]:
        async with self._pool.acquire() as conn:
            rs_row = await conn.fetchrow(
                "SELECT last_read_seq FROM read_states WHERE conversation_id = $1 AND user_id = $2",
                conv_id,
                user_id,
            )
            last_read = rs_row["last_read_seq"] if rs_row else 0

            c_row = await conn.fetchrow(
                "SELECT last_seq FROM conversation_counter WHERE conversation_id = $1",
                conv_id,
            )
            latest_seq = c_row["last_seq"] if c_row else 0

            unread_row = await conn.fetchrow(
                """
                SELECT COUNT(*) as cnt FROM messages
                WHERE conversation_id = $1 AND seq > $2 AND seq <= $3
                  AND sender_id <> $4 AND content_type = 'text'
                """,
                conv_id,
                last_read,
                latest_seq,
                user_id,
            )
            unread_cnt = unread_row["cnt"] if unread_row else 0
            return last_read, latest_seq, unread_cnt

    async def update_read_state(
        self, conv_id: uuid.UUID, user_id: uuid.UUID, through_seq: int
    ) -> tuple[int, int, int]:
        latest_seq = await self.get_latest_seq(conv_id)
        current_read, _, _ = await self.get_read_state(conv_id, user_id)
        new_read = clamp_read_state(current_read, through_seq, latest_seq)

        now = datetime.now(UTC)
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO read_states (conversation_id, user_id, last_read_seq, updated_at)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (conversation_id, user_id)
                DO UPDATE SET
                    last_read_seq = GREATEST(read_states.last_read_seq, EXCLUDED.last_read_seq),
                    updated_at = EXCLUDED.updated_at
                """,
                conv_id,
                user_id,
                new_read,
                now,
            )
        return await self.get_read_state(conv_id, user_id)

    async def get_unread_summary(self, conv_id: uuid.UUID, user_id: uuid.UUID) -> dict[str, Any]:
        last_read, latest_seq, _ = await self.get_read_state(conv_id, user_id)
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, conversation_id, seq, sender_id, content_type, text_content, created_at
                FROM messages
                WHERE conversation_id = $1 AND seq > $2 AND seq <= $3
                ORDER BY seq ASC
                """,
                conv_id,
                last_read,
                latest_seq,
            )
            candidates = [
                SummaryCandidateMessage(
                    id=r["id"],
                    conversation_id=r["conversation_id"],
                    seq=r["seq"],
                    sender_id=r["sender_id"],
                    content_type=r["content_type"],
                    text=r["text_content"],
                    created_at=r["created_at"].astimezone(UTC),
                )
                for r in rows
            ]

        selected, omitted_count = filter_messages_for_summary(candidates, user_id)
        if not selected:
            return {
                "status": "empty",
                "summary": None,
                "source_count": 0,
                "omitted_count": 0,
                "last_read_seq": last_read,
                "snapshot_seq": latest_seq,
                "source_from_seq": None,
                "source_to_seq": None,
            }

        min_seq = selected[0].seq
        max_seq = selected[-1].seq
        summary_text = f"Summary of {len(selected)} unread messages: " + " ".join(
            m.text or "" for m in selected[:3]
        )

        return {
            "status": "ready",
            "summary": summary_text,
            "source_count": len(selected),
            "omitted_count": omitted_count,
            "last_read_seq": last_read,
            "snapshot_seq": latest_seq,
            "source_from_seq": min_seq,
            "source_to_seq": max_seq,
        }


_global_chat_repo: ChatRepository | None = None


async def get_chat_repository() -> ChatRepository:
    global _global_chat_repo
    if _global_chat_repo is not None:
        return _global_chat_repo

    from app.settings import get_settings

    settings = get_settings()

    dsn = settings.database_url
    if dsn and (dsn.startswith("postgresql://") or dsn.startswith("postgresql+asyncpg://")):
        try:
            repo = PostgresChatRepository(dsn)
            await repo.init_db()
            _global_chat_repo = repo
            return _global_chat_repo
        except Exception as exc:
            logger.warning("Could not connect to Postgres Chat (%s), fallback to Memory repo", exc)

    mem_repo = MemoryChatRepository()
    await mem_repo.init_db()
    _global_chat_repo = mem_repo
    return _global_chat_repo


def set_chat_repository(repo: ChatRepository | None) -> None:
    global _global_chat_repo
    _global_chat_repo = repo
