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

import json
import os
import ssl
from pathlib import Path
from typing import Any, Optional

import asyncpg

try:
    from azure.identity.aio import ManagedIdentityCredential as AsyncManagedIdentityCredential
except ModuleNotFoundError:
    AsyncManagedIdentityCredential = None  # type: ignore[assignment]

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
        self._appsettings_cache: Optional[dict[str, Any]] = None
        self._managed_identity_credential: Any = None

    @property
    def is_initialized(self) -> bool:
        return self.pool is not None

    def _load_appsettings(self) -> dict[str, Any]:
        if self._appsettings_cache is not None:
            return self._appsettings_cache

        settings_path = os.environ.get("APPSETTINGS_PATH")
        if not settings_path:
            settings_path = str(Path(__file__).resolve().parents[1] / "deploy" / "appsettings.json")

        try:
            with open(settings_path, "r", encoding="utf-8") as handle:
                self._appsettings_cache = json.load(handle)
        except Exception:
            self._appsettings_cache = {}

        return self._appsettings_cache

    def _get_appsettings_postgres(self) -> dict[str, Any]:
        appsettings = self._load_appsettings()
        azure_services = appsettings.get("AzureServices")
        if not isinstance(azure_services, dict):
            return {}
        postgres = azure_services.get("PostgreSQL")
        if not isinstance(postgres, dict):
            return {}
        return postgres

    @staticmethod
    def _normalize_setting(value: Any) -> Optional[str]:
        if value is None:
            return None
        text = str(value).strip()
        if not text or text.lower() in {"not_set", "null", "none", "empty"}:
            return None
        return text

    @staticmethod
    def _parse_bool(value: Any, default: bool = False) -> bool:
        if value is None:
            return default
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in {"1", "true", "yes", "on"}

    @staticmethod
    def _build_ssl_context(ssl_mode: Optional[str]) -> Optional[ssl.SSLContext]:
        mode = (ssl_mode or "").strip().lower()
        if not mode or mode == "disable":
            return None

        context = ssl.create_default_context()
        if mode in {"allow", "prefer"}:
            context.check_hostname = False
        return context

    async def _connect_with_managed_identity(self, *args: Any, **kwargs: Any) -> asyncpg.Connection:
        if self._managed_identity_credential is None:
            raise RuntimeError("Managed identity credential is not initialized")

        token = await self._managed_identity_credential.get_token(
            "https://ossrdbms-aad.database.windows.net/.default"
        )
        kwargs["password"] = token.token
        return await asyncpg.connect(*args, **kwargs)

    async def _resolve_connect_kwargs(self, dsn: Optional[str], kwargs: dict[str, Any]) -> dict[str, Any]:
        connect_kwargs = dict(kwargs)
        app_pg = self._get_appsettings_postgres()

        min_size = int(
            self._normalize_setting(os.environ.get("PG_MIN_POOL_SIZE"))
            or self._normalize_setting(app_pg.get("MinPoolSize"))
            or 2
        )
        max_size = int(
            self._normalize_setting(os.environ.get("PG_MAX_POOL_SIZE"))
            or self._normalize_setting(app_pg.get("MaxPoolSize"))
            or 10
        )
        command_timeout = int(self._normalize_setting(os.environ.get("PG_COMMAND_TIMEOUT")) or 60)

        use_managed_identity = self._parse_bool(
            os.environ.get("POSTGRES_USE_MANAGED_IDENTITY"),
            default=self._parse_bool(app_pg.get("UseManagedIdentity"), default=False),
        )

        if dsn is None and not use_managed_identity:
            dsn = os.environ.get("DATABASE_URL")

        if dsn and use_managed_identity:
            raise RuntimeError("DATABASE_URL/DSN auth cannot be combined with PostgreSQL managed identity mode")

        if dsn:
            connect_kwargs["dsn"] = dsn
            connect_kwargs.setdefault("min_size", min_size)
            connect_kwargs.setdefault("max_size", max_size)
            connect_kwargs.setdefault("command_timeout", command_timeout)
            return connect_kwargs

        host = self._normalize_setting(os.environ.get("PGHOST")) or self._normalize_setting(app_pg.get("Host")) or "localhost"
        port = int(self._normalize_setting(os.environ.get("PGPORT")) or self._normalize_setting(app_pg.get("Port")) or 5432)
        database = self._normalize_setting(os.environ.get("PGDATABASE")) or self._normalize_setting(app_pg.get("Database")) or "eol"
        user = self._normalize_setting(os.environ.get("PGUSER")) or self._normalize_setting(app_pg.get("Username")) or "eol"
        password = self._normalize_setting(os.environ.get("PGPASSWORD"))
        ssl_mode = self._normalize_setting(os.environ.get("PGSSLMODE")) or self._normalize_setting(app_pg.get("SslMode"))
        if use_managed_identity:
            if AsyncManagedIdentityCredential is None:
                raise RuntimeError("azure-identity[aio] is required for PostgreSQL managed identity authentication")

            credential_kwargs: dict[str, Any] = {}
            managed_identity_client_id = self._normalize_setting(os.environ.get("MANAGED_IDENTITY_CLIENT_ID"))
            if managed_identity_client_id:
                credential_kwargs["client_id"] = managed_identity_client_id

            if self._managed_identity_credential is None:
                self._managed_identity_credential = AsyncManagedIdentityCredential(**credential_kwargs)

        connect_kwargs.update(
            {
                "host": host,
                "port": port,
                "database": database,
                "user": user,
                "min_size": min_size,
                "max_size": max_size,
                "command_timeout": command_timeout,
            }
        )

        if use_managed_identity:
            connect_kwargs["connect"] = self._connect_with_managed_identity
        else:
            connect_kwargs["password"] = password or ""

        ssl_context = self._build_ssl_context(ssl_mode)
        if ssl_context is not None:
            connect_kwargs["ssl"] = ssl_context

        return connect_kwargs

    async def initialize(self, dsn: str = None, **kwargs) -> None:
        """Create the asyncpg connection pool.

        Args:
            dsn: PostgreSQL connection string. Falls back to DATABASE_URL env var,
                 then constructs from PGHOST/PGPORT/PGDATABASE/PGUSER/PGPASSWORD.
        """
        if self.pool is not None:
            logger.warning("PostgresClient already initialized -- skipping")
            return

        connect_kwargs = await self._resolve_connect_kwargs(dsn=dsn, kwargs=kwargs)

        # Add init callback to register JSONB codec
        async def init_connection(conn):
            await conn.set_type_codec(
                'jsonb',
                encoder=json.dumps,
                decoder=json.loads,
                schema='pg_catalog'
            )

        connect_kwargs['init'] = init_connection

        pool = None
        try:
            pool = await asyncpg.create_pool(**connect_kwargs)

            # Verify connectivity
            await pool.execute("SELECT 1")
        except Exception:
            if pool is not None:
                await pool.close()
            if self._managed_identity_credential is not None:
                await self._managed_identity_credential.close()
                self._managed_identity_credential = None
            raise

        self.pool = pool
        logger.info("asyncpg pool initialized for PostgreSQL repositories")

    async def close(self) -> None:
        """Gracefully close the connection pool."""
        if self.pool is not None:
            await self.pool.close()
            self.pool = None
            logger.info("asyncpg pool closed")
        if self._managed_identity_credential is not None:
            await self._managed_identity_credential.close()
            self._managed_identity_credential = None


# Module-level singleton
postgres_client = PostgresClient()
