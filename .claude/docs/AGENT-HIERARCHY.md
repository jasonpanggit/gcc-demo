# Agent Hierarchy & Debugging Guide

Operational reference for the 5-layer agent stack in `app/agentic/eol`.
Covers layer responsibilities, request tracing, context propagation, debugging
patterns, simplification opportunities, and logging standards.

---

## 5-Layer Stack Overview

```
┌──────────────────────────────────────────────────────────────────────┐
│  Layer 1 — API Router   (api/*.py)                                   │
│  HTTP entry, request validation, StandardResponse wrapping           │
├──────────────────────────────────────────────────────────────────────┤
│  Layer 2 — Orchestrator (agents/*_orchestrator.py)                   │
│  Multi-agent coordination, asyncio.gather(), error aggregation       │
├──────────────────────────────────────────────────────────────────────┤
│  Layer 3 — Domain Agent (agents/*_sub_agent.py, agents/*_agent.py)   │
│  Domain logic, prompt construction, single-concern Azure/MCP calls   │
├──────────────────────────────────────────────────────────────────────┤
│  Layer 4 — MCP Client   (utils/*_mcp_client.py, mcp_composite_client)│
│  Tool routing, session management, retry, result normalisation       │
├──────────────────────────────────────────────────────────────────────┤
│  Layer 5 — MCP Server   (mcp_servers/*.py)                           │
│  Tool implementation, Azure SDK calls, data serialisation            │
└──────────────────────────────────────────────────────────────────────┘
```

External MCP (`@azure/mcp`) is reached via the composite client at Layer 4;
it is not a local `mcp_servers/` module.

---

## Layer Responsibilities

| Layer | Representative Files | Responsibility | Key Patterns |
|-------|---------------------|----------------|--------------|
| 1 — API Router | `api/eol.py`, `api/sre.py`, `api/inventory.py` | Validate HTTP request, call orchestrator, wrap result in `StandardResponse` | `@router.post`, `StandardResponse`, `@endpoint_stats` decorator |
| 2 — Orchestrator | `agents/eol_orchestrator.py`, `agents/sre_orchestrator.py`, `agents/inventory_orchestrator.py`, `agents/mcp_orchestrator.py` | Fan out to multiple sub-agents, aggregate results/errors, coordinate retries | `asyncio.gather()`, `ErrorAggregator`, `_spawn_background()`, `shutdown()` |
| 3 — Domain Agent | `agents/sre_sub_agent.py`, `agents/patch_sub_agent.py`, `agents/monitor_agent.py`, `agents/network_agent.py` | Domain-specific logic (SRE incident response, patch lifecycle, network diagnostics) | `DomainSubAgent` base class, single-concern design |
| 4 — MCP Client | `utils/sre_mcp_client.py`, `utils/mcp_composite_client.py`, `utils/patch_mcp_client.py`, `utils/network_mcp_client.py` | Route tool calls to correct server, retry on transient failure, normalise responses | `@retry_async`, `mcp_composite_client.call_tool()`, tool-name dispatch |
| 5 — MCP Server | `mcp_servers/sre_mcp_server.py`, `mcp_servers/network_mcp_server.py`, `mcp_servers/patch_mcp_server.py` | Implement `@mcp.tool()` decorated handlers, call Azure SDK, return structured dicts | `FastMCP`, `@mcp.tool()`, Azure SDK clients (Compute, Network, Monitor) |

---

## Request Lifecycle Walkthrough

Tracing an EOL analysis request from HTTP to MCP tool and back:

```
POST /api/eol/analyze  (HTTP)
 │
 ├─ [L1] api/eol.py ~line 45
 │       Validate request body → build query context
 │       Call eol_orchestrator.analyze()
 │
 ├─ [L2] agents/eol_orchestrator.py ~line 80
 │       asyncio.gather([
 │         os_inventory_agent.run(),
 │         software_inventory_agent.run(),
 │         eol_data_agent.run(),
 │       ])
 │       Aggregate partial failures via ErrorAggregator
 │
 ├─ [L3] agents/os_inventory_agent.py  (example sub-agent)
 │       Build inventory query
 │       Call mcp_composite_client.call_tool("inventory_list_vms", ...)
 │
 ├─ [L4] utils/mcp_composite_client.py ~line 60
 │       Route "inventory_list_vms" → utils/inventory_mcp_client.py
 │       Apply @retry_async with RetryStats (utils/retry.py)
 │       Return normalised dict
 │
 ├─ [L5] mcp_servers/inventory_mcp_server.py
 │       @mcp.tool() inventory_list_vms()
 │       Call Azure Compute SDK → list VMs
 │       Return serialised results
 │
 └─ Response bubbles back:
       L5 → L4 (normalised) → L3 (domain result) → L2 (aggregated)
       → L1 (StandardResponse wrapping) → HTTP 200
```

