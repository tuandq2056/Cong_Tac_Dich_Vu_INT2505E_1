"""HTTP entry point for the social service."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.adapters.repository import get_social_repository
from app.api.conversations import router as conversations_router
from app.api.errors import register_error_handlers
from app.api.friends import router as friends_router
from app.api.internal import router as internal_router
from app.settings import get_settings


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    repo = await get_social_repository(settings)
    yield
    await repo.close()


def create_app() -> FastAPI:
    """Build the application. Tests call this with a test configuration."""
    settings = get_settings()
    app = FastAPI(
        title="WebChat Social",
        version="1.0.0",
        description="Friendships, conversations and membership.",
        lifespan=lifespan,
    )

    register_error_handlers(app)

    @app.get("/healthz", tags=["ops"], summary="Liveness check")
    def healthz() -> dict[str, str]:
        return {"status": "ok", "service": settings.service_name}

    app.include_router(friends_router)
    app.include_router(conversations_router)
    app.include_router(internal_router)

    return app
