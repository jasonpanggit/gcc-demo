# Directory and File Structure

Comprehensive layout of the GCC Demo platform codebase.

---

## Repository Overview

```
gcc-demo/
├── .claude/              # Claude Code configuration
├── .git/                 # Git repository
├── .github/              # GitHub workflows
├── .planning/            # Planning documents (codebase maps)
├── .terraform/           # Terraform state
├── .venv/                # Python virtual environment
├── .vscode/              # VS Code settings
├── app/                  # Application code
├── demos/                # Demo configurations
├── litellm/              # LiteLLM proxy
├── modules/              # Terraform modules
├── scripts/              # Utility scripts
├── workbooks/            # Azure Monitor workbooks
├── CLAUDE.md             # Project guide
├── main.tf               # Root Terraform config
├── variables.tf          # Root variables
├── outputs.tf            # Root outputs
├── providers.tf          # Provider configuration
├── terraform.tfvars      # Terraform variables
├── credentials.tfvars    # Credentials (gitignored)
├── run-demo.sh           # Demo execution script
├── pytest.ini            # Pytest configuration
└── README.md             # Project documentation
```

**Total Files:**
- **33 Terraform files** (`.tf` in `modules/`)
- **169 Python files** (in `app/agentic/eol/`)
- **7 demo configurations** (in `demos/`)
- **11 Terraform modules** (in `modules/`)

---

## Terraform Infrastructure (`/`)

### Root Configuration

```
gcc-demo/
├── main.tf                 # Root module (31KB)
├── variables.tf            # Variable definitions (31KB)
├── outputs.tf              # Output definitions (7.7KB)
├── providers.tf            # Provider configuration
├── terraform.tfvars        # Variable values
├── credentials.tfvars      # Credentials (gitignored)
├── credentials.tfvars.example  # Credentials template
├── .terraform.lock.hcl     # Dependency lock file
├── terraform.tfstate       # State file (104KB)
└── run-demo.sh             # Demo execution wrapper (11KB)
```

**Key Files:**
- `main.tf` - Invokes 11 modules, configures resources
- `variables.tf` - 100+ variable definitions
- `outputs.tf` - Network, compute, storage outputs
- `run-demo.sh` - Interactive demo selection

---

### Terraform Modules (`modules/`)

```
modules/
├── networking/             # VNets, subnets, peering
├── compute/                # VMs (Windows, Linux, NVA)
├── gateways/               # VPN Gateway, ExpressRoute
├── firewall/               # Azure Firewall
├── storage/                # Storage accounts
├── monitoring/             # Log Analytics, Insights
├── arc/                    # Azure Arc integration
├── agentic/                # App Service + AOAI + Cosmos
├── container_apps/         # Container Apps + ACR
├── avd/                    # Azure Virtual Desktop
└── routing/                # Route tables, Route Server
```

**Module Pattern:**
```
modules/<name>/
├── main.tf                 # Module resources
├── variables.tf            # Module variables
├── outputs.tf              # Module outputs
└── README.md               # Module documentation (if present)
```

**Module Details:**

| Module | Purpose | Key Resources |
|--------|---------|---------------|
| **networking** | Hub-spoke VNets | VNets, subnets, peering |
| **compute** | Virtual machines | Windows/Linux VMs, NICs, disks |
| **gateways** | Network gateways | VPN Gateway, ExpressRoute Gateway |
| **firewall** | Azure Firewall | Firewall, policies, rules |
| **storage** | Storage accounts | Blob storage, file shares |
| **monitoring** | Observability | Log Analytics, Application Insights |
| **arc** | Azure Arc | Arc-enabled servers, policies |
| **agentic** | EOL App | App Service, AOAI, Cosmos DB |
| **container_apps** | Containers | Container Apps Environment, ACR |
| **avd** | Virtual Desktop | AVD host pools, workspaces |
| **routing** | Network routing | Route tables, Route Server, BGP |

---

### Demo Configurations (`demos/`)

