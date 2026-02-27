# System Architecture

High-level architecture and design patterns of the GCC Demo platform.

---

## Overview

The GCC Demo platform consists of two major components:

1. **Terraform Infrastructure** - Azure hub-spoke networking with compute, storage, and monitoring
2. **EOL Agentic Application** - FastAPI-based AI agent platform for End-of-Life tracking and Site Reliability Engineering (SRE)

---

## Architecture Diagram

```
┌──────────────────────────────────────────────────────────────────────┐
│                        GCC Demo Platform                              │
└──────────────────────────────────────────────────────────────────────┘
                                    │
                ┌───────────────────┴───────────────────┐
                │                                       │
    ┌───────────▼──────────┐               ┌──────────▼──────────┐
    │  Terraform (IaC)     │               │   FastAPI App       │
    │  Hub-Spoke Network   │               │   (EOL + SRE)       │
    │  Compute + Storage   │               │   Multi-Agent       │
    └──────────────────────┘               └─────────────────────┘
            │                                        │
            │                                        │
    ┌───────▼────────┐                   ┌──────────▼─────────────┐
    │ 11 TF Modules  │                   │   20 API Routers       │
    │ 7 Demo Configs │                   │   41 Agent Modules     │
    │ 33 .tf Files   │                   │   71 Utility Modules   │
    └────────────────┘                   │   9 MCP Servers        │
                                         │   169 Python Files      │
                                         └────────────────────────┘
```

---

## Component Architecture: Terraform Infrastructure

### Hub-Spoke Topology

```
                    ┌─────────────────┐
                    │   Hub VNet      │
                    │  (Central)      │
                    └────────┬────────┘
                             │
          ┌──────────────────┼──────────────────┐
          │                  │                  │
    ┌─────▼─────┐     ┌─────▼─────┐     ┌─────▼─────┐
    │ Spoke 1   │     │ Spoke 2   │     │ Spoke N   │
    │ (Workload)│     │ (Workload)│     │ (Workload)│
    └───────────┘     └───────────┘     └───────────┘
```

### Terraform Module Hierarchy

```
main.tf (root)
    │
    ├─► networking/         # VNets, subnets, peering
    ├─► compute/            # VMs (Windows, Linux, NVA)
    ├─► gateways/           # VPN Gateway, ExpressRoute
    ├─► firewall/           # Azure Firewall
    ├─► storage/            # Storage accounts
    ├─► monitoring/         # Log Analytics, Insights
    ├─► arc/                # Azure Arc integration
    ├─► agentic/            # App Service + AOAI + Cosmos
    ├─► container_apps/     # Container Apps + ACR
    ├─► avd/                # Azure Virtual Desktop
    └─► routing/            # Route tables, Route Server
```

### Demo Scenarios

7 pre-configured demo scenarios with varying complexity:

1. Basic hub-spoke
2. Hub-spoke with firewall
3. Hub-spoke with VPN gateway
4. Hub-spoke with ExpressRoute
5. Full stack (firewall + VPN + ExpressRoute)
6. On-prem connectivity simulation
7. Custom configuration

**Pattern:** Each demo has:
- `demos/<name>/<name>.tfvars` - Configuration variables
- Variable-driven optional resources (`count = var.deploy_<component> ? 1 : 0`)
- Hub-specific variables (`hub_vnet_address_space`, `hub_gateway_subnet_prefix`)

---

## Component Architecture: FastAPI Application

### High-Level Application Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                    FastAPI Application                        │
│                      (main.py)                                │
└─────────────────────────┬────────────────────────────────────┘
                          │
        ┌─────────────────┼─────────────────┐
        │                 │                 │
    ┌───▼────┐      ┌────▼─────┐     ┌────▼─────┐
    │  API   │      │  Agents  │     │   MCP    │
    │Routers │      │  (41)    │     │ Servers  │
    │  (20)  │      │          │     │   (9)    │
    └───┬────┘      └────┬─────┘     └────┬─────┘
        │                │                │
        └────────────────┼────────────────┘
                         │
                    ┌────▼─────┐
                    │ Utilities│
                    │   (71)   │
                    └──────────┘
                         │
        ┌────────────────┼────────────────┐
        │                │                │
    ┌───▼────┐      ┌───▼─────┐     ┌───▼────┐
    │ Azure  │      │ Cosmos  │     │  Log   │
    │  AOAI  │      │   DB    │     │Analytics│
    └────────┘      └─────────┘     └────────┘
