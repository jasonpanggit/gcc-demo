# External Integrations

Comprehensive map of external services, APIs, databases, and third-party integrations in the GCC Demo platform.

---

## Integration Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     GCC Demo Application                     │
│                   (FastAPI + MCP Agents)                     │
└─────────────────────────────────────────────────────────────┘
         │          │          │          │          │
         ├──────────┼──────────┼──────────┼──────────┤
         ▼          ▼          ▼          ▼          ▼
   ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐
   │ Azure   │ │ Cosmos  │ │   Log   │ │ Azure   │ │ Teams   │
   │  AOAI   │ │   DB    │ │Analytics│ │   MCP   │ │Webhooks │
   └─────────┘ └─────────┘ └─────────┘ └─────────┘ └─────────┘
         │          │          │          │          │
   ┌─────────────────────────────────────────────────────┐
   │            Azure Management Plane (ARM)             │
   │  Resource Graph • Network Watcher • Monitoring      │
   │  Compute • Storage • Network • Patch Management     │
   └─────────────────────────────────────────────────────┘
```

---

## Azure Cloud Services

### Azure OpenAI (Primary AI Platform)

**Purpose:** LLM inference for agentic operations

**Configuration:**
- `AZURE_OPENAI_ENDPOINT` - Service endpoint URL
- `AZURE_OPENAI_DEPLOYMENT` - Model deployment name (gpt-4o, gpt-4o-mini)

**Usage:**
- AI agent orchestration
- Natural language processing
- Classification and analysis
- EOL data interpretation

**Implementation:**
- SDK: `openai==2.21.0`
- Token counting: `tiktoken 0.12.0`
- Location: `utils/config.py` (`AzureConfig.aoai_endpoint`)

---

### Azure Cosmos DB (NoSQL Database)

**Purpose:** L2 persistence layer for caching and inventory storage

**Configuration:**
- `AZURE_COSMOS_DB_ENDPOINT` - Cosmos DB endpoint
- `AZURE_COSMOS_DB_DATABASE` - Database name (default: `eol_cache`)
- `AZURE_COSMOS_DB_CONTAINER` - Default container (default: `eol_responses`)

**Containers:**
1. **eol_responses** - EOL query response cache
2. **resource_inventory** - Azure resource inventory data
3. **resource_inventory_metadata** - Inventory scan metadata

**Configuration Details:**
- Autoscale RU: 400-4000 RU/s (configurable via env vars)
- TTL-based expiration for cache entries
- Optional: Can be disabled for local/mock development

**Implementation:**
- SDK: `azure-cosmos 4.7.0`
- Location: `utils/config.py` (`AzureConfig.cosmos_*`)
- Clients: Response cache, inventory cache, metadata cache

**Terraform Provisioning:**
- Module: `modules/agentic/` (creates Cosmos DB + containers)

---

### Azure Log Analytics

**Purpose:** Resource inventory queries and operational logs

**Configuration:**
- `LOG_ANALYTICS_WORKSPACE_ID` - Workspace GUID
- `LOG_ANALYTICS_WORKSPACE_RESOURCE_ID` - Full ARM resource ID

**Usage:**
- OS inventory queries (KQL)
- Software inventory discovery
- Heartbeat monitoring
- Update compliance tracking

**Implementation:**
- SDK: `azure-monitor-query 1.4.0`
- MCP Server: `inventory_mcp_server.py`
- Tools: `law_get_os_inventory`, `law_get_software_inventory`

**Sample KQL Queries:**
```kql
// OS Inventory
Heartbeat
| where TimeGenerated > ago(30d)
| summarize arg_max(TimeGenerated, *) by Computer
| project Computer, OSType, OSVersion

