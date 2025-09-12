"""
OS inventory cache built on top of base_cosmos.
Stores OS inventory query results.
"""
import hashlib
import json
import asyncio
from dataclasses import dataclass, asdict
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta, timezone

from .cosmos_cache import base_cosmos
from .helpers import safe_parse_datetime
import logging

logger = logging.getLogger(__name__)


@dataclass
class CachedInventoryData:
    id: str
    cache_type: str
    agent_name: str
    query_params: Dict[str, Any]
    data: List[Dict[str, Any]]
    data_count: int
    created_at: str
    expires_at: str
    cache_key: str
    workspace_id: str

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]):
        filtered = {k: v for k, v in data.items() if not k.startswith('_') and k != 'ttl'}
        return cls(**filtered)


class OsInventoryMemoryCache:
    def __init__(self, container_id: str = 'inventory_os'):
        self.container_id = container_id
        self.container = None
        self.cache_duration_hours = 4
        self.memory_cache: Dict[str, CachedInventoryData] = {}
        self.memory_lock = asyncio.Lock()
        self.initialized = False

        # Don't try to get container during __init__ to avoid startup Cosmos calls
        # Container will be obtained during async initialize() or first use

    async def initialize(self):
        """Async initializer to ensure base_cosmos is initialized and container is available."""
        if self.initialized and self.container:
            return  # Already initialized
            
        try:
            await base_cosmos._initialize_async()
            if not self.container:  # Only get container if we don't have one
                self.container = base_cosmos.get_container(self.container_id)
            self.initialized = True
            logger.debug(f"OsInventoryMemoryCache initialized with container {self.container_id}")
        except Exception as e:
            logger.debug(f"OsInventoryMemoryCache initialize failed: {e}")

    def _ensure_container(self):
        """Ensure container is available, get it if needed"""
        # If we already have a container, verify it's still valid
        if self.container:
            logger.debug(f"Container {self.container_id} already available")
            return
            
        # Only get container if base_cosmos is initialized
        if not base_cosmos.initialized:
            logger.debug(f"Base cosmos not initialized, cannot get container {self.container_id}")
            return
            
        try:
            logger.debug(f"Getting container {self.container_id} from base_cosmos")
            self.container = base_cosmos.get_container(self.container_id)
            self.initialized = True
            logger.debug(f"Successfully obtained container {self.container_id}")
        except Exception as e:
            logger.debug(f"Failed to get container {self.container_id}: {e}")
            self.container = None

    def _generate_cache_key(self, agent_name: str, query_params: Dict[str, Any], workspace_id: str) -> str:
        sorted_params = json.dumps(query_params, sort_keys=True)
        key_data = f"os_{agent_name}_{sorted_params}_{workspace_id}".lower()
        return hashlib.md5(key_data.encode()).hexdigest()

    async def get_cached_data(self, agent_name: str, query_params: Dict[str, Any], workspace_id: str) -> Optional[Dict[str, Any]]:
        self._ensure_container()
        if not self.container:
            return None
        cache_key = self._generate_cache_key(agent_name, query_params, workspace_id)
        try:
            async with self.memory_lock:
                cached = self.memory_cache.get(cache_key)
            if cached:
                expires_at = safe_parse_datetime(cached.expires_at)
                if datetime.now(timezone.utc) <= expires_at:
                    return {"success": True, "data": cached.data, "count": cached.data_count, "cached_at": cached.created_at, "expires_at": cached.expires_at}
                else:
                    async with self.memory_lock:
                        self.memory_cache.pop(cache_key, None)
        except Exception:
            pass

        try:
            query = "SELECT * FROM c WHERE c.cache_key = @cache_key"
            params = [{"name": "@cache_key", "value": cache_key}]
            items = list(self.container.query_items(query=query, parameters=params, enable_cross_partition_query=True))
            if not items:
                return None
            cached = CachedInventoryData.from_dict(items[0])
            expires_at = safe_parse_datetime(cached.expires_at)
            if datetime.now(timezone.utc) <= expires_at:
                try:
                    async with self.memory_lock:
                        self.memory_cache[cache_key] = cached
                except Exception:
                    pass
                return {"success": True, "data": cached.data, "count": cached.data_count, "cached_at": cached.created_at, "expires_at": cached.expires_at}
            else:
                try:
                    self.container.delete_item(item=cached.id, partition_key=cached.cache_key)
                except Exception:
                    pass
                return None
        except Exception as e:
            logger.debug(f"OsInventoryMemoryCache error: {e}")
            return None

    async def cache_data(self, agent_name: str, query_params: Dict[str, Any], workspace_id: str, data: List[Dict[str, Any]]) -> bool:
        self._ensure_container()
        if not self.container:
            return False
        if not data:
            return False
        try:
            cache_key = self._generate_cache_key(agent_name, query_params, workspace_id)
            created = datetime.now(timezone.utc)
            expires = created + timedelta(hours=self.cache_duration_hours)
            cached = CachedInventoryData(id=cache_key, cache_type='os', agent_name=agent_name, query_params=query_params, data=data, data_count=len(data), created_at=created.isoformat(), expires_at=expires.isoformat(), cache_key=cache_key, workspace_id=workspace_id)
            self.container.upsert_item(cached.to_dict())
            try:
                async with self.memory_lock:
                    self.memory_cache[cache_key] = cached
            except Exception:
                pass
            return True
        except Exception as e:
            logger.debug(f"OsInventoryMemoryCache cache_data error: {e}")
            return False

    async def clear_cache(self, agent_name: Optional[str] = None) -> Dict[str, Any]:
        self._ensure_container()
        if not self.container:
            return {"success": False, "error": "Container not available"}
        try:
            query_parts = ["SELECT * FROM c WHERE 1=1"]
            params = []
            if agent_name:
                query_parts.append("AND c.agent_name = @agent_name")
                params.append({"name": "@agent_name", "value": agent_name})
            query = " ".join(query_parts)
            items = list(self.container.query_items(query=query, parameters=params, enable_cross_partition_query=True))
            deleted = 0
            for it in items:
                try:
                    self.container.delete_item(item=it['id'], partition_key=it['cache_key'])
                    deleted += 1
                    try:
                        async with self.memory_lock:
                            self.memory_cache.pop(it.get('cache_key'), None)
                    except Exception:
                        pass
                except Exception:
                    pass
            return {"success": True, "deleted_count": deleted}
        except Exception as e:
            logger.debug(f"OsInventoryMemoryCache clear_cache error: {e}")
            return {"success": False, "error": str(e)}

    async def get_cache_stats(self):
        self._ensure_container()
        if not self.container:
            return {"success": False, "error": "Container not available"}
        
        # Cache stats for 5 minutes to reduce Cosmos DB load
        cache_key = "os_cache_stats"
        async with self.memory_lock:
            cached_stats = self.memory_cache.get(cache_key)
        
        if cached_stats:
            expires_at = safe_parse_datetime(cached_stats.expires_at)
            if datetime.now(timezone.utc) <= expires_at:
                return {
                    "success": True, 
                    "total_items": cached_stats.data.get("total_items", 0),
                    "expired_items": cached_stats.data.get("expired_items", 0), 
                    "active_items": cached_stats.data.get("active_items", 0),
                    "type_breakdown": cached_stats.data.get("type_breakdown", {"os": 0}),
                    "agent_breakdown": cached_stats.data.get("agent_breakdown", {}),
                    "cached": True,
                    "stats_cached_at": cached_stats.created_at
                }
        
        try:
            # More efficient stats query - combine counts in single query
            now = datetime.now(timezone.utc).isoformat()
            
            # Get total and expired counts in one efficient query
            stats_query = """
            SELECT 
                COUNT(1) as total_count,
                SUM(CASE WHEN c.expires_at < @now THEN 1 ELSE 0 END) as expired_count
            FROM c
            """
            stats_result = list(self.container.query_items(
                query=stats_query, 
                parameters=[{"name":"@now","value":now}], 
                enable_cross_partition_query=True
            ))[0]
            
            total = stats_result['total_count']
            expired = stats_result['expired_count']
            
            # Get agent breakdown efficiently - only distinct agent names with counts
            agent_query = """
            SELECT c.agent_name, COUNT(1) as count
            FROM c 
            GROUP BY c.agent_name
            """
            agent_results = list(self.container.query_items(query=agent_query, enable_cross_partition_query=True))
            breakdown = {result['agent_name']: result['count'] for result in agent_results}
            
            stats_data = {
                "total_items": total, 
                "expired_items": expired, 
                "active_items": total-expired, 
                "type_breakdown": {"os": total}, 
                "agent_breakdown": breakdown
            }
            
            # Cache these stats for 5 minutes
            created = datetime.now(timezone.utc)
            expires = created + timedelta(minutes=5)
            cached_entry = CachedInventoryData(
                id=cache_key,
                cache_type='stats',
                agent_name='system',
                query_params={},
                data=stats_data,
                data_count=1,
                created_at=created.isoformat(),
                expires_at=expires.isoformat(),
                cache_key=cache_key,
                workspace_id='global'
            )
            
            async with self.memory_lock:
                self.memory_cache[cache_key] = cached_entry
            
            return {"success": True, **stats_data}
        except Exception as e:
            logger.debug(f"OsInventoryMemoryCache get_cache_stats error: {e}")
            return {"success": False, "error": str(e)}


# Singleton
os_inventory_cache = OsInventoryMemoryCache()
