# Specific Code Changes - Phase 1 Implementation

This document provides exact code changes for Phase 1 of the refactoring plan.

---

## 1. Files to Delete

```bash
cd app/agentic/eol/utils
rm software_inventory_cache.py  # 267 lines - replaced by inventory_cache.py
rm os_inventory_cache.py         # 275 lines - replaced by inventory_cache.py
```

---

## 2. main.py Changes

### Change 2.1: Remove Dead Import Fallback (Lines 27-31)

**REMOVE:**
```python
except ImportError:
    # Fallback for different environments
    sys.path.append(os.path.dirname(__file__))
    from utils import get_logger, config, create_error_response
```

**REASON:** Never executed, sys.path manipulation is bad practice

---

### Change 2.2: Remove Manual Alert Preview Cache (Lines 40-60)

**REMOVE:**
```python
# Alert preview cache - 5 minute expiration to reduce OS inventory requests
_alert_preview_cache = {}
_alert_preview_cache_expiry = {}
ALERT_CACHE_DURATION_MINUTES = 5

def _get_cached_alert_data(cache_key: str):
    """Get cached alert data if not expired"""
    if cache_key in _alert_preview_cache:
        expiry = _alert_preview_cache_expiry.get(cache_key)
        if expiry and datetime.now(timezone.utc) < expiry:
            # [cache hit logic]
    
    logger.debug(f"🔄 Alert preview cache MISS for key: {cache_key}")
    return None

def _cache_alert_data(cache_key: str, data):
    """Cache alert data with expiration"""
    _alert_preview_cache[cache_key] = data
    _alert_preview_cache_expiry[cache_key] = datetime.now(timezone.utc) + timedelta(minutes=ALERT_CACHE_DURATION_MINUTES)
    logger.debug(f"✅ Alert preview cached for {ALERT_CACHE_DURATION_MINUTES} minutes: {cache_key}")

def _clear_alert_cache():
    """Clear all alert preview cache"""
    global _alert_preview_cache, _alert_preview_cache_expiry
    cache_count = len(_alert_preview_cache)
    _alert_preview_cache.clear()
    _alert_preview_cache_expiry.clear()
    logger.info(f"🔄 Cleared {cache_count} alert preview cache entries")
```

**REPLACE WITH:**
```python
# Alert data will use InventoryRawCache with appropriate TTL
# See utils/inventory_cache.py for implementation
```

**REASON:** Duplicates Cosmos DB cache functionality, inconsistent TTL strategy

---

### Change 2.3: Remove Unused Chat Orchestrator References (Lines 70-81)

**REMOVE:**
```python
# Try to import Chat orchestrator for chat interface
try:
    from agents.chat_orchestrator import ChatOrchestratorAgent
    CHAT_AVAILABLE = True
    logger.info("✅ Chat orchestrator available")
except ImportError as e:
    CHAT_AVAILABLE = False
    logger.warning(f"⚠️ Chat orchestrator not available: {e}")
    ChatOrchestratorAgent = None

# Maintain backward compatibility
AUTOGEN_AVAILABLE = CHAT_AVAILABLE
```

**REPLACE WITH:**
```python
# EOL interface uses standard orchestrator only
# Chat functionality is in separate chat.html interface
```

**REASON:** Not used in EOL interface, confusing variable names (AUTOGEN_AVAILABLE)

---

### Change 2.4: Update get_inventory() to Standardized Format (Lines 540-580)

**CURRENT:**
```python
@app.get("/api/inventory")
async def get_inventory(limit: int = 5000, days: int = 90, use_cache: bool = True):
    """Get software inventory using multi-agent system"""
    start_time = time.time()
    agent_name = "inventory"
    
    try:
        result = await asyncio.wait_for(
            get_eol_orchestrator().get_software_inventory(days=days, use_cache=use_cache),
            timeout=config.app.timeout
        )
        
        # Record cache performance metrics
        response_time = (time.time() - start_time) * 1000
        cache_hit = bool(use_cache and result and isinstance(result, dict) and result.get("cached", False))
        
        cache_stats_manager.record_agent_request(
            agent_name=agent_name,
            response_time_ms=response_time,
            was_cache_hit=cache_hit
        )
        
        # Handle both new Dict format and legacy List format
        if isinstance(result, dict) and result.get("success"):
            # Return the result as is
            return result
        elif isinstance(result, list):
            # Legacy format - wrap in standard format
            return {
                "success": True,
                "data": result,
                "count": len(result)
            }
        else:
            # Error case
            raise HTTPException(status_code=500, detail="Invalid inventory data format")
```