```
demos/
├── demo1/
│   └── demo1.tfvars
├── demo2/
│   └── demo2.tfvars
├── demo3/
│   └── demo3.tfvars
├── demo4/
│   └── demo4.tfvars
├── demo5/
│   └── demo5.tfvars
├── demo6/
│   └── demo6.tfvars
└── demo7/
    └── demo7.tfvars
```

**Demo Scenarios:**
1. **demo1** - Basic hub-spoke topology
2. **demo2** - Hub-spoke with Azure Firewall
3. **demo3** - Hub-spoke with VPN Gateway
4. **demo4** - Hub-spoke with ExpressRoute
5. **demo5** - Full stack (Firewall + VPN + ER)
6. **demo6** - On-prem connectivity simulation
7. **demo7** - Custom configuration

**Usage:**
```bash
./run-demo.sh
# OR
terraform apply -var-file="credentials.tfvars" -var-file="demos/demo1/demo1.tfvars"
```

---

## FastAPI Application (`app/agentic/eol/`)

### Top-Level Structure

```
app/agentic/eol/
├── agents/                 # 41 agent modules
├── api/                    # 20 API router modules
├── mcp_servers/            # 9 MCP server implementations
├── utils/                  # 71 utility modules
├── tests/                  # Test suite
├── templates/              # Jinja2 HTML templates
├── static/                 # CSS, JavaScript assets
├── deploy/                 # Deployment scripts
├── docs/                   # Documentation
├── main.py                 # FastAPI entrypoint
├── requirements.txt        # Python dependencies
├── .env.example            # Environment variable template
├── pytest.ini              # Test configuration
├── CLAUDE.md               # Domain navigation
└── README.md               # Application documentation
```

---

### Agents Directory (`agents/`)

**41 Agent Modules:**

```
agents/
├── base_eol_agent.py          # Base class for EOL agents
├── base_sre_agent.py          # Base class for SRE agents
├── eol_orchestrator.py        # EOL workflow orchestrator
├── sre_orchestrator.py        # SRE workflow orchestrator
├── inventory_orchestrator.py  # Inventory orchestrator
├── mcp_orchestrator.py        # MCP tool routing
│
├── # EOL Vendor Agents (OS/Software)
├── microsoft_agent.py         # Microsoft products
├── endoflife_agent.py         # endoflife.date API
├── postgresql_agent.py        # PostgreSQL
├── redhat_agent.py            # Red Hat Enterprise Linux
├── ubuntu_agent.py            # Ubuntu
├── oracle_agent.py            # Oracle Database
├── php_agent.py               # PHP
├── nodejs_agent.py            # Node.js
├── python_agent.py            # Python
├── apache_agent.py            # Apache HTTP Server
├── vmware_agent.py            # VMware products
├── eolstatus_agent.py         # Generic EOL status
├── azure_ai_agent.py          # Azure AI integration
│
├── # Inventory Agents
├── inventory_agent.py         # Inventory coordination
├── os_inventory_agent.py      # OS discovery
├── software_inventory_agent.py  # Software discovery
│
├── # SRE Domain Agents
├── monitor_agent.py           # Monitoring and alerting
├── incident_response_agent.py # Incident handling
├── remediation_agent.py       # Automated remediation
├── performance_analysis_agent.py  # Performance optimization
├── cost_optimization_agent.py     # Cost analysis
├── configuration_management_agent.py  # Config drift
├── deployment_agent.py        # Deployment operations
├── slo_management_agent.py    # SLO tracking
├── health_monitoring_agent.py # Health checks
├── azure_ai_sre_agent.py      # Azure AI SRE
│
├── # Sub-Agents
├── sre_sub_agent.py           # SRE tool execution
├── patch_sub_agent.py         # Patch operations
│
└── # Web Automation
    └── playwright_agent.py    # Browser automation
```

**Agent Categories:**

