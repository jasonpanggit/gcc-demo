"""Tests for the PostgreSQL-backed CVEScanRepository."""

from typing import Any, cast

import pytest

from models.cve_models import ScanResult


class _FakeConnection:
    def __init__(self):
        self.rows = {}

    async def execute(self, query, *args):
        if "INSERT INTO cve_scans" in query:
            self.rows[args[0]] = {
                "scan_id": args[0],
                "status": args[1],
                "started_at": args[2],
                "completed_at": args[3],
                "total_vms": args[4],
                "scanned_vms": args[5],
                "total_matches": args[6],
                "matches": args[7],
                "vm_match_summaries": args[8],
                "vm_installed_kbs": args[9],
                "vm_installed_packages": args[10],
                "vm_os_family": args[11],
                "truncated": args[12],
                "total_matches_before_truncation": args[13],
                "matches_stored_separately": args[14],
                "error": args[15],
            }
            return "INSERT 0 1"
        if "DELETE FROM cve_scans" in query:
            existed = self.rows.pop(args[0], None)
            return "DELETE 1" if existed else "DELETE 0"
        return "OK"

    async def fetchrow(self, query, *args):
        return self.rows.get(args[0])

    async def fetch(self, query, *args):
        return list(self.rows.values())[: args[0]]


class _Acquire:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakePool:
    def __init__(self):
        self.conn = _FakeConnection()

    def acquire(self):
        return _Acquire(self.conn)


@pytest.fixture
def repo():
    from utils.cve_scanner import CVEScanRepository

    return CVEScanRepository(cast(Any, _FakePool()))


def _scan(scan_id: str = "scan-1") -> ScanResult:
    return ScanResult(
        scan_id=scan_id,
        started_at="2026-03-18T00:00:00+00:00",
        completed_at="2026-03-18T01:00:00+00:00",
        status="completed",
        total_vms=2,
        scanned_vms=2,
        total_matches=4,
        matches=[],
        vm_match_summaries={"vm-1": {"total_cves": 4}},
        vm_os_family={"vm-1": "windows"},
        matches_stored_separately=True,
    )


@pytest.mark.asyncio
async def test_save_and_get_scan(repo):
    scan = _scan()
    await repo.save(scan)

    result = await repo.get(scan.scan_id)

    assert result is not None
    assert result.scan_id == scan.scan_id
    assert result.vm_match_summaries == {"vm-1": {"total_cves": 4}}
    assert result.vm_os_family == {"vm-1": "windows"}
    assert result.matches_stored_separately is True


@pytest.mark.asyncio
async def test_list_status_summaries_returns_scan_dicts(repo):
    await repo.save(_scan("scan-1"))
    await repo.save(_scan("scan-2"))

    rows = await repo.list_status_summaries(limit=10)

    assert len(rows) == 2
    assert rows[0]["scan_id"] == "scan-1"
    assert rows[0]["matches_stored_separately"] is True


@pytest.mark.asyncio
async def test_delete_scan(repo):
    scan = _scan()
    await repo.save(scan)

    deleted = await repo.delete(scan.scan_id)

    assert deleted is True
    assert await repo.get(scan.scan_id) is None
