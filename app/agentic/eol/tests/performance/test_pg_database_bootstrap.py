"""
Fresh Database Bootstrap Verification -- Phase 10, Plan 6.

Verifies that ``pg_database.py`` bootstrap succeeds on a completely empty
PostgreSQL database.  Simulates production deployment to a fresh Azure
PostgreSQL Flexible Server.

Tests cover: table creation, FK enforcement, MV creation + refresh,
index existence, function existence, trigger existence.

Requires DATABASE_URL.  All tests are skipped otherwise.
"""
from __future__ import annotations

import os
from urllib.parse import urlparse, urlunparse
from uuid import uuid4

import pytest
import pytest_asyncio

try:
    import asyncpg
except ImportError:
    asyncpg = None  # type: ignore[assignment]

# ------------------------------------------------------------------ #
# Module-level skip when DATABASE_URL is absent
# ------------------------------------------------------------------ #
DATABASE_URL = os.getenv("DATABASE_URL")
pytestmark = [
    pytest.mark.skipif(
        not DATABASE_URL,
        reason="DATABASE_URL not set -- bootstrap tests require PostgreSQL",
    ),
    pytest.mark.asyncio,
    pytest.mark.performance,
]


# ------------------------------------------------------------------ #
# Expected schema artefacts (aligned with pg_database.py after P10.5)
# ------------------------------------------------------------------ #
_EXPECTED_MV_NAMES = [
    "mv_inventory_os_cve_counts",
    "mv_cve_dashboard_summary",
    "mv_cve_top_by_score",
    "mv_cve_exposure",
    "mv_cve_trending",
    "mv_vm_vulnerability_posture",
    "mv_vm_cve_detail",
]


def _replace_db_name(dsn: str, new_db: str) -> str:
    """Return *dsn* with the database component replaced by *new_db*."""
    parsed = urlparse(dsn)
    # path is "/<dbname>" — replace with new db name
    new_path = f"/{new_db}"
    return urlunparse(parsed._replace(path=new_path))


# ------------------------------------------------------------------ #
# Session-scoped ephemeral database fixture
# ------------------------------------------------------------------ #
@pytest_asyncio.fixture(scope="function")
async def fresh_pool():
    """Create a temporary empty database, bootstrap it, and yield a pool.

    On teardown the temporary database is dropped.

    If the user lacks CREATE DATABASE privileges the fixture falls back
    to the existing database and re-runs bootstrap (documented limitation).
    """
    if not DATABASE_URL or asyncpg is None:
        pytest.skip("DATABASE_URL not set or asyncpg not installed")

    temp_db_name = f"phase10_bootstrap_test_{uuid4().hex[:8]}"
    used_temp_db = False

    # --- attempt to create a fresh temporary database ---
    try:
        admin_conn = await asyncpg.connect(DATABASE_URL)
        try:
            await admin_conn.execute(f'CREATE DATABASE "{temp_db_name}"')
            used_temp_db = True
        finally:
            await admin_conn.close()
    except Exception:
        # Insufficient privileges — fall back to the existing database
        pass

    if used_temp_db:
        temp_dsn = _replace_db_name(DATABASE_URL, temp_db_name)
    else:
        # Fallback: use existing DB but bootstrap will still exercise
        # IF NOT EXISTS paths on every DDL statement.
        temp_dsn = DATABASE_URL

    pool = await asyncpg.create_pool(temp_dsn, min_size=2, max_size=5)

    # Run the full bootstrap on the (empty) database
    from utils.pg_database import PostgresDatabaseManager

    mgr = PostgresDatabaseManager(pool)
    await mgr.ensure_runtime_schema()

    yield pool

    # --- teardown ---
    await pool.close()

    if used_temp_db:
        try:
            admin_conn = await asyncpg.connect(DATABASE_URL)
            try:
                # Terminate remaining connections before DROP
                await admin_conn.execute(f"""
                    SELECT pg_terminate_backend(pid)
                    FROM pg_stat_activity
                    WHERE datname = '{temp_db_name}' AND pid <> pg_backend_pid()
                """)
                await admin_conn.execute(f'DROP DATABASE IF EXISTS "{temp_db_name}"')
            finally:
                await admin_conn.close()
        except Exception:
            pass  # best-effort cleanup