| Category | Count | Purpose |
|----------|-------|---------|
| **Base Classes** | 2 | Agent inheritance |
| **Orchestrators** | 4 | High-level coordination |
| **EOL Vendors** | 12 | OS/software EOL lookups |
| **Inventory** | 3 | Resource discovery |
| **SRE Domain** | 10 | SRE operations |
| **Sub-Agents** | 2 | Low-level operations |
| **Automation** | 1 | Web scraping |
| **Total** | 41 | |

**Naming Convention:**
- Orchestrators: `*_orchestrator.py`
- Base classes: `base_*.py`
- Vendor agents: `<vendor>_agent.py`
- Domain agents: `<domain>_agent.py`
- Sub-agents: `*_sub_agent.py`

---

### API Routers Directory (`api/`)

**20 API Router Modules:**

```
api/
├── __init__.py
├── health.py              # Health checks
├── debug.py               # Debug utilities
├── cache.py               # Cache statistics
├── eol.py                 # EOL queries
├── inventory.py           # Inventory operations
├── alerts.py              # Alert management
├── communications.py      # Teams notifications
├── azure_mcp.py           # Azure MCP integration
├── agents.py              # Agent management
├── sre.py                 # SRE operations
├── sre_tools.py           # SRE tool endpoints
├── sre_chat.py            # SRE chat interface
├── compute.py             # VM operations
├── network.py             # Network diagnostics
├── storage.py             # Storage operations
├── patch.py               # Patch management
├── monitor.py             # Monitoring tools
├── teams_bot.py           # Teams Bot integration
├── copilot_studio.py      # Copilot Studio integration
└── azure_ai_sre.py        # Azure AI SRE endpoints
```

**Router Categories:**

| Category | Routers | Purpose |
|----------|---------|---------|
| **Core** | 3 | Health, debug, cache |
| **EOL** | 2 | EOL queries, inventory |
| **SRE** | 5 | SRE operations, chat, tools |
| **Azure Resources** | 4 | Compute, network, storage, patch |
| **Monitoring** | 2 | Alerts, monitoring |
| **Communications** | 2 | Teams, notifications |
| **Integrations** | 3 | Azure MCP, Copilot Studio, Azure AI |
| **Management** | 1 | Agent management |
| **Total** | 20 | |

**Naming Convention:**
- Domain routers: `<domain>.py` (e.g., `compute.py`, `network.py`)
- SRE routers: `sre*.py` (e.g., `sre.py`, `sre_chat.py`)
- Integration routers: `<service>*.py` (e.g., `teams_bot.py`)

---

### MCP Servers Directory (`mcp_servers/`)

**9 MCP Server Implementations:**

```
mcp_servers/
├── os_eol_mcp_server.py             # EOL lookups
├── inventory_mcp_server.py          # Log Analytics queries
├── compute_mcp_server.py            # VM operations
├── storage_mcp_server.py            # Storage operations
├── network_mcp_server.py            # Network diagnostics
├── patch_mcp_server.py              # Patch management
├── monitor_mcp_server.py            # Monitoring tools
├── azure_cli_executor_server.py     # CLI executor
└── azure_monitor_community_mcp_server.py  # GitHub scraper
```

**Server Capabilities:**

| Server | Tools | Azure SDKs Used |
|--------|-------|-----------------|
| **os_eol_mcp_server** | EOL lookups | None (API/scraping) |
| **inventory_mcp_server** | LAW queries | `azure-monitor-query` |
| **compute_mcp_server** | VM ops | `azure-mgmt-compute` |
| **storage_mcp_server** | Storage ops | `azure-mgmt-storage` |
| **network_mcp_server** | Network diagnostics | `azure-mgmt-network` |
| **patch_mcp_server** | Patch mgmt | `azure-mgmt-compute`, `azure-mgmt-resourcegraph` |
| **monitor_mcp_server** | Monitoring | `azure-mgmt-monitor` |
| **azure_cli_executor** | CLI executor | `subprocess` (az commands) |
| **azure_monitor_community** | GitHub scraper | `httpx`, `beautifulsoup4` |

---

