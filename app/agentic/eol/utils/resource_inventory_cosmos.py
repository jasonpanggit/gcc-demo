"""
Cosmos DB container setup for the Resource Inventory feature.

Creates two containers with custom indexing and autoscale throughput:
  - resource_inventory:          stores discovered Azure resource documents
  - resource_inventory_metadata: stores per-subscription scan metadata

Usage:
    from utils.resource_inventory_cosmos import resource_inventory_setup
    await resource_inventory_setup.initialize()
    inv_container = resource_inventory_setup.get_inventory_container()
    meta_container = resource_inventory_setup.get_metadata_container()
"""

import logging
from typing import Optional, Any, Dict

try:
    from azure.cosmos import PartitionKey
    COSMOS_IMPORTS_OK = True
except Exception:
    COSMOS_IMPORTS_OK = False

from .cosmos_cache import base_cosmos

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Container definitions
# ---------------------------------------------------------------------------

INVENTORY_CONTAINER_ID = "resource_inventory"
METADATA_CONTAINER_ID = "resource_inventory_metadata"
PARTITION_KEY_PATH = "/subscription_id"

# Autoscale: 400–4000 RU/s  (max_throughput controls the ceiling)
AUTOSCALE_MAX_THROUGHPUT = 4000

# Indexing policy for resource_inventory with composite indexes for
# common query patterns (filter by type+location, group+name, etc.)
INVENTORY_INDEXING_POLICY: Dict[str, Any] = {
    "indexingMode": "consistent",
    "automatic": True,
    "includedPaths": [{"path": "/*"}],
    "excludedPaths": [{"path": "/\"_etag\"/?"}],
    "compositeIndexes": [
        [
            {"path": "/resource_type", "order": "ascending"},
            {"path": "/location", "order": "ascending"},
        ],
        [
            {"path": "/resource_group", "order": "ascending"},
            {"path": "/resource_name", "order": "ascending"},
        ],
        [
            {"path": "/subscription_id", "order": "ascending"},
            {"path": "/resource_type", "order": "ascending"},
            {"path": "/location", "order": "ascending"},
        ],
    ],
}

# Metadata container uses the default indexing policy (all paths indexed).
METADATA_INDEXING_POLICY: Dict[str, Any] = {
    "indexingMode": "consistent",
    "automatic": True,
    "includedPaths": [{"path": "/*"}],
    "excludedPaths": [{"path": "/\"_etag\"/?"}],
}


class ResourceInventorySetup:
    """Manages creation and access to the resource-inventory Cosmos DB containers."""

    def __init__(self):
        self._inventory_container: Optional[Any] = None
        self._metadata_container: Optional[Any] = None

    # ------------------------------------------------------------------
    # Initialization
    # ------------------------------------------------------------------

    async def initialize(self) -> bool:
        """Ensure base Cosmos client is ready. Containers are created on first access."""
        if not COSMOS_IMPORTS_OK:
            logger.warning("Cosmos DB SDK not installed – resource inventory disabled")
            return False

        if not base_cosmos.initialized:
            await base_cosmos._initialize_async()

        if not base_cosmos.initialized:
            logger.warning("Cosmos DB not available – resource inventory disabled")
            return False

        logger.info("✅ ResourceInventorySetup ready (containers created on demand)")
        return True

    # ------------------------------------------------------------------
    # Container accessors (lazy creation with custom indexing)
    # ------------------------------------------------------------------

    def _create_container(
        self,
        container_id: str,
        indexing_policy: Dict[str, Any],
    ) -> Any:
        """Create or get a container with autoscale throughput and custom indexing."""
        base_cosmos._ensure_initialized()
        if not base_cosmos.initialized:
            raise RuntimeError("Cosmos base client not initialized")

        # Check the base_cosmos container cache first
        cache_key = f"{container_id}:{PARTITION_KEY_PATH}:autoscale:{AUTOSCALE_MAX_THROUGHPUT}"
        if cache_key in base_cosmos._container_cache:
            logger.debug(f"✅ Using cached container reference for {container_id}")
            return base_cosmos._container_cache[cache_key]

        logger.info(f"🔄 Creating/getting container {container_id} (autoscale {AUTOSCALE_MAX_THROUGHPUT} RU/s)")

        container = base_cosmos.database.create_container_if_not_exists(
            id=container_id,
            partition_key=PartitionKey(path=PARTITION_KEY_PATH, kind="Hash"),
            indexing_policy=indexing_policy,
            offer_throughput=AUTOSCALE_MAX_THROUGHPUT,
        )

        base_cosmos._container_cache[cache_key] = container
        logger.info(f"✅ Container {container_id} ready (cache size: {len(base_cosmos._container_cache)})")
        return container

    def get_inventory_container(self) -> Any:
        """Return the resource_inventory container (lazy-created)."""
        if self._inventory_container is None:
            self._inventory_container = self._create_container(
                INVENTORY_CONTAINER_ID,
                INVENTORY_INDEXING_POLICY,
            )
        return self._inventory_container

    def get_metadata_container(self) -> Any:
        """Return the resource_inventory_metadata container (lazy-created)."""
        if self._metadata_container is None:
            self._metadata_container = self._create_container(
                METADATA_CONTAINER_ID,
                METADATA_INDEXING_POLICY,
            )
        return self._metadata_container

    # ------------------------------------------------------------------
    # Diagnostics
    # ------------------------------------------------------------------

    def get_status(self) -> Dict[str, Any]:
        """Return diagnostic info about the resource-inventory containers."""
        return {
            "cosmos_initialized": base_cosmos.initialized,
            "inventory_container_ready": self._inventory_container is not None,
            "metadata_container_ready": self._metadata_container is not None,
            "inventory_container_id": INVENTORY_CONTAINER_ID,
            "metadata_container_id": METADATA_CONTAINER_ID,
            "autoscale_max_throughput": AUTOSCALE_MAX_THROUGHPUT,
        }


# Shared singleton – import this in other modules
resource_inventory_setup = ResourceInventorySetup()
