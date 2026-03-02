# Legacy Routing Modules

**Status:** Deprecated as of 2026-03-02 (Phase 3 — Unified Routing Pipeline)

These modules are archived here for reference and emergency rollback.
**Do NOT use them in new code.** Use `utils/unified_router.py` instead.

---

## Deprecated Modules

### `tool_router.py` — ToolRouter

**Original purpose:** Keyword-based intent filtering for the MCP orchestrator.
Classified user queries into domains and returned a subset of tools to reduce
the tool catalog sent to the LLM.

**Replaced by:** `utils/unified_router.py` → `UnifiedRouter` (fast strategy)

### `tool_embedder.py` — ToolEmbedder

**Original purpose:** Semantic embedding-based tool ranking using Azure OpenAI
embeddings. Built an in-memory cosine similarity index over tool descriptions.

**Replaced by:** `utils/unified_router.py` → `UnifiedRouter` (quality strategy)

---

## Migration Guide

### ToolRouter → UnifiedRouter

**Before (legacy):**
```python
from utils.tool_router import ToolRouter

router = ToolRouter(composite_client)
filtered_tools = router.filter_tools_for_query(
    user_message,
    all_tools,
    source_map,
    prior_tool_names=["check_health"],
)
```

**After (unified):**
```python
from utils.unified_router import get_unified_router

router = get_unified_router()  # Singleton
plan = await router.route(user_message, strategy="fast")
# plan.tools    — list of tool names to use
# plan.domain   — primary domain (DomainLabel enum)
# plan.orchestrator — "mcp" or "sre"
```

### ToolEmbedder → UnifiedRouter

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
# quality strategy uses primary + secondary domain expansion
# analogous to semantic ranking but without embedding API calls
```

---

## Rollback Procedure

If the unified router causes issues:

1. Set feature flag: `USE_UNIFIED_ROUTER=false` (if implemented)
2. In MCPOrchestratorAgent, restore `_tool_router` and `_tool_embedder` usage
3. Import from `utils.legacy.tool_router` / `utils.legacy.tool_embedder`
4. Revert `utils/unified_router.py` and `utils/domain_classifier.py`
5. File a bug report with reproduction steps

---

**Created:** 2026-03-02
**Phase:** 03-01 (Unified Routing Pipeline)
**Replacements:** `utils/unified_router.py`, `utils/domain_classifier.py`
