"""
PatchRepository — Patch management PostgreSQL data access.

Provides single-query patch management view (BH-010 fix), per-VM patch
detail, install history, and write paths for assessment upsert and
install recording.

SQL sources:
- Query 11a: TARGET-SQL-INVENTORY-DOMAIN.md (BH-010 fix)
- Query 11b + 4c: TARGET-SQL-INVENTORY-DOMAIN.md / TARGET-SQL-CVE-DOMAIN.md
- Patch install history: patch_installs table

Phase 8 plan: P8.4 (PatchRepository + AlertRepository)
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import asyncpg

try:
    from utils.logging_config import get_logger
except ModuleNotFoundError:
    from app.agentic.eol.utils.logging_config import get_logger

logger = get_logger(__name__)


# ====================================================================== #
#  SQL Constants
# ====================================================================== #

# From: TARGET-SQL-INVENTORY-DOMAIN.md Query 11a (BH-010 fix)
# Single JOINed query eliminates the two-query /machines + /arg-patch-data pattern
QUERY_PATCH_MANAGEMENT_VIEW = """
SELECT v.resource_id, v.vm_name, v.os_name, v.os_type, v.location, v.resource_group,
       pac.machine_name, pac.total_patches, pac.critical_count, pac.security_count,
       pac.last_modified, pac.os_version, pac.vm_type AS pac_vm_type,
       (SELECT COUNT(*) FROM available_patches ap WHERE ap.resource_id = v.resource_id) AS available_patch_count
FROM vms v
LEFT JOIN patch_assessments_cache pac ON pac.resource_id = v.resource_id
WHERE ($1::uuid IS NULL OR v.subscription_id = $1)
ORDER BY COALESCE(pac.critical_count, 0) DESC, v.vm_name ASC
LIMIT $2 OFFSET $3;
"""

# Patch install history with optional resource_id filter
QUERY_PATCH_INSTALL_HISTORY = """
SELECT id, resource_id, operation_url, machine_name, status, is_done,
       installed_patch_count, failed_patch_count, pending_patch_count,
       start_date_time, completed_at, created_at, updated_at
FROM patch_installs
WHERE ($1::text IS NULL OR resource_id = $1)
ORDER BY created_at DESC
LIMIT $2 OFFSET $3;
"""

# Upsert a patch assessment cache row
QUERY_UPSERT_ASSESSMENT = """
INSERT INTO patch_assessments_cache (
    resource_id, machine_name, os_name, os_version, vm_type,
    critical_count, security_count, other_count,
    total_patches, last_modified, cached_at
)
VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, NOW())
ON CONFLICT (resource_id) DO UPDATE SET
    machine_name     = EXCLUDED.machine_name,
    os_name          = EXCLUDED.os_name,
    os_version       = EXCLUDED.os_version,
    vm_type          = EXCLUDED.vm_type,
    critical_count   = EXCLUDED.critical_count,
    security_count   = EXCLUDED.security_count,
    other_count      = EXCLUDED.other_count,
    total_patches    = EXCLUDED.total_patches,
    last_modified    = EXCLUDED.last_modified,
    cached_at        = NOW();
"""

# Record a patch install operation
QUERY_INSERT_INSTALL = """
INSERT INTO patch_installs (
    resource_id, operation_url, machine_name, status, is_done,
    installed_patch_count, failed_patch_count, pending_patch_count,
    start_date_time, completed_at
)
VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
RETURNING id, resource_id, operation_url, machine_name, status, is_done,
          installed_patch_count, failed_patch_count, pending_patch_count,
          start_date_time, completed_at, created_at, updated_at;
