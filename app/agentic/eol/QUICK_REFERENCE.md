# Quick Reference - EOL Codebase Refactoring

## 📁 Key Documents

1. **REFACTORING_SUMMARY.md** - Executive summary, read this first
2. **REFACTORING_PLAN.md** - Comprehensive plan with all details
3. **PHASE1_CHANGES.md** - Exact code changes with line numbers
4. **This file** - Quick reference for common tasks

---

## 🔍 What to Review

### Before Implementation
```bash
# Read executive summary (5 mins)
cat REFACTORING_SUMMARY.md

# Review detailed plan (15 mins)
cat REFACTORING_PLAN.md

# Check specific changes (10 mins)
cat PHASE1_CHANGES.md
```

### Key Problem Areas
```bash
# Check duplicate cache files
ls -lh utils/*_cache.py

# Check main.py manual caches
grep -n "_alert_preview_cache\|_inventory_context_cache\|AUTOGEN_AVAILABLE" main.py

# Check API response format inconsistencies
grep -n "isinstance(result, dict)\|isinstance(result, list)" main.py
```

---

## 🎯 Priority Actions

### High Priority (Do First)
1. ✅ Consolidate cache implementations
   - File: `PHASE1_CHANGES.md` Section 1
   - Impact: -542 lines, improved performance
   
2. ✅ Standardize API responses
   - File: `PHASE1_CHANGES.md` Sections 2.4-2.6
   - Impact: Eliminates frontend confusion

3. ✅ Remove legacy code
   - File: `PHASE1_CHANGES.md` Sections 2.1-2.3
   - Impact: -80 lines, improved clarity

### Medium Priority (Do Next)
- Update agent implementations
- Add response models
- Enhance inventory_cache.py

### Low Priority (Do Later)
- Template updates
- Documentation
- Performance tuning

---

## 📊 Impact Summary

### Code Reduction
| Item | Before | After | Saved |
|------|--------|-------|-------|
| Cache files | 5 | 3 | -2 files |
| Lines of code | ~15,000 | ~10,500 | -4,500 lines |
| Duplicate code | 800 lines | <100 lines | -700 lines |
| Manual caches | 3 | 0 | -3 caches |

### Performance Improvement
| Metric | Before | After | Gain |
|--------|--------|-------|------|
| Cosmos DB calls | 100/min | 50/min | 50% ↓ |
| Cache response | 50-200ms | 10-50ms | 75% ↓ |
| Memory usage | High | Moderate | 30% ↓ |

---

## 🔧 Implementation Commands

### Quick Start
```bash
# Create feature branch
git checkout -b refactor/phase-1

# Delete duplicate files
rm app/agentic/eol/utils/software_inventory_cache.py
rm app/agentic/eol/utils/os_inventory_cache.py

# Create new file
touch app/agentic/eol/utils/response_models.py
```

### Testing
```bash
# Unit tests
pytest tests/test_cache.py -v

# Integration tests
pytest tests/test_api.py -v

# Full test suite
pytest tests/ -v --cov=app/agentic/eol
```

### Deployment
```bash
# Commit changes
git add -A
git commit -m "Phase 1: Cache consolidation and API standardization"

# Push to remote
git push origin refactor/phase-1

# Create PR
gh pr create --title "Phase 1: Refactoring" --body "See REFACTORING_SUMMARY.md"
```

---

## ⚠️ Common Pitfalls

### 1. Breaking Existing Frontend
**Problem:** Changing API format breaks templates
**Solution:** Update backend first, test, then update templates

### 2. Cache Performance Regression
**Problem:** Unified cache slower than specialized
**Solution:** Monitor metrics, use feature flags, rollback if needed

### 3. Import Errors After Deleting Files
**Problem:** Other files still import deleted cache modules
**Solution:** Search for all imports first:
```bash
grep -r "from utils.software_inventory_cache" app/agentic/eol/
grep -r "from utils.os_inventory_cache" app/agentic/eol/
```

### 4. Data Format Confusion
**Problem:** Mixing old and new formats during transition
**Solution:** Use StandardResponse.to_dict() consistently

---

## 🎨 Code Patterns

### Old Pattern (BAD)
```python
# Inconsistent response formats
if isinstance(result, dict):
    return result
elif isinstance(result, list):
    return {"data": result}
else:
    return {"error": "Invalid format"}
```

### New Pattern (GOOD)
```python
# Consistent response format
from utils.response_models import StandardResponse

if success:
    return StandardResponse.success_response(
        data=results,
        cached=was_cached,
        metadata={"source": "log_analytics"}
    ).to_dict()
else:
    return StandardResponse.error_response(
        error=error_message,
        metadata={"attempted_operation": "get_inventory"}
    ).to_dict()
```

