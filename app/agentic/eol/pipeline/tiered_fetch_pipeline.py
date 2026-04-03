"""Tiered fetch pipeline for EOL data queries.

Executes source adapters through sequential reliability tiers (1 -> 2 -> 3 -> 4),
with concurrent execution within each tier, per-adapter timeouts (SRC-05), confidence
scoring, and early termination when a result exceeds the confidence threshold.

Usage:
    from pipeline import TieredFetchPipeline, create_default_registry
    from utils.normalization import NormalizedQuery

    registry = create_default_registry(agents)
    pipeline = TieredFetchPipeline(registry, confidence_threshold=0.80)
    result = await pipeline.fetch(NormalizedQuery.from_software("python", "3.9"))
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from typing import List, Optional

from utils.confidence_scorer import confidence_scorer
from utils.normalization import NormalizedQuery

from .source_adapter import AdapterRegistry, SourceAdapter, SourceResult

logger = logging.getLogger(__name__)


class TieredFetchPipeline:
    """Sequential-tier pipeline with concurrent intra-tier execution.

    Processes tiers from lowest (most reliable) to highest (least reliable).
    Stops early when a result's confidence meets the configured threshold.

    Attributes:
        registry: AdapterRegistry grouping adapters by tier.
        confidence_threshold: Minimum confidence for early termination.
    """

    def __init__(
        self,
        registry: AdapterRegistry,
        confidence_threshold: float = 0.80,
    ) -> None:
        """Initialize the pipeline.

        Args:
            registry: AdapterRegistry with adapters registered by tier.
            confidence_threshold: Score >= this triggers early termination.
                Default 0.80 matches config.eol.pipeline_confidence_threshold.
        """
        self._registry = registry
        self._confidence_threshold = confidence_threshold

    async def fetch(self, query: NormalizedQuery) -> Optional[SourceResult]:
        """Execute the tiered pipeline for a query.

        Tier execution:
        1. Iterate tiers in ascending order (1, 2, 3, 4).
        2. For each tier, run all adapters concurrently with per-adapter timeouts.
        3. Score each successful result via ConfidenceScorer.
          4. If a Tier 1 or Tier 2 structured source returns a usable result,
              return it before invoking legacy vendor scrapers.
          5. Otherwise, if the best result's confidence >= threshold, return it.
          6. Otherwise, continue to the next tier.
          7. If all tiers exhausted, return the best result seen (or None).

        Args:
            query: Normalized software/OS query.

        Returns:
            Best SourceResult found, or None if all adapters returned nothing.
        """
        pipeline_start = time.monotonic()
        tiers = self._registry.all_tiers()
        tiers_tried: List[int] = []
        best_overall: Optional[SourceResult] = None
        early_terminated = False

        for tier_num in tiers:
            adapters = self._registry.get_tier(tier_num)
            if not adapters:
                continue

            tiers_tried.append(tier_num)
            tier_results = await self._run_tier(adapters, query)

            # Score each successful result
            for result in tier_results:
                scored_confidence = confidence_scorer.score(
                    result.raw_data.get("data", {}) if result.raw_data else {},
                    result.tier,
                )
                result.confidence = scored_confidence

            # Pick best from this tier
            tier_best = self._pick_best(tier_results)

            # Update overall best
            if tier_best is not None:
                if best_overall is None or tier_best.confidence > best_overall.confidence:
                    best_overall = tier_best

            # Structured sources are authoritative enough to avoid legacy
            # vendor scrapers when they already returned a version-aligned EOL.
            if tier_best is not None and self._should_short_circuit_structured_result(
                query, tier_best
            ):
                early_terminated = True
                self._log_result(
                    query, tiers_tried, tiers, best_overall, early_terminated, pipeline_start
                )
                return best_overall

            # Early termination check
            if tier_best is not None and tier_best.confidence >= self._confidence_threshold:
                early_terminated = True
                self._log_result(
                    query, tiers_tried, tiers, best_overall, early_terminated, pipeline_start
                )
                return best_overall

        # All tiers exhausted — return best effort
        self._log_result(
            query, tiers_tried, tiers, best_overall, early_terminated, pipeline_start
        )
        return best_overall

    async def _run_tier(
        self,
        adapters: List[SourceAdapter],
        query: NormalizedQuery,
    ) -> List[SourceResult]:
        """Run all adapters in a tier concurrently with per-adapter timeouts.

        Each adapter.fetch() is wrapped in asyncio.wait_for() with the
        adapter's declared timeout. TimeoutError is caught and treated
        as a miss. Other exceptions from gather(return_exceptions=True)
        are also treated as misses.

        Args:
            adapters: List of adapters in this tier.
            query: Normalized query to pass to each adapter.

        Returns:
            List of successful SourceResults (may be empty).
        """

        async def _guarded_fetch(adapter: SourceAdapter) -> Optional[SourceResult]:
            """Wrap adapter.fetch with timeout."""
            try:
                return await asyncio.wait_for(
                    adapter.fetch(query),
                    timeout=adapter.timeout,
                )
            except asyncio.TimeoutError:
                logger.warning(
                    "[pipeline] adapter=%s tier=%d timed out after %ds for query=%s",
                    adapter.name,
                    adapter.tier,
                    adapter.timeout,
                    query.raw_name,
                )
                return None
            except Exception as exc:
                logger.warning(
                    "[pipeline] adapter=%s tier=%d error: %s",
                    adapter.name,
                    adapter.tier,
                    exc,
                )
                return None

        raw_results = await asyncio.gather(
            *[_guarded_fetch(a) for a in adapters],
            return_exceptions=True,
        )

        # Filter to successful SourceResults
        successes: List[SourceResult] = []
        for r in raw_results:
            if isinstance(r, SourceResult):
                successes.append(r)
            elif isinstance(r, Exception):
                logger.warning("[pipeline] gather-level exception: %s", r)
            # None results are silent misses

        return successes

    @staticmethod
    def _pick_best(results: List[SourceResult]) -> Optional[SourceResult]:
        """Pick the best result from a list by confidence (highest wins).

        If multiple results have the same confidence, prefer the one
        with an eol_date.

        Args:
            results: List of scored SourceResults.

        Returns:
            Best SourceResult or None if list is empty.
        """
        if not results:
            return None

        def _sort_key(r: SourceResult) -> tuple:
            return (r.confidence, 1 if r.eol_date else 0)

        return max(results, key=_sort_key)

    @staticmethod
    def _normalize_version_token(value: Optional[str]) -> str:
        if not value:
            return ""
        return re.sub(r"[^a-z0-9.]+", " ", str(value).lower()).strip()

    def _structured_result_version_aligned(
        self,
        query: NormalizedQuery,
        result: SourceResult,
    ) -> bool:
        """Return True when a structured result plausibly matches the query version."""
        if not query.raw_version:
            return False

        query_version = self._normalize_version_token(query.raw_version)
        if not query_version:
            return False

        raw_data = result.raw_data.get("data", {}) if result.raw_data else {}
        candidates = [
            result.version,
            raw_data.get("version") if isinstance(raw_data, dict) else None,
            raw_data.get("cycle") if isinstance(raw_data, dict) else None,
        ]

        normalized_candidates = [
            self._normalize_version_token(candidate) for candidate in candidates if candidate
        ]
        if not normalized_candidates:
            return False

        return any(
            candidate == query_version
            or candidate.startswith(f"{query_version}.")
            or candidate.startswith(f"{query_version} ")
            for candidate in normalized_candidates
        )

    def _should_short_circuit_structured_result(
        self,
        query: NormalizedQuery,
        result: SourceResult,
    ) -> bool:
        """Return True when Tier 1/2 data is good enough to skip vendor scrapers."""
        if result.tier not in (1, 2):
            return False
        if not result.eol_date:
            return False
        return self._structured_result_version_aligned(query, result)

    async def fetch_all(self, query: NormalizedQuery) -> List[SourceResult]:
        """Run ALL tiers and return ALL successful results (scored).

        Unlike fetch(), this method does NOT early-terminate. It runs every
        tier sequentially, scores each result via ConfidenceScorer, and
        returns all successful SourceResults for cross-source validation.

        Args:
            query: Normalized software/OS query.

        Returns:
            List of scored SourceResults from all tiers (may be empty).
        """
        pipeline_start = time.monotonic()
        all_results: List[SourceResult] = []

        for tier_num in self._registry.all_tiers():
            adapters = self._registry.get_tier(tier_num)
            if not adapters:
                continue

            tier_results = await self._run_tier(adapters, query)

            for result in tier_results:
                scored_confidence = confidence_scorer.score(
                    result.raw_data.get("data", {}) if result.raw_data else {},
                    result.tier,
                )
                result.confidence = scored_confidence
                all_results.append(result)

        duration_ms = round((time.monotonic() - pipeline_start) * 1000, 1)
        logger.info(
            '[pipeline] fetch_all query="%s" version="%s" results=%d duration_ms=%.1f',
            query.raw_name,
            query.raw_version or "",
            len(all_results),
            duration_ms,
        )
        return all_results

    def _log_result(
        self,
        query: NormalizedQuery,
        tiers_tried: List[int],
        all_tiers: List[int],
        best: Optional[SourceResult],
        early_terminated: bool,
        start_time: float,
    ) -> None:
        """Log tier progression summary at INFO level."""
        duration_ms = round((time.monotonic() - start_time) * 1000, 1)
        tiers_skipped = [t for t in all_tiers if t not in tiers_tried]

        if best is not None:
            logger.info(
                '[pipeline] query="%s" version="%s" tiers_tried=%s tiers_skipped=%s '
                "result_tier=%d result_source=%s confidence=%.3f "
                "early_terminated=%s duration_ms=%.1f",
                query.raw_name,
                query.raw_version or "",
                tiers_tried,
                tiers_skipped,
                best.tier,
                best.source,
                best.confidence,
                early_terminated,
                duration_ms,
            )
        else:
            logger.info(
                '[pipeline] query="%s" version="%s" tiers_tried=%s tiers_skipped=%s '
                "result_tier=none confidence=0.0 early_terminated=false duration_ms=%.1f",
                query.raw_name,
                query.raw_version or "",
                tiers_tried,
                tiers_skipped,
                duration_ms,
            )
