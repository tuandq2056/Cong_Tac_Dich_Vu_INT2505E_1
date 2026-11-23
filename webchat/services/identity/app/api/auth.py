"""Authentication endpoints for Identity service."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.adapters.repository import UserRepository, get_repository
from app.adapters.security import (
    create_access_token,
    hash_password,
    verify_password,
)
from app.api.schemas import (
    CredentialsRequest,
    GoogleExchangeRequest,
    PublicUserResponse,
    TokenResponse,
    format_utc_z,
)
from app.domain.exceptions import (
    GoogleDisabledError,
    InvalidCredentialsError,
)
from app.domain.models import User, normalize_username, validate_password
from app.settings import Settings, get_settings

router = APIRouter(prefix="/api/v1/auth", tags=["Identity"])


@router.post(
    "/register",
    status_code=status.HTTP_201_CREATED,
    response_model=PublicUserResponse,
    summary="Create an account",
)
async def register(
    payload: CredentialsRequest,
    settings: Annotated[Settings, Depends(get_settings)],
) -> PublicUserResponse:
    # Validate username and password using framework-free domain logic
    normalized_name = normalize_username(payload.username)
    validate_password(payload.password)

    repo: UserRepository = await get_repository(settings)
    pwd_hash = hash_password(payload.password)
    user = User.create(username=normalized_name)
    saved_user = await repo.create_user(user, pwd_hash)

    return PublicUserResponse(
        id=saved_user.id,
        username=saved_user.username,
        created_at=format_utc_z(saved_user.created_at),
    )


@router.post(
    "/login",
    status_code=status.HTTP_200_OK,
    response_model=TokenResponse,
    summary="Exchange credentials for an access token",
)
async def login(
    payload: CredentialsRequest,
    settings: Annotated[Settings, Depends(get_settings)],
) -> TokenResponse:
    # Basic validation
    try:
        normalized_name = normalize_username(payload.username)
        validate_password(payload.password)
    except Exception as exc:
        raise InvalidCredentialsError("Invalid username or password.") from exc

    repo: UserRepository = await get_repository(settings)
    found = await repo.get_by_username(normalized_name)
    if found is None:
        raise InvalidCredentialsError("Invalid username or password.")

    user, pwd_hash = found
    if not verify_password(payload.password, pwd_hash):
        raise InvalidCredentialsError("Invalid username or password.")

    token = create_access_token(user.id, user.username, settings)
    return TokenResponse(
        access_token=token,
        token_type="bearer",
        expires_in=3600,
        user=PublicUserResponse(
            id=user.id,
            username=user.username,
            created_at=format_utc_z(user.created_at),
        ),
    )


@router.get(
    "/google/start",
    summary="Initiate Google OAuth2 flow",
)
async def google_start(
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, str]:
    if not settings.google_enabled:
        raise GoogleDisabledError("Google login is disabled in this environment.")
    return {"url": "https://accounts.google.com/o/oauth2/v2/auth"}


@router.post(
    "/google/exchange",
    summary="Exchange Google authorization code",
)
async def google_exchange(
    payload: GoogleExchangeRequest,
    settings: Annotated[Settings, Depends(get_settings)],
) -> TokenResponse:
    if not settings.google_enabled:
        raise GoogleDisabledError("Google login is disabled in this environment.")
    raise GoogleDisabledError("Google login is disabled in this environment.")