### Old Cache Pattern (BAD)
```python
# Manual cache management
_cache = {}
_cache_expiry = {}

def get_data():
    if key in _cache and not expired:
        return _cache[key]
    # ... fetch data ...
    _cache[key] = data
    return data
```

### New Cache Pattern (GOOD)
```python
# Unified cache management
from utils.inventory_cache import InventoryRawCache

cache = InventoryRawCache(base_cosmos)

def get_data():
    # Cache handles TTL, memory, and Cosmos DB automatically
    cached = cache.get_cached_data(cache_key, cache_type="software")
    if cached:
        return cached
    
    # ... fetch data ...
    cache.store_cached_data(cache_key, data, cache_type="software")
    return data
```

---

## 📋 Pre-Flight Checklist

### Before Starting
- [ ] Read REFACTORING_SUMMARY.md
- [ ] Review REFACTORING_PLAN.md
- [ ] Check PHASE1_CHANGES.md for exact changes
- [ ] Create backup branch
- [ ] Get team approval

### Before Committing
- [ ] All tests pass
- [ ] No unused imports
- [ ] Documentation updated
- [ ] Performance tested
- [ ] Error cases handled

### Before Merging
- [ ] Code review completed
- [ ] CI/CD tests pass
- [ ] Staging deployment successful
- [ ] Metrics look good
- [ ] Rollback plan ready

---

## 🚀 Fast Track (Minimal Changes)

If you want the quickest impact with minimal risk:

### Option 1: Just Delete Duplicates (30 mins)
1. Delete `software_inventory_cache.py`
2. Delete `os_inventory_cache.py`
3. Update agents to use `InventoryRawCache`
4. Test

**Result:** -542 lines, same functionality

### Option 2: Just Clean main.py (1 hour)
1. Remove manual alert cache (lines 40-60)
2. Remove AUTOGEN references (lines 70-81)
3. Remove inventory context cache (lines ~1370-1390)
4. Test

**Result:** -80 lines, cleaner code

### Option 3: Just Standardize APIs (2 hours)
1. Create `response_models.py`
2. Update `/api/inventory` endpoint
3. Update `/api/inventory/raw/os` endpoint
4. Test

**Result:** Consistent API format

---

## 💡 Tips & Tricks

### Finding Duplicate Code
```bash
# Find similar function names
grep -rn "def _ensure_container" app/agentic/eol/utils/

# Find duplicate dataclasses
grep -rn "class CachedInventoryData" app/agentic/eol/utils/

# Find inconsistent returns
grep -rn "return.*success.*data" app/agentic/eol/
```

### Testing Cache Changes
```bash
# Clear all caches
curl -X POST http://localhost:8000/api/cache/clear

# Check cache stats
curl http://localhost:8000/api/cache/status

# Test inventory endpoint
curl http://localhost:8000/api/inventory?use_cache=false
```

### Monitoring Performance
```bash
# Watch logs
tail -f logs/app.log | grep "cache"

# Check Cosmos DB metrics
# Go to Azure Portal > Cosmos DB > Metrics

# Monitor API response times
# Go to Application Insights > Performance
```

---

## 📞 Help & Support

### Questions?
1. Check REFACTORING_PLAN.md Section 12
2. Review PHASE1_CHANGES.md for specific code
3. Search codebase for examples

### Issues During Implementation?
1. Check rollback plan (PHASE1_CHANGES.md Section 8)
2. Review common pitfalls above
3. Test incrementally, commit often

### Need More Details?
- **Architecture:** See REFACTORING_PLAN.md Section 1
- **Code changes:** See PHASE1_CHANGES.md
- **Testing:** See PHASE1_CHANGES.md Section 6
- **Deployment:** See PHASE1_CHANGES.md Section 7

---

## 🎯 Success Criteria

### Code Quality ✅
- [ ] No duplicate cache implementations
- [ ] Single API response format
- [ ] No manual cache management in main.py
- [ ] Consistent error handling

### Performance ✅
- [ ] Cache hit rate maintained or improved
- [ ] API response time <200ms (p95)
- [ ] Cosmos DB RU usage reduced
- [ ] Memory usage stable

### Maintainability ✅
- [ ] Clear separation of concerns
- [ ] Single source of truth
- [ ] Well-documented changes
- [ ] Easy to extend

---

*Quick Reference Version: 1.0*
*For full details, see REFACTORING_PLAN.md*