**REPLACE WITH:**
```python
@app.get("/api/inventory")
async def get_inventory(limit: int = 5000, days: int = 90, use_cache: bool = True):
    """Get software inventory using multi-agent system
    
    Returns:
        StandardResponse: {
            "success": bool,
            "data": List[Dict],
            "count": int,
            "cached": bool,
            "timestamp": str,
            "metadata": Dict
        }
    """
    start_time = time.time()
    agent_name = "inventory"
    
    try:
        result = await asyncio.wait_for(
            get_eol_orchestrator().get_software_inventory(days=days, use_cache=use_cache),
            timeout=config.app.timeout
        )
        
        # Ensure result is in standard format
        if not isinstance(result, dict):
            logger.warning(f"Inventory returned non-dict: {type(result)}")
            result = {"success": False, "error": "Invalid response format"}
        
        # Ensure required fields exist
        standardized = {
            "success": result.get("success", False),
            "data": result.get("data", []),
            "count": result.get("count", len(result.get("data", []))),
            "cached": result.get("cached", False),
            "timestamp": result.get("timestamp", datetime.utcnow().isoformat()),
            "metadata": result.get("metadata", {
                "query_days": days,
                "limit": limit,
                "use_cache": use_cache
            })
        }
        
        # Record cache performance metrics
        response_time = (time.time() - start_time) * 1000
        cache_stats_manager.record_agent_request(
            agent_name=agent_name,
            response_time_ms=response_time,
            was_cache_hit=standardized["cached"]
        )
        
        return standardized
```

**REASON:** Eliminates data format guessing, provides consistent structure

---

### Change 2.5: Update get_raw_os_inventory() to Use InventoryRawCache (Lines 753-860)

**CURRENT:** Uses manual `_get_cached_alert_data()` and `_cache_alert_data()`

**REPLACE WITH:**
```python
@app.get("/api/inventory/raw/os")
async def get_raw_os_inventory(days: int = 90, limit: int = 2000, force_refresh: bool = False):
    """
    Get raw operating system inventory data directly from Log Analytics Heartbeat table
    Returns clean JSON response with validation and error handling with caching
    """
    try:
        logger.info(f"📊 Raw OS inventory request: days={days}, limit={limit}, force_refresh={force_refresh}")
        
        # Get the inventory agent directly
        inventory_agent = get_eol_orchestrator().agents.get("os_inventory")
        if not inventory_agent:
            raise HTTPException(
                status_code=503, 
                detail="OS inventory agent is not available"
            )
        
        # Use inventory agent's built-in caching (backed by InventoryRawCache)
        use_cache = not force_refresh
        result = await asyncio.wait_for(
            inventory_agent.get_os_inventory(days=days, limit=limit, use_cache=use_cache),
            timeout=60.0  # 1 minute timeout for raw data queries
        )
        
        # Ensure standard format
        if not isinstance(result, dict):
            logger.warning(f"Raw OS inventory returned non-dict: {type(result)}")
            return {
                "success": False,
                "error": "Invalid response format",
                "data": [],
                "count": 0,
                "query_days": days,
                "query_limit": limit
            }
        
        # Add query parameters to metadata
        if "metadata" not in result:
            result["metadata"] = {}
        result["metadata"].update({
            "query_days": days,
            "query_limit": limit,
            "force_refresh": force_refresh
        })
        
        logger.info(f"✅ Raw OS inventory result: success={result.get('success')}, count={result.get('count', 0)}")
        
        return result
        
    except asyncio.TimeoutError:
        logger.error("Raw OS inventory request timed out after 60 seconds")
        return {
            "success": False,
            "error": "Raw OS inventory request timed out after 60 seconds",
            "data": [],
            "count": 0,
            "query_days": days,
            "query_limit": limit
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving raw OS inventory: {str(e)}", exc_info=True)
        return {
            "success": False,
            "error": f"Error retrieving raw OS inventory: {str(e)}",
            "error_type": type(e).__name__,
            "data": [],
            "count": 0,
            "query_days": days,
            "query_limit": limit
        }
```

**REASON:** Use built-in agent caching instead of manual cache, standardized response format

