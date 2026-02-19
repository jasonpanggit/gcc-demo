"""
Test Suite for Inventory Feature Flags System
Tests feature flag lifecycle, rollout stages, circuit breaker, and rollback.
"""
import os
import time
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# Helpers: import under controlled env to avoid singleton leakage
# ---------------------------------------------------------------------------

def _fresh_flags(**env_overrides):
    """Create a fresh InventoryFeatureFlags instance with optional env vars."""
    from utils.inventory_feature_flags import InventoryFeatureFlags
    with patch.dict(os.environ, env_overrides, clear=False):
        return InventoryFeatureFlags()


@pytest.mark.unit
class TestInventoryFeatureConstants:
    """Verify feature name constants and stage mappings."""

    def test_feature_names_defined(self):
        from utils.inventory_feature_flags import InventoryFeature
        assert InventoryFeature.DISCOVERY == "inventory_discovery"
        assert InventoryFeature.READS == "inventory_reads"
        assert InventoryFeature.PARAMETER_RESOLUTION == "inventory_parameter_resolution"
        assert InventoryFeature.FAST_PATH == "inventory_fast_path"
        assert len(InventoryFeature.ALL) == 4

    def test_rollout_stage_enum(self):
        from utils.inventory_feature_flags import RolloutStage
        assert int(RolloutStage.DISCOVERY_ONLY) == 1
        assert int(RolloutStage.FULL_ACTIVATION) == 4


@pytest.mark.unit
class TestFeatureFlagDefaults:
    """Validate default flag states without env overrides."""

    def test_default_states(self):
        """Discovery enabled by default, others disabled."""
        flags = _fresh_flags()
        from utils.inventory_feature_flags import InventoryFeature
        assert flags.is_feature_enabled(InventoryFeature.DISCOVERY) is True
        assert flags.is_feature_enabled(InventoryFeature.READS) is False
        assert flags.is_feature_enabled(InventoryFeature.PARAMETER_RESOLUTION) is False
        assert flags.is_feature_enabled(InventoryFeature.FAST_PATH) is False

    def test_default_rollout_stage(self):
        flags = _fresh_flags()
        assert flags.get_rollout_stage() == 1

    def test_unknown_feature_returns_false(self):
        flags = _fresh_flags()
        assert flags.is_feature_enabled("nonexistent_feature") is False


@pytest.mark.unit
class TestEnvironmentOverrides:
    """Individual env var overrides."""

    def test_enable_reads_via_env(self):
        from utils.inventory_feature_flags import InventoryFeature
        flags = _fresh_flags(INVENTORY_ENABLE_READS="true")
        assert flags.is_feature_enabled(InventoryFeature.READS) is True

    def test_disable_discovery_via_env(self):
        from utils.inventory_feature_flags import InventoryFeature
        flags = _fresh_flags(INVENTORY_ENABLE_DISCOVERY="false")
        assert flags.is_feature_enabled(InventoryFeature.DISCOVERY) is False

    def test_enable_all_via_env(self):
        from utils.inventory_feature_flags import InventoryFeature
        flags = _fresh_flags(
            INVENTORY_ENABLE_DISCOVERY="true",
            INVENTORY_ENABLE_READS="true",
            INVENTORY_ENABLE_PARAMETER_RESOLUTION="true",
            INVENTORY_ENABLE_FAST_PATH="true",
        )
        for feat in InventoryFeature.ALL:
            assert flags.is_feature_enabled(feat) is True
        assert flags.get_rollout_stage() == 4


