"""
Optimised Cosmos DB queries for the Resource Inventory feature.

Provides pre-built, parameterised queries that leverage the composite indexes
defined in ``resource_inventory_cosmos.py``:
    1. [/resource_type, /location]
    2. [/resource_group, /resource_name]
    3. [/subscription_id, /resource_type, /location]

Each query helper returns a ``QuerySpec`` (query string + parameters + options)
so callers can pass it straight to ``container.query_items(**spec)``.

A lightweight ``QueryBenchmark`` class is also provided for measuring actual
RU consumption and latency against a live container.

Usage::

    from utils.resource_inventory_queries import optimised_queries, QueryBenchmark

    # Build a query
    spec = optimised_queries.vms_in_subscription("sub-123")
    items = list(container.query_items(**spec))

    # Benchmark
    bench = QueryBenchmark(container)
    report = bench.run_all("sub-123")
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Query result type
# ---------------------------------------------------------------------------

@dataclass
class QuerySpec:
    """Container-ready query specification."""

    query: str
    parameters: List[Dict[str, str]]
    partition_key: Optional[str] = None
    max_item_count: int = 100

    def to_kwargs(self) -> Dict[str, Any]:
        """Return kwargs suitable for ``container.query_items()``."""
        kwargs: Dict[str, Any] = {
            "query": self.query,
            "parameters": self.parameters,
            "max_item_count": self.max_item_count,
        }
        if self.partition_key is not None:
            kwargs["partition_key"] = self.partition_key
        else:
            kwargs["enable_cross_partition_query"] = True
        return kwargs


# ---------------------------------------------------------------------------
# Optimised query builders
# ---------------------------------------------------------------------------

class OptimisedQueries:
    """Pre-built queries that align with the composite indexes.

    Design principles:
      • Always supply ``partition_key`` (subscription_id) so Cosmos routes to
        a single logical partition — avoids fan-out and keeps RU cost ≤ 5 RU
        for typical result sets.
      • Filter columns in the same order as the composite index to allow the
        engine to seek directly instead of scanning.
      • Use ``SELECT`` projections to reduce response payload and RU.
      • Use ``OFFSET … LIMIT`` for pagination to cap response size.
    """

    # -- 1. Find all VMs in a subscription -----------------------------------
    #    Uses composite index [/resource_type, /location] inside a single
    #    partition (subscription_id).  Expected cost: 2–5 RU.

    @staticmethod
    def vms_in_subscription(
        subscription_id: str,
        location: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> QuerySpec:
        """All virtual machines in *subscription_id*, optionally filtered by location."""
        query = (
            "SELECT c.id, c.resource_name, c.resource_group, c.location, "
            "c.tags, c.selected_properties, c.last_seen "
            "FROM c WHERE c.resource_type = @rtype"
        )
        params: List[Dict[str, str]] = [
            {"name": "@rtype", "value": "microsoft.compute/virtualmachines"},
        ]
        if location:
            query += " AND c.location = @loc"
            params.append({"name": "@loc", "value": location})
        query += " ORDER BY c.resource_type ASC, c.location ASC"
        query += f" OFFSET {offset} LIMIT {limit}"
        return QuerySpec(query=query, parameters=params, partition_key=subscription_id)

    # -- 2. Find resources by name pattern -----------------------------------
    #    Uses composite index [/resource_group, /resource_name].
    #    CONTAINS is needed for pattern matching (LIKE is not supported).
    #    Expected cost: 3–8 RU depending on partition size.

    @staticmethod
    def resources_by_name(
        subscription_id: str,
        name_pattern: str,
        resource_group: Optional[str] = None,
        limit: int = 50,
    ) -> QuerySpec:
        """Resources whose name contains *name_pattern* (case-insensitive)."""
        query = (
            "SELECT c.id, c.resource_name, c.resource_type, c.resource_group, "
            "c.location, c.tags "
            "FROM c WHERE CONTAINS(LOWER(c.resource_name), @pattern)"
        )
        params: List[Dict[str, str]] = [
            {"name": "@pattern", "value": name_pattern.lower()},
        ]
        if resource_group:
            query += " AND c.resource_group = @rg"
            params.append({"name": "@rg", "value": resource_group})
        query += " ORDER BY c.resource_group ASC, c.resource_name ASC"
        query += f" OFFSET 0 LIMIT {limit}"
        return QuerySpec(query=query, parameters=params, partition_key=subscription_id)

    # -- 3. Find resources by tag --------------------------------------------
    #    Cosmos indexes all paths by default (/*) so tag lookups use the
    #    automatic range index on /tags/<key>.  Expected cost: 3–6 RU.

    @staticmethod
    def resources_by_tag(
        subscription_id: str,
        tag_key: str,
        tag_value: Optional[str] = None,
        limit: int = 100,
    ) -> QuerySpec:
        """Resources that have tag *tag_key* (optionally matching *tag_value*)."""
        query = (
            "SELECT c.id, c.resource_name, c.resource_type, c.resource_group, "
            "c.location, c.tags "
            "FROM c WHERE IS_DEFINED(c.tags[@tagKey])"
        )
        params: List[Dict[str, str]] = [
            {"name": "@tagKey", "value": tag_key},
        ]
        if tag_value is not None:
            query = (
                "SELECT c.id, c.resource_name, c.resource_type, c.resource_group, "
                "c.location, c.tags "
                "FROM c WHERE c.tags[@tagKey] = @tagVal"
            )
            params.append({"name": "@tagVal", "value": tag_value})
        query += f" OFFSET 0 LIMIT {limit}"
        return QuerySpec(query=query, parameters=params, partition_key=subscription_id)

    # -- 4. Get relationships for a resource ---------------------------------
    #    Point-read by id within the partition.  Expected cost: 1 RU.

    @staticmethod
    def resource_relationships(
        subscription_id: str,
        resource_doc_id: str,
    ) -> QuerySpec:
        """Fetch relationship data for a single resource document."""
        query = (
            "SELECT c.id, c.resource_name, c.resource_type, "
            "c.relationships, c.selected_properties "
            "FROM c WHERE c.id = @docId"
        )
        params = [{"name": "@docId", "value": resource_doc_id}]
        return QuerySpec(query=query, parameters=params, partition_key=subscription_id)

    # -- 5. Resources by type and location (multi-filter) --------------------
    #    Directly leverages composite index [/subscription_id, /resource_type, /location].
    #    Expected cost: 2–4 RU.

    @staticmethod
    def resources_by_type_and_location(
        subscription_id: str,
        resource_type: str,
        location: str,
        limit: int = 100,
    ) -> QuerySpec:
        """Resources matching both type and location within a subscription."""
        query = (
            "SELECT c.id, c.resource_name, c.resource_group, c.tags, "
            "c.selected_properties "
            "FROM c WHERE c.resource_type = @rtype AND c.location = @loc"
            " ORDER BY c.resource_type ASC, c.location ASC"
            f" OFFSET 0 LIMIT {limit}"
        )
        params = [
            {"name": "@rtype", "value": resource_type.lower()},
            {"name": "@loc", "value": location},
        ]
        return QuerySpec(query=query, parameters=params, partition_key=subscription_id)

    # -- 6. Resource count by type (aggregation) -----------------------------
    #    Expected cost: 3–5 RU.

    @staticmethod
    def resource_counts_by_type(subscription_id: str) -> QuerySpec:
        """Aggregate resource counts grouped by type."""
        query = (
            "SELECT c.resource_type, COUNT(1) AS cnt "
            "FROM c GROUP BY c.resource_type"
        )
        return QuerySpec(query=query, parameters=[], partition_key=subscription_id)

    # -- 7. Recently updated resources ----------------------------------------
    #    Expected cost: 3–5 RU.

    @staticmethod
    def recently_updated(
        subscription_id: str,
        since_iso: str,
        limit: int = 50,
    ) -> QuerySpec:
        """Resources updated after *since_iso* timestamp."""
        query = (
            "SELECT c.id, c.resource_name, c.resource_type, c.location, c.last_seen "
            "FROM c WHERE c.last_seen >= @since"
            f" OFFSET 0 LIMIT {limit}"
        )
        params = [{"name": "@since", "value": since_iso}]
        return QuerySpec(query=query, parameters=params, partition_key=subscription_id)


# Module-level singleton
optimised_queries = OptimisedQueries()


# ---------------------------------------------------------------------------
# Benchmark runner
# ---------------------------------------------------------------------------

@dataclass
class BenchmarkResult:
    """Result of a single benchmark query execution."""

    query_name: str
    request_charge_ru: float = 0.0
    latency_ms: float = 0.0
    items_returned: int = 0
    meets_target: bool = False  # target: < 10 RU
    error: Optional[str] = None


class QueryBenchmark:
    """Execute benchmark queries against a live Cosmos container and report RU costs.

    Usage::

        bench = QueryBenchmark(container)
        report = bench.run_all("sub-123")
        for r in report:
            print(f"{r.query_name}: {r.request_charge_ru} RU ({r.latency_ms:.0f} ms)")
    """

    RU_TARGET = 10.0  # maximum acceptable RU per query

    def __init__(self, container: Any) -> None:
        self._container = container

    def _execute(self, name: str, spec: QuerySpec) -> BenchmarkResult:
        """Run a single query and capture RU charge + latency."""
        result = BenchmarkResult(query_name=name)
        try:
            start = time.perf_counter()
            kwargs = spec.to_kwargs()
            kwargs["populate_query_metrics"] = True

            items_iter = self._container.query_items(**kwargs)
            items = list(items_iter)

            result.latency_ms = (time.perf_counter() - start) * 1000
            result.items_returned = len(items)

            # Extract RU charge from response headers
            last_headers = getattr(items_iter, "response_headers", None)
            if last_headers and "x-ms-request-charge" in last_headers:
                result.request_charge_ru = float(last_headers["x-ms-request-charge"])
            elif hasattr(items_iter, "get_response_headers"):
                hdrs = items_iter.get_response_headers()
                if hdrs and "x-ms-request-charge" in hdrs:
                    result.request_charge_ru = float(hdrs["x-ms-request-charge"])

            result.meets_target = result.request_charge_ru < self.RU_TARGET
        except Exception as exc:
            result.error = str(exc)
            result.latency_ms = (time.perf_counter() - start) * 1000
            logger.warning("Benchmark '%s' failed: %s", name, exc)

        return result

    def run_all(self, subscription_id: str) -> List[BenchmarkResult]:
        """Run the standard benchmark suite and return results.

        Queries executed:
          1. Find all VMs in subscription
          2. Find resources by name pattern
          3. Find resources by tag (environment=prod)
          4. Get relationships for a resource
          5. Resources by type + location
          6. Resource counts by type
          7. Recently updated resources
        """
        queries: List[tuple[str, QuerySpec]] = [
            ("find_all_vms", optimised_queries.vms_in_subscription(subscription_id)),
            ("find_by_name_pattern", optimised_queries.resources_by_name(subscription_id, "web")),
            ("find_by_tag", optimised_queries.resources_by_tag(subscription_id, "environment", "prod")),
            ("get_relationships", optimised_queries.resource_relationships(subscription_id, "sample-doc-id")),
            ("type_and_location", optimised_queries.resources_by_type_and_location(
                subscription_id, "microsoft.compute/virtualmachines", "eastus")),
            ("counts_by_type", optimised_queries.resource_counts_by_type(subscription_id)),
            ("recently_updated", optimised_queries.recently_updated(subscription_id, "2026-01-01T00:00:00Z")),
        ]

        results: List[BenchmarkResult] = []
        for name, spec in queries:
            r = self._execute(name, spec)
            results.append(r)
            status = "✅" if r.meets_target else ("⚠️" if r.error is None else "❌")
            logger.info(
                "%s %s: %.2f RU, %d items, %.0f ms",
                status, name, r.request_charge_ru, r.items_returned, r.latency_ms,
            )

        return results

    @staticmethod
    def summary(results: List[BenchmarkResult]) -> Dict[str, Any]:
        """Generate a summary report from benchmark results."""
        successful = [r for r in results if r.error is None]
        failed = [r for r in results if r.error is not None]
        meeting_target = [r for r in successful if r.meets_target]

        return {
            "total_queries": len(results),
            "successful": len(successful),
            "failed": len(failed),
            "meeting_ru_target": len(meeting_target),
            "ru_target": QueryBenchmark.RU_TARGET,
            "avg_ru": (
                round(sum(r.request_charge_ru for r in successful) / len(successful), 2)
                if successful else 0.0
            ),
            "max_ru": (
                round(max(r.request_charge_ru for r in successful), 2)
                if successful else 0.0
            ),
            "avg_latency_ms": (
                round(sum(r.latency_ms for r in successful) / len(successful), 1)
                if successful else 0.0
            ),
            "details": [
                {
                    "query": r.query_name,
                    "ru": round(r.request_charge_ru, 2),
                    "latency_ms": round(r.latency_ms, 1),
                    "items": r.items_returned,
                    "meets_target": r.meets_target,
                    "error": r.error,
                }
                for r in results
            ],
            "recommendations": _generate_recommendations(results),
        }


# ---------------------------------------------------------------------------
# Query cost estimation (offline, no live DB needed)
# ---------------------------------------------------------------------------

# Estimated RU costs based on Cosmos DB pricing model:
#   - Point read: ~1 RU per 1 KB document
#   - Index-seek query (single partition): ~2.5 RU base + 0.5 RU per 1 KB returned
#   - Cross-partition query: add ~3 RU per partition touched
#   - CONTAINS / string scan: ~5–8 RU (depends on partition data size)
#   - Aggregation (GROUP BY): ~3–5 RU

ESTIMATED_RU_COSTS: Dict[str, Dict[str, Any]] = {
    "find_all_vms": {
        "description": "All VMs in subscription (single partition, composite index seek)",
        "estimated_ru": "2–5 RU",
        "index_used": "[/resource_type, /location]",
        "strategy": "Partition-scoped + composite index ORDER BY eliminates sort cost",
    },
    "find_by_name_pattern": {
        "description": "Resources matching name pattern (CONTAINS scan within partition)",
        "estimated_ru": "3–8 RU",
        "index_used": "[/resource_group, /resource_name] for ORDER BY",
        "strategy": "CONTAINS requires scan but partition-scoping keeps cost low",
    },
    "find_by_tag": {
        "description": "Resources with specific tag key/value",
        "estimated_ru": "3–6 RU",
        "index_used": "Automatic range index on /tags/*",
        "strategy": "Single-partition equality filter on tag value",
    },
    "get_relationships": {
        "description": "Single resource by document ID (point-read equivalent)",
        "estimated_ru": "1 RU",
        "index_used": "Primary index (id within partition)",
        "strategy": "Effectively a point read – lowest possible cost",
    },
    "type_and_location": {
        "description": "Resources by type + location (triple composite index)",
        "estimated_ru": "2–4 RU",
        "index_used": "[/subscription_id, /resource_type, /location]",
        "strategy": "Full composite index seek – most efficient multi-filter query",
    },
    "counts_by_type": {
        "description": "Aggregate counts grouped by resource type",
        "estimated_ru": "3–5 RU",
        "index_used": "Range index on /resource_type",
        "strategy": "Server-side GROUP BY avoids transferring individual documents",
    },
    "recently_updated": {
        "description": "Resources updated since a given timestamp",
        "estimated_ru": "3–5 RU",
        "index_used": "Range index on /last_seen",
        "strategy": "Range filter within single partition, OFFSET/LIMIT pagination",
    },
}


def _generate_recommendations(results: List[BenchmarkResult]) -> List[str]:
    """Generate optimisation recommendations based on benchmark results."""
    recommendations: List[str] = []

    over_target = [r for r in results if r.error is None and not r.meets_target]
    if not over_target:
        recommendations.append("All queries are within the 10 RU target – no changes needed.")
        return recommendations

    for r in over_target:
        if "name" in r.query_name.lower():
            recommendations.append(
                f"'{r.query_name}' ({r.request_charge_ru:.1f} RU): Consider adding a "
                "computed lowercase_name field and an equality index instead of CONTAINS."
            )
        elif "tag" in r.query_name.lower():
            recommendations.append(
                f"'{r.query_name}' ({r.request_charge_ru:.1f} RU): Add a composite index "
                "[/tags/<common_key>, /resource_type] for frequently-queried tag keys."
            )
        else:
            recommendations.append(
                f"'{r.query_name}' ({r.request_charge_ru:.1f} RU): Review SELECT projection "
                "to return fewer fields, or add tighter OFFSET/LIMIT."
            )

    return recommendations
