"""Repository adapters for user persistence in Identity service."""

from __future__ import annotations

import logging
import uuid
from abc import ABC, abstractmethod
from datetime import UTC
from typing import Any

from app.domain.exceptions import UsernameTakenError
from app.domain.models import User
from app.settings import Settings

logger = logging.getLogger("webchat.identity")


class UserRepository(ABC):
    @abstractmethod
    async def get_by_id(self, user_id: uuid.UUID) -> tuple[User, str] | None:
        """Return (User, password_hash) or None."""
        ...

    @abstractmethod
    async def get_by_username(self, username: str) -> tuple[User, str] | None:
        """Lookup by normalized username, case-insensitive."""
        ...

    @abstractmethod
    async def create_user(self, user: User, password_hash: str) -> User:
        """Persist a new user. Raise UsernameTakenError on collision."""
        ...

    @abstractmethod
    async def init_db(self) -> None:
        """Initialize tables/indices."""
        ...

    @abstractmethod
    async def close(self) -> None:
        """Clean up connection pools."""
        ...


class MemoryUserRepository(UserRepository):
    """In-memory thread/task safe repository for unit testing and offline fallbacks."""

    def __init__(self) -> None:
        # id -> (User, password_hash)
        self._by_id: dict[uuid.UUID, tuple[User, str]] = {}
        # normalized username -> id
        self._by_username: dict[str, uuid.UUID] = {}

    async def get_by_id(self, user_id: uuid.UUID) -> tuple[User, str] | None:
        return self._by_id.get(user_id)

    async def get_by_username(self, username: str) -> tuple[User, str] | None:
        normalized = username.strip().lower()
        uid = self._by_username.get(normalized)
        if uid is None:
            return None
        return self._by_id.get(uid)

    async def create_user(self, user: User, password_hash: str) -> User:
        normalized = user.username.lower()
        if normalized in self._by_username:
            raise UsernameTakenError(f"Username '{user.username}' is already taken.")
        self._by_id[user.id] = (user, password_hash)
        self._by_username[normalized] = user.id
        return user

    async def init_db(self) -> None:
        pass

    async def close(self) -> None:
        pass


class PostgresUserRepository(UserRepository):
    """PostgreSQL repository using asyncpg."""

    def __init__(self, dsn: str) -> None:
        # Normalize postgresql+asyncpg:// to postgresql://
        if dsn.startswith("postgresql+asyncpg://"):
            dsn = "postgresql://" + dsn[len("postgresql+asyncpg://") :]
        self._dsn = dsn
        self._pool: Any = None

    async def init_db(self) -> None:
        import asyncpg

        self._pool = await asyncpg.create_pool(dsn=self._dsn, min_size=1, max_size=10)
        async with self._pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id UUID PRIMARY KEY,
                    username VARCHAR(32) UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_users_username_lower ON users (LOWER(username));
            """)
        logger.info("PostgreSQL Identity schema initialized successfully.")

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()

    async def get_by_id(self, user_id: uuid.UUID) -> tuple[User, str] | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT id, username, password_hash, created_at FROM users WHERE id = $1",
                user_id,
            )
            if not row:
                return None
            user = User(
                id=row["id"],
                username=row["username"],
                created_at=row["created_at"].astimezone(UTC),
            )
            return user, row["password_hash"]

    async def get_by_username(self, username: str) -> tuple[User, str] | None:
        normalized = username.strip().lower()
        async with self._pool.acquire() as conn:
            query = (
                "SELECT id, username, password_hash, created_at "
                "FROM users WHERE LOWER(username) = $1"
            )
            row = await conn.fetchrow(query, normalized)
            if not row:
                return None
            user = User(
                id=row["id"],
                username=row["username"],
                created_at=row["created_at"].astimezone(UTC),
            )
            return user, row["password_hash"]

    async def create_user(self, user: User, password_hash: str) -> User:
        import asyncpg

        async with self._pool.acquire() as conn:
            try:
                await conn.execute(
                    """
                    INSERT INTO users (id, username, password_hash, created_at)
                    VALUES ($1, $2, $3, $4)
                    """,
                    user.id,
                    user.username,
                    password_hash,
                    user.created_at,
                )
                return user
            except asyncpg.UniqueViolationError as exc:
                raise UsernameTakenError(f"Username '{user.username}' is already taken.") from exc


_global_repo: UserRepository | None = None


async def get_repository(settings: Settings | None = None) -> UserRepository:
    global _global_repo
    if _global_repo is not None:
        return _global_repo

    if settings is None:
        from app.settings import get_settings

        settings = get_settings()

    dsn = settings.database_url
    if dsn and (dsn.startswith("postgresql://") or dsn.startswith("postgresql+asyncpg://")):
        try:
            repo = PostgresUserRepository(dsn)
            await repo.init_db()
            _global_repo = repo
            return _global_repo
        except Exception as exc:
            logger.warning(
                "Could not connect to Postgres (%s), fallback to Memory repo", exc
            )

    mem_repo = MemoryUserRepository()
    await mem_repo.init_db()
    _global_repo = mem_repo
    return _global_repo


def set_repository(repo: UserRepository | None) -> None:
    global _global_repo
    _global_repo = repo
