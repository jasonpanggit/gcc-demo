# Legacy Routing Utilities

These modules were superseded by the Phase 3 unified routing pipeline.

## Contents

| File | Superseded by |
|------|--------------|
| `tool_router.py` | `utils.router.Router` + `utils.unified_domain_registry` |
| `tool_embedder.py` | `utils.tool_retriever.ToolRetriever` (Stage 2 semantic ranking) |

## Migration

Replace `ToolRouter` usage with:
```python
from utils.router import Router
router = Router()
matches = await router.route(query, tool_source_map=source_map)
```

Replace `ToolEmbedder` usage with:
```python
from utils.tool_retriever import ToolRetriever
retriever = ToolRetriever(composite_client)
result = await retriever.retrieve(query, domain_matches)
```

## Why kept

`ToolEmbedder` is still used by `ToolRetriever` as the Stage 2 semantic
ranking engine. It is not deleted — only moved to make its legacy status
explicit. `ToolRouter` is kept for `scripts/selection_reporter.py` which
uses its `explain()` method for diagnostic output.
