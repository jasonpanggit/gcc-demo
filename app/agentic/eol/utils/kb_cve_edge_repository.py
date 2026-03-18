"""Persistence for canonical KB-to-CVE reverse mappings."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Optional

import asyncpg

try:
    from models.cve_models import KBCVEEdge, PatchAdvisoryEdge, UnifiedCVE
    from utils.logging_config import get_logger
    from utils.normalization import extract_kb_ids, normalize_kb_id
except ModuleNotFoundError:
    from app.agentic.eol.models.cve_models import KBCVEEdge, PatchAdvisoryEdge, UnifiedCVE
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
            id=f"microsoft:{kb_number}:{cve.cve_id.upper()}",
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
    """PostgreSQL-backed repository for reverse KB-to-CVE edges."""

    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    async def initialize(self):
        logger.info("KBCVEEdgeRepository initialized with PostgreSQL")

    @staticmethod
    def _edge_id(kb_number: str, cve_id: str, source: str) -> str:
        return f"{source}:{kb_number}:{cve_id.upper()}"

    @staticmethod
    def _normalize_source_os_family(source: str, os_family: Optional[str]) -> str:
        if os_family:
            return os_family
        return "windows" if source == "microsoft" else source

    @classmethod
    def _row_to_edge(cls, row: asyncpg.Record) -> PatchAdvisoryEdge:
        source = row["source"]
        kb_number = row["kb_number"]
        cve_id = row["cve_id"].upper()
        return PatchAdvisoryEdge(
            id=cls._edge_id(kb_number, cve_id, source),
            kb_number=kb_number,
            cve_id=cve_id,
            source=source,
            os_family=cls._normalize_source_os_family(source, row["os_family"]),
            advisory_id=row["advisory_id"] or kb_number,
            affected_packages=row["affected_pkgs"],
            fixed_packages=row["fixed_pkgs"],
            update_id=row["update_id"],
            document_title=row["document_title"],
            cvrf_url=row["cvrf_url"],
            severity=row["severity"],
            published_date=row["published_date"],
            last_seen=row["last_seen"] or datetime.now(timezone.utc),
        )

    async def _upsert_edges(self, edges: List[PatchAdvisoryEdge]) -> int:
        if not edges:
            return 0

        async with self.pool.acquire() as conn:
            for edge in edges:
                if not edge.id:
                    edge.id = self._edge_id(edge.kb_number, edge.cve_id, edge.source)
                await conn.execute(
                    """
                    INSERT INTO kb_cve_edges (
                        kb_number, cve_id, source, os_family, advisory_id,
                        affected_pkgs, fixed_pkgs, update_id, document_title,
                        cvrf_url, published_date, severity, last_seen, cached_at
                    )
                    VALUES (
                        $1, $2, $3, $4, $5,
                        $6, $7, $8, $9,
                        $10, $11, $12, $13, NOW()
                    )
                    ON CONFLICT (kb_number, cve_id, source) DO UPDATE SET
                        os_family = COALESCE(EXCLUDED.os_family, kb_cve_edges.os_family),
                        advisory_id = COALESCE(EXCLUDED.advisory_id, kb_cve_edges.advisory_id),
                        affected_pkgs = COALESCE(EXCLUDED.affected_pkgs, kb_cve_edges.affected_pkgs),
                        fixed_pkgs = COALESCE(EXCLUDED.fixed_pkgs, kb_cve_edges.fixed_pkgs),
                        update_id = COALESCE(EXCLUDED.update_id, kb_cve_edges.update_id),
                        document_title = COALESCE(EXCLUDED.document_title, kb_cve_edges.document_title),
                        cvrf_url = COALESCE(EXCLUDED.cvrf_url, kb_cve_edges.cvrf_url),
                        published_date = COALESCE(EXCLUDED.published_date, kb_cve_edges.published_date),
                        severity = COALESCE(EXCLUDED.severity, kb_cve_edges.severity),
                        last_seen = EXCLUDED.last_seen,
                        cached_at = NOW()
                    """,
                    edge.kb_number,
                    edge.cve_id.upper(),
                    edge.source,
                    edge.os_family,
                    edge.advisory_id or edge.kb_number,
                    edge.affected_packages,
                    edge.fixed_packages,
                    edge.update_id,
                    edge.document_title,
                    edge.cvrf_url,
                    edge.published_date,
                    edge.severity,
                    edge.last_seen,
                )
        return len(edges)

    async def sync_cve_edges(self, cve: UnifiedCVE) -> List[KBCVEEdge]:
        desired_edges = _build_edges_for_cve(cve)
        desired_ids = {edge.id for edge in desired_edges}
        existing_edges = await self.get_advisories_for_cve(cve.cve_id, source="microsoft")

        stale_edges = [edge for edge in existing_edges if edge.id not in desired_ids]

        async with self.pool.acquire() as conn:
            for edge in stale_edges:
                await conn.execute(
                    "DELETE FROM kb_cve_edges WHERE kb_number = $1 AND cve_id = $2 AND source = $3",
                    edge.kb_number,
                    edge.cve_id.upper(),
                    edge.source,
                )

        await self._upsert_edges(desired_edges)

        return desired_edges

    async def list_edges_for_cve(self, cve_id: str) -> List[KBCVEEdge]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT kb_number, cve_id, source, os_family, advisory_id,
                       affected_pkgs, fixed_pkgs, update_id, document_title,
                       cvrf_url, published_date, severity, last_seen
                FROM kb_cve_edges
                WHERE cve_id = $1
                ORDER BY source, kb_number
                """,
                cve_id.upper(),
            )
        return [self._row_to_edge(row) for row in rows]

    async def get_edges_for_kb(self, kb_number: str) -> List[KBCVEEdge]:
        normalized_kb = normalize_kb_id(kb_number)
        if not normalized_kb:
            return []

        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT kb_number, cve_id, source, os_family, advisory_id,
                       affected_pkgs, fixed_pkgs, update_id, document_title,
                       cvrf_url, published_date, severity, last_seen
                FROM kb_cve_edges
                WHERE kb_number = $1
                ORDER BY cve_id
                """,
                normalized_kb,
            )
        return [self._row_to_edge(row) for row in rows]

    async def get_cve_ids_for_kb(self, kb_number: str) -> List[str]:
        edges = await self.get_edges_for_kb(kb_number)
        return sorted({edge.cve_id for edge in edges})

    async def get_advisories_for_cve(
        self,
        cve_id: str,
        source: Optional[str] = None,
    ) -> List[PatchAdvisoryEdge]:
        """Fetch all advisory edges for a CVE, optionally filtered by source.

        source: None = all sources, or "microsoft" | "redhat" | "ubuntu"
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT kb_number, cve_id, source, os_family, advisory_id,
                       affected_pkgs, fixed_pkgs, update_id, document_title,
                       cvrf_url, published_date, severity, last_seen
                FROM kb_cve_edges
                WHERE cve_id = $1
                  AND ($2::text IS NULL OR source = $2)
                ORDER BY source, kb_number
                """,
                cve_id.upper(),
                source,
            )
        return [self._row_to_edge(row) for row in rows]

    async def get_fixed_packages_for_cve(
        self,
        cve_id: str,
        os_family: str,
    ) -> Dict[str, List[str]]:
        """Return {advisory_id: [package_names]} for a CVE + os_family."""
        source_map = {"ubuntu": "ubuntu", "rhel": "redhat", "centos": "redhat", "debian": "debian"}
        source = source_map.get(os_family.lower())
        edges = await self.get_advisories_for_cve(cve_id, source=source)
        result: Dict[str, List[str]] = {}
        for edge in edges:
            if edge.fixed_packages:
                advisory = edge.advisory_id or edge.kb_number
                result[advisory] = edge.fixed_packages
        return result

    async def get_kbs_for_cve(self, cve_id: str) -> List[str]:
        """Return list of KB IDs (Windows) that fix a given CVE."""
        edges = await self.get_advisories_for_cve(cve_id, source="microsoft")
        return sorted({edge.kb_number for edge in edges})

    async def upsert_linux_edges(self, edges: List[PatchAdvisoryEdge]) -> int:
        """Batch upsert Linux advisory edges. Returns count upserted."""
        return await self._upsert_edges(edges)

    async def bulk_upsert(self, edges: List[PatchAdvisoryEdge]) -> int:
        """Batch upsert any edges (Windows or Linux). Returns count upserted."""
        return await self._upsert_edges(edges)


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

    async def get_advisories_for_cve(
        self,
        cve_id: str,
        source: Optional[str] = None,
    ) -> List[PatchAdvisoryEdge]:
        normalized_cve = cve_id.upper()
        edges = [e for e in self.items.values() if e.cve_id == normalized_cve]
        if source:
            edges = [e for e in edges if e.source == source]
        return edges

    async def get_fixed_packages_for_cve(
        self,
        cve_id: str,
        os_family: str,
    ) -> Dict[str, List[str]]:
        source_map = {"ubuntu": "ubuntu", "rhel": "redhat", "centos": "redhat", "debian": "debian"}
        source = source_map.get(os_family.lower())
        edges = await self.get_advisories_for_cve(cve_id, source=source)
        result: Dict[str, List[str]] = {}
        for edge in edges:
            if edge.fixed_packages:
                advisory = edge.advisory_id or edge.kb_number
                result[advisory] = edge.fixed_packages
        return result

    async def get_kbs_for_cve(self, cve_id: str) -> List[str]:
        edges = await self.get_advisories_for_cve(cve_id, source="microsoft")
        return sorted({edge.kb_number for edge in edges})

    async def upsert_linux_edges(self, edges: List[PatchAdvisoryEdge]) -> int:
        count = 0
        for edge in edges:
            if not edge.id:
                edge.id = f"{edge.source}:{edge.kb_number}:{edge.cve_id}"
            self.items[edge.id] = edge
            count += 1
        return count

    async def bulk_upsert(self, edges: List[PatchAdvisoryEdge]) -> int:
        return await self.upsert_linux_edges(edges)