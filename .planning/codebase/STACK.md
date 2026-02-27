# Technical Stack

Comprehensive technical stack for the GCC Demo platform.

---

## Core Languages & Runtimes

### Python 3.13
- **Primary application language** for EOL agentic platform
- Async/await patterns throughout with uvloop for performance
- Type hints and dataclasses for configuration management

### HCL (Terraform)
- **Infrastructure as Code** language
- 11 modular Terraform modules for Azure resource provisioning
- Variable-driven configuration with demo-specific tfvars

### Bash
- Deployment automation scripts
- Infrastructure provisioning wrappers (run-demo.sh)
- Container deployment and log monitoring utilities

---

## Backend Framework & Web Server

### FastAPI 0.121.2
- **Modern async web framework** for Python
- Auto-generated OpenAPI documentation
- Pydantic 2.12.4 for request/response validation
- StandardResponse models for consistent API contracts

### Uvicorn 0.38.0
- **ASGI server** with standard extras
- Uvloop, httptools, websockets for performance
- Hot reload support for development
- SSE (Server-Sent Events) streaming via sse-starlette 3.0.3

---

## AI & LLM Integration

### Azure OpenAI
- **Primary LLM provider** via Azure Cognitive Services
- GPT-4o, GPT-4o-mini deployments
- Managed through Azure OpenAI SDK (openai==2.21.0)
- Token counting with tiktoken 0.12.0

### Microsoft Agent Framework 1.0.0rc1
- **Agentic orchestration framework** (optional, preview release)
- Used for inventory assistant experience
- Packages: agent-framework, agent-framework-ag-ui, agent-framework-chatkit
- Agent-first workflow orchestration with USE_WORKFLOW_ORCHESTRATOR flag

### Azure AI Agent Service
- **Managed agent lifecycle** integration
- Persistent conversation state in Azure AI Project
- Packages: azure-ai-projects==2.0.0b3, azure-ai-agents==1.2.0b5
- Replaces legacy Bing Search with azure-search-documents 11.5.3

### Model Context Protocol (MCP)
- **Tool integration protocol** (mcp==1.25.0)
- FastMCP for local server implementations
- 9 local MCP servers for specialized operations
- External Azure MCP integration (@azure/mcp via Node.js)

---

## Azure SDK & Cloud Services

### Core Azure SDKs
- **azure-identity 1.17.1** - Authentication (DefaultAzureCredential, ClientSecretCredential)
- **azure-core 1.36.0** - Common functionality across SDKs

### Azure Management SDKs
- **azure-mgmt-resource 23.1.1** - Resource management
- **azure-mgmt-compute 33.0.0** - VM operations
- **azure-mgmt-network 27.0.0** - Network operations
- **azure-mgmt-monitor 6.0.2** - Monitoring and alerts
- **azure-mgmt-storage 21.2.1** - Storage account management
- **azure-mgmt-resourcehealth 1.0.0b1** - Resource health checks
- **azure-mgmt-resourcegraph 8.0.1** - Dependency mapping queries
- **azure-mgmt-web 7.0.0** - App Service operations
- **azure-mgmt-redis 14.0.0** - Redis cache operations
- **azure-mgmt-containerservice 20.0.0** - AKS operations

### Azure Data & Monitoring
- **azure-monitor-query 1.4.0** - Log Analytics and metrics queries
- **azure-cosmos 4.7.0** - Cosmos DB client for caching/persistence
- **Azure Log Analytics** - KQL queries for resource inventory

### Observability
- **OpenTelemetry** - Distributed tracing support
- opentelemetry-semantic-conventions-ai==0.4.13 (pinned for Agent Framework RC1 compatibility)
- **Application Insights** - Telemetry and diagnostics

---

## Microsoft Copilot Studio & Agent Integration

### Copilot Studio Runtime
- **microsoft-agents-copilotstudio-client** >=0.5.0, <0.7.0
- **microsoft-agents-hosting-core** >=0.5.0, <0.7.0
- **microsoft-agents-activity** >=0.5.0, <0.7.0

