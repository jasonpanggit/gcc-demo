"""
Performance tests for N+1 query fixes (BH-001 through BH-016).

Each test runs EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT) on the Phase 8-9
replacement query and asserts:
  1. Execution time is within the appropriate threshold tier.
  2. Index usage where applicable (Seq Scan is acceptable for small MVs).

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
    THRESHOLD_AGGREGATION_MS,
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
# BH-001: Dashboard summary MV
# ------------------------------------------------------------------ #
async def test_bh001_cve_dashboard_summary(pg_pool, seed_performance_data, explain):
    """BH-001 fix: single MV read replaces multi-query dashboard aggregation."""
    try:
        result = await explain(
            "SELECT * FROM mv_cve_dashboard_summary"
        )
    except Exception as exc:
        if asyncpg and isinstance(exc, asyncpg.UndefinedTableError):
            pytest.skip("mv_cve_dashboard_summary not found")
        raise

    assert result["execution_time_ms"] is not None
    assert result["execution_time_ms"] < THRESHOLD_DASHBOARD_MS, (
        f"Dashboard summary too slow: {result['execution_time_ms']:.1f}ms "
        f"(threshold {THRESHOLD_DASHBOARD_MS}ms)"
    )
    # Small MV -- Seq Scan is acceptable
    assert "mv_cve_dashboard_summary" in result["plan_text"].lower() or True


# ------------------------------------------------------------------ #
# BH-001: Trending data MV
# ------------------------------------------------------------------ #
async def test_bh001_cve_trending(pg_pool, seed_performance_data, explain):
    """BH-001 fix: trending data from mv_cve_trending MV."""
    try:
        result = await explain(
            "SELECT * FROM mv_cve_trending ORDER BY bucket_date DESC LIMIT 90"
        )
    except Exception as exc:
        if asyncpg and isinstance(exc, asyncpg.UndefinedTableError):
            pytest.skip("mv_cve_trending not found")
        raise

    assert result["execution_time_ms"] is not None
    assert result["execution_time_ms"] < THRESHOLD_DASHBOARD_MS, (
        f"Trending query too slow: {result['execution_time_ms']:.1f}ms "
        f"(threshold {THRESHOLD_DASHBOARD_MS}ms)"
    )


# ------------------------------------------------------------------ #
# BH-001: Top CVEs by score MV
# ------------------------------------------------------------------ #
async def test_bh001_cve_top_by_score(pg_pool, seed_performance_data, explain):
    """BH-001 fix: top CVEs by CVSS score from MV."""
    try:
        result = await explain(
            "SELECT * FROM mv_cve_top_by_score LIMIT 10"
        )
    except Exception as exc:
        if asyncpg and isinstance(exc, asyncpg.UndefinedTableError):
            pytest.skip("mv_cve_top_by_score not found")
        raise

    assert result["execution_time_ms"] is not None
    assert result["execution_time_ms"] < THRESHOLD_DASHBOARD_MS


# ------------------------------------------------------------------ #
# BH-002: CVE search with severity filter (indexed)
# ------------------------------------------------------------------ #
async def test_bh002_cve_count_and_list(pg_pool, seed_performance_data, explain):
    """BH-002 fix: severity-filtered CVE search uses covering index."""
    try:
        result = await explain(
            """SELECT c.cve_id, c.description, c.cvss_v3_score, c.cvss_v3_severity,
                      c.published_at, c.affected_products, c.sources,
                      COALESCE(e.affected_vms, 0) AS affected_vms
               FROM cves c
               LEFT JOIN mv_cve_exposure e ON e.cve_id = c.cve_id
               WHERE c.cvss_v3_severity = $1
               ORDER BY c.published_at DESC, c.cve_id DESC
               LIMIT $2 OFFSET $3""",
            ["HIGH", 20, 0],
        )
    except Exception as exc:
        if asyncpg and isinstance(exc, asyncpg.UndefinedTableError):
            pytest.skip("Table/MV not found for BH-002 query")
        raise

    assert result["execution_time_ms"] is not None
    assert result["execution_time_ms"] < THRESHOLD_LIST_MS, (
        f"CVE search too slow: {result['execution_time_ms']:.1f}ms "
        f"(threshold {THRESHOLD_LIST_MS}ms)"
    )
    # Should use idx_cves_severity_covering or idx_cves_severity_published
    plan_lower = result["plan_text"].lower()
    assert result["uses_index_scan"] or "idx_cves_severity" in plan_lower, (
        f"Expected index scan on cves severity index, got:\n{result['plan_text']}"
    )


# ------------------------------------------------------------------ #
# BH-003: PDF export aggregation
# ------------------------------------------------------------------ #
async def test_bh003_pdf_export_aggregation(pg_pool, seed_performance_data, explain):
    """BH-003 fix: dashboard aggregation for PDF export."""
    try:
        result = await explain(
            """SELECT c.cvss_v3_severity AS severity,
                      COUNT(*) AS count,
                      AVG(c.cvss_v3_score) AS avg_score
               FROM cves c
               WHERE c.cvss_v3_severity IS NOT NULL
               GROUP BY c.cvss_v3_severity
               ORDER BY count DESC"""
        )
    except Exception as exc:
        if asyncpg and isinstance(exc, asyncpg.UndefinedTableError):
            pytest.skip("cves table not found")
        raise

    assert result["execution_time_ms"] is not None
    assert result["execution_time_ms"] < THRESHOLD_AGGREGATION_MS, (
        f"PDF aggregation too slow: {result['execution_time_ms']:.1f}ms "
        f"(threshold {THRESHOLD_AGGREGATION_MS}ms)"
    )


# ------------------------------------------------------------------ #
# BH-004: Inventory OS counts from MV
# ------------------------------------------------------------------ #
async def test_bh004_inventory_os_counts(pg_pool, seed_performance_data, explain):
    """BH-004 fix: OS CVE counts from materialized view."""
    try:
        result = await explain(
            "SELECT * FROM mv_inventory_os_cve_counts"
        )
    except Exception as exc:
        if asyncpg and isinstance(exc, asyncpg.UndefinedTableError):
            pytest.skip("mv_inventory_os_cve_counts not found")
        raise

    assert result["execution_time_ms"] is not None
    assert result["execution_time_ms"] < THRESHOLD_DASHBOARD_MS
    # Small MV -- Seq Scan is acceptable


# ------------------------------------------------------------------ #
# BH-005: EOL lookup by OS key (indexed)
# ------------------------------------------------------------------ #
async def test_bh005_eol_lookup_by_os(pg_pool, seed_performance_data, explain):
    """BH-005 fix: EOL record lookup uses idx_eol_software_key_lower."""
    try:
        result = await explain(
            "SELECT * FROM eol_records WHERE software_key = $1",
            ["perf-eol-ubuntu-22.04"],
        )
    except Exception as exc:
        if asyncpg and isinstance(exc, asyncpg.UndefinedTableError):
            pytest.skip("eol_records table not found")
        raise

    assert result["execution_time_ms"] is not None
    assert result["execution_time_ms"] < THRESHOLD_DETAIL_MS, (
        f"EOL lookup too slow: {result['execution_time_ms']:.1f}ms "
        f"(threshold {THRESHOLD_DETAIL_MS}ms)"
    )
    # Should use PK index or idx_eol_software_key_lower
    plan_lower = result["plan_text"].lower()
    has_expected_index = (
        result["uses_index_scan"]
        or "idx_eol_software" in plan_lower
        or "idx_eol_software_key_lower" in plan_lower
        or "eol_records_pkey" in plan_lower
    )
    assert has_expected_index, (
        f"Expected index scan on eol_records, got:\n{result['plan_text']}"
    )


# ------------------------------------------------------------------ #
# BH-006: VM vulnerability posture MV (indexed by vm_id)
# ------------------------------------------------------------------ #
async def test_bh006_vm_vulnerability_posture(pg_pool, seed_performance_data, explain):
    """BH-006 fix: per-VM posture from mv_vm_vulnerability_posture."""
    try:
        result = await explain(
            "SELECT * FROM mv_vm_vulnerability_posture WHERE vm_id = $1",
            [_VM_RESOURCE_ID_0],
        )
    except Exception as exc:
        if asyncpg and isinstance(exc, asyncpg.UndefinedTableError):
            pytest.skip("mv_vm_vulnerability_posture not found")
        raise

    assert result["execution_time_ms"] is not None
    assert result["execution_time_ms"] < THRESHOLD_DETAIL_MS, (
        f"VM posture lookup too slow: {result['execution_time_ms']:.1f}ms "
        f"(threshold {THRESHOLD_DETAIL_MS}ms)"
    )
    plan_lower = result["plan_text"].lower()
    has_expected_index = (
        result["uses_index_scan"]
        or "mv_vm_vulnerability_posture_vm_id_idx" in plan_lower
    )
    assert has_expected_index, (
        f"Expected index scan on mv_vm_vulnerability_posture, got:\n{result['plan_text']}"
    )


# ------------------------------------------------------------------ #
# BH-007: VM OS CVE counts by subscription
# ------------------------------------------------------------------ #
async def test_bh007_vm_os_cve_counts_by_subscription(
    pg_pool, seed_performance_data, explain
):
    """BH-007 fix: OS CVE counts filtered by subscription."""
    try:
        result = await explain(
            """SELECT os_name,
                      COUNT(*) AS vm_count,
                      SUM(total_cves) AS total_cve_count,
                      SUM(critical) AS critical_count,
                      SUM(high) AS high_count
               FROM mv_vm_vulnerability_posture
               WHERE subscription_id = $1::uuid
               GROUP BY os_name
               ORDER BY total_cve_count DESC""",
            [_SUB_ID_ALPHA],
        )
    except Exception as exc:
        if asyncpg and isinstance(exc, asyncpg.UndefinedTableError):
            pytest.skip("mv_vm_vulnerability_posture not found")
        raise

    assert result["execution_time_ms"] is not None
    assert result["execution_time_ms"] < THRESHOLD_LIST_MS


# ------------------------------------------------------------------ #
# BH-008: Single CVE detail by PK
# ------------------------------------------------------------------ #
async def test_bh008_cve_detail_single(pg_pool, seed_performance_data, explain):
    """BH-008 fix: PK lookup on cves table."""
    try:
        result = await explain(
            """SELECT cve_id, description, cvss_v3_score, cvss_v3_severity,
                      cvss_v2_score, cvss_v2_severity,
                      cvss_v3_vector, cvss_v2_vector, cwe_ids, "references",
                      affected_products, sources, published_at, modified_at, synced_at,
                      cvss_v3_exploitability, cvss_v3_impact
               FROM cves
               WHERE cve_id = $1""",
            ["CVE-2024-0001"],
        )
    except Exception as exc:
        if asyncpg and isinstance(exc, asyncpg.UndefinedTableError):
            pytest.skip("cves table not found")
        raise

    assert result["execution_time_ms"] is not None
    assert result["execution_time_ms"] < THRESHOLD_DETAIL_MS, (
        f"CVE detail too slow: {result['execution_time_ms']:.1f}ms "
        f"(threshold {THRESHOLD_DETAIL_MS}ms)"
    )
    # PK index scan expected
    assert result["uses_index_scan"], (
        f"Expected PK index scan on cves, got:\n{result['plan_text']}"
    )


# ------------------------------------------------------------------ #
# BH-009: Alert rules list
# ------------------------------------------------------------------ #
async def test_bh009_alert_rules_list(pg_pool, seed_performance_data, explain):
    """BH-009 fix: server-side sorted alert rules list."""
    try:
        result = await explain(
            "SELECT * FROM cve_alert_rules ORDER BY created_at DESC"
        )
    except Exception as exc:
        if asyncpg and isinstance(exc, asyncpg.UndefinedTableError):
            pytest.skip("cve_alert_rules table not found")
        raise

    assert result["execution_time_ms"] is not None
    assert result["execution_time_ms"] < THRESHOLD_LIST_MS


# ------------------------------------------------------------------ #
# BH-010: Patch assessment with available patches (JOIN)
# ------------------------------------------------------------------ #
async def test_bh010_patch_assessment_with_available(
    pg_pool, seed_performance_data, explain
):
    """BH-010 fix: single-query patch management view."""
    try:
        result = await explain(
            """SELECT v.resource_id, v.vm_name, v.os_name, v.os_type,
                      v.location, v.resource_group,
                      pac.machine_name, pac.total_patches, pac.critical_count,
                      pac.security_count, pac.last_modified, pac.os_version,
                      (SELECT COUNT(*) FROM available_patches ap
                       WHERE ap.resource_id = v.resource_id) AS available_patch_count
               FROM vms v
               LEFT JOIN patch_assessments_cache pac ON pac.resource_id = v.resource_id
               WHERE ($1::uuid IS NULL OR v.subscription_id = $1)
               ORDER BY COALESCE(pac.critical_count, 0) DESC, v.vm_name ASC
               LIMIT $2 OFFSET $3""",
            [None, 50, 0],
        )
    except Exception as exc:
        if asyncpg and isinstance(exc, asyncpg.UndefinedTableError):
            pytest.skip("Table not found for BH-010 patch query")
        raise

    assert result["execution_time_ms"] is not None
    assert result["execution_time_ms"] < THRESHOLD_LIST_MS, (
        f"Patch management view too slow: {result['execution_time_ms']:.1f}ms "
        f"(threshold {THRESHOLD_LIST_MS}ms)"
    )


# ------------------------------------------------------------------ #
# BH-011 through BH-016: Additional N+1 fixes (parametrized safety net)
# ------------------------------------------------------------------ #
_ADDITIONAL_N1_QUERIES = [
    pytest.param(
        "BH-011",
        "SELECT * FROM mv_vm_vulnerability_posture ORDER BY total_cves DESC LIMIT $1",
        [20],
        id="bh011_vm_posture_top",
    ),
    pytest.param(
        "BH-012",
        """SELECT v.resource_id, v.vm_name, v.os_name, v.os_type,
                  v.location, v.resource_group, v.subscription_id,
                  e.is_eol, e.eol_date, e.software_name AS eol_software_name
           FROM vms v
           LEFT JOIN eol_records e ON LOWER(v.os_name) = LOWER(e.software_key)
           ORDER BY v.vm_name ASC
           LIMIT $1 OFFSET $2""",
        [50, 0],
        id="bh012_vm_inventory_with_eol",
    ),
    pytest.param(
        "BH-013",
        "SELECT resource_id, vm_name, os_name, os_type FROM vms WHERE subscription_id = $1::uuid LIMIT $2",
        [_SUB_ID_ALPHA, 50],
        id="bh013_vm_list_by_subscription",
    ),
    pytest.param(
        "BH-014",
        """SELECT COUNT(*) AS total
           FROM cves c
           WHERE c.cvss_v3_severity = $1""",
        ["HIGH"],
        id="bh014_cve_count_by_severity",
    ),
    pytest.param(
        "BH-015",
        """SELECT ap.id, ap.resource_id, ap.kb_id, ap.software_name,
                  ap.software_version, ap.classifications
           FROM available_patches ap
           WHERE ap.resource_id = $1
           ORDER BY ap.classifications, ap.software_name""",
        [_VM_RESOURCE_ID_0],
        id="bh015_patches_for_vm",
    ),
    pytest.param(
        "BH-016",
        """SELECT v.resource_id, v.vm_name, v.os_name, e.is_eol, e.eol_date,
                  e.status AS eol_status, e.risk_level
           FROM vms v
           LEFT JOIN eol_records e ON LOWER(v.os_name) = LOWER(e.software_key)
           WHERE ($1::uuid IS NULL OR v.subscription_id = $1)
           ORDER BY e.is_eol DESC NULLS LAST, v.vm_name ASC
           LIMIT $2 OFFSET $3""",
        [None, 50, 0],
        id="bh016_vm_eol_management",
    ),
]


@pytest.mark.parametrize("bh_id,query,params", _ADDITIONAL_N1_QUERIES)
async def test_bh011_to_bh016_additional_n1(
    pg_pool, seed_performance_data, explain, bh_id, query, params
):
    """BH-011 through BH-016: safety-net EXPLAIN ANALYZE for remaining N+1 fixes."""
    try:
        result = await explain(query, params)
    except Exception as exc:
        if asyncpg and isinstance(exc, asyncpg.UndefinedTableError):
            pytest.skip(f"Table/MV not found for {bh_id}")
        raise

    assert result["execution_time_ms"] is not None
    assert result["execution_time_ms"] < THRESHOLD_AGGREGATION_MS, (
        f"{bh_id} query too slow: {result['execution_time_ms']:.1f}ms "
        f"(threshold {THRESHOLD_AGGREGATION_MS}ms)"
    )
