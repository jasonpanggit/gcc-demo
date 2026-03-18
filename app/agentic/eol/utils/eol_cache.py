"""
EOL-specific caching - MEMORY-ONLY layer for short-term acceleration.

CONSOLIDATION NOTE (January 2026):
    This module provides MEMORY-ONLY caching. Persistent storage has been
    moved to `eol_inventory` which serves as the single source of truth for all
    EOL data. The orchestrator (eol_orchestrator.py) handles reads from and writes
    to eol_inventory.

    Agent-level caching has been removed across all specialized
    agents (microsoft_agent, endoflife_agent, redhat_agent, etc.).

    This module is retained for:
    - In-memory acceleration of frequently accessed data
    - Backward compatibility with existing code that imports eol_cache
    - Cache statistics tracking

For persistent EOL data management, use `utils.eol_inventory` instead.
"""
import hashlib
import asyncio
import time
from dataclasses import dataclass, asdict
from typing import Dict, Any, Optional
from datetime import datetime, timedelta, timezone

from .helpers import safe_parse_datetime
import logging

# Import cache statistics manager for performance tracking
try:
    from .cache_stats_manager import cache_stats_manager
except ImportError:
    cache_stats_manager = None

logger = logging.getLogger(__name__)


@dataclass
class CachedEOLResponse:
    id: str
    software_name: str
    version: Optional[str]
    agent_name: str
    response_data: Dict[str, Any]
    confidence_level: float
    created_at: str
    expires_at: str
    cache_key: str
    verified: bool = False
    source_url: Optional[str] = None
    verification_status: Optional[str] = None
    marked_as_failed: bool = False

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]):
        filtered = {k: v for k, v in data.items() if not k.startswith('_') and k != 'ttl'}
        return cls(**filtered)


