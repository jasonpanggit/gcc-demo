"""
Base Cosmos DB helper and lightweight cache foundation.
This module provides a single, shared base client and helpers that
specialized cache modules (e.g. eol_cache, inventory caches) should use.
"""
import os
import traceback
import logging
import asyncio
import re
from copy import deepcopy
from typing import Optional, Dict, Any

try:
    from azure.cosmos import CosmosClient, PartitionKey
    from azure.identity import DefaultAzureCredential
    COSMOS_IMPORTS_OK = True
except Exception:
    COSMOS_IMPORTS_OK = False

from .config import config

logger = logging.getLogger(__name__)

# Suppress Azure SDK verbose logging
azure_loggers = [
    "azure.core.pipeline.policies.http_logging_policy",
    "azure.identity",
    "azure.core",
    "azure.cosmos",
    "urllib3.connectionpool"
]
for azure_logger_name in azure_loggers:
    azure_logger = logging.getLogger(azure_logger_name)
    azure_logger.setLevel(logging.WARNING)


class BaseCosmosClient:
    """Shared Cosmos client and helpers used by specialized caches.

    Responsibilities:
    - Initialize a single CosmosClient and database reference
    - Provide a helper to create/get containers with caching
    - Expose simple diagnostics
    """

    def __init__(self):
        self.cosmos_client: Optional[CosmosClient] = None
        self.database = None
        self.initialized = False
        self._initialization_attempted = False
        self.last_error: Optional[str] = None
        # Cache container references to avoid repeated Cosmos DB calls
        self._container_cache: Dict[str, Any] = {}

    @staticmethod
    def _is_firewall_forbidden(exc: Exception) -> bool:
        """Return True when Cosmos rejects the request due to network/firewall rules."""
        text = str(exc or "").lower()
        return (
            "forbidden" in text
            and "request originated from ip" in text
            and "firewall" in text
        )

    def _ensure_initialized(self):
        """Synchronous best-effort initialization used for quick validation."""
        if self._initialization_attempted:
            return
        self._initialization_attempted = True

        if not COSMOS_IMPORTS_OK:
            logger.warning("Cosmos DB packages not available - operations disabled")
            self.last_error = "Cosmos DB SDK not installed"
            return

        if not getattr(config.azure, 'cosmos_endpoint', None):
            logger.warning("Cosmos DB endpoint not configured - operations disabled")
            self.last_error = 'Cosmos DB endpoint not configured'
            return

        try:
            use_sp_runtime = os.getenv("USE_SERVICE_PRINCIPAL", "false").lower() == "true"
            has_sp_creds = bool((os.getenv("AZURE_CLIENT_ID") or "").strip()) and bool((os.getenv("AZURE_CLIENT_SECRET") or "").strip())
            credential = DefaultAzureCredential(
                exclude_environment_credential=not (use_sp_runtime and has_sp_creds)
            )
            # Validate token availability (best-effort).
            # Skip when COSMOS_SKIP_CREDENTIAL_VALIDATION=true (e.g. CI / mock mode)
            # to prevent blocking in environments without Azure credentials.
            if os.getenv("COSMOS_SKIP_CREDENTIAL_VALIDATION", "false").lower() != "true":
                credential.get_token('https://cosmos.azure.com/.default')

            self.cosmos_client = CosmosClient(config.azure.cosmos_endpoint, credential=credential)
            self.database = self.cosmos_client.create_database_if_not_exists(id=config.azure.cosmos_database)
            self.initialized = True
            logger.info("✅ Base Cosmos client initialized")
        except Exception as e:
            if self._is_firewall_forbidden(e):
                message = (
                    "Cosmos DB access blocked by firewall/public-network rules; "
                    "continuing with in-memory cache only. "
                    "Allow app outbound IPs or use Cosmos private endpoint/VNet integration."
                )
                logger.warning("⚠️ %s", message)
                self.last_error = f"Cosmos firewall blocked access: {e}"
            else:
                tb = traceback.format_exc()
                logger.error(f"❌ Failed to initialize base Cosmos client: {e}\n{tb}")
                self.last_error = tb
            self.initialized = False

    async def _initialize_async(self):
        """Async initializer used by services that want to eagerly load containers."""
        if self._initialization_attempted:
            return
        self._initialization_attempted = True

        if not COSMOS_IMPORTS_OK:
            logger.warning("Cosmos DB packages not available - operations disabled")
            self.last_error = "Cosmos DB SDK not installed"
            return

        if not getattr(config.azure, 'cosmos_endpoint', None):
            logger.warning("Cosmos DB endpoint not configured - operations disabled")
            self.last_error = 'Cosmos DB endpoint not configured'
            return

        try:
            use_sp_runtime = os.getenv("USE_SERVICE_PRINCIPAL", "false").lower() == "true"
            has_sp_creds = bool((os.getenv("AZURE_CLIENT_ID") or "").strip()) and bool((os.getenv("AZURE_CLIENT_SECRET") or "").strip())
            credential = DefaultAzureCredential(
                exclude_environment_credential=not (use_sp_runtime and has_sp_creds)
            )
            # Skip credential validation when COSMOS_SKIP_CREDENTIAL_VALIDATION=true
            if os.getenv("COSMOS_SKIP_CREDENTIAL_VALIDATION", "false").lower() != "true":
                credential.get_token('https://cosmos.azure.com/.default')

            self.cosmos_client = CosmosClient(url=config.azure.cosmos_endpoint, credential=credential)
            self.database = self.cosmos_client.create_database_if_not_exists(id=config.azure.cosmos_database)
            self.initialized = True
            logger.info("✅ Base Cosmos client initialized (async)")
        except Exception as e:
            if self._is_firewall_forbidden(e):
                message = (
                    "Cosmos DB access blocked by firewall/public-network rules; "
                    "continuing with in-memory cache only. "
                    "Allow app outbound IPs or use Cosmos private endpoint/VNet integration."
                )
                logger.warning("⚠️ %s", message)
                self.last_error = f"Cosmos firewall blocked access: {e}"
            else:
                tb = traceback.format_exc()
                logger.error(f"❌ Failed to initialize base Cosmos client (async): {e}\n{tb}")
                self.last_error = tb
            self.initialized = False

    def get_container(self, container_id: str, partition_path: str = '/cache_key', offer_throughput: int = 400, default_ttl: Optional[int] = None):
        """Create or get a container under the shared database with caching.

        This is synchronous and will try to initialize the base client first.
        Container references are cached to avoid repeated Cosmos DB calls.

        Returns:
            Container reference, or ``None`` when Cosmos DB is unavailable
            (e.g. not configured, missing credentials, or disabled in test mode).
            Callers should guard: ``if container is None: return``.
        """
        self._ensure_initialized()
        if not self.initialized:
            logger.debug("get_container(%s): Cosmos not initialized, returning None", container_id)
            return None

        # Check if container is already cached
        cache_key = f"{container_id}:{partition_path}:{offer_throughput}:{default_ttl or 'no-ttl'}"
        logger.debug(f"🔍 Looking for container cache key: {cache_key}")
        logger.debug(f"🔍 Available cache keys: {list(self._container_cache.keys())}")
        
        if cache_key in self._container_cache:
            logger.debug(f"✅ Using cached container reference for {container_id}")
            return self._container_cache[cache_key]

        # Create container if it doesn't exist - only log warning for new containers
        try:
            logger.info(f"🔄 Creating/getting Cosmos DB container {container_id} (first time)")

            container_kwargs = {
                "id": container_id,
                "partition_key": PartitionKey(path=partition_path, kind='Hash'),
                "offer_throughput": offer_throughput,
            }

            # Respect default TTL when provided so callers can set retention
            if default_ttl is not None:
                container_kwargs["default_ttl"] = default_ttl

            container = self.database.create_container_if_not_exists(**container_kwargs)
            
            # Cache the container reference
            self._container_cache[cache_key] = container
            logger.info(f"✅ Container {container_id} cached for future use (cache size: {len(self._container_cache)})")
            
            return container
        except Exception as e:
            logger.error(f"❌ Error creating/getting container {container_id}: {e}")
            raise

    def get_cache_info(self) -> dict:
        """Get information about the current container cache state"""
        return {
            "initialized": self.initialized,
            "cached_containers": len(self._container_cache),
            "container_cache_keys": list(self._container_cache.keys()),
            "last_error": self.last_error
        }
    
    def clear_container_cache(self):
        """Clear the container cache - useful for debugging or forcing recreation"""
        cache_size = len(self._container_cache)
        self._container_cache.clear()
        logger.info(f"🗑️ Container cache cleared ({cache_size} containers removed)")


