"""HTTP entry point for the identity service."""

from fastapi import FastAPI

from app.api.errors import register_error_handlers
from app.settings import get_settings


def create_app() -> FastAPI:
    """Build the application. Tests call this with a test configuration."""
    settings = get_settings()
    app = FastAPI(
        title="WebChat Identity",
        version="1.0.0",
        description="Accounts, usernames and tokens.",
    )

    register_error_handlers(app)

    @app.get("/healthz", tags=["ops"], summary="Liveness check")
    def healthz() -> dict[str, str]:
        return {"status": "ok", "service": settings.service_name}

    return app