```

### Agent Hierarchy

The application uses a **multi-tier agent architecture**:

```
┌──────────────────────────────────────────────────────────┐
│                    Orchestrators                          │
│  EOLOrchestrator, SREOrchestrator, InventoryOrchestrator │
└────────────────────────┬─────────────────────────────────┘
                         │
         ┌───────────────┼───────────────┐
         │               │               │
    ┌────▼────┐    ┌────▼────┐    ┌────▼────┐
    │  Domain │    │  Domain │    │  Domain │
    │ Agents  │    │ Agents  │    │ Agents  │
    │  (EOL)  │    │  (SRE)  │    │(Inventory)│
    └────┬────┘    └────┬────┘    └────┬────┘
         │               │               │
    ┌────▼────┐    ┌────▼────┐    ┌────▼────┐
    │  Vendor │    │   Sub   │    │   MCP   │
    │ Agents  │    │ Agents  │    │ Clients │
    │ (OS/SW) │    │ (Patch/ │    │ (Tools) │
    │         │    │Monitor) │    │         │
    └─────────┘    └─────────┘    └─────────┘
```

#### Tier 1: Orchestrators (Top-Level Coordinators)

**Purpose:** High-level workflow coordination, multi-agent delegation

**Orchestrators:**
- `eol_orchestrator.py` - EOL workflow orchestration
- `sre_orchestrator.py` - SRE operations coordination
- `inventory_orchestrator.py` - Inventory scanning orchestration
- `mcp_orchestrator.py` - MCP tool routing and lifecycle

**Responsibilities:**
- Parse user intent
- Select appropriate domain agents
- Aggregate results from multiple agents
- Format responses via StandardResponse

**Pattern:**
```python
class EOLOrchestrator:
    def __init__(self):
        self.agents = self._initialize_agents()

    async def process_request(self, query: str):
        # 1. Classify intent
        # 2. Route to domain agent(s)
        # 3. Aggregate results
        # 4. Return StandardResponse
```

#### Tier 2: Domain Agents (Specialized Capabilities)

**Purpose:** Domain-specific logic and decision-making

**EOL Domain Agents:**
- `base_eol_agent.py` - Base class for EOL agents
- `microsoft_agent.py` - Microsoft products
- `endoflife_agent.py` - endoflife.date API
- `postgresql_agent.py` - PostgreSQL
- `redhat_agent.py` - Red Hat Enterprise Linux
- `ubuntu_agent.py` - Ubuntu
- `oracle_agent.py` - Oracle Database
- (+ 10 more vendor agents)

**SRE Domain Agents:**
- `base_sre_agent.py` - Base class for SRE agents
- `monitor_agent.py` - Monitoring and alerting
- `incident_response_agent.py` - Incident handling
- `remediation_agent.py` - Automated remediation
- `performance_analysis_agent.py` - Performance optimization
- `cost_optimization_agent.py` - Cost analysis
- `configuration_management_agent.py` - Config drift detection
- (+ 5 more SRE agents)

**Inventory Domain Agents:**
- `inventory_agent.py` - Inventory coordination
- `os_inventory_agent.py` - OS discovery
- `software_inventory_agent.py` - Software discovery

**Pattern:**
```python
class MicrosoftEOLAgent(BaseEOLAgent):
    def __init__(self):
        super().__init__(agent_name="microsoft")

    async def get_eol_data(self, software_name: str, version: str):
        # 1. Check cache (L1 + L2)
        # 2. Query vendor API or scrape
        # 3. Parse response
        # 4. Return standardized format
