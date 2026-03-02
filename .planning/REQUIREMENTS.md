# Requirements - Orchestrator Architecture Refactor

**Project:** Orchestrator Architecture Clarity & Unification
**Date:** 2026-03-02
**Status:** Requirements Definition (from Research Synthesis)
**Scope:** Full architectural redesign (1-2 weeks)

---

## 1. Overview

### 1.1 Project Vision

Transform the Azure Agentic Platform's orchestrator architecture from a confusing dual-orchestrator model into a clear, maintainable system with:
- Single shared tool registry serving all orchestrators
- Clear boundaries between orchestrator responsibilities  
- Consistent UI/UX patterns across interfaces
- Industry-standard patterns for extensibility

### 1.2 Key Problems (from Research)

#### Orchestrator Confusion
- **MCPOrchestratorAgent**: 140+ tools, 12 sources, 3 parallel routing systems (ToolRouter, ToolEmbedder, Pipeline Router)
- **SREOrchestratorAgent**: 48 SRE tools, sub-agent delegation model
- **Issue**: Two incompatible architectures with overlapping capabilities

#### Tool Registration Chaos
- **5-layer registration flow**: MCP server → client wrapper → composite → manifest → orchestrator
- **Duplication**: Each tool registered 3-4 times across layers
- **Maintenance burden**: Changes require updates in multiple locations

#### UI Inconsistency
- **azure-mcp.html**: Dropdown-based tool selector with metadata-driven examples
- **sre.html**: Category-based button chips with hardcoded examples
- **Issue**: Same underlying capabilities presented differently

#### Routing Complexity Crisis
- **3 simultaneous routing systems** in production (legacy ReAct, Phase 5 pipeline, Phase 6 full pipeline)
- No clear migration path between systems
- Performance overhead from parallel routing

### 1.3 Solution Approach

**Unified Architecture** with:
1. **Shared Tool Registry** - MCP host pattern with centralized tool catalog
2. **Domain Classification Layer** - Route queries to appropriate specialist orchestrators
3. **Consistent UI Components** - Reusable example presentation patterns
4. **Single Routing Pipeline** - Consolidate 3 systems into one
5. **Standard Sub-Agent Integration** - Common pattern for domain specialists

---

## 2. Functional Requirements

### FR1: Shared Tool Registry

**Description:** Centralized MCP tool catalog accessible by all orchestrators

**Acceptance Criteria:**
- ✅ Single `MCPToolRegistry` class in `utils/tool_registry.py`
- ✅ Replaces scattered tool registration across orchestrators
- ✅ Supports dynamic tool discovery (not static lists)
- ✅ Provides tool metadata (name, description, parameters, source, domain)
- ✅ Handles tool lifecycle (register, discover, invoke, unregister)
- ✅ Zero-duplication goal (tools registered once, available everywhere)

**Interface:**
```python
class MCPToolRegistry:
    async def register_server(server_config: ServerConfig) -> None
    async def discover_tools(domain: Optional[str] = None) -> List[Tool]
    async def invoke_tool(tool_name: str, arguments: Dict) -> ToolResult
    def get_tool_metadata(tool_name: str) -> ToolMetadata
    def get_sources() -> List[str]
```

### FR2: Unified Orchestrator Base

**Description:** Common orchestration logic shared by all domain orchestrators

**Acceptance Criteria:**
- ✅ `BaseOrchestrator` class in `agents/base_orchestrator.py`
- ✅ Shared grounding logic (tenant/subscription/resource context)
- ✅ Common response formatting (HTML generation)
- ✅ Standard error handling and fallback patterns
- ✅ Unified telemetry and logging
- ✅ Sub-agent integration protocol

**Architecture:**
```
BaseOrchestrator (shared logic)
    ├─→ MCPOrchestratorAgent (general Azure operations)
    ├─→ SREOrchestratorAgent (SRE workflows)
    └─→ [Future domain orchestrators]
```

### FR3: Single Routing Pipeline

**Description:** Consolidate 3 parallel routing systems into one

**Acceptance Criteria:**
- ✅ Remove legacy ToolRouter/ToolEmbedder path
- ✅ Consolidate Phase 5 and Phase 6 pipelines
- ✅ Single entry point: `route_query(query, context) -> ExecutionPlan`
- ✅ Domain classification → specialist assignment
- ✅ Tool selection via semantic ranking
- ✅ Configurable routing strategy (fast/quality/comprehensive)

