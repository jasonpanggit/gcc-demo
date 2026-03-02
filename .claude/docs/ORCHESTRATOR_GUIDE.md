# Orchestrator Guide

**Purpose:** When to use each orchestrator, how they relate to the orchestrator architecture.

**Date:** 2026-03-02
**Version:** 1.0

---

## Quick Decision Matrix

| Use Case | Orchestrator | Entry Point | Key Traits |
|----------|--------------|-------------|------------|
| **Azure resource operations via MCP tools** | MCPOrchestratorAgent | `POST /api/azure-mcp/chat` | BaseOrchestrator, UnifiedRouter, MCPHost.from_config(), ReAct pattern |
| **SRE health checks, incident triage** | SREOrchestratorAgent | `POST /api/sre/execute` | BaseSREAgent, UnifiedRouter, Azure AI SRE Agent, workflow-driven |
| **EOL lifecycle analysis, patching** | EOLOrchestratorAgent | `POST /api/eol/*` | Standalone, specialist EOL sub-agents, workflow coordinator |
| **Inventory queries, discovery** | InventoryAssistantOrchestrator | `POST /api/inventory/*` | Standalone, Microsoft agent_framework, resource discovery |

---

## MCPOrchestratorAgent

**Class:** `agents/mcp_orchestrator.py`

**Inherits:** `BaseOrchestrator` (`agents/base_orchestrator.py`)

**MCP Initialization:**
```python
from utils.mcp_host import MCPHost

# Phase 5+ declarative config
self._mcp_client = await MCPHost.from_config()
# Reads config/mcp_servers.yaml, initializes all enabled servers
```

**Routing:**
- Uses `UnifiedRouter` with 3 strategies: `fast`, `quality`, `comprehensive`
- Domain-aware tool filtering via `DomainClassifier`
- Process with routing: `BaseOrchestrator.process_with_routing(message, strategy="fast")`

**Pattern:**
- **ReAct Loop:** Reason → Act → Observe cycles with Azure OpenAI
- Direct tool execution through MCPHost
- Stateless: each request is independent
- All 52 tools from MCPToolRegistry available

**When to Use:**
- Ad-hoc Azure queries ("list all VMs in subscription X")
- Resource exploration and discovery
- One-off administrative tasks
- Multi-step operations requiring general reasoning
- Direct MCP tool calls

**NOT for:**
- SRE-specific health scoring and incident workflows → use SREOrchestratorAgent
- EOL lifecycle and patch management → use EOLOrchestratorAgent
- Inventory-focused discovery → use InventoryAssistantOrchestrator

**UI:** `/azure-mcp` (`templates/azure-mcp.html`)

**Example Request:**
```bash
curl -X POST http://localhost:8000/api/azure-mcp/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "List all storage accounts in subscription abc-123",
    "conversation_id": "conv-001"
  }'
```

---

## SREOrchestratorAgent

**Class:** `agents/sre_orchestrator.py`

**Inherits:** `BaseSREAgent` (NOT `BaseOrchestrator` — see ARC-04 recommendation)

**MCP Initialization:**
- Uses `SREMCPClient` (not MCPHost directly)
- **ARC-04 recommendation:** Consolidate SREMCPClient → MCPHost in Q2 2026
- Current pattern: `SREMCPClient` wraps multiple domain clients (SRE, network, compute, storage)

**Routing:**
- Uses `UnifiedRouter.route()` via `process_with_routing()` method
- Domain classification routes to appropriate SRE sub-agents
- Multi-agent coordination with `asyncio.gather()`

**Pattern:**
- **Agent-First:** Routes queries through Azure AI Agent (`gccsreagent`) for reasoning
- **Workflow-driven:** Specialized SRE patterns (health checks, incident response, compliance)
- **Stateful:** Maintains thread context across conversation
- Sub-agent delegation to `SRESubAgent` for domain-specific operations

**When to Use:**
- SRE health checks and monitoring
- Incident response workflows (triage → correlate → impact → RCA → remediate)
- Security compliance audits
- Automated remediation patterns
- Health scoring and anomaly detection

**NOT for:**
- General Azure resource queries → use MCPOrchestratorAgent
- EOL analysis → use EOLOrchestratorAgent
- Pure inventory discovery → use InventoryAssistantOrchestrator

**UI:** `/azure-ai-sre` (`templates/sre.html`)

**Example Request:**
```bash
curl -X POST http://localhost:8000/api/sre/execute \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Run health check on container app myapp-prod",
    "conversation_id": "sre-001"
  }'
```