// Software Inventory
ConfigurationData
| where ConfigDataType == "Software"
| summarize by Computer, SoftwareName, SoftwareVersion
```

---

### Azure Resource Graph

**Purpose:** Large-scale Azure resource queries and dependency mapping

**Configuration:**
- Subscription ID: `SUBSCRIPTION_ID` or `AZURE_SUBSCRIPTION_ID`

**Usage:**
- Patch assessment queries
- Resource inventory aggregation
- Compliance reporting
- Cross-subscription queries

**Implementation:**
- SDK: `azure-mgmt-resourcegraph 8.0.1`
- MCP Server: `patch_mcp_server.py`
- Authentication: DefaultAzureCredential or ClientSecretCredential

---

### Azure Monitor

**Purpose:** Monitoring, diagnostics, and alerting

**Capabilities:**
- Network Watcher connectivity checks
- Scheduled query alerts
- Application Gateway backend health
- VPN/ExpressRoute diagnostics
- NSG flow logs

**Implementation:**
- SDK: `azure-mgmt-monitor 6.0.2`, `azure-monitor-query 1.4.0`
- MCP Servers: `network_mcp_server.py`, `monitor_mcp_server.py`
- Tools: Network diagnostics, WAF health, route tables

**Azure Monitor Community Integration:**
- MCP Server: `azure_monitor_community_mcp_server.py`
- Scrapes GitHub: AzureMonitorCommunity repo
- Downloads workbooks, queries, alerts
- Deploys via Azure CLI

---

### Azure Management SDKs (ARM)

**Purpose:** Azure resource management and operations

**Core SDKs:**
- `azure-mgmt-compute 33.0.0` - VM operations
- `azure-mgmt-network 27.0.0` - Network operations
- `azure-mgmt-resource 23.1.1` - Resource management
- `azure-mgmt-storage 21.2.1` - Storage operations
- `azure-mgmt-resourcehealth 1.0.0b1` - Health checks

**Operations:**
- VM lifecycle (start, stop, restart, patch)
- Network diagnostics (NSG, routes, connectivity)
- Storage account management
- Resource health queries
- Private DNS management

**MCP Servers:**
- `compute_mcp_server.py` - VM operations
- `network_mcp_server.py` - Network diagnostics
- `storage_mcp_server.py` - Storage management
- `patch_mcp_server.py` - Patch operations

---

### Azure CLI Integration

**Purpose:** Command-line operations for complex Azure tasks

**Configuration:**
- `AZURE_CLI_EXECUTOR_ENABLED` - Enable/disable CLI executor
- `AZURE_CLI_EXECUTOR_LOG_LEVEL` - Logging verbosity

**Usage:**
- Azure Monitor Community deployments
- Complex resource queries
- Legacy operations not in SDK

**Implementation:**
- MCP Server: `azure_cli_executor_server.py`
- Client: `utils/azure_cli_executor_client.py`
- Authentication: Service principal via `az login --service-principal`
- Consumers: compute, storage, monitor MCP servers

**Commands Executed:**
```bash
az vm list --resource-group <rg> --output json
az storage account list --resource-group <rg>
az monitor scheduled-query create ...
az network watcher test-connectivity ...
```

---

## Model Context Protocol (MCP)

### Local MCP Servers (FastMCP)

**Location:** `app/agentic/eol/mcp_servers/`

**Servers:**
1. **inventory_mcp_server.py** - Log Analytics inventory queries
2. **os_eol_mcp_server.py** - EOL lookup tools
3. **compute_mcp_server.py** - VM operations
4. **storage_mcp_server.py** - Storage operations
5. **network_mcp_server.py** - Network diagnostics
6. **patch_mcp_server.py** - Patch management
7. **monitor_mcp_server.py** - Monitoring tools
8. **azure_cli_executor_server.py** - CLI executor
9. **azure_monitor_community_mcp_server.py** - GitHub scraper

**Pattern:**
```python
from mcp.server.fastmcp import FastMCP

mcp = FastMCP(name="server_name")

@mcp.tool()
async def tool_name(param: str) -> Dict[str, Any]:
    """Tool implementation."""
    return {"success": True, "data": result}