**Flow:**
```
User Query
    ↓
[Domain Classifier]
    ↓
[Specialist Orchestrator Selection]
    ├─→ SRE Agent (health, incidents, diagnostics)
    ├─→ General MCP Agent (other Azure operations)
    └─→ Inventory Assistant (resource discovery)
    ↓
[Tool Retrieval] (semantic + manifest-based)
    ↓
[Execution] (with verification)
    ↓
[Response Composition]
```

### FR4: Consistent UI Patterns

**Description:** Unified tool example presentation across templates

**Acceptance Criteria:**
- ✅ Shared `tool-examples.html` component
- ✅ Backend API: `GET /api/tools/examples?domain={domain}`
- ✅ Consistent category taxonomy (Health, Incident, Network, Security, Inventory, etc.)
- ✅ Unified metadata format for examples
- ✅ Both dropdown AND chip presentation modes supported
- ✅ Parameter hints and documentation links

**Component Interface:**
```html
{% macro render_tool_examples(mode='dropdown', domain=None) %}
  <!-- Renders examples in specified mode -->
  <!-- Fetches from /api/tools/examples -->
{% endmacro %}
```

### FR5: Domain Classification

**Description:** Intent-based routing to appropriate orchestrator

**Acceptance Criteria:**
- ✅ Classify queries into domains: SRE, Inventory, Network, Compute, Storage, General
- ✅ LLM-based classification with fallback to keyword patterns
- ✅ Multi-domain queries supported (e.g., "health + cost")
- ✅ User can override domain selection (UI affordance)
- ✅ Domain metadata includes: tools, example prompts, specialist agent

### FR6: Dynamic Tool Discovery

**Description:** Replace static tool lists with capability-based discovery

**Acceptance Criteria:**
- ✅ Tools discovered at runtime via `list_tools()` protocol
- ✅ Tool availability notifications (MCP `tools/list_changed`)
- ✅ Graceful degradation when servers unavailable
- ✅ Tool metadata refreshed periodically (configurable interval)
- ✅ No hardcoded tool names in orchestrator logic

### FR7: Declarative Server Configuration

**Description:** YAML-driven MCP server registration

**Acceptance Criteria:**
- ✅ `config/mcp_servers.yaml` defines all servers
- ✅ Config includes: name, command, args, env, domains, enabled
- ✅ Servers auto-register on startup
- ✅ Hot-reload support (config changes without restart)
- ✅ Override support for testing (mock servers)

**Example Config:**
```yaml
servers:
  - name: sre_mcp
    command: python
    args: ["-m", "mcp_servers.sre_mcp_server"]
    domains: [sre, health, incident]
    enabled: true
  - name: azure_cli
    command: python
    args: ["-m", "mcp_servers.azure_cli_executor_server"]
    domains: [general]
    enabled: true
```

---

## 3. Non-Functional Requirements

### NFR1: Performance

**Targets:**
- Tool discovery: <500ms for full catalog refresh
- Query routing: <200ms for domain classification
- Tool execution: Existing latency maintained
- Concurrent queries: Support 10+ simultaneous users

**Optimizations:**
- Tool metadata cached (with TTL)
- Semantic embeddings precomputed
- Connection pooling for MCP servers

### NFR2: Maintainability

**Goals:**
- Add new MCP server: <30 minutes (config + restart)
- Add new tool example: <5 minutes (metadata update)
- Onboard new developer: <2 hours with docs
- Code duplication: <10% across orchestrators

**Measures:**
- Clear separation of concerns
- Self-documenting code patterns
- Comprehensive inline documentation
- Architecture decision records (ADRs)

### NFR3: Backwards Compatibility

**Strategy:**
- **Breaking changes allowed** with migration guide
- Existing API endpoints preserved temporarily (deprecated)
- User-facing URLs unchanged (`/azure-mcp`, `/azure-ai-sre`)
- Graceful degradation for legacy clients

**Migration Support:**
- Deprecation warnings logged
- Feature flags for gradual rollout
- Side-by-side operation period (2 weeks)

### NFR4: Observability