# Shared base client instance used by specialized caches
base_cosmos = BaseCosmosClient()


class _LegacyContainerAdapter:
    """Compatibility adapter for older async container access patterns."""

    def __init__(self, container_id: str, partition_path: str):
        self._container_id = container_id
        self._partition_path = partition_path
        self._container = None
        self._items: Dict[str, Dict[str, Any]] = {}

    def _get_container(self):
        if self._container is not None:
            return self._container

        self._container = base_cosmos.get_container(
            container_id=self._container_id,
            partition_path=self._partition_path,
            offer_throughput=400,
        )
        return self._container

    async def create_item(self, body: Dict[str, Any]):
        container = self._get_container()
        if container is not None:
            return container.create_item(body=body)

        item_id = body["id"]
        if item_id in self._items:
            raise ValueError(f"Item {item_id} already exists in {self._container_id}")
        self._items[item_id] = deepcopy(body)
        return deepcopy(body)

    def query_items(self, query: str, parameters=None, enable_cross_partition_query: bool = False):
        del enable_cross_partition_query

        container = self._get_container()
        if container is not None:
            return container.query_items(query=query, parameters=parameters, enable_cross_partition_query=True)

        return self._query_items_in_memory(query, parameters or [])

    async def replace_item(self, item: str, body: Dict[str, Any]):
        container = self._get_container()
        if container is not None:
            return container.replace_item(item=item, body=body)

        if item not in self._items:
            raise KeyError(f"Item {item} not found in {self._container_id}")
        self._items[item] = deepcopy(body)
        return deepcopy(body)

    async def delete_item(self, item: str, partition_key=None):
        del partition_key

        container = self._get_container()
        if container is not None:
            return container.delete_item(item=item, partition_key=partition_key)

        self._items.pop(item, None)
        return None

    def _query_items_in_memory(self, query: str, parameters):
        params = {param["name"]: param["value"] for param in parameters}
        rows = [deepcopy(item) for item in self._items.values()]

        if "c.id = @rule_id" in query:
            rows = [item for item in rows if item.get("id") == params.get("@rule_id")]
        if "c.id = @record_id" in query:
            rows = [item for item in rows if item.get("id") == params.get("@record_id")]
        if "c.name = @name" in query:
            rows = [item for item in rows if item.get("name") == params.get("@name")]
        if "c.alert_type = @alert_type" in query:
            rows = [item for item in rows if item.get("alert_type") == params.get("@alert_type")]
        if "c.acknowledged = @acknowledged" in query:
            rows = [item for item in rows if item.get("acknowledged") == params.get("@acknowledged")]
        if "c.dismissed = @dismissed" in query:
            rows = [item for item in rows if item.get("dismissed") == params.get("@dismissed")]
        if "c.scan_id = @scan_id" in query:
            rows = [item for item in rows if item.get("scan_id") == params.get("@scan_id")]
        if "c.timestamp >= @start_date" in query:
            rows = [item for item in rows if (item.get("timestamp") or "") >= params.get("@start_date", "")]
        if "c.timestamp <= @end_date" in query:
            rows = [item for item in rows if (item.get("timestamp") or "") <= params.get("@end_date", "")]
        if "c.alert_type = 'critical'" in query:
            rows = [item for item in rows if item.get("alert_type") == "critical"]
        if "c.acknowledged = false" in query:
            rows = [item for item in rows if item.get("acknowledged") is False]
        if "c.dismissed = false" in query:
            rows = [item for item in rows if item.get("dismissed") is False]
        if "c.escalated = false" in query:
            rows = [item for item in rows if item.get("escalated") is False]
        if "c.timestamp < @cutoff_time" in query:
            rows = [item for item in rows if (item.get("timestamp") or "") < params.get("@cutoff_time", "")]
        if "c.enabled = true" in query:
            rows = [item for item in rows if item.get("enabled") is True]

        if "ORDER BY c.created_at DESC" in query:
            rows.sort(key=lambda item: item.get("created_at", ""), reverse=True)
        elif "ORDER BY c.timestamp DESC" in query:
            rows.sort(key=lambda item: item.get("timestamp", ""), reverse=True)
        elif "ORDER BY c.timestamp ASC" in query:
            rows.sort(key=lambda item: item.get("timestamp", ""))

        offset = 0
        limit = None
        offset_match = re.search(r"OFFSET\s+(\d+)", query)
        if offset_match:
            offset = int(offset_match.group(1))
        limit_match = re.search(r"LIMIT\s+(\d+)", query)
        if limit_match:
            limit = int(limit_match.group(1))

        if offset:
            rows = rows[offset:]
        if limit is not None:
            rows = rows[:limit]

        return rows


class _LegacyCosmosClientAdapter:
    """Compatibility surface for modules that still expect get_container_client."""

    _PARTITION_PATHS = {
        "cve_alert_rules": "/rule_type",
        "cve_alert_history": "/alert_type",
    }

    def __init__(self):
        self._containers: Dict[str, _LegacyContainerAdapter] = {}

    def get_container_client(self, database: str, container: str):
        del database

        if container not in self._containers:
            partition_path = self._PARTITION_PATHS.get(container, "/id")
            self._containers[container] = _LegacyContainerAdapter(container, partition_path)
        return self._containers[container]


_legacy_cosmos_client = _LegacyCosmosClientAdapter()


def get_cosmos_client() -> _LegacyCosmosClientAdapter:
    """Return the legacy-compatible Cosmos client surface used by CVE managers."""

    return _legacy_cosmos_client
