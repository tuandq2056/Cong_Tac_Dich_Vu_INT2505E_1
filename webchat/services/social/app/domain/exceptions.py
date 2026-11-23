"""Domain exceptions for Social service. Framework-free."""

from __future__ import annotations


class DomainError(Exception):
    """Base exception for all domain business rule violations."""

    def __init__(self, message: str, code: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.code = code


class UserNotFoundError(DomainError):
    def __init__(self, message: str = "User not found.") -> None:
        super().__init__(message, code="USER_NOT_FOUND")


class SelfInviteError(DomainError):
    def __init__(self, message: str = "Cannot send a friend request to yourself.") -> None:
        super().__init__(message, code="SELF_INVITE")


class AlreadyFriendsError(DomainError):
    def __init__(self, message: str = "Users are already friends.") -> None:
        super().__init__(message, code="ALREADY_FRIENDS")


class IncomingRequestExistsError(DomainError):
    def __init__(
        self,
        related_id: str,
        message: str = "An incoming friend request from this user already exists.",
    ) -> None:
        super().__init__(message, code="INCOMING_REQUEST_EXISTS")
        self.related_id = related_id


class ActionForbiddenError(DomainError):
    def __init__(self, message: str = "Action forbidden.") -> None:
        super().__init__(message, code="ACTION_FORBIDDEN")


class RequestNotFoundError(DomainError):
    def __init__(self, message: str = "Friend request not found.") -> None:
        super().__init__(message, code="REQUEST_NOT_FOUND")


class RequestClosedError(DomainError):
    def __init__(self, message: str = "Friend request is already closed.") -> None:
        super().__init__(message, code="REQUEST_CLOSED")


class InvalidCursorError(DomainError):
    def __init__(self, message: str = "Invalid or expired pagination cursor.") -> None:
        super().__init__(message, code="INVALID_CURSOR")


class SelfConversationError(DomainError):
    def __init__(self, message: str = "Cannot create a direct conversation with yourself.") -> None:
        super().__init__(message, code="SELF_CONVERSATION")


class FriendshipRequiredError(DomainError):
    def __init__(self, message: str = "Friendship is required to perform this action.") -> None:
        super().__init__(message, code="FRIENDSHIP_REQUIRED")


class ConversationNotFoundError(DomainError):
    def __init__(self, message: str = "Conversation not found.") -> None:
        super().__init__(message, code="CONVERSATION_NOT_FOUND")


class InvalidMembersError(DomainError):
    def __init__(self, message: str = "Invalid group members specification.") -> None:
        super().__init__(message, code="INVALID_MEMBERS")


class IdempotencyConflictError(DomainError):
    def __init__(self, message: str = "Idempotency key reused with different payload.") -> None:
        super().__init__(message, code="IDEMPOTENCY_CONFLICT")


class IdentityUnavailableError(DomainError):
    def __init__(self, message: str = "Identity service is currently unavailable.") -> None:
        super().__init__(message, code="IDENTITY_UNAVAILABLE")


class SocialUnavailableError(DomainError):
    def __init__(self, message: str = "Social data store is currently unavailable.") -> None:
        super().__init__(message, code="SOCIAL_UNAVAILABLE")


class ServiceForbiddenError(DomainError):
    def __init__(self, message: str = "Service token forbidden.") -> None:
        super().__init__(message, code="SERVICE_FORBIDDEN")


class UnauthenticatedError(DomainError):
    def __init__(self, message: str = "Authentication required.") -> None:
        super().__init__(message, code="UNAUTHENTICATED")
