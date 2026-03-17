"""
Performance test conftest -- asyncpg pool fixture, seed data generator,
and EXPLAIN ANALYZE convenience fixture.

Phase 10: Validation & Cleanup infrastructure.
Requires DATABASE_URL to be set; all tests are skipped otherwise.
"""
from __future__ import annotations

import logging
import os
import uuid

import pytest
import pytest_asyncio

try:
    import asyncpg
except ImportError:
    asyncpg = None  # type: ignore[assignment]

from tests.performance.helpers import run_explain_analyze

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------ #
# Module-level skip when DATABASE_URL is absent
# ------------------------------------------------------------------ #
DATABASE_URL = os.getenv("DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not DATABASE_URL,
    reason="DATABASE_URL not set -- performance tests require PostgreSQL",
)


# ------------------------------------------------------------------ #
# Register performance marker
# ------------------------------------------------------------------ #
def pytest_configure(config):
    config.addinivalue_line(
        "markers", "performance: Performance validation tests requiring PostgreSQL"
    )


# ------------------------------------------------------------------ #
# Session-scoped asyncpg pool
# ------------------------------------------------------------------ #
@pytest_asyncio.fixture(scope="session")
async def pg_pool():
    """Create a session-scoped asyncpg pool and ensure schema exists."""
    if not DATABASE_URL or asyncpg is None:
        pytest.skip("DATABASE_URL not set or asyncpg not installed")

    pool = await asyncpg.create_pool(DATABASE_URL, min_size=2, max_size=5)

    # Ensure schema is present
    from utils.pg_database import PostgresDatabaseManager
    db_manager = PostgresDatabaseManager(pool)
    await db_manager.ensure_runtime_schema()

    yield pool

    await pool.close()


# ------------------------------------------------------------------ #
# Seed data for performance testing
# ------------------------------------------------------------------ #
_SCAN_ID = "perf-test-scan-001"

# Subscription UUIDs (deterministic for idempotency)
_SUB_IDS = [
    uuid.UUID("aaaaaaaa-0000-0000-0000-000000000001"),
    uuid.UUID("aaaaaaaa-0000-0000-0000-000000000002"),
]

# OS distributions for VMs
_WINDOWS_OS = ["Windows Server 2019", "Windows Server 2022"]
_LINUX_OS = ["Ubuntu 22.04", "Red Hat Enterprise Linux 9"]

# Severity distribution for 100 CVEs: 10 CRITICAL, 20 HIGH, 40 MEDIUM, 20 LOW, 10 NULL
_SEVERITY_MAP = (
    [("CRITICAL", 9.5)] * 10
    + [("HIGH", 7.5)] * 20
    + [("MEDIUM", 5.0)] * 40
    + [("LOW", 2.5)] * 20
    + [(None, None)] * 10
)

# MV refresh list -- aligned with pg_database.py _create_materialized_views
_MV_NAMES = [
    "mv_cve_dashboard_summary",
    "mv_cve_trending",
    "mv_cve_top_by_score",
    "mv_cve_exposure",
    "mv_vm_vulnerability_posture",
    "mv_vm_cve_detail",
    "mv_inventory_os_cve_counts",
]


