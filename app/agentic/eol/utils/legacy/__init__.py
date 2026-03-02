"""Legacy routing modules — archived as part of Phase 3 unified routing consolidation.

These modules existed before the UnifiedRouter was introduced. They are preserved
here for reference and emergency rollback, but should NOT be used in new code.

## Migration Guide

### From ToolRouter

**Before (legacy):**
```python
from utils.tool_router import ToolRouter

router = ToolRouter(composite_client)
filtered_tools = router.filter_tools_for_query(user_message, all_tools, source_map)
```

**After (unified):**
```python
from utils.unified_router import UnifiedRouter, get_unified_router

router = get_unified_router()  # Singleton
plan = await router.route(user_message, strategy="fast")
# plan.tools is the filtered list of tool names
# plan.orchestrator tells you which orchestrator to use
```

### From ToolEmbedder

**Before (legacy):**
```python
from utils.tool_embedder import ToolEmbedder

embedder = ToolEmbedder()
await embedder.build_index(all_tool_definitions)
relevant_tools = await embedder.retrieve(query, top_k=10)
```

**After (unified):**
```python
from utils.unified_router import get_unified_router

router = get_unified_router()
plan = await router.route(query, strategy="quality")
# quality strategy includes semantic-like secondary domain expansion
# plan.tools contains the ranked tool names
```

---

## Rollback Procedure

If the unified router causes issues:

1. Set environment variable: `USE_UNIFIED_ROUTER=false`
2. Restore imports from `utils.legacy.tool_router` and `utils.legacy.tool_embedder`
3. Update orchestrators to use legacy routers
4. File a bug report with the issue details

---

## Files

- `tool_router.py` — Keyword-based tool pre-filtering (ToolRouter class)
- `tool_embedder.py` — Semantic embedding-based tool ranking (ToolEmbedder class)
- `README.md` — This migration guide

---

**Deprecated:** 2026-03-02 (Phase 3 — Unified Routing Pipeline)
**Replaced by:** `utils/unified_router.py`, `utils/domain_classifier.py`
"""
