"""Identity domain models and business invariants. Framework-free."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from .exceptions import DomainError

USERNAME_PATTERN = re.compile(r"^[a-zA-Z0-9_]{3,32}$")


class InvalidUsernameError(DomainError):
    def __init__(
        self,
        message: str = "Username must be 3-32 ASCII alphanumeric or underscore characters.",
    ) -> None:
        super().__init__(message, code="INVALID_USERNAME")


class InvalidPasswordError(DomainError):
    def __init__(
        self,
        message: str = "Password must be between 8 and 128 Unicode code points.",
    ) -> None:
        super().__init__(message, code="INVALID_PASSWORD")


def normalize_username(raw: str) -> str:
    """Validate and normalize username to lowercase per spec."""
    if not isinstance(raw, str) or not USERNAME_PATTERN.match(raw):
        raise InvalidUsernameError()
    return raw.lower()


def validate_password(password: str) -> None:
    """Validate password length in Unicode code points, preserving whitespace."""
    if not isinstance(password, str):
        raise InvalidPasswordError()
    length = len(password)
    if length < 8 or length > 128:
        raise InvalidPasswordError()


@dataclass(frozen=True)
class User:
    id: uuid.UUID
    username: str
    created_at: datetime

    @classmethod
    def create(cls, username: str, user_id: uuid.UUID | None = None) -> User:
        return cls(
            id=user_id or uuid.uuid4(),
            username=normalize_username(username),
            created_at=datetime.now(UTC),
        )
