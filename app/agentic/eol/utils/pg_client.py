"""asyncpg pool singleton for the EOL platform.

Phase 8: Foundation for all PostgreSQL domain repositories.
All repos accept this pool in their constructors.

Usage:
    from utils.pg_client import postgres_client

    # In app lifespan:
    await postgres_client.initialize(dsn="postgresql://...")

    # In repository construction:
    repo = CVERepository(postgres_client.pool)
"""
from __future__ import annotations

import os
from typing import Optional

import asyncpg

try:
    from utils.logging_config import get_logger
except ModuleNotFoundError:
    from app.agentic.eol.utils.logging_config import get_logger

logger = get_logger(__name__)


class PostgresClient:
    """Async PostgreSQL connection pool manager.

    Provides a shared asyncpg.Pool that repositories consume via constructor injection.
    Does NOT depend on config.py -- receives DSN externally for testability.
    """

    def __init__(self) -> None:
        self.pool: Optional[asyncpg.Pool] = None

    @property
    def is_initialized(self) -> bool:
        return self.pool is not None

    async def initialize(self, dsn: str = None, **kwargs) -> None:
        """Create the asyncpg connection pool.

        Args:
            dsn: PostgreSQL connection string. Falls back to DATABASE_URL env var,
                 then constructs from PGHOST/PGPORT/PGDATABASE/PGUSER/PGPASSWORD.
        """
        if self.pool is not None:
            logger.warning("PostgresClient already initialized -- skipping")
            return

        if dsn is None:
            dsn = os.environ.get("DATABASE_URL")

        if dsn is None:
            host = os.environ.get("PGHOST", "localhost")
            port = os.environ.get("PGPORT", "5432")
            database = os.environ.get("PGDATABASE", "eol")
            user = os.environ.get("PGUSER", "eol")
            password = os.environ.get("PGPASSWORD", "")
            dsn = f"postgresql://{user}:{password}@{host}:{port}/{database}"

        pool = await asyncpg.create_pool(
            dsn=dsn,
            min_size=kwargs.pop("min_size", 2),
            max_size=kwargs.pop("max_size", 10),
            command_timeout=kwargs.pop("command_timeout", 60),
            **kwargs,
        )

        # Verify connectivity
        await pool.execute("SELECT 1")

        self.pool = pool
        logger.info("asyncpg pool initialized (min=2, max=10)")

    async def close(self) -> None:
        """Gracefully close the connection pool."""
        if self.pool is not None:
            await self.pool.close()
            self.pool = None
            logger.info("asyncpg pool closed")


# Module-level singleton
postgres_client = PostgresClient()
