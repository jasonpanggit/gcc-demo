# Phase 2: API Standardization & Response Format Consolidation

## Analysis Summary

### Current State
- **70 API endpoints** across main.py
- **Inconsistent response formats**: Mix of dict, list, StandardResponse, custom formats
- **Redundant error handling**: Error handling duplicated across endpoints
- **Mixed data patterns**: Some endpoints return `{"data": [...]}`, others return arrays directly
- **Template complexity**: UI templates have custom unwrapping logic for different formats

### Identified Issues

#### 1. Response Format Inconsistencies
```python
# Pattern 1: Direct dict return (most common)
return {"success": True, "data": [...], "count": 10}

# Pattern 2: Direct list return (legacy)
return [...]

# Pattern 3: Nested dict with status
return {"status": "ok", "summary": {...}}

# Pattern 4: create_error_response utility
return create_error_response(e, "context")

# Pattern 5: StandardResponse usage (partial)
# Only used in some newer endpoints
```

#### 2. Error Handling Duplication
Each endpoint repeats:
- Try/except blocks
- Timeout handling
- HTTPException raising
- Error logging
- Cache statistics recording

#### 3. Data Unwrapping Logic
Templates must handle multiple formats:
```javascript
// UI JavaScript has to check:
if (response.data) { ... }          // StandardResponse
else if (Array.isArray(response)) { ... }  // Direct array
else if (response.success) { ... }  // Custom dict
```

## Phase 2 Goals

### Primary Objectives
1. ✅ **Standardize all API responses** using `StandardResponse` model
2. ✅ **Create endpoint decorators** for common functionality
3. ✅ **Reduce template complexity** by consistent data structure
4. ✅ **Improve error handling** with centralized patterns
5. ✅ **Enhance API documentation** with OpenAPI examples

### Metrics Targets
- **Code reduction**: -300 to -500 lines (from redundant error handling)
- **Response consistency**: 100% endpoints using StandardResponse
- **Template simplification**: -200 lines from data unwrapping removal
- **Documentation**: OpenAPI docs for all 70 endpoints

## Implementation Plan

### Step 1: Create Endpoint Decorators (New File)
**File**: `utils/endpoint_decorators.py`

```python
from functools import wraps
from fastapi import HTTPException
import asyncio
import time
from utils.cache_stats_manager import cache_stats_manager
from utils.response_models import StandardResponse, create_standard_response
from utils import get_logger

logger = get_logger(__name__)

def with_timeout_and_stats(
    agent_name: str,
    timeout_seconds: int = 30,
    track_cache: bool = True
):
    """
    Decorator to add timeout, error handling, and cache statistics to endpoints
    
    Usage:
        @app.get("/api/example")
        @with_timeout_and_stats(agent_name="example", timeout_seconds=30)
        async def example_endpoint():
            result = await some_async_operation()
            return result  # Will be wrapped in StandardResponse automatically
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            start_time = time.time()
            cache_hit = False
            had_error = False
            
            try:
                # Execute with timeout
                result = await asyncio.wait_for(
                    func(*args, **kwargs),
                    timeout=timeout_seconds
                )
                
                # Detect cache hit from result
                if isinstance(result, dict):
                    cache_hit = result.get("cached", False)
                
                # Record statistics
                response_time = (time.time() - start_time) * 1000
                if track_cache:
                    cache_stats_manager.record_agent_request(
                        agent_name=agent_name,
                        response_time_ms=response_time,
                        was_cache_hit=cache_hit,
                        had_error=False
                    )
                
                # Wrap in StandardResponse if not already
                if isinstance(result, StandardResponse):
                    return result
                elif isinstance(result, dict) and "success" in result:
                    # Already has success field, keep as-is
                    return result
                else:
                    # Wrap in standard format
                    return create_standard_response(
                        data=result,
                        message=f"{agent_name} operation completed successfully"
                    )
                    
            except asyncio.TimeoutError:
                response_time = (time.time() - start_time) * 1000
                if track_cache:
                    cache_stats_manager.record_agent_request(
                        agent_name=agent_name,
                        response_time_ms=response_time,
                        was_cache_hit=False,
                        had_error=True
                    )
                
                logger.error(f"{agent_name} request timed out after {timeout_seconds}s")
                raise HTTPException(
                    status_code=504,
                    detail=f"{agent_name} request timed out after {timeout_seconds} seconds"
                )
                
            except HTTPException:
                # Re-raise HTTP exceptions without modification
                raise
                
            except Exception as e:
                response_time = (time.time() - start_time) * 1000
                if track_cache:
                    cache_stats_manager.record_agent_request(
                        agent_name=agent_name,
                        response_time_ms=response_time,
                        was_cache_hit=False,
                        had_error=True
                    )
                
                logger.error(f"Error in {agent_name}: {str(e)}", exc_info=True)
                raise HTTPException(
                    status_code=500,
                    detail=f"Error in {agent_name}: {str(e)}"
                )
        
        return wrapper
    return decorator
```

