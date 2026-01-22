"""
Unified Inventory Cache - Handles both software and OS inventory with memory + Cosmos DB persistence
"""
import json
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from .cosmos_cache import BaseCosmosClient

# Import Cosmos DB exceptions for proper error handling
try:
    from azure.cosmos.exceptions import CosmosResourceNotFoundError
    COSMOS_EXCEPTIONS_AVAILABLE = True
except ImportError:
    # Fallback if Cosmos SDK not available
    CosmosResourceNotFoundError = None
    COSMOS_EXCEPTIONS_AVAILABLE = False

class InventoryRawCache:
    """
    Unified cache for inventory data (software and OS) with memory + Cosmos DB persistence.
    Supports separate containers for different cache types with 4-hour cache duration.
    """
    
    def __init__(self, cosmos_client: BaseCosmosClient, cache_duration_hours: int = 4):
        """
        Initialize the unified inventory cache.
        
        Args:
            cosmos_client: BaseCosmosClient instance for Cosmos DB operations
            cache_duration_hours: Cache duration in hours (default: 4 hours)
        """
        self.cosmos_client = cosmos_client
        self.cache_duration = timedelta(hours=cache_duration_hours)
        
        # Memory cache for frequently accessed data
        self._memory_cache: Dict[str, Dict[str, Any]] = {}
        
        # Container mappings for different cache types
        self.container_mapping = {
            "software": "inventory_software",
            "os": "inventory_os"
        }
        
        # print(f"[InventoryRawCache] Initialized unified cache with {cache_duration_hours}h duration")
        # print(f"[InventoryRawCache] Container mapping: {self.container_mapping}")
    
    async def initialize(self):
        """
        Initialize the inventory cache - ensures containers are created when needed.
        This method now uses lazy initialization to avoid unnecessary container requests.
        """
        try:
            # Ensure base cosmos client is initialized
            if not self.cosmos_client.initialized:
                await self.cosmos_client._initialize_async()
            
            # Don't pre-create containers during initialization to avoid unnecessary requests
            # Containers will be created on first use via the cached get_container() method
            if self.cosmos_client.initialized:
                print(f"[InventoryRawCache] Initialization complete - containers will be created on demand")
            else:
                print(f"[InventoryRawCache] Cosmos DB not available - cache will use memory only")
                
        except Exception as e:
            print(f"[InventoryRawCache] Initialization error: {e}")
    
    def _get_container_name(self, cache_type: str) -> str:
        """Get the appropriate container name for the cache type."""
        return self.container_mapping.get(cache_type, f"inventory_{cache_type}")
    
    def _get_memory_key(self, cache_type: str, cache_key: str) -> str:
        """Generate memory cache key combining cache type and key."""
        return f"{cache_type}:{cache_key}"
    
    def _is_cache_valid(self, timestamp_str: str) -> bool:
        """Check if cache entry is still valid based on timestamp."""
        try:
            cache_time = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
            current_time = datetime.now(cache_time.tzinfo) if cache_time.tzinfo else datetime.now()
            return current_time - cache_time < self.cache_duration
        except Exception as e:
            print(f"[InventoryRawCache] Error parsing timestamp {timestamp_str}: {e}")
            return False
    
    def get_cached_data(self, cache_key: str, cache_type: str = "software") -> Optional[List[Dict]]:
        """
        Retrieve cached inventory data with memory + Cosmos DB fallback.
        
        Args:
            cache_key: Unique identifier for the cached data
            cache_type: Type of cache ("software" or "os")
            
        Returns:
            Cached data if valid, None otherwise
        """
        result = self.get_cached_data_with_metadata(cache_key, cache_type)
        return result['data'] if result else None
    
    def get_cached_data_with_metadata(self, cache_key: str, cache_type: str = "software") -> Optional[Dict]:
        """
        Retrieve cached inventory data with metadata including timestamp.
        
        Args:
            cache_key: Unique identifier for the cached data
            cache_type: Type of cache ("software" or "os")
            
        Returns:
            Dict with 'data' and 'timestamp' if valid, None otherwise
        """
        memory_key = self._get_memory_key(cache_type, cache_key)
        container_name = self._get_container_name(cache_type)
        
        # print(f"[InventoryRawCache] Retrieving {cache_type} cache for key: {cache_key}")
        
        # Check memory cache first
        if memory_key in self._memory_cache:
            memory_entry = self._memory_cache[memory_key]
            if self._is_cache_valid(memory_entry['timestamp']):
                data_size = len(memory_entry['data']) if memory_entry['data'] else 0
                # print(f"[InventoryRawCache] Memory cache HIT - {data_size} records")
                return {
                    'data': memory_entry['data'],
                    'timestamp': memory_entry['timestamp'],
                    'metadata': memory_entry.get('metadata')
                }
            else:
                # print(f"[InventoryRawCache] Memory cache EXPIRED - removing entry")
                del self._memory_cache[memory_key]
        
        # Fallback to Cosmos DB
        # print(f"[InventoryRawCache] Checking Cosmos DB container: {container_name}")
        
        # Check if Cosmos DB is available
        if not self.cosmos_client.initialized:
            # print(f"[InventoryRawCache] Cosmos DB not initialized - cache miss")
            return None
            
        start_time = time.time()
        
        try:
            # Query for the cache document by ID
            query = "SELECT * FROM c WHERE c.id = @cache_key"
            params = [{"name": "@cache_key", "value": cache_key}]
            # Use the cached get_container method to avoid repeated container creation requests
            container = self.cosmos_client.get_container(container_name)
            items = list(container.query_items(query=query, parameters=params, enable_cross_partition_query=True))
            
            if items and self._is_cache_valid(items[0].get('timestamp', '')):
                cache_doc = items[0]
                data = cache_doc.get('data', [])
                data_size = len(data) if data else 0
                cosmos_time = time.time() - start_time
                
                # print(f"[InventoryRawCache] Cosmos DB cache HIT - {data_size} records ({cosmos_time:.2f}s)")
                
                # Update memory cache
                self._memory_cache[memory_key] = {
                    'data': data,
                    'timestamp': cache_doc.get('timestamp'),
                    'metadata': cache_doc.get('metadata')
                }
                # print(f"[InventoryRawCache] Updated memory cache with {data_size} records")
                
                return {
                    'data': data,
                    'timestamp': cache_doc.get('timestamp'),
                    'metadata': cache_doc.get('metadata')
                }
            else:
                cosmos_time = time.time() - start_time
                # print(f"[InventoryRawCache] Cosmos DB cache MISS/EXPIRED ({cosmos_time:.2f}s)")
                return None
                
        except Exception as e:
            cosmos_time = time.time() - start_time
            print(f"[InventoryRawCache] Cosmos DB error ({cosmos_time:.2f}s): {e}")
            return None
    
    def store_cached_data(self, cache_key: str, data: List[Dict], cache_type: str = "software", metadata: Optional[Dict[str, Any]] = None) -> bool:
        """
        Store inventory data in both memory and Cosmos DB cache.
        
        Args:
            cache_key: Unique identifier for the cached data
            data: Inventory data to cache
            cache_type: Type of cache ("software" or "os")
            
        Returns:
            True if successfully stored, False otherwise
        """
        memory_key = self._get_memory_key(cache_type, cache_key)
        container_name = self._get_container_name(cache_type)
        timestamp = datetime.now().isoformat()
        data_size = len(data) if data else 0
        
        # print(f"[InventoryRawCache] Storing {cache_type} cache - {data_size} records")
        
        # Store in memory cache
        self._memory_cache[memory_key] = {
            'data': data,
            'timestamp': timestamp,
            'metadata': metadata
        }
        # print(f"[InventoryRawCache] Memory cache updated with {data_size} records")
        
        # Store in Cosmos DB
        cache_doc = {
            'id': cache_key,
            'cache_type': cache_type,
            'data': data,
            'timestamp': timestamp,
            'record_count': data_size,
            'metadata': metadata
        }
        
        # Check if Cosmos DB is available
        if not self.cosmos_client.initialized:
            # print(f"[InventoryRawCache] Cosmos DB not initialized - memory cache only")
            return True  # Memory cache was successful
        
        start_time = time.time()
        try:
            container = self.cosmos_client.get_container(container_name)
            result = container.upsert_item(cache_doc)
            cosmos_time = time.time() - start_time
            
            if result:
                # print(f"[InventoryRawCache] Cosmos DB storage SUCCESS - {data_size} records ({cosmos_time:.2f}s)")
                return True
            else:
                print(f"[InventoryRawCache] Cosmos DB storage FAILED ({cosmos_time:.2f}s)")
                return False
                
        except Exception as e:
            cosmos_time = time.time() - start_time
            print(f"[InventoryRawCache] Cosmos DB storage ERROR ({cosmos_time:.2f}s): {e}")
            return False
    
    def clear_cache(self, cache_key: str, cache_type: str = "software") -> bool:
        """
        Clear cached data from both memory and Cosmos DB.
        
        Args:
            cache_key: Unique identifier for the cached data to clear
            cache_type: Type of cache ("software" or "os")
            
        Returns:
            True if successfully cleared, False otherwise
        """
        memory_key = self._get_memory_key(cache_type, cache_key)
        container_name = self._get_container_name(cache_type)
        
        # print(f"[InventoryRawCache] Clearing {cache_type} cache for key: {cache_key}")
        
        # Clear from memory cache
        if memory_key in self._memory_cache:
            del self._memory_cache[memory_key]
            # print(f"[InventoryRawCache] Memory cache cleared for key: {cache_key}")
        
        # Clear from Cosmos DB
        if not self.cosmos_client.initialized:
            # print(f"[InventoryRawCache] Cosmos DB not initialized - memory clear only")
            return True  # Memory clear was successful
            
        start_time = time.time()
        try:
            container = self.cosmos_client.get_container(container_name)
            container.delete_item(item=cache_key, partition_key=cache_key)
            cosmos_time = time.time() - start_time
            
            # print(f"[InventoryRawCache] Cosmos DB cache cleared SUCCESS ({cosmos_time:.2f}s)")
            return True
                
        except Exception as e:
            cosmos_time = time.time() - start_time
            
            # Check if it's a "NotFound" error (document doesn't exist) - this is OK
            if (COSMOS_EXCEPTIONS_AVAILABLE and CosmosResourceNotFoundError and isinstance(e, CosmosResourceNotFoundError)) or \
               "NotFound" in str(e) or "does not exist" in str(e):
                # print(f"[InventoryRawCache] Cosmos DB cache already cleared - document not found ({cosmos_time:.2f}s)")
                return True  # Consider this a success since the goal (no document) is achieved
            else:
                # Log actual errors only for non-NotFound exceptions
                print(f"[InventoryRawCache] Cosmos DB clear ERROR ({cosmos_time:.2f}s): {e}")
                return False
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics for monitoring and debugging.
        
        Returns:
            Dictionary with cache statistics
        """
        memory_stats = {}
        for cache_type in self.container_mapping.keys():
            type_entries = [k for k in self._memory_cache.keys() if k.startswith(f"{cache_type}:")]
            memory_stats[cache_type] = len(type_entries)
        
        return {
            'memory_cache_entries': memory_stats,
            'total_memory_entries': len(self._memory_cache),
            'cache_duration_hours': self.cache_duration.total_seconds() / 3600,
            'supported_cache_types': list(self.container_mapping.keys()),
            'cosmos_initialized': self.cosmos_client.initialized
        }
    
    async def clear_all_cache(self, cache_type: Optional[str] = None) -> Dict[str, Any]:
        """
        Clear cache entries for specified type or all types.
        Provides agent-compatible interface for cache clearing.
        
        Args:
            cache_type: "software", "os", or None for all
            
        Returns:
            Dictionary with operation results
        """
        if cache_type:
            # Clear specific type
            types_to_clear = [cache_type]
        else:
            # Clear all types
            types_to_clear = list(self.container_mapping.keys())
        
        cleared_count = 0
        
        # Clear memory cache
        keys_to_remove = []
        for key in list(self._memory_cache.keys()):
            for ct in types_to_clear:
                if key.startswith(f"{ct}:"):
                    keys_to_remove.append(key)
                    break
        
        for key in keys_to_remove:
            del self._memory_cache[key]
            cleared_count += 1
        
        print(f"[InventoryRawCache] Cleared {cleared_count} memory cache entries for {types_to_clear}")
        
        # Note: Cosmos DB TTL will handle expiration of old entries
        # No need to manually delete from Cosmos DB
        
        return {
            "success": True,
            "cleared_count": cleared_count,
            "cache_types": types_to_clear,
            "message": f"Cleared {cleared_count} cache entries"
        }


# Create module-level instance for backward compatibility
from .cosmos_cache import base_cosmos
inventory_cache = InventoryRawCache(base_cosmos)
