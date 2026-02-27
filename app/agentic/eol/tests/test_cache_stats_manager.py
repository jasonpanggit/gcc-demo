"""
Cache Stats Manager Tests

Tests for enhanced cache statistics tracking.
Created: 2026-02-27 (Phase 3, Week 3, Day 1)
"""

import pytest
from unittest.mock import MagicMock


class TestCacheHitMissStats:
    """Tests for CacheHitMissStats dataclass."""

    def test_cache_hit_miss_stats_imports(self):
        """Test CacheHitMissStats can be imported."""
        from utils.cache_stats_manager import CacheHitMissStats

        assert CacheHitMissStats is not None

    def test_cache_hit_miss_stats_initialization(self):
        """Test CacheHitMissStats initializes with zeros."""
        from utils.cache_stats_manager import CacheHitMissStats

        stats = CacheHitMissStats()

        assert stats.hits == 0
        assert stats.misses == 0
        assert stats.total_requests == 0

    def test_record_hit(self):
        """Test record_hit increments counters."""
        from utils.cache_stats_manager import CacheHitMissStats

        stats = CacheHitMissStats()
        stats.record_hit()

        assert stats.hits == 1
        assert stats.total_requests == 1
        assert stats.misses == 0

    def test_record_miss(self):
        """Test record_miss increments counters."""
        from utils.cache_stats_manager import CacheHitMissStats

        stats = CacheHitMissStats()
        stats.record_miss()

        assert stats.misses == 1
        assert stats.total_requests == 1
        assert stats.hits == 0

    def test_hit_rate_calculation(self):
        """Test hit_rate property calculates percentage."""
        from utils.cache_stats_manager import CacheHitMissStats

        stats = CacheHitMissStats()
        stats.record_hit()
        stats.record_hit()
        stats.record_miss()

        # 2 hits out of 3 requests = 66.67%
        assert abs(stats.hit_rate - 66.67) < 0.1

    def test_hit_rate_zero_requests(self):
        """Test hit_rate returns 0 for zero requests."""
        from utils.cache_stats_manager import CacheHitMissStats

        stats = CacheHitMissStats()
        assert stats.hit_rate == 0.0

    def test_miss_rate_calculation(self):
        """Test miss_rate property calculates percentage."""
        from utils.cache_stats_manager import CacheHitMissStats

        stats = CacheHitMissStats()
        stats.record_hit()
        stats.record_miss()

        # 1 miss out of 2 requests = 50%
        assert abs(stats.miss_rate - 50.0) < 0.1


class TestUrlStats:
    """Tests for UrlStats dataclass."""

    def test_url_stats_imports(self):
        """Test UrlStats can be imported."""
        from utils.cache_stats_manager import UrlStats

        assert UrlStats is not None

    def test_url_stats_initialization(self):
        """Test UrlStats initializes with defaults."""
        from utils.cache_stats_manager import UrlStats

        stats = UrlStats()

        assert stats.url == ""
        assert stats.request_count == 0
        assert stats.cache_hits == 0
        assert stats.cache_misses == 0
        assert stats.error_count == 0

    def test_url_stats_with_data(self):
        """Test UrlStats with provided data."""
        from utils.cache_stats_manager import UrlStats

        stats = UrlStats(
            url="https://example.com/eol",
            request_count=10,
            cache_hits=7,
            cache_misses=3
        )

        assert stats.url == "https://example.com/eol"
        assert stats.request_count == 10
        assert stats.cache_hits == 7

    def test_url_hit_rate_calculation(self):
        """Test hit_rate property for URL stats."""
        from utils.cache_stats_manager import UrlStats

        stats = UrlStats(cache_hits=8, cache_misses=2)

        # 8 hits out of 10 total = 80%
        assert abs(stats.hit_rate - 80.0) < 0.1

    def test_avg_response_time_calculation(self):
        """Test avg_response_time_ms calculation."""
        from utils.cache_stats_manager import UrlStats

        stats = UrlStats(
            request_count=4,
            total_response_time_ms=400.0
        )

        assert stats.avg_response_time_ms == 100.0

    def test_avg_response_time_zero_requests(self):
        """Test avg_response_time_ms returns 0 for zero requests."""
        from utils.cache_stats_manager import UrlStats

        stats = UrlStats()
        assert stats.avg_response_time_ms == 0.0

    def test_error_rate_calculation(self):
        """Test error_rate calculation."""
        from utils.cache_stats_manager import UrlStats

        stats = UrlStats(
            request_count=20,
            error_count=2
        )

        # 2 errors out of 20 requests = 10%
        assert abs(stats.error_rate - 10.0) < 0.1


class TestAgentPerformanceStats:
    """Tests for AgentPerformanceStats dataclass."""

    def test_agent_performance_stats_imports(self):
        """Test AgentPerformanceStats can be imported."""
        from utils.cache_stats_manager import AgentPerformanceStats

        assert AgentPerformanceStats is not None

    def test_agent_performance_stats_initialization(self):
        """Test AgentPerformanceStats initializes with defaults."""
        from utils.cache_stats_manager import AgentPerformanceStats

        stats = AgentPerformanceStats()

        assert stats.request_count == 0
        assert stats.total_response_time_ms == 0.0
        assert stats.error_count == 0
        # cache_stats may be None or initialized CacheHitMissStats
        assert stats.cache_stats is None or hasattr(stats.cache_stats, 'hits')

    def test_agent_performance_with_cache_stats(self):
        """Test AgentPerformanceStats with cache stats."""
        from utils.cache_stats_manager import AgentPerformanceStats, CacheHitMissStats

        cache_stats = CacheHitMissStats()
        cache_stats.record_hit()

        perf_stats = AgentPerformanceStats(cache_stats=cache_stats)

        assert perf_stats.cache_stats is not None
        assert perf_stats.cache_stats.hits == 1


class TestCacheStatsManagerModule:
    """Tests for cache_stats_manager module structure."""

    def test_module_imports(self):
        """Test cache_stats_manager module imports."""
        from utils import cache_stats_manager

        assert hasattr(cache_stats_manager, 'CacheHitMissStats')
        assert hasattr(cache_stats_manager, 'UrlStats')
        assert hasattr(cache_stats_manager, 'AgentPerformanceStats')
        assert hasattr(cache_stats_manager, 'datetime')
        assert hasattr(cache_stats_manager, 'dataclass')

    def test_cache_stats_manager_class_exists(self):
        """Test CacheStatsManager class exists."""
        from utils import cache_stats_manager

        # The main manager class should exist
        assert hasattr(cache_stats_manager, 'CacheStatsManager') or \
               hasattr(cache_stats_manager, 'cache_stats_manager')

    def test_dataclasses_are_serializable(self):
        """Test dataclasses can be converted to dict."""
        from utils.cache_stats_manager import CacheHitMissStats
        from dataclasses import asdict

        stats = CacheHitMissStats()
        stats.record_hit()

        # Should be serializable to dict
        stats_dict = asdict(stats)
        assert isinstance(stats_dict, dict)
        assert stats_dict['hits'] == 1
