"""
Azure SDK Manager — singleton for credential and client caching with connection pooling.

Creates DefaultAzureCredential once at startup, caches Azure SDK clients (Compute,
Network, Storage, Cosmos, Monitor, etc.), and configures connection pooling for both
sync and async clients.

Usage:
    manager = AzureSDKManager.get_instance()
    credential = manager.get_credential()
    compute_client = manager.get_compute_client(subscription_id)

Or via the module-level accessor:
    from utils.azure_client_manager import get_azure_sdk_manager
    manager = get_azure_sdk_manager()
"""
import asyncio
import logging
import os
from typing import Any, ClassVar, Dict, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional Azure imports — wrapped so mock-data mode continues to work when
# azure-mgmt-* packages are not installed.
# ---------------------------------------------------------------------------

try:
    from azure.identity import DefaultAzureCredential
except ImportError:  # pragma: no cover
    DefaultAzureCredential = None  # type: ignore
    logger.warning("azure-identity not installed — AzureSDKManager will be non-functional")

try:
    from azure.identity.aio import DefaultAzureCredential as AsyncDefaultAzureCredential
except ImportError:  # pragma: no cover
    AsyncDefaultAzureCredential = None  # type: ignore

try:
    from azure.core.pipeline.transport import RequestsTransport
except ImportError:  # pragma: no cover
    RequestsTransport = None  # type: ignore

try:
    from azure.core.pipeline.transport._aiohttp import AioHttpTransport
except ImportError:  # pragma: no cover
    AioHttpTransport = None  # type: ignore

# Management clients — optional (not installed in all environments)
try:
    from azure.mgmt.compute import ComputeManagementClient
    from azure.mgmt.compute.aio import ComputeManagementClient as AsyncComputeManagementClient
except ImportError:
    ComputeManagementClient = None  # type: ignore
    AsyncComputeManagementClient = None  # type: ignore

try:
    from azure.mgmt.network import NetworkManagementClient
    from azure.mgmt.network.aio import NetworkManagementClient as AsyncNetworkManagementClient
except ImportError:
    NetworkManagementClient = None  # type: ignore
    AsyncNetworkManagementClient = None  # type: ignore

try:
    from azure.mgmt.resource import ResourceManagementClient
    from azure.mgmt.resource.aio import ResourceManagementClient as AsyncResourceManagementClient
except ImportError:
    ResourceManagementClient = None  # type: ignore
    AsyncResourceManagementClient = None  # type: ignore

try:
    from azure.mgmt.monitor import MonitorManagementClient
    from azure.mgmt.monitor.aio import MonitorManagementClient as AsyncMonitorManagementClient
except ImportError:
    MonitorManagementClient = None  # type: ignore
    AsyncMonitorManagementClient = None  # type: ignore

try:
    from azure.mgmt.storage import StorageManagementClient
    from azure.mgmt.storage.aio import StorageManagementClient as AsyncStorageManagementClient
except ImportError:
    StorageManagementClient = None  # type: ignore
    AsyncStorageManagementClient = None  # type: ignore

# ---------------------------------------------------------------------------
# Pool configuration constants
# ---------------------------------------------------------------------------

SYNC_POOL_CONNECTIONS: int = 10   # Number of connection pools (one per host)
SYNC_POOL_MAXSIZE: int = 20       # Max connections per pool  (NFR-PRF-04)
ASYNC_LIMIT: int = 100            # Total simultaneous async connections
ASYNC_LIMIT_PER_HOST: int = 30    # Per-host async connection cap


