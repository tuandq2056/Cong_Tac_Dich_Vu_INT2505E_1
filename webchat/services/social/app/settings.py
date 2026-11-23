"""Runtime configuration for the social service."""

import os
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
        populate_by_name=True,
    )

    service_name: str = "social"
    database_url: str = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://webchat:webchat@localhost:5432/social",
    )
    identity_url: str = os.getenv("IDENTITY_URL", "http://identity:8000")
    jwt_secret: str = os.getenv("WEBCHAT_JWT_SECRET", "dev-only-change-me")
    jwt_issuer: str = os.getenv("WEBCHAT_JWT_ISSUER", "webchat-identity")
    jwt_audience: str = os.getenv("WEBCHAT_JWT_AUDIENCE", "webchat")
    service_jwt_secret: str = os.getenv("SERVICE_JWT_SECRET", "dev-only-service-secret")
    identity_internal_audience: str = os.getenv("IDENTITY_INTERNAL_AUDIENCE", "identity-internal")
    internal_audience: str = os.getenv("SOCIAL_INTERNAL_AUDIENCE", "social-internal")

    @property
    def using_development_secret(self) -> bool:
        return self.jwt_secret == "dev-only-change-me"


@lru_cache
def get_settings() -> Settings:
    return Settings()