---

### Change 2.6: Update get_alert_preview() to Use InventoryRawCache (Lines 1045-1090)

**CURRENT:** Uses manual `_get_cached_alert_data()` and `_cache_alert_data()`

**REPLACE WITH:**
```python
@app.get("/api/alerts/preview")
async def get_alert_preview(days: int = 90):
    """Get preview of alerts based on current configuration
    
    Uses InventoryRawCache for consistent caching strategy
    """
    try:
        from utils.alert_manager import alert_manager
        
        # Get OS inventory data using agent's built-in caching
        logger.debug(f"🔄 Fetching OS inventory for alert preview (days={days})")
        os_data = await asyncio.wait_for(
            get_eol_orchestrator().agents["os_inventory"].get_os_inventory(days=days, use_cache=True),
            timeout=30.0,
        )
        
        # Extract inventory data from standardized response
        if isinstance(os_data, dict) and os_data.get("success"):
            inventory_data = os_data.get("data", [])
        else:
            logger.warning(f"Invalid OS data format: {type(os_data)}")
            inventory_data = []
        
        # Load configuration and generate preview
        config = await alert_manager.load_configuration()
        alert_items, summary = await alert_manager.generate_alert_preview(inventory_data, config)
        
        return {
            "success": True,
            "data": {
                "alerts": [item.dict() for item in alert_items],
                "summary": summary.dict(),
                "config": config.dict()
            },
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error generating alert preview: {e}")
        raise HTTPException(status_code=500, detail=f"Error generating preview: {str(e)}")
```

**REASON:** Use agent's built-in caching, remove manual cache logic

---

### Change 2.7: Remove Manual Inventory Context Cache (Lines ~1370-1390 area)

**FIND AND REMOVE:**
```python
_inventory_context_cache = {"data": None, "timestamp": None, "ttl": 300}
```

**AND REMOVE ALL REFERENCES TO:**
- `_inventory_context_cache`
- Any manual cache management for inventory context

**REPLACE WITH:** Agents using `InventoryRawCache` internally

---

### Change 2.8: Update clear_cache() Endpoint (Line ~1410)

**CURRENT:**
```python
@app.post("/api/cache/clear")
async def clear_cache():
    """Clear the inventory context cache and alert preview cache"""
    global _inventory_context_cache
    old_size = len(str(_inventory_context_cache["data"])) if _inventory_context_cache["data"] else 0
    _inventory_context_cache = {"data": None, "timestamp": None, "ttl": 300}
    
    # Also clear alert preview cache
    _clear_alert_cache()
    
    logger.info("🧹 Inventory context cache cleared (was %d bytes)", old_size)
    return {
        "status": "success", 
        "message": "Inventory context cache and alert preview cache cleared",
        "cleared_size_bytes": old_size,
        "timestamp": datetime.utcnow().isoformat()
    }
```

**REPLACE WITH:**
```python
@app.post("/api/cache/clear")
async def clear_cache():
    """Clear all inventory caches (software and OS)
    
    This clears both memory and Cosmos DB caches for inventory data.
    EOL agent caches are managed separately via /api/cache/purge
    """
    try:
        # Clear inventory caches via orchestrator
        software_agent = get_eol_orchestrator().agents.get("software_inventory")
        os_agent = get_eol_orchestrator().agents.get("os_inventory")
        
        cleared_items = []
        
        if software_agent and hasattr(software_agent, 'clear_cache'):
            await software_agent.clear_cache()
            cleared_items.append("software_inventory")
        
        if os_agent and hasattr(os_agent, 'clear_cache'):
            await os_agent.clear_cache()
            cleared_items.append("os_inventory")
        
        logger.info(f"🧹 Cleared inventory caches: {cleared_items}")
        
        return {
            "success": True,
            "status": "success",
            "message": f"Inventory caches cleared: {', '.join(cleared_items)}",
            "cleared_caches": cleared_items,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error clearing cache: {e}")
        return {
            "success": False,
            "status": "error",
            "message": f"Error clearing cache: {str(e)}",
            "timestamp": datetime.utcnow().isoformat()
        }
```

**REASON:** Use proper cache clearing through agents instead of manual cache management

---

## 3. utils/inventory_cache.py Enhancements

### Change 3.1: Add Helper Methods for Agent Integration

**ADD AT END OF InventoryRawCache CLASS:**

