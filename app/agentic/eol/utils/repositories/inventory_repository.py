"""InventoryRepository -- VM inventory, resource inventory, and software inventory.

Phase 8 (P8.3): Consolidated repository covering queries 9a-9c, 10a-10b from
TARGET-SQL-INVENTORY-DOMAIN.md.

Key improvements:
- BH-005 fix: Bulk LEFT JOIN to eol_records replaces N+1 POST /api/search/eol per OS row
- BH-013/BH-015 inherently fixed: All queries use canonical vms table with resource_id PK
- Upsert methods for sync jobs (vms, resource_inventory)
"""
from __future__ import annotations

from typing import Dict, List, Optional

try:
    import asyncpg
except ImportError:
    asyncpg = None  # type: ignore[assignment]

try:
    from utils.logging_config import get_logger
except ModuleNotFoundError:
    from app.agentic.eol.utils.logging_config import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# SQL Constants -- copied verbatim from Phase 6 TARGET-SQL-INVENTORY-DOMAIN.md
# ---------------------------------------------------------------------------

# From: TARGET-SQL-INVENTORY-DOMAIN.md Query 9a (BH-005 fix)
QUERY_VM_INVENTORY_WITH_EOL = """
WITH vm_data AS (
    SELECT v.resource_id, v.vm_name, v.os_name, v.os_type, v.vm_type,
           v.location, v.resource_group, v.subscription_id
    FROM vms v
    WHERE ($1::uuid IS NULL OR v.subscription_id = $1)
      AND ($2::text IS NULL OR v.os_name ILIKE '%' || $2 || '%')
),
-- For each VM pick the single eol_record with the best (longest) software_key prefix match
-- and among ties take the soonest eol_date so the most urgent risk is surfaced.
-- Example: "Windows Server 2016 Datacenter" matches both "windows server" (14 chars)
-- and "windows server 2016" (19 chars) — we keep the longer, more specific match.
eol_matched AS (
    SELECT DISTINCT ON (d.resource_id)
           d.resource_id,
           e.is_eol, e.eol_date, e.software_name AS eol_software_name,
           e.version_key AS os_version
    FROM vm_data d
    JOIN eol_records e
      ON LOWER(d.os_name) LIKE LOWER(e.software_key) || '%'
     AND item_type = 'os'
    ORDER BY d.resource_id,
             LENGTH(e.software_key) DESC,   -- longest (most specific) key wins
             e.eol_date ASC NULLS LAST       -- then soonest EOL date
)
SELECT d.resource_id, d.vm_name, d.os_name, d.os_type, d.vm_type,
       d.location, d.resource_group, d.subscription_id,
       m.is_eol, m.eol_date, m.eol_software_name, m.os_version
FROM vm_data d
LEFT JOIN eol_matched m ON d.resource_id = m.resource_id
ORDER BY d.vm_name ASC
LIMIT $3 OFFSET $4;
"""

# From: TARGET-SQL-INVENTORY-DOMAIN.md Query 9b
QUERY_VM_INVENTORY_COUNT = """
SELECT COUNT(*) AS total
FROM vms v
WHERE ($1::uuid IS NULL OR v.subscription_id = $1)
  AND ($2::text IS NULL OR v.os_name ILIKE '%' || $2 || '%');
"""

# PK lookup on vms table (used by cve_inventory.py)
QUERY_VM_BY_ID = """
SELECT resource_id, subscription_id, resource_group, vm_name,
       os_name, os_type, vm_type, location, tags,
       created_at, updated_at, last_synced_at
FROM vms
WHERE LOWER(resource_id) = LOWER($1);
"""

# From: TARGET-SQL-INVENTORY-DOMAIN.md Query 9c
QUERY_SOFTWARE_FOR_VM = """
SELECT software_name, software_type, software_version, publisher, cached_at
FROM arc_software_inventory
WHERE resource_id = $1
ORDER BY software_name;
"""

# From: TARGET-SQL-INVENTORY-DOMAIN.md Query 10a
QUERY_RESOURCE_LIST = """
SELECT id as resource_id, name, resource_type, subscription_id, resource_group,
       location, normalized_os_name as os_name, properties->>'os_type' as os_type,
       CASE
         WHEN tags IS NULL THEN '{}'::jsonb
         WHEN jsonb_typeof(tags) = 'string' THEN (tags #>> '{}')::jsonb
         ELSE tags
       END as tags,
       discovered_at as last_synced_at,
       eol_status, eol_date, risk_level as eol_confidence
FROM resource_inventory
WHERE ($1::text IS NULL OR subscription_id = $1::text)
  AND ($2::text IS NULL OR LOWER(resource_type) = LOWER($2::text))
  AND ($3::text IS NULL OR name ILIKE '%' || $3::text || '%')
ORDER BY name ASC
LIMIT $4 OFFSET $5;
"""