@pytest.mark.unit
class TestRolloutStageEnv:
    """Stage-based activation via INVENTORY_ROLLOUT_STAGE env var."""

    def test_stage_1_env(self):
        from utils.inventory_feature_flags import InventoryFeature
        flags = _fresh_flags(INVENTORY_ROLLOUT_STAGE="1")
        assert flags.is_feature_enabled(InventoryFeature.DISCOVERY) is True
        assert flags.is_feature_enabled(InventoryFeature.READS) is False
        assert flags.get_rollout_stage() == 1

    def test_stage_2_env(self):
        from utils.inventory_feature_flags import InventoryFeature
        flags = _fresh_flags(INVENTORY_ROLLOUT_STAGE="2")
        assert flags.is_feature_enabled(InventoryFeature.DISCOVERY) is True
        assert flags.is_feature_enabled(InventoryFeature.READS) is True
        assert flags.is_feature_enabled(InventoryFeature.PARAMETER_RESOLUTION) is False
        assert flags.get_rollout_stage() == 2

    def test_stage_3_env(self):
        from utils.inventory_feature_flags import InventoryFeature
        flags = _fresh_flags(INVENTORY_ROLLOUT_STAGE="3")
        assert flags.is_feature_enabled(InventoryFeature.PARAMETER_RESOLUTION) is True
        assert flags.is_feature_enabled(InventoryFeature.FAST_PATH) is False
        assert flags.get_rollout_stage() == 3

    def test_stage_4_env(self):
        from utils.inventory_feature_flags import InventoryFeature
        flags = _fresh_flags(INVENTORY_ROLLOUT_STAGE="4")
        for feat in InventoryFeature.ALL:
            assert flags.is_feature_enabled(feat) is True
        assert flags.get_rollout_stage() == 4

    def test_stage_clamped_high(self):
        """Stages above 4 are clamped to 4."""
        flags = _fresh_flags(INVENTORY_ROLLOUT_STAGE="99")
        assert flags.get_rollout_stage() == 4

    def test_stage_clamped_low(self):
        """Stages below 1 are clamped to 1."""
        flags = _fresh_flags(INVENTORY_ROLLOUT_STAGE="0")
        assert flags.get_rollout_stage() == 1

    def test_stage_overrides_individual_flags(self):
        """Stage env takes precedence over individual flag env vars."""
        from utils.inventory_feature_flags import InventoryFeature
        flags = _fresh_flags(
            INVENTORY_ROLLOUT_STAGE="1",
            INVENTORY_ENABLE_FAST_PATH="true",  # Should be ignored
        )
        assert flags.is_feature_enabled(InventoryFeature.FAST_PATH) is False

    def test_invalid_stage_falls_back_to_flags(self):
        """Non-numeric stage falls back to individual env vars."""
        from utils.inventory_feature_flags import InventoryFeature
        flags = _fresh_flags(
            INVENTORY_ROLLOUT_STAGE="invalid",
            INVENTORY_ENABLE_READS="true",
        )
        assert flags.is_feature_enabled(InventoryFeature.READS) is True


@pytest.mark.unit
class TestEnableDisable:
    """Programmatic enable/disable with audit logging."""

    def test_enable_feature(self):
        from utils.inventory_feature_flags import InventoryFeature
        flags = _fresh_flags()
        assert flags.is_feature_enabled(InventoryFeature.READS) is False
        flags.enable_feature(InventoryFeature.READS, reason="test")
        assert flags.is_feature_enabled(InventoryFeature.READS) is True

    def test_disable_feature(self):
        from utils.inventory_feature_flags import InventoryFeature
        flags = _fresh_flags()
        assert flags.is_feature_enabled(InventoryFeature.DISCOVERY) is True
        flags.disable_feature(InventoryFeature.DISCOVERY, reason="maintenance")
        assert flags.is_feature_enabled(InventoryFeature.DISCOVERY) is False

    def test_state_change_recorded(self):
        from utils.inventory_feature_flags import InventoryFeature
        flags = _fresh_flags()
        flags.enable_feature(InventoryFeature.READS, reason="rollout")
        metrics = flags.get_feature_metrics(InventoryFeature.READS)
        assert len(metrics["state_changes"]) >= 1
        last = metrics["state_changes"][-1]
        assert last["old_state"] is False
        assert last["new_state"] is True
        assert "rollout" in last["reason"]


