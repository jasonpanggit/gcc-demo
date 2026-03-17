"""
asyncpg Pool Singleton for the EOL platform.

Provides a shared asyncpg connection pool via a module-level singleton.
All repository classes accept asyncpg.Pool in their constructors and
should obtain it from ``postgres_client.pool``.

Usage::

    from utils.pg_client import postgres_client

    # During application startup:
    await postgres_client.initialize(dsn="postgresql://...")

    # In repository constructors:
    repo = CVERepository(pool=postgres_client.pool)

    # During application shutdown:
    await postgres_client.close()

Phase 8 foundation (P8.1).
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

    Thin wrapper around :func:`asyncpg.create_pool` that exposes a
    module-level singleton (``postgres_client``).  The class does NOT
    import or depend on ``config.py`` — it receives its DSN externally
    so it can be tested independently.
    """

    def __init__(self) -> None:
        self.pool: Optional[asyncpg.Pool] = None

    # ------------------------------------------------------------------ #
    #  Lifecycle
    # ------------------------------------------------------------------ #

    async def initialize(self, dsn: str = None, **kwargs) -> None:
        """Create the asyncpg connection pool.

        Parameters
        ----------
        dsn : str, optional
            A full ``postgresql://`` connection string.  When *None* the
            DSN is resolved from environment variables in this order:

            1. ``DATABASE_URL`` (single env var)
            2. Constructed from ``PGHOST``, ``PGPORT``, ``PGDATABASE``,
               ``PGUSER``, ``PGPASSWORD``

        **kwargs
            Forwarded to :func:`asyncpg.create_pool` (e.g.
            ``min_size``, ``max_size``, ``ssl``).
        """
        if self.pool is not None:
            logger.warning("asyncpg pool already initialized — skipping")
            return

        if dsn is None:
            dsn = os.environ.get("DATABASE_URL")

        if dsn is None:
            # Construct from individual PG* env vars
            host = os.environ.get("PGHOST", "localhost")
            port = os.environ.get("PGPORT", "5432")
            database = os.environ.get("PGDATABASE", "eol")
            user = os.environ.get("PGUSER", "postgres")
            password = os.environ.get("PGPASSWORD", "")
            dsn = f"postgresql://{user}:{password}@{host}:{port}/{database}"

        pool_defaults = {
            "min_size": 2,
            "max_size": 10,
            "command_timeout": 60,
        }
        pool_defaults.update(kwargs)

        pool = await asyncpg.create_pool(dsn=dsn, **pool_defaults)

        # Verify connectivity
        await pool.execute("SELECT 1")

        self.pool = pool
        logger.info(
            "asyncpg pool initialized (min=%s, max=%s)",
            pool_defaults["min_size"],
            pool_defaults["max_size"],
        )

    async def close(self) -> None:
        """Gracefully close the connection pool."""
        if self.pool is not None:
            await self.pool.close()
            logger.info("asyncpg pool closed")
            self.pool = None

    # ------------------------------------------------------------------ #
    #  Introspection
    # ------------------------------------------------------------------ #

    @property
    def is_initialized(self) -> bool:
        """Return ``True`` if the pool has been created."""
        return self.pool is not None


# ====================================================================== #
#  Module-level singleton
# ====================================================================== #
postgres_client = PostgresClient()
