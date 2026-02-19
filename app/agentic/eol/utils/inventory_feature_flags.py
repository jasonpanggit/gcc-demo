"""
Inventory Feature Flag System - Controlled rollout for resource inventory features.

Provides staged rollout with monitoring, automatic rollback on high error rates,
and environment-variable-based overrides for quick enable/disable.

Rollout Stages:
    Stage 1: Discovery only (populate cache, validation)
    Stage 2: Read queries enabled (compare with direct API)
    Stage 3: Parameter resolution enabled (monitor errors)
    Stage 4: Full activation (fast-path enabled)

Environment Variables:
    INVENTORY_ENABLE_DISCOVERY          - Enable background discovery (default: true)
    INVENTORY_ENABLE_READS              - Enable read queries from inventory (default: false)
    INVENTORY_ENABLE_PARAMETER_RESOLUTION - Enable auto-population (default: false)
    INVENTORY_ENABLE_FAST_PATH          - Enable fast-path existence checks (default: false)
    INVENTORY_ROLLOUT_STAGE             - Set rollout stage directly (1-4, overrides flags)
    INVENTORY_ERROR_THRESHOLD           - Auto-disable threshold % (default: 5.0)
"""

from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import IntEnum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Feature names
# ---------------------------------------------------------------------------

class InventoryFeature:
    """Feature name constants."""
    DISCOVERY = "inventory_discovery"
    READS = "inventory_reads"
    PARAMETER_RESOLUTION = "inventory_parameter_resolution"
    FAST_PATH = "inventory_fast_path"

    ALL = [
        "inventory_discovery",
        "inventory_reads",
        "inventory_parameter_resolution",
        "inventory_fast_path",
    ]


# ---------------------------------------------------------------------------
# Rollout stages
# ---------------------------------------------------------------------------

class RolloutStage(IntEnum):
    """Controlled rollout stages mapping features to activation level."""
    DISCOVERY_ONLY = 1
    READS_ENABLED = 2
    PARAMETER_RESOLUTION = 3
    FULL_ACTIVATION = 4


# Stage -> which features are active at that stage
_STAGE_FEATURES: Dict[int, List[str]] = {
    1: [InventoryFeature.DISCOVERY],
    2: [InventoryFeature.DISCOVERY, InventoryFeature.READS],
    3: [InventoryFeature.DISCOVERY, InventoryFeature.READS,
        InventoryFeature.PARAMETER_RESOLUTION],
    4: InventoryFeature.ALL,
}

# Environment variable -> feature mapping
_ENV_FEATURE_MAP: Dict[str, str] = {
    "INVENTORY_ENABLE_DISCOVERY": InventoryFeature.DISCOVERY,
    "INVENTORY_ENABLE_READS": InventoryFeature.READS,
    "INVENTORY_ENABLE_PARAMETER_RESOLUTION": InventoryFeature.PARAMETER_RESOLUTION,
    "INVENTORY_ENABLE_FAST_PATH": InventoryFeature.FAST_PATH,
}

# Default states per feature (when no stage or env override)
_DEFAULT_STATES: Dict[str, bool] = {
    InventoryFeature.DISCOVERY: True,
    InventoryFeature.READS: False,
    InventoryFeature.PARAMETER_RESOLUTION: False,
    InventoryFeature.FAST_PATH: False,
}


# ---------------------------------------------------------------------------
# Per-feature metrics tracker
# ---------------------------------------------------------------------------

@dataclass
class _FeatureMetrics:
    """Tracks success/failure rates for a single feature."""
    successes: int = 0
    failures: int = 0
    total_calls: int = 0
    total_latency_ms: float = 0.0
    last_failure_time: Optional[float] = None
    circuit_open: bool = False
    circuit_opened_at: Optional[float] = None
    state_changes: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def error_rate_percent(self) -> float:
        if self.total_calls == 0:
            return 0.0
        return (self.failures / self.total_calls) * 100.0

    @property
    def avg_latency_ms(self) -> float:
        if self.total_calls == 0:
            return 0.0
        return self.total_latency_ms / self.total_calls


# ---------------------------------------------------------------------------
# InventoryFeatureFlags
# ---------------------------------------------------------------------------

