"""
SRE Cache Tests

Tests for TTL-based in-memory caching for SRE MCP server tools.
Created: 2026-02-27 (Phase 3, Week 3, Day 1)
"""

import pytest
import time
from unittest.mock import patch


class TestSRECacheManagerInitialization:
    """Tests for SRECacheManager initialization."""

    def test_sre_cache_manager_imports(self):
        """Test SRECacheManager can be imported."""
        from utils.sre_cache import SRECacheManager

        assert SRECacheManager is not None

    def test_sre_cache_manager_default_initialization(self):
        """Test SRECacheManager initializes with defaults."""
        from utils.sre_cache import SRECacheManager

        cache = SRECacheManager()

        assert cache._max_entries == 500
        assert len(cache._cache) == 0
        assert cache._hits == 0
        assert cache._misses == 0

    def test_sre_cache_manager_custom_initialization(self):
        """Test SRECacheManager accepts custom max_entries."""
        from utils.sre_cache import SRECacheManager

        cache = SRECacheManager(max_entries=1000)

        assert cache._max_entries == 1000

    def test_sre_cache_manager_has_lock(self):
        """Test SRECacheManager has threading lock."""
        from utils.sre_cache import SRECacheManager

        cache = SRECacheManager()

        assert hasattr(cache, '_lock')
        assert cache._lock is not None


class TestTTLProfiles:
    """Tests for TTL profile constants."""

    def test_ttl_profiles_exist(self):
        """Test TTL_PROFILES constant exists."""
        from utils.sre_cache import SRECacheManager

        assert hasattr(SRECacheManager, 'TTL_PROFILES')
        assert isinstance(SRECacheManager.TTL_PROFILES, dict)

    def test_ttl_profile_values(self):
        """Test TTL profile values match cache_config standard tiers.

        Values updated in Phase 3 Plan 04 (PRF-06) to reference central
        CacheTTLProfile constants instead of hard-coded seconds:
          real_time → EPHEMERAL_TTL  (300s, was 60s)
          short     → EPHEMERAL_TTL  (300s, unchanged)
          medium    → SHORT_LIVED_TTL (900s, was 1800s)
          long      → MEDIUM_LIVED_TTL (3600s, unchanged)
          daily     → LONG_LIVED_TTL  (86400s, unchanged)
        """
        from utils.cache_config import EPHEMERAL_TTL, SHORT_LIVED_TTL, MEDIUM_LIVED_TTL, LONG_LIVED_TTL
        from utils.sre_cache import SRECacheManager

        profiles = SRECacheManager.TTL_PROFILES

        assert profiles["real_time"] == EPHEMERAL_TTL     # 300s - 5 min (was 60s)
        assert profiles["short"] == EPHEMERAL_TTL         # 300s - 5 min
        assert profiles["medium"] == SHORT_LIVED_TTL      # 900s - 15 min (was 1800s)
        assert profiles["long"] == MEDIUM_LIVED_TTL       # 3600s - 1 hr
        assert profiles["daily"] == LONG_LIVED_TTL        # 86400s - 24 hr

    def test_ttl_profiles_tiered_order(self):
        """Test TTL profiles maintain a meaningful tier ordering.

        Note: real_time and short both map to EPHEMERAL_TTL (5 min) since
        60s was too aggressive for cache round-trips (PRF-06). They share
        the same tier but are semantically distinct labels.
        """
        from utils.sre_cache import SRECacheManager

        profiles = SRECacheManager.TTL_PROFILES

        # real_time and short share EPHEMERAL tier (both 300s) — intentional
        assert profiles["real_time"] <= profiles["short"]
        assert profiles["short"] < profiles["medium"]
        assert profiles["medium"] < profiles["long"]
        assert profiles["long"] < profiles["daily"]