```

#### Tier 3: Sub-Agents and Specialized Workers

**Purpose:** Low-level operations, tool execution

**Sub-Agents:**
- `sre_sub_agent.py` - SRE tool execution
- `patch_sub_agent.py` - Patch operations
- `azure_ai_agent.py` - Azure AI integration
- `azure_ai_sre_agent.py` - Azure AI SRE

**Tool Clients:**
- `compute_mcp_client.py` - VM operations
- `network_mcp_client.py` - Network diagnostics
- `patch_mcp_client.py` - Patch management
- `inventory_mcp_client.py` - Inventory queries
- `os_eol_mcp_client.py` - EOL lookups
- `sre_mcp_client.py` - SRE tools
- `azure_mcp_client.py` - Azure MCP external server

---

### Model Context Protocol (MCP) Architecture

```
┌──────────────────────────────────────────────────────────┐
│              MCP Composite Client                         │
│         (Aggregates All MCP Sources)                      │
└────────────────────────┬─────────────────────────────────┘
                         │
        ┌────────────────┼────────────────┐
        │                │                │
    ┌───▼────┐      ┌───▼─────┐     ┌───▼────┐
    │ Local  │      │ Local   │     │ Azure  │
    │  MCP   │      │  MCP    │     │  MCP   │
    │Server 1│      │Server N │     │(External)│
    └───┬────┘      └───┬─────┘     └───┬────┘
        │                │                │
    FastMCP          FastMCP          @azure/mcp
    (stdio)          (stdio)          (npx, stdio)
```

**MCP Servers (Local FastMCP):**
1. `os_eol_mcp_server.py` - EOL lookups
2. `inventory_mcp_server.py` - Log Analytics queries
3. `compute_mcp_server.py` - VM operations
4. `storage_mcp_server.py` - Storage operations
5. `network_mcp_server.py` - Network diagnostics
6. `patch_mcp_server.py` - Patch management
7. `monitor_mcp_server.py` - Monitoring tools
8. `azure_cli_executor_server.py` - CLI executor
9. `azure_monitor_community_mcp_server.py` - GitHub scraper

**MCP Client Pattern:**
```python
from mcp.client import StdioServerParameters, stdio_client

# Spawn local MCP server
server_params = StdioServerParameters(
    command="python",
    args=[server_script_path]
)

async with stdio_client(server_params) as (read, write):
    async with ClientSession(read, write) as session:
        await session.initialize()
        tools = await session.list_tools()
        result = await session.call_tool(tool_name, arguments)
```

**Composite Client:**
- `mcp_composite_client.py` aggregates tools from all MCP sources
- Provides unified tool catalog to orchestrators
- Manages MCP server lifecycle (startup, shutdown)

---

### Caching Architecture

```
┌──────────────────────────────────────────────────────────┐
│                     Request                               │
└────────────────────────┬─────────────────────────────────┘
                         │
                    ┌────▼────┐
                    │ L1 Cache│
                    │(In-Mem) │
                    └────┬────┘
                         │ Miss
                    ┌────▼────┐
                    │ L2 Cache│
                    │(Cosmos) │
                    └────┬────┘
                         │ Miss
                    ┌────▼────┐
                    │  Source │
                    │(Azure/  │
                    │ Vendor) │
                    └────┬────┘
                         │
                    ┌────▼────┐
                    │ Response│
                    └─────────┘
                         │
        ┌────────────────┼────────────────┐
        │                │                │
    Store L1        Store L2        Return
    (always)      (if enabled)      (to caller)