### Utilities Directory (`utils/`)

**71 Utility Modules:**

```
utils/
├── __init__.py
│
├── # Configuration & Logging
├── config.py              # Central configuration
├── logger.py              # Logging setup
├── chat_config.py         # Chat configuration
│
├── # Response & Error Handling
├── response_models.py     # StandardResponse
├── response_composer.py   # Response composition
├── endpoint_decorators.py # Endpoint decorators
├── error_handlers.py      # Error handling
├── helpers.py             # Utility functions
├── verifier.py            # Verification utilities
│
├── # Caching
├── eol_cache.py           # EOL cache (L1)
├── inventory_cache.py     # Inventory cache (L1)
├── sre_cache.py           # SRE cache (L1)
├── cosmos_cache.py        # Cosmos DB cache (L2)
├── resource_inventory_cache.py      # Inventory cache manager
├── resource_inventory_cosmos.py     # Cosmos inventory storage
├── cache_stats_manager.py           # Cache statistics
│
├── # MCP Clients
├── mcp_composite_client.py          # Composite MCP client
├── azure_mcp_client.py              # Azure MCP external
├── compute_mcp_client.py            # Compute MCP client
├── network_mcp_client.py            # Network MCP client
├── storage_mcp_client.py            # Storage MCP client
├── patch_mcp_client.py              # Patch MCP client
├── monitor_mcp_client.py            # Monitor MCP client
├── inventory_mcp_client.py          # Inventory MCP client
├── os_eol_mcp_client.py             # EOL MCP client
├── sre_mcp_client.py                # SRE MCP client
├── azure_cli_executor_client.py     # CLI executor client
│
├── # Inventory
├── eol_inventory.py       # EOL inventory logic
├── resource_inventory_client.py     # Inventory client
├── vendor_url_inventory.py          # Vendor URL mapping
├── software_mappings.py   # Software name mappings
├── inventory_metrics.py   # Inventory metrics
├── inventory_feature_flags.py       # Feature flags
│
├── # SRE
├── sre_startup.py         # SRE initialization
├── sre_interaction_handler.py       # SRE chat handler
├── sre_inventory_integration.py     # SRE inventory integration
│
├── # Communications & Notifications
├── teams_notification_client.py     # Teams webhooks
├── alert_manager.py       # Alert management
│
├── # Tool Management
├── tool_parameter_mappings.py       # Tool parameter mapping
├── unified_domain_registry.py       # Domain registry
├── agent_registry.py      # Agent registry
├── sre_tool_registry.py   # SRE tool registry
│
├── # Tool Retrieval & Manifests
├── tool_embedder.py       # Tool embedding
├── tool_retriever.py      # Semantic tool search
├── tool_manifest_index.py # Tool manifest indexing
├── manifests/             # Tool manifest directory
│   ├── __init__.py
│   ├── compute_manifest.py
│   ├── network_manifest.py
│   ├── storage_manifest.py
│   ├── patch_manifest.py
│   ├── monitor_manifest.py
│   ├── inventory_manifest.py
│   └── sre_manifest.py
│
├── # Routing & Gateway
├── sre_gateway.py         # SRE classification
├── pipeline_routing.py    # Pipeline routing
│
├── # Authentication & Metrics
├── auth.py                # Authentication utilities
├── metrics.py             # Metrics tracking
│
├── # Web Automation
├── playwright_pool.py     # Browser pool management
│
├── # Agent Framework Integration
├── agent_framework_clients.py       # Agent Framework clients
│
├── # Middleware
├── middleware.py          # FastAPI middleware
│
└── # Data
    └── data/              # Static data files
```

**Utility Categories:**

