"""VMCVEMatchRepository - per-VM CVE match document storage.

Stores and retrieves CVE match documents for individual VMs.
Documents live in the same Cosmos container as scan metadata,
identified by ID format: "{scan_id}--{vm_name}".

Partition key is scan_id for co-location with the main scan doc.
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

try:
    from models.cve_models import CVEMatch
    from utils.logging_config import get_logger
except ModuleNotFoundError:
    from app.agentic.eol.models.cve_models import CVEMatch
    from app.agentic.eol.utils.logging_config import get_logger

logger = get_logger(__name__)

_SIZE_LIMIT_BYTES = 1_800_000  # 1.8MB - safety margin below Cosmos 2MB limit


class VMCVEMatchRepository:
    """Repository for per-VM CVE match document storage in Cosmos DB.

    Documents are stored in the same container as CVEScanRepository,
    co-located by scan_id partition key.
    """

    def __init__(self, cosmos_client, database_name: str, container_name: str):
        self.cosmos_client = cosmos_client
        self.database_name = database_name
        self.container_name = container_name
        self.container = None

    async def initialize(self):
        """Initialize Cosmos container reference."""
        try:
            database = self.cosmos_client.get_database_client(self.database_name)
            self.container = database.get_container_client(self.container_name)
            logger.info(f"VMCVEMatchRepository initialized: {self.container_name}")
        except Exception as e:
            logger.error(f"Failed to initialize VMCVEMatchRepository: {e}")
            raise

    async def save_vm_matches(
        self,
        scan_id: str,
        vm_id: str,
        vm_name: str,
        matches: List[CVEMatch],
    ) -> None:
        """Save all CVE matches for a VM.

        Args:
            scan_id: Parent scan ID (also the Cosmos partition key)
            vm_id: Full Azure resource ID of the VM
            vm_name: VM display name
            matches: CVEMatch objects to persist

        Raises:
            ValueError: If the serialized document exceeds 1.8MB
        """
        doc_id = self._build_vm_match_doc_id(scan_id, vm_id)

        item = {
            "id": doc_id,
            "scan_id": scan_id,
            "vm_id": vm_id,
            "vm_name": vm_name,
            "total_matches": len(matches),
            "matches": [m.dict() for m in matches],
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        doc_size = len(json.dumps(item).encode("utf-8"))
        if doc_size > _SIZE_LIMIT_BYTES:
            raise ValueError(
                f"Document too large for VM {vm_name}: {doc_size:,} bytes "
                f"(limit {_SIZE_LIMIT_BYTES:,} bytes)"
            )

        await asyncio.to_thread(self.container.upsert_item, body=item)
        logger.info(f"Saved {len(matches)} CVE matches for VM {vm_name} (doc: {doc_id})")

    async def get_vm_matches(
        self,
        scan_id: str,
        vm_id: str,
        offset: int = 0,
        limit: int = 100,
    ) -> Optional[Dict[str, Any]]:
        """Fetch paginated CVE matches for a VM via point read.

        Args:
            scan_id: Parent scan ID
            vm_id: VM resource ID (full path or bare name)
            offset: Starting index for pagination
            limit: Maximum number of matches to return

        Returns:
            Dict with vm_id, vm_name, total_matches, matches, has_more
            or None if document not found
        """
        doc_id = self._build_vm_match_doc_id(scan_id, vm_id)

        try:
            item = await asyncio.to_thread(
                self.container.read_item,
                item=doc_id,
                partition_key=scan_id,
            )
        except Exception:
            logger.debug(f"VM match document not found: {doc_id}")
            return None

        all_matches = item.get("matches", [])
        page = all_matches[offset : offset + limit]

        return {
            "vm_id": item["vm_id"],
            "vm_name": item["vm_name"],
            "total_matches": item["total_matches"],
            "matches": page,
            "has_more": (offset + limit) < len(all_matches),
        }

    async def delete_vm_matches(self, scan_id: str, vm_id: str) -> None:
        """Delete the VM match document for a specific VM."""
        doc_id = self._build_vm_match_doc_id(scan_id, vm_id)
        await asyncio.to_thread(
            self.container.delete_item,
            item=doc_id,
            partition_key=scan_id,
        )
        logger.info(f"Deleted VM match document: {doc_id}")

    async def delete_all_for_scan(self, scan_id: str) -> int:
        """Delete all VM match documents for a scan.

        Returns:
            Number of documents deleted
        """
        query = (
            "SELECT c.id FROM c "
            "WHERE c.scan_id = @scan_id AND CONTAINS(c.id, '--')"
        )
        items = await asyncio.to_thread(
            lambda: list(
                self.container.query_items(
                    query=query,
                    parameters=[{"name": "@scan_id", "value": scan_id}],
                    partition_key=scan_id,
                )
            )
        )

        for item in items:
            await asyncio.to_thread(
                self.container.delete_item,
                item=item["id"],
                partition_key=scan_id,
            )

        logger.info(f"Deleted {len(items)} VM match documents for scan {scan_id}")
        return len(items)

    def _build_vm_match_doc_id(self, scan_id: str, vm_id: str) -> str:
        """Build deterministic document ID from scan_id and VM resource ID.

        Extracts last path segment from Azure resource ID, or uses bare name.
        Example:
            scan_id="abc-123",
            vm_id="/subscriptions/.../virtualMachines/WIN-SERVER"
            → "abc-123--WIN-SERVER"
        """
        vm_suffix = vm_id.split("/")[-1] if "/" in vm_id else vm_id
        return f"{scan_id}--{vm_suffix}"
