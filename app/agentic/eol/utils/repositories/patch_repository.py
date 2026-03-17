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

from typing import Dict, List, Optional

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

# From: TARGET-SQL-INVENTORY-DOMAIN.md Query 11b + TARGET-SQL-CVE-DOMAIN.md Query 4c
QUERY_PATCHES_FOR_VM = """
SELECT ap.id, ap.resource_id, ap.kb_id, ap.software_name, ap.software_version,
       ap.classifications, ap.assessment_state, ap.assessment_timestamp
FROM available_patches ap
WHERE ap.resource_id = $1
ORDER BY ap.classifications, ap.software_name;
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
    assessment_status, last_assessment,
    critical_count, high_count, medium_count, low_count, other_count,
    total_patches, reboot_pending, cached_at
)
VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, NOW())
ON CONFLICT (resource_id) DO UPDATE SET
    machine_name      = EXCLUDED.machine_name,
    os_name           = EXCLUDED.os_name,
    os_version        = EXCLUDED.os_version,
    vm_type           = EXCLUDED.vm_type,
    assessment_status = EXCLUDED.assessment_status,
    last_assessment   = EXCLUDED.last_assessment,
    critical_count    = EXCLUDED.critical_count,
    high_count        = EXCLUDED.high_count,
    medium_count      = EXCLUDED.medium_count,
    low_count         = EXCLUDED.low_count,
    other_count       = EXCLUDED.other_count,
    total_patches     = EXCLUDED.total_patches,
    reboot_pending    = EXCLUDED.reboot_pending,
    cached_at         = NOW();
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
        """Query 11b / 4c — Available patches for a specific VM.

        Used by both patch-management detail and vm-vulnerability patch
        coverage views.
        """
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(QUERY_PATCHES_FOR_VM, resource_id)
        return [dict(r) for r in rows]

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
            os_version, vm_type, assessment_status, last_assessment,
            critical_count, high_count, medium_count, low_count,
            other_count, total_patches, reboot_pending.
        """
        async with self._pool.acquire() as conn:
            await conn.execute(
                QUERY_UPSERT_ASSESSMENT,
                assessment["resource_id"],
                assessment.get("machine_name"),
                assessment.get("os_name"),
                assessment.get("os_version"),
                assessment.get("vm_type"),
                assessment.get("assessment_status"),
                assessment.get("last_assessment"),
                assessment.get("critical_count", 0),
                assessment.get("high_count", 0),
                assessment.get("medium_count", 0),
                assessment.get("low_count", 0),
                assessment.get("other_count", 0),
                assessment.get("total_patches", 0),
                assessment.get("reboot_pending", False),
            )

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