```

**Clients:** `utils/*_mcp_client.py` files

---

### External Azure MCP Server

**Provider:** `@azure/mcp` (Node.js package)

**Purpose:** Comprehensive Azure tools via external MCP server

**Configuration:**
- `AZURE_MCP_ENABLED` - Enable Azure MCP integration
- `AZURE_MCP_URL` - External MCP endpoint (if using remote)
- `USE_SERVICE_PRINCIPAL` - Auth mode flag

**Authentication Modes:**
1. **Service Principal:**
   - `AZURE_CLIENT_ID`
   - `AZURE_CLIENT_SECRET`
   - `AZURE_TENANT_ID`

2. **Managed Identity:**
   - `MANAGED_IDENTITY_CLIENT_ID` (optional)

**Implementation:**
- Client: `utils/azure_mcp_client.py`
- Spawns: `npx @azure/mcp` (external process via stdio)
- Composite: `utils/mcp_composite_client.py` (aggregates all MCP sources)

**Usage Pattern:**
```python
from utils.azure_mcp_client import azure_mcp_client

# Initialize
await azure_mcp_client.initialize(auth_mode="service_principal")

# Call tool
result = await azure_mcp_client.call_tool(
    "azure_tool_name",
    {"param": "value"}
)
```

---

## Authentication & Identity

### Primary Methods

1. **Service Principal (Client Secret)**
   - Environment Variables:
     - `AZURE_SP_CLIENT_ID` / `AZURE_CLIENT_ID`
     - `AZURE_SP_CLIENT_SECRET` / `AZURE_CLIENT_SECRET`
     - `AZURE_TENANT_ID` / `TENANT_ID`
   - Usage: Azure CLI login, explicit SDK auth
   - Implementation: `ClientSecretCredential`

2. **Managed Identity**
   - Preferred for production deployments
   - Uses `DefaultAzureCredential` (fallback chain)
   - Optional: `MANAGED_IDENTITY_CLIENT_ID` for user-assigned MI

3. **Azure CLI Session**
   - Local development fallback
   - `az login` authentication
   - Used by `azure_cli_executor_server.py`

### Token Acquisition

**Pattern:**
```python
from azure.identity import DefaultAzureCredential, ClientSecretCredential

# Prefer DefaultAzureCredential (supports MI)
credential = DefaultAzureCredential()

# Explicit service principal (when required)
if client_id and client_secret:
    credential = ClientSecretCredential(
        tenant_id=tenant_id,
        client_id=client_id,
        client_secret=client_secret
    )

# Get token
token = credential.get_token("https://management.azure.com/.default")
```

**Security Best Practices:**
- Store secrets in Azure Key Vault (not env vars in production)
- Use Managed Identity wherever possible
- Never commit secrets to repository
- Rotate service principal credentials regularly

---

## Notifications & Communications

### Microsoft Teams

**Purpose:** Incident notifications and alerts

**Configuration:**
- `TEAMS_WEBHOOK_URL` - Standard incoming webhook
- `TEAMS_CRITICAL_WEBHOOK_URL` - Critical alerts webhook

**Alternative (Teams Bot):**
- `TEAMS_BOT_APP_ID` - Bot application ID
- `TEAMS_BOT_APP_PASSWORD` - Bot password
- Supports bidirectional communication

**Implementation:**
- Client: `utils/teams_notification_client.py`
- Library: `pymsteams 0.2.2`
- Pattern: Connector cards (webhook-based)

**Usage:**
```python
from utils.teams_notification_client import teams_client

await teams_client.send_notification(
    title="Incident Alert",
    message="Critical service degradation detected",
    severity="critical"
)
```

**Notes:**
- Webhook approach is deprecated by Microsoft
- Teams Bot recommended for production (proactive messaging)
- API router: `api/teams_bot.py` (bidirectional integration)

---

## Third-Party Integrations

### GitHub (AzureMonitorCommunity)

**Purpose:** Download Azure Monitor workbooks, queries, and alerts

**Repository:** `https://github.com/microsoft/AzureMonitorCommunity`

**Implementation:**
- MCP Server: `azure_monitor_community_mcp_server.py`
- Scraping: `httpx 0.28.1` + `beautifulsoup4 4.12.3`
- Deployment: via Azure CLI

**Tools:**
- List workbooks/queries/alerts (HTML scraping)
- Download raw JSON/ARM templates
- Deploy to Azure subscription

---

## Observability & Monitoring

### Application Insights

**Configuration:**
- `APPLICATIONINSIGHTS_CONNECTION_STRING` - AppInsights connection string

**Usage:**
- Application telemetry
- Distributed tracing (OpenTelemetry)
- Performance metrics

**Implementation:**
- SDK: OpenTelemetry (`opentelemetry-semantic-conventions-ai==0.4.13`)
- Location: `utils/config.py`

---

### Logging Strategy

**Pattern:**
```python
from utils import get_logger, config

logger = get_logger(__name__, config.app.log_level)
```

**Log Destinations:**
- **Local Development:** `stdout` (colored)
- **Azure App Service:** `stderr` (plain)
- **Container Apps:** `stderr` (plain)

**Suppressed Loggers:**
```python
logging.getLogger("openai").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("azure.core.pipeline").setLevel(logging.WARNING)
```

---

### Metrics & Performance

**Tracked Metrics:**
- Response time (per endpoint)
- Cache hit/miss rates (L1 + L2)
- Tool execution latency
- Token usage (LLM calls)
- Connection pool stats

**Implementation:**
- Decorators: `@with_timeout_and_stats()`
- Manager: `utils/cache_stats_manager.py`
- API: `/api/cache/stats` (cache statistics endpoint)

---

## Caching Architecture

### Two-Tier Caching

**L1 Cache (In-Memory):**
- Python dictionaries with TTL
- Fast access (microseconds)
- Process-local scope
- Default TTL: 300 seconds

**L2 Cache (Cosmos DB):**
- Persistent storage
- Shared across instances
- Longer TTLs (configurable per resource type)
- Async writes (non-blocking)

**Cache Flow:**
```
Request → Check L1 → Check L2 → Execute → Store L2 → Store L1 → Response
            ↓ hit      ↓ hit                    ↓          ↓
         Return     Return + Backfill L1    (if Cosmos   (always)
                                             enabled)
```

**Configuration:**
- `INVENTORY_L1_TTL_DEFAULT` - L1 TTL (seconds)
- `INVENTORY_L2_TTL_*` - L2 TTLs per resource type
- Cosmos DB containers (as above)

---

## Environment Variables Reference

### Required Variables

| Variable | Purpose | Example |
|----------|---------|---------|
| `AZURE_OPENAI_ENDPOINT` | AOAI endpoint | `https://my-aoai.openai.azure.com/` |
| `AZURE_OPENAI_DEPLOYMENT` | AOAI model | `gpt-4o` |
| `LOG_ANALYTICS_WORKSPACE_ID` | Log Analytics | `12345678-1234-...` |
| `SUBSCRIPTION_ID` | Azure subscription | `abcdef01-2345-...` |

### Authentication (Choose One)

**Service Principal:**
- `AZURE_SP_CLIENT_ID` or `AZURE_CLIENT_ID`
- `AZURE_SP_CLIENT_SECRET` or `AZURE_CLIENT_SECRET`
- `AZURE_TENANT_ID` or `TENANT_ID`

**Managed Identity:**
- `MANAGED_IDENTITY_CLIENT_ID` (optional)

### Optional Features

| Variable | Purpose | Default |
|----------|---------|---------|
| `AZURE_COSMOS_DB_ENDPOINT` | Cosmos DB caching | (disabled) |
| `TEAMS_WEBHOOK_URL` | Teams notifications | (disabled) |
| `AZURE_MCP_ENABLED` | Azure MCP server | `false` |
| `AZURE_CLI_EXECUTOR_ENABLED` | CLI executor | `true` |
| `APPLICATIONINSIGHTS_CONNECTION_STRING` | AppInsights | (disabled) |

### Feature Flags

| Variable | Purpose | Default |
|----------|---------|---------|
| `DEBUG_MODE` | Debug logging | `false` |
| `INVENTORY_ENABLE` | Inventory features | `true` |
| `AZURE_AI_SRE_ENABLED` | Azure AI SRE agent | `false` |
| `USE_SERVICE_PRINCIPAL` | Azure MCP auth mode | `false` |

**Full Reference:** `app/agentic/eol/.env.example` (80+ variables documented)

---

## Deployment Integration Points

### Container Apps Deployment

**Script:** `app/agentic/eol/deploy/deploy-container.sh`

**Integration:**
- Azure Container Registry (ACR)
- Container Apps Environment
- VNet integration
- Diagnostic settings (Log Analytics)

**Configuration:**
- `deploy/appsettings.json` - App settings template
- `generate-appsettings.sh` - Config generation from env vars

---

### Terraform Provisioning

**Modules:**
- `modules/agentic/` - App Service + AOAI + Cosmos DB
- `modules/container_apps/` - Container Apps + ACR
- `modules/networking/` - VNet + subnets
- `modules/monitoring/` - Log Analytics + Application Insights

**Demo Scenarios:** 7 configurations in `demos/` directory

**Execution:**
```bash
./run-demo.sh
terraform apply -var-file="credentials.tfvars" -var-file="demos/<demo>/<demo>.tfvars"
```

---

## No Explicit Message Queue

**Note:** This codebase does NOT use:
- Azure Service Bus
- Azure Event Grid
- Kafka or other message brokers

**Notification Path:**
- Teams webhooks (synchronous HTTP POST)
- Azure Monitor action groups (managed by Azure)

**For Event-Driven Patterns:**
- Consider adding Service Bus or Event Grid
- Implement in future phases if required

---

## Security Recommendations

1. **Secrets Management:**
   - Migrate from env vars to Azure Key Vault
   - Use Key Vault references in App Service/Container Apps

2. **Authentication:**
   - Prefer Managed Identity over Service Principal
   - Rotate SP credentials every 90 days
   - Use least-privilege RBAC roles

3. **Network Security:**
   - VNet integration for private connectivity
   - Private endpoints for Cosmos DB, AOAI
   - NSGs and Azure Firewall (deployed via Terraform)

4. **Monitoring:**
   - Enable Application Insights for production
   - Configure alerts for critical failures
   - Review Cosmos DB RU consumption

5. **Compliance:**
   - Never commit secrets to repository
   - Use pipeline secrets for CI/CD
   - Audit access logs (Log Analytics)

---

## Testing Integration Points

**Test Script:** `app/agentic/eol/tests/run_tests.sh`

**Modes:**
- `--remote` - Remote integration tests (requires Azure)
- `--mcp-server <name>` - MCP server tool tests
- `--coverage` - Coverage reports

**Mock Mode:**
- `./run_mock.sh` - No Azure dependencies
- Bypasses authentication and external calls

---

## Operational Checklist

**Before Deployment:**
- [ ] Provision Cosmos DB containers (`eol_responses`, `resource_inventory`, `resource_inventory_metadata`)
- [ ] Create Log Analytics workspace
- [ ] Deploy Azure OpenAI resource
- [ ] Configure service principal or managed identity
- [ ] Set environment variables (see `.env.example`)
- [ ] Configure Teams webhook (optional)
- [ ] Enable Application Insights (recommended)

**Post-Deployment:**
- [ ] Verify `/health` endpoint
- [ ] Test inventory scan: `/api/inventory/scan`
- [ ] Check cache stats: `/api/cache/stats`
- [ ] Monitor logs (App Service or Container Apps)
- [ ] Validate Teams notifications (if configured)

---

**Last Updated:** 2026-02-27
**Source:** Codebase exploration + `.env.example` + `utils/config.py`
**Maintainer:** Development Team
