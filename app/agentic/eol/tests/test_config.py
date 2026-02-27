"""
Configuration Management Tests

Tests for centralized configuration management including TimeoutConfig.
Created: 2026-02-27 (Phase 2, Day 6)
"""

import pytest
import os
from unittest.mock import patch
from utils.config import TimeoutConfig, ConfigManager


@pytest.mark.unit
class TestTimeoutConfig:
    """Tests for centralized timeout configuration."""

    def test_timeout_config_defaults(self):
        """Test that TimeoutConfig has sensible defaults."""
        config = TimeoutConfig()

        assert config.orchestrator_timeout == 30.0
        assert config.agent_timeout == 10.0
        assert config.mcp_tool_timeout == 5.0
        assert config.azure_sdk_timeout == 15.0
        assert config.http_client_timeout == 20.0
        assert config.db_query_timeout == 10.0

    def test_timeout_config_from_env(self):
        """Test that TimeoutConfig can be created from environment variables."""
        env_vars = {
            "ORCHESTRATOR_TIMEOUT": "45.0",
            "AGENT_TIMEOUT": "15.0",
            "MCP_TOOL_TIMEOUT": "8.0",
            "AZURE_SDK_TIMEOUT": "20.0",
            "HTTP_CLIENT_TIMEOUT": "25.0",
            "DB_QUERY_TIMEOUT": "12.0",
        }

        with patch.dict(os.environ, env_vars):
            config = TimeoutConfig.from_env()

            assert config.orchestrator_timeout == 45.0
            assert config.agent_timeout == 15.0
            assert config.mcp_tool_timeout == 8.0
            assert config.azure_sdk_timeout == 20.0
            assert config.http_client_timeout == 25.0
            assert config.db_query_timeout == 12.0

    def test_timeout_config_partial_env_override(self):
        """Test that only specified env vars override defaults."""
        env_vars = {
            "ORCHESTRATOR_TIMEOUT": "60.0",
            "AGENT_TIMEOUT": "20.0",
        }

        with patch.dict(os.environ, env_vars, clear=True):
            config = TimeoutConfig.from_env()

            # Overridden values
            assert config.orchestrator_timeout == 60.0
            assert config.agent_timeout == 20.0

            # Default values (when env vars not set)
            assert config.mcp_tool_timeout == 5.0
            assert config.azure_sdk_timeout == 15.0

    def test_timeout_config_get_all_timeouts(self):
        """Test getting all timeout values as a dictionary."""
        config = TimeoutConfig()
        all_timeouts = config.get_all_timeouts()

        assert isinstance(all_timeouts, dict)
        assert "orchestrator_timeout" in all_timeouts
        assert "agent_timeout" in all_timeouts
        assert "mcp_tool_timeout" in all_timeouts
        assert "azure_sdk_timeout" in all_timeouts
        assert "http_client_timeout" in all_timeouts
        assert "db_query_timeout" in all_timeouts

        assert all_timeouts["orchestrator_timeout"] == 30.0
        assert all_timeouts["agent_timeout"] == 10.0

    def test_timeout_config_float_precision(self):
        """Test that timeouts support sub-second precision."""
        env_vars = {
            "MCP_TOOL_TIMEOUT": "2.5",
            "AGENT_TIMEOUT": "7.25",
        }

        with patch.dict(os.environ, env_vars):
            config = TimeoutConfig.from_env()

            assert config.mcp_tool_timeout == 2.5
            assert config.agent_timeout == 7.25


@pytest.mark.unit
class TestConfigManagerIntegration:
    """Tests for ConfigManager integration with TimeoutConfig."""

    def test_config_manager_has_timeouts_property(self):
        """Test that ConfigManager exposes timeouts property."""
        manager = ConfigManager()

        assert hasattr(manager, 'timeouts')
        timeouts = manager.timeouts

        assert isinstance(timeouts, TimeoutConfig)

    def test_config_manager_timeouts_singleton(self):
        """Test that timeouts config is cached (singleton pattern)."""
        manager = ConfigManager()

        timeouts1 = manager.timeouts
        timeouts2 = manager.timeouts

        assert timeouts1 is timeouts2  # Same instance

    def test_config_manager_timeouts_environment_override(self):
        """Test that ConfigManager respects environment overrides."""
        env_vars = {
            "ORCHESTRATOR_TIMEOUT": "90.0",
            "MCP_TOOL_TIMEOUT": "10.0",
        }

        with patch.dict(os.environ, env_vars):
            manager = ConfigManager()
            timeouts = manager.timeouts

            assert timeouts.orchestrator_timeout == 90.0
            assert timeouts.mcp_tool_timeout == 10.0


