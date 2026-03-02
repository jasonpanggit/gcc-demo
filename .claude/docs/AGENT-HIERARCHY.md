# Agent Hierarchy & Debugging Guide

Operational reference for the 5-layer agent stack in `app/agentic/eol`. Covers
responsibility boundaries, a step-by-step request trace, context propagation
evidence, debugging workflows, and architecture simplification recommendations.

See also: [NETWORK-AGENT-GUIDE.md](NETWORK-AGENT-GUIDE.md),
[SRE-ORCHESTRATOR-README.md](SRE-ORCHESTRATOR-README.md),
[SRE-ARCHITECTURE.md](SRE-ARCHITECTURE.md).

---

## 5-Layer Stack Overview

```
┌─────────────────────────────────────────────────────────────────┐
│  Layer 1 — API Router        (api/*.py)                         │
│  HTTP entry point · request validation · StandardResponse wrap  │
└───────────────────────────┬─────────────────────────────────────┘
                            │  dict / Pydantic model
┌───────────────────────────▼─────────────────────────────────────┐
│  Layer 2 — Orchestrator      (agents/*_orchestrator.py)         │
│  Multi-agent coordination · error aggregation · gather()        │
└───────────────────────────┬─────────────────────────────────────┘
                            │  domain request
┌───────────────────────────▼─────────────────────────────────────┐
│  Layer 3 — Domain Agent      (agents/sre_sub_agent.py           │
│                               agents/patch_sub_agent.py         │
│                               agents/monitor_agent.py)          │
│  Domain-specific logic · ReAct loops · tool selection           │
└───────────────────────────┬─────────────────────────────────────┘
                            │  tool call request
┌───────────────────────────▼─────────────────────────────────────┐
│  Layer 4 — MCP Client        (utils/*_mcp_client.py             │
│                               utils/mcp_host.py                 │
│                               utils/mcp_composite_client.py)    │
│  Tool routing · registry lookup · call dispatch                 │
└───────────────────────────┬─────────────────────────────────────┘
                            │  tool arguments (JSON)
┌───────────────────────────▼─────────────────────────────────────┐
│  Layer 5 — MCP Server        (mcp_servers/*.py)                 │
│  Tool implementation · Azure SDK calls · structured response    │
└─────────────────────────────────────────────────────────────────┘
```

---

## Layer Responsibilities

| Layer | Files | Responsibility | Key Patterns |
|-------|-------|----------------|--------------|
| **1 API Router** | `api/sre_orchestrator.py`, `api/azure_ai_sre.py`, `api/azure_mcp.py`, `api/inventory_asst.py`, + 16 others | Receive HTTP requests, validate input, emit `StandardResponse`, wire timeouts | `@with_timeout_and_stats`, `StandardResponse(success=…)` |
| **2 Orchestrator** | `agents/sre_orchestrator.py`, `agents/mcp_orchestrator.py`, `agents/inventory_orchestrator.py`, `agents/eol_orchestrator.py` | Fan-out to sub-agents, aggregate errors, enforce retry policy, manage lifecycle | `asyncio.gather()`, `retry_async()`, `.shutdown()` |
| **3 Domain Agent** | `agents/sre_sub_agent.py`, `agents/patch_sub_agent.py`, `agents/monitor_agent.py`, `agents/network_agent.py` | Domain-specific reasoning, multi-step ReAct loops, tool selection | `DomainSubAgent` protocol, `get_capabilities()` |
| **4 MCP Client** | `utils/mcp_host.py`, `utils/sre_mcp_client.py`, `utils/network_mcp_client.py`, `utils/*_mcp_client.py` | Resolve tool names against `MCPToolRegistry`, dispatch calls, deserialise responses | `MCPHost.call_tool()` → `MCPToolRegistry.invoke_tool()` |
| **5 MCP Server** | `mcp_servers/sre_mcp_server.py`, `mcp_servers/network_mcp_server.py`, `mcp_servers/patch_mcp_server.py`, + 6 others | `@mcp.tool()` implementations, Azure SDK calls, structured JSON return | FastMCP `@mcp.tool()`, `logger.info()` milestones |