class InventoryFeatureFlags:
    """Feature flag manager for inventory system rollout.

    Supports:
      - Per-feature enable/disable via environment variables
      - Stage-based activation (1-4)
      - Automatic circuit-breaker on high error rates
      - Monitoring metrics per feature
      - Rollback via env var or API call
    """

    # Circuit breaker reset interval (seconds)
    CIRCUIT_BREAKER_RESET_INTERVAL = 300  # 5 minutes

    def __init__(self, error_threshold: float = 5.0) -> None:
        self._lock = threading.RLock()
        self._error_threshold = float(
            os.getenv("INVENTORY_ERROR_THRESHOLD", str(error_threshold))
        )

        # Feature state: True = enabled, False = disabled
        self._flags: Dict[str, bool] = {}
        # Metrics per feature
        self._metrics: Dict[str, _FeatureMetrics] = {
            feat: _FeatureMetrics() for feat in InventoryFeature.ALL
        }

        # Initialise from environment / stage
        self._load_from_environment()
        logger.info(
            "InventoryFeatureFlags initialised: stage=%s flags=%s threshold=%.1f%%",
            self.get_rollout_stage(),
            {k: v for k, v in self._flags.items()},
            self._error_threshold,
        )

    # ---- initialisation ----------------------------------------------------

    def _load_from_environment(self) -> None:
        """Load flag states from environment variables.

        Priority: INVENTORY_ROLLOUT_STAGE > individual env vars > defaults.
        """
        stage_env = os.getenv("INVENTORY_ROLLOUT_STAGE")
        if stage_env is not None:
            try:
                stage = int(stage_env)
                stage = max(1, min(4, stage))
                active_features = _STAGE_FEATURES.get(stage, [])
                for feat in InventoryFeature.ALL:
                    self._flags[feat] = feat in active_features
                return
            except ValueError:
                logger.warning(
                    "Invalid INVENTORY_ROLLOUT_STAGE='%s', falling back to individual flags",
                    stage_env,
                )

        # Per-feature env overrides
        for env_var, feat in _ENV_FEATURE_MAP.items():
            env_val = os.getenv(env_var)
            if env_val is not None:
                self._flags[feat] = env_val.lower() in ("true", "1", "yes")
            else:
                self._flags[feat] = _DEFAULT_STATES[feat]

    # ---- public API --------------------------------------------------------

    def is_feature_enabled(self, feature_name: str) -> bool:
        """Check if a feature is currently active.

        Returns False if:
          - The flag is disabled
          - The circuit breaker is open (high error rate)
        """
        with self._lock:
            if feature_name not in self._flags:
                return False

            if not self._flags[feature_name]:
                return False

            # Check circuit breaker
            metrics = self._metrics.get(feature_name)
            if metrics and metrics.circuit_open:
                # Auto-reset after cooldown
                if (metrics.circuit_opened_at and
                        time.time() - metrics.circuit_opened_at > self.CIRCUIT_BREAKER_RESET_INTERVAL):
                    metrics.circuit_open = False
                    metrics.circuit_opened_at = None
                    metrics.successes = 0
                    metrics.failures = 0
                    metrics.total_calls = 0
                    metrics.total_latency_ms = 0.0
                    logger.info("Circuit breaker reset for feature '%s'", feature_name)
                else:
                    return False

            return True

    def enable_feature(self, feature_name: str, reason: str = "") -> None:
        """Enable a feature flag with audit logging."""
        with self._lock:
            was_enabled = self._flags.get(feature_name, False)
            self._flags[feature_name] = True

            # Reset circuit breaker on explicit enable
            metrics = self._metrics.get(feature_name)
            if metrics:
                metrics.circuit_open = False
                metrics.circuit_opened_at = None

            if not was_enabled:
                self._record_state_change(feature_name, False, True, reason)
                logger.info(
                    "Feature '%s' ENABLED%s",
                    feature_name,
                    f" (reason: {reason})" if reason else "",
                )

    def disable_feature(self, feature_name: str, reason: str = "") -> None:
        """Disable a feature flag with audit logging."""
        with self._lock:
            was_enabled = self._flags.get(feature_name, False)
            self._flags[feature_name] = False

            if was_enabled:
                self._record_state_change(feature_name, True, False, reason)
                logger.info(
                    "Feature '%s' DISABLED%s",
                    feature_name,
                    f" (reason: {reason})" if reason else "",
                )

    def get_rollout_stage(self) -> int:
        """Determine current effective rollout stage based on active flags.

        Returns the highest stage whose required features are all enabled (1-4).
        """
        with self._lock:
            current_stage = 0
            for stage in sorted(_STAGE_FEATURES.keys()):
                required = _STAGE_FEATURES[stage]
                if all(self._flags.get(f, False) for f in required):
                    current_stage = stage
                else:
                    break
            return max(current_stage, 1)

    def set_rollout_stage(self, stage: int, reason: str = "") -> None:
        """Activate all features up to the given stage, disable higher ones."""
        stage = max(1, min(4, stage))
        active_features = _STAGE_FEATURES.get(stage, [])
        with self._lock:
            for feat in InventoryFeature.ALL:
                should_enable = feat in active_features
                old = self._flags.get(feat, False)
                self._flags[feat] = should_enable
                if old != should_enable:
                    self._record_state_change(
                        feat, old, should_enable,
                        f"stage_change_to_{stage}" + (f": {reason}" if reason else ""),
                    )
        logger.info("Rollout stage set to %d%s", stage, f" ({reason})" if reason else "")

    # ---- monitoring --------------------------------------------------------

    def record_success(self, feature_name: str, latency_ms: float = 0.0) -> None:
        """Record a successful operation for a feature."""
        with self._lock:
            m = self._metrics.get(feature_name)
            if m is None:
                return
            m.successes += 1
            m.total_calls += 1
            m.total_latency_ms += latency_ms

    def record_failure(self, feature_name: str, latency_ms: float = 0.0) -> None:
        """Record a failed operation and check circuit breaker threshold."""
        with self._lock:
            m = self._metrics.get(feature_name)
            if m is None:
                return
            m.failures += 1
            m.total_calls += 1
            m.total_latency_ms += latency_ms
            m.last_failure_time = time.time()

            # Evaluate circuit breaker (min 10 calls before tripping)
            if m.total_calls >= 10 and m.error_rate_percent > self._error_threshold:
                if not m.circuit_open:
                    m.circuit_open = True
                    m.circuit_opened_at = time.time()
                    self._record_state_change(
                        feature_name, True, False,
                        f"circuit_breaker: error_rate={m.error_rate_percent:.1f}% > {self._error_threshold}%",
                    )
                    logger.warning(
                        "Circuit breaker OPENED for '%s': %.1f%% error rate (%d/%d calls)",
                        feature_name, m.error_rate_percent, m.failures, m.total_calls,
                    )

    def get_feature_metrics(self, feature_name: str) -> Dict[str, Any]:
        """Get monitoring metrics for a specific feature."""
        with self._lock:
            m = self._metrics.get(feature_name)
            if m is None:
                return {"error": f"Unknown feature: {feature_name}"}
            return {
                "feature": feature_name,
                "enabled": self._flags.get(feature_name, False),
                "circuit_open": m.circuit_open,
                "successes": m.successes,
                "failures": m.failures,
                "total_calls": m.total_calls,
                "error_rate_percent": round(m.error_rate_percent, 2),
                "avg_latency_ms": round(m.avg_latency_ms, 2),
                "last_failure_time": (
                    datetime.fromtimestamp(m.last_failure_time, tz=timezone.utc).isoformat()
                    if m.last_failure_time else None
                ),
                "state_changes": m.state_changes[-10:],  # Last 10 changes
            }

    def get_all_metrics(self) -> Dict[str, Any]:
        """Get comprehensive status across all features."""
        with self._lock:
            return {
                "rollout_stage": self.get_rollout_stage(),
                "error_threshold_percent": self._error_threshold,
                "circuit_breaker_reset_seconds": self.CIRCUIT_BREAKER_RESET_INTERVAL,
                "features": {
                    feat: self.get_feature_metrics(feat)
                    for feat in InventoryFeature.ALL
                },
            }

    def get_flags_summary(self) -> Dict[str, bool]:
        """Get a simple dict of feature name -> enabled status."""
        with self._lock:
            return {
                feat: self.is_feature_enabled(feat)
                for feat in InventoryFeature.ALL
            }

    # ---- rollback ----------------------------------------------------------

    def rollback_all(self, reason: str = "manual_rollback") -> None:
        """Emergency rollback: disable everything except discovery."""
        self.set_rollout_stage(1, reason=reason)
        logger.warning("ROLLBACK: All features disabled except discovery (%s)", reason)

    def reset_metrics(self, feature_name: Optional[str] = None) -> None:
        """Reset monitoring counters. If feature_name is None, resets all."""
        with self._lock:
            targets = [feature_name] if feature_name else InventoryFeature.ALL
            for feat in targets:
                m = self._metrics.get(feat)
                if m:
                    m.successes = 0
                    m.failures = 0
                    m.total_calls = 0
                    m.total_latency_ms = 0.0
                    m.circuit_open = False
                    m.circuit_opened_at = None
                    # Keep state_changes for audit trail

    # ---- internal ----------------------------------------------------------

    def _record_state_change(
        self, feature: str, old: bool, new: bool, reason: str
    ) -> None:
        """Append an auditable state-change record."""
        m = self._metrics.get(feature)
        if m is None:
            return
        m.state_changes.append({
            "feature": feature,
            "old_state": old,
            "new_state": new,
            "reason": reason,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_instance: Optional[InventoryFeatureFlags] = None
_instance_lock = threading.Lock()


def get_inventory_feature_flags() -> InventoryFeatureFlags:
    """Get or create the InventoryFeatureFlags singleton."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = InventoryFeatureFlags()
    return _instance
