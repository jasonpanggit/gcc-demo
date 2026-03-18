"""VMCVEMatchRepository - per-VM CVE match document storage (PostgreSQL).

Stores and retrieves CVE match documents for individual VMs in PostgreSQL.
Table: vm_cve_matches
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import asyncpg

try:
    from models.cve_models import CVEMatch
    from utils.logging_config import get_logger
except ModuleNotFoundError:
    from app.agentic.eol.models.cve_models import CVEMatch
    from app.agentic.eol.utils.logging_config import get_logger

logger = get_logger(__name__)


class VMCVEMatchRepositoryPG:
    """Repository for per-VM CVE match document storage in PostgreSQL.

    Stores VM-specific CVE matches in the vm_cve_matches table.
    """

    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    async def initialize(self):
        """Initialize repository (PostgreSQL tables created by schema bootstrap)."""
        logger.info("VMCVEMatchRepository initialized with PostgreSQL")

    async def save_vm_matches(
        self,
        scan_id: str,
        vm_id: str,
        vm_name: str,
        matches: List[CVEMatch],
        installed_kb_ids: Optional[List[str]] = None,
        available_kb_ids: Optional[List[str]] = None,
        installed_cve_ids: Optional[List[str]] = None,
        available_cve_ids: Optional[List[str]] = None,
        patch_summary: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Save all CVE matches for a VM.

        Args:
            scan_id: Parent scan ID
            vm_id: Full Azure resource ID of the VM
            vm_name: VM display name
            matches: CVEMatch objects to persist
            installed_kb_ids: KB IDs already installed on this VM
            available_kb_ids: KB IDs available (not yet installed) for this VM
            installed_cve_ids: CVE IDs covered by installed KBs
            available_cve_ids: CVE IDs that would be covered by available KBs
            patch_summary: Aggregated patch coverage statistics
        """
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO vm_cve_matches (
                    scan_id, vm_id, vm_name, total_matches, matches,
                    installed_kb_ids, available_kb_ids,
                    installed_cve_ids, available_cve_ids,
                    patch_summary, created_at
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                ON CONFLICT (scan_id, vm_id) DO UPDATE SET
                    vm_name = EXCLUDED.vm_name,
                    total_matches = EXCLUDED.total_matches,
                    matches = EXCLUDED.matches,
                    installed_kb_ids = EXCLUDED.installed_kb_ids,
                    available_kb_ids = EXCLUDED.available_kb_ids,
                    installed_cve_ids = EXCLUDED.installed_cve_ids,
                    available_cve_ids = EXCLUDED.available_cve_ids,
                    patch_summary = EXCLUDED.patch_summary,
                    created_at = EXCLUDED.created_at
                """,
                scan_id,
                vm_id,
                vm_name,
                len(matches),
                json.dumps([m.dict() for m in matches]),
                json.dumps(installed_kb_ids or []),
                json.dumps(available_kb_ids or []),
                json.dumps(installed_cve_ids or []),
                json.dumps(available_cve_ids or []),
                json.dumps(patch_summary or {}),
                datetime.now(timezone.utc),
            )

        logger.info(f"Saved {len(matches)} CVE matches for VM {vm_name} (scan {scan_id})")

    async def get_vm_matches(
        self,
        scan_id: str,
        vm_id: str,
        offset: int = 0,
        limit: int = 100,
    ) -> Optional[Dict[str, Any]]:
        """Fetch paginated CVE matches for a VM.

        Args:
            scan_id: Parent scan ID
            vm_id: VM resource ID (full path or bare name)
            offset: Starting index for pagination
            limit: Maximum number of matches to return

        Returns:
            Dict with vm_id, vm_name, total_matches, matches, has_more
            or None if not found
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT vm_id, vm_name, total_matches, matches,
                       installed_kb_ids, available_kb_ids,
                       installed_cve_ids, available_cve_ids,
                       patch_summary, created_at
                FROM vm_cve_matches
                WHERE scan_id = $1 AND vm_id = $2
                """,
                scan_id,
                vm_id,
            )

            if not row:
                logger.debug(f"VM match not found for scan {scan_id}, VM {vm_id}")
                return None

            all_matches = json.loads(row["matches"]) if row["matches"] else []
            actual_total = len(all_matches)
            page = all_matches[offset : offset + limit]

            return {
                "vm_id": row["vm_id"],
                "vm_name": row["vm_name"],
                "total_matches": actual_total,
                "matches": page,
                "has_more": (offset + limit) < actual_total,
                "installed_kb_ids": json.loads(row["installed_kb_ids"]) if row["installed_kb_ids"] else [],
                "available_kb_ids": json.loads(row["available_kb_ids"]) if row["available_kb_ids"] else [],
                "installed_cve_ids": json.loads(row["installed_cve_ids"]) if row["installed_cve_ids"] else [],
                "available_cve_ids": json.loads(row["available_cve_ids"]) if row["available_cve_ids"] else [],
                "patch_summary": json.loads(row["patch_summary"]) if row["patch_summary"] else {},
            }

    async def delete_vm_matches(self, scan_id: str, vm_id: str) -> None:
        """Delete the VM match document for a specific VM."""
        async with self.pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM vm_cve_matches WHERE scan_id = $1 AND vm_id = $2",
                scan_id,
                vm_id,
            )
        logger.info(f"Deleted VM match for scan {scan_id}, VM {vm_id}")

    async def delete_all_for_scan(self, scan_id: str) -> int:
        """Delete all VM match documents for a scan.

        Returns:
            Number of documents deleted
        """
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM vm_cve_matches WHERE scan_id = $1",
                scan_id,
            )
            # Parse "DELETE N" to get count
            count = int(result.split()[-1]) if result and result.split() else 0
            logger.info(f"Deleted {count} VM match documents for scan {scan_id}")
            return count

    async def list_scan_vms(self, scan_id: str) -> List[str]:
        """List all VM IDs that have matches in this scan.

        Args:
            scan_id: Scan ID

        Returns:
            List of VM resource IDs
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT vm_id FROM vm_cve_matches WHERE scan_id = $1 ORDER BY vm_name",
                scan_id,
            )
            return [row["vm_id"] for row in rows]