---

## Request Lifecycle Walkthrough

Trace: *"Run SRE health check for my container app"* from HTTP to MCP tool and back.

### Step 1 — HTTP arrives at Layer 1 (API Router)
```
POST /api/sre/execute
  └─ api/sre_orchestrator.py:138  @router.post("/execute")
       ensure_correlation_id()    ← sets correlation_id_var (Phase 2)
       StandardResponse wrap      ← utils/response_models.py
```

### Step 2 — Dispatch to Layer 2 (Orchestrator)
```
api/sre_orchestrator.py:~158
  └─ agents/sre_orchestrator.py:408  SREOrchestratorAgent.handle_request()
       classify_sre_domain()         ← utils/query_patterns.py
       asyncio.gather(sub-agents)
```

### Step 3 — Domain logic in Layer 3 (Domain Agent)
```
agents/sre_orchestrator.py:~450
  └─ agents/sre_sub_agent.py        SRESubAgent._run() ReAct loop
       LLM call → tool_name chosen  ← Azure OpenAI
       _call_tool("check_resource_health", {...})
```

### Step 4 — Tool routing in Layer 4 (MCP Client)
```
agents/sre_sub_agent.py
  └─ utils/mcp_host.py:253          MCPHost.call_tool(tool_name, args)
       utils/tool_registry.py:504   MCPToolRegistry.invoke_tool()
         → resolves "check_resource_health" → sre domain, priority 10
         → routes to utils/sre_mcp_client.py:190  SREMCPClient.call_tool()
```

### Step 5 — Tool execution in Layer 5 (MCP Server)
```
utils/sre_mcp_client.py → FastMCP protocol
  └─ mcp_servers/sre_mcp_server.py:402  check_resource_health()
       Azure SDK call (ResourceManagementClient / Monitor)
       returns structured dict: {"status": "Healthy", "metrics": {...}}
```

### Step 6 — Response bubbles back up
```
MCP Server → MCP Client → Domain Agent → Orchestrator → API Router
  └─ Orchestrator aggregates results from all sub-agents
  └─ api/sre_orchestrator.py:231  return StandardResponse(success=True, data=…)
  └─ HTTP 200 with correlation_id in response body
```

---

## Context Propagation

### How correlation_id flows

`correlation_id_var` is a Python `contextvars.ContextVar` defined in
`utils/correlation_id.py:16`. Because `asyncio` propagates `Context` objects
automatically across `await` boundaries, the ID set at Layer 1 is visible at
all lower layers without explicit passing.

```
Layer 1 (API)         ensure_correlation_id() → sets correlation_id_var
                                │
Layer 2 (Orchestrator)  asyncio.gather() → child tasks inherit Context
                                │
Layer 3 (Domain Agent)  logger.info() → add_correlation_id processor appends cid
                                │
Layer 4 (MCP Client)    error_boundary.py:78 → captures cid in error context
                                │
Layer 5 (MCP Server)    logger.info() → same processor appends cid (if structlog)
```

### Grep evidence (codebase scan, 2026-03-02)

| Location | Evidence |
|----------|---------|
| `utils/correlation_id.py:16` | `correlation_id_var: ContextVar` defined |
| `utils/logger.py:156` | `add_correlation_id` processor injects cid into every log record |
| `utils/logger.py:195` | Processor registered in structlog chain |
| `utils/error_boundary.py:78` | `get_correlation_id()` captured in error context |
| `utils/error_boundary.py:188` | Second error path also captures cid |
| `utils/agent_message_bus.py:34` | `correlation_id` field on inter-agent messages |
| `utils/agent_message_bus.py:207` | New UUID generated per message-bus request |

### Known gaps

- **Layers 1–3 (API → Orchestrators → Domain Agents):** `correlation_id_var` is
  set via `ensure_correlation_id()` but there is no middleware that automatically
  seeds the var from an incoming `X-Correlation-ID` HTTP header. The ID is
  generated fresh per request in `utils/correlation_id.py:52`.
