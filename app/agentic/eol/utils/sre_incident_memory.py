"""SRE Incident Memory — Cosmos-backed store for SRE incident records.

Stores incident → action → outcome triples after each completed SRE workflow.
On new queries, retrieves similar past incidents and injects them as a compact
context prefix (≤300 tokens) so the SRE agent learns from past resolutions.

Similarity (v1): Token Jaccard overlap — fast, no embeddings needed.
Upgrade path: swap `_jaccard_similarity` for `text-embedding-3-small` in v2
              without changing any public API.

Usage:
    memory = SREIncidentMemory()
    await memory.initialize()

    # After resolving an incident:
    await memory.store(
        workflow_id="wf-123",
        query="container app is returning 503",
        domain="health",
        tools_used=["check_container_app_health", "diagnose_app_service"],
        resolution="Restarted app revision, replica count was 0",
        outcome="resolved",
    )

    # Before a new query:
    context = await memory.get_context_prefix("my app is down with 503 errors")
    # Returns: "Similar past incidents:\\n1. container app is returning 503 → Restarted..."
"""
from __future__ import annotations

import json
import re
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

try:
    from app.agentic.eol.utils.cosmos_cache import base_cosmos
    from app.agentic.eol.utils.logger import get_logger
except ModuleNotFoundError:
    from utils.cosmos_cache import base_cosmos  # type: ignore[import-not-found]
    from utils.logger import get_logger  # type: ignore[import-not-found]

logger = get_logger(__name__)

_CONTAINER_ID = "sre_incidents"
_PARTITION_PATH = "/domain"
_DEFAULT_TTL_SECONDS = 90 * 24 * 3600  # 90 days retention
_TOP_K_DEFAULT = 3
_CONTEXT_MAX_CHARS = 1_200  # ≈300 tokens at 4 chars/token


@dataclass
class IncidentRecord:
    """A single stored SRE incident."""

    id: str
    workflow_id: str
    query: str
    domain: str
    tools_used: List[str]
    resolution: str
    outcome: str  # "resolved" | "escalated" | "partial"
    timestamp: str  # ISO 8601

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "IncidentRecord":
        return cls(
            id=d.get("id", ""),
            workflow_id=d.get("workflow_id", ""),
            query=d.get("query", ""),
            domain=d.get("domain", "general"),
            tools_used=d.get("tools_used", []),
            resolution=d.get("resolution", ""),
            outcome=d.get("outcome", "unknown"),
            timestamp=d.get("timestamp", ""),
        )


