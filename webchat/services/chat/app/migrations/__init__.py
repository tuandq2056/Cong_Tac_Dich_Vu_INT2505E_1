"""Upgrade the Chat database in one PostgreSQL transaction."""

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import Connection, text
from sqlalchemy.ext.asyncio import create_async_engine


def _upgrade(connection: Connection) -> None:
    # Serialize startup of multiple processes, including creation of alembic_version.
    connection.execute(text("SELECT pg_advisory_xact_lock(704110001)"))
    config = Config()
    config.set_main_option("script_location", Path(__file__).parent.as_posix())
    config.attributes["connection"] = connection
    command.upgrade(config, "head")


async def upgrade_database(dsn: str) -> None:
    url = dsn.replace("postgresql://", "postgresql+asyncpg://", 1)
    engine = create_async_engine(url)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(_upgrade)
    finally:
        await engine.dispose()