**SRE incident path** follows the same structure via `api/sre.py` →
`agents/sre_orchestrator.py` → `agents/sre_sub_agent.py` →
`utils/sre_mcp_client.py` → `mcp_servers/sre_mcp_server.py`.

---

## Context Propagation

### How correlation_id_var Flows

`utils/correlation_id.py` defines `correlation_id_var` — a Python `ContextVar`
that is automatically thread-safe and async-safe (each asyncio task has its own
copy via `contextvars` semantics).

**Propagation mechanism (automatic via structured logger):**

`utils/logger.py` registers `add_correlation_id` as a structlog processor
(line ~195). Every `logger.info/debug/warning/error(...)` call anywhere in the
codebase automatically appends `"correlation_id": <value>` to the log record if
a value is set in the ContextVar.

**Grep evidence — layers that consume the ContextVar:**

```
utils/correlation_id.py:16   — correlation_id_var definition (ContextVar)
utils/correlation_id.py:39   — set_correlation_id() sets the var
utils/correlation_id.py:49   — get_correlation_id() reads the var
utils/logger.py:169          — add_correlation_id() reads and injects into every log
utils/error_boundary.py:78   — error context includes correlation_id on exceptions
utils/error_boundary.py:190  — aggregator error context also includes it
utils/agent_message_bus.py:51 — AgentMessage carries correlation_id field
```

**Coverage summary:**

| Layer | correlation_id visible in logs? | Notes |
|-------|--------------------------------|-------|
| L1 API Router | ✅ via structured logger | All routers use `get_logger()` |
| L2 Orchestrator | ✅ via structured logger + ErrorAggregator | `error_boundary.py` captures it on failures |
| L3 Domain Agent | ✅ via structured logger | Any `logger.*()` call includes it automatically |
| L4 MCP Client | ✅ via structured logger | retry callbacks log with cid in context |
| L5 MCP Server | ⚠️ partial | Servers use `logging.getLogger()` (stdlib), not structured logger — cid not automatically injected |

### Known Gaps

1. **L5 MCP Servers** — `mcp_servers/*.py` use `logging.getLogger(__name__)` directly
   (stdlib), bypassing the structlog processor chain. `correlation_id` is not appended
   to server-side tool logs. To close this gap: replace stdlib loggers in MCP servers
   with `from utils.logger import get_logger`.

2. **L1 Injection missing** — No middleware or router currently calls
   `set_correlation_id()` on inbound requests. The ContextVar is only set
   explicitly in test helpers (`set_correlation_id(...)`) or via
   `ensure_correlation_id()` in utility code. For production traceability,
   a FastAPI middleware reading `X-Correlation-ID` from inbound headers and
   calling `set_correlation_id()` is recommended.

---

## Debugging Guide

### How to Trace a Failing Request

1. **Capture the correlation_id** — if injected, appears in all structured log entries
   as `"correlation_id": "abc-123..."`. Filter logs:
   ```bash
   grep '"correlation_id": "abc-123"' app.log
   ```

2. **Identify the failing layer** by log message pattern:

   | Pattern | Layer | File to inspect |
   |---------|-------|-----------------|
   | `"StandardResponse"` error or HTTP 500 | L1 | `api/*.py` |
   | `"gather failed"` / `ErrorAggregator` error | L2 | `agents/*_orchestrator.py` |
   | `"domain agent error"` / tool call timeout | L3 | `agents/*_sub_agent.py` |
   | `"MCP call failed"` / retry exhausted | L4 | `utils/*_mcp_client.py` |
   | `"Azure SDK"` exception / throttling | L5 | `mcp_servers/*.py` |

3. **Retry metrics** — if L4 retry fired, `RetryStats` attributes logged by
   `on_retry` callback (if wired): `attempt`, `delay`, `last_exception`.

4. **Background task failures** — `EOLOrchestratorAgent._spawn_background()` and
   `MCPOrchestratorAgent._spawn_background()` add a `done_callback` that logs
   exceptions silently; check for `"background task raised"` log lines.

5. **Playwright failures** — `PlaywrightPool` not initialized (e.g. pool disabled
   due to `PLAYWRIGHT_AVAILABLE=False`) logs: `"Playwright not available on this host"`.
   Concurrency cap warning: `"MAX_PLAYWRIGHT_CONCURRENCY=N exceeds hard cap 5"`.

### Common Failure Signatures Per Layer

