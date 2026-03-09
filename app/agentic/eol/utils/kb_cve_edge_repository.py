"""Persistence for canonical KB-to-CVE reverse mappings."""
from __future__ import annotations

import asyncio
from datetime import timezone
from typing import Dict, List

try:
    from models.cve_models import KBCVEEdge, UnifiedCVE
    from utils.logging_config import get_logger
    from utils.normalization import extract_kb_ids, normalize_kb_id
except ModuleNotFoundError:
    from app.agentic.eol.models.cve_models import KBCVEEdge, UnifiedCVE
    from app.agentic.eol.utils.logging_config import get_logger
    from app.agentic.eol.utils.normalization import extract_kb_ids, normalize_kb_id


logger = get_logger(__name__)


def _build_edges_for_cve(cve: UnifiedCVE) -> List[KBCVEEdge]:
    kb_numbers: List[str] = []
    seen = set()

    for reference in cve.references:
        for kb_number in extract_kb_ids(reference.url):
            if kb_number in seen:
                continue
            seen.add(kb_number)
            kb_numbers.append(kb_number)

    advisory_id = None
    update_id = None
    document_title = None
    cvrf_url = None
    severity = None

    for vendor_meta in cve.vendor_metadata:
        if vendor_meta.source != "microsoft":
            continue

        advisory_id = advisory_id or vendor_meta.advisory_id
        update_id = update_id or vendor_meta.update_id
        document_title = document_title or vendor_meta.document_title
        cvrf_url = cvrf_url or vendor_meta.cvrf_url
        severity = severity or vendor_meta.severity

        values = [vendor_meta.advisory_id, vendor_meta.kb_numbers]
        metadata = vendor_meta.metadata or {}
        for field in ("kbArticles", "kb_numbers", "kbNumbers"):
            values.append(metadata.get(field))

        for value in values:
            for kb_number in extract_kb_ids(value, allow_bare_numeric=True):
                if kb_number in seen:
                    continue
                seen.add(kb_number)
                kb_numbers.append(kb_number)

    last_seen = cve.last_synced
    if last_seen.tzinfo is None:
        last_seen = last_seen.replace(tzinfo=timezone.utc)

    return [
        KBCVEEdge(
            id=f"{kb_number}:{cve.cve_id.upper()}",
            kb_number=kb_number,
            cve_id=cve.cve_id.upper(),
            advisory_id=advisory_id,
            update_id=update_id,
            document_title=document_title,
            cvrf_url=cvrf_url,
            severity=severity,
            last_seen=last_seen,
        )
        for kb_number in kb_numbers
    ]


class KBCVEEdgeRepository:
    """Cosmos-backed repository for reverse KB-to-CVE edges."""

    def __init__(self, cosmos_client, database_name: str, container_name: str):
        self.cosmos_client = cosmos_client
        self.database_name = database_name
        self.container_name = container_name
        self.container = None

    async def initialize(self):
        database = self.cosmos_client.get_database_client(self.database_name)
        self.container = database.get_container_client(self.container_name)
        logger.info("KBCVEEdgeRepository initialized: %s", self.container_name)

    async def sync_cve_edges(self, cve: UnifiedCVE) -> List[KBCVEEdge]:
        desired_edges = _build_edges_for_cve(cve)
        desired_ids = {edge.id for edge in desired_edges}
        existing_edges = await self.list_edges_for_cve(cve.cve_id)

        for edge in existing_edges:
            if edge.id in desired_ids:
                continue
            await asyncio.to_thread(
                self.container.delete_item,
                item=edge.id,
                partition_key=edge.kb_number,
            )

        for edge in desired_edges:
            await asyncio.to_thread(self.container.upsert_item, edge.model_dump(mode="json"))

        return desired_edges

    async def list_edges_for_cve(self, cve_id: str) -> List[KBCVEEdge]:
        query = "SELECT * FROM c WHERE c.cve_id = @cve_id"
        items = await asyncio.to_thread(
            lambda: list(
                self.container.query_items(
                    query=query,
                    parameters=[{"name": "@cve_id", "value": cve_id.upper()}],
                    enable_cross_partition_query=True,
                )
            )
        )
        return [KBCVEEdge(**item) for item in items]

    async def get_edges_for_kb(self, kb_number: str) -> List[KBCVEEdge]:
        normalized_kb = normalize_kb_id(kb_number)
        if not normalized_kb:
            return []

        query = "SELECT * FROM c WHERE c.kb_number = @kb_number"
        items = await asyncio.to_thread(
            lambda: list(
                self.container.query_items(
                    query=query,
                    parameters=[{"name": "@kb_number", "value": normalized_kb}],
                    partition_key=normalized_kb,
                )
            )
        )
        return [KBCVEEdge(**item) for item in items]

    async def get_cve_ids_for_kb(self, kb_number: str) -> List[str]:
        edges = await self.get_edges_for_kb(kb_number)
        return sorted({edge.cve_id for edge in edges})


class InMemoryKBCVEEdgeRepository:
    """In-memory reverse KB-to-CVE repository for tests and mock mode."""

    def __init__(self):
        self.items: Dict[str, KBCVEEdge] = {}

    async def initialize(self):
        return None

    async def sync_cve_edges(self, cve: UnifiedCVE) -> List[KBCVEEdge]:
        existing_ids = [edge_id for edge_id, edge in self.items.items() if edge.cve_id == cve.cve_id.upper()]
        desired_edges = _build_edges_for_cve(cve)
        desired_ids = {edge.id for edge in desired_edges}

        for edge_id in existing_ids:
            if edge_id not in desired_ids:
                self.items.pop(edge_id, None)

        for edge in desired_edges:
            self.items[edge.id] = edge

        return desired_edges

    async def list_edges_for_cve(self, cve_id: str) -> List[KBCVEEdge]:
        normalized_cve = cve_id.upper()
        return [edge for edge in self.items.values() if edge.cve_id == normalized_cve]

    async def get_edges_for_kb(self, kb_number: str) -> List[KBCVEEdge]:
        normalized_kb = normalize_kb_id(kb_number)
        if not normalized_kb:
            return []
        return [edge for edge in self.items.values() if edge.kb_number == normalized_kb]

    async def get_cve_ids_for_kb(self, kb_number: str) -> List[str]:
        edges = await self.get_edges_for_kb(kb_number)
        return sorted({edge.cve_id for edge in edges})