"""Domain exceptions for Identity service. Framework-free."""

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


class UsernameTakenError(DomainError):
    def __init__(self, message: str = "Username is already taken.") -> None:
        super().__init__(message, code="USERNAME_TAKEN")


class InvalidCredentialsError(DomainError):
    def __init__(self, message: str = "Invalid username or password.") -> None:
        super().__init__(message, code="INVALID_CREDENTIALS")


class UnauthenticatedError(DomainError):
    def __init__(self, message: str = "Authentication required.") -> None:
        super().__init__(message, code="UNAUTHENTICATED")


class ServiceForbiddenError(DomainError):
    def __init__(self, message: str = "Service token forbidden.") -> None:
        super().__init__(message, code="SERVICE_FORBIDDEN")


class GoogleDisabledError(DomainError):
    def __init__(self, message: str = "Google OAuth is disabled.") -> None:
        super().__init__(message, code="GOOGLE_DISABLED")


class GoogleUnavailableError(DomainError):
    def __init__(self, message: str = "Google OAuth service is unavailable.") -> None:
        super().__init__(message, code="GOOGLE_UNAVAILABLE")


class GoogleCodeInvalidError(DomainError):
    def __init__(self, message: str = "Google authorization code is invalid.") -> None:
        super().__init__(message, code="GOOGLE_CODE_INVALID")


class OAuthStateInvalidError(DomainError):
    def __init__(self, message: str = "OAuth state parameter is invalid or expired.") -> None:
        super().__init__(message, code="OAUTH_STATE_INVALID")


class IdentityUnavailableError(DomainError):
    def __init__(self, message: str = "Identity store is unavailable.") -> None:
        super().__init__(message, code="IDENTITY_UNAVAILABLE")
