"""Apply pending Chat migrations using the configured DATABASE_URL."""

import asyncio

from app.migrations import upgrade_database
from app.settings import get_settings

if __name__ == "__main__":
    asyncio.run(upgrade_database(get_settings().database_url))