class EolMemoryCache:
    def __init__(self, container_id: str = 'eol_cache'):
        self.container_id = container_id
        self.cache_duration_days = 30
        self.min_confidence_threshold = 80.0
        self.memory_cache: Dict[str, CachedEOLResponse] = {}
        self.memory_lock = asyncio.Lock()
        self.initialized = True  # Always initialized (memory-only)

    async def initialize(self):
        """No-op — memory-only cache is always ready."""
        self.initialized = True

    def _generate_cache_key(self, software_name: str, version: Optional[str], agent_name: str) -> str:
        key_data = f"{agent_name}_{software_name}_{version or 'any'}".lower()
        return hashlib.md5(key_data.encode()).hexdigest()

    async def get_cached_response(self, software_name: str, version: Optional[str], agent_name: str):
        start_time = time.time()
        cache_key = self._generate_cache_key(software_name, version, agent_name)

        # memory-only lookup
        try:
            async with self.memory_lock:
                cached = self.memory_cache.get(cache_key)
            if cached:
                expires_at = safe_parse_datetime(cached.expires_at)
                if datetime.now(timezone.utc) <= expires_at and not getattr(cached, 'marked_as_failed', False):
                    # Record cache hit statistics
                    if cache_stats_manager:
                        response_time = (time.time() - start_time) * 1000
                        cache_stats_manager.record_agent_request(
                            agent_name=agent_name,
                            response_time_ms=response_time,
                            was_cache_hit=True
                        )

                    return cached.response_data
                else:
                    async with self.memory_lock:
                        self.memory_cache.pop(cache_key, None)
        except Exception:
            pass

        # Record cache miss statistics
        if cache_stats_manager:
            response_time = (time.time() - start_time) * 1000
            cache_stats_manager.record_agent_request(
                agent_name=agent_name,
                response_time_ms=response_time,
                was_cache_hit=False
            )
        return None

    async def cache_response(self, software_name: str, version: Optional[str], agent_name: str, response_data: Dict[str, Any], verified: bool = False, source_url: Optional[str] = None, verification_status: Optional[str] = None):
        """Memory-only caching - persistent storage handled by eol_inventory (single source of truth)"""
        try:
            # simple confidence extraction
            confidence = response_data.get('confidence') or response_data.get('confidence_level') or response_data.get('confidence_score') or 0
            try:
                confidence = float(confidence)
                if confidence <= 1.0:
                    confidence *= 100
            except Exception:
                confidence = 0

            cache_key = self._generate_cache_key(software_name, version, agent_name)
            created = datetime.now(timezone.utc)
            expires = created + timedelta(days=self.cache_duration_days)
            cached = CachedEOLResponse(
                id=cache_key,
                software_name=software_name,
                version=version,
                agent_name=agent_name,
                response_data=response_data,
                confidence_level=confidence,
                created_at=created.isoformat(),
                expires_at=expires.isoformat(),
                cache_key=cache_key,
                verified=verified,
                source_url=source_url,
                verification_status=verification_status,
                marked_as_failed=(verification_status == 'failed')
            )

            # Memory-only cache
            try:
                async with self.memory_lock:
                    self.memory_cache[cache_key] = cached
            except Exception:
                pass
            return True
        except Exception as e:
            logger.debug(f"EolMemoryCache cache_response error: {e}")
            return False

    async def clear_cache(self, software_name: Optional[str] = None, agent_name: Optional[str] = None):
        """Clear memory cache"""
        try:
            deleted = 0
            keys_to_remove = []

            async with self.memory_lock:
                for cache_key, cached in list(self.memory_cache.items()):
                    match = True
                    if software_name and cached.software_name != software_name:
                        match = False
                    if agent_name and cached.agent_name != agent_name:
                        match = False
                    if match:
                        keys_to_remove.append(cache_key)

                for key in keys_to_remove:
                    self.memory_cache.pop(key, None)
                    deleted += 1

            return {"success": True, "deleted_count": deleted, "note": "Memory cache only - use eol_inventory for persistent data management"}
        except Exception as e:
            logger.debug(f"EolMemoryCache clear_cache error: {e}")
            return {"success": False, "error": str(e)}

    async def get_cache_stats(self):
        """Return memory cache statistics."""
        try:
            now = datetime.now(timezone.utc)
            total = 0
            expired = 0
            breakdown = {}

            async with self.memory_lock:
                for cache_key, cached in self.memory_cache.items():
                    if cache_key == "eol_cache_stats":
                        continue
                    total += 1
                    agent_name = cached.agent_name
                    breakdown[agent_name] = breakdown.get(agent_name, 0) + 1
                    expires_at = safe_parse_datetime(cached.expires_at)
                    if expires_at and now > expires_at:
                        expired += 1

            return {
                "success": True,
                "total_items": total,
                "expired_items": expired,
                "active_items": max(0, total - expired),
                "agent_breakdown": breakdown,
                "storage": "memory_only"
            }
        except Exception as e:
            logger.debug(f"EolMemoryCache get_cache_stats error: {e}")
            return {"success": False, "error": str(e)}

    # Convenience helpers used by other parts of the app (backwards compatibility)
    async def delete_cached_data(self, cache_key: str):
        """Delete a single cached item by cache_key/id."""
        try:
            async with self.memory_lock:
                self.memory_cache.pop(cache_key, None)
            return {"success": True, "deleted": True}
        except Exception as e:
            logger.debug(f"EolMemoryCache delete_cached_data error: {e}")
            return {"success": False, "error": str(e)}

    async def purge_agent_cache(self, agent_name: str):
        """Purge all cache entries for a given agent by delegating to clear_cache."""
        return await self.clear_cache(agent_name=agent_name)

    async def delete_failed_cache_entry(self, software_name: str, version: Optional[str], agent_name: str):
        """Delete cache entries for a software/agent (used when verification fails)."""
        # delegate to clear_cache which supports software_name and agent_name filters
        return await self.clear_cache(software_name=software_name, agent_name=agent_name)


# Singleton
eol_cache = EolMemoryCache()