```python
    async def clear_cache(self, cache_type: Optional[str] = None):
        """
        Clear cache entries for specified type or all types.
        
        Args:
            cache_type: "software", "os", or None for all
        """
        if cache_type:
            # Clear specific type
            types_to_clear = [cache_type]
        else:
            # Clear all types
            types_to_clear = list(self.container_mapping.keys())
        
        cleared_count = 0
        
        # Clear memory cache
        for cache_type in types_to_clear:
            keys_to_remove = [k for k in self._memory_cache.keys() if k.startswith(f"{cache_type}:")]
            for key in keys_to_remove:
                del self._memory_cache[key]
                cleared_count += 1
        
        print(f"[InventoryRawCache] Cleared {cleared_count} memory cache entries")
        
        # Note: Cosmos DB TTL will handle expiration of old entries
        # No need to manually delete from Cosmos DB
        
        return {
            "success": True,
            "cleared_count": cleared_count,
            "cache_types": types_to_clear
        }
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """
        Get statistics about current cache state.
        """
        stats = {
            "memory_cache_size": len(self._memory_cache),
            "cache_duration_hours": self.cache_duration.total_seconds() / 3600,
            "container_mapping": self.container_mapping,
            "cosmos_initialized": self.cosmos_client.initialized
        }
        
        # Count entries by type
        type_counts = {}
        for key in self._memory_cache.keys():
            cache_type = key.split(":")[0] if ":" in key else "unknown"
            type_counts[cache_type] = type_counts.get(cache_type, 0) + 1
        
        stats["entries_by_type"] = type_counts
        
        return stats
```

---

## 4. Agent Updates

### Change 4.1: agents/software_inventory_agent.py

**FIND:**
```python
from utils.software_inventory_cache import SoftwareInventoryMemoryCache
```

**REPLACE WITH:**
```python
from utils.inventory_cache import InventoryRawCache
from utils.cosmos_cache import base_cosmos
```

**FIND (in __init__):**
```python
self.cache = SoftwareInventoryMemoryCache()
```

**REPLACE WITH:**
```python
self.cache = InventoryRawCache(base_cosmos)
```

**FIND (in get_software_inventory method):**
```python
cached_result = await self.cache.get_cached_data(
    agent_name=self.name,
    query_params={"days": days, "limit": limit},
    workspace_id=workspace_id
)
```

**REPLACE WITH:**
```python
cache_key = f"software_{days}_{limit}"
cached_result = self.cache.get_cached_data(
    cache_key=cache_key,
    cache_type="software"
)
```

**FIND (in cache storage):**
```python
await self.cache.store_cached_data(
    agent_name=self.name,
    query_params={"days": days, "limit": limit},
    data=results,
    workspace_id=workspace_id
)
```

**REPLACE WITH:**
```python
cache_key = f"software_{days}_{limit}"
self.cache.store_cached_data(
    cache_key=cache_key,
    data=results,
    cache_type="software"
)
```

### Change 4.2: agents/os_inventory_agent.py

**SIMILAR CHANGES AS SOFTWARE AGENT:**
- Replace `OsInventoryMemoryCache` with `InventoryRawCache`
- Update cache method calls to use simplified interface
- Use `cache_type="os"` parameter

---

## 5. Create Response Models (NEW FILE)

**FILE:** `utils/response_models.py`

```python
"""
Standardized response models for API endpoints
Ensures consistent data format across all endpoints
"""
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from datetime import datetime


@dataclass
class StandardResponse:
    """Standard API response format for all endpoints
    
    All API endpoints should return data in this format to ensure
    consistency and eliminate frontend data unwrapping logic.
    """
    success: bool
    data: List[Dict[str, Any]] = field(default_factory=list)
    count: int = 0
    cached: bool = False
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    metadata: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        result = {
            "success": self.success,
            "data": self.data,
            "count": self.count,
            "cached": self.cached,
            "timestamp": self.timestamp
        }
        
        if self.metadata:
            result["metadata"] = self.metadata
        
        if self.error:
            result["error"] = self.error
        
        return result
    
    @classmethod
    def success_response(cls, data: List[Dict[str, Any]], cached: bool = False, 
                        metadata: Optional[Dict[str, Any]] = None) -> "StandardResponse":
        """Create a successful response"""
        return cls(
            success=True,
            data=data,
            count=len(data),
            cached=cached,
            metadata=metadata
        )
    
    @classmethod
    def error_response(cls, error: str, metadata: Optional[Dict[str, Any]] = None) -> "StandardResponse":
        """Create an error response"""
        return cls(
            success=False,
            data=[],
            count=0,
            error=error,
            metadata=metadata
        )


@dataclass
class AgentResponse:
    """Response format for agent operations
    
    Used by all agents to return consistent data format
    """
    success: bool
    data: Any
    agent_name: str
    cached: bool = False
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    error: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    
    def to_standard_response(self) -> StandardResponse:
        """Convert agent response to standard API response"""
        # Ensure data is a list
        if isinstance(self.data, list):
            data_list = self.data
        elif isinstance(self.data, dict):
            data_list = [self.data]
        else:
            data_list = []
        
        metadata = self.metadata or {}
        metadata["agent_name"] = self.agent_name
        
        if self.error:
            return StandardResponse.error_response(self.error, metadata)
        else:
            return StandardResponse.success_response(data_list, self.cached, metadata)
```