class SREIncidentMemory:
    """Cosmos-backed incident memory store for the SRE orchestrator.

    Gracefully degrades to no-op when Cosmos is unavailable (never raises).
    """

    def __init__(self) -> None:
        self._container: Optional[Any] = None
        self._initialized: bool = False
        self._fallback_store: List[Dict[str, Any]] = []  # in-memory fallback

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def initialize(self) -> bool:
        """Initialize the Cosmos container. Returns True on success."""
        if self._initialized:
            return self._container is not None

        try:
            base_cosmos._ensure_initialized()
            if not base_cosmos.initialized:
                logger.warning(
                    "SREIncidentMemory: Cosmos unavailable — using in-memory fallback"
                )
                self._initialized = True
                return False

            self._container = base_cosmos.get_container(
                container_id=_CONTAINER_ID,
                partition_path=_PARTITION_PATH,
                offer_throughput=400,
                default_ttl=_DEFAULT_TTL_SECONDS,
            )
            self._initialized = True
            logger.info("✅ SREIncidentMemory: Cosmos container '%s' ready", _CONTAINER_ID)
            return True

        except Exception as exc:
            logger.warning("SREIncidentMemory: Failed to init Cosmos: %s", exc)
            self._initialized = True
            return False

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    async def store(
        self,
        workflow_id: str,
        query: str,
        domain: str,
        tools_used: List[str],
        resolution: str,
        outcome: str = "resolved",
    ) -> Optional[str]:
        """Persist an incident record. Returns the record ID or None on failure."""
        if not self._initialized:
            await self.initialize()

        record = IncidentRecord(
            id=str(uuid.uuid4()),
            workflow_id=workflow_id,
            query=query,
            domain=domain,
            tools_used=tools_used,
            resolution=resolution,
            outcome=outcome,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        doc = record.to_dict()

        if self._container is not None:
            try:
                self._container.upsert_item(doc)
                logger.debug(
                    "SREIncidentMemory: stored incident id=%s domain=%s", record.id, domain
                )
                return record.id
            except Exception as exc:
                logger.warning("SREIncidentMemory: Failed to store in Cosmos: %s", exc)
                # Fall through to in-memory fallback

        # In-memory fallback
        self._fallback_store.append(doc)
        # Keep fallback bounded to last 100 records
        if len(self._fallback_store) > 100:
            self._fallback_store = self._fallback_store[-100:]
        return record.id

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    async def retrieve_similar(
        self,
        query: str,
        top_k: int = _TOP_K_DEFAULT,
        domain: Optional[str] = None,
    ) -> List[IncidentRecord]:
        """Return the top-k most similar past incidents to the given query.

        Similarity is computed via token Jaccard overlap (v1).
        When domain is provided, results are biased toward same-domain records.

        Returns an empty list on any failure — never raises.
        """
        if not self._initialized:
            await self.initialize()

        candidates = await self._fetch_candidates(domain=domain, limit=200)
        if not candidates:
            return []

        scored = [
            (self._jaccard_similarity(query, c.get("query", "")), c)
            for c in candidates
        ]
        scored.sort(key=lambda t: t[0], reverse=True)

        return [
            IncidentRecord.from_dict(doc)
            for score, doc in scored[:top_k]
            if score > 0
        ]

    async def get_context_prefix(
        self,
        query: str,
        top_k: int = _TOP_K_DEFAULT,
        domain: Optional[str] = None,
    ) -> str:
        """Return a compact context string for injection into the user message.

        Example output (≤_CONTEXT_MAX_CHARS chars):
            Similar past incidents:
            1. [health] Container app returning 503 → Restarted app revision (resolved)
            2. [health] App service unhealthy after deploy → Rolled back deployment (resolved)
        """
        records = await self.retrieve_similar(query, top_k=top_k, domain=domain)
        if not records:
            return ""

        lines = ["Similar past incidents:"]
        total_chars = len(lines[0])
        for i, rec in enumerate(records, start=1):
            short_query = rec.query[:100] + ("…" if len(rec.query) > 100 else "")
            short_res = rec.resolution[:120] + ("…" if len(rec.resolution) > 120 else "")
            line = f"{i}. [{rec.domain}] {short_query} → {short_res} ({rec.outcome})"
            if total_chars + len(line) + 1 > _CONTEXT_MAX_CHARS:
                break
            lines.append(line)
            total_chars += len(line) + 1

        if len(lines) == 1:
            return ""  # Only header, no results fit
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _fetch_candidates(
        self, domain: Optional[str], limit: int
    ) -> List[Dict[str, Any]]:
        """Fetch recent incident records from Cosmos or in-memory fallback."""
        if self._container is not None:
            try:
                query_str = (
                    f"SELECT TOP {limit} * FROM c ORDER BY c._ts DESC"
                    if domain is None
                    else (
                        f"SELECT TOP {limit} * FROM c WHERE c.domain = @domain "
                        f"ORDER BY c._ts DESC"
                    )
                )
                params = [{"name": "@domain", "value": domain}] if domain else None
                kwargs: Dict[str, Any] = {"query": query_str, "enable_cross_partition_query": True}
                if params:
                    kwargs["parameters"] = params
                return list(self._container.query_items(**kwargs))
            except Exception as exc:
                logger.warning("SREIncidentMemory: Cosmos query failed: %s", exc)

        # In-memory fallback — filter by domain if specified
        items = self._fallback_store[-limit:]
        if domain:
            items = [i for i in items if i.get("domain") == domain]
        return list(reversed(items))  # newest first

    @staticmethod
    def _tokenize(text: str) -> set[str]:
        """Extract lowercase alpha-numeric tokens of length ≥ 3."""
        return {
            tok
            for tok in re.findall(r"[a-z0-9]+", text.lower())
            if len(tok) >= 3
        }

    @classmethod
    def _jaccard_similarity(cls, a: str, b: str) -> float:
        """Jaccard similarity between two text strings (token sets).

        Returns a float in [0, 1]. Returns 0 when either string is empty.
        """
        tokens_a = cls._tokenize(a)
        tokens_b = cls._tokenize(b)
        if not tokens_a or not tokens_b:
            return 0.0
        intersection = tokens_a & tokens_b
        union = tokens_a | tokens_b
        return len(intersection) / len(union)


# Module-level singleton
_memory_instance: Optional[SREIncidentMemory] = None


def get_sre_incident_memory() -> SREIncidentMemory:
    """Return the module-level SREIncidentMemory singleton."""
    global _memory_instance
    if _memory_instance is None:
        _memory_instance = SREIncidentMemory()
    return _memory_instance