# ================================================================== #
#  Test 1: Bootstrap succeeds on empty database
# ================================================================== #
async def test_bootstrap_succeeds_on_empty_db(fresh_pool):
    """ensure_runtime_schema() completes without exception and creates tables."""
    async with fresh_pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
        )
    from utils.pg_database import PostgresDatabaseManager

    table_names = {r["tablename"] for r in rows}
    assert len(table_names) >= len(PostgresDatabaseManager._REQUIRED_TABLES), (
        f"Expected >= {len(PostgresDatabaseManager._REQUIRED_TABLES)} tables, "
        f"got {len(table_names)}"
    )


# ================================================================== #
#  Test 2: All required tables created
# ================================================================== #
async def test_all_required_tables_created(fresh_pool):
    """Every table listed in _REQUIRED_TABLES must exist in the public schema."""
    from utils.pg_database import PostgresDatabaseManager

    async with fresh_pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
        )
    existing = {r["tablename"] for r in rows}

    missing = [
        t for t in PostgresDatabaseManager._REQUIRED_TABLES if t not in existing
    ]
    assert missing == [], f"Missing required tables: {missing}"


# ================================================================== #
#  Test 3: All FK constraints exist
# ================================================================== #
async def test_all_fk_constraints_exist(fresh_pool):
    """Every tuple in _REQUIRED_RELATIONS must have a matching FK in the catalog."""
    from utils.pg_database import PostgresDatabaseManager

    _FK_CHECK = """
        SELECT 1
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
            ON tc.constraint_name = kcu.constraint_name
        JOIN information_schema.constraint_column_usage ccu
            ON tc.constraint_name = ccu.constraint_name
        WHERE tc.constraint_type = 'FOREIGN KEY'
          AND tc.table_name = $1
          AND kcu.column_name = $2
          AND ccu.table_name = $3
          AND ccu.column_name = $4
    """

    missing_fks = []
    async with fresh_pool.acquire() as conn:
        for child_tbl, child_col, parent_tbl, parent_col in PostgresDatabaseManager._REQUIRED_RELATIONS:
            has_fk = await conn.fetchval(
                _FK_CHECK, child_tbl, child_col, parent_tbl, parent_col,
            )
            if has_fk is None:
                missing_fks.append(f"{child_tbl}.{child_col} -> {parent_tbl}.{parent_col}")

    assert missing_fks == [], f"Missing FK constraints: {missing_fks}"


async def test_missing_fk_is_repaired_without_bootstrap_rerun(fresh_pool):
    """A missing FK on an existing table is repaired in place.

    Regression for startup failures where ensure_runtime_schema() used to
    re-run the full bootstrap when slo_measurements.slo_id lacked its FK.
    """
    from utils.pg_database import PostgresDatabaseManager

    mgr = PostgresDatabaseManager(fresh_pool)

    async with fresh_pool.acquire() as conn:
        await conn.execute(
            "ALTER TABLE slo_measurements "
            "DROP CONSTRAINT IF EXISTS slo_measurements_slo_id_fkey"
        )
        await conn.execute(
            "INSERT INTO slo_measurements (slo_id, value) "
            "VALUES ('orphan-slo', 99.9)"
        )

    async def _fail_bootstrap():
        raise AssertionError("ensure_runtime_schema should repair FK without rerunning bootstrap")

    mgr._bootstrap_runtime_schema = _fail_bootstrap  # type: ignore[method-assign]

    await mgr.ensure_runtime_schema()

    async with fresh_pool.acquire() as conn:
        orphan_rows = await conn.fetchval(
            "SELECT COUNT(*) FROM slo_measurements WHERE slo_id = 'orphan-slo'"
        )
        repaired_fk = await conn.fetchval(
            """
            SELECT 1
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
                ON tc.constraint_name = kcu.constraint_name
            JOIN information_schema.constraint_column_usage ccu
                ON tc.constraint_name = ccu.constraint_name
            WHERE tc.constraint_type = 'FOREIGN KEY'
              AND tc.table_name = 'slo_measurements'
              AND kcu.column_name = 'slo_id'
              AND ccu.table_name = 'slo_definitions'
              AND ccu.column_name = 'slo_id'
            """
        )

    assert orphan_rows == 0, "Expected orphan SLO rows to be deleted before FK repair"
    assert repaired_fk == 1, "Expected slo_measurements.slo_id FK to be recreated"


