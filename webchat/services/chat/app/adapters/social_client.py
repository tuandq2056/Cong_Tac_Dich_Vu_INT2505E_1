"""Social service client for Chat service."""

from __future__ import annotations

import time
import uuid

import httpx
import jwt

from app.domain.exceptions import SocialUnavailableError
from app.settings import Settings


def make_service_token(settings: Settings) -> str:
    now = int(time.time())
    payload = {
        "iss": "webchat-chat",
        "sub": "chat",
        "aud": settings.social_internal_audience,
        "iat": now,
        "exp": now + 3600,
    }
    return jwt.encode(payload, settings.service_jwt_secret, algorithm="HS256")


class SocialClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        # (conv_id, user_id) -> (can_read, can_send)
        self._perms_cache: dict[tuple[uuid.UUID, uuid.UUID], tuple[bool, bool]] = {}

    def set_permission(
        self, conv_id: uuid.UUID, user_id: uuid.UUID, can_read: bool, can_send: bool
    ) -> None:
        self._perms_cache[(conv_id, user_id)] = (can_read, can_send)

    async def check_permissions(self, conv_id: uuid.UUID, user_id: uuid.UUID) -> tuple[bool, bool]:
        key = (conv_id, user_id)
        if key in self._perms_cache:
            return self._perms_cache[key]

        base = self.settings.social_url.rstrip("/")
        url = f"{base}/internal/v1/conversations/{conv_id}/members/{user_id}/permissions"
        token = make_service_token(self.settings)
        headers = {"Authorization": f"Bearer {token}"}

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.get(url, headers=headers)
                if res.status_code == 200:
                    data = res.json()
                    can_read = bool(data.get("can_read", False))
                    can_send = bool(data.get("can_send", False))
                    self._perms_cache[key] = (can_read, can_send)
                    return can_read, can_send
                if res.status_code == 404:
                    return False, False
                raise SocialUnavailableError("Social service returned error status.")
        except httpx.RequestError as exc:
            # Check cache or raise
            if key in self._perms_cache:
                return self._perms_cache[key]
            raise SocialUnavailableError(f"Cannot connect to social service: {exc}") from exc


_global_social_client: SocialClient | None = None


def get_social_client() -> SocialClient:
    global _global_social_client
    if _global_social_client is None:
        from app.settings import get_settings

        settings = get_settings()
        _global_social_client = SocialClient(settings)
    return _global_social_client


def set_social_client(client: SocialClient | None) -> None:
    global _global_social_client
    _global_social_client = client
