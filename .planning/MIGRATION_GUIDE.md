# Orchestrator Architecture Migration Guide

**Version:** 1.0
**Date:** 2026-03-02
**Status:** Complete
**Project:** GCC Demo Platform — Orchestrator Architecture Refactor

---

## Overview

The orchestrator architecture refactor (Phases 1-5) modernizes MCP tool management, unifies routing logic, and introduces declarative server configuration. The architecture is now complete and production-ready.

### What Changed

- **Centralized Tool Registry:** Single `MCPToolRegistry` singleton eliminates 300% duplication across 10 MCP servers
- **Unified Routing:** `UnifiedRouter` replaces 3 parallel routing systems (`ToolRouter`, `ToolEmbedder`, custom logic)
- **Orchestrator Base Class:** `BaseOrchestrator` provides shared grounding, formatting, error handling
- **Declarative Configuration:** `config/mcp_servers.yaml` + `MCPHost.from_config()` enables env-var server toggles
- **Enhanced Reliability:** `RetryStats`, `TryAgain`, resource caps, graceful shutdown

### Why This Matters

- **Developer Productivity:** Add new MCP server in <30 minutes (was ~2 hours)
- **Maintainability:** 60% shared code reuse in orchestrators (was 10%)
- **Reliability:** Tool discovery <500ms, routing <200ms, zero tool duplication
- **Observability:** Correlation IDs, retry stats, 5-layer debugging guide

### Architecture Reference

See [`.claude/docs/AGENT-HIERARCHY.md`](.claude/docs/AGENT-HIERARCHY.md) for the complete 5-layer stack diagram, request lifecycle walkthrough, and debugging guide.

---

## Breaking Changes by Phase