### Power Fx & CLR
- **powerfx** >=0.0.31, <0.1.0 - Formula language for low-code expressions
- **clr-loader** >=0.2.7, <0.3.0 - .NET runtime interop

---

## Data Processing & Caching

### Databases
- **Azure Cosmos DB** (NoSQL)
  - EOL response caching (L2 persistence)
  - Resource inventory storage
  - SRE incident memory and audit trails
  - Containers: eol_responses, resource_inventory, resource_inventory_metadata

### Caching Architecture
- **L1 Cache**: In-memory (Python dictionaries, TTL-based expiration)
- **L2 Cache**: Cosmos DB persistence with longer TTLs
- **Cache managers**: cache_stats_manager, sre_cache, resource_inventory_cache
- Configurable TTLs per resource type and operation

### Data Formats
- **JSON** - API payloads, configuration files, manifests
- **YAML** - PyYAML 6.0.2 for configuration parsing
- **HTML** - html2text 2025.4.15 for content extraction
- **PDF** - pdfplumber 0.11.4 for document parsing
- **XML/HTML** - beautifulsoup4 4.12.3, lxml 5.3.0 for web scraping

---

## HTTP Clients & Web Automation

### HTTP Libraries
- **aiohttp 3.10.5** - Async HTTP client for agent operations
- **httpx 0.28.1** - Modern HTTP client with HTTP/2 support
- **playwright 1.50.0** - Browser automation for web scraping

### Utilities
- **python-multipart 0.0.9** - Multipart form parsing
- **email-validator 2.1.0** - Email format validation
- **aiofiles 24.1.0** - Async file I/O

---

## Testing & Quality

### Test Framework
- **pytest 8.3.2** - Primary test runner
- **pytest-asyncio 0.23.8** - Async test support
- Test script: tests/run_tests.sh with coverage, remote, and MCP server modes

### Test Coverage Areas
- Unit tests for utilities and agents
- Remote integration tests (--remote flag)
- MCP server tool tests (--mcp-server flag)
- UI tests (Playwright-based)

---

## Infrastructure & IaC

### Terraform
- **Provider**: azurerm >= 3.100.0
- **Modules**: 11 specialized modules
  - networking, compute, gateways, firewall, storage, monitoring, arc
  - agentic (App Service + AOAI + Cosmos DB)
  - container_apps (Container Apps Environment + ACR)
  - avd (Azure Virtual Desktop)
  - routing

### Demo Scenarios
- 7 demo configurations in demos/ directory
- Variable-driven with credentials.tfvars + demo-specific tfvars
- Hub-spoke networking patterns with optional components (count-based)

---

## Container & Deployment

### Docker
- Dockerfile for EOL application
- Azure Container Registry (ACR) for image storage
- Multi-container support (main app + MCP sidecar)

### Azure Container Apps
- Container Apps Environment with VNet integration
- Internal load balancer support
- Zone redundancy configuration
- Diagnostic settings for log collection

### Azure App Service
- Linux App Service Plan (asp-*)
- Alternative deployment target to Container Apps
- VNet integration for private networking

### Deployment Automation
- deploy-container.sh - Container Apps deployment
- show-logs.sh - Log monitoring
- generate-appsettings.sh - Configuration generation

---

## Utilities & Scheduling

### Background Processing
- **apscheduler >=3.10.4** - Periodic task scheduling for SRE operations
- Inventory discovery scheduler (full scan + incremental)
- Resource health monitoring

### Progress & Monitoring
- **tqdm 4.67.1** - Progress bars for long-running operations
- Custom metrics tracking (calls, latency, tokens, tool usage)

---

## Notifications & Integrations

### Microsoft Teams
- **pymsteams 0.2.2** - Teams webhook notifications
- SRE incident notifications
- Alert management integration

### A2A SDK
- **a2a-sdk 0.3.12** - Azure-to-Azure service integration

