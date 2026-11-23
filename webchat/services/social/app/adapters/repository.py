"""Repository adapters for Social service."""

from __future__ import annotations

import json
import logging
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from app.domain.exceptions import (
    ActionForbiddenError,
    AlreadyFriendsError,
    ConversationNotFoundError,
    DomainError,
    FriendshipRequiredError,
    IdempotencyConflictError,
    IncomingRequestExistsError,
    RequestClosedError,
    RequestNotFoundError,
    SelfConversationError,
)
from app.domain.models import (
    FriendRequestStatus,
    canonical_pair,
    validate_friend_request_actors,
    validate_group_members,
    validate_group_name,
)

logger = logging.getLogger("webchat.social")


@dataclass(frozen=True)
class StoredFriendRequest:
    id: uuid.UUID
    sender_id: uuid.UUID
    recipient_id: uuid.UUID
    status: FriendRequestStatus
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class StoredConversation:
    id: uuid.UUID
    type: str  # "direct" or "group"
    name: str | None
    created_by: uuid.UUID | None
    member_count: int
    created_at: datetime


class SocialRepository(ABC):
    @abstractmethod
    async def create_or_get_friend_request(
        self, sender_id: uuid.UUID, recipient_id: uuid.UUID
    ) -> tuple[StoredFriendRequest, bool]:
        """Return (friend_request, is_created)."""
        ...

    @abstractmethod
    async def list_friend_requests(
        self,
        user_id: uuid.UUID,
        direction: str | None = None,
        status: FriendRequestStatus | None = None,
    ) -> list[StoredFriendRequest]: ...

    @abstractmethod
    async def update_friend_request(
        self, request_id: uuid.UUID, actor_id: uuid.UUID, action: str
    ) -> StoredFriendRequest: ...

    @abstractmethod
    async def list_friends(self, user_id: uuid.UUID) -> list[uuid.UUID]: ...

    @abstractmethod
    async def remove_friend(self, user_a: uuid.UUID, user_b: uuid.UUID) -> None: ...

    @abstractmethod
    async def is_friend(self, user_a: uuid.UUID, user_b: uuid.UUID) -> bool: ...

    @abstractmethod
    async def get_or_create_direct_conversation(
        self, user_a: uuid.UUID, user_b: uuid.UUID
    ) -> tuple[StoredConversation, uuid.UUID, bool]:
        """Return (conv, peer_id, is_created)."""
        ...

    @abstractmethod
    async def create_group_conversation(
        self,
        creator_id: uuid.UUID,
        idempotency_key: str,
        name: str,
        member_ids: list[uuid.UUID],
        request_hash: str,
    ) -> tuple[int, dict[str, Any]]:
        """Return (status_code, response_dict)."""
        ...

    @abstractmethod
    async def list_conversations_for_user(
        self, user_id: uuid.UUID
    ) -> list[tuple[StoredConversation, uuid.UUID | None]]:
        """Return list of (conv, peer_id_if_direct)."""
        ...

    @abstractmethod
    async def get_conversation(
        self, conv_id: uuid.UUID, requester_id: uuid.UUID
    ) -> tuple[StoredConversation, uuid.UUID | None]: ...

    @abstractmethod
    async def get_conversation_members(
        self, conv_id: uuid.UUID, requester_id: uuid.UUID
    ) -> list[uuid.UUID]: ...

    @abstractmethod
    async def get_member_permissions(
        self, conv_id: uuid.UUID, user_id: uuid.UUID
    ) -> tuple[bool, bool]:
        """Return (can_read, can_send)."""
        ...

    @abstractmethod
    async def init_db(self) -> None: ...

    @abstractmethod
    async def close(self) -> None: ...