async def test_missing_fk_permission_error_is_nonfatal_in_container_mode(monkeypatch, fresh_pool):
    """Container mode should not fail startup on ownership-only FK repair errors."""
    from utils.pg_database import PostgresDatabaseManager

    mgr = PostgresDatabaseManager(fresh_pool)

    async with fresh_pool.acquire() as conn:
        await conn.execute(
            "ALTER TABLE slo_measurements "
            "DROP CONSTRAINT IF EXISTS slo_measurements_slo_id_fkey"
        )

    async def _raise_owner_error(*_args, **_kwargs):
        raise RuntimeError("must be owner of table slo_measurements")

    monkeypatch.setenv("CONTAINER_MODE", "true")
    monkeypatch.setattr(mgr, "_repair_missing_foreign_key", _raise_owner_error)

    await mgr.ensure_runtime_schema()


async def test_missing_fk_noncanonical_state_is_nonfatal_in_container_mode(monkeypatch, fresh_pool):
    """Container mode should tolerate a repair attempt that leaves the FK absent."""
    from utils.pg_database import PostgresDatabaseManager

    mgr = PostgresDatabaseManager(fresh_pool)

    async with fresh_pool.acquire() as conn:
        await conn.execute(
            "ALTER TABLE vm_cve_match_rows "
            "DROP CONSTRAINT IF EXISTS fk_vmcvematch_vm"
        )

    async def _noop_repair(*_args, **_kwargs):
        return None

    monkeypatch.setenv("CONTAINER_MODE", "true")
    monkeypatch.setattr(mgr, "_repair_missing_foreign_key", _noop_repair)

    await mgr.ensure_runtime_schema()


# ================================================================== #
#  Test 4: All materialized views created
# ================================================================== #
async def test_all_materialized_views_created(fresh_pool):
    """All 7 expected materialized views must exist after bootstrap."""
    async with fresh_pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT matviewname FROM pg_matviews WHERE schemaname = 'public'"
        )
    existing_mvs = {r["matviewname"] for r in rows}

    missing = [mv for mv in _EXPECTED_MV_NAMES if mv not in existing_mvs]
    assert missing == [], f"Missing materialized views: {missing}"


# ================================================================== #
#  Test 5: MV refresh on empty data
# ================================================================== #
async def test_mv_refresh_on_empty_data(fresh_pool):
    """Refreshing each MV on empty source tables must not raise.

    ``mv_cve_dashboard_summary`` always returns exactly 1 row
    (it uses COUNT/COALESCE); all others return 0 rows when source is empty.
    """
    async with fresh_pool.acquire() as conn:
        for mv_name in _EXPECTED_MV_NAMES:
            await conn.execute(f"REFRESH MATERIALIZED VIEW {mv_name}")
            count = await conn.fetchval(f"SELECT COUNT(*) FROM {mv_name}")
            if mv_name == "mv_cve_dashboard_summary":
                assert count == 1, (
                    f"{mv_name}: expected exactly 1 row, got {count}"
                )
            else:
                assert count == 0, (
                    f"{mv_name}: expected 0 rows on empty data, got {count}"
                )