**Note:** SREOrchestratorAgent has two tool access paths:
1. Via `SREMCPClient` (current)
2. Via `MCPToolRegistry` (Phase 1+ shared catalog)

Both access the same underlying tools. ARC-04 recommends consolidating to single MCPHost path in Q2 2026.

---

## EOLOrchestratorAgent

**Class:** `agents/eol_orchestrator.py`

**Inherits:** Standalone (no BaseOrchestrator)

**MCP Integration:** None — uses specialist EOL sub-agents

**Pattern:**
- **Specialist Agent Coordinator:** Routes to PatchSubAgent, NetworkAgent, etc.
- **Workflow-based:** EOL lifecycle stages (detect → assess → plan → execute → verify)
- Does NOT use MCPToolRegistry or MCPHost
- Own routing logic based on EOL domain expertise

**Specialist Sub-Agents:**
- `PatchSubAgent` — patch management operations
- `NetworkAgent` — network configuration analysis
- Domain-specific agents for OS EOL, framework EOL, etc.

**When to Use:**
- End-of-life OS and framework analysis
- Patch management planning and execution
- OS lifecycle queries ("which VMs run Windows Server 2012 R2?")
- Modernization planning

**NOT for:**
- General Azure operations → use MCPOrchestratorAgent
- SRE health checks → use SREOrchestratorAgent
- Inventory discovery → use InventoryAssistantOrchestrator

**UI:** `/eol` and various `/api/eol/*` endpoints

**Important:** Do NOT force MCPToolRegistry on this orchestrator. It uses specialist agents with own tool sets and patterns. Forcing MCP integration would break 1843 lines of working code.

**Example Request:**
```bash
curl -X POST http://localhost:8000/api/eol/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "resource_group": "prod-rg",
    "subscription_id": "abc-123"
  }'
```

---

## InventoryAssistantOrchestrator

**Class:** `agents/inventory_orchestrator.py`

**Inherits:** Standalone (uses Microsoft `agent_framework`)

**MCP Integration:** None — uses agent_framework patterns

**Pattern:**
- **Agent Framework:** Built on Microsoft's agent_framework library
- **Discovery-focused:** Subscription-wide resource scanning
- Does NOT use MCPToolRegistry or UnifiedRouter
- Own resource discovery engine

**When to Use:**
- Inventory queries across subscriptions
- Resource discovery and cataloging
- Subscription-wide scans
- Resource graph queries
- Cost and usage analysis

**NOT for:**
- Azure operations → use MCPOrchestratorAgent
- SRE workflows → use SREOrchestratorAgent
- EOL analysis → use EOLOrchestratorAgent

**UI:** `/inventory-assistant` (`templates/inventory-assistant.html`)

**Important:** Do NOT force MCPToolRegistry on this orchestrator. It uses agent_framework patterns incompatible with MCPHost. Respects existing 2211-line implementation.

**Example Request:**
```bash
curl -X POST http://localhost:8000/api/inventory/query \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Find all VMs with tag environment=prod",
    "subscription_id": "abc-123"
  }'
```

---

## Shared Infrastructure

All four orchestrators share:

### MCPToolRegistry (Singleton)

```python
from utils.tool_registry import get_tool_registry

registry = get_tool_registry()
# 52 tools from 10 MCP servers
# Zero duplication
```

**Used by:**
- ✅ MCPOrchestratorAgent (via MCPHost)
- ✅ SREOrchestratorAgent (via SREMCPClient → registry)
- ❌ EOLOrchestratorAgent (specialist agents)
- ❌ InventoryAssistantOrchestrator (agent_framework)

### UnifiedRouter (Singleton)

```python
from utils.unified_router import get_unified_router

router = get_unified_router()
plan = await router.route(query, strategy="fast")
```

**Used by:**
- ✅ MCPOrchestratorAgent (`process_with_routing()`)
- ✅ SREOrchestratorAgent (`process_with_routing()`)
- ❌ EOLOrchestratorAgent (own routing)
- ❌ InventoryAssistantOrchestrator (own routing)

### Graceful Shutdown

All orchestrators implement `shutdown()` method (Phase 4-02):

```python
# In main.py _run_shutdown_tasks():
await mcp_orchestrator.shutdown()
await sre_orchestrator.shutdown()
await eol_orchestrator.shutdown()
await inventory_orchestrator.shutdown()
```

---

## Architecture Layers

See [`.claude/docs/AGENT-HIERARCHY.md`](AGENT-HIERARCHY.md) for complete 5-layer stack diagram.

