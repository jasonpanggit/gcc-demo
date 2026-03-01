"""
Unit tests for cache_config.py - TTL centralization module.

Tests cover:
- CacheTTLProfile enum values
- Module-level TTL constants
- get_ttl() helper function
- TTL_PROFILE_MAP legacy dict
- Environment variable override behavior

Created: 2026-03-01 (Phase 3, Plan 04)
"""

import os
import importlib
import sys
import pytest


class TestCacheTTLProfileEnum:
    """Tests for CacheTTLProfile IntEnum values."""

    def test_ephemeral_is_300(self):
        """EPHEMERAL TTL is 5 minutes (300 seconds)."""
        from utils.cache_config import CacheTTLProfile
        assert CacheTTLProfile.EPHEMERAL == 300

    def test_short_lived_is_900(self):
        """SHORT_LIVED TTL is 15 minutes (900 seconds)."""
        from utils.cache_config import CacheTTLProfile
        assert CacheTTLProfile.SHORT_LIVED == 900

    def test_medium_lived_is_3600(self):
        """MEDIUM_LIVED TTL is 1 hour (3600 seconds)."""
        from utils.cache_config import CacheTTLProfile
        assert CacheTTLProfile.MEDIUM_LIVED == 3600

    def test_long_lived_is_86400(self):
        """LONG_LIVED TTL is 24 hours (86400 seconds)."""
        from utils.cache_config import CacheTTLProfile
        assert CacheTTLProfile.LONG_LIVED == 86400


class TestModuleLevelConstants:
    """Tests for module-level integer TTL constants."""

    def test_ephemeral_ttl_is_int(self):
        """EPHEMERAL_TTL module constant is an int."""
        from utils.cache_config import EPHEMERAL_TTL
        assert isinstance(EPHEMERAL_TTL, int)

    def test_short_lived_ttl_is_int(self):
        """SHORT_LIVED_TTL module constant is an int."""
        from utils.cache_config import SHORT_LIVED_TTL
        assert isinstance(SHORT_LIVED_TTL, int)

    def test_medium_lived_ttl_is_int(self):
        """MEDIUM_LIVED_TTL module constant is an int."""
        from utils.cache_config import MEDIUM_LIVED_TTL
        assert isinstance(MEDIUM_LIVED_TTL, int)

    def test_long_lived_ttl_is_int(self):
        """LONG_LIVED_TTL module constant is an int."""
        from utils.cache_config import LONG_LIVED_TTL
        assert isinstance(LONG_LIVED_TTL, int)

    def test_constants_match_enum(self):
        """Module constants match CacheTTLProfile enum values."""
        from utils.cache_config import (
            CacheTTLProfile,
            EPHEMERAL_TTL, SHORT_LIVED_TTL, MEDIUM_LIVED_TTL, LONG_LIVED_TTL,
        )
        assert EPHEMERAL_TTL == int(CacheTTLProfile.EPHEMERAL)
        assert SHORT_LIVED_TTL == int(CacheTTLProfile.SHORT_LIVED)
        assert MEDIUM_LIVED_TTL == int(CacheTTLProfile.MEDIUM_LIVED)
        assert LONG_LIVED_TTL == int(CacheTTLProfile.LONG_LIVED)


class TestGetTTLHelper:
    """Tests for get_ttl() convenience function."""

    def test_get_ttl_returns_int(self):
        """get_ttl returns an integer."""
        from utils.cache_config import get_ttl, CacheTTLProfile
        assert isinstance(get_ttl(CacheTTLProfile.SHORT_LIVED), int)

    def test_get_ttl_short_lived_returns_900(self):
        """get_ttl(SHORT_LIVED) returns 900."""
        from utils.cache_config import get_ttl, CacheTTLProfile
        assert get_ttl(CacheTTLProfile.SHORT_LIVED) == 900

    def test_get_ttl_all_profiles(self):
        """get_ttl works for all profiles."""
        from utils.cache_config import get_ttl, CacheTTLProfile
        assert get_ttl(CacheTTLProfile.EPHEMERAL) == 300
        assert get_ttl(CacheTTLProfile.SHORT_LIVED) == 900
        assert get_ttl(CacheTTLProfile.MEDIUM_LIVED) == 3600
        assert get_ttl(CacheTTLProfile.LONG_LIVED) == 86400


class TestEnvVarOverride:
    """Tests for environment variable overrides."""

    def test_env_var_override_ephemeral(self):
        """CACHE_TTL_EPHEMERAL env var overrides the EPHEMERAL value."""
        # Set env var, then reload the module to pick it up
        os.environ["CACHE_TTL_EPHEMERAL"] = "120"
        try:
            # Force module reload so the IntEnum re-reads os.getenv
            if "utils.cache_config" in sys.modules:
                del sys.modules["utils.cache_config"]
            from utils.cache_config import CacheTTLProfile
            assert CacheTTLProfile.EPHEMERAL == 120
        finally:
            del os.environ["CACHE_TTL_EPHEMERAL"]
            # Restore original module
            if "utils.cache_config" in sys.modules:
                del sys.modules["utils.cache_config"]