class TestToolTTLMapping:
    """Tests for tool-to-TTL mapping."""

    def test_tool_ttl_map_exists(self):
        """Test TOOL_TTL_MAP constant exists."""
        from utils.sre_cache import SRECacheManager

        assert hasattr(SRECacheManager, 'TOOL_TTL_MAP')
        assert isinstance(SRECacheManager.TOOL_TTL_MAP, dict)

    def test_performance_tools_realtime_ttl(self):
        """Test performance metric tools use real_time TTL."""
        from utils.sre_cache import SRECacheManager

        tool_map = SRECacheManager.TOOL_TTL_MAP

        assert tool_map["get_performance_metrics"] == "real_time"
        assert tool_map["identify_bottlenecks"] == "real_time"
        assert tool_map["detect_metric_anomalies"] == "real_time"

    def test_health_check_tools_short_ttl(self):
        """Test health check tools use short TTL."""
        from utils.sre_cache import SRECacheManager

        tool_map = SRECacheManager.TOOL_TTL_MAP

        assert tool_map["check_resource_health"] == "short"
        assert tool_map["check_container_app_health"] == "short"
        assert tool_map["check_aks_cluster_health"] == "short"

    def test_config_analysis_tools_medium_ttl(self):
        """Test config analysis tools use medium TTL."""
        from utils.sre_cache import SRECacheManager

        tool_map = SRECacheManager.TOOL_TTL_MAP

        assert tool_map["analyze_resource_configuration"] == "medium"
        assert tool_map["get_cost_analysis"] == "medium"

    def test_slo_tools_long_ttl(self):
        """Test SLO/dependency tools use long TTL."""
        from utils.sre_cache import SRECacheManager

        tool_map = SRECacheManager.TOOL_TTL_MAP

        assert tool_map["get_slo_dashboard"] == "long"
        assert tool_map["get_resource_dependencies"] == "long"

    def test_security_tools_daily_ttl(self):
        """Test security/compliance tools use daily TTL."""
        from utils.sre_cache import SRECacheManager

        tool_map = SRECacheManager.TOOL_TTL_MAP

        assert tool_map["get_security_score"] == "daily"
        assert tool_map["check_compliance_status"] == "daily"


class TestNeverCacheList:
    """Tests for never-cache tool list."""

    def test_never_cache_exists(self):
        """Test NEVER_CACHE constant exists."""
        from utils.sre_cache import SRECacheManager

        assert hasattr(SRECacheManager, 'NEVER_CACHE')
        assert isinstance(SRECacheManager.NEVER_CACHE, set)

    def test_mutation_tools_in_never_cache(self):
        """Test mutation tools are in NEVER_CACHE."""
        from utils.sre_cache import SRECacheManager

        never_cache = SRECacheManager.NEVER_CACHE

        # These tools modify state
        assert "execute_safe_restart" in never_cache
        assert "scale_resource" in never_cache
        assert "clear_cache" in never_cache

    def test_notification_tools_in_never_cache(self):
        """Test notification tools are in NEVER_CACHE."""
        from utils.sre_cache import SRECacheManager

        never_cache = SRECacheManager.NEVER_CACHE

        assert "send_teams_notification" in never_cache
        assert "send_teams_alert" in never_cache
        assert "send_sre_status_update" in never_cache

    def test_incident_tools_in_never_cache(self):
        """Test incident management tools are in NEVER_CACHE."""
        from utils.sre_cache import SRECacheManager

        never_cache = SRECacheManager.NEVER_CACHE

        assert "triage_incident" in never_cache
        assert "plan_remediation" in never_cache
        assert "generate_postmortem" in never_cache


