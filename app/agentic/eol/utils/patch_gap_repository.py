"""Cosmos-backed store for pre-computed per-VM patch gap documents and fleet summary.

Container: cve_patch_gaps
Partition key: /id  (vm_id for per-VM docs; "_fleet_summary" for the singleton)
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

try:
    from azure.cosmos import exceptions as cosmos_exceptions
    COSMOS_IMPORTS_OK = True
except ModuleNotFoundError:
    COSMOS_IMPORTS_OK = False

try:
    from models.cve_models import PatchGapFleetSummary, PatchGapVMDoc
    from utils.logging_config import get_logger
except ModuleNotFoundError:
    from app.agentic.eol.models.cve_models import PatchGapFleetSummary, PatchGapVMDoc
    from app.agentic.eol.utils.logging_config import get_logger


logger = get_logger(__name__)

_FLEET_SUMMARY_ID = "_fleet_summary"


class PatchGapRepository:
    """Cosmos-backed store for pre-computed patch gap documents.

    Container: cve_patch_gaps
    Partition key: /id
      - Per-VM docs: id = vm_id
      - Fleet summary: id = "_fleet_summary"
    """

    def __init__(self, cosmos_client, database_name: str, container_name: str):
        if not COSMOS_IMPORTS_OK:
            raise ImportError("Azure Cosmos DB SDK not available")

        self.cosmos_client = cosmos_client
        self.database_name = database_name
        self.container_name = container_name
        self.container = None

    async def initialize(self) -> None:
        """Resolve the container client (lazy init)."""
        database = self.cosmos_client.get_database_client(self.database_name)
        self.container = database.get_container_client(self.container_name)
        logger.info("PatchGapRepository initialized: %s", self.container_name)

    async def _get_container(self):
        """Return container client, initializing on first use."""
        if self.container is None:
            await self.initialize()
        return self.container

    # ------------------------------------------------------------------
    # Per-VM operations
    # ------------------------------------------------------------------

    async def upsert_vm_gap(self, doc: PatchGapVMDoc) -> None:
        """Insert or update a per-VM patch gap document.

        Uses optimistic concurrency via _etag when the doc carries one
        (i.e. was read from Cosmos before being written back).
        Partition key = vm_id = doc.id.
        """
        container = await self._get_container()
        body = doc.model_dump(mode="json")
        body["id"] = doc.vm_id  # ensure id == vm_id

        # Build access condition for optimistic concurrency if _etag is present
        kwargs: dict = {"body": body}
        etag = body.pop("_etag", None)
        if etag:
            kwargs["etag"] = etag
            kwargs["match_condition"] = "IfMatch"

        try:
            await asyncio.to_thread(container.upsert_item, **kwargs)
            logger.debug("Upserted VM gap doc: %s", doc.vm_id)
        except cosmos_exceptions.CosmosHttpResponseError as exc:
            logger.error("Failed to upsert VM gap doc %s: %s", doc.vm_id, exc)
            raise

    async def get_vm_gap(self, vm_id: str) -> Optional[PatchGapVMDoc]:
        """Point-read a per-VM patch gap document.

        Args:
            vm_id: VM resource ID (used as both document id and partition key).

        Returns:
            PatchGapVMDoc or None if not found.
        """
        container = await self._get_container()
        try:
            item = await asyncio.to_thread(
                container.read_item,
                item=vm_id,
                partition_key=vm_id,
            )
            return self._doc_to_vm_gap(item)
        except cosmos_exceptions.CosmosResourceNotFoundError:
            logger.debug("VM gap doc not found: %s", vm_id)
            return None
        except Exception as exc:
            logger.error("Failed to read VM gap doc %s: %s", vm_id, exc)
            return None

    async def get_all_vm_gaps(self, max_age_hours: int = 48) -> List[PatchGapVMDoc]:
        """Fetch all per-VM docs computed within the last *max_age_hours* hours.

        Excludes the fleet summary singleton.
        Age filtering is done in Python after the query because Cosmos SQL
        date comparison requires careful type handling.
        """
        container = await self._get_container()
        # Exclude the fleet summary doc explicitly
        query = "SELECT * FROM c WHERE c.id != @fleet_id"
        parameters = [{"name": "@fleet_id", "value": _FLEET_SUMMARY_ID}]

        try:
            items = await asyncio.to_thread(
                lambda: list(
                    container.query_items(
                        query=query,
                        parameters=parameters,
                        enable_cross_partition_query=True,
                    )
                )
            )
        except Exception as exc:
            logger.error("Failed to query VM gap docs: %s", exc)
            return []

        cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
        results: List[PatchGapVMDoc] = []
        for item in items:
            try:
                doc = self._doc_to_vm_gap(item)
                # Filter by computed_at age
                computed_at_str = doc.computed_at
                if computed_at_str:
                    try:
                        computed_dt = datetime.fromisoformat(computed_at_str)
                        if computed_dt.tzinfo is None:
                            computed_dt = computed_dt.replace(tzinfo=timezone.utc)
                        if computed_dt >= cutoff:
                            results.append(doc)
                    except ValueError:
                        # If we can't parse the timestamp, include the doc conservatively
                        results.append(doc)
                else:
                    results.append(doc)
            except Exception as exc:
                logger.warning("Failed to parse VM gap doc %s: %s", item.get("id"), exc)

        return results

    # ------------------------------------------------------------------
    # Fleet summary operations
    # ------------------------------------------------------------------

    async def upsert_fleet_summary(self, summary: PatchGapFleetSummary) -> None:
        """Insert or update the singleton fleet summary document.

        id = "_fleet_summary", partition_key = "_fleet_summary".
        """
        container = await self._get_container()
        body = summary.model_dump(mode="json")
        body["id"] = _FLEET_SUMMARY_ID  # enforce singleton key

        try:
            await asyncio.to_thread(container.upsert_item, body=body)
            logger.debug("Upserted fleet summary doc")
        except cosmos_exceptions.CosmosHttpResponseError as exc:
            logger.error("Failed to upsert fleet summary: %s", exc)
            raise

    async def get_fleet_summary(self) -> Optional[PatchGapFleetSummary]:
        """Point-read the fleet summary singleton.

        Returns:
            PatchGapFleetSummary or None if not yet computed.
        """
        container = await self._get_container()
        try:
            item = await asyncio.to_thread(
                container.read_item,
                item=_FLEET_SUMMARY_ID,
                partition_key=_FLEET_SUMMARY_ID,
            )
            return self._doc_to_fleet_summary(item)
        except cosmos_exceptions.CosmosResourceNotFoundError:
            logger.debug("Fleet summary doc not found")
            return None
        except Exception as exc:
            logger.error("Failed to read fleet summary: %s", exc)
            return None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _strip_cosmos_fields(item: dict) -> dict:
        """Remove Cosmos system metadata fields before model construction."""
        strip = {"_rid", "_self", "_attachments", "_ts"}
        return {k: v for k, v in item.items() if k not in strip}

    def _doc_to_vm_gap(self, item: dict) -> PatchGapVMDoc:
        return PatchGapVMDoc(**self._strip_cosmos_fields(item))

    def _doc_to_fleet_summary(self, item: dict) -> PatchGapFleetSummary:
        return PatchGapFleetSummary(**self._strip_cosmos_fields(item))


# =============================================================================
# In-memory implementation (mock / test mode)
# =============================================================================

class InMemoryPatchGapRepository:
    """In-memory patch gap store for mock and test mode.

    Shares the same interface as PatchGapRepository.
    """

    def __init__(self):
        # Keyed by vm_id; fleet summary stored under _FLEET_SUMMARY_ID
        self._vm_docs: Dict[str, PatchGapVMDoc] = {}
        self._fleet_summary: Optional[PatchGapFleetSummary] = None

    async def initialize(self) -> None:
        return None

    # ------------------------------------------------------------------
    # Per-VM operations
    # ------------------------------------------------------------------

    async def upsert_vm_gap(self, doc: PatchGapVMDoc) -> None:
        self._vm_docs[doc.vm_id] = doc
        logger.debug("InMemory: upserted VM gap doc %s", doc.vm_id)

    async def get_vm_gap(self, vm_id: str) -> Optional[PatchGapVMDoc]:
        return self._vm_docs.get(vm_id)

    async def get_all_vm_gaps(self, max_age_hours: int = 48) -> List[PatchGapVMDoc]:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
        results: List[PatchGapVMDoc] = []
        for doc in self._vm_docs.values():
            try:
                computed_dt = datetime.fromisoformat(doc.computed_at)
                if computed_dt.tzinfo is None:
                    computed_dt = computed_dt.replace(tzinfo=timezone.utc)
                if computed_dt >= cutoff:
                    results.append(doc)
            except (ValueError, AttributeError):
                results.append(doc)
        return results

    # ------------------------------------------------------------------
    # Fleet summary operations
    # ------------------------------------------------------------------

    async def upsert_fleet_summary(self, summary: PatchGapFleetSummary) -> None:
        self._fleet_summary = summary
        logger.debug("InMemory: upserted fleet summary")

    async def get_fleet_summary(self) -> Optional[PatchGapFleetSummary]:
        return self._fleet_summary