# From: TARGET-SQL-INVENTORY-DOMAIN.md Query 10b
QUERY_CACHE_STATUS = """
SELECT subscription_id, resource_type, last_fetched_at as cached_at, expires_at, row_count
FROM resource_inventory_cache_state
WHERE expires_at > NOW()
ORDER BY last_fetched_at DESC;
"""

# Query 10c -- Count resources with same filters as list query
QUERY_RESOURCE_COUNT = """
SELECT COUNT(*) AS total
FROM resource_inventory
WHERE ($1::text IS NULL OR subscription_id = $1::text)
  AND ($2::text IS NULL OR LOWER(resource_type) = LOWER($2::text))
  AND ($3::text IS NULL OR name ILIKE '%' || $3::text || '%');
"""

# ---------------------------------------------------------------------------
# Write SQL -- upsert patterns for sync jobs
# ---------------------------------------------------------------------------

UPSERT_VM = """
INSERT INTO vms (resource_id, subscription_id, resource_group, vm_name,
                 os_name, os_type, vm_type, location, tags)
VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
ON CONFLICT (resource_id) DO UPDATE SET
    subscription_id = EXCLUDED.subscription_id,
    resource_group  = EXCLUDED.resource_group,
    vm_name         = EXCLUDED.vm_name,
    os_name         = EXCLUDED.os_name,
    os_type         = EXCLUDED.os_type,
    vm_type         = EXCLUDED.vm_type,
    location        = EXCLUDED.location,
    tags            = EXCLUDED.tags,
    updated_at      = NOW(),
    last_synced_at  = NOW();
"""

UPSERT_RESOURCE = """
INSERT INTO resource_inventory (id, name, type, location, resource_group,
                                subscription_id, properties, tags)
VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
ON CONFLICT (id) DO UPDATE SET
    name            = EXCLUDED.name,
    type            = EXCLUDED.type,
    location        = EXCLUDED.location,
    resource_group  = EXCLUDED.resource_group,
    subscription_id = EXCLUDED.subscription_id,
    properties      = EXCLUDED.properties,
    tags            = EXCLUDED.tags,
    synced_at       = NOW();
"""

# ---------------------------------------------------------------------------
# SQL Constants -- Cache freshness (Phase 8 P8.6, TARGET-SQL-ADMIN-DOMAIN.md)
# ---------------------------------------------------------------------------

# From: TARGET-SQL-ADMIN-DOMAIN.md ARG freshness
QUERY_ARG_FRESHNESS = """
SELECT COUNT(*) AS row_count,
       MAX(cached_at) AS latest_cached_at,
       MIN(cached_at) AS oldest_cached_at
FROM patch_assessments_cache;
"""

# From: TARGET-SQL-ADMIN-DOMAIN.md LAW freshness
QUERY_LAW_FRESHNESS = """
SELECT COUNT(*) AS row_count,
       MAX(cached_at) AS latest_cached_at,
       MIN(cached_at) AS oldest_cached_at
FROM os_inventory_snapshots;
"""

# From: TARGET-SQL-ADMIN-DOMAIN.md TTL config
QUERY_TTL_CONFIG = """
SELECT source_name, ttl_tier, ttl_seconds, updated_at
FROM cache_ttl_config
ORDER BY source_name;
"""


