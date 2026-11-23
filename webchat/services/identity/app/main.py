"""HTTP entry point for the identity service."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.adapters.repository import get_repository
from app.api.auth import router as auth_router
from app.api.errors import register_error_handlers
from app.api.internal import router as internal_router
from app.api.users import router as users_router
from app.settings import get_settings


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    repo = await get_repository()
    yield
    await repo.close()


def create_app() -> FastAPI:
    """Build the application. Tests call this with a test configuration."""
    settings = get_settings()
    app = FastAPI(
        title="WebChat Identity",
        version="1.0.0",
        description="Accounts, usernames and tokens.",
        lifespan=lifespan,
    )

    register_error_handlers(app)

    @app.get("/healthz", tags=["ops"], summary="Liveness check")
    def healthz() -> dict[str, str]:
        return {"status": "ok", "service": settings.service_name}

    app.include_router(auth_router)
    app.include_router(users_router)
    app.include_router(internal_router)

    return app