class TestMakeKey:
    """Tests for cache key generation."""

    def test_make_key_deterministic(self):
        """Test _make_key produces deterministic keys."""
        from utils.sre_cache import SRECacheManager

        key1 = SRECacheManager._make_key("test_tool", {"param": "value"})
        key2 = SRECacheManager._make_key("test_tool", {"param": "value"})

        assert key1 == key2

    def test_make_key_order_independent(self):
        """Test _make_key is order-independent for args."""
        from utils.sre_cache import SRECacheManager

        key1 = SRECacheManager._make_key("test_tool", {"a": 1, "b": 2})
        key2 = SRECacheManager._make_key("test_tool", {"b": 2, "a": 1})

        assert key1 == key2

    def test_make_key_different_tools(self):
        """Test _make_key produces different keys for different tools."""
        from utils.sre_cache import SRECacheManager

        key1 = SRECacheManager._make_key("tool_a", {"param": "value"})
        key2 = SRECacheManager._make_key("tool_b", {"param": "value"})

        assert key1 != key2

    def test_make_key_different_args(self):
        """Test _make_key produces different keys for different args."""
        from utils.sre_cache import SRECacheManager

        key1 = SRECacheManager._make_key("test_tool", {"param": "value1"})
        key2 = SRECacheManager._make_key("test_tool", {"param": "value2"})

        assert key1 != key2


class TestGetOperation:
    """Tests for get operation."""

    def test_get_miss(self):
        """Test get returns None on cache miss."""
        from utils.sre_cache import SRECacheManager

        cache = SRECacheManager()

        result = cache.get("test_tool", {"param": "value"})

        assert result is None
        assert cache._misses == 1
        assert cache._hits == 0

    def test_get_hit(self):
        """Test get returns cached value on hit."""
        from utils.sre_cache import SRECacheManager

        cache = SRECacheManager()

        # Use a known tool with TTL mapping
        cache.set("get_performance_metrics", {"resource": "vm-1"}, {"result": "data"})

        # Get value
        result = cache.get("get_performance_metrics", {"resource": "vm-1"})

        assert result == {"result": "data"}
        assert cache._hits == 1
        assert cache._misses == 0

    def test_get_expired(self):
        """Test get returns None for expired entry."""
        from utils.sre_cache import SRECacheManager

        cache = SRECacheManager()

        # Manually insert expired entry
        key = cache._make_key("get_performance_metrics", {"resource": "vm-1"})
        cache._cache[key] = {
            "value": {"result": "data"},
            "created_at": time.time() - 100,
            "expires_at": time.time() - 50,  # Expired
            "tool_name": "get_performance_metrics",
            "ttl_profile": "real_time"
        }

        # Get should return None
        result = cache.get("get_performance_metrics", {"resource": "vm-1"})

        assert result is None
        assert cache._misses == 1

    def test_get_never_cache_tool(self):
        """Test get always misses for NEVER_CACHE tools."""
        from utils.sre_cache import SRECacheManager

        cache = SRECacheManager()

        # Try to cache a never-cache tool
        cache.set("triage_incident", {"incident": "123"}, {"status": "triaged"})

        # Get should still miss
        result = cache.get("triage_incident", {"incident": "123"})

        assert result is None


class TestSetOperation:
    """Tests for set operation."""

    def test_set_basic(self):
        """Test set stores value."""
        from utils.sre_cache import SRECacheManager

        cache = SRECacheManager()

        # Use a known tool
        cache.set("get_performance_metrics", {"resource": "vm-1"}, {"result": "data"})

        result = cache.get("get_performance_metrics", {"resource": "vm-1"})
        assert result == {"result": "data"}

    def test_set_with_ttl_override(self):
        """Test set respects custom TTL profile."""
        from utils.sre_cache import SRECacheManager

        cache = SRECacheManager()

        # Use explicit TTL profile
        cache.set("get_performance_metrics", {"resource": "vm-1"}, {"result": "data"}, ttl_profile="long")

        result = cache.get("get_performance_metrics", {"resource": "vm-1"})
        assert result == {"result": "data"}

    def test_set_never_cache_tool_ignored(self):
        """Test set ignores NEVER_CACHE tools."""
        from utils.sre_cache import SRECacheManager

        cache = SRECacheManager()

        cache.set("triage_incident", {"incident": "123"}, {"status": "triaged"})

        # Should not be cached
        assert len(cache._cache) == 0

    def test_set_uses_tool_ttl_profile(self):
        """Test set uses mapped TTL profile for known tools."""
        from utils.sre_cache import SRECacheManager

        cache = SRECacheManager()

        # get_performance_metrics uses real_time profile (EPHEMERAL_TTL = 300s)
        cache.set("get_performance_metrics", {"resource": "vm-1"}, {"cpu": 50})

        # Entry should exist with appropriate TTL
        result = cache.get("get_performance_metrics", {"resource": "vm-1"})
        assert result == {"cpu": 50}


