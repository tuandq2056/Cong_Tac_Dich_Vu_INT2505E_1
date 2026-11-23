"""HTTP entry point for the chat service."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.adapters.repository import get_chat_repository
from app.api.chat import router as chat_router
from app.api.errors import register_error_handlers
from app.api.websocket import router as ws_router
from app.settings import get_settings


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    repo = await get_chat_repository(settings)
    yield
    await repo.close()


def create_app() -> FastAPI:
    """Build the application. Tests call this with a test configuration."""
    settings = get_settings()
    app = FastAPI(
        title="WebChat Chat",
        version="1.0.0",
        description="Messages, attachments, read-state and summaries.",
        lifespan=lifespan,
    )

    register_error_handlers(app)

    @app.get("/healthz", tags=["ops"], summary="Liveness check")
    def healthz() -> dict[str, str]:
        return {"status": "ok", "service": settings.service_name}

    app.include_router(chat_router)
    app.include_router(ws_router)

    return app