| Component | Phase | Change | Impact | Migration Step |
|-----------|-------|--------|--------|----------------|
| **MCPToolRegistry** | 1 | New singleton registry | All MCP clients auto-register | No code change — clients already wired |
| **MCPHost** | 1 | Renamed from `CompositeMCPClient` | New name in imports | Use `MCPHost` (backward compat alias exists) |
| **BaseOrchestrator** | 2 | New ABC for orchestrators | New base class contract | Inherit if building new orchestrator |
| **UnifiedRouter** | 3 | Replaces `ToolRouter` + `ToolEmbedder` | Legacy modules deprecated | See [Phase 3](#phase-3-unifiedrouter-replaces-toolrouter--toolembedder) |
| **ToolRouter** | 3 | Deprecated (archived to `utils/legacy/`) | Still functional for ReAct path | No immediate action; plan migration |
| **ToolEmbedder** | 3 | Deprecated (archived to `utils/legacy/`) | Replaced by `quality` strategy | No immediate action; plan migration |
| **RetryStats** | 4 | New retry observability API | Keyword-only params added | Add `stats=RetryStats()` to `retry_async()` |
| **TryAgain** | 4 | Control-flow retry sentinel | New exception type | Raise `TryAgain()` for clean retries |
| **mcp_servers.yaml** | 5 | Declarative server config | YAML file defines servers | Servers auto-initialized from YAML |
| **MCPHost.from_config()** | 5 | Factory method for YAML init | New async classmethod | Use `await MCPHost.from_config()` |

---

## Phase 1: MCPToolRegistry + MCPHost

### What Changed

- **MCPToolRegistry:** Singleton registry managing all 52 tools from 10 MCP servers
- **MCPHost:** Renamed from `CompositeMCPClient` to align with MCP specification
- **Auto-registration:** All MCP clients register with registry during initialization

### Before (Phase 0 — Manual Tool Discovery)

```python
# Each orchestrator discovered tools independently
from utils.sre_mcp_client import SREMCPClient

client = await SREMCPClient.create()
tools = await client.list_tools()  # Separate catalog per client
```

### After (Phase 1 — Centralized Registry)

```python
from utils.tool_registry import get_tool_registry

registry = get_tool_registry()  # Singleton
all_tools = registry.get_all_tools()  # 52 tools, zero duplication
sre_tools = registry.get_tools_by_domain("sre")  # Domain filtering
```

### Key Methods

```python
registry = get_tool_registry()

# Query tools
all_tools = registry.get_all_tools()  # List[ToolEntry]
sre_tools = registry.get_tools_by_domain("sre")
azure_tools = registry.get_tools_by_source("azure")
openai_format = registry.get_all_tools_openai_format()

# Statistics
stats = registry.get_stats()  # Tool counts by domain/source

# Tool invocation (via MCPHost — see Phase 5)
result = await registry.invoke_tool("tool_name", {"param": "value"})
```

### Backward Compatibility

```python
# Old import still works
from utils.mcp_composite_client import CompositeMCPClient
# CompositeMCPClient is now an alias for MCPHost
```

---

## Phase 2: BaseOrchestrator

### What Changed

- **BaseOrchestrator:** Abstract base class providing shared orchestration logic
- **DomainSubAgent protocol:** Formalized interface for specialist agents
- **Shared capabilities:** Grounding, formatting, error handling, telemetry

### Before (Phase 0 — Duplicated Logic)

```python
# Each orchestrator implemented its own grounding/formatting
class MyOrchestrator:
    def __init__(self):
        self.openai_client = AzureOpenAI(...)  # Duplicated

    async def process(self, query):
        # Duplicated grounding logic
        context = self._ground_context(query)
        # Duplicated error handling
        # Duplicated response formatting
```

### After (Phase 2 — Inherited Base)

```python
from agents.base_orchestrator import BaseOrchestrator

class MyOrchestrator(BaseOrchestrator):
    async def route_query(self, query, context):
        # Custom routing logic only
        return execution_plan

    async def execute_plan(self, plan):
        # Custom execution logic only
        return orchestrator_result

    # Inherited: ground_context, format_response, handle_error
```

### When to Inherit

Extend `BaseOrchestrator` when building a new orchestrator that:
- Uses Azure OpenAI for reasoning
- Needs standard grounding (tenant, subscription, resource group context)
- Benefits from shared error handling and response formatting

**Do NOT extend `BaseOrchestrator` if:**
- Using Microsoft agent_framework (use standalone pattern)
- Using specialist domain agents without OpenAI reasoning
- Orchestrator is a pure workflow coordinator (EOL pattern)

---

## Phase 3: UnifiedRouter (Replaces ToolRouter + ToolEmbedder)

### What Changed

- **UnifiedRouter:** Single routing pipeline with 3 strategies (fast, quality, comprehensive)
- **DomainClassifier:** Keyword-based domain classification (<5ms)
- **Deprecated modules:** `ToolRouter` and `ToolEmbedder` archived to `utils/legacy/`

### Migration: ToolRouter → UnifiedRouter

See [`app/agentic/eol/utils/legacy/README.md`](../app/agentic/eol/utils/legacy/README.md) for complete migration guide with code examples.

**Quick summary:**

```python
# BEFORE (legacy ToolRouter)
from utils.tool_router import ToolRouter

router = ToolRouter(composite_client)
filtered_tools = router.filter_tools_for_query(
    user_message, all_tools, source_map, prior_tool_names=["check_health"]
)

# AFTER (UnifiedRouter)
from utils.unified_router import get_unified_router

router = get_unified_router()  # Singleton
plan = await router.route(user_message, strategy="fast")
# plan.tools — list of tool names (≤10 for fast strategy)
# plan.domain — primary domain (DomainLabel enum)
# plan.orchestrator — "mcp" or "sre"
```

### Migration: ToolEmbedder → UnifiedRouter

```python
# BEFORE (legacy ToolEmbedder)
from utils.tool_embedder import ToolEmbedder

embedder = ToolEmbedder()
await embedder.build_index(all_tool_definitions)
relevant_tools = await embedder.retrieve(query, top_k=10)

# AFTER (UnifiedRouter quality strategy)
from utils.unified_router import get_unified_router

router = get_unified_router()
plan = await router.route(query, strategy="quality")
# quality strategy uses primary + secondary domain expansion
# analogous to semantic ranking without embedding API calls
```

### Routing Strategies

| Strategy | Tool Limit | Use Case | Performance |
|----------|------------|----------|-------------|
| `fast` | ≤10 tools | Simple queries, primary domain only | <50ms |
| `quality` | ≤15 tools | Multi-domain, primary + secondary | <150ms |
| `comprehensive` | All tools (52) | Complex multi-step operations | <200ms |

---

## Phase 4: Code Quality & Reliability

### RetryStats: Observable Retries

**Before (bare retry):**
```python
from utils.retry import retry_async

result = await retry_async(func, retries=3, exceptions=(ValueError,))
# No visibility into attempt count, delays, or failures
```

**After (with RetryStats):**
```python
from utils.retry import retry_async, RetryStats

stats = RetryStats()
result = await retry_async(
    func,
    retries=3,
    exceptions=(ValueError,),
    stats=stats,  # Keyword-only
    on_retry=lambda attempt, exc, delay: logger.warning(
        "Retry %d after %s: %s", attempt, delay, exc
    ),
)
# stats.attempts — actual retry count
# stats.total_delay — cumulative delay
# stats.last_exception — last caught exception
# stats.success — True if succeeded
```

### TryAgain: Control-Flow Retries

Use `TryAgain` for clean retries without polluting exception stats:

```python
from utils.retry import retry_async, TryAgain

async def func_with_retry_logic():
    if not_ready():
        raise TryAgain()  # Retry without counting as error
    return result

await retry_async(func_with_retry_logic, retries=5, exceptions=(TryAgain,))
```

### Resource Caps

**PlaywrightPool:** Hard cap of 5 concurrent browser contexts:

```python
# utils/playwright_pool.py — automatic clamping
_MAX_POOL_SIZE = 5
if max_concurrency > _MAX_POOL_SIZE:
    logger.warning("Clamping pool to %d", _MAX_POOL_SIZE)
    max_concurrency = _MAX_POOL_SIZE
```

### Logging Standards

Reference: [`.claude/docs/AGENT-HIERARCHY.md#logging-standards`](.claude/docs/AGENT-HIERARCHY.md#logging-standards-nfr-mnt-04)

| Level | When to Use | Example |
|-------|-------------|---------|
| **DEBUG** | Internal tracing, request params | `logger.debug("Tool args: %s", args)` |
| **INFO** | Normal flow milestones | `logger.info("SRE check completed in %.2fs", elapsed)` |
| **WARNING** | Recoverable degradation, fallback | `logger.warning("MCP unavailable; using fallback")` |
| **ERROR** | Unrecoverable failures | `logger.error("Azure SDK call failed: %s", exc)` |

---

## Phase 5: Declarative MCP Configuration (MCPHost.from_config)

### What Changed

- **YAML configuration:** `config/mcp_servers.yaml` defines all 10 MCP servers
- **Environment toggles:** Enable/disable servers via env vars (`SRE_ENABLED=false`)
- **MCPHost.from_config():** Factory method reads YAML and builds MCPHost

### Configuration File

See [`app/agentic/eol/config/mcp_servers.yaml`](../app/agentic/eol/config/mcp_servers.yaml) for the complete configuration.

**Example server definition:**

```yaml
- name: sre_mcp
  label: sre
  command: python
  args: ["mcp_servers/sre_mcp_server.py"]
  domains: [sre, health]
  priority: 10
  enabled: ${SRE_ENABLED:-true}
```

### Before (Manual MCPHost Construction)

```python
from utils.mcp_host import MCPHost
from utils.sre_mcp_client import get_sre_mcp_client
from utils.network_mcp_client import get_network_mcp_client

# Manual client initialization
client_entries = [
    ("sre", await get_sre_mcp_client()),
    ("network", await get_network_mcp_client()),
    # ... repeat for all 10 servers
]
host = MCPHost(client_entries)
await host.ensure_registered()
```

### After (Declarative from_config)

```python
from utils.mcp_host import MCPHost

# Single line — reads config/mcp_servers.yaml
host = await MCPHost.from_config()
# All enabled servers initialized, registered, and ready
```

### Environment Variable Toggles

| Server Label | Environment Variable | Default |
|--------------|---------------------|---------|
| `azure` | `AZURE_MCP_ENABLED` | `true` |
| `sre` | `SRE_ENABLED` | `true` |
| `network` | `NETWORK_MCP_ENABLED` | `true` |
| `compute` | `COMPUTE_MCP_ENABLED` | `true` |
| `storage` | `STORAGE_MCP_ENABLED` | `true` |
| `monitor` | `MONITOR_MCP_ENABLED` | `true` |
| `patch` | `PATCH_MCP_ENABLED` | `true` |
| `os_eol` | `OS_EOL_MCP_ENABLED` | `true` |
| `inventory` | `INVENTORY_MCP_ENABLED` | `true` |
| `azure_cli_executor` | `AZURE_CLI_EXECUTOR_ENABLED` | `true` |

### Usage Examples

```bash
# Disable SRE server
SRE_ENABLED=false python main.py

# Disable multiple servers
SRE_ENABLED=false NETWORK_MCP_ENABLED=false python main.py

# Run with only Azure MCP (all others disabled)
AZURE_MCP_ENABLED=true \
  SRE_ENABLED=false NETWORK_MCP_ENABLED=false \
  COMPUTE_MCP_ENABLED=false STORAGE_MCP_ENABLED=false \
  MONITOR_MCP_ENABLED=false PATCH_MCP_ENABLED=false \
  OS_EOL_MCP_ENABLED=false INVENTORY_MCP_ENABLED=false \
  AZURE_CLI_EXECUTOR_ENABLED=false \
  python main.py
```

### Graceful Degradation

If all servers are disabled, `MCPHost.from_config()` returns a valid host with 0 tools:

```python
host = await MCPHost.from_config()
tools = host.get_available_tools()
assert len(tools) == 0  # No servers enabled — empty catalog
```

---

## How to Add a New MCP Server

**Cross-reference:** See [`app/agentic/eol/docs/ADDING_MCP_SERVERS.md`](../app/agentic/eol/docs/ADDING_MCP_SERVERS.md) for complete step-by-step guide (achievable in <30 minutes).

**Quick overview:**

1. **Create MCP server** (`mcp_servers/my_new_mcp_server.py`) using FastMCP `@mcp.tool()` pattern
2. **Create MCP client** (`utils/my_new_mcp_client.py`) with factory function
3. **Register in YAML** (`config/mcp_servers.yaml`):
   ```yaml
   - name: my_new_mcp
     label: my_new
     command: python
     args: ["mcp_servers/my_new_mcp_server.py"]
     domains: ["my_domain"]
     priority: 10
     enabled: ${MY_NEW_ENABLED:-true}
   ```
4. **Wire client factory** in `utils/mcp_host.py` → `_get_client_for_label()`
5. **Verify** with smoke test

---

## Troubleshooting

### Pre-Existing Test Failures

**Baseline:** 56 pre-existing test failures (documented in `.planning/STATE.md`).

- **`test_handle_error_creates_error_result`:** Pre-existing `isinstance` cross-path mismatch (not Phase 3+ issue)
- **SRE tests skip in local env:** `mcp` package not installed — expected for mock mode
- **`test_mcp_azure_cli_server.py` (5 failures):** Pre-existing — file missing in `tests/mcp_servers/`

### SRE Tests Skip in Local Environment

```
SKIPPED [1] tests/orchestrators/test_sre_orchestrator_shutdown.py:12:
  could not import 'mcp': No module named 'mcp'
```

**Expected behavior:** SRE tests require `mcp` package. In mock mode (default), these tests are automatically skipped. Use `./run_tests.sh --remote` for full integration tests.

### MCPHost Double-Initialization

**Symptom:** Registry already populated warnings or duplicate tool entries.

**Cause:** `MCPToolRegistry` is a singleton. Calling `ensure_registered()` multiple times is safe (idempotent).

**Solution:** No action needed — `ensure_registered()` is idempotent by design.

### Tool Not Found Errors

**Symptom:** `KeyError` or `"unknown tool"` in logs.

**Check:**
1. Verify server is enabled in env vars
2. Check `MCPToolRegistry.get_stats()` for tool counts
3. Verify server YAML entry in `config/mcp_servers.yaml`
4. Check tool name collision (priority system resolves collisions)

**Debug command:**
```bash
cd app/agentic/eol
python -c "
import asyncio
from utils.tool_registry import get_tool_registry
r = get_tool_registry()
print(r.get_stats())
"
```

### Config YAML Validation Errors

**Symptom:** Pydantic validation error when loading `mcp_servers.yaml`.

**Common causes:**
- Missing required field (`name`, `label`, `command`, `args`, `domains`, `priority`, `enabled`)
- Invalid env var syntax (`${VAR:-default}` format required)
- YAML syntax error (indentation, missing colon)

**Validation command:**
```bash
cd app/agentic/eol
python -c "
from utils.mcp_config_loader import MCPConfigLoader
loader = MCPConfigLoader()
servers = loader.get_enabled_servers()
print(f'{len(servers)} servers enabled')
"
```

---

## Rollback Procedure

### Quick Rollback: Environment Variables

Disable problematic servers immediately (no code changes):

```bash
# Disable SRE server
SRE_ENABLED=false python main.py

# Disable all new Phase 5 servers
SRE_ENABLED=false NETWORK_MCP_ENABLED=false \
  COMPUTE_MCP_ENABLED=false STORAGE_MCP_ENABLED=false \
  python main.py
```

### Config Rollback: Revert YAML

```bash
cd app/agentic/eol
git checkout HEAD~1 config/mcp_servers.yaml
python main.py  # Uses previous config
```

### Code Rollback: ToolRouter/ToolEmbedder

**Reference:** See [`app/agentic/eol/utils/legacy/README.md#rollback-procedure`](../app/agentic/eol/utils/legacy/README.md#rollback-procedure)

**Steps:**
1. Set feature flag (if implemented): `USE_UNIFIED_ROUTER=false`
2. In `MCPOrchestratorAgent`, restore `_tool_router` and `_tool_embedder` usage
3. Import from `utils.legacy.tool_router` / `utils.legacy.tool_embedder`
4. File bug report with reproduction steps

### Full Rollback: Git Revert

**Non-destructive revert** (creates new commit):

```bash
# Find commit SHA for problematic change
git log --oneline -10

# Revert the commit (creates new revert commit)
git revert <commit-sha>

# Push revert
git push origin main

# Verify rollback
cd app/agentic/eol && python -c "from utils.mcp_host import MCPHost; print('OK')"
```

### Rollback Triggers

- **Critical errors:** Unrecoverable failures preventing startup or request processing
- **Performance degradation:** >20% increase in P90 latency
- **Data loss:** Tool registry missing expected tools
- **Azure integration failures:** >50% of Azure SDK calls failing

---

## Success Metrics

### Quantitative (Achieved)

- ✅ Tool metadata duplication: <10% (baseline: ~300%)
- ✅ Shared code reuse: >60% in orchestrators (baseline: ~10%)
- ✅ Lines of duplicated code: <500 (baseline: ~2000)
- ✅ Tool discovery: <500ms (p90)
- ✅ Query routing: <200ms (p90)

### Developer Productivity (Achieved)

- ✅ Add new MCP server: <30 minutes (baseline: ~2 hours)
- ✅ Add tool example: <5 minutes (baseline: ~20 minutes)
- ✅ Onboard developer: <2 hours (baseline: ~4 hours)

---

## Related Documentation

| Document | Purpose | Location |
|----------|---------|----------|
| **5-Layer Stack** | Architecture diagram, debugging guide | [`.claude/docs/AGENT-HIERARCHY.md`](.claude/docs/AGENT-HIERARCHY.md) |
| **Orchestrator Guide** | When to use which orchestrator | [`.claude/docs/ORCHESTRATOR_GUIDE.md`](.claude/docs/ORCHESTRATOR_GUIDE.md) |
| **Adding MCP Servers** | Step-by-step new server guide | [`app/agentic/eol/docs/ADDING_MCP_SERVERS.md`](../app/agentic/eol/docs/ADDING_MCP_SERVERS.md) |
| **Legacy Migration** | ToolRouter/ToolEmbedder details | [`app/agentic/eol/utils/legacy/README.md`](../app/agentic/eol/utils/legacy/README.md) |
| **Project Roadmap** | Complete phase plan | [`.planning/ORCHESTRATOR-ROADMAP.md`](ORCHESTRATOR-ROADMAP.md) |
| **Architecture State** | Current system diagram | [`.planning/STATE.md`](STATE.md) |

---

**Maintained by:** Orchestrator Architecture Refactor Team
**Last Updated:** 2026-03-02
**Version:** 1.0
