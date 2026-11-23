"""Runtime configuration for the social service."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    service_name: str = "social"
    database_url: str = "postgresql+asyncpg://webchat:webchat@localhost:5432/social"
    jwt_secret: str = "dev-only-change-me"
    jwt_issuer: str = "webchat-identity"
    jwt_audience: str = "webchat"

    @property
    def using_development_secret(self) -> bool:
        return self.jwt_secret == "dev-only-change-me"


@lru_cache
def get_settings() -> Settings:
    return Settings()