```

**L1 Cache (In-Memory):**
- Module: `utils/eol_cache.py`, `utils/inventory_cache.py`, `utils/sre_cache.py`
- Storage: Python dictionaries
- TTL: 300 seconds (default, configurable)
- Scope: Process-local

**L2 Cache (Cosmos DB):**
- Module: `utils/cosmos_cache.py`, `utils/resource_inventory_cosmos.py`
- Storage: Cosmos DB containers
- TTL: Per-resource-type (1800s for VMs, 3600s for storage, etc.)
- Scope: Global (shared across instances)

**Cache Managers:**
- `cache_stats_manager.py` - Metrics tracking (hits, misses, latency)
- `inventory_cache.py` - Inventory-specific caching
- `sre_cache.py` - SRE operation caching

---

### API Router Architecture

**20 API Routers:**
- `health.py` - Health checks
- `debug.py` - Debug utilities
- `cache.py` - Cache statistics
- `eol.py` - EOL queries
- `inventory.py` - Inventory operations
- `alerts.py` - Alert management
- `communications.py` - Teams notifications
- `azure_mcp.py` - Azure MCP integration
- `agents.py` - Agent management
- (+ 11 more routers)

**Router Pattern:**
```python
from fastapi import APIRouter
from utils.response_models import StandardResponse
from utils.endpoint_decorators import standard_endpoint

router = APIRouter(prefix="/api/example", tags=["example"])

@router.get("/data", response_model=StandardResponse)
@standard_endpoint(agent_name="example", timeout_seconds=30)
async def get_data():
    result = await agent.fetch_data()
    return StandardResponse.success_response(data=result)
```

**Endpoint Decorators:**
- `@standard_endpoint` - Standard timeout + error handling + cache stats
- `@readonly_endpoint` - Shorter timeout, no cache tracking
- `@write_endpoint` - Longer timeout, no cache tracking

---

### Data Flow

#### EOL Query Flow

```
1. User Request
   │
   ├─► FastAPI Router (/api/eol/...)
   │   │
   │   └─► @standard_endpoint decorator
   │       │
   │       └─► EOLOrchestrator.process_query()
   │           │
   │           ├─► Check L1 Cache (eol_cache.get())
   │           │   └─► Hit? Return cached
   │           │
   │           ├─► Check L2 Cache (cosmos_cache.get_response())
   │           │   └─► Hit? Backfill L1, return cached
   │           │
   │           ├─► Route to Vendor Agent (e.g., MicrosoftEOLAgent)
   │           │   │
   │           │   ├─► Query vendor API or scrape
   │           │   └─► Parse + standardize response
   │           │
   │           ├─► Store in L2 Cache (cosmos_cache.store_response())
   │           ├─► Store in L1 Cache (eol_cache.set())
   │           └─► Return StandardResponse
   │
   └─► Return to user
```

#### Inventory Scan Flow

```
1. User triggers scan (/api/inventory/scan)
   │
   ├─► InventoryOrchestrator.run_full_scan()
   │   │
   │   ├─► Spawn OSInventoryAgent
   │   │   └─► inventory_mcp_client.call_tool("law_get_os_inventory")
   │   │       └─► Query Log Analytics (KQL: Heartbeat)
   │   │
   │   ├─► Spawn SoftwareInventoryAgent
   │   │   └─► inventory_mcp_client.call_tool("law_get_software_inventory")
   │   │       └─► Query Log Analytics (KQL: ConfigurationData)
   │   │
   │   ├─► For each discovered software:
   │   │   └─► EOLOrchestrator.get_eol_data(software, version)
   │   │       └─► (EOL flow as above)
   │   │
   │   ├─► Store inventory in Cosmos DB (resource_inventory_cosmos)
   │   ├─► Store metadata (resource_inventory_metadata)
   │   └─► Return summary
   │
   └─► Return scan results + EOL findings