**Requirements:**
- Structured logging (JSON format)
- Telemetry headers (X-Token-Count, X-Agent-Used)
- Request tracing (correlation IDs)
- Performance metrics (latency, token usage, cache hits)
- Error tracking (failures by tool/domain)

**Implementation:**
- Callback-based hooks for monitoring
- OpenTelemetry-compatible spans
- Dashboard for ops team

### NFR5: Extensibility

**Design Principles:**
- Plugin architecture for new orchestrators
- Hook points for custom routing logic
- Tool wrapper abstraction for non-MCP sources
- UI component library for custom interfaces

### NFR6: Testability

**Coverage Targets:**
- Unit tests: >80% for core logic
- Integration tests: All MCP server interactions
- E2E tests: Critical user flows
- Mocking support: All external dependencies

**Test Infrastructure:**
- Mock MCP servers for testing
- Fixture library for common scenarios
- CI/CD integration (run on PR)

---

## 4. Architecture Requirements

### AR1: MCP Host Pattern

**Adopt:** Official MCP spec pattern for multi-server management

**Components:**
- `MCPHost` - Coordinates multiple MCP clients
- One `MCPClient` per MCP server
- Dedicated connection management
- Capability negotiation per server

**Reference:** MCP Architecture Overview (industry-patterns.md)

### AR2: Tool Kits Pattern

**Adopt:** Logical grouping of related tools (from LangChain/Semantic Kernel)

**Examples:**
- `AzureHealthToolKit` - health check, diagnostics, metrics
- `AzureNetworkToolKit` - NSG audit, routing, connectivity
- `AzureCostToolKit` - cost analysis, recommendations, anomaly detection

**Benefits:**
- Easier discovery (browse by kit)
- Better LLM context (semantically grouped)
- Clearer documentation structure

### AR3: Domain Sub-Agent Protocol

**Adopt:** Standard interface for domain specialists

**Interface:**
```python
class DomainSubAgent(ABC):
    @abstractmethod
    async def handle_query(query: str, context: Dict) -> AgentResult
    
    @abstractmethod
    def get_capabilities() -> List[Capability]
    
    @abstractmethod
    def get_supported_domains() -> List[str]
```

**Implementations:**
- `SRESubAgent` - existing (health, incidents, diagnostics)
- `MonitorAgent` - existing (workbooks, alerts, queries)
- `PatchSubAgent` - existing (patch assessment, installation)
- `NetworkAgent` - existing (network audit, NSG analysis)

### AR4: Callback-Based Observability

**Adopt:** Hook pattern for monitoring (from Semantic Kernel)

**Hooks:**
```python
class ObservabilityHooks:
    async def on_tool_invoked(tool: str, args: Dict) -> None
    async def on_tool_completed(tool: str, result: ToolResult, duration: float) -> None
    async def on_routing_completed(domains: List[str], tools: List[str]) -> None
    async def on_error(error: Exception, context: Dict) -> None
```

**Usage:**
- Custom metrics collection
- External logging services
- Performance monitoring
- Alerting on failures

### AR5: Error Boundaries

**Pattern:** Prevent single tool failure from cascading

**Implementation:**
- Try/except wrappers around all tool calls
- Fallback strategies (retry, alternative tool, graceful degradation)
- Error context preservation (for debugging)
- User-friendly error messages (hide internals)

---

## 5. Success Criteria

### SC1: Clarity

**Measure:** Developer survey (1-5 scale)
- ✅ "I understand when to use each orchestrator" (target: >4.0)
- ✅ "Tool registration process is clear" (target: >4.5)
- ✅ "Adding new tools is straightforward" (target: >4.0)

### SC2: Reduced Duplication

**Measure:** Static code analysis
- ✅ Tool metadata duplication: <10% (currently ~300%)
- ✅ Shared code reuse: >60% in orchestrators
- ✅ Lines of duplicated code: <500 (from current ~2000)

### SC3: UI Consistency

**Measure:** User testing + code review
- ✅ Example presentation follows same patterns
- ✅ All tools have curated examples
- ✅ Parameter hints available for all tools
- ✅ Visual design consistent (spacing, colors, interactions)

### SC4: Performance