@pytest_asyncio.fixture(scope="session")
async def seed_performance_data(pg_pool):
    """Insert deterministic seed data for performance tests.

    Data covers all 7 MVs' source tables: cves, vms, subscriptions,
    vm_cve_match_rows, kb_cve_edges, eol_records, cve_scans.

    Uses ON CONFLICT DO NOTHING for idempotency.
    """
    async with pg_pool.acquire() as conn:
        # --- Subscriptions (2) ---
        await conn.executemany(
            """
            INSERT INTO subscriptions (subscription_id, subscription_name)
            VALUES ($1, $2)
            ON CONFLICT DO NOTHING
            """,
            [
                (_SUB_IDS[0], "perf-test-sub-alpha"),
                (_SUB_IDS[1], "perf-test-sub-beta"),
            ],
        )

        # --- VMs (30): 15 Windows + 15 Linux ---
        vm_rows = []
        for i in range(30):
            sub_id = _SUB_IDS[i % 2]
            if i < 15:
                os_name = _WINDOWS_OS[i % len(_WINDOWS_OS)]
                os_type = "Windows"
            else:
                os_name = _LINUX_OS[i % len(_LINUX_OS)]
                os_type = "Linux"
            vm_rows.append((
                f"/subscriptions/{sub_id}/resourceGroups/rg-perf/providers/Microsoft.Compute/virtualMachines/vm-perf-{i:03d}",
                sub_id,
                "rg-perf",
                f"vm-perf-{i:03d}",
                os_name,
                os_type,
            ))

        await conn.executemany(
            """
            INSERT INTO vms (resource_id, subscription_id, resource_group, vm_name, os_name, os_type)
            VALUES ($1, $2, $3, $4, $5, $6)
            ON CONFLICT DO NOTHING
            """,
            vm_rows,
        )

        # --- CVEs (100) ---
        cve_rows = []
        for i in range(100):
            severity, score = _SEVERITY_MAP[i]
            cve_rows.append((
                f"CVE-2024-{i:04d}",
                f"Test vulnerability #{i} for performance testing.",
                severity,
                score,
            ))

        await conn.executemany(
            """
            INSERT INTO cves (cve_id, description, cvss_v3_severity, cvss_v3_score)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT DO NOTHING
            """,
            cve_rows,
        )

        # --- CVE Scans (1 completed) ---
        await conn.execute(
            """
            INSERT INTO cve_scans (scan_id, status, started_at, completed_at, total_vms, scanned_vms, total_matches)
            VALUES ($1, 'completed', NOW() - INTERVAL '1 hour', NOW(), 30, 30, 300)
            ON CONFLICT DO NOTHING
            """,
            _SCAN_ID,
        )

        # --- VM-CVE match rows (300): 30 VMs x 10 CVEs each ---
        match_rows = []
        for vm_idx in range(30):
            vm_resource_id = vm_rows[vm_idx][0]
            vm_name = vm_rows[vm_idx][3]
            for cve_offset in range(10):
                cve_idx = (vm_idx * 3 + cve_offset) % 100
                severity, score = _SEVERITY_MAP[cve_idx]
                match_rows.append((
                    _SCAN_ID,
                    vm_resource_id,
                    vm_name,
                    f"CVE-2024-{cve_idx:04d}",
                    severity,
                    score,
                ))

        await conn.executemany(
            """
            INSERT INTO vm_cve_match_rows (scan_id, vm_id, vm_name, cve_id, severity, cvss_score)
            VALUES ($1, $2, $3, $4, $5, $6)
            ON CONFLICT DO NOTHING
            """,
            match_rows,
        )

        # --- KB-CVE edges (50) ---
        kb_rows = []
        for i in range(50):
            cve_idx = i % 100
            kb_rows.append((
                f"KB{5000000 + i}",
                f"CVE-2024-{cve_idx:04d}",
                "MSRC",
            ))

        await conn.executemany(
            """
            INSERT INTO kb_cve_edges (kb_number, cve_id, source)
            VALUES ($1, $2, $3)
            ON CONFLICT DO NOTHING
            """,
            kb_rows,
        )

        # --- EOL records (10) ---
        eol_os_names = [
            "Windows Server 2019", "Windows Server 2022",
            "Ubuntu 22.04", "Red Hat Enterprise Linux 9",
            "Windows Server 2016", "Ubuntu 20.04",
            "CentOS 7", "Debian 11",
            "Windows Server 2012 R2", "SUSE Linux Enterprise 15",
        ]
        eol_rows = []
        for i, sw_name in enumerate(eol_os_names):
            is_eol = i >= 5  # first 5 are current, rest are EOL
            eol_date = "2024-06-30" if is_eol else "2028-12-31"
            eol_rows.append((
                f"perf-eol-{sw_name.lower().replace(' ', '-')}",
                sw_name,
                is_eol,
                eol_date,
            ))

        await conn.executemany(
            """
            INSERT INTO eol_records (software_key, software_name, is_eol, eol_date)
            VALUES ($1, $2, $3, $4::DATE)
            ON CONFLICT DO NOTHING
            """,
            eol_rows,
        )

        # --- Alert rules (3) ---
        alert_rule_ids = [
            uuid.UUID("bbbbbbbb-0000-0000-0000-000000000001"),
            uuid.UUID("bbbbbbbb-0000-0000-0000-000000000002"),
            uuid.UUID("bbbbbbbb-0000-0000-0000-000000000003"),
        ]
        alert_rule_rows = [
            (alert_rule_ids[0], "perf-critical-rule", "CRITICAL", True),
            (alert_rule_ids[1], "perf-high-rule", "HIGH", True),
            (alert_rule_ids[2], "perf-medium-rule", "MEDIUM", False),
        ]

        await conn.executemany(
            """
            INSERT INTO cve_alert_rules (rule_id, rule_name, severity_threshold, enabled)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT DO NOTHING
            """,
            alert_rule_rows,
        )

        # --- Alert history (10) ---
        alert_history_rows = []
        for i in range(10):
            rule_id = alert_rule_ids[i % 3]
            cve_idx = i % 100
            severity = _SEVERITY_MAP[cve_idx][0] or "MEDIUM"
            alert_history_rows.append((
                rule_id,
                f"CVE-2024-{cve_idx:04d}",
                severity,
            ))

        await conn.executemany(
            """
            INSERT INTO cve_alert_history (rule_id, cve_id, severity)
            VALUES ($1, $2, $3)
            ON CONFLICT DO NOTHING
            """,
            alert_history_rows,
        )

        # --- Refresh all materialized views ---
        for mv in _MV_NAMES:
            try:
                await conn.execute(f"REFRESH MATERIALIZED VIEW {mv}")
                logger.info("Refreshed MV: %s", mv)
            except Exception as exc:
                logger.warning("Could not refresh MV %s: %s", mv, exc)

    yield


# ------------------------------------------------------------------ #
# Convenience explain fixture
# ------------------------------------------------------------------ #
@pytest_asyncio.fixture(scope="function")
async def explain(pg_pool):
    """Return an async callable that runs EXPLAIN ANALYZE on a query.

    Usage in tests::

        result = await explain("SELECT * FROM cves WHERE cve_id = $1", ["CVE-2024-0001"])
        assert result["execution_time_ms"] < 50
    """

    async def _explain(query: str, params: list = None) -> dict:
        return await run_explain_analyze(pg_pool, query, params)

    return _explain
