"""Exercise the first migration and simultaneous sends in a disposable PostgreSQL database."""

import asyncio
import os
import uuid
from urllib.parse import urlsplit, urlunsplit

import asyncpg
import pytest

from app.adapters.repository import PostgresChatRepository
from app.domain.exceptions import ClientMessageIdConflictError


@pytest.mark.skipif(not os.getenv("CHAT_TEST_ADMIN_DSN"), reason="needs PostgreSQL with CREATEDB")
@pytest.mark.parametrize("legacy", [False, True], ids=["empty", "pre_migration"])
def test_migrate_and_replay(legacy: bool) -> None:
    asyncio.run(migrate_and_replay(os.environ["CHAT_TEST_ADMIN_DSN"], legacy))


async def migrate_and_replay(admin_dsn: str, legacy: bool) -> None:
    parts = urlsplit(admin_dsn)
    database = f"chat_test_{uuid.uuid4().hex}"
    dsn = urlunsplit(parts._replace(path=f"/{database}"))
    admin = await asyncpg.connect(admin_dsn)
    try:
        await admin.execute(f'CREATE DATABASE "{database}"')
        try:
            await exercise_database(dsn, legacy)
        finally:
            await admin.execute(f'DROP DATABASE "{database}" WITH (FORCE)')
    finally:
        await admin.close()


async def exercise_database(dsn: str, legacy: bool) -> None:
    conn = await asyncpg.connect(dsn)
    repo = PostgresChatRepository(dsn)
    room, sender, client_id = (uuid.uuid4() for _ in range(3))
    try:
        if legacy:
            await conn.execute("""
                CREATE TABLE conversation_counter (
                    conversation_id uuid PRIMARY KEY, last_seq bigint
                );
                CREATE TABLE messages (
                    id uuid PRIMARY KEY, conversation_id uuid, seq bigint, sender_id uuid,
                    client_message_id uuid, content_type varchar(20), text_content text,
                    attachment_id uuid, created_at timestamptz,
                    UNIQUE(conversation_id, seq),
                    UNIQUE(conversation_id, sender_id, client_message_id)
                )
            """)
            await conn.execute("INSERT INTO conversation_counter VALUES ($1, 1)", room)
            await conn.execute(
                """
                INSERT INTO messages VALUES ($1, $2, 1, $3, $4, 'text', 'original', NULL, now())
            """,
                uuid.uuid4(),
                room,
                sender,
                uuid.uuid4(),
            )

        await repo.init_db()
        assert await conn.fetchval("SELECT version_num FROM alembic_version") == "0001_chat"
        args = dict(
            conv_id=room,
            sender_id=sender,
            client_message_id=client_id,
            content_type="text",
            sender_username="alice",
            text_content="hello",
        )
        sends = await asyncio.gather(*(repo.send_message(**args) for _ in range(4)))
        first = sends[0][0]
        assert sum(not replayed for _, replayed in sends) == 1
        assert all(message == first for message, _ in sends)
        assert first.seq == (2 if legacy else 1)
        with pytest.raises(ClientMessageIdConflictError):
            await repo.send_message(**(args | {"conv_id": uuid.uuid4()}))
        with pytest.raises(ClientMessageIdConflictError):
            await repo.send_message(**(args | {"text_content": "edited"}))
        assert await repo.get_latest_seq(room) == first.seq

        await repo.close()
        repo = PostgresChatRepository(dsn)
        await repo.init_db()
        assert await repo.send_message(**args) == (first, True)
        messages, _ = await repo.list_messages(room)
        assert messages[-1] == first
        if legacy:
            assert messages[0].sender_username == f"user_{str(sender)[:8]}"
            assert messages[0].text_content == "original"
    finally:
        await repo.close()
        await conn.close()
