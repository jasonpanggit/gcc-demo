"""
EOL-specific caching - MEMORY-ONLY layer for short-term acceleration.

CONSOLIDATION NOTE (January 2026):
    This module now provides MEMORY-ONLY caching. Cosmos DB persistence has been
    moved to `eol_inventory` which serves as the single source of truth for all
    EOL data. The orchestrator (eol_orchestrator.py) handles reads from and writes
    to eol_inventory.

    Agent-level caching via cosmos_cache has been disabled across all specialized
    agents (microsoft_agent, endoflife_agent, redhat_agent, etc.).

    This module is retained for:
    - In-memory acceleration of frequently accessed data
    - Backward compatibility with existing code that imports eol_cache
    - Cache statistics tracking

For persistent EOL data management, use `utils.eol_inventory` instead.
"""
import hashlib
import asyncio
import traceback
import time
from dataclasses import dataclass, asdict
from typing import Dict, Any, Optional
from datetime import datetime, timedelta, timezone

from .cosmos_cache import base_cosmos
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
        self.container = None
        self.cache_duration_days = 30
        self.min_confidence_threshold = 80.0
        self.memory_cache: Dict[str, CachedEOLResponse] = {}
        self.memory_lock = asyncio.Lock()
        self.initialized = False

        # Don't try to get container during __init__ to avoid startup Cosmos calls
        # Container will be obtained during async initialize() or first use

    async def initialize(self):
        """Ensure the base cosmos client is initialized and the container is available."""
        if self.initialized and self.container:
            return  # Already initialized
            
        try:
            await base_cosmos._initialize_async()
            if not self.container:  # Only get container if we don't have one
                self.container = base_cosmos.get_container(self.container_id)
            self.initialized = True
            logger.debug(f"EolMemoryCache initialized with container {self.container_id}")
        except Exception as e:
            logger.debug(f"EolMemoryCache initialize failed: {e}")

    def _ensure_container(self):
        """Ensure container is available, get it if needed"""
        if not self.container and base_cosmos.initialized:
            try:
                self.container = base_cosmos.get_container(self.container_id)
                self.initialized = True
            except Exception as e:
                logger.debug(f"Failed to get container {self.container_id}: {e}")

    def _generate_cache_key(self, software_name: str, version: Optional[str], agent_name: str) -> str:
        key_data = f"{agent_name}_{software_name}_{version or 'any'}".lower()
        return hashlib.md5(key_data.encode()).hexdigest()

    async def get_cached_response(self, software_name: str, version: Optional[str], agent_name: str):
        start_time = time.time()
        cache_key = self._generate_cache_key(software_name, version, agent_name)
        cache_hit = False
        
        # memory-first
        try:
            async with self.memory_lock:
                cached = self.memory_cache.get(cache_key)
            if cached:
                expires_at = safe_parse_datetime(cached.expires_at)
                if datetime.now(timezone.utc) <= expires_at and not getattr(cached, 'marked_as_failed', False):
                    cache_hit = True
                    
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

        # fallback to cosmos if available
        self._ensure_container()
        if not self.container:
            # Record cache miss statistics
            if cache_stats_manager:
                response_time = (time.time() - start_time) * 1000
                cache_stats_manager.record_agent_request(
                    agent_name=agent_name,
                    response_time_ms=response_time,
                    was_cache_hit=False
                )
            return None
            
        try:
            query = "SELECT * FROM c WHERE c.cache_key = @cache_key AND (c.marked_as_failed = false OR NOT IS_DEFINED(c.marked_as_failed))"
            params = [{"name": "@cache_key", "value": cache_key}]
            items = list(self.container.query_items(query=query, parameters=params, enable_cross_partition_query=True))
            if not items:
                # Record cache miss statistics
                if cache_stats_manager:
                    response_time = (time.time() - start_time) * 1000
                    cache_stats_manager.record_agent_request(
                        agent_name=agent_name,
                        response_time_ms=response_time,
                        was_cache_hit=False
                    )
                return None
                
            # pick best item
            items.sort(key=lambda x: (not x.get('verified', False), -x.get('confidence_level', 0)))
            best = items[0]
            cached = CachedEOLResponse.from_dict(best)
            expires_at = safe_parse_datetime(cached.expires_at)
            if datetime.now(timezone.utc) <= expires_at:
                cache_hit = True
                try:
                    async with self.memory_lock:
                        self.memory_cache[cache_key] = cached
                except Exception:
                    pass
                
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
                # cleanup expired item
                try:
                    self.container.delete_item(item=cached.id, partition_key=cached.cache_key)
                except Exception:
                    pass
                
                # Record cache miss statistics (expired)
                if cache_stats_manager:
                    response_time = (time.time() - start_time) * 1000
                    cache_stats_manager.record_agent_request(
                        agent_name=agent_name,
                        response_time_ms=response_time,
                        was_cache_hit=False
                    )
                
                return None
        except Exception as e:
            logger.debug(f"EolMemoryCache get_cached_response error: {e}")
            
            # Record error in statistics
            if cache_stats_manager:
                response_time = (time.time() - start_time) * 1000
                cache_stats_manager.record_agent_request(
                    agent_name=agent_name,
                    response_time_ms=response_time,
                    was_cache_hit=False,
                    had_error=True
                )
            
            return None

    async def cache_response(self, software_name: str, version: Optional[str], agent_name: str, response_data: Dict[str, Any], verified: bool = False, source_url: Optional[str] = None, verification_status: Optional[str] = None):
        """Memory-only caching - Cosmos persistence moved to eol_inventory (single source of truth)"""
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
            
            # Memory-only cache (Cosmos persistence handled by eol_inventory)
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
        """Clear memory cache only - Cosmos cache managed via eol_inventory"""
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
            
            return {"success": True, "deleted_count": deleted, "note": "Memory cache only - use eol_inventory for Cosmos cache management"}
        except Exception as e:
            logger.debug(f"EolMemoryCache clear_cache error: {e}")
            return {"success": False, "error": str(e)}

    async def get_cache_stats(self):
        self._ensure_container()
        if not self.container:
            return {"success": False, "error": "Container not available"}
        
        # Cache stats for 5 minutes to reduce Cosmos DB load
        cache_key = "eol_cache_stats"
        async with self.memory_lock:
            cached_stats = self.memory_cache.get(cache_key)
        
        if cached_stats:
            expires_at = safe_parse_datetime(cached_stats.expires_at)
            if datetime.now(timezone.utc) <= expires_at:
                return {
                    "success": True, 
                    "total_items": cached_stats.response_data.get("total_items", 0),
                    "expired_items": cached_stats.response_data.get("expired_items", 0), 
                    "active_items": cached_stats.response_data.get("active_items", 0),
                    "agent_breakdown": cached_stats.response_data.get("agent_breakdown", {}),
                    "cached": True,
                    "stats_cached_at": cached_stats.created_at
                }
        
        try:
            # Use simpler queries to avoid BadRequest errors
            logger.debug("Getting EOL cache statistics from Cosmos DB")
            
            # First try a simple count query without parameters
            total_query = "SELECT VALUE COUNT(1) FROM c"
            try:
                total_result = list(self.container.query_items(
                    query=total_query, 
                    enable_cross_partition_query=True
                ))
                total = total_result[0] if total_result else 0
                logger.debug(f"Total items query successful: {total}")
            except Exception as count_error:
                logger.warning(f"Failed to get total count, falling back to zero: {count_error}")
                total = 0
            
            # Try to get all documents and process expiration locally (more reliable)
            expired = 0
            breakdown = {}
            
            try:
                # Get a sample of documents to calculate breakdown and expiration
                sample_query = "SELECT c.agent_name, c.expires_at FROM c"
                sample_results = list(self.container.query_items(
                    query=sample_query, 
                    enable_cross_partition_query=True
                ))
                
                now = datetime.now(timezone.utc)
                agent_counts = {}
                
                for doc in sample_results:
                    # Count agent breakdown
                    agent_name = doc.get('agent_name', 'unknown')
                    agent_counts[agent_name] = agent_counts.get(agent_name, 0) + 1
                    
                    # Check expiration (handle various datetime formats)
                    expires_at_str = doc.get('expires_at')
                    if expires_at_str:
                        try:
                            expires_at = safe_parse_datetime(expires_at_str)
                            if expires_at and now > expires_at:
                                expired += 1
                        except Exception:
                            # Skip invalid dates
                            pass
                
                breakdown = agent_counts
                logger.debug(f"Processed {len(sample_results)} documents, expired: {expired}")
                
            except Exception as sample_error:
                logger.warning(f"Failed to get document sample for breakdown: {sample_error}")
                # Set basic fallback values
                breakdown = {}
                expired = 0
            
            stats_data = {
                "total_items": total, 
                "expired_items": expired, 
                "active_items": max(0, total - expired), 
                "agent_breakdown": breakdown
            }
            
            # Cache these stats for 5 minutes using EOL cache structure
            created = datetime.now(timezone.utc)
            expires = created + timedelta(minutes=5)
            cached_entry = CachedEOLResponse(
                id=cache_key,
                software_name='system-stats',
                version=None,
                agent_name='system',
                response_data=stats_data,
                confidence_level=1.0,
                created_at=created.isoformat(),
                expires_at=expires.isoformat(),
                cache_key=cache_key
            )
            
            async with self.memory_lock:
                self.memory_cache[cache_key] = cached_entry
            
            logger.info(f"✅ EOL cache stats retrieved successfully: {stats_data}")
            return {"success": True, **stats_data}
        except Exception as e:
            logger.error(f"❌ Failed to get EOL cache stats: {e}")
            logger.debug(f"🐛 EolMemoryCache get_cache_stats error: {e}")
            return {"success": False, "error": str(e)}

    # Convenience helpers used by other parts of the app (backwards compatibility)
    async def delete_cached_data(self, cache_key: str):
        """Delete a single cached item by cache_key/id."""
        self._ensure_container()
        if not self.container:
            return {"success": False, "error": "Container not available"}
        try:
            try:
                self.container.delete_item(item=cache_key, partition_key=cache_key)
            except Exception:
                # best-effort: try to query and delete by id
                try:
                    items = list(self.container.query_items(query="SELECT * FROM c WHERE c.cache_key = @cache_key", parameters=[{"name":"@cache_key","value":cache_key}], enable_cross_partition_query=True))
                    for it in items:
                        try:
                            self.container.delete_item(item=it['id'], partition_key=it.get('cache_key'))
                        except Exception:
                            pass
                except Exception:
                    pass

            # remove from memory cache
            try:
                async with self.memory_lock:
                    self.memory_cache.pop(cache_key, None)
            except Exception:
                pass

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
