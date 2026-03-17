"""
Performance tests for In-Memory Join fixes (BH-017 through BH-023).

Each test runs EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT) on the Phase 8-9
replacement query that moved Python-side joins into SQL JOINs or MVs.

Asserts:
  1. Execution time within threshold tier.
  2. Index usage where applicable.

Requires: DATABASE_URL env var, pg_pool and seed_performance_data fixtures
from conftest.py, helpers from helpers.py.
"""
from __future__ import annotations

import pytest

try:
    import asyncpg
except ImportError:
    asyncpg = None  # type: ignore[assignment]

from tests.performance.helpers import (
    SMALL_MV_NAMES,
    THRESHOLD_DASHBOARD_MS,
    THRESHOLD_DETAIL_MS,
    THRESHOLD_LIST_MS,
    parse_explain_output,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.performance]


# ------------------------------------------------------------------ #
# Seeded data constants (aligned with conftest._SCAN_ID, _SUB_IDS)
# ------------------------------------------------------------------ #
_SCAN_ID = "perf-test-scan-001"
_SUB_ID_ALPHA = "aaaaaaaa-0000-0000-0000-000000000001"
_VM_RESOURCE_ID_0 = (
    f"/subscriptions/{_SUB_ID_ALPHA}/resourceGroups/rg-perf/"
    "providers/Microsoft.Compute/virtualMachines/vm-perf-000"
)


# ------------------------------------------------------------------ #
# BH-017: CVE-VM matches with SQL JOIN (not Python join)
# ------------------------------------------------------------------ #
async def test_bh017_cve_vm_matches_joined(pg_pool, seed_performance_data, explain):
    """BH-017 fix: vm_cve_match_rows JOIN vms done in SQL, not Python."""
    try:
        result = await explain(
            """SELECT m.scan_id, m.vm_id, m.vm_name, m.cve_id, m.severity,
                      m.cvss_score, m.patch_status, m.kb_ids,
                      v.os_name, v.os_type
               FROM vm_cve_match_rows m
               JOIN vms v ON v.resource_id = m.vm_id
               WHERE m.scan_id = $1 AND m.cve_id = $2""",
            [_SCAN_ID, "CVE-2024-0001"],
        )
    except Exception as exc:
        if asyncpg and isinstance(exc, asyncpg.UndefinedTableError):
            pytest.skip("vm_cve_match_rows or vms table not found")
        raise

    assert result["execution_time_ms"] is not None
    assert result["execution_time_ms"] < THRESHOLD_LIST_MS, (
        f"CVE-VM match join too slow: {result['execution_time_ms']:.1f}ms "
        f"(threshold {THRESHOLD_LIST_MS}ms)"
    )
    # Should use idx_vmcvematch_cve_scan
    plan_lower = result["plan_text"].lower()
    has_expected_index = (
        result["uses_index_scan"]
        or "idx_vmcvematch_cve_scan" in plan_lower
    )
    assert has_expected_index, (
        f"Expected index scan via idx_vmcvematch_cve_scan, got:\n{result['plan_text']}"
    )


# ------------------------------------------------------------------ #
# BH-018: Inventory OS counts from MV (replaces 3-query Python aggregation)
# ------------------------------------------------------------------ #
async def test_bh018_inventory_os_counts_mv(pg_pool, seed_performance_data, explain):
    """BH-018 fix: OS counts from mv_inventory_os_cve_counts MV (not Python)."""
    try:
        result = await explain(
            "SELECT * FROM mv_inventory_os_cve_counts"
        )
    except Exception as exc:
        if asyncpg and isinstance(exc, asyncpg.UndefinedTableError):
            pytest.skip("mv_inventory_os_cve_counts not found")
        raise

    assert result["execution_time_ms"] is not None
    assert result["execution_time_ms"] < THRESHOLD_DASHBOARD_MS, (
        f"Inventory OS counts MV too slow: {result['execution_time_ms']:.1f}ms "
        f"(threshold {THRESHOLD_DASHBOARD_MS}ms)"
    )
    # Small MV -- Seq Scan is acceptable


# ------------------------------------------------------------------ #
# BH-019: VM CVE detail from MV (replaces Python-side join)
# ------------------------------------------------------------------ #
async def test_bh019_vm_cve_detail_mv(pg_pool, seed_performance_data, explain):
    """BH-019 fix: VM CVE detail from mv_vm_cve_detail MV."""
    try:
        result = await explain(
            """SELECT * FROM mv_vm_cve_detail
               WHERE scan_id = $1 AND vm_id = $2""",
            [_SCAN_ID, _VM_RESOURCE_ID_0],
        )
    except Exception as exc:
        if asyncpg and isinstance(exc, asyncpg.UndefinedTableError):
            pytest.skip("mv_vm_cve_detail not found")
        raise

    assert result["execution_time_ms"] is not None
    assert result["execution_time_ms"] < THRESHOLD_LIST_MS, (
        f"VM CVE detail MV too slow: {result['execution_time_ms']:.1f}ms "
        f"(threshold {THRESHOLD_LIST_MS}ms)"
    )
    plan_lower = result["plan_text"].lower()
    has_expected_index = (
        result["uses_index_scan"]
        or "mv_vm_cve_detail_scan_vm_cve_idx" in plan_lower
    )
    assert has_expected_index, (
        f"Expected mv_vm_cve_detail_scan_vm_cve_idx, got:\n{result['plan_text']}"
    )


