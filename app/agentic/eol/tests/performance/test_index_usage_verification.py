"""
Index existence and usage verification tests.

Validates that all Phase 6 indexes, materialized views, functions, triggers,
and FK constraints created by pg_database.py bootstrap DDL are present
in the runtime PostgreSQL schema.

Requires: DATABASE_URL env var, pg_pool from conftest.py.
"""
from __future__ import annotations

import pytest

try:
    import asyncpg
except ImportError:
    asyncpg = None  # type: ignore[assignment]

pytestmark = [pytest.mark.asyncio, pytest.mark.performance]


# ------------------------------------------------------------------ #
# Expected indexes from pg_database.py bootstrap DDL
# ------------------------------------------------------------------ #
EXPECTED_INDEXES = {
    "cves": {
        "idx_cves_cvss3",
        "idx_cves_published",
        "idx_cves_sources",
        "idx_cves_products",
        "idx_cves_fts",
        "idx_cves_severity",
        "idx_cves_severity_published",
        "idx_cves_severity_score",
        "idx_cves_high_severity",
        "idx_cves_severity_covering",
    },
    "kb_cve_edges": {
        "idx_edges_cve",
        "idx_edges_cve_source",
    },
    "cve_scans": {
        "idx_cve_scans_status_completed",
        "idx_scans_completed",
    },
    "subscriptions": {
        "idx_subscriptions_name",
        "idx_subscriptions_tenant",
    },
    "vms": {
        "idx_vms_subscription",
        "idx_vms_os_name",
        "idx_vms_os_type",
        "idx_vms_location",
        "idx_vms_resource_group",
        "idx_vms_tags",
        "idx_vms_last_synced",
        "idx_vms_os_name_lower",
        "idx_vms_subscription_os",
    },
    "vm_cve_match_rows": {
        "idx_vmcvematch_scan_severity",
        "idx_vmcvematch_cve_scan",
        "idx_vmcvematch_vm_scan",
        "idx_vmcvematch_kb_ids",
    },
    "resource_inventory": {
        "idx_inventory_sub",
        "idx_inventory_sub_lower_type",
        "idx_resource_inventory_normalized_os",
        "idx_resource_inventory_name_lower",
        "idx_resource_inventory_normalized",
        "idx_resource_inventory_eol_date",
        "idx_resource_inventory_type_eol",
    },
    "os_inventory_snapshots": {
        "idx_os_inventory_snapshots_resource_id",
        "idx_os_inventory_computer_name_lower",
    },
    "inventory_vm_metadata": {
        "idx_invmeta_sub_rg",
        "idx_invmeta_vmtype_ostype",
        "idx_invmeta_last_synced",
    },
    "patch_assessments_cache": {
        "idx_patch_cache_resource_id",
        "idx_patchcache_resource_lastmod",
    },
    "available_patches": {
        "idx_patches_resource_id",
    },
    "arc_software_inventory": {
        "idx_arc_sw_inventory_resource_id",
    },
    "cve_vm_detections": {
        "idx_cve_vm_resource_id",
        "idx_cve_vm_cve_id",
    },
    "eol_records": {
        "idx_eol_software",
        "idx_eol_status",
        "idx_eol_item_type",
        "idx_eol_normalized",
        "idx_eol_software_key_lower",
    },
    "eol_agent_responses": {
        "idx_eol_responses_session",
        "idx_eol_responses_timestamp",
    },
    "normalization_failures": {
        "idx_normfail_raw",
    },
    "cve_alert_rules": {
        "idx_alert_rules_enabled",
        "idx_alert_rules_active",
    },
    "cve_alert_history": {
        "idx_alerthistory_rule",
        "idx_alerthistory_cve",
        "idx_alerthistory_fired",
        "idx_alerthistory_severity_fired",
        "idx_alerthistory_unsent",
        "idx_alerthistory_rule_covering",
    },
    "workflow_contexts": {
        "idx_wfctx_session_agent",
        "idx_wfctx_expires",
    },
    "audit_trail": {
        "idx_audit_entity",
        "idx_audit_created",
    },
    "slo_measurements": {
        "idx_slo_measurements_slo_id",
    },
}


# ------------------------------------------------------------------ #
# Expected materialized views (7 bootstrap MVs)
# ------------------------------------------------------------------ #
EXPECTED_MVS = [
    "mv_inventory_os_cve_counts",
    "mv_cve_dashboard_summary",
    "mv_cve_top_by_score",
    "mv_cve_exposure",
    "mv_cve_trending",
    "mv_vm_vulnerability_posture",
    "mv_vm_cve_detail",
]