```

#### SRE Operations Flow

```
1. User request (/api/sre/...)
   │
   ├─► SREOrchestrator.handle_request()
   │   │
   │   ├─► SRE Gateway classification (sre_gateway.classify())
   │   │   └─► LLM determines domain (monitoring, incident, patch, etc.)
   │   │
   │   ├─► Route to Domain Agent
   │   │   ├─► MonitorAgent (for monitoring queries)
   │   │   ├─► IncidentResponseAgent (for incidents)
   │   │   ├─► RemediationAgent (for remediation)
   │   │   └─► ...
   │   │
   │   ├─► Domain Agent → MCP Client → MCP Server → Azure SDK
   │   │   Example:
   │   │   MonitorAgent
   │   │     └─► network_mcp_client.call_tool("get_nsg_flow_logs")
   │   │         └─► network_mcp_server (NetworkManagementClient)
   │   │             └─► Azure Network API
   │   │
   │   └─► Return StandardResponse
   │
   └─► Return to user
```

---

### Authentication Flow

```
┌─────────────────────────────────────────────────────────┐
│              Application Startup                         │
└────────────────────────┬────────────────────────────────┘
                         │
                    ┌────▼────┐
                    │  Auth   │
                    │  Check  │
                    └────┬────┘
                         │
        ┌────────────────┼────────────────┐
        │                │                │
    ┌───▼────┐      ┌───▼─────┐     ┌───▼────┐
    │Service │      │ Managed │     │ Azure  │
    │Principal│      │ Identity│     │  CLI   │
    │ (SP)   │      │  (MI)   │     │Session │
    └───┬────┘      └───┬─────┘     └───┬────┘
        │                │                │
        └────────────────┼────────────────┘
                         │
                    ┌────▼────┐
                    │ Azure   │
                    │  Token  │
                    └────┬────┘
                         │
        ┌────────────────┼────────────────┐
        │                │                │
    ┌───▼────┐      ┌───▼─────┐     ┌───▼────┐
    │ Azure  │      │  Azure  │     │ Azure  │
    │  AOAI  │      │ Resource│     │ Cosmos │
    │  SDK   │      │  SDKs   │     │   DB   │
    └────────┘      └─────────┘     └────────┘
```

**Credential Priority:**
1. Service Principal (if `AZURE_SP_CLIENT_ID` set) → `ClientSecretCredential`
2. Managed Identity (if deployed to Azure) → `DefaultAzureCredential`
3. Azure CLI Session (local dev) → `AzureCliCredential` (part of Default chain)

---

### Configuration Management

```
┌──────────────────────────────────────────────────────────┐
│                  ConfigManager                            │
│            (utils/config.py)                              │
└────────────────────────┬─────────────────────────────────┘
                         │
        ┌────────────────┼────────────────┐
        │                │                │
    ┌───▼────┐      ┌───▼─────┐     ┌───▼────┐
    │ .env   │      │appsettings│   │ Env    │
    │  file  │      │  .json   │     │  Vars  │
    └───┬────┘      └───┬─────┘     └───┬────┘
        │                │                │
        └────────────────┼────────────────┘
                         │
        ┌────────────────┼────────────────┐
        │                │                │
    ┌───▼────┐      ┌───▼─────┐     ┌───▼────┐
    │ Azure  │      │   App   │     │Inventory│
    │ Config │      │ Config  │     │ Config │
    └────────┘      └─────────┘     └────────┘
