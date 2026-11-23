"""Identity service client for Social service."""

from __future__ import annotations

import time
import uuid
from datetime import datetime
from typing import Any

import httpx
import jwt

from app.domain.exceptions import IdentityUnavailableError, UserNotFoundError
from app.settings import Settings


def make_service_token(settings: Settings) -> str:
    now = int(time.time())
    payload = {
        "iss": "webchat-social",
        "sub": "social",
        "aud": settings.identity_internal_audience,
        "iat": now,
        "exp": now + 3600,
    }
    return jwt.encode(payload, settings.service_jwt_secret, algorithm="HS256")


class IdentityClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._cache: dict[uuid.UUID, dict[str, Any]] = {}

    def set_user_cache(self, user_id: uuid.UUID, username: str, created_at: datetime) -> None:
        self._cache[user_id] = {
            "id": str(user_id),
            "username": username,
            "created_at": created_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
        }

    async def get_user(self, user_id: uuid.UUID) -> dict[str, Any]:
        if user_id in self._cache:
            return self._cache[user_id]

        url = f"{self.settings.identity_url.rstrip('/')}/internal/v1/users/{user_id}"
        token = make_service_token(self.settings)
        headers = {"Authorization": f"Bearer {token}"}

        try:
            async with httpx.AsyncClient(timeout=0.5) as client:
                res = await client.get(url, headers=headers)
                if res.status_code == 200:
                    data = res.json()
                    self._cache[user_id] = data
                    return data
                if res.status_code == 404:
                    raise UserNotFoundError(f"User '{user_id}' does not exist.")
                raise IdentityUnavailableError("Identity service returned error response.")
        except httpx.RequestError as exc:
            # Check if we have in cache or raise IdentityUnavailableError
            if user_id in self._cache:
                return self._cache[user_id]
            raise IdentityUnavailableError(f"Cannot connect to identity service: {exc}") from exc


_global_identity_client: IdentityClient | None = None


def get_identity_client() -> IdentityClient:
    global _global_identity_client
    if _global_identity_client is None:
        from app.settings import get_settings

        settings = get_settings()
        _global_identity_client = IdentityClient(settings)
    return _global_identity_client


def set_identity_client(client: IdentityClient | None) -> None:
    global _global_identity_client
    _global_identity_client = client