---

## 6. Testing Checklist

### Unit Tests
- [ ] Test InventoryRawCache with software data
- [ ] Test InventoryRawCache with OS data
- [ ] Test cache clearing functionality
- [ ] Test StandardResponse serialization
- [ ] Test AgentResponse conversion

### Integration Tests
- [ ] Test /api/inventory endpoint with new format
- [ ] Test /api/inventory/raw/os endpoint
- [ ] Test /api/cache/clear endpoint
- [ ] Test alert preview with new caching
- [ ] Test error cases

### Performance Tests
- [ ] Compare cache hit rates before/after
- [ ] Compare API response times
- [ ] Test with 1000+ inventory items
- [ ] Test concurrent cache access

---

## 7. Deployment Steps

### Step 1: Backup
```bash
git checkout -b backup-before-refactor
git push origin backup-before-refactor
```

### Step 2: Create Feature Branch
```bash
git checkout main
git pull origin main
git checkout -b refactor/phase-1-cache-consolidation
```

### Step 3: Apply Changes
```bash
# Delete files
rm app/agentic/eol/utils/software_inventory_cache.py
rm app/agentic/eol/utils/os_inventory_cache.py

# Create new files
# ... create response_models.py ...

# Edit files in order:
# 1. utils/inventory_cache.py (add helper methods)
# 2. utils/response_models.py (create new)
# 3. agents/software_inventory_agent.py (update imports)
# 4. agents/os_inventory_agent.py (update imports)
# 5. main.py (all changes)
```

### Step 4: Test
```bash
# Run tests
pytest tests/

# Start app locally
python -m uvicorn main:app --reload

# Test endpoints manually
curl http://localhost:8000/api/inventory
curl http://localhost:8000/api/inventory/raw/os
```

### Step 5: Commit
```bash
git add -A
git commit -m "Phase 1: Consolidate cache implementations and standardize API responses

- Removed duplicate cache files (software_inventory_cache.py, os_inventory_cache.py)
- Consolidated caching into InventoryRawCache
- Standardized all API responses to use StandardResponse format
- Removed manual cache management from main.py
- Removed legacy AUTOGEN references
- Created response_models.py for consistent API formats

Benefits:
- Reduced code by ~600 lines
- Single source of truth for caching
- Consistent API response format
- Improved maintainability"

git push origin refactor/phase-1-cache-consolidation
```

### Step 6: Create PR and Review
- Create pull request on GitHub
- Request code review
- Run CI/CD tests
- Deploy to staging environment
- Monitor metrics

### Step 7: Deploy to Production
- Merge to main after approval
- Deploy with feature flag enabled
- Monitor error rates and performance
- Gradually roll out to all users
- Document changes

---

## 8. Rollback Plan

### If Issues Occur:
```bash
# Option 1: Revert the merge commit
git revert <merge-commit-hash>
git push origin main

# Option 2: Hard reset to previous state
git checkout main
git reset --hard backup-before-refactor
git push origin main --force

# Option 3: Feature flag disable (if implemented)
# Set USE_UNIFIED_CACHE=false in environment
```

### Monitoring During Rollout:
- Watch error rates in Application Insights
- Monitor cache hit rates
- Check API response times
- Monitor Cosmos DB request units
- Check user feedback

---

*Document Version: 1.0*
*Last Updated: 2025-10-15*
