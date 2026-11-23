"""Runtime configuration for the chat service."""

import os
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
        populate_by_name=True,
    )

    service_name: str = "chat"
    database_url: str = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://webchat:webchat@localhost:5432/chat",
    )
    social_url: str = os.getenv("SOCIAL_URL", "http://social:8000")
    identity_url: str = os.getenv("IDENTITY_URL", "http://identity:8000")
    jwt_secret: str = os.getenv("WEBCHAT_JWT_SECRET", "dev-only-change-me")
    jwt_issuer: str = os.getenv("WEBCHAT_JWT_ISSUER", "webchat-identity")
    jwt_audience: str = os.getenv("WEBCHAT_JWT_AUDIENCE", "webchat")
    service_jwt_secret: str = os.getenv("SERVICE_JWT_SECRET", "dev-only-service-secret")
    social_internal_audience: str = os.getenv("SOCIAL_INTERNAL_AUDIENCE", "social-internal")
    attachment_root: str = os.getenv("ATTACHMENT_ROOT", "/tmp/webchat/attachments")

    @property
    def using_development_secret(self) -> bool:
        return self.jwt_secret == "dev-only-change-me"


@lru_cache
def get_settings() -> Settings:
    return Settings()