# ================================================================== #
#  Test 6: FK enforcement rejects orphan insert
# ================================================================== #
async def test_fk_enforcement_rejects_orphan(fresh_pool):
    """Inserting a vm_cve_match_row referencing a non-existent vm must fail.

    Uses SAVEPOINT for rollback safety so one failed INSERT does not
    abort the enclosing transaction.
    """
    async with fresh_pool.acquire() as conn:
        async with conn.transaction():
            # Insert a valid scan so scan_id FK is satisfied
            await conn.execute(
                "INSERT INTO cve_scans (scan_id, status) "
                "VALUES ('test-fk-orphan', 'pending') "
                "ON CONFLICT DO NOTHING"
            )
            # Insert a valid CVE so cve_id FK is satisfied
            await conn.execute(
                "INSERT INTO cves (cve_id, description) "
                "VALUES ('CVE-9999-0001', 'FK enforcement test') "
                "ON CONFLICT DO NOTHING"
            )

            # Attempt to insert a match row with a non-existent vm_id
            with pytest.raises(asyncpg.ForeignKeyViolationError):
                # Use a SAVEPOINT so the FK error doesn't abort the
                # outer transaction
                sp = conn.transaction()
                await sp.start()
                try:
                    await conn.execute(
                        "INSERT INTO vm_cve_match_rows "
                        "(scan_id, vm_id, cve_id) "
                        "VALUES ('test-fk-orphan', 'nonexistent-vm-id', 'CVE-9999-0001')"
                    )
                except asyncpg.ForeignKeyViolationError:
                    await sp.rollback()
                    raise
                else:
                    await sp.rollback()


# ================================================================== #
#  Test 7: latest_completed_scan_id() function
# ================================================================== #
async def test_latest_completed_scan_id_function(fresh_pool):
    """The ``latest_completed_scan_id()`` SQL function must exist and work."""
    async with fresh_pool.acquire() as conn:
        # Use a savepoint so all test data is rolled back automatically
        tr = conn.transaction()
        await tr.start()
        try:
            # On empty DB the function should return NULL
            result = await conn.fetchval("SELECT latest_completed_scan_id()")
            assert result is None, (
                f"Expected None on empty DB, got {result!r}"
            )

            # Insert a completed scan
            await conn.execute(
                "INSERT INTO cve_scans (scan_id, status, completed_at) "
                "VALUES ('fn-test-001', 'completed', NOW()) "
                "ON CONFLICT DO NOTHING"
            )

            result = await conn.fetchval("SELECT latest_completed_scan_id()")
            assert result == "fn-test-001", (
                f"Expected 'fn-test-001', got {result!r}"
            )
        finally:
            await tr.rollback()


# ================================================================== #
#  Test 8: FTS trigger populates search_vector
# ================================================================== #
async def test_fts_trigger_populates_search_vector(fresh_pool):
    """The ``trg_cves_search_vector_update`` trigger must populate
    ``search_vector`` on INSERT and make the row discoverable via tsquery.
    """
    async with fresh_pool.acquire() as conn:
        # Use a savepoint so all test data is rolled back automatically
        tr = conn.transaction()
        await tr.start()
        try:
            await conn.execute(
                "INSERT INTO cves (cve_id, description) "
                "VALUES ('CVE-9999-FTS', 'test buffer overflow vulnerability') "
                "ON CONFLICT DO NOTHING"
            )

            sv = await conn.fetchval(
                "SELECT search_vector FROM cves WHERE cve_id = 'CVE-9999-FTS'"
            )
            assert sv is not None, "search_vector should be populated by trigger"

            hit = await conn.fetchval(
                "SELECT cve_id FROM cves "
                "WHERE search_vector @@ to_tsquery('english', 'overflow')"
            )
            assert hit == "CVE-9999-FTS", (
                f"Expected FTS match for 'overflow', got {hit!r}"
            )
        finally:
            await tr.rollback()
