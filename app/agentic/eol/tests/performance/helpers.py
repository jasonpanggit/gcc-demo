"""
Performance test helpers -- EXPLAIN ANALYZE output parser, threshold constants,
and convenience runner for PostgreSQL query plan analysis.

Phase 10: Validation & Cleanup infrastructure consumed by all P10.2+ test files.
"""
from __future__ import annotations

import re
from typing import Optional

# ------------------------------------------------------------------ #
# Performance threshold constants (milliseconds)
# ------------------------------------------------------------------ #
THRESHOLD_DASHBOARD_MS = 100    # Dashboard/hot-path queries
THRESHOLD_LIST_MS = 200         # Paginated list endpoints
THRESHOLD_DETAIL_MS = 50        # Single-record lookups (PK)
THRESHOLD_AGGREGATION_MS = 500  # Analytics, PDF exports, cross-table stats

# ------------------------------------------------------------------ #
# Materialized views small enough that Seq Scan is acceptable
# ------------------------------------------------------------------ #
SMALL_MV_NAMES = {
    "mv_cve_dashboard_summary",
    "mv_cve_trending",
    "mv_inventory_os_cve_counts",
}

# ------------------------------------------------------------------ #
# Regex patterns for EXPLAIN ANALYZE output parsing
# ------------------------------------------------------------------ #
_RE_EXECUTION_TIME = re.compile(r"Execution Time:\s+([\d.]+)\s+ms")
_RE_PLANNING_TIME = re.compile(r"Planning Time:\s+([\d.]+)\s+ms")

_INDEX_SCAN_INDICATORS = ("Index Scan", "Index Only Scan", "Bitmap Index Scan")


def parse_explain_output(plan_text: str) -> dict:
    """Parse PostgreSQL EXPLAIN ANALYZE text output into a structured dict.

    Args:
        plan_text: Raw text output from ``EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)``.

    Returns:
        dict with keys:
            - ``execution_time_ms`` (float | None)
            - ``planning_time_ms`` (float | None)
            - ``uses_index_scan`` (bool)
            - ``has_seq_scan`` (bool)
            - ``plan_text`` (str)
    """
    execution_time_ms: Optional[float] = None
    planning_time_ms: Optional[float] = None

    match_exec = _RE_EXECUTION_TIME.search(plan_text)
    if match_exec:
        execution_time_ms = float(match_exec.group(1))

    match_plan = _RE_PLANNING_TIME.search(plan_text)
    if match_plan:
        planning_time_ms = float(match_plan.group(1))

    uses_index_scan = any(ind in plan_text for ind in _INDEX_SCAN_INDICATORS)
    has_seq_scan = "Seq Scan" in plan_text

    return {
        "execution_time_ms": execution_time_ms,
        "planning_time_ms": planning_time_ms,
        "uses_index_scan": uses_index_scan,
        "has_seq_scan": has_seq_scan,
        "plan_text": plan_text,
    }


async def run_explain_analyze(
    pool,
    query: str,
    params: list = None,
) -> dict:
    """Execute ``EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)`` for *query* and parse results.

    Args:
        pool: An ``asyncpg.Pool`` instance.
        query: The SQL query to analyse (without the EXPLAIN prefix).
        params: Optional positional parameters for the query.

    Returns:
        Parsed dict from :func:`parse_explain_output`.
    """
    explain_query = f"EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT) {query}"

    if params:
        rows = await pool.fetch(explain_query, *params)
    else:
        rows = await pool.fetch(explain_query)

    plan_text = "\n".join(row["QUERY PLAN"] for row in rows)
    return parse_explain_output(plan_text)