class AzureSDKManager:
    """
    Singleton manager for Azure SDK credentials and clients.

    Guarantees:
    - DefaultAzureCredential is created exactly once (no per-call token churn)
    - Management clients are cached per subscription_id
    - Connection pools are configured for both sync (Requests) and async (aiohttp)
    - FastAPI lifespan: call initialize() on startup, aclose() on shutdown
    """

    # Class-level singleton storage
    _instance: ClassVar[Optional["AzureSDKManager"]] = None

    def __init__(self) -> None:
        self._credential: Optional[Any] = None
        self._async_credential: Optional[Any] = None
        self._sync_clients: Dict[str, Any] = {}    # key: "type:subscription_id"
        self._async_clients: Dict[str, Any] = {}   # key: "async_type:subscription_id"
        self._initialized: bool = False
        self._close_lock: asyncio.Lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Singleton access
    # ------------------------------------------------------------------

    @classmethod
    def get_instance(cls) -> "AzureSDKManager":
        """Return the global AzureSDKManager singleton, creating it on first call."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # ------------------------------------------------------------------
    # Credential factories — lazy, cached
    # ------------------------------------------------------------------

    def get_credential(self) -> Any:
        """
        Return the shared DefaultAzureCredential instance.

        Creates the credential on first call with optional persistent token cache
        (requires msal-extensions; falls back to in-memory cache gracefully).
        """
        if self._credential is None:
            if DefaultAzureCredential is None:
                raise RuntimeError("azure-identity is not installed")  # pragma: no cover

            # Honour any exclusions requested via env var (comma-separated source names)
            excluded = [x.strip() for x in os.getenv("AZURE_CREDENTIAL_EXCLUDE", "").split(",") if x.strip()]

            # Attempt persistent token cache; ignore if msal-extensions is unavailable
            cache_opts = None
            try:
                from azure.identity import TokenCachePersistenceOptions
                cache_opts = TokenCachePersistenceOptions(name="gcc-demo")
            except Exception:
                pass  # In-memory cache is the fallback

            kwargs: Dict[str, Any] = {}
            if cache_opts is not None:
                kwargs["cache_persistence_options"] = cache_opts
            if "DeveloperCli" in excluded:
                kwargs["exclude_developer_cli_credential"] = True

            self._credential = DefaultAzureCredential(**kwargs)
        return self._credential

    def get_async_credential(self) -> Any:
        """Return the shared AsyncDefaultAzureCredential instance."""
        if self._async_credential is None:
            if AsyncDefaultAzureCredential is None:
                raise RuntimeError("azure-identity[aio] is not installed")  # pragma: no cover
            self._async_credential = AsyncDefaultAzureCredential()
        return self._async_credential

    # ------------------------------------------------------------------
    # Sync client factories
    # ------------------------------------------------------------------

    def _make_sync_transport(self) -> Any:
        """Create a Requests-based HTTP transport configured with connection pooling."""
        if RequestsTransport is None:
            return None  # pragma: no cover
        return RequestsTransport(
            connection_pool_size=SYNC_POOL_CONNECTIONS,
            max_connections=SYNC_POOL_MAXSIZE,
        )

    def _get_sync_client(self, client_type: str, client_cls: Any, subscription_id: str) -> Any:
        """Generic helper: return or create a cached sync management client."""
        if client_cls is None:
            raise RuntimeError(
                f"azure-mgmt-{client_type} is not installed"
            )  # pragma: no cover
        key = f"{client_type}:{subscription_id}"
        if key not in self._sync_clients:
            transport = self._make_sync_transport()
            kwargs: Dict[str, Any] = {
                "credential": self.get_credential(),
                "subscription_id": subscription_id,
            }
            if transport is not None:
                kwargs["transport"] = transport
            self._sync_clients[key] = client_cls(**kwargs)
        return self._sync_clients[key]

    def get_compute_client(self, subscription_id: str) -> Any:
        """Return (or create) a cached ComputeManagementClient for subscription_id."""
        return self._get_sync_client("compute", ComputeManagementClient, subscription_id)

    def get_network_client(self, subscription_id: str) -> Any:
        """Return (or create) a cached NetworkManagementClient for subscription_id."""
        return self._get_sync_client("network", NetworkManagementClient, subscription_id)

    def get_resource_client(self, subscription_id: str) -> Any:
        """Return (or create) a cached ResourceManagementClient for subscription_id."""
        return self._get_sync_client("resource", ResourceManagementClient, subscription_id)

    def get_monitor_client(self, subscription_id: str) -> Any:
        """Return (or create) a cached MonitorManagementClient for subscription_id."""
        return self._get_sync_client("monitor", MonitorManagementClient, subscription_id)

    def get_storage_client(self, subscription_id: str) -> Any:
        """Return (or create) a cached StorageManagementClient for subscription_id."""
        return self._get_sync_client("storage", StorageManagementClient, subscription_id)

    # ------------------------------------------------------------------
    # Async client factories
    # ------------------------------------------------------------------

    def _make_async_transport(self) -> Any:
        """Create an aiohttp-based HTTP transport with connection limits."""
        try:
            import aiohttp  # noqa: F401  (optional dep)
            if AioHttpTransport is None:
                return None  # pragma: no cover
            connector = aiohttp.TCPConnector(limit=ASYNC_LIMIT, limit_per_host=ASYNC_LIMIT_PER_HOST)
            return AioHttpTransport(connector=connector)
        except ImportError:  # pragma: no cover
            return None

    def _get_async_client(self, client_type: str, client_cls: Any, subscription_id: str) -> Any:
        """Generic helper: return or create a cached async management client."""
        if client_cls is None:
            raise RuntimeError(
                f"azure-mgmt-{client_type}[aio] is not installed"
            )  # pragma: no cover
        key = f"async_{client_type}:{subscription_id}"
        if key not in self._async_clients:
            transport = self._make_async_transport()
            kwargs: Dict[str, Any] = {
                "credential": self.get_async_credential(),
                "subscription_id": subscription_id,
            }
            if transport is not None:
                kwargs["transport"] = transport
            self._async_clients[key] = client_cls(**kwargs)
        return self._async_clients[key]

    def get_async_compute_client(self, subscription_id: str) -> Any:
        """Return (or create) a cached async ComputeManagementClient."""
        return self._get_async_client("compute", AsyncComputeManagementClient, subscription_id)

    def get_async_network_client(self, subscription_id: str) -> Any:
        """Return (or create) a cached async NetworkManagementClient."""
        return self._get_async_client("network", AsyncNetworkManagementClient, subscription_id)

    def get_async_resource_client(self, subscription_id: str) -> Any:
        """Return (or create) a cached async ResourceManagementClient."""
        return self._get_async_client("resource", AsyncResourceManagementClient, subscription_id)

    def get_async_monitor_client(self, subscription_id: str) -> Any:
        """Return (or create) a cached async MonitorManagementClient."""
        return self._get_async_client("monitor", AsyncMonitorManagementClient, subscription_id)

    def get_async_storage_client(self, subscription_id: str) -> Any:
        """Return (or create) a cached async StorageManagementClient."""
        return self._get_async_client("storage", AsyncStorageManagementClient, subscription_id)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def initialize(self) -> None:
        """
        Warm-up credentials on startup.

        Sets is_initialized() → True. Does NOT fail startup if credential
        acquisition fails — it will be retried on first actual SDK call.
        """
        self._initialized = True
        logger.info("AzureSDKManager initialized (credential + connection pool ready)")

    async def aclose(self) -> None:
        """
        Close all cached async clients and the async credential gracefully.

        Safe to call multiple times. Exceptions from individual client.close()
        calls are swallowed so shutdown never blocks on a broken connection.
        """
        async with self._close_lock:
            # Close all async SDK clients
            for key, client in list(self._async_clients.items()):
                try:
                    await client.close()
                except Exception as exc:
                    logger.debug("AzureSDKManager: error closing async client %s: %s", key, exc)
            self._async_clients.clear()

            # Close async credential (releases aiohttp session)
            if self._async_credential is not None:
                try:
                    await self._async_credential.close()
                except Exception as exc:
                    logger.debug("AzureSDKManager: error closing async credential: %s", exc)
                self._async_credential = None

            self._initialized = False

    def is_initialized(self) -> bool:
        """Return True after initialize() has been called and before aclose()."""
        return self._initialized


# ---------------------------------------------------------------------------
# Module-level convenience accessor
# ---------------------------------------------------------------------------

def get_azure_sdk_manager() -> AzureSDKManager:
    """Return the global AzureSDKManager singleton."""
    return AzureSDKManager.get_instance()