@pytest.mark.unit
class TestSetRolloutStage:
    """Programmatic stage transitions."""

    def test_set_stage_2(self):
        from utils.inventory_feature_flags import InventoryFeature
        flags = _fresh_flags()
        flags.set_rollout_stage(2, reason="validated")
        assert flags.is_feature_enabled(InventoryFeature.READS) is True
        assert flags.is_feature_enabled(InventoryFeature.PARAMETER_RESOLUTION) is False
        assert flags.get_rollout_stage() == 2

    def test_set_stage_4_then_1(self):
        from utils.inventory_feature_flags import InventoryFeature
        flags = _fresh_flags()
        flags.set_rollout_stage(4)
        assert flags.get_rollout_stage() == 4
        flags.set_rollout_stage(1, reason="rollback")
        assert flags.get_rollout_stage() == 1
        assert flags.is_feature_enabled(InventoryFeature.FAST_PATH) is False

    def test_set_stage_records_changes(self):
        from utils.inventory_feature_flags import InventoryFeature
        flags = _fresh_flags()
        flags.set_rollout_stage(3)
        metrics = flags.get_feature_metrics(InventoryFeature.READS)
        changes = metrics["state_changes"]
        assert any("stage_change_to_3" in c.get("reason", "") for c in changes)


@pytest.mark.unit
class TestMonitoringMetrics:
    """Success/failure tracking and metric queries."""

    def test_record_success(self):
        from utils.inventory_feature_flags import InventoryFeature
        flags = _fresh_flags()
        flags.record_success(InventoryFeature.DISCOVERY, latency_ms=12.5)
        m = flags.get_feature_metrics(InventoryFeature.DISCOVERY)
        assert m["successes"] == 1
        assert m["total_calls"] == 1
        assert m["error_rate_percent"] == 0.0
        assert m["avg_latency_ms"] == 12.5

    def test_record_failure(self):
        from utils.inventory_feature_flags import InventoryFeature
        flags = _fresh_flags()
        flags.record_failure(InventoryFeature.DISCOVERY, latency_ms=50.0)
        m = flags.get_feature_metrics(InventoryFeature.DISCOVERY)
        assert m["failures"] == 1
        assert m["error_rate_percent"] == 100.0
        assert m["last_failure_time"] is not None

    def test_error_rate_calculation(self):
        from utils.inventory_feature_flags import InventoryFeature
        flags = _fresh_flags()
        for _ in range(8):
            flags.record_success(InventoryFeature.DISCOVERY)
        for _ in range(2):
            flags.record_failure(InventoryFeature.DISCOVERY)
        m = flags.get_feature_metrics(InventoryFeature.DISCOVERY)
        assert m["error_rate_percent"] == 20.0
        assert m["total_calls"] == 10

    def test_get_all_metrics(self):
        from utils.inventory_feature_flags import InventoryFeature
        flags = _fresh_flags()
        result = flags.get_all_metrics()
        assert "rollout_stage" in result
        assert "features" in result
        assert len(result["features"]) == 4
        for feat in InventoryFeature.ALL:
            assert feat in result["features"]

    def test_get_flags_summary(self):
        from utils.inventory_feature_flags import InventoryFeature
        flags = _fresh_flags()
        summary = flags.get_flags_summary()
        assert isinstance(summary, dict)
        assert len(summary) == 4
        assert summary[InventoryFeature.DISCOVERY] is True
        assert summary[InventoryFeature.READS] is False

    def test_unknown_feature_metrics(self):
        flags = _fresh_flags()
        m = flags.get_feature_metrics("unknown_feature")
        assert "error" in m