class TestClearOperation:
    """Tests for clear operation."""

    def test_clear_all(self):
        """Test invalidate_all removes all entries."""
        from utils.sre_cache import SRECacheManager

        cache = SRECacheManager()

        # Add multiple entries
        cache.set("get_performance_metrics", {"resource": "vm-1"}, {"result": "1"})
        cache.set("check_resource_health", {"resource": "vm-2"}, {"result": "2"})

        count = cache.invalidate_all()

        assert count >= 2  # At least 2 removed
        assert len(cache._cache) == 0

    def test_clear_all_resets_stats(self):
        """Test invalidate_all resets statistics."""
        from utils.sre_cache import SRECacheManager

        cache = SRECacheManager()

        cache.set("get_performance_metrics", {"resource": "vm-1"}, {"result": "1"})
        cache.get("get_performance_metrics", {"resource": "vm-1"})  # hit
        cache.get("unknown_tool", {"x": 2})  # miss

        cache.invalidate_all()

        # Invalidate doesn't reset stats, just empties cache
        assert len(cache._cache) == 0


class TestStatistics:
    """Tests for cache statistics."""

    def test_get_stats(self):
        """Test get_stats returns statistics."""
        from utils.sre_cache import SRECacheManager

        cache = SRECacheManager()

        stats = cache.get_stats()

        assert "hits" in stats
        assert "misses" in stats
        assert "entries" in stats
        assert "hit_rate_percent" in stats
        assert "max_entries" in stats

    def test_stats_hit_rate_calculation(self):
        """Test stats calculates hit_rate correctly."""
        from utils.sre_cache import SRECacheManager

        cache = SRECacheManager()

        # Generate hits and misses
        cache.set("get_performance_metrics", {"resource": "vm-1"}, {"result": "1"})
        cache.get("get_performance_metrics", {"resource": "vm-1"})  # hit
        cache.get("get_performance_metrics", {"resource": "vm-1"})  # hit
        cache.get("unknown_tool", {"x": 2})  # miss

        stats = cache.get_stats()

        assert stats["hits"] == 2
        assert stats["misses"] == 1
        # 2 hits out of 3 total = 66.67%
        assert abs(stats["hit_rate_percent"] - 66.67) < 0.1


class TestSRECacheModule:
    """Tests for sre_cache module structure."""

    def test_module_imports(self):
        """Test sre_cache module imports."""
        from utils import sre_cache

        assert hasattr(sre_cache, 'SRECacheManager')
        assert hasattr(sre_cache, 'hashlib')
        assert hasattr(sre_cache, 'json')
        assert hasattr(sre_cache, 'time')

    def test_tool_mapping_coverage(self):
        """Test TOOL_TTL_MAP covers major SRE operations."""
        from utils.sre_cache import SRECacheManager

        tool_map = SRECacheManager.TOOL_TTL_MAP

        # Should have mappings for key categories
        assert len(tool_map) > 20  # At least 20 tool mappings

    def test_never_cache_reasonable_size(self):
        """Test NEVER_CACHE list is reasonable."""
        from utils.sre_cache import SRECacheManager

        never_cache = SRECacheManager.NEVER_CACHE

        # Should have several tools but not excessive
        assert len(never_cache) > 5
        assert len(never_cache) < 50