- **Layer 5 (MCP Servers):** MCP servers run as separate subprocess/in-process
  servers; they see the structlog processor but the `ContextVar` is not propagated
  across the FastMCP protocol boundary. Correlation IDs in MCP tool logs come from
  the server's own logger, not the parent request context.
- **Mitigation:** Structlog's `add_correlation_id` processor attaches the cid to
  every log record emitted from Layers 1–4, making cross-layer log correlation
  possible by filtering on `correlation_id`.

---

## Debugging Guide

### How to trace a failing request

1. **Find the correlation_id**: Every `StandardResponse` includes the cid in its
   log context. Search application logs for the UUID seen in the error response.

2. **Filter logs by layer**:
   ```
   # Layer 1 logs — request receipt, timeout, StandardResponse wrap
   grep "correlation_id=<CID>" logs | grep "api\."

   # Layer 2 logs — orchestrator dispatch, gather errors
   grep "correlation_id=<CID>" logs | grep "agents\..*orchestrator"

   # Layer 3 logs — ReAct loop iterations, tool choices
   grep "correlation_id=<CID>" logs | grep "agents\.sre_sub_agent\|agents\.patch"

   # Layer 4 logs — tool routing, registry misses
   grep "correlation_id=<CID>" logs | grep "utils\.mcp_host\|utils\.tool_registry"

   # Layer 5 logs — Azure SDK errors, tool return values
   grep "correlation_id=<CID>" logs | grep "mcp_servers\."
   ```

3. **Check retry stats**: If a tool is retrying, `utils/retry.py` emits
   `on_retry` callbacks with `(attempt, exc, delay)`. Look for
   `"retry attempt"` entries near the cid.

### Common failure signatures per layer

| Layer | Symptom | Log Signal | Check |
|-------|---------|------------|-------|
| **L1 API** | 422 or 500 | `"StandardResponse success=False"` | Input validation; timeout exceeded `with_timeout_and_stats` |
| **L2 Orchestrator** | Partial results | `"gather error"` or `"sub-agent failed"` | Individual sub-agent logs; error aggregator `utils/error_aggregator.py` |
| **L3 Domain Agent** | Empty tool list | `"no tools available"` | MCP server connectivity; `MCPToolRegistry.get_stats()` |
| **L4 MCP Client** | Tool not found | `"unknown tool"` or `KeyError` | Tool name collision/priority; `utils/tool_registry.py` registry state |
| **L5 MCP Server** | Azure error | `"AzureError"` / `"ResourceNotFound"` | Azure credential; subscription/resource group scoping |

### Useful one-liners

```bash
# Verify tool registry has 52 tools
python -c "
import asyncio, sys; sys.path.insert(0,'app/agentic/eol')
from utils.tool_registry import get_tool_registry
r = get_tool_registry(); print(r.get_stats())
"

# Check which tools are registered per domain
python -c "
import sys; sys.path.insert(0,'app/agentic/eol')
from utils.tool_registry import get_tool_registry
r = get_tool_registry()
for domain in ['sre','network','compute','storage','patch']:
    tools = r.get_tools_by_domain(domain)
    print(f'{domain}: {len(tools)} tools')
"
```

---

## Architecture Simplification Recommendations (ARC-04)

> **Scope:** These are forward-looking recommendations for Q2 2026 review.
> No code changes are made in Phase 4. Each item is tagged with the
> estimated effort and the concrete opportunity.

### Rec-1: Merge `SREMCPClient` into `MCPHost`

**Opportunity:** `utils/sre_mcp_client.py:190` duplicates `MCPHost.call_tool()`
semantics. SRE-specific routing logic (`SREMCPDisabledError` handling) could live
as a plugin or subclass of `MCPHost` rather than a parallel call path. This would
reduce two divergent tool-call paths to one.

**Effort:** Medium (2–3 days). Requires updating `agents/sre_orchestrator.py` and
`agents/sre_sub_agent.py` to use `MCPHost` exclusively.

**Benefit:** One canonical tool-dispatch path → easier to instrument, test, and
extend with new retry / observability hooks.

