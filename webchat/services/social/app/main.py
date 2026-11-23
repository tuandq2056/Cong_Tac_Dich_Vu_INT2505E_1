"""HTTP entry point for the social service."""

from fastapi import FastAPI

from app.api.errors import register_error_handlers
from app.settings import get_settings


def create_app() -> FastAPI:
    """Build the application. Tests call this with a test configuration."""
    settings = get_settings()
    app = FastAPI(
        title="WebChat Social",
        version="1.0.0",
        description="Friendships, conversations and membership.",
    )

    register_error_handlers(app)

    @app.get("/healthz", tags=["ops"], summary="Liveness check")
    def healthz() -> dict[str, str]:
        return {"status": "ok", "service": settings.service_name}

    return app