@pytest.mark.unit
class TestCircuitBreaker:
    """Automatic disable on high error rates."""

    def test_circuit_opens_above_threshold(self):
        """Circuit breaker opens after error rate exceeds threshold (min 10 calls)."""
        from utils.inventory_feature_flags import InventoryFeature
        flags = _fresh_flags()
        # Need >= 10 calls to trip. 9 failures + 1 success = 90% error > 5%
        for _ in range(9):
            flags.record_failure(InventoryFeature.DISCOVERY)
        # After 9 calls, threshold not evaluated (< 10 calls)
        assert flags.is_feature_enabled(InventoryFeature.DISCOVERY) is True
        # 10th call: now error_rate = 90% > 5%
        flags.record_failure(InventoryFeature.DISCOVERY)
        assert flags.is_feature_enabled(InventoryFeature.DISCOVERY) is False
        m = flags.get_feature_metrics(InventoryFeature.DISCOVERY)
        assert m["circuit_open"] is True

    def test_circuit_does_not_open_below_threshold(self):
        """Error rate below threshold keeps feature enabled."""
        from utils.inventory_feature_flags import InventoryFeature
        # 1% error threshold: need high failures to trip at 5% default
        flags = _fresh_flags()
        for _ in range(96):
            flags.record_success(InventoryFeature.DISCOVERY)
        for _ in range(4):
            flags.record_failure(InventoryFeature.DISCOVERY)
        # 4% error rate < 5% threshold
        assert flags.is_feature_enabled(InventoryFeature.DISCOVERY) is True

    def test_circuit_resets_after_cooldown(self):
        """Circuit breaker resets after the cooldown interval."""
        from utils.inventory_feature_flags import InventoryFeature
        flags = _fresh_flags()
        flags.CIRCUIT_BREAKER_RESET_INTERVAL = 0.1  # 100ms for fast test

        # Trip the breaker
        for _ in range(10):
            flags.record_failure(InventoryFeature.DISCOVERY)
        assert flags.is_feature_enabled(InventoryFeature.DISCOVERY) is False

        # Wait past cooldown
        time.sleep(0.15)
        assert flags.is_feature_enabled(InventoryFeature.DISCOVERY) is True

    def test_explicit_enable_resets_circuit(self):
        """Calling enable_feature resets the circuit breaker."""
        from utils.inventory_feature_flags import InventoryFeature
        flags = _fresh_flags()
        for _ in range(10):
            flags.record_failure(InventoryFeature.DISCOVERY)
        assert flags.is_feature_enabled(InventoryFeature.DISCOVERY) is False

        flags.enable_feature(InventoryFeature.DISCOVERY, reason="manual_override")
        assert flags.is_feature_enabled(InventoryFeature.DISCOVERY) is True

    def test_custom_error_threshold_env(self):
        """Custom threshold via INVENTORY_ERROR_THRESHOLD env var."""
        from utils.inventory_feature_flags import InventoryFeature
        flags = _fresh_flags(INVENTORY_ERROR_THRESHOLD="50.0")
        # 40% error rate should NOT trip at 50% threshold
        for _ in range(6):
            flags.record_success(InventoryFeature.DISCOVERY)
        for _ in range(4):
            flags.record_failure(InventoryFeature.DISCOVERY)
        assert flags.is_feature_enabled(InventoryFeature.DISCOVERY) is True


@pytest.mark.unit
class TestRollback:
    """Emergency rollback and metric reset."""

    def test_rollback_all(self):
        from utils.inventory_feature_flags import InventoryFeature
        flags = _fresh_flags()
        flags.set_rollout_stage(4)
        assert flags.get_rollout_stage() == 4

        flags.rollback_all(reason="incident")
        assert flags.get_rollout_stage() == 1
        assert flags.is_feature_enabled(InventoryFeature.DISCOVERY) is True
        assert flags.is_feature_enabled(InventoryFeature.READS) is False
        assert flags.is_feature_enabled(InventoryFeature.FAST_PATH) is False

    def test_reset_metrics_single(self):
        from utils.inventory_feature_flags import InventoryFeature
        flags = _fresh_flags()
        flags.record_success(InventoryFeature.DISCOVERY, latency_ms=10.0)
        flags.record_failure(InventoryFeature.READS, latency_ms=20.0)

        flags.reset_metrics(InventoryFeature.DISCOVERY)

        m_disc = flags.get_feature_metrics(InventoryFeature.DISCOVERY)
        assert m_disc["total_calls"] == 0
        assert m_disc["successes"] == 0

        m_reads = flags.get_feature_metrics(InventoryFeature.READS)
        assert m_reads["total_calls"] == 1  # Not reset

    def test_reset_metrics_all(self):
        from utils.inventory_feature_flags import InventoryFeature
        flags = _fresh_flags()
        for feat in InventoryFeature.ALL:
            flags.record_success(feat)
        flags.reset_metrics()
        for feat in InventoryFeature.ALL:
            m = flags.get_feature_metrics(feat)
            assert m["total_calls"] == 0


@pytest.mark.unit
class TestSingleton:
    """Module-level singleton accessor."""

    def test_singleton_returns_same_instance(self):
        from utils.inventory_feature_flags import get_inventory_feature_flags
        # Reset singleton for isolation
        import utils.inventory_feature_flags as mod
        mod._instance = None

        a = get_inventory_feature_flags()
        b = get_inventory_feature_flags()
        assert a is b

        # Clean up
        mod._instance = None