### Rec-2: Replace per-file `logger = get_logger(__name__)` with a class-level mixin

**Opportunity:** Every agent and MCP server file repeats the same two-line logger
setup. A `LoggingMixin` or `@logged` class decorator that wires `self.logger`
automatically would reduce boilerplate and ensure every module uses the same
structlog configuration.

**Effort:** Low (1 day). Pure refactor; no behaviour change.

**Benefit:** Eliminates risk of modules accidentally calling `logging.getLogger`
directly (bypassing structlog + `add_correlation_id` processor).

### Rec-3: Consolidate `BaseSREAgent` and `BaseOrchestrator` hierarchies

**Opportunity:** `SREOrchestratorAgent` extends `BaseSREAgent` while
`MCPOrchestratorAgent` extends `BaseOrchestrator`. The two base classes share
significant surface area (lifecycle, shutdown, error handling). A unified
`BaseOrchestrator` with opt-in SRE capability mixins would make the hierarchy
explicit and reduce duplicated lifecycle code (e.g., twin `shutdown()` stubs
introduced in Phase 4-02).

**Effort:** Large (1 week). Requires careful test coverage before migration.

**Benefit:** Single lifecycle contract for all orchestrators; `shutdown()` tested
in one place; new orchestrator types inherit correct defaults.

### Rec-4: Promote `correlation_id_var` seeding to FastAPI middleware

**Opportunity:** Currently no middleware injects `X-Correlation-ID` headers from
incoming requests into `correlation_id_var` (see Context Propagation gap above).
A one-file FastAPI middleware in `utils/middleware/correlation_id_middleware.py`
would close this gap and enable end-to-end distributed tracing from client to
MCP server.

**Effort:** Low (half-day). Pure addition; no existing code changes.

**Benefit:** External callers (Azure API Management, LB health probes) can pass
their own trace IDs; full request chain becomes searchable by a single ID.

---

## Logging Standards (NFR-MNT-04)

| Level | When to use | Concrete example |
|-------|-------------|-----------------|
| **DEBUG** | Internal tracing, request params, diagnostic details | `logger.debug("Tool args: %s", args)` |
| **INFO** | Normal flow milestones — request received, tool called, response sent | `logger.info("SRE health check completed in %.2fs", elapsed)` |
| **WARNING** | Recoverable degradation, fallback path, clamping | `logger.warning("Playwright cap exceeded; clamping to %d", MAX)` |
| **ERROR** | Unrecoverable failures that prevent a response being returned | `logger.error("Azure SDK call failed: %s", exc)` |

### Correct vs incorrect usage

```python
# ✅ CORRECT — fallback/degraded path is WARNING (system continues)
logger.warning("MCP server unavailable; returning fallback response")

# ❌ INCORRECT — fallback is not an error
logger.error("MCP server unavailable; returning fallback response")

# ✅ CORRECT — diagnostic detail is DEBUG
logger.debug("Routing query '%s' to domain '%s'", query[:80], domain)

# ❌ INCORRECT — request-param detail is noise at INFO
logger.info("Routing query '%s' to domain '%s'", query[:80], domain)

# ✅ CORRECT — milestone is INFO
logger.info("Tool '%s' completed (attempt=%d, elapsed=%.2fs)", name, attempt, elapsed)

# ❌ INCORRECT — tool args are DEBUG-level detail, not a milestone
logger.info("Calling tool '%s' with args %s", name, args)
```

### Pattern reminder

```python
# Every module: one logger at module level
logger = get_logger(__name__, config.app.log_level)

# Do NOT use standard library directly (bypasses correlation_id processor)
# ❌ import logging; logger = logging.getLogger(__name__)
# ✅ from utils.logger import get_logger; logger = get_logger(__name__)
```

---

**Version:** 1.0 (Created 2026-03-02)
**Author:** Phase 4-03 Code Quality Polish
**Covers:** ARC-01 (5-layer stack), ARC-02 (debugging guide), ARC-03 (context propagation), ARC-04 (simplification recs), NFR-MNT-04 (logging standards)