# ------------------------------------------------------------------ #
# Test 1: All expected indexes exist (parametrized)
# ------------------------------------------------------------------ #
@pytest.mark.parametrize(
    "table_name,expected_index_names",
    list(EXPECTED_INDEXES.items()),
    ids=list(EXPECTED_INDEXES.keys()),
)
async def test_all_expected_indexes_exist(
    pg_pool, table_name, expected_index_names
):
    """Validate that every index from pg_database.py bootstrap exists in pg_indexes."""
    async with pg_pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT indexname FROM pg_indexes WHERE schemaname = 'public' AND tablename = $1",
            table_name,
        )

    actual_indexes = {row["indexname"] for row in rows}

    # If the table doesn't exist at all, skip gracefully
    if not actual_indexes:
        # Check if table exists
        async with pg_pool.acquire() as conn:
            table_check = await conn.fetchval(
                "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
                "WHERE table_schema = 'public' AND table_name = $1)",
                table_name,
            )
        if not table_check:
            pytest.skip(f"Table '{table_name}' not found in schema")

    missing = expected_index_names - actual_indexes
    assert not missing, (
        f"Table '{table_name}' is missing indexes: {sorted(missing)}. "
        f"Actual indexes: {sorted(actual_indexes)}"
    )


# ------------------------------------------------------------------ #
# Test 2: All materialized views exist
# ------------------------------------------------------------------ #
async def test_all_materialized_views_exist(pg_pool):
    """Validate that all 7 bootstrap MVs exist in pg_matviews."""
    async with pg_pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT matviewname FROM pg_matviews WHERE schemaname = 'public'"
        )

    actual_mvs = {row["matviewname"] for row in rows}
    missing = [mv for mv in EXPECTED_MVS if mv not in actual_mvs]

    assert not missing, (
        f"Missing materialized views: {missing}. "
        f"Actual MVs: {sorted(actual_mvs)}"
    )


# ------------------------------------------------------------------ #
# Test 3: latest_completed_scan_id() function exists
# ------------------------------------------------------------------ #
async def test_latest_completed_scan_id_function_exists(pg_pool):
    """Validate that latest_completed_scan_id() function is callable."""
    try:
        async with pg_pool.acquire() as conn:
            result = await conn.fetchval("SELECT latest_completed_scan_id()")
        # Result can be NULL or a scan_id string -- both are valid
        assert result is None or isinstance(result, str)
    except asyncpg.UndefinedFunctionError:
        pytest.fail("Function latest_completed_scan_id() does not exist")
    except asyncpg.UndefinedTableError:
        pytest.skip("Underlying table for latest_completed_scan_id() not found")


# ------------------------------------------------------------------ #
# Test 4: FTS trigger exists on cves table
# ------------------------------------------------------------------ #
async def test_fts_trigger_exists(pg_pool):
    """Validate that trg_cves_search_vector_update trigger exists."""
    async with pg_pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT tgname FROM pg_trigger WHERE tgname = 'trg_cves_search_vector_update'"
        )

    assert len(rows) == 1, (
        f"Expected exactly 1 trigger named 'trg_cves_search_vector_update', "
        f"found {len(rows)}"
    )


# ------------------------------------------------------------------ #
# Test 5: FK constraints enforced (referential integrity)
# ------------------------------------------------------------------ #
async def test_fk_constraints_enforced(pg_pool):
    """Validate FK constraints by attempting an invalid INSERT into vm_cve_match_rows.

    Uses SAVEPOINT/ROLLBACK TO SAVEPOINT pattern to avoid poisoning
    the connection's transaction state.
    """
    async with pg_pool.acquire() as conn:
        tr = conn.transaction()
        await tr.start()
        try:
            # Create a savepoint so we can roll back the bad insert
            await conn.execute("SAVEPOINT fk_test_sp")

            with pytest.raises(asyncpg.ForeignKeyViolationError):
                await conn.execute(
                    """INSERT INTO vm_cve_match_rows (scan_id, vm_id, cve_id)
                       VALUES ('fake-scan', 'nonexistent-vm', 'CVE-9999-9999')"""
                )

            # Rollback the savepoint regardless
            await conn.execute("ROLLBACK TO SAVEPOINT fk_test_sp")
        finally:
            await tr.rollback()