class MemorySocialRepository(SocialRepository):
    def __init__(self) -> None:
        # id -> StoredFriendRequest
        self._friend_requests: dict[uuid.UUID, StoredFriendRequest] = {}
        # set of (user_low, user_high)
        self._friendships: set[tuple[uuid.UUID, uuid.UUID]] = set()
        # id -> StoredConversation
        self._conversations: dict[uuid.UUID, StoredConversation] = {}
        # conv_id -> set of member_ids
        self._conv_members: dict[uuid.UUID, set[uuid.UUID]] = {}
        # (user_low, user_high) -> conv_id
        self._direct_pairs: dict[tuple[uuid.UUID, uuid.UUID], uuid.UUID] = {}
        # (user_id, idempotency_key) -> (request_hash, status_code, body_dict)
        self._idempotency: dict[tuple[uuid.UUID, str], tuple[str, int, dict[str, Any]]] = {}

    async def init_db(self) -> None:
        pass

    async def close(self) -> None:
        pass

    async def is_friend(self, user_a: uuid.UUID, user_b: uuid.UUID) -> bool:
        if user_a == user_b:
            return False
        pair = canonical_pair(user_a, user_b)
        return pair in self._friendships

    async def create_or_get_friend_request(
        self, sender_id: uuid.UUID, recipient_id: uuid.UUID
    ) -> tuple[StoredFriendRequest, bool]:
        validate_friend_request_actors(sender_id, recipient_id)

        # Check if already friends
        if await self.is_friend(sender_id, recipient_id):
            raise AlreadyFriendsError("Users are already friends.")

        # Check existing requests between pair
        for req in self._friend_requests.values():
            if req.status == FriendRequestStatus.PENDING:
                if req.sender_id == sender_id and req.recipient_id == recipient_id:
                    # Idempotent replay (200 OK)
                    return req, False
                if req.sender_id == recipient_id and req.recipient_id == sender_id:
                    # Reverse pending request exists -> 409 INCOMING_REQUEST_EXISTS
                    raise IncomingRequestExistsError(
                        related_id=str(req.id),
                        message="Recipient already sent a pending friend request to you.",
                    )

        now = datetime.now(UTC)
        new_req = StoredFriendRequest(
            id=uuid.uuid4(),
            sender_id=sender_id,
            recipient_id=recipient_id,
            status=FriendRequestStatus.PENDING,
            created_at=now,
            updated_at=now,
        )
        self._friend_requests[new_req.id] = new_req
        return new_req, True

    async def list_friend_requests(
        self,
        user_id: uuid.UUID,
        direction: str | None = None,
        status: FriendRequestStatus | None = None,
    ) -> list[StoredFriendRequest]:
        result: list[StoredFriendRequest] = []
        for req in self._friend_requests.values():
            if status is not None and req.status != status:
                continue
            if direction == "incoming":
                if req.recipient_id == user_id:
                    result.append(req)
            elif direction == "outgoing":
                if req.sender_id == user_id:
                    result.append(req)
            else:
                if req.sender_id == user_id or req.recipient_id == user_id:
                    result.append(req)
        # Order by created_at desc
        result.sort(key=lambda r: r.created_at, reverse=True)
        return result

    async def update_friend_request(
        self, request_id: uuid.UUID, actor_id: uuid.UUID, action: str
    ) -> StoredFriendRequest:
        req = self._friend_requests.get(request_id)
        if req is None:
            raise RequestNotFoundError(f"Friend request '{request_id}' not found.")

        target_status_map = {
            "accept": FriendRequestStatus.ACCEPTED,
            "accepted": FriendRequestStatus.ACCEPTED,
            "decline": FriendRequestStatus.DECLINED,
            "declined": FriendRequestStatus.DECLINED,
            "cancel": FriendRequestStatus.CANCELLED,
            "cancelled": FriendRequestStatus.CANCELLED,
        }
        target_status = target_status_map.get(action.lower())
        if not target_status:
            raise DomainError(f"Invalid action: {action}", code="VALIDATION_ERROR")

        # Actor permissions
        if target_status in (FriendRequestStatus.ACCEPTED, FriendRequestStatus.DECLINED):
            if req.recipient_id != actor_id:
                raise ActionForbiddenError("Only recipient can accept or decline this request.")
        elif target_status == FriendRequestStatus.CANCELLED:
            if req.sender_id != actor_id:
                raise ActionForbiddenError("Only sender can cancel this request.")

        # Idempotent replay
        if req.status == target_status:
            return req

        # Cannot transition closed request
        if req.status != FriendRequestStatus.PENDING:
            raise RequestClosedError("Friend request is already closed.")

        now = datetime.now(UTC)
        updated = StoredFriendRequest(
            id=req.id,
            sender_id=req.sender_id,
            recipient_id=req.recipient_id,
            status=target_status,
            created_at=req.created_at,
            updated_at=now,
        )
        self._friend_requests[req.id] = updated

        if target_status == FriendRequestStatus.ACCEPTED:
            pair = canonical_pair(req.sender_id, req.recipient_id)
            self._friendships.add(pair)

        return updated

    async def list_friends(self, user_id: uuid.UUID) -> list[uuid.UUID]:
        friends: list[uuid.UUID] = []
        for low, high in self._friendships:
            if low == user_id:
                friends.append(high)
            elif high == user_id:
                friends.append(low)
        friends.sort(key=str)
        return friends

    async def remove_friend(self, user_a: uuid.UUID, user_b: uuid.UUID) -> None:
        pair = canonical_pair(user_a, user_b)
        self._friendships.discard(pair)

    async def get_or_create_direct_conversation(
        self, user_a: uuid.UUID, user_b: uuid.UUID
    ) -> tuple[StoredConversation, uuid.UUID, bool]:
        if user_a == user_b:
            raise SelfConversationError("Cannot create conversation with yourself.")

        if not await self.is_friend(user_a, user_b):
            raise FriendshipRequiredError("Friendship required for direct conversation.")

        pair = canonical_pair(user_a, user_b)
        if pair in self._direct_pairs:
            conv_id = self._direct_pairs[pair]
            conv = self._conversations[conv_id]
            return conv, user_b, False

        conv_id = uuid.uuid4()
        now = datetime.now(UTC)
        conv = StoredConversation(
            id=conv_id,
            type="direct",
            name=None,
            created_by=None,
            member_count=2,
            created_at=now,
        )
        self._conversations[conv_id] = conv
        self._conv_members[conv_id] = {user_a, user_b}
        self._direct_pairs[pair] = conv_id
        return conv, user_b, True

    async def create_group_conversation(
        self,
        creator_id: uuid.UUID,
        idempotency_key: str,
        name: str,
        member_ids: list[uuid.UUID],
        request_hash: str,
    ) -> tuple[int, dict[str, Any]]:
        # Check idempotency (ADR 0005)
        key_tuple = (creator_id, idempotency_key)
        if key_tuple in self._idempotency:
            stored_hash, status_code, body = self._idempotency[key_tuple]
            if stored_hash == request_hash:
                return 200, body
            raise IdempotencyConflictError("Idempotency key reused with different request payload.")

        valid_name = validate_group_name(name)
        all_members = validate_group_members(creator_id, member_ids)

        # All other members must be friends of creator
        for mid in all_members:
            if mid != creator_id and not await self.is_friend(creator_id, mid):
                raise FriendshipRequiredError(f"User {mid} is not your friend.")

        conv_id = uuid.uuid4()
        now = datetime.now(UTC)
        conv = StoredConversation(
            id=conv_id,
            type="group",
            name=valid_name,
            created_by=creator_id,
            member_count=len(all_members),
            created_at=now,
        )
        self._conversations[conv_id] = conv
        self._conv_members[conv_id] = set(all_members)

        response_body = {
            "id": str(conv_id),
            "type": "group",
            "name": valid_name,
            "created_by": {
                "id": str(creator_id),
                "username": "",  # Will be enriched by API layer
                "created_at": "",
            },
            "member_count": len(all_members),
            "created_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        }

        self._idempotency[key_tuple] = (request_hash, 201, response_body)
        return 201, response_body

    async def list_conversations_for_user(
        self, user_id: uuid.UUID
    ) -> list[tuple[StoredConversation, uuid.UUID | None]]:
        result: list[tuple[StoredConversation, uuid.UUID | None]] = []
        for conv_id, members in self._conv_members.items():
            if user_id in members:
                conv = self._conversations[conv_id]
                peer_id: uuid.UUID | None = None
                if conv.type == "direct":
                    others = [m for m in members if m != user_id]
                    peer_id = others[0] if others else user_id
                result.append((conv, peer_id))
        result.sort(key=lambda item: item[0].created_at, reverse=True)
        return result

    async def get_conversation(
        self, conv_id: uuid.UUID, requester_id: uuid.UUID
    ) -> tuple[StoredConversation, uuid.UUID | None]:
        conv = self._conversations.get(conv_id)
        if conv is None:
            raise ConversationNotFoundError("Conversation not found.")
        members = self._conv_members.get(conv_id, set())
        if requester_id not in members:
            raise ConversationNotFoundError("Conversation not found.")
        peer_id: uuid.UUID | None = None
        if conv.type == "direct":
            others = [m for m in members if m != requester_id]
            peer_id = others[0] if others else requester_id
        return conv, peer_id

    async def get_conversation_members(
        self, conv_id: uuid.UUID, requester_id: uuid.UUID
    ) -> list[uuid.UUID]:
        members = self._conv_members.get(conv_id)
        if members is None or requester_id not in members:
            raise ConversationNotFoundError("Conversation not found.")
        return sorted(list(members), key=str)

    async def get_member_permissions(
        self, conv_id: uuid.UUID, user_id: uuid.UUID
    ) -> tuple[bool, bool]:
        members = self._conv_members.get(conv_id)
        if members is None or user_id not in members:
            return False, False
        return True, True


class PostgresSocialRepository(SocialRepository):
    """PostgreSQL implementation of SocialRepository using asyncpg."""

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
                CREATE TABLE IF NOT EXISTS friend_requests (
                    id UUID PRIMARY KEY,
                    sender_id UUID NOT NULL,
                    recipient_id UUID NOT NULL,
                    status VARCHAR(20) NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL,
                    updated_at TIMESTAMPTZ NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_fr_sender ON friend_requests (sender_id);
                CREATE INDEX IF NOT EXISTS idx_fr_recipient ON friend_requests (recipient_id);

                CREATE TABLE IF NOT EXISTS friendships (
                    user_low UUID NOT NULL,
                    user_high UUID NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL,
                    PRIMARY KEY (user_low, user_high)
                );

                CREATE TABLE IF NOT EXISTS conversations (
                    id UUID PRIMARY KEY,
                    type VARCHAR(10) NOT NULL,
                    name VARCHAR(80),
                    created_by UUID,
                    member_count INT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL
                );

                CREATE TABLE IF NOT EXISTS conversation_members (
                    conversation_id UUID NOT NULL,
                    user_id UUID NOT NULL,
                    joined_at TIMESTAMPTZ NOT NULL,
                    PRIMARY KEY (conversation_id, user_id)
                );

                CREATE TABLE IF NOT EXISTS direct_conversation_pairs (
                    conversation_id UUID NOT NULL,
                    user_low UUID NOT NULL,
                    user_high UUID NOT NULL,
                    UNIQUE (user_low, user_high)
                );

                CREATE TABLE IF NOT EXISTS idempotency_keys (
                    user_id UUID NOT NULL,
                    key VARCHAR(64) NOT NULL,
                    request_hash VARCHAR(64) NOT NULL,
                    response_status INT NOT NULL,
                    response_body TEXT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL,
                    PRIMARY KEY (user_id, key)
                );
            """)
        logger.info("PostgreSQL Social schema initialized successfully.")

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()

    async def is_friend(self, user_a: uuid.UUID, user_b: uuid.UUID) -> bool:
        if user_a == user_b:
            return False
        low, high = canonical_pair(user_a, user_b)
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT 1 FROM friendships WHERE user_low = $1 AND user_high = $2",
                low,
                high,
            )
            return row is not None

    async def create_or_get_friend_request(
        self, sender_id: uuid.UUID, recipient_id: uuid.UUID
    ) -> tuple[StoredFriendRequest, bool]:
        validate_friend_request_actors(sender_id, recipient_id)
        if await self.is_friend(sender_id, recipient_id):
            raise AlreadyFriendsError("Users are already friends.")

        async with self._pool.acquire() as conn:
            async with conn.transaction():
                # Check pending requests between pair
                rows = await conn.fetch(
                    """
                    SELECT id, sender_id, recipient_id, status, created_at, updated_at
                    FROM friend_requests
                    WHERE status = 'pending' AND (
                        (sender_id = $1 AND recipient_id = $2) OR
                        (sender_id = $2 AND recipient_id = $1)
                    )
                    """,
                    sender_id,
                    recipient_id,
                )
                for r in rows:
                    if r["sender_id"] == sender_id:
                        return StoredFriendRequest(
                            id=r["id"],
                            sender_id=r["sender_id"],
                            recipient_id=r["recipient_id"],
                            status=FriendRequestStatus(r["status"]),
                            created_at=r["created_at"].astimezone(UTC),
                            updated_at=r["updated_at"].astimezone(UTC),
                        ), False
                    if r["sender_id"] == recipient_id:
                        raise IncomingRequestExistsError(
                            related_id=str(r["id"]),
                            message="Recipient already sent a pending friend request to you.",
                        )

                now = datetime.now(UTC)
                req_id = uuid.uuid4()
                await conn.execute(
                    """
                    INSERT INTO friend_requests
                    (id, sender_id, recipient_id, status, created_at, updated_at)
                    VALUES ($1, $2, $3, 'pending', $4, $4)
                    """,
                    req_id,
                    sender_id,
                    recipient_id,
                    now,
                )
                return StoredFriendRequest(
                    id=req_id,
                    sender_id=sender_id,
                    recipient_id=recipient_id,
                    status=FriendRequestStatus.PENDING,
                    created_at=now,
                    updated_at=now,
                ), True

    async def list_friend_requests(
        self,
        user_id: uuid.UUID,
        direction: str | None = None,
        status: FriendRequestStatus | None = None,
    ) -> list[StoredFriendRequest]:
        query = (
            "SELECT id, sender_id, recipient_id, status, created_at, updated_at "
            "FROM friend_requests WHERE 1=1"
        )
        params: list[Any] = []

        if status:
            params.append(status.value)
            query += f" AND status = ${len(params)}"

        if direction == "incoming":
            params.append(user_id)
            query += f" AND recipient_id = ${len(params)}"
        elif direction == "outgoing":
            params.append(user_id)
            query += f" AND sender_id = ${len(params)}"
        else:
            params.append(user_id)
            query += f" AND (sender_id = ${len(params)} OR recipient_id = ${len(params)})"

        query += " ORDER BY created_at DESC"

        async with self._pool.acquire() as conn:
            rows = await conn.fetch(query, *params)
            return [
                StoredFriendRequest(
                    id=r["id"],
                    sender_id=r["sender_id"],
                    recipient_id=r["recipient_id"],
                    status=FriendRequestStatus(r["status"]),
                    created_at=r["created_at"].astimezone(UTC),
                    updated_at=r["updated_at"].astimezone(UTC),
                )
                for r in rows
            ]

    async def update_friend_request(
        self, request_id: uuid.UUID, actor_id: uuid.UUID, action: str
    ) -> StoredFriendRequest:
        target_status_map = {
            "accept": FriendRequestStatus.ACCEPTED,
            "accepted": FriendRequestStatus.ACCEPTED,
            "decline": FriendRequestStatus.DECLINED,
            "declined": FriendRequestStatus.DECLINED,
            "cancel": FriendRequestStatus.CANCELLED,
            "cancelled": FriendRequestStatus.CANCELLED,
        }
        target_status = target_status_map.get(action.lower())
        if not target_status:
            raise DomainError(f"Invalid action: {action}", code="VALIDATION_ERROR")

        async with self._pool.acquire() as conn:
            async with conn.transaction():
                query = (
                    "SELECT id, sender_id, recipient_id, status, created_at, updated_at "
                    "FROM friend_requests WHERE id = $1 FOR UPDATE"
                )
                row = await conn.fetchrow(query, request_id)
                if not row:
                    raise RequestNotFoundError(f"Friend request '{request_id}' not found.")

                sender_id = row["sender_id"]
                recipient_id = row["recipient_id"]
                curr_status = FriendRequestStatus(row["status"])

                if target_status in (FriendRequestStatus.ACCEPTED, FriendRequestStatus.DECLINED):
                    if recipient_id != actor_id:
                        raise ActionForbiddenError(
                            "Only recipient can accept or decline this request."
                        )
                elif target_status == FriendRequestStatus.CANCELLED:
                    if sender_id != actor_id:
                        raise ActionForbiddenError("Only sender can cancel this request.")

                if curr_status == target_status:
                    return StoredFriendRequest(
                        id=row["id"],
                        sender_id=sender_id,
                        recipient_id=recipient_id,
                        status=curr_status,
                        created_at=row["created_at"].astimezone(UTC),
                        updated_at=row["updated_at"].astimezone(UTC),
                    )

                if curr_status != FriendRequestStatus.PENDING:
                    raise RequestClosedError("Friend request is already closed.")

                now = datetime.now(UTC)
                await conn.execute(
                    "UPDATE friend_requests SET status = $1, updated_at = $2 WHERE id = $3",
                    target_status.value,
                    now,
                    request_id,
                )

                if target_status == FriendRequestStatus.ACCEPTED:
                    low, high = canonical_pair(sender_id, recipient_id)
                    await conn.execute(
                        """
                        INSERT INTO friendships (user_low, user_high, created_at)
                        VALUES ($1, $2, $3)
                        ON CONFLICT DO NOTHING
                        """,
                        low,
                        high,
                        now,
                    )

                return StoredFriendRequest(
                    id=request_id,
                    sender_id=sender_id,
                    recipient_id=recipient_id,
                    status=target_status,
                    created_at=row["created_at"].astimezone(UTC),
                    updated_at=now,
                )

    async def list_friends(self, user_id: uuid.UUID) -> list[uuid.UUID]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT CASE WHEN user_low = $1 THEN user_high ELSE user_low END AS friend_id
                FROM friendships
                WHERE user_low = $1 OR user_high = $1
                ORDER BY friend_id ASC
                """,
                user_id,
            )
            return [r["friend_id"] for r in rows]

    async def remove_friend(self, user_a: uuid.UUID, user_b: uuid.UUID) -> None:
        low, high = canonical_pair(user_a, user_b)
        async with self._pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM friendships WHERE user_low = $1 AND user_high = $2",
                low,
                high,
            )

    async def get_or_create_direct_conversation(
        self, user_a: uuid.UUID, user_b: uuid.UUID
    ) -> tuple[StoredConversation, uuid.UUID, bool]:
        if user_a == user_b:
            raise SelfConversationError("Cannot create conversation with yourself.")
        if not await self.is_friend(user_a, user_b):
            raise FriendshipRequiredError("Friendship required for direct conversation.")

        low, high = canonical_pair(user_a, user_b)
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                query = (
                    "SELECT conversation_id FROM direct_conversation_pairs "
                    "WHERE user_low = $1 AND user_high = $2"
                )
                pair_row = await conn.fetchrow(query, low, high)
                if pair_row:
                    conv_id = pair_row["conversation_id"]
                    conv_row = await conn.fetchrow(
                        "SELECT * FROM conversations WHERE id = $1", conv_id
                    )
                    return (
                        StoredConversation(
                            id=conv_row["id"],
                            type=conv_row["type"],
                            name=conv_row["name"],
                            created_by=conv_row["created_by"],
                            member_count=conv_row["member_count"],
                            created_at=conv_row["created_at"].astimezone(UTC),
                        ),
                        user_b,
                        False,
                    )

                conv_id = uuid.uuid4()
                now = datetime.now(UTC)
                await conn.execute(
                    """
                    INSERT INTO conversations (id, type, name, created_by, member_count, created_at)
                    VALUES ($1, 'direct', NULL, NULL, 2, $2)
                    """,
                    conv_id,
                    now,
                )
                await conn.execute(
                    """
                    INSERT INTO conversation_members (conversation_id, user_id, joined_at)
                    VALUES ($1, $2, $4), ($1, $3, $4)
                    """,
                    conv_id,
                    user_a,
                    user_b,
                    now,
                )
                await conn.execute(
                    """
                    INSERT INTO direct_conversation_pairs (conversation_id, user_low, user_high)
                    VALUES ($1, $2, $3)
                    """,
                    conv_id,
                    low,
                    high,
                )
                conv = StoredConversation(
                    id=conv_id,
                    type="direct",
                    name=None,
                    created_by=None,
                    member_count=2,
                    created_at=now,
                )
                return conv, user_b, True

    async def create_group_conversation(
        self,
        creator_id: uuid.UUID,
        idempotency_key: str,
        name: str,
        member_ids: list[uuid.UUID],
        request_hash: str,
    ) -> tuple[int, dict[str, Any]]:
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                # Check idempotency
                idemp_query = (
                    "SELECT request_hash, response_status, response_body "
                    "FROM idempotency_keys WHERE user_id = $1 AND key = $2"
                )
                row = await conn.fetchrow(idemp_query, creator_id, idempotency_key)
                if row:
                    if row["request_hash"] == request_hash:
                        return row["response_status"], json.loads(row["response_body"])
                    raise IdempotencyConflictError(
                        "Idempotency key reused with different request payload."
                    )

                valid_name = validate_group_name(name)
                all_members = validate_group_members(creator_id, member_ids)

                # Check all members are friends of creator
                for mid in all_members:
                    if mid != creator_id:
                        low, high = canonical_pair(creator_id, mid)
                        f_row = await conn.fetchrow(
                            "SELECT 1 FROM friendships WHERE user_low = $1 AND user_high = $2",
                            low,
                            high,
                        )
                        if not f_row:
                            raise FriendshipRequiredError(f"User {mid} is not your friend.")

                conv_id = uuid.uuid4()
                now = datetime.now(UTC)
                await conn.execute(
                    """
                    INSERT INTO conversations (id, type, name, created_by, member_count, created_at)
                    VALUES ($1, 'group', $2, $3, $4, $5)
                    """,
                    conv_id,
                    valid_name,
                    creator_id,
                    len(all_members),
                    now,
                )
                for mid in all_members:
                    await conn.execute(
                        """
                        INSERT INTO conversation_members (conversation_id, user_id, joined_at)
                        VALUES ($1, $2, $3)
                        """,
                        conv_id,
                        mid,
                        now,
                    )

                response_body = {
                    "id": str(conv_id),
                    "type": "group",
                    "name": valid_name,
                    "created_by": {
                        "id": str(creator_id),
                        "username": "",
                        "created_at": "",
                    },
                    "member_count": len(all_members),
                    "created_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
                }
                await conn.execute(
                    """
                    INSERT INTO idempotency_keys
                    (user_id, key, request_hash, response_status, response_body, created_at)
                    VALUES ($1, $2, $3, 201, $4, $5)
                    """,
                    creator_id,
                    idempotency_key,
                    request_hash,
                    json.dumps(response_body),
                    now,
                )
                return 201, response_body

    async def list_conversations_for_user(
        self, user_id: uuid.UUID
    ) -> list[tuple[StoredConversation, uuid.UUID | None]]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT c.id, c.type, c.name, c.created_by, c.member_count, c.created_at,
                       d.user_low, d.user_high
                FROM conversation_members m
                JOIN conversations c ON m.conversation_id = c.id
                LEFT JOIN direct_conversation_pairs d ON c.id = d.conversation_id
                WHERE m.user_id = $1
                ORDER BY c.created_at DESC
                """,
                user_id,
            )
            result: list[tuple[StoredConversation, uuid.UUID | None]] = []
            for r in rows:
                conv = StoredConversation(
                    id=r["id"],
                    type=r["type"],
                    name=r["name"],
                    created_by=r["created_by"],
                    member_count=r["member_count"],
                    created_at=r["created_at"].astimezone(UTC),
                )
                peer_id: uuid.UUID | None = None
                if conv.type == "direct":
                    low = r["user_low"]
                    high = r["user_high"]
                    peer_id = high if low == user_id else low
                result.append((conv, peer_id))
            return result

    async def get_conversation(
        self, conv_id: uuid.UUID, requester_id: uuid.UUID
    ) -> tuple[StoredConversation, uuid.UUID | None]:
        async with self._pool.acquire() as conn:
            # Check requester is member
            m_row = await conn.fetchrow(
                "SELECT 1 FROM conversation_members WHERE conversation_id = $1 AND user_id = $2",
                conv_id,
                requester_id,
            )
            if not m_row:
                raise ConversationNotFoundError("Conversation not found.")

            c_row = await conn.fetchrow(
                """
                SELECT c.id, c.type, c.name, c.created_by, c.member_count, c.created_at,
                       d.user_low, d.user_high
                FROM conversations c
                LEFT JOIN direct_conversation_pairs d ON c.id = d.conversation_id
                WHERE c.id = $1
                """,
                conv_id,
            )
            if not c_row:
                raise ConversationNotFoundError("Conversation not found.")

            conv = StoredConversation(
                id=c_row["id"],
                type=c_row["type"],
                name=c_row["name"],
                created_by=c_row["created_by"],
                member_count=c_row["member_count"],
                created_at=c_row["created_at"].astimezone(UTC),
            )
            peer_id: uuid.UUID | None = None
            if conv.type == "direct":
                low = c_row["user_low"]
                high = c_row["user_high"]
                peer_id = high if low == requester_id else low
            return conv, peer_id

    async def get_conversation_members(
        self, conv_id: uuid.UUID, requester_id: uuid.UUID
    ) -> list[uuid.UUID]:
        async with self._pool.acquire() as conn:
            m_row = await conn.fetchrow(
                "SELECT 1 FROM conversation_members WHERE conversation_id = $1 AND user_id = $2",
                conv_id,
                requester_id,
            )
            if not m_row:
                raise ConversationNotFoundError("Conversation not found.")

            q = (
                "SELECT user_id FROM conversation_members "
                "WHERE conversation_id = $1 ORDER BY user_id ASC"
            )
            rows = await conn.fetch(q, conv_id)
            return [r["user_id"] for r in rows]

    async def get_member_permissions(
        self, conv_id: uuid.UUID, user_id: uuid.UUID
    ) -> tuple[bool, bool]:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT 1 FROM conversation_members WHERE conversation_id = $1 AND user_id = $2",
                conv_id,
                user_id,
            )
            if not row:
                return False, False
            return True, True


_global_social_repo: SocialRepository | None = None


async def get_social_repository() -> SocialRepository:
    global _global_social_repo
    if _global_social_repo is not None:
        return _global_social_repo

    from app.settings import get_settings

    settings = get_settings()

    dsn = settings.database_url
    if dsn and (dsn.startswith("postgresql://") or dsn.startswith("postgresql+asyncpg://")):
        try:
            repo = PostgresSocialRepository(dsn)
            await repo.init_db()
            _global_social_repo = repo
            return _global_social_repo
        except Exception as exc:
            logger.warning(
                "Could not connect to Postgres Social (%s), fallback to Memory repo", exc
            )

    mem_repo = MemorySocialRepository()
    await mem_repo.init_db()
    _global_social_repo = mem_repo
    return _global_social_repo


def set_social_repository(repo: SocialRepository | None) -> None:
    global _global_social_repo
    _global_social_repo = repo