---

## Development Tools

### Environment Management
- **python-dotenv 1.2.1** - .env file loading
- .env.example template with all configuration variables
- appsettings.json for deployment configuration

### Template Engine
- **Jinja2 3.1.4** - HTML template rendering for UI
- templates/ directory with base.html, index.html, azure-ai-sre.html, eol.html

---

## Configuration Management

### Config Architecture
- Centralized ConfigManager in utils/config.py
- Dataclass-based configuration sections:
  - AzureConfig (AOAI, Log Analytics, Cosmos DB, subscription/tenant)
  - AppConfig (title, version, timeout, log_level, debug_mode)
  - InventoryAssistantConfig (provider, timeout)
  - AzureAISREConfig (agent_id, project_endpoint, enabled)
  - AgentPerformanceConfig (timeouts, parallelism, caching, connection pooling)
  - PatchManagementConfig (timeouts, batch processing, compliance thresholds)
  - InventoryConfig (TTLs, scanning schedules, security filters)

### Environment Variables
- 80+ configuration parameters documented in .env.example
- Required: AZURE_OPENAI_ENDPOINT, LOG_ANALYTICS_WORKSPACE_ID
- Optional: Cosmos DB, Application Insights, Azure AI Project
- Feature flags: DEBUG_MODE, AZURE_AI_SRE_ENABLED, INVENTORY_ENABLE

---

## Logging & Observability

### Logging Strategy
- **Python logging** module with custom formatters
- get_logger(__name__, config.app.log_level) pattern
- Module-level loggers throughout codebase
- Suppressed verbose Azure SDK HTTP logging

### Metrics & Monitoring
- Response time tracking with endpoint decorators
- Cache hit/miss statistics (cache_stats_manager)
- Tool execution metrics (calls, latency, tokens)
- Agent performance metrics (connection pool, timeout tracking)

---

## Module Counts & Code Organization

### Application Structure (app/agentic/eol)
- **41 agent modules** (orchestrators, base classes, domain specialists, vendor agents)
- **20 API router modules** (health, debug, cache, inventory, alerts, communications, SRE, etc.)
- **71 utility modules** (config, logging, caching, MCP clients, tool routing, manifests)
- **9 local MCP servers** (SRE, monitor, inventory, OS EOL, CLI executor, patch, network, +2)

### Frontend
- **Templates**: Jinja2 HTML templates in templates/
- **Static Assets**: CSS, JavaScript in static/ directory
- **UI Patterns**: Common component library in static/css/common-components.css

---

## Build & Runtime Commands

### Local Development
```bash
cd app/agentic/eol
source ../../../.venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

### Mock Mode (No Azure Dependencies)
```bash
./run_mock.sh
```

### Testing
```bash
cd tests
./run_tests.sh                    # All tests
./run_tests.sh --remote           # Remote integration tests
./run_tests.sh --mcp-server sre   # MCP server tests
./run_tests.sh --coverage         # Coverage report
```

### Infrastructure Deployment
```bash
./run-demo.sh
terraform plan -var-file="credentials.tfvars" -var-file="demos/<demo>/<demo>.tfvars"
terraform apply -var-file="credentials.tfvars" -var-file="demos/<demo>/<demo>.tfvars"
```

### Container Deployment
```bash
cd app/agentic/eol/deploy
./deploy-container.sh [version] [build-only] [force-rebuild]
./show-logs.sh
```

---

## Version & Compatibility

- **Python**: 3.13 (primary), 3.11/3.9 support in litellm venv
- **Terraform**: >= 1.0
- **Azure Provider**: >= 3.100.0
- **FastAPI**: 0.121.2 (pinned for Agent Framework compatibility)
- **Pydantic**: 2.12.4
- **Agent Framework**: 1.0.0rc1 (preview release)

---

**Last Updated**: 2026-02-27
**Source**: requirements.txt, config.py, main.tf, CLAUDE.md files