**Measure:** Automated benchmarks
- ✅ Tool discovery: <500ms (90th percentile)
- ✅ Query routing: <200ms (90th percentile)  
- ✅ End-to-end latency: No regression (within 5%)

### SC5: Maintainability

**Measure:** Development velocity
- ✅ Add new MCP server: <30min (currently ~2 hours)
- ✅ Add tool example: <5min (currently ~20min)
- ✅ Onboard developer: <2 hours with docs

### SC6: Test Coverage

**Measure:** Coverage reports
- ✅ Unit test coverage: >80%
- ✅ Integration tests: All MCP servers
- ✅ E2E tests: Critical workflows (health check, incident triage)
- ✅ Zero critical bugs in production

---

## 6. Constraints

### C1: No MCP Server Changes

**Constraint:** Existing MCP server implementations remain unchanged

**Rationale:** 
- Servers are stable and tested
- Changes would delay project
- Focus is orchestration layer, not tool implementation

### C2: Breaking Changes Allowed

**Constraint:** API/orchestrator interfaces can break with migration guide

**Rationale:**
- Current architecture cannot be incrementally fixed
- Clean slate enables proper design
- Migration period minimizes disruption

### C3: Timeline: 1-2 Weeks

**Constraint:** Full redesign completed within 2 weeks

**Phases:**
- Week 1: Foundation (registry, base orchestrator)
- Week 2: Migration (routing, UI, testing)

### C4: Preserve Tool Capabilities

**Constraint:** All existing tool functionality must work after refactor

**Validation:**
- Regression test suite (all current E2E tests pass)
- Tool inventory comparison (pre vs post)
- No user-reported capability loss

### C5: FastAPI + MCP Protocol

**Constraint:** Keep existing tech stack

**Preserved:**
- FastAPI for API layer
- MCP protocol for tool servers
- Python 3.11+
- Azure OpenAI for LLM calls

---

## 7. Dependencies

### D1: Research Findings

**Input:** 4 research documents completed
- orchestrator-patterns.md
- mcp-tool-registry.md
- ui-templates.md
- industry-patterns.md

### D2: Existing Codebase

**Assets to Preserve:**
- 9 MCP servers (all functional)
- Domain sub-agents (SRE, Monitor, Patch, Network)
- UI templates (layouts, styles)
- Test infrastructure

### D3: Industry Patterns

**References:**
- MCP specification (official)
- LangChain tool kits pattern
- CrewAI agent coordination
- Semantic Kernel plugin architecture
- AutoGen multi-agent patterns

### D4: Team Availability

**Resources Required:**
- Backend developer (full-time, 2 weeks)
- Frontend developer (part-time, 3 days)
- QA engineer (testing phase, 2 days)
- Code reviewer (ongoing)

---

## 8. Out of Scope

### OS1: MCP Server Implementations

Individual tool logic within MCP servers (sre_mcp_server.py, etc.) will not be modified.

### OS2: External Azure MCP Package

The `@azure/mcp` npm package integration stays as-is (no upstream changes).

### OS3: LLM Model Changes

No changes to Azure OpenAI models or prompting strategies (orthogonal concern).

### OS4: Cache Architecture

Existing L1/L2 cache system (memory + Cosmos) unchanged (separate optimization effort).

### OS5: Authentication/Authorization

No changes to auth flows, RBAC, or credential management.

---

## 9. Acceptance Process

### Phase 1: Requirements Approval

- ✅ Stakeholder review of this document
- ✅ Approval to proceed with roadmap creation

### Phase 2: Roadmap Approval

- ✅ Detailed phase breakdown created
- ✅ Deliverables and timelines confirmed
- ✅ Resource allocation approved

### Phase 3: Implementation Gates

Each phase requires:
- ✅ Plan approval (via `/gsd:plan-phase`)
- ✅ Code review (PR approval)
- ✅ Tests passing (CI/CD green)
- ✅ User acceptance (UAT if applicable)

### Phase 4: Final Acceptance

- ✅ All success criteria met
- ✅ Migration guide published
- ✅ Documentation updated
- ✅ Production deployment successful
- ✅ Zero critical bugs (2 week observation)

---

**Status:** Ready for roadmap creation
**Next Step:** Create `.planning/ROADMAP.md` with detailed phases
**Command:** `/gsd:plan-phase 1` (after roadmap approval)