### Step 2: Refactor Endpoints (main.py)
Convert endpoints one section at a time:

#### Before (54 lines):
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
        
        response_time = (time.time() - start_time) * 1000
        cache_hit = bool(use_cache and result and isinstance(result, dict) and result.get("cached", False))
        
        cache_stats_manager.record_agent_request(
            agent_name=agent_name,
            response_time_ms=response_time,
            was_cache_hit=cache_hit
        )
        
        if isinstance(result, dict) and result.get("success"):
            inventory_data = result.get("data", [])
            if limit and limit > 0:
                inventory_data = inventory_data[:limit]
                result["data"] = inventory_data
                result["count"] = len(inventory_data)
            return result
        elif isinstance(result, list):
            if limit and limit > 0:
                result = result[:limit]
            return result
        else:
            return result if isinstance(result, dict) else {"success": False, "data": [], "error": "Unknown error"}
            
    except asyncio.TimeoutError:
        response_time = (time.time() - start_time) * 1000
        cache_stats_manager.record_agent_request(
            agent_name=agent_name,
            response_time_ms=response_time,
            was_cache_hit=False,
            had_error=True
        )
        logger.error("Inventory request timed out after %d seconds", config.app.timeout)
        raise HTTPException(status_code=504, detail=f"Inventory request timed out after {config.app.timeout} seconds")
    except Exception as e:
        response_time = (time.time() - start_time) * 1000
        cache_stats_manager.record_agent_request(
            agent_name=agent_name,
            response_time_ms=response_time,
            was_cache_hit=False,
            had_error=True
        )
        logger.error("Error retrieving inventory: %s", e)
        raise HTTPException(status_code=500, detail=f"Error retrieving inventory: {str(e)}")
```

#### After (12 lines):
```python
@app.get("/api/inventory", response_model=StandardResponse)
@with_timeout_and_stats(agent_name="inventory", timeout_seconds=config.app.timeout)
async def get_inventory(limit: int = 5000, days: int = 90, use_cache: bool = True):
    """Get software inventory using multi-agent system"""
    result = await get_eol_orchestrator().get_software_inventory(
        days=days, 
        use_cache=use_cache
    )
    
    # Apply limit if specified
    if limit and limit > 0 and isinstance(result, dict) and "data" in result:
        result["data"] = result["data"][:limit]
        result["count"] = len(result["data"])
    
    return result
```

**Savings**: -42 lines per endpoint × 70 endpoints = **~2,940 lines potential reduction**

### Step 3: Update Templates (templates/*.html)
Remove data unwrapping logic:

#### Before:
```javascript
fetch('/api/inventory')
    .then(response => response.json())
    .then(data => {
        // Handle multiple formats
        let items = [];
        if (data.data) {
            items = data.data;  // StandardResponse
        } else if (Array.isArray(data)) {
            items = data;  // Legacy array
        } else if (data.success && data.items) {
            items = data.items;  // Custom format
        }
        renderTable(items);
    });
```

#### After:
```javascript
fetch('/api/inventory')
    .then(response => response.json())
    .then(data => {
        // All responses now use StandardResponse format
        if (data.success) {
            renderTable(data.data);
        } else {
            showError(data.message);
        }
    });