"""


# ====================================================================== #
#  Repository
# ====================================================================== #

class PatchRepository:
    """PostgreSQL repository for patch management domain.

    Covers:
    - Patch management view (single JOINed query — BH-010 fix)
    - Per-VM available patches
    - Patch install history
    - Assessment cache upsert
    - Install recording
    """

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def _sync_missing_kb_edges(self, kb_numbers: List[str]) -> int:
        """Populate KB-to-CVE edges for the provided KB numbers.

        This uses the canonical KB edge upsert path and guarantees the
        temporary vendor client is closed on both success and failure.
        """
        if not kb_numbers:
            return 0

        vendor_client = None
        try:
            from utils.cve_sync_operations import sync_kb_edges_for_kbs
            from utils.vendor_feed_client import VendorFeedClient
            from utils.config import get_config

            cfg = get_config()
            vendor_client = VendorFeedClient(
                redhat_base_url=cfg.cve_data.redhat_base_url,
                ubuntu_base_url=cfg.cve_data.ubuntu_base_url,
                msrc_base_url=cfg.cve_data.msrc_base_url,
                msrc_api_key=cfg.cve_data.msrc_api_key or None,
                request_timeout=cfg.cve_data.request_timeout,
            )
            return await sync_kb_edges_for_kbs(
                kb_numbers,
                vendor_client,
                pool=self._pool,
                batch_size=10,
            )
        finally:
            if vendor_client is not None:
                await vendor_client.close()

    # ------------------------------------------------------------------ #
    #  Read methods
    # ------------------------------------------------------------------ #

    async def get_patch_management_view(
        self,
        subscription_id: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Dict]:
        """Query 11a — Single-query patch management view (BH-010 fix).

        Returns VMs with LEFT JOINed patch assessment data and a correlated
        subquery for available_patch_count.  Eliminates the two-query
        /machines + /arg-patch-data page load pattern.
        """
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                QUERY_PATCH_MANAGEMENT_VIEW,
                subscription_id,
                limit,
                offset,
            )
        return [dict(r) for r in rows]

    async def get_patches_for_vm(self, resource_id: str) -> List[Dict]:
        """Get available patches for a VM. Delegates to get_available_patches_for_vm."""
        return await self.get_available_patches_for_vm(resource_id)

    async def get_installed_patches_for_vm(self, resource_id: str) -> List[Dict]:
        """Get installed patches for a specific VM from inventory_software_cache.

        Reads cached software inventory, filters for KB patches, maps to CVEs.
        Auto-syncs missing KB-to-CVE edges from MSRC on demand.
        """
        vm_name = resource_id.split("/")[-1] if "/" in resource_id else resource_id

        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT DISTINCT
                    'KB' || substring(item->>'name' FROM 'KB(\\d{6,7})') AS kb_number,
                    item->>'name' AS patch_name
                FROM inventory_software_cache,
                     jsonb_array_elements((data#>>'{}')::jsonb) AS item
                WHERE cache_key = 'software_inventory'
                  AND UPPER(item->>'computer') = UPPER($1)
                  AND item->>'name' ~ 'KB\\d{6,7}'
                ORDER BY kb_number;
                """,
                vm_name,
            )

            if not rows:
                return []

            kb_patches = [row["kb_number"] for row in rows]
            kb_to_name = {row["kb_number"]: row["patch_name"] for row in rows}
            cve_rows = await conn.fetch(
                """
                SELECT
                    kb_number,
                    ARRAY_AGG(DISTINCT cve_id ORDER BY cve_id) AS cve_ids
                FROM kb_cve_edges
                WHERE kb_number = ANY($1::text[])
                GROUP BY kb_number
                ORDER BY kb_number;
                """,
                kb_patches,
            )

        kb_to_cves = {row["kb_number"]: row["cve_ids"] for row in cve_rows}
        missing_kbs = [kb for kb in kb_patches if kb not in kb_to_cves]

        if missing_kbs:
            logger.info(
                "Found %d installed KBs without CVE mappings, syncing from MSRC: %s...",
                len(missing_kbs),
                missing_kbs[:5],
            )
            try:
                synced_count = await self._sync_missing_kb_edges(missing_kbs)
                logger.info(
                    "Auto-synced %d CVE edges for %d missing KBs",
                    synced_count,
                    len(missing_kbs),
                )

                async with self._pool.acquire() as conn:
                    updated_cve_rows = await conn.fetch(
                        """
                        SELECT
                            kb_number,
                            ARRAY_AGG(DISTINCT cve_id ORDER BY cve_id)
                                FILTER (WHERE cve_id IS NOT NULL) AS cve_ids
                        FROM kb_cve_edges
                        WHERE kb_number = ANY($1::text[])
                        GROUP BY kb_number;
                        """,
                        missing_kbs,
                    )

                for row in updated_cve_rows:
                    kb_to_cves[row["kb_number"]] = row["cve_ids"] or []
                for kb in missing_kbs:
                    kb_to_cves.setdefault(kb, [])
            except Exception as e:
                logger.error(f"Failed to auto-sync KB edges: {e}", exc_info=True)

        return [
            {
                "patch_id": kb,
                "kb_ids": [kb],
                "patch_name": kb_to_name.get(kb, kb),
                "classification": "Installed",
                "cve_ids": kb_to_cves.get(kb, []),
            }
            for kb in kb_patches
        ]

    async def get_available_patches_for_vm(self, resource_id: str) -> List[Dict]:
        """Get pending/available patches from patch_assessments_cache (ARG data).

        These are patches that Azure recommends but haven't been installed yet.
        Auto-syncs missing KB→CVE edges from MSRC on demand.
        """
        async with self._pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT
                    ap.kb_number,
                    ap.title AS patch_name,
                    ap.classification,
                    ap.severity,
                    ARRAY_AGG(DISTINCT k.cve_id ORDER BY k.cve_id) FILTER (WHERE k.cve_id IS NOT NULL) AS cve_ids
                FROM available_patches ap
                LEFT JOIN kb_cve_edges k ON k.kb_number = ap.kb_number
                WHERE ap.resource_id = $1
                GROUP BY ap.kb_number, ap.title, ap.classification, ap.severity
                ORDER BY
                    CASE ap.classification
                        WHEN 'Critical' THEN 1
                        WHEN 'Security' THEN 2
                        WHEN 'UpdateRollup' THEN 3
                        ELSE 4
                    END,
                    ap.title;
            """, resource_id)

        # Find KBs without CVE mappings
        kb_to_cves = {row["kb_number"]: row["cve_ids"] for row in rows}
        missing_kbs = [row["kb_number"] for row in rows if not row["cve_ids"]]

        if missing_kbs:
            # Auto-sync missing KBs from MSRC
            logger.info(f"Found {len(missing_kbs)} available patches without CVE mappings, syncing from MSRC: {missing_kbs[:5]}...")
            try:
                synced_count = await self._sync_missing_kb_edges(missing_kbs)
                logger.info(f"Auto-synced {synced_count} CVE edges for {len(missing_kbs)} available patches")

                # Re-fetch CVE mappings after sync
                async with self._pool.acquire() as conn:
                    updated_cve_rows = await conn.fetch("""
                        SELECT
                            kb_number,
                            ARRAY_AGG(DISTINCT cve_id ORDER BY cve_id) AS cve_ids
                        FROM kb_cve_edges
                        WHERE kb_number = ANY($1::text[])
                        GROUP BY kb_number;
                    """, missing_kbs)

                    for row in updated_cve_rows:
                        kb_to_cves[row["kb_number"]] = row["cve_ids"]
                    for kb in missing_kbs:
                        kb_to_cves.setdefault(kb, [])

            except Exception as e:
                logger.error(f"Failed to auto-sync available patch KB edges: {e}", exc_info=True)

        # Format for JavaScript
        result = []
        for row in rows:
            kb = row["kb_number"]
            result.append({
                "patch_id": kb,
                "kb_ids": [kb] if kb else [],
                "patch_name": row["patch_name"],
                "classification": row["classification"],
                "status": row["severity"],
                "cve_ids": kb_to_cves.get(kb) or [],
            })
        return result

    async def list_install_history(
        self,
        resource_id: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Dict]:
        """List patch install operations, optionally filtered by resource_id."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                QUERY_PATCH_INSTALL_HISTORY,
                resource_id,
                limit,
                offset,
            )
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------ #
    #  Write methods
    # ------------------------------------------------------------------ #

    async def upsert_patch_assessment(self, assessment: Dict) -> None:
        """INSERT INTO patch_assessments_cache ON CONFLICT DO UPDATE.

        Parameters
        ----------
        assessment : dict
            Must contain keys: resource_id, machine_name, os_name,
            os_version, vm_type, critical_count, security_count,
            other_count, total_patches, last_modified.
        """
        async with self._pool.acquire() as conn:
            await conn.execute(
                QUERY_UPSERT_ASSESSMENT,
                assessment["resource_id"],          # $1
                assessment.get("machine_name"),      # $2
                assessment.get("os_name"),           # $3
                assessment.get("os_version"),        # $4
                assessment.get("vm_type"),           # $5
                assessment.get("critical_count", 0), # $6
                assessment.get("security_count", 0), # $7
                assessment.get("other_count", 0),    # $8
                assessment.get("total_patches", 0),  # $9
                assessment.get("last_modified"),     # $10
            )

    async def upsert_available_patches(
        self,
        resource_id: str,
        patches: List[Dict[str, Any]],
    ) -> int:
        """Persist ARG patch assessment rows to available_patches table.

        Args:
            resource_id: VM ARM resource ID.
            patches: List of patch dicts with keys: patchName, kbId, classifications,
                     rebootBehavior, assessmentState.

        Returns:
            Count of rows upserted (excludes skipped null-kbId rows).
        """
        import json as _json  # noqa: PLC0415
        valid_rows = []
        for p in patches:
            kb_raw = p.get("kbId") or ""
            if not kb_raw or str(kb_raw).lower() == "null":
                continue
            kb_number = f"KB{kb_raw}" if not str(kb_raw).upper().startswith("KB") else str(kb_raw)

            classifications = p.get("classifications") or []
            if isinstance(classifications, str):
                try:
                    classifications = _json.loads(classifications)
                except Exception:
                    classifications = [classifications]

            classification = classifications[0] if classifications else "Other"
            severity = "Critical" if any(
                c in ("Critical", "Security") for c in classifications
            ) else "Other"
            reboot_required = p.get("rebootBehavior", "") == "AlwaysRequiresReboot"

            valid_rows.append((
                resource_id,
                kb_number,
                p.get("patchName") or "",
                classification,
                severity,
                reboot_required,
            ))

        if not valid_rows:
            return 0

        sql = """
            INSERT INTO available_patches
                (resource_id, kb_number, title, classification, severity, reboot_required, installed, cached_at)
            VALUES ($1, $2, $3, $4, $5, $6, FALSE, NOW())
            ON CONFLICT (resource_id, kb_number) DO UPDATE SET
                title           = EXCLUDED.title,
                classification  = EXCLUDED.classification,
                severity        = EXCLUDED.severity,
                reboot_required = EXCLUDED.reboot_required,
                cached_at       = NOW()
        """
        async with self._pool.acquire() as conn:
            await conn.executemany(sql, valid_rows)
        return len(valid_rows)

    async def record_install(self, install_data: Dict) -> Dict:
        """INSERT INTO patch_installs and return the inserted row as dict.

        Parameters
        ----------
        install_data : dict
            Must contain keys: resource_id, operation_url, machine_name,
            status, is_done, installed_patch_count, failed_patch_count,
            pending_patch_count, start_date_time, completed_at.

        Returns
        -------
        dict
            The newly inserted row including server-generated id, created_at,
            and updated_at.
        """
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                QUERY_INSERT_INSTALL,
                install_data["resource_id"],
                install_data["operation_url"],
                install_data.get("machine_name"),
                install_data.get("status", "InProgress"),
                install_data.get("is_done", False),
                install_data.get("installed_patch_count", 0),
                install_data.get("failed_patch_count", 0),
                install_data.get("pending_patch_count", 0),
                install_data.get("start_date_time"),
                install_data.get("completed_at"),
            )
        return dict(row)