| Category | Count | Purpose |
|----------|-------|---------|
| **Configuration** | 3 | Config management, logging |
| **Response Handling** | 6 | Response models, error handling |
| **Caching** | 8 | L1/L2 cache, statistics |
| **MCP Clients** | 11 | MCP server clients |
| **Inventory** | 7 | Inventory logic, metrics |
| **SRE** | 3 | SRE initialization, handlers |
| **Communications** | 2 | Teams, alerts |
| **Tool Management** | 4 | Tool routing, registry |
| **Tool Retrieval** | 3 | Semantic search, manifests |
| **Manifests** | 8 | Tool manifest definitions |
| **Routing** | 2 | Gateway, pipeline |
| **Auth & Metrics** | 2 | Authentication, metrics |
| **Web Automation** | 1 | Playwright pool |
| **Agent Framework** | 1 | Agent Framework clients |
| **Middleware** | 1 | FastAPI middleware |
| **Data** | 1 | Static data files |
| **Total** | 71 | |

---

### Tests Directory (`tests/`)

```
tests/
├── __init__.py
├── run_tests.sh           # Test execution script
│
├── # Unit Tests
├── test_router.py         # Router tests
├── test_sre_gateway.py    # SRE gateway tests
├── test_sre_tool_registry.py          # Tool registry tests
├── test_sre_incident_memory.py        # Incident memory tests
├── test_tool_embedder.py  # Tool embedder tests
├── test_tool_retriever.py # Tool retrieval tests
├── test_tool_manifest_index.py        # Manifest index tests
├── test_unified_domain_registry.py    # Domain registry tests
├── test_pipeline_routing.py           # Pipeline routing tests
├── test_resource_inventory_service.py # Inventory service tests
├── test_cli_executor_safety.py        # CLI executor safety tests
│
├── # Integration Tests
├── test_remote_sre.py     # Remote SRE tests
├── test_remote_tool_selection.py      # Remote tool selection tests
│
├── # Phase Tests
├── test_phase6_pipeline.py            # Phase 6 pipeline tests
├── test_phase7_default.py             # Phase 7 default tests
│
└── # MCP Server Tests (run via --mcp-server flag)
    └── (MCP server tool tests)
```

**Test Categories:**

| Category | Tests | Purpose |
|----------|-------|---------|
| **Unit Tests** | 11 | Component testing |
| **Integration Tests** | 2 | Remote API testing |
| **Phase Tests** | 2 | Feature phase validation |
| **MCP Tests** | N/A | MCP server tool testing |
| **Total** | 15+ | |

**Test Execution:**
```bash
cd tests
./run_tests.sh                    # All tests
./run_tests.sh --remote           # Remote tests
./run_tests.sh --mcp-server sre   # MCP server tests
./run_tests.sh --coverage         # Coverage report
```

---

### Templates Directory (`templates/`)

```
templates/
├── base.html              # Base template
├── index.html             # Home page
├── eol.html               # EOL query interface
├── azure-ai-sre.html      # Azure AI SRE interface
├── sre-chat.html          # SRE chat interface
├── inventory.html         # Inventory interface
├── sre.html               # SRE operations interface
├── cache-stats.html       # Cache statistics
├── agents.html            # Agent management
├── compute.html           # Compute operations
├── network.html           # Network diagnostics
├── storage.html           # Storage operations
├── patch.html             # Patch management
├── monitor.html           # Monitoring
├── alerts.html            # Alerts
├── communications.html    # Communications
├── copilot-studio.html    # Copilot Studio
├── teams-bot.html         # Teams Bot
└── debug.html             # Debug utilities
```

**Template Engine:** Jinja2

**Pattern:**
- Base template: `base.html` (common layout, navigation)
- Page templates extend `base.html`
- Static assets: `static/css/`, `static/js/`

---

### Static Assets (`static/`)

```
static/
├── css/
│   ├── common-components.css    # Shared components
│   ├── eol.css                  # EOL styles
│   ├── sre.css                  # SRE styles
│   └── ...
└── js/
    └── (JavaScript files if any)
```

---

### Deployment Scripts (`deploy/`)

```
deploy/
├── deploy-container.sh          # Container Apps deployment
├── show-logs.sh                 # Log monitoring
├── generate-appsettings.sh      # Config generation
├── appsettings.json             # App settings template
├── Dockerfile                   # Container image
└── teams-app/                   # Teams App manifest
    ├── manifest.json
    └── ...
```

