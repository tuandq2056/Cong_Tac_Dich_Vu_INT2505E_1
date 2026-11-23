"""Domain exceptions for Chat service. Framework-free."""

from __future__ import annotations


class DomainError(Exception):
    """Base exception for all domain business rule violations."""

    def __init__(self, message: str, code: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.code = code


class ConversationNotFoundError(DomainError):
    def __init__(self, message: str = "Conversation not found.") -> None:
        super().__init__(message, code="CONVERSATION_NOT_FOUND")


class AttachmentNotFoundError(DomainError):
    def __init__(self, message: str = "Attachment not found.") -> None:
        super().__init__(message, code="ATTACHMENT_NOT_FOUND")


class InvalidAttachmentError(DomainError):
    def __init__(self, message: str = "Invalid attachment file or metadata.") -> None:
        super().__init__(message, code="INVALID_ATTACHMENT")


class UploadTooLargeError(DomainError):
    def __init__(self, message: str = "Attachment exceeds maximum allowed upload size.") -> None:
        super().__init__(message, code="UPLOAD_TOO_LARGE")


class UnsupportedMediaTypeError(DomainError):
    def __init__(self, message: str = "Unsupported media type.") -> None:
        super().__init__(message, code="UNSUPPORTED_MEDIA_TYPE")


class InvalidRangeError(DomainError):
    def __init__(self, message: str = "Invalid message sequence range.") -> None:
        super().__init__(message, code="INVALID_RANGE")


class ReadAheadError(DomainError):
    def __init__(
        self,
        message: str = "Cannot advance read state beyond latest message sequence.",
    ) -> None:
        super().__init__(message, code="READ_AHEAD")


class SummaryUnavailableError(DomainError):
    def __init__(
        self,
        message: str = "Unread summary provider is temporarily unavailable.",
    ) -> None:
        super().__init__(message, code="SUMMARY_UNAVAILABLE")


class FriendshipRequiredError(DomainError):
    def __init__(self, message: str = "Friendship is required to perform this action.") -> None:
        super().__init__(message, code="FRIENDSHIP_REQUIRED")


class SocialUnavailableError(DomainError):
    def __init__(self, message: str = "Social service is currently unavailable.") -> None:
        super().__init__(message, code="SOCIAL_UNAVAILABLE")


class ChatUnavailableError(DomainError):
    def __init__(self, message: str = "Chat data store is currently unavailable.") -> None:
        super().__init__(message, code="CHAT_UNAVAILABLE")


class ClientMessageIdConflictError(DomainError):
    def __init__(self, message: str = "Client message ID conflict with different payload.") -> None:
        super().__init__(message, code="CLIENT_MESSAGE_ID_CONFLICT")


class AttachmentKindMismatchError(DomainError):
    def __init__(self, message: str = "Attachment kind does not match content.") -> None:
        super().__init__(message, code="ATTACHMENT_KIND_MISMATCH")


class AttachmentInUseError(DomainError):
    def __init__(self, message: str = "Attachment is already bound to a message.") -> None:
        super().__init__(message, code="ATTACHMENT_IN_USE")


class UnauthenticatedError(DomainError):
    def __init__(self, message: str = "Authentication required.") -> None:
        super().__init__(message, code="UNAUTHENTICATED")


class ServiceForbiddenError(DomainError):
    def __init__(self, message: str = "Service token forbidden.") -> None:
        super().__init__(message, code="SERVICE_FORBIDDEN")