class InventoryRepository:
    """PostgreSQL repository for VM inventory, resource inventory, and software inventory.

    Accepts an asyncpg.Pool in constructor. All read methods return List[Dict]
    or int. Write methods re-raise on error.
    """

    def __init__(self, pool: "asyncpg.Pool"):
        self.pool = pool

    # ------------------------------------------------------------------
    # Read methods
    # ------------------------------------------------------------------

    async def get_vm_inventory_with_eol(
        self,
        subscription_id: Optional[str] = None,
        os_search: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Dict]:
        """Query 9a -- VM inventory with bulk EOL lookup (BH-005 fix).

        Single CTE + LEFT JOIN replaces N+1 POST /api/search/eol per OS row.
        """
        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(
                    QUERY_VM_INVENTORY_WITH_EOL,
                    subscription_id,
                    os_search,
                    limit,
                    offset,
                )
                return [dict(r) for r in rows]
        except asyncpg.PostgresError as exc:
            logger.error("get_vm_inventory_with_eol failed: %s", exc)
            return []

    async def get_vm_by_id(self, resource_id: str) -> Optional[Dict]:
        """Single VM by resource_id PK lookup. Used by cve_inventory.py."""
        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(QUERY_VM_BY_ID, resource_id)
                return dict(row) if row else None
        except asyncpg.PostgresError as exc:
            logger.error("get_vm_by_id failed for %s: %s", resource_id, exc)
            return None

    async def count_vm_inventory(
        self,
        subscription_id: Optional[str] = None,
        os_search: Optional[str] = None,
    ) -> int:
        """Query 9b -- VM inventory count for pagination."""
        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(
                    QUERY_VM_INVENTORY_COUNT,
                    subscription_id,
                    os_search,
                )
                return row["total"] if row else 0
        except asyncpg.PostgresError as exc:
            logger.error("count_vm_inventory failed: %s", exc)
            return 0

    async def get_software_for_vm(self, resource_id: str) -> List[Dict]:
        """Query 9c -- Software inventory for a single VM."""
        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(QUERY_SOFTWARE_FOR_VM, resource_id)
                return [dict(r) for r in rows]
        except asyncpg.PostgresError as exc:
            logger.error("get_software_for_vm failed: %s", exc)
            return []

    async def list_resources(
        self,
        subscription_id: Optional[str] = None,
        resource_type: Optional[str] = None,
        name_search: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Dict]:
        """Query 10a -- Resource inventory list with filters."""
        import json
        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(
                    QUERY_RESOURCE_LIST,
                    subscription_id,
                    resource_type,
                    name_search,
                    limit,
                    offset,
                )
                # Parse JSON fields that might be strings
                results = []
                for r in rows:
                    row_dict = dict(r)
                    # Ensure tags is a dict, not a string
                    tags_value = row_dict.get('tags')

                    if tags_value:
                        # Keep parsing until we get a dict (handles multiple layers of JSON encoding)
                        max_iterations = 5
                        iteration = 0
                        while isinstance(tags_value, str) and iteration < max_iterations:
                            try:
                                tags_value = json.loads(tags_value)
                                iteration += 1
                            except (json.JSONDecodeError, TypeError) as e:
                                logger.warning(f"Failed to parse tags for {row_dict.get('name')} at iteration {iteration}: {e}")
                                tags_value = {}
                                break

                        # Ensure final result is a dict
                        if isinstance(tags_value, dict):
                            row_dict['tags'] = tags_value
                        else:
                            logger.warning(f"Tags for {row_dict.get('name')} is still {type(tags_value)} after parsing")
                            row_dict['tags'] = {}
                    else:
                        # Null or missing tags
                        row_dict['tags'] = {}
                    results.append(row_dict)
                return results
        except asyncpg.PostgresError as exc:
            logger.error("list_resources failed: %s", exc)
            return []

    async def count_resources(
        self,
        subscription_id: Optional[str] = None,
        resource_type: Optional[str] = None,
        name_search: Optional[str] = None,
    ) -> int:
        """Query 10c -- Count resources with same filters as list_resources."""
        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(
                    QUERY_RESOURCE_COUNT,
                    subscription_id,
                    resource_type,
                    name_search,
                )
                return row["total"] if row else 0
        except asyncpg.PostgresError as exc:
            logger.error("count_resources failed: %s", exc)
            return 0

    async def get_cache_status(self) -> List[Dict]:
        """Query 10b -- Resource inventory cache freshness status."""
        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(QUERY_CACHE_STATUS)
                return [dict(r) for r in rows]
        except asyncpg.PostgresError as exc:
            logger.error("get_cache_status failed: %s", exc)
            return []

    # ------------------------------------------------------------------
    # Write methods (for sync jobs) -- re-raise on error
    # ------------------------------------------------------------------

    async def upsert_vm(self, vm_data: Dict) -> None:
        """INSERT INTO vms ... ON CONFLICT (resource_id) DO UPDATE.

        Uses the safe upsert pattern (never DELETE + INSERT) to preserve
        CASCADE FK integrity with 6 child tables.
        """
        try:
            async with self.pool.acquire() as conn:
                await conn.execute(
                    UPSERT_VM,
                    vm_data["resource_id"],
                    vm_data["subscription_id"],
                    vm_data["resource_group"],
                    vm_data["vm_name"],
                    vm_data.get("os_name"),
                    vm_data.get("os_type"),
                    vm_data.get("vm_type"),
                    vm_data.get("location"),
                    vm_data.get("tags", {}),
                )
        except asyncpg.PostgresError as exc:
            logger.error(
                "upsert_vm failed for %s: %s", vm_data.get("resource_id"), exc
            )
            raise

    async def upsert_resource(self, resource_data: Dict) -> None:
        """INSERT INTO resource_inventory ... ON CONFLICT (id) DO UPDATE.

        Upserts a single resource record from ARG discovery.
        """
        try:
            async with self.pool.acquire() as conn:
                await conn.execute(
                    UPSERT_RESOURCE,
                    resource_data["id"],
                    resource_data.get("name"),
                    resource_data.get("type"),
                    resource_data.get("location"),
                    resource_data.get("resource_group"),
                    resource_data.get("subscription_id"),
                    resource_data.get("properties", {}),
                    resource_data.get("tags", {}),
                )
        except asyncpg.PostgresError as exc:
            logger.error(
                "upsert_resource failed for %s: %s",
                resource_data.get("id"),
                exc,
            )
            raise

    # ------------------------------------------------------------------
    # Cache freshness (Phase 8 P8.6, TARGET-SQL-ADMIN-DOMAIN.md)
    # ------------------------------------------------------------------

    async def get_arg_freshness(self) -> Dict:
        """ARG cache freshness aggregate for /api/cache/status."""
        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(QUERY_ARG_FRESHNESS)
                return dict(row) if row else {"row_count": 0}
        except asyncpg.PostgresError as exc:
            logger.error("get_arg_freshness failed: %s", exc)
            return {"row_count": 0}

    async def get_law_freshness(self) -> Dict:
        """LAW cache freshness aggregate for /api/cache/status."""
        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(QUERY_LAW_FRESHNESS)
                return dict(row) if row else {"row_count": 0}
        except asyncpg.PostgresError as exc:
            logger.error("get_law_freshness failed: %s", exc)
            return {"row_count": 0}

    async def get_ttl_config(self) -> List[Dict]:
        """TTL configuration for all cache sources."""
        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(QUERY_TTL_CONFIG)
                return [dict(r) for r in rows]
        except asyncpg.PostgresError as exc:
            logger.error("get_ttl_config failed: %s", exc)
            return []

    async def sync_vms_os_data_from_snapshots(self) -> Dict[str, Any]:
        """Update vms table OS data from two sources:

        1. os_inventory_snapshots (Arc VMs — has full version string in os_name)
        2. resource_inventory (Azure VMs — has normalized_os_name + normalized_os_version)

        For Azure VMs we build a normalised display name like "windows server 2019"
        by concatenating normalized_os_name and normalized_os_version from
        resource_inventory. This fixes the generic "windows server" problem.

        Returns:
            Dict with sync statistics (snapshot_updated, ri_updated, errors)
        """
        try:
            async with self.pool.acquire() as conn:
                # Pass 1 — Arc VMs: sync from os_inventory_snapshots (unchanged logic)
                r1 = await conn.execute("""
                    UPDATE vms
                    SET
                        os_name = COALESCE(osi.os_name, vms.os_name),
                        os_type = COALESCE(osi.os_type, vms.os_type)
                    FROM os_inventory_snapshots osi
                    WHERE vms.resource_id = osi.resource_id
                      AND (vms.os_name IS NULL OR vms.os_name = 'Unknown'
                           OR vms.os_type IS NULL OR vms.os_type = 'Unknown')
                """)
                snapshot_updated = int(r1.split()[-1]) if r1 and r1.split() else 0

                # Pass 2 — Azure VMs: sync from resource_inventory using
                # normalized_os_name + normalized_os_version.
                # Always overwrite generic os_name values that lack a version year
                # (i.e. plain "windows server" / "linux" without a year suffix).
                # The CONCAT produces e.g. "windows server 2019".
                r2 = await conn.execute("""
                    UPDATE vms
                    SET
                        os_name = TRIM(
                            ri.normalized_os_name
                            || CASE
                                   WHEN ri.normalized_os_version IS NOT NULL
                                        AND ri.normalized_os_version <> ''
                                   THEN ' ' || ri.normalized_os_version
                                   ELSE ''
                               END
                        ),
                        updated_at     = NOW(),
                        last_synced_at = NOW()
                    FROM resource_inventory ri
                    WHERE LOWER(vms.resource_id) = LOWER(ri.id)
                      AND ri.normalized_os_name IS NOT NULL
                      AND ri.normalized_os_name <> ''
                      AND ri.normalized_os_version IS NOT NULL
                      AND ri.normalized_os_version <> ''
                      AND (
                          -- overwrite only when the stored value is generic (no year)
                          vms.os_name IS NULL
                          OR vms.os_name = 'Unknown'
                          OR NOT (vms.os_name ~* '\\d{4}')
                      )
                """)
                ri_updated = int(r2.split()[-1]) if r2 and r2.split() else 0

                logger.info(
                    "Synced OS data to vms table: %d from snapshots, %d from resource_inventory",
                    snapshot_updated, ri_updated,
                )

                return {
                    "snapshot_updated": snapshot_updated,
                    "ri_updated": ri_updated,
                    "updated_count": snapshot_updated + ri_updated,
                    "status": "success",
                }
        except asyncpg.PostgresError as exc:
            logger.error("sync_vms_os_data_from_snapshots failed: %s", exc)
            return {
                "updated_count": 0,
                "status": "error",
                "error": str(exc),
            }