```

### Step 4: Add OpenAPI Documentation
Add comprehensive docstrings with examples:

```python
@app.get("/api/inventory", response_model=StandardResponse)
@with_timeout_and_stats(agent_name="inventory", timeout_seconds=config.app.timeout)
async def get_inventory(
    limit: int = 5000, 
    days: int = 90, 
    use_cache: bool = True
):
    """
    Get software inventory using multi-agent system
    
    Retrieves software installation data from Azure Log Analytics and analyzes
    it for EOL status. Results are cached for performance.
    
    Args:
        limit: Maximum number of records to return (default: 5000)
        days: Number of days to look back for inventory data (default: 90)
        use_cache: Whether to use cached data if available (default: True)
    
    Returns:
        StandardResponse with software inventory data:
        ```json
        {
            "success": true,
            "data": [
                {
                    "computer": "SERVER-01",
                    "software_name": "Python",
                    "version": "3.11.0",
                    "publisher": "Python Software Foundation",
                    "eol_status": "supported"
                }
            ],
            "count": 1,
            "cached": true,
            "timestamp": "2025-10-15T12:00:00Z"
        }
        ```
    
    Raises:
        HTTPException: 504 if request times out
        HTTPException: 500 if error retrieving inventory
    """
    result = await get_eol_orchestrator().get_software_inventory(
        days=days, 
        use_cache=use_cache
    )
    
    if limit and limit > 0 and isinstance(result, dict) and "data" in result:
        result["data"] = result["data"][:limit]
        result["count"] = len(result["data"])
    
    return result
```

## Rollout Strategy

### Phase 2.1: Foundation (Day 1)
1. ✅ Create `utils/endpoint_decorators.py`
2. ✅ Add unit tests for decorators
3. ✅ Update 5 inventory endpoints as proof of concept
4. ✅ Test with mock data
5. ✅ Commit changes

### Phase 2.2: API Standardization (Day 2)
1. ✅ Convert all cache endpoints (10 endpoints)
2. ✅ Convert all inventory endpoints (8 endpoints)
3. ✅ Convert all EOL search endpoints (6 endpoints)
4. ✅ Convert all agent endpoints (8 endpoints)
5. ✅ Test all endpoints with automated tests
6. ✅ Commit changes

### Phase 2.3: Template Updates (Day 3)
1. ✅ Update `templates/index.html`
2. ✅ Update `templates/cache.html`
3. ✅ Update `templates/inventory.html`
4. ✅ Update `templates/eol_search.html`
5. ✅ Test UI with mock data
6. ✅ Commit changes

### Phase 2.4: Documentation (Day 4)
1. ✅ Add OpenAPI docstrings to all endpoints
2. ✅ Generate API documentation
3. ✅ Create migration guide
4. ✅ Update README with API examples
5. ✅ Final commit and documentation

## Success Metrics

### Code Quality
- **Lines removed**: ~2,500-3,000 lines
- **Complexity reduction**: 70% less error handling code
- **Consistency**: 100% endpoints using StandardResponse

### Developer Experience
- **API predictability**: Single response format
- **Error handling**: Centralized and consistent
- **Documentation**: Complete OpenAPI docs
- **Testing**: Simplified with consistent responses

### Performance
- **No degradation**: Decorator overhead < 1ms
- **Cache statistics**: Preserved and enhanced
- **Timeout handling**: More reliable with decorator

### UI/UX
- **Template simplification**: -200 lines JavaScript
- **Consistent error messages**: Better user feedback
- **Faster development**: No format checking needed

## Risk Mitigation

### Breaking Changes
- **Risk**: Existing API consumers may break
- **Mitigation**: 
  - Keep backward compatibility for 2 releases
  - Add deprecation warnings
  - Provide migration guide
  - Version API endpoints if needed

### Performance Impact
- **Risk**: Decorator overhead adds latency
- **Mitigation**:
  - Benchmark decorator performance
  - Optimize hot paths
  - Add caching if needed

### Testing Coverage
- **Risk**: Template changes break UI
- **Mitigation**:
  - Test each template update in isolation
  - Use mock data for all testing
  - Visual regression testing

## Next Steps

1. **Get approval** for Phase 2 plan
2. **Start Phase 2.1** (foundation work)
3. **Run automated tests** after each change
4. **Commit frequently** with clear messages
5. **Document as you go** for future reference

---

**Estimated Timeline**: 4 days
**Estimated LOC Reduction**: -2,500 to -3,000 lines
**Risk Level**: Medium (breaking changes possible)
**Benefit**: High (major improvement in maintainability)
