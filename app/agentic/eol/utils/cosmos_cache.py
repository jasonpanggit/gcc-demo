"""
Base Cosmos DB helper and lightweight cache foundation.
This module provides a single, shared base client and helpers that
specialized cache modules (e.g. eol_cache, inventory caches) should use.
"""
import os
import traceback
import logging
import asyncio
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
            credential = DefaultAzureCredential()
            # validate token availability (best-effort)
            credential.get_token('https://cosmos.azure.com/.default')

            self.cosmos_client = CosmosClient(config.azure.cosmos_endpoint, credential=credential)
            self.database = self.cosmos_client.create_database_if_not_exists(id=config.azure.cosmos_database)
            self.initialized = True
            logger.info("✅ Base Cosmos client initialized")
        except Exception as e:
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
            credential = DefaultAzureCredential()
            credential.get_token('https://cosmos.azure.com/.default')

            self.cosmos_client = CosmosClient(url=config.azure.cosmos_endpoint, credential=credential)
            self.database = self.cosmos_client.create_database_if_not_exists(id=config.azure.cosmos_database)
            self.initialized = True
            logger.info("✅ Base Cosmos client initialized (async)")
        except Exception as e:
            tb = traceback.format_exc()
            logger.error(f"❌ Failed to initialize base Cosmos client (async): {e}\n{tb}")
            self.last_error = tb
            self.initialized = False

    def get_container(self, container_id: str, partition_path: str = '/cache_key', offer_throughput: int = 400, default_ttl: Optional[int] = None):
        """Create or get a container under the shared database with caching.

        This is synchronous and will try to initialize the base client first.
        Container references are cached to avoid repeated Cosmos DB calls.
        """
        self._ensure_initialized()
        if not self.initialized:
            raise RuntimeError('Cosmos base client not initialized')

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