# ------------------------------------------------------------------ #
# BH-020: CVE exposure from MV (replaces Python aggregation)
# ------------------------------------------------------------------ #
async def test_bh020_cve_exposure_mv(pg_pool, seed_performance_data, explain):
    """BH-020 fix: CVE exposure from mv_cve_exposure MV with severity filter."""
    try:
        result = await explain(
            """SELECT * FROM mv_cve_exposure
               WHERE severity = $1
               ORDER BY affected_vms DESC
               LIMIT 10""",
            ["CRITICAL"],
        )
    except Exception as exc:
        if asyncpg and isinstance(exc, asyncpg.UndefinedTableError):
            pytest.skip("mv_cve_exposure not found")
        raise

    assert result["execution_time_ms"] is not None
    assert result["execution_time_ms"] < THRESHOLD_LIST_MS, (
        f"CVE exposure MV too slow: {result['execution_time_ms']:.1f}ms "
        f"(threshold {THRESHOLD_LIST_MS}ms)"
    )
    plan_lower = result["plan_text"].lower()
    has_expected_index = (
        result["uses_index_scan"]
        or "mv_cve_exposure_severity_affected_idx" in plan_lower
    )
    assert has_expected_index, (
        f"Expected mv_cve_exposure_severity_affected_idx, got:\n{result['plan_text']}"
    )


# ------------------------------------------------------------------ #
# BH-021: Alert history with rule name JOIN
# ------------------------------------------------------------------ #
async def test_bh021_alert_history_joined(pg_pool, seed_performance_data, explain):
    """BH-021 fix: alert history JOINed with rules in SQL (not Python)."""
    try:
        result = await explain(
            """SELECT h.*, r.rule_name
               FROM cve_alert_history h
               JOIN cve_alert_rules r ON r.rule_id = h.rule_id
               ORDER BY h.fired_at DESC
               LIMIT 20"""
        )
    except Exception as exc:
        if asyncpg and isinstance(exc, asyncpg.UndefinedTableError):
            pytest.skip("cve_alert_history or cve_alert_rules table not found")
        raise

    assert result["execution_time_ms"] is not None
    assert result["execution_time_ms"] < THRESHOLD_LIST_MS, (
        f"Alert history join too slow: {result['execution_time_ms']:.1f}ms "
        f"(threshold {THRESHOLD_LIST_MS}ms)"
    )


# ------------------------------------------------------------------ #
# BH-022: KB-CVE edge lookup (indexed by cve_id)
# ------------------------------------------------------------------ #
async def test_bh022_kb_cve_edge_lookup(pg_pool, seed_performance_data, explain):
    """BH-022 fix: KB-CVE edge lookup uses idx_edges_cve."""
    try:
        result = await explain(
            "SELECT * FROM kb_cve_edges WHERE cve_id = $1",
            ["CVE-2024-0001"],
        )
    except Exception as exc:
        if asyncpg and isinstance(exc, asyncpg.UndefinedTableError):
            pytest.skip("kb_cve_edges table not found")
        raise

    assert result["execution_time_ms"] is not None
    assert result["execution_time_ms"] < THRESHOLD_DETAIL_MS, (
        f"KB-CVE edge lookup too slow: {result['execution_time_ms']:.1f}ms "
        f"(threshold {THRESHOLD_DETAIL_MS}ms)"
    )
    plan_lower = result["plan_text"].lower()
    has_expected_index = (
        result["uses_index_scan"]
        or "idx_edges_cve" in plan_lower
        or "idx_edges_cve_source" in plan_lower
    )
    assert has_expected_index, (
        f"Expected idx_edges_cve or idx_edges_cve_source, got:\n{result['plan_text']}"
    )


# ------------------------------------------------------------------ #
# BH-023: VM posture by subscription (MV indexed)
# ------------------------------------------------------------------ #
async def test_bh023_vm_posture_by_subscription(
    pg_pool, seed_performance_data, explain
):
    """BH-023 fix: VM posture by subscription uses MV index."""
    try:
        result = await explain(
            """SELECT * FROM mv_vm_vulnerability_posture
               WHERE subscription_id = $1::uuid""",
            [_SUB_ID_ALPHA],
        )
    except Exception as exc:
        if asyncpg and isinstance(exc, asyncpg.UndefinedTableError):
            pytest.skip("mv_vm_vulnerability_posture not found")
        raise

    assert result["execution_time_ms"] is not None
    assert result["execution_time_ms"] < THRESHOLD_LIST_MS, (
        f"VM posture by subscription too slow: {result['execution_time_ms']:.1f}ms "
        f"(threshold {THRESHOLD_LIST_MS}ms)"
    )
    plan_lower = result["plan_text"].lower()
    has_expected_index = (
        result["uses_index_scan"]
        or "mv_vm_vulnerability_posture_sub_rg_idx" in plan_lower
    )
    assert has_expected_index, (
        f"Expected mv_vm_vulnerability_posture_sub_rg_idx, got:\n{result['plan_text']}"
    )