**Quick reference:**

```
┌─────────────────────────────────────────┐
│  Layer 1 — API Router (api/*.py)        │
└───────────────┬─────────────────────────┘
                │
┌───────────────▼─────────────────────────┐
│  Layer 2 — Orchestrator                 │
│  • MCPOrchestratorAgent                 │
│  • SREOrchestratorAgent                 │
│  • EOLOrchestratorAgent                 │
│  • InventoryAssistantOrchestrator       │
└───────────────┬─────────────────────────┘
                │
┌───────────────▼─────────────────────────┐
│  Layer 3 — Domain Agent/Sub-Agent       │
│  • SRESubAgent                          │
│  • PatchSubAgent                        │
│  • NetworkAgent                         │
└───────────────┬─────────────────────────┘
                │
┌───────────────▼─────────────────────────┐
│  Layer 4 — MCP Client (utils/*_client)  │
│  • MCPHost, MCPToolRegistry             │
└───────────────┬─────────────────────────┘
                │
┌───────────────▼─────────────────────────┐
│  Layer 5 — MCP Server (mcp_servers/)    │
│  • FastMCP @mcp.tool() implementations  │
└─────────────────────────────────────────┘
```

---

## Adding a New Orchestrator

### When to Create a New Orchestrator

Create a new orchestrator when:
- Domain requires fundamentally different reasoning pattern
- Existing orchestrators don't fit use case
- Need custom tool routing or workflow logic

**Do NOT create new orchestrator if:**
- Can be handled by existing orchestrator with different strategy
- Only need new MCP tools (add to registry instead)
- Only need new domain classification (extend DomainClassifier)

### Decision: Extend BaseOrchestrator or Standalone?

**Extend `BaseOrchestrator` if:**
- Using Azure OpenAI for reasoning
- Need standard grounding (tenant, subscription, resource group)
- Want shared error handling and response formatting
- ReAct or similar LLM-driven pattern

**Use Standalone pattern if:**
- Using different framework (agent_framework, custom)
- Workflow-based coordination (no LLM reasoning)
- Existing specialist agents with own patterns

### Implementation Checklist

1. **Create orchestrator class** (`agents/my_orchestrator.py`)
2. **Decide inheritance:** `BaseOrchestrator` or standalone
3. **Wire API router** (`api/my_orchestrator.py`)
4. **Add UI template** (`templates/my-orchestrator.html`)
5. **Implement `shutdown()`** (Phase 4-02 contract)
6. **Register in main.py** (`_run_startup_tasks()` and `_run_shutdown_tasks()`)
7. **Add tests** (`tests/orchestrators/test_my_orchestrator.py`)
8. **Document** (update this guide)

---

## Troubleshooting

### Which orchestrator should I use?

**Decision tree:**

1. **Is it Azure resource operations?** → MCPOrchestratorAgent
2. **Is it SRE/health/incident?** → SREOrchestratorAgent
3. **Is it EOL/patching?** → EOLOrchestratorAgent
4. **Is it inventory/discovery?** → InventoryAssistantOrchestrator

### Tool not available in orchestrator

**Check:**
1. Server enabled in `config/mcp_servers.yaml`?
2. Tool registered in `MCPToolRegistry`? (`registry.get_stats()`)
3. Orchestrator uses MCPHost or direct registry access?

**Debug:**
```bash
cd app/agentic/eol
python -c "
from utils.tool_registry import get_tool_registry
r = get_tool_registry()
print(r.get_stats())
"
```

### Orchestrator not responding

**Check:**
1. Orchestrator initialized in `main.py`?
2. Route wired in appropriate API router?
3. UI template exists and linked?
4. Logs show request received? (`correlation_id` in logs)

**Debug:**
```bash
curl -X GET http://localhost:8000/health
# Should return 200 OK
```

---

## Related Documentation

| Document | Purpose |
|----------|---------|
| [AGENT-HIERARCHY.md](AGENT-HIERARCHY.md) | 5-layer stack, debugging guide |
| [MIGRATION_GUIDE.md](../../.planning/MIGRATION_GUIDE.md) | Phase 1-5 migration guide |
| [ADDING_MCP_SERVERS.md](../../app/agentic/eol/docs/ADDING_MCP_SERVERS.md) | Add new MCP server guide |
| [STATE.md](../../.planning/STATE.md) | Current architecture state |

---

**Maintained by:** Orchestrator Architecture Refactor Team
**Last Updated:** 2026-03-02
**Version:** 1.0