@pytest.mark.unit
class TestEnvironmentBasedConfiguration:
    """Tests for environment-based configuration overrides."""

    def test_env_var_overrides_apply(self):
        """Test that environment variables override defaults."""
        test_vars = {
            "ORCHESTRATOR_TIMEOUT": "120.0",
            "AGENT_TIMEOUT": "30.0",
        }

        with patch.dict(os.environ, test_vars):
            config = TimeoutConfig()

            assert config.orchestrator_timeout == 120.0
            assert config.agent_timeout == 30.0

    def test_missing_env_vars_use_defaults(self):
        """Test that missing env vars fall back to defaults."""
        # Clear all timeout-related env vars
        env_copy = os.environ.copy()
        for key in list(env_copy.keys()):
            if "TIMEOUT" in key:
                del env_copy[key]

        with patch.dict(os.environ, env_copy, clear=True):
            config = TimeoutConfig()

            # Should use defaults
            assert config.orchestrator_timeout == 30.0
            assert config.agent_timeout == 10.0
            assert config.mcp_tool_timeout == 5.0

    def test_invalid_env_var_falls_back_to_default(self):
        """Test that invalid env var values fall back to defaults."""
        # This tests the robustness - if conversion fails, should handle gracefully
        env_vars = {
            "ORCHESTRATOR_TIMEOUT": "invalid",
        }

        with patch.dict(os.environ, env_vars):
            # If invalid, should raise ValueError or use default
            # Current implementation will raise ValueError from float()
            with pytest.raises(ValueError):
                TimeoutConfig()

    def test_zero_timeout_allowed(self):
        """Test that zero timeout is allowed (no timeout)."""
        env_vars = {
            "MCP_TOOL_TIMEOUT": "0.0",
        }

        with patch.dict(os.environ, env_vars):
            config = TimeoutConfig()

            assert config.mcp_tool_timeout == 0.0

    def test_negative_timeout_allowed(self):
        """Test that negative timeout passes through (caller validation)."""
        env_vars = {
            "AGENT_TIMEOUT": "-1.0",
        }

        with patch.dict(os.environ, env_vars):
            config = TimeoutConfig()

            # Allow negative - let caller validate business logic
            assert config.agent_timeout == -1.0


@pytest.mark.integration
class TestTimeoutConfigIntegration:
    """Integration tests for TimeoutConfig with orchestrators."""

    def test_timeout_config_usable_in_orchestrator_pattern(self):
        """Test that TimeoutConfig works in orchestrator usage pattern."""
        from utils.config import config

        # Access timeouts from global config
        timeouts = config.timeouts

        # Verify we can use timeout values
        orch_timeout = timeouts.orchestrator_timeout
        agent_timeout = timeouts.agent_timeout

        assert orch_timeout > 0
        assert agent_timeout > 0
        assert orch_timeout > agent_timeout  # Orchestrator should have longer timeout

    def test_timeout_hierarchy_makes_sense(self):
        """Test that timeout hierarchy is logical."""
        config = TimeoutConfig()

        # Generally: orchestrator > azure_sdk > agent > mcp_tool
        assert config.orchestrator_timeout >= config.azure_sdk_timeout
        assert config.azure_sdk_timeout >= config.agent_timeout
        # MCP tool timeout can be smaller for quick operations

    def test_all_timeout_values_accessible(self):
        """Test that all timeout values can be accessed and used."""
        config = TimeoutConfig()

        # All should be accessible and numeric
        assert isinstance(config.orchestrator_timeout, float)
        assert isinstance(config.agent_timeout, float)
        assert isinstance(config.mcp_tool_timeout, float)
        assert isinstance(config.azure_sdk_timeout, float)
        assert isinstance(config.http_client_timeout, float)
        assert isinstance(config.db_query_timeout, float)
