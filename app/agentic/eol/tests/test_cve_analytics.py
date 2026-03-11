"""
Unit tests for CVE analytics service.

Tests all 6 analytics functions with comprehensive coverage:
- MTTP calculation
- Trending data
- Top CVEs by exposure
- VM vulnerability posture
- Aging distribution
- Summary statistics
"""
import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from typing import List, Dict, Any

from utils.cve_analytics import CVEAnalytics
from models.cve_models import UnifiedCVE, CVSSScore, ApplicablePatch, CVEPatchMapping


class TestCVEAnalytics:
    """Test suite for CVE analytics service."""

    @pytest.fixture
    def mock_scanner(self):
        """Create mock CVE scanner."""
        scanner = AsyncMock()
        scanner.get_latest_scan_results = AsyncMock()
        scanner.list_recent_scans = AsyncMock(return_value=[])
        return scanner

    @pytest.fixture
    def mock_service(self):
        """Create mock CVE service."""
        service = AsyncMock()
        service.get_cve = AsyncMock()
        return service

    @pytest.fixture
    def mock_patch_mapper(self):
        """Create mock patch mapper."""
        mapper = AsyncMock()
        mapper.get_patches_for_cve = AsyncMock()
        mapper.get_install_history_for_cve = AsyncMock(return_value=[])
        mapper.supports_install_history = True
        return mapper

    @pytest.fixture
    def analytics(self, mock_scanner, mock_service, mock_patch_mapper):
        """Create analytics instance with mocks."""
        return CVEAnalytics(mock_scanner, mock_service, mock_patch_mapper)

    def _create_mock_cve(
        self,
        cve_id: str,
        published_date: datetime,
        severity: str = "HIGH",
        cvss_score: float = 7.5
    ) -> UnifiedCVE:
        """Helper to create mock CVE."""
        return UnifiedCVE(
            cve_id=cve_id,
            description=f"Test CVE {cve_id}",
            published_date=published_date,
            last_modified_date=published_date,
            cvss_v3=CVSSScore(
                version="3.1",
                base_score=cvss_score,
                base_severity=severity,
                vector_string="CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:N/A:N"
            ),
            sources=["nvd"]
        )

    @pytest.mark.asyncio
    async def test_calculate_mttp_with_patched_cves(
        self,
        analytics,
        mock_scanner,
        mock_service,
        mock_patch_mapper
    ):
        """Test MTTP calculation with patched CVEs."""
        # Arrange: 3 CVEs discovered on day 0, patched on days 5, 10, 15
        base_date = datetime(2026, 1, 1, tzinfo=timezone.utc)

        # Mock scan results with 3 CVE matches
        mock_scanner.get_latest_scan_results.return_value = {
            "matches": [
                {"cve_id": "CVE-2026-0001", "vm_id": "vm-1", "severity": "CRITICAL", "cvss_score": 9.0},
                {"cve_id": "CVE-2026-0002", "vm_id": "vm-2", "severity": "HIGH", "cvss_score": 7.5},
                {"cve_id": "CVE-2026-0003", "vm_id": "vm-3", "severity": "HIGH", "cvss_score": 7.0}
            ]
        }

        # Mock CVEs with discovery dates
        cves = [
            self._create_mock_cve("CVE-2026-0001", base_date, "CRITICAL", 9.0),
            self._create_mock_cve("CVE-2026-0002", base_date, "HIGH", 7.5),
            self._create_mock_cve("CVE-2026-0003", base_date, "HIGH", 7.0)
        ]

        mock_service.get_cve.side_effect = lambda cve_id: next(
            (cve for cve in cves if cve.cve_id == cve_id), None
        )

        # Mock install history with real completion timestamps
        patch_dates = [
            base_date + timedelta(days=5),   # Patched after 5 days
            base_date + timedelta(days=10),  # Patched after 10 days
            base_date + timedelta(days=15)   # Patched after 15 days
        ]

        def mock_install_history(cve_id, _time_range_days):
            idx = int(cve_id.split('-')[-1]) - 1
            return [{"completed_at": patch_dates[idx].isoformat()}]

        mock_patch_mapper.get_install_history_for_cve.side_effect = mock_install_history

        # Act
        mttp = await analytics.calculate_mttp(30)

        # Assert: MTTP = (5 + 10 + 15) / 3 = 10 days
        assert mttp == 10.0

    @pytest.mark.asyncio
    async def test_calculate_mttp_excludes_unpatched(
        self,
        analytics,
        mock_scanner,
        mock_service,
        mock_patch_mapper
    ):
        """Test MTTP excludes CVEs without patches."""
        base_date = datetime(2026, 1, 1, tzinfo=timezone.utc)

        # Mock 5 CVE matches
        mock_scanner.get_latest_scan_results.return_value = {
            "matches": [
                {"cve_id": f"CVE-2026-000{i}", "vm_id": f"vm-{i}", "severity": "HIGH", "cvss_score": 7.0}
                for i in range(1, 6)
            ]
        }

        # Mock CVEs
        cves = [
            self._create_mock_cve(f"CVE-2026-000{i}", base_date)
            for i in range(1, 6)
        ]
        mock_service.get_cve.side_effect = lambda cve_id: next(
            (cve for cve in cves if cve.cve_id == cve_id), None
        )

        # Only 2 have install history records
        def mock_install_history(cve_id, _time_range_days):
            idx = int(cve_id.split('-')[-1])
            if idx in [1, 2]:
                return [{"completed_at": (base_date + timedelta(days=idx * 5)).isoformat()}]
            return []

        mock_patch_mapper.get_install_history_for_cve.side_effect = mock_install_history

        # Act
        mttp = await analytics.calculate_mttp(30)

        # Assert: Only 2 patched CVEs counted: (5 + 10) / 2 = 7.5 days
        assert mttp == 7.5

    @pytest.mark.asyncio
    async def test_calculate_mttp_returns_none_without_install_history(
        self,
        analytics,
        mock_scanner,
        mock_patch_mapper
    ):
        """MTTP should be unavailable when the patch layer cannot provide install history."""
        mock_scanner.get_latest_scan_results.return_value = {
            "matches": [
                {"cve_id": "CVE-2026-0001", "vm_id": "vm-1", "severity": "HIGH", "cvss_score": 7.0}
            ]
        }
        mock_patch_mapper.supports_install_history = False

        mttp = await analytics.calculate_mttp(30)

        assert mttp is None
        mock_patch_mapper.get_install_history_for_cve.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_get_trending_data_daily_buckets(
        self,
        analytics,
        mock_scanner,
        mock_service
    ):
        """Test trending data with daily buckets (30-day range)."""
        # Mock scan results
        mock_scanner.get_latest_scan_results.return_value = {
            "matches": [
                {"cve_id": f"CVE-2026-000{i}", "vm_id": "vm-1", "severity": "HIGH", "cvss_score": 7.0}
                for i in range(1, 6)
            ]
        }

        # Mock CVEs with various published dates
        now = datetime.now(timezone.utc)
        dates = [now - timedelta(days=i * 6) for i in range(5)]  # Spread across 30 days

        cves = [
            self._create_mock_cve(f"CVE-2026-000{i}", dates[i - 1])
            for i in range(1, 6)
        ]
        mock_service.get_cve.side_effect = lambda cve_id: next(
            (cve for cve in cves if cve.cve_id == cve_id), None
        )

        # Act
        trending = await analytics.get_trending_data(30, None)

        # Assert
        assert len(trending) == 30  # 30 daily buckets
        assert all("date" in bucket and "count" in bucket for bucket in trending)
        # Total count should match CVEs (may be 4 or 5 depending on bucket boundaries)
        total_count = sum(bucket["count"] for bucket in trending)
        assert 4 <= total_count <= 5

    @pytest.mark.asyncio
    async def test_get_trending_data_weekly_buckets(
        self,
        analytics,
        mock_scanner,
        mock_service
    ):
        """Test trending data with weekly buckets (90-day range)."""
        mock_scanner.get_latest_scan_results.return_value = {
            "matches": [
                {"cve_id": "CVE-2026-0001", "vm_id": "vm-1", "severity": "HIGH", "cvss_score": 7.0}
            ]
        }

        cve = self._create_mock_cve("CVE-2026-0001", datetime.now(timezone.utc) - timedelta(days=30))
        mock_service.get_cve.return_value = cve

        # Act
        trending = await analytics.get_trending_data(90, None)

        # Assert: ~13 weekly buckets (90 / 7)
        assert 12 <= len(trending) <= 13

    @pytest.mark.asyncio
    async def test_top_cves_sorted_by_exposure_then_cvss(
        self,
        analytics,
        mock_scanner,
        mock_service
    ):
        """Test top CVEs sorted by affected VMs then CVSS."""
        # CVE-0001: 5 VMs, CVSS 9.0
        # CVE-0002: 5 VMs, CVSS 7.0 (same VM count, lower CVSS)
        # CVE-0003: 3 VMs, CVSS 10.0 (fewer VMs, highest CVSS)
        mock_scanner.get_latest_scan_results.return_value = {
            "matches": [
                {"cve_id": "CVE-2026-0001", "vm_id": f"vm-{i}", "severity": "CRITICAL", "cvss_score": 9.0}
                for i in range(1, 6)
            ] + [
                {"cve_id": "CVE-2026-0002", "vm_id": f"vm-{i}", "severity": "HIGH", "cvss_score": 7.0}
                for i in range(1, 6)
            ] + [
                {"cve_id": "CVE-2026-0003", "vm_id": f"vm-{i}", "severity": "CRITICAL", "cvss_score": 10.0}
                for i in range(1, 4)
            ]
        }

        base_date = datetime(2026, 1, 1, tzinfo=timezone.utc)
        cves = [
            self._create_mock_cve("CVE-2026-0001", base_date, "CRITICAL", 9.0),
            self._create_mock_cve("CVE-2026-0002", base_date, "HIGH", 7.0),
            self._create_mock_cve("CVE-2026-0003", base_date, "CRITICAL", 10.0)
        ]
        mock_service.get_cve.side_effect = lambda cve_id: next(
            (cve for cve in cves if cve.cve_id == cve_id), None
        )

        # Act
        top_cves = await analytics.get_top_cves_by_exposure(None, limit=10)

        # Assert: Sorted by VM count DESC, then CVSS DESC
        assert len(top_cves) == 3
        assert top_cves[0]["cve_id"] == "CVE-2026-0001"  # 5 VMs, 9.0 CVSS
        assert top_cves[0]["affected_vms"] == 5
        assert top_cves[1]["cve_id"] == "CVE-2026-0002"  # 5 VMs, 7.0 CVSS
        assert top_cves[1]["affected_vms"] == 5
        assert top_cves[2]["cve_id"] == "CVE-2026-0003"  # 3 VMs, 10.0 CVSS
        assert top_cves[2]["affected_vms"] == 3

    @pytest.mark.asyncio
    async def test_get_trending_data_prefers_scan_history(
        self,
        analytics,
        mock_scanner,
    ):
        """Trending should reflect scan detection dates when recent scan history exists."""
        now = datetime.now(timezone.utc)

        recent_scans = [
            {
                "status": "completed",
                "started_at": now.isoformat(),
                "matches": [
                    {"cve_id": "CVE-2026-0001", "severity": "HIGH"},
                    {"cve_id": "CVE-2026-0001", "severity": "HIGH"},
                    {"cve_id": "CVE-2026-0002", "severity": "CRITICAL"},
                ],
            },
            {
                "status": "completed",
                "started_at": (now - timedelta(days=8)).isoformat(),
                "matches": [
                    {"cve_id": "CVE-2026-0003", "severity": "HIGH"},
                ],
            },
        ]
        mock_scanner.list_recent_scans.return_value = recent_scans

        trending = await analytics.get_trending_data(30, None)

        assert sum(bucket["count"] for bucket in trending) == 3
        assert any(bucket["count"] == 2 for bucket in trending)
        assert any(bucket["count"] == 1 for bucket in trending)

    @pytest.mark.asyncio
    async def test_vm_posture_sorted_by_severity_then_count(
        self,
        analytics,
        mock_scanner
    ):
        """Test VM posture sorted by severity then CVE count."""
        # vm-1: 1 CRITICAL CVE
        # vm-2: 5 HIGH CVEs
        # vm-3: 10 MEDIUM CVEs
        mock_scanner.get_latest_scan_results.return_value = {
            "matches": [
                {"cve_id": "CVE-2026-0001", "vm_id": "vm-1", "vm_name": "prod-01", "severity": "CRITICAL", "cvss_score": 9.0}
            ] + [
                {"cve_id": f"CVE-2026-{i:04d}", "vm_id": "vm-2", "vm_name": "prod-02", "severity": "HIGH", "cvss_score": 7.0}
                for i in range(2, 7)
            ] + [
                {"cve_id": f"CVE-2026-{i:04d}", "vm_id": "vm-3", "vm_name": "prod-03", "severity": "MEDIUM", "cvss_score": 5.0}
                for i in range(7, 17)
            ]
        }

        # Act
        vm_posture = await analytics.get_vm_vulnerability_posture(None)

        # Assert: CRITICAL first, then HIGH, then MEDIUM
        assert len(vm_posture) == 3
        assert vm_posture[0]["vm_id"] == "vm-1"
        assert vm_posture[0]["highest_severity"] == "CRITICAL"
        assert vm_posture[0]["cve_count"] == 1

        assert vm_posture[1]["vm_id"] == "vm-2"
        assert vm_posture[1]["highest_severity"] == "HIGH"
        assert vm_posture[1]["cve_count"] == 5

        assert vm_posture[2]["vm_id"] == "vm-3"
        assert vm_posture[2]["highest_severity"] == "MEDIUM"
        assert vm_posture[2]["cve_count"] == 10

    @pytest.mark.asyncio
    async def test_aging_distribution_buckets(
        self,
        analytics,
        mock_scanner,
        mock_service
    ):
        """Test CVE aging distribution with correct bucketing."""
        now = datetime.now(timezone.utc)

        # CVEs at exact bucket boundaries
        mock_scanner.get_latest_scan_results.return_value = {
            "matches": [
                {"cve_id": "CVE-2026-0001", "vm_id": "vm-1", "severity": "HIGH", "cvss_score": 7.0},  # 3 days old
                {"cve_id": "CVE-2026-0002", "vm_id": "vm-1", "severity": "HIGH", "cvss_score": 7.0},  # 7 days old (boundary)
                {"cve_id": "CVE-2026-0003", "vm_id": "vm-1", "severity": "HIGH", "cvss_score": 7.0},  # 15 days old
                {"cve_id": "CVE-2026-0004", "vm_id": "vm-1", "severity": "HIGH", "cvss_score": 7.0},  # 30 days old (boundary)
                {"cve_id": "CVE-2026-0005", "vm_id": "vm-1", "severity": "HIGH", "cvss_score": 7.0},  # 60 days old
                {"cve_id": "CVE-2026-0006", "vm_id": "vm-1", "severity": "HIGH", "cvss_score": 7.0},  # 90 days old (boundary)
                {"cve_id": "CVE-2026-0007", "vm_id": "vm-1", "severity": "HIGH", "cvss_score": 7.0},  # 100 days old
            ]
        }

        cves = [
            self._create_mock_cve("CVE-2026-0001", now - timedelta(days=3)),
            self._create_mock_cve("CVE-2026-0002", now - timedelta(days=7)),
            self._create_mock_cve("CVE-2026-0003", now - timedelta(days=15)),
            self._create_mock_cve("CVE-2026-0004", now - timedelta(days=30)),
            self._create_mock_cve("CVE-2026-0005", now - timedelta(days=60)),
            self._create_mock_cve("CVE-2026-0006", now - timedelta(days=90)),
            self._create_mock_cve("CVE-2026-0007", now - timedelta(days=100))
        ]
        mock_service.get_cve.side_effect = lambda cve_id: next(
            (cve for cve in cves if cve.cve_id == cve_id), None
        )

        # Act
        aging = await analytics.get_aging_distribution(None)

        # Assert: Correct bucketing
        assert aging["0-7_days"] == 2    # 3 and 7 days
        assert aging["8-30_days"] == 2   # 15 and 30 days
        assert aging["31-90_days"] == 2  # 60 and 90 days
        assert aging["90+_days"] == 1    # 100 days

    @pytest.mark.asyncio
    async def test_summary_stats_with_severity_filter(
        self,
        analytics,
        mock_service
    ):
        """Summary stats should use cache-backed counts for the selected severity."""
        mock_service.count_cves = AsyncMock(return_value=27)

        # Act
        stats = await analytics.get_summary_stats(30, "CRITICAL")

        # Assert: Only the selected severity bucket is populated
        assert stats["total_cves"] == 27
        assert stats["critical"] == 27
        assert stats["high"] == 0
        assert stats["medium"] == 0
        assert stats["low"] == 0
        mock_service.count_cves.assert_awaited_once()
        filters = mock_service.count_cves.await_args.args[0]
        assert filters["severity"] == "CRITICAL"
        assert "published_after" in filters

    @pytest.mark.asyncio
    async def test_summary_stats_without_severity_uses_cache_counts(
        self,
        analytics,
        mock_service
    ):
        """Summary stats should aggregate per-severity counts from cached CVEs."""
        async def count_side_effect(filters):
            mapping = {
                "CRITICAL": 5,
                "HIGH": 47,
                "MEDIUM": 20,
                "LOW": 8,
            }
            return mapping[filters["severity"]]

        mock_service.count_cves = AsyncMock(side_effect=count_side_effect)

        stats = await analytics.get_summary_stats(365, None)

        assert stats == {
            "total_cves": 80,
            "critical": 5,
            "high": 47,
            "medium": 20,
            "low": 8,
        }
        assert mock_service.count_cves.await_count == 4
        for call in mock_service.count_cves.await_args_list:
            assert "published_after" in call.args[0]

    @pytest.mark.asyncio
    async def test_empty_scan_results_returns_zeros(
        self,
        analytics,
        mock_scanner,
        mock_service
    ):
        """Test all functions return zero values gracefully when no scan results."""
        mock_scanner.get_latest_scan_results.return_value = None
        mock_service.count_cves = AsyncMock(return_value=0)

        # Act
        mttp = await analytics.calculate_mttp(30)
        trending = await analytics.get_trending_data(30, None)
        top_cves = await analytics.get_top_cves_by_exposure(None)
        vm_posture = await analytics.get_vm_vulnerability_posture(None)
        aging = await analytics.get_aging_distribution(None)
        stats = await analytics.get_summary_stats(30, None)

        # Assert: All return empty/zero values
        assert mttp == 0.0
        # Trending returns empty buckets even with no data (for smooth chart rendering)
        assert len(trending) == 30 and all(bucket["count"] == 0 for bucket in trending)
        assert top_cves == []
        assert vm_posture == []
        assert aging == {"0-7_days": 0, "8-30_days": 0, "31-90_days": 0, "90+_days": 0}
        assert stats["total_cves"] == 0