```
L1  — AttributeError in response model   → missing field in StandardResponse
L1  — 422 Unprocessable Entity           → request body fails Pydantic validation
L2  — asyncio.TimeoutError               → sub-agent exceeded TimeoutConfig
L2  — ErrorAggregator has_errors=True    → partial failure; check errors[] list
L3  — KeyError / missing key in result   → MCP server response schema change
L4  — RetryStats.success=False           → all retries exhausted; see last_exception
L5  — azure.core.exceptions.HttpResponseError → Azure RBAC / quota / region issue
L5  — ClientConnectorError               → network path to Azure unavailable
```

---

## Architecture Simplification Recommendations (ARC-04)

> These are forward-looking recommendations for the **Q2 2026 review cycle**.
> No code changes are made in Phase 4.

### Opportunity 1: Consolidate MCP Client Routing

Currently each domain has its own `*_mcp_client.py` (sre, network, inventory,
patch, os_eol, monitor — 6 files) that largely duplicate the call/retry pattern.
The composite client (`mcp_composite_client.py`) already does routing by tool
name. Recommendation: deprecate individual domain clients and centralise all
tool dispatch in the composite client using a tool-manifest–driven registry.
This eliminates ~300 lines of near-duplicate boilerplate.

### Opportunity 2: Single Middleware for correlation_id Injection

Currently `set_correlation_id()` is never called on incoming HTTP requests in
production code — correlation IDs only flow when explicitly set in tests or
internal utility code. Adding one FastAPI `@app.middleware("http")` that reads
`X-Correlation-ID` (or generates one) and calls `set_correlation_id()` would
give every request end-to-end traceability with zero per-route changes.

### Opportunity 3: Unify MCP Server Logger Pattern

MCP servers use stdlib `logging.getLogger()` while agents/utils use the
structlog `get_logger()` wrapper. Unifying on `get_logger()` closes the L5
correlation-ID gap and ensures JSON-structured log output at the server layer.
Estimated impact: ~9 files, ~1 line change each.

### Opportunity 4: Per-Request SRE Orchestrator → Optional Singleton

`SREOrchestratorAgent` is created per-request (no state cached). For concurrent
SRE queries this means repeated initialisation overhead. The `get_sre_orchestrator_instance()`
stub already added in Phase 4 (`utils/sre_startup.py`) provides the hook to
migrate to a singleton with a proper lifecycle if profiling confirms the overhead
is significant.

---

## Logging Standards (NFR-MNT-04)

All application code should use the structlog-backed `get_logger()`:

```python
from utils.logger import get_logger
logger = get_logger(__name__, config.app.log_level)
```

### Level Guidelines

| Level | When to use | Example |
|-------|-------------|---------|
| `DEBUG` | Diagnostic internals, cache hit/miss, per-field inspection | `logger.debug("cache hit", key=cache_key)` |
| `INFO` | State transitions, startup/shutdown, request completed | `logger.info("request processed", duration_ms=42)` |
| `WARNING` | Recoverable abnormality, fallback path taken, cap enforced | `logger.warning("pool cap exceeded; clamping", requested=10, cap=5)` |
| `ERROR` | Unrecoverable failure within a component, exception caught | `logger.error("Azure SDK call failed", exc_info=True)` |
| `CRITICAL` | System-level failure requiring immediate operator attention | Reserved for startup failures or data-corruption scenarios |

### Correct vs Incorrect Examples

```python
# ✅ CORRECT — diagnostic detail is DEBUG
logger.debug("os inventory cache miss", hostname=hostname)

# ❌ INCORRECT — diagnostic detail logged at INFO floods production logs
logger.info("os inventory cache miss", hostname=hostname)

# ✅ CORRECT — fallback path is WARNING (operator should know)
logger.warning("Cosmos unavailable; using in-memory fallback", error=str(e))

# ❌ INCORRECT — fallback path at INFO is invisible in production log levels
logger.info("Cosmos unavailable; using in-memory fallback", error=str(e))

# ✅ CORRECT — stdlib logger ONLY in non-application infrastructure code
import logging
logger = logging.getLogger(__name__)   # acceptable in mcp_servers/*.py pending migration

# ❌ INCORRECT — stdlib logger in agent or utility code bypasses correlation_id injection
import logging
logger = logging.getLogger(__name__)   # agents/* and utils/* should use get_logger()
```

### Automatic Fields (via structlog processor chain)

Every log call via `get_logger()` automatically includes:
- `timestamp` — ISO-8601
- `level` — log level string
- `logger` — module name (from `__name__`)
- `correlation_id` — value from `correlation_id_var` ContextVar (if set)

---

**Version:** 1.0 (Created 2026-03-02)
**Covers:** Phase 4 ARC-01 through ARC-04, NFR-MNT-04
**See also:** `.claude/docs/SRE-ARCHITECTURE.md`, `.claude/docs/SRE-ORCHESTRATOR-README.md`, `.claude/docs/NETWORK-AGENT-GUIDE.md`