```

**Config Dataclasses:**
- `AzureConfig` - Azure service endpoints (AOAI, Cosmos, Log Analytics)
- `AppConfig` - Application settings (title, version, timeouts, log level)
- `InventoryConfig` - Inventory-specific settings (TTLs, scanning)
- `PatchManagementConfig` - Patch operation timeouts
- `AgentPerformanceConfig` - Agent parallelism, caching
- `AzureAISREConfig` - Azure AI SRE agent integration

**Loading Order:**
1. Load `.env` file (if exists)
2. Load `appsettings.json` (if exists)
3. Override with environment variables
4. Validate required settings (`config.validate_config()`)

---

## Design Patterns

### 1. Orchestrator Pattern

**Purpose:** Decouple high-level workflow logic from domain-specific implementations

**Implementation:**
- Orchestrators coordinate multiple domain agents
- Domain agents focus on single responsibility
- Results aggregated via StandardResponse

### 2. Agent Hierarchy Pattern

**Purpose:** Multi-tier agent specialization

**Tiers:**
1. **Orchestrators** - Workflow coordination
2. **Domain Agents** - Specialized capabilities
3. **Sub-Agents / Clients** - Low-level operations

### 3. Caching Strategy Pattern

**Purpose:** Multi-tier caching for performance

**Tiers:**
- L1: Fast in-memory cache (microseconds)
- L2: Persistent shared cache (milliseconds)
- Source: External APIs (seconds)

### 4. MCP Tool Abstraction Pattern

**Purpose:** Uniform tool interface across local and external servers

**Implementation:**
- Local servers: FastMCP `@mcp.tool()` decorator
- Clients: Standardized `call_tool(name, args)` interface
- Composite client: Aggregated tool catalog

### 5. Response Standardization Pattern

**Purpose:** Consistent API responses across all endpoints

**Format:**
```json
{
  "success": true,
  "data": [...],
  "cached": true,
  "metadata": {},
  "error": null
}
```

### 6. Decorator-Based Patterns

**Purpose:** Cross-cutting concerns (timeout, error handling, caching)

**Decorators:**
- `@standard_endpoint` - Timeout + error handling + cache stats
- `@handle_api_errors` - API-level error handling
- `@handle_agent_errors` - Agent-level error handling
- `@retry_on_failure` - Retry logic with exponential backoff

---

## Scalability Considerations

### Horizontal Scaling

**FastAPI Application:**
- Stateless design (external cache in Cosmos DB)
- Async I/O throughout (high concurrency)
- Multiple instances behind load balancer

**Bottlenecks:**
- Azure OpenAI rate limits (tokens per minute)
- Cosmos DB RU consumption
- Log Analytics query limits

### Vertical Scaling

**Resource Allocation:**
- App Service Plan: Scale up (more CPU/RAM per instance)
- Container Apps: Scale out (more container instances)
- Cosmos DB: Autoscale RU (400-4000 RU/s default)

---

## Security Architecture

### Authentication & Authorization

**Layers:**
1. **Application Identity:** Service Principal or Managed Identity
2. **Azure SDK Auth:** ClientSecretCredential or DefaultAzureCredential
3. **RBAC Roles:** Least-privilege roles for Azure resources

**Secrets Management:**
- Current: Environment variables
- Recommended: Azure Key Vault references

### Network Security

**Terraform Deployments:**
- VNet integration for private connectivity
- NSGs for subnet-level filtering
- Azure Firewall for egress control
- Private endpoints for Cosmos DB, AOAI

---

## Monitoring & Observability

### Logging

**Levels:**
- DEBUG: Detailed diagnostics
- INFO: Normal operations
- WARNING: Non-critical issues
- ERROR: Critical failures

**Destinations:**
- Local: `stdout` (colored)
- Azure: `stderr` (plain for log collection)
- Log Analytics: Diagnostic settings

### Metrics

**Tracked:**
- Response time per endpoint
- Cache hit/miss rates (L1 + L2)
- Tool execution latency
- Token usage (LLM calls)

**API:** `/api/cache/stats`, `/api/debug/metrics`

### Tracing

**OpenTelemetry:**
- Distributed tracing support
- Application Insights integration
- Semantic conventions for AI operations

---

## Deployment Architecture

### Deployment Targets

1. **Azure App Service:**
   - Linux App Service Plan
   - VNet integration
   - Application settings via portal

2. **Azure Container Apps:**
   - Container Apps Environment
   - ACR for image storage
   - Multi-container support (app + MCP sidecar)

### CI/CD Integration

**Terraform:**
- Manual deployment via `run-demo.sh`
- State file: `terraform.tfstate` (local)

**Application:**
- Docker build: `deploy-container.sh`
- Image push to ACR
- Container Apps deployment

---

**Last Updated:** 2026-02-27
**Source:** Codebase exploration + architecture analysis
**Maintainer:** Development Team
