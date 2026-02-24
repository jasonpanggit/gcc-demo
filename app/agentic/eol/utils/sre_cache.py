"""
SRE Cache Manager - TTL-based caching for SRE MCP server tools.

Provides in-memory caching with configurable TTL profiles to reduce
redundant Azure API calls and improve response times.
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
from typing import Any, Dict, Optional

try:
    from app.agentic.eol.utils.logger import get_logger
except ModuleNotFoundError:
    from utils.logger import get_logger  # type: ignore[import-not-found]

logger = get_logger(__name__)


class SRECacheManager:
    """TTL-based in-memory cache for SRE tool results."""

    TTL_PROFILES: Dict[str, int] = {
        "real_time": 60,       # 1 min  - performance metrics
        "short": 300,          # 5 min  - health checks, alerts
        "medium": 1800,        # 30 min - config analysis, costs
        "long": 3600,          # 1 hr   - dependencies, SLOs
        "daily": 86400,        # 24 hr  - security score, compliance
    }

    # Map tool names to their default TTL profile
    TOOL_TTL_MAP: Dict[str, str] = {
        # Real-time (1 min)
        "get_performance_metrics": "real_time",
        "identify_bottlenecks": "real_time",
        "detect_metric_anomalies": "real_time",
        # Short (5 min)
        "check_resource_health": "short",
        "check_container_app_health": "short",
        "check_aks_cluster_health": "short",
        "correlate_alerts": "short",
        "get_request_telemetry": "short",
        # Medium (30 min)
        "analyze_resource_configuration": "medium",
        "get_cost_analysis": "medium",
        "get_cost_recommendations": "medium",
        "analyze_cost_anomalies": "medium",
        "query_app_service_configuration": "medium",
        "query_container_app_configuration": "medium",
        "query_aks_configuration": "medium",
        "query_apim_configuration": "medium",
        # Long (1 hr)
        "get_resource_dependencies": "long",
        "get_slo_dashboard": "long",
        "analyze_dependency_map": "long",
        "calculate_error_budget": "long",
        "predict_resource_exhaustion": "long",
        # Daily (24 hr)
        "get_security_score": "daily",
        "check_compliance_status": "daily",
        "list_security_recommendations": "daily",
        "identify_orphaned_resources": "daily",
        "describe_capabilities": "daily",
    }

    # Tools that should NEVER be cached (mutations, notifications, unique operations)
    NEVER_CACHE: set = {
        "triage_incident",
        "plan_remediation",
        "execute_safe_restart",
        "execute_restart_resource",
        "scale_resource",
        "execute_scale_resource",
        "clear_cache",
        "execute_clear_redis_cache",
        "send_teams_notification",
        "send_teams_alert",
        "send_sre_status_update",
        "define_slo",
        "generate_incident_summary",
        "generate_postmortem",
        "execute_automation_runbook",
        "create_incident_ticket",
        "get_audit_trail",
    }

    def __init__(self, max_entries: int = 500) -> None:
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.RLock()
        self._max_entries = max_entries
        self._hits = 0
        self._misses = 0

    @staticmethod
    def _make_key(tool_name: str, args: Dict[str, Any]) -> str:
        """Generate a deterministic cache key from tool name and arguments."""
        # Sort args for deterministic hashing, exclude context-like params
        filtered = {k: v for k, v in sorted(args.items())
                    if k not in ("context", "ctx", "_context")}
        args_str = json.dumps(filtered, sort_keys=True, default=str)
        args_hash = hashlib.md5(args_str.encode()).hexdigest()[:12]
        return f"{tool_name}:{args_hash}"

    def get(self, tool_name: str, args: Dict[str, Any]) -> Optional[Any]:
        """
        Retrieve a cached result if available and not expired.

        Returns:
            Cached value or None if miss/expired
        """
        if tool_name in self.NEVER_CACHE:
            return None

        key = self._make_key(tool_name, args)

        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                self._misses += 1
                return None

            if time.time() > entry["expires_at"]:
                # Expired — remove and return miss
                del self._cache[key]
                self._misses += 1
                return None

            self._hits += 1
            logger.debug(
                "SRE cache HIT for %s (key=%s, age=%.0fs)",
                tool_name, key[:20], time.time() - entry["created_at"]
            )
            return entry["value"]

    def set(
        self,
        tool_name: str,
        args: Dict[str, Any],
        value: Any,
        ttl_profile: Optional[str] = None,
    ) -> None:
        """
        Cache a tool result with TTL.

        Args:
            tool_name: Name of the SRE tool
            args: Tool arguments (used for cache key)
            value: Result to cache
            ttl_profile: Override TTL profile (defaults to TOOL_TTL_MAP lookup)
        """
        if tool_name in self.NEVER_CACHE:
            return

        profile = ttl_profile or self.TOOL_TTL_MAP.get(tool_name)
        if not profile:
            return  # Tool not configured for caching

        ttl_seconds = self.TTL_PROFILES.get(profile, 300)
        key = self._make_key(tool_name, args)
        now = time.time()

        with self._lock:
            # Evict oldest entries if at capacity
            if len(self._cache) >= self._max_entries:
                self._evict_expired()
                if len(self._cache) >= self._max_entries:
                    self._evict_oldest(count=self._max_entries // 10)

            self._cache[key] = {
                "value": value,
                "created_at": now,
                "expires_at": now + ttl_seconds,
                "tool_name": tool_name,
                "ttl_profile": profile,
            }

    def invalidate(self, tool_name: str, args: Optional[Dict[str, Any]] = None) -> int:
        """
        Invalidate cache entries for a tool.

        Args:
            tool_name: Tool to invalidate
            args: Specific args to invalidate (None = all entries for tool)

        Returns:
            Number of entries removed
        """
        removed = 0
        with self._lock:
            if args is not None:
                key = self._make_key(tool_name, args)
                if key in self._cache:
                    del self._cache[key]
                    removed = 1
            else:
                keys_to_remove = [
                    k for k, v in self._cache.items()
                    if v.get("tool_name") == tool_name
                ]
                for k in keys_to_remove:
                    del self._cache[k]
                removed = len(keys_to_remove)

        if removed:
            logger.debug("SRE cache invalidated %d entries for %s", removed, tool_name)
        return removed

    def invalidate_all(self) -> int:
        """Clear all cache entries. Returns count of removed entries."""
        with self._lock:
            count = len(self._cache)
            self._cache.clear()
            self._hits = 0
            self._misses = 0
        logger.info("SRE cache cleared (%d entries removed)", count)
        return count

    def _evict_expired(self) -> int:
        """Remove all expired entries."""
        now = time.time()
        expired_keys = [
            k for k, v in self._cache.items()
            if now > v["expires_at"]
        ]
        for k in expired_keys:
            del self._cache[k]
        return len(expired_keys)

    def _evict_oldest(self, count: int = 10) -> None:
        """Remove the N oldest entries by creation time."""
        sorted_entries = sorted(
            self._cache.items(),
            key=lambda item: item[1]["created_at"]
        )
        for key, _ in sorted_entries[:count]:
            del self._cache[key]

    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        with self._lock:
            total = self._hits + self._misses
            hit_rate = (self._hits / total * 100) if total > 0 else 0.0
            return {
                "entries": len(self._cache),
                "max_entries": self._max_entries,
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate_percent": round(hit_rate, 1),
                "ttl_profiles": dict(self.TTL_PROFILES),
            }


# Module-level singleton
_sre_cache: Optional[SRECacheManager] = None
_cache_lock = threading.Lock()


def get_sre_cache() -> SRECacheManager:
    """Get or create the SRE cache singleton."""
    global _sre_cache
    if _sre_cache is None:
        with _cache_lock:
            if _sre_cache is None:
                _sre_cache = SRECacheManager()
    return _sre_cache