**Usage:**
```bash
cd deploy
./deploy-container.sh [version] [build-only] [force-rebuild]
./show-logs.sh
```

---

### Documentation (`docs/`)

```
docs/
├── (Various .md files)
└── ...
```

---

## LiteLLM Proxy (`litellm/`)

```
litellm/
├── config.yaml            # LiteLLM configuration
├── start-litellm.sh       # Startup script
└── ...
```

**Purpose:** Proxy layer for LLM requests (GitHub Copilot, Azure OpenAI)

---

## Scripts (`scripts/`)

```
scripts/
├── (Utility scripts)
└── ...
```

---

## Configuration Files (Root)

```
gcc-demo/
├── .claude/
│   ├── docs/              # Extended documentation
│   │   ├── DEVELOPER-ONBOARDING.md
│   │   ├── CHEATSHEET.md
│   │   ├── DEMO-EXECUTION-GUIDE.md
│   │   ├── SRE-ARCHITECTURE.md
│   │   ├── SRE-ORCHESTRATOR-README.md
│   │   └── UI-PATTERNS.md
│   └── ...
│
├── .gitignore             # Git ignore patterns
├── .hintrc                # Hint configuration
├── CLAUDE.md              # Project guide
├── README.md              # Project documentation
├── pytest.ini             # Pytest configuration
└── requirements.txt       # Python dependencies (if any)
```

---

## Naming Conventions

### Terraform

**Resources:**
- Pattern: `<type>-<component>-<project>-<environment>`
- Example: `nic-nva-gcc-demo-prod`

**Variables:**
- Snake case: `project_name`, `environment`
- Boolean flags: `deploy_<component>`
- Hub variables: `hub_vnet_address_space`

### Python

**Files:**
- Snake case: `eol_orchestrator.py`, `response_models.py`
- Test files: `test_*.py`
- MCP servers: `*_mcp_server.py`
- MCP clients: `*_mcp_client.py`
- Base classes: `base_*.py`

**Classes:**
- PascalCase: `EOLOrchestrator`, `StandardResponse`
- Agents: `*Agent` suffix
- Orchestrators: `*Orchestrator` suffix

**Functions:**
- Snake case: `get_eol_data()`, `ensure_standard_format()`
- Private functions: `_private_function()`

---

## File Counts Summary

| Component | Files/Modules | Purpose |
|-----------|---------------|---------|
| **Terraform Modules** | 11 | Infrastructure modules |
| **Terraform Files** | 33 | `.tf` files |
| **Demo Configs** | 7 | Demo scenarios |
| **Python Files** | 169 | Application code |
| **Agents** | 41 | Agent modules |
| **API Routers** | 20 | FastAPI routers |
| **MCP Servers** | 9 | MCP server implementations |
| **Utilities** | 71 | Utility modules |
| **Tests** | 15+ | Test files |
| **Templates** | 19 | Jinja2 HTML templates |

---

## Growth Patterns

**When to Add Files:**

1. **New Terraform Module:**
   - `modules/<name>/main.tf`
   - `modules/<name>/variables.tf`
   - `modules/<name>/outputs.tf`

2. **New Agent:**
   - `agents/<vendor>_agent.py` (extends `BaseEOLAgent` or `BaseSREAgent`)

3. **New API Router:**
   - `api/<domain>.py` (imports `APIRouter`, uses decorators)

4. **New MCP Server:**
   - `mcp_servers/<domain>_mcp_server.py` (FastMCP)
   - `utils/<domain>_mcp_client.py` (client wrapper)

5. **New Utility:**
   - `utils/<utility>.py` (specific purpose)

6. **New Template:**
   - `templates/<page>.html` (extends `base.html`)

---

**Last Updated:** 2026-02-27
**Source:** Codebase exploration + directory analysis
**Maintainer:** Development Team
