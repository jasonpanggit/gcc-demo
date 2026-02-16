# 🔄 EOL Agentic Platform

An advanced End-of-Life (EOL) analysis and Azure operations platform built on Azure Container Apps, FastAPI, and Azure OpenAI. The system uses a **hybrid orchestrator + sub-agent architecture** with 5 MCP (Model Context Protocol) servers to provide real-time Azure resource management, inventory analysis, and Azure Monitor Community resource discovery and deployment.

## 🚀 Overview

The EOL Agentic Platform combines a central MCP orchestrator with a specialized Monitor sub-agent to deliver:
- **Azure resource management** via Azure MCP Server (~85 tools)
- **OS/software inventory analysis** from Log Analytics with EOL cross-referencing
- **Azure Monitor resource discovery and deployment** (workbooks, alerts, KQL queries)
- **Azure CLI execution** for services without dedicated MCP tools

The orchestrator uses a **ReAct (Reasoning + Acting) loop** with Azure OpenAI (GPT-4o-mini) and delegates monitor-specific tasks to a focused sub-agent, reducing tool confusion and improving deployment reliability.

**Architecture Highlights:**
- 🏗️ **Hybrid Model**: Orchestrator handles general Azure ops; MonitorAgent handles monitor resources autonomously
- 🔧 **5 MCP Servers**: azure, azure_cli, os_eol, inventory, monitor (100+ tools total)
- 🤖 **ReAct Loop**: Up to 50 reasoning iterations with hallucination guard
- 📡 **SSE Streaming**: Real-time communication events (reasoning → action → observation → synthesis)
- 🚀 **Deploy Tools**: Dedicated deploy_workbook, deploy_query, deploy_alert (no manual CLI construction)

### Key Features

### Parameter discovery & interactive selection (SRE)

The SRE orchestrator includes a built-in interactive parameter discovery workflow to handle ambiguous or missing inputs. This improves usability for common operations like health checks, restarts, scaling, and cost analysis.

- Component: `utils/sre_interaction_handler.py` (SREInteractionHandler)
  - Detects missing parameters with check_required_params(tool_name, params)
  - Decides whether discovery is needed via needs_resource_discovery(tool_name, params, query)
  - Performs targeted discovery (resource groups, container apps, VMs, Log Analytics workspaces) using an azure_cli_executor when available
  - Formats selection prompts via SREResponseFormatter.format_selection_prompt and parses user replies with parse_user_selection

- Component: `utils/sre_response_formatter.py` (SREResponseFormatter)
  - Converts raw tool outputs and discovery lists into friendly HTML (tables, summaries, next steps)
  - Selection prompt payload includes options with index, name, and id for quick selection

Usage notes:
- The orchestrator will automatically attempt discovery and will either auto-select a single match or prompt the user when multiple matches are found.
- If discovery is not possible (azure_cli_executor missing) the orchestrator returns a needs_user_input payload with a helpful HTML message suggesting how to provide the missing values.

Examples:
- "Check health of my app" → If ambiguous, the orchestrator lists container apps for selection; user replies "2" → agent proceeds with the selected resource.
- "Restart api-prod-01" → Orchestrator detects the name and proceeds without a selection prompt when confidence is high.

Debugging tips:
- If discovery returns empty, verify the Azure CLI executor configuration and that `az` is authenticated (`az account show`).
- See `utils/sre_interaction_handler.py` and `utils/sre_response_formatter.py` for formatter details and available selection inputs.


### Key Features

- **🔍 Intelligent Inventory Discovery**: Real-time software and OS inventory from Azure Log Analytics (Azure Arc enabled)
- **🤖 Hybrid Orchestrator Architecture**: Central orchestrator with specialized MonitorAgent sub-agent
- **💬 AI-Powered Chat Interface**: Conversational AI using Azure OpenAI (GPT-4o-mini) with ReAct reasoning loop
- **📊 Azure Monitor Resource Management**: Discover, view, and deploy workbooks, alerts, and KQL queries from the Azure Monitor Community repository
- **🔔 Intelligent Alert Management**: Configurable EOL alerts with SMTP email notifications
- **🎯 Smart EOL Search**: Confidence scoring, early termination, and comprehensive EOL history tracking
- **⚡ Performance Optimized**: Multi-level caching (in-memory, Cosmos DB), parallel tool execution, and hallucination guard
- **📈 Advanced Analytics**: Real-time statistics dashboard with agent performance metrics and cache analytics
- **🌐 MCP Protocol**: 5 MCP servers aggregated via CompositeMCPClient with source-aware routing

## 🏗️ Architecture

### Hybrid Orchestrator + Sub-Agent Architecture

The application uses a hybrid architecture where a central orchestrator delegates domain-specific tasks to specialized sub-agents:

```
User → FastAPI (SSE) → MCPOrchestratorAgent
                          ├── Direct: Azure MCP tools (~85 tools)
                          ├── Direct: Azure CLI Executor (1 tool)
                          ├── Direct: OS EOL Server (2 tools)
                          ├── Direct: Inventory Server (7 tools)
                          └── Delegate: monitor_agent meta-tool → MonitorAgent
                                ├── get_service_monitor_resources
                                ├── search_categories / list_resources
                                ├── get_resource_content
                                ├── deploy_workbook / deploy_query / deploy_alert
```

#### Core Orchestrators
- **`MCPOrchestratorAgent`**: Main orchestrator with ReAct loop (AsyncAzureOpenAI SDK). Manages 100+ tools via CompositeMCPClient. Delegates monitor tasks to MonitorAgent. Includes hallucination guard, conversation summarization, and SSE streaming.
- **`MonitorAgent`**: Focused sub-agent for Azure Monitor Community resources. Own system prompt, ~12 tools, 15-iteration ReAct loop, stateless per invocation.
- **`EOLOrchestratorAgent`**: Coordinates EOL data gathering from specialized vendor agents with async fan-out, confidence scoring, and early termination.

#### EOL Agents
- **`MicrosoftEOLAgent`**: Windows, SQL Server, Office, .NET lifecycle data
- **`RedHatEOLAgent`**: RHEL, CentOS, Fedora lifecycle information
- **`UbuntuEOLAgent`**: Ubuntu and Canonical product lifecycles
- **`EndOfLifeAgent`**: General EOL data from endoflife.date API
- **`OracleEOLAgent`**: Oracle database and middleware lifecycles
- **`VMwareEOLAgent`**: VMware product lifecycle data
- **`ApacheEOLAgent`**: Apache web server and components
- **`NodeJSEOLAgent`**: Node.js runtime lifecycle
- **`PostgreSQLEOLAgent`**: PostgreSQL database lifecycle
- **`PHPEOLAgent`**: PHP runtime lifecycle
- **`PythonEOLAgent`**: Python interpreter lifecycle

#### Supporting Agents
- **`OpenAIAgent`**: Azure OpenAI (GPT-4) integration for AI-powered analysis
- **`AzureAIAgent`**: Azure AI Agent Service for intelligent web data extraction
- **`PlaywrightAgent`**: Automated browser-based web scraping

## 🛠️ Technology Stack

### Backend
- **FastAPI 0.112.x**: High-performance async web framework
- **Python 3.11+**: Core runtime environment
- **Azure OpenAI SDK**: GPT-4o-mini via AsyncAzureOpenAI with ReAct loop
- **Azure SDK**: Integration with Azure services (Identity, Monitor Query, Cosmos DB)
- **Azure Management SDK**: Native Azure resource management
- **MCP SDK**: Model Context Protocol for tool server communication
- **Pydantic 2.x**: Data validation and serialization

### AI & Web Automation
- **Azure OpenAI**: GPT-4o-mini powered conversational AI (AsyncAzureOpenAI SDK)
- **Azure MCP Server**: `@azure/mcp@latest` for Azure resource management (~85 tools)
- **Playwright 1.50.0**: Browser automation for web scraping
- **Azure Log Analytics**: Real-time inventory data source

### Data & Caching
- **Azure Cosmos DB 4.7.0**: Persistent storage for communications, EOL results, and cache
- **Multi-level Caching**: In-memory + Cosmos DB with intelligent cache management
- **Cache Statistics Manager**: Real-time performance monitoring and metrics
- **Alert Manager**: EOL alert configuration and SMTP notifications

#### Cache Precedence & Observability
- Cache order: Cosmos `eol_table` ➜ in-process session cache ➜ agents (Playwright fallback last)
- TTL-aware: `eol_table` container enforces TTL at creation; entries expire server-side
- Metrics endpoints: `/api/eol-cache-stats` (hits/misses, memory cache) and `/api/eol-latency` (p50/p95/avg agent timing with recent samples)

### Frontend
- **Jinja2 Templates**: Server-side rendering with dynamic data
- **HTML5/CSS3/JavaScript**: Modern interactive web interface
- **Bootstrap 5**: Responsive UI framework with custom styling
- **Font Awesome**: Icon library for visual indicators
- **Real-time Updates**: Auto-refresh dashboards and live statistics

## 📁 Project Structure

```
app/agentic/eol/
├── api/                              # Modular API routers (NEW: Phase 2 refactoring)
│   ├── __init__.py                   # API package initialization
│   ├── health.py                     # Health check endpoints (3)
│   ├── cache.py                      # Cache management (17)
│   ├── inventory.py                  # Inventory operations (7)
│   ├── eol.py                        # EOL analysis (5)
│   ├── cosmos.py                     # Cosmos DB operations (6)
│   ├── agents.py                     # Agent management (5)
│   ├── alerts.py                     # Alert configuration (6)
│   ├── communications.py             # Communication history (6)
│   ├── chat.py                       # AI chat interface (1)
│   ├── ui.py                         # HTML page templates (8)
│   ├── azure_mcp.py                  # Azure MCP co-pilot SSE chat (2)
│   └── debug.py                      # Debug utilities (3)
├── agents/                           # Orchestrator and agent system
│   ├── mcp_orchestrator.py           # Main MCP orchestrator (ReAct loop, AsyncAzureOpenAI)
│   ├── monitor_agent.py              # Monitor sub-agent (hybrid delegation target)
│   ├── base_eol_agent.py             # Base class for all EOL agents
│   ├── inventory_orchestrator.py     # Conversational AI orchestrator
│   ├── eol_orchestrator.py           # EOL analysis orchestrator
│   ├── inventory_agent.py            # Inventory coordination
│   ├── os_inventory_agent.py         # OS inventory from Log Analytics
│   ├── software_inventory_agent.py   # Software inventory from Log Analytics
│   ├── microsoft_agent.py            # Microsoft EOL agent
│   ├── redhat_agent.py               # Red Hat EOL agent
│   ├── ubuntu_agent.py               # Ubuntu EOL agent
│   ├── endoflife_agent.py            # General EOL API agent
│   ├── oracle_agent.py               # Oracle EOL agent
│   ├── vmware_agent.py               # VMware EOL agent
│   ├── apache_agent.py               # Apache EOL agent
│   ├── nodejs_agent.py               # Node.js EOL agent
│   ├── postgresql_agent.py           # PostgreSQL EOL agent
│   ├── php_agent.py                  # PHP EOL agent
│   ├── python_agent.py               # Python EOL agent
│   ├── openai_agent.py               # Azure OpenAI (GPT-4) integration
│   ├── azure_ai_agent.py             # Azure AI Agent Service integration
│   ├── playwright_agent.py           # Playwright web scraping
├── templates/                        # Web interface templates
│   ├── base.html                     # Base template with common layout
│   ├── index.html                    # Dashboard homepage with statistics
│   ├── inventory_asst.html           # Inventory assistant conversational interface
│   ├── eol.html                      # EOL analysis interface (deprecated)
│   ├── eol-searches.html             # EOL search history viewer
│   ├── inventory.html                # Inventory management
│   ├── alerts.html                   # Alert management interface
│   ├── cache.html                    # Cache statistics dashboard
│   ├── agent-cache-details.html      # Detailed agent cache metrics
│   ├── agents.html                   # Agent status monitoring
│   └── azure-mcp.html               # Azure MCP co-pilot chat interface (SSE)
├── static/                           # Static web assets (CSS, JS, images)
├── utils/                            # Utility modules
│   ├── __init__.py                   # Utilities export
│   ├── config.py                     # Configuration management
│   ├── logger.py                     # Structured logging
│   ├── helpers.py                    # Helper functions
│   ├── decorators.py                 # Endpoint decorators (timeout, stats)
│   ├── cache_stats_manager.py        # Real-time performance monitoring
│   ├── mcp_composite_client.py       # Aggregates MCP clients with source routing
│   ├── response_formatter.py         # HTML formatting + deduplication
│   ├── azure_mcp_client.py           # Azure MCP Server client wrapper
│   ├── azure_cli_executor_client.py  # Azure CLI MCP client
│   ├── os_eol_mcp_client.py          # OS EOL MCP client
│   ├── inventory_mcp_client.py       # Inventory MCP client
│   ├── monitor_mcp_client.py         # Monitor MCP client
│   ├── cosmos_cache.py               # Cosmos DB base client
│   ├── eol_cache.py                  # EOL results caching
│   ├── inventory_cache.py            # Unified inventory cache
│   ├── os_inventory_cache.py         # OS inventory cache
│   ├── software_inventory_cache.py   # Software inventory cache
│   ├── alert_manager.py              # EOL alert configuration & SMTP
│   └── data/                         # Static data files (vendor mappings, etc.)
├── mcp_servers/                      # Local MCP server implementations
│   ├── monitor_mcp_server.py         # Azure Monitor Community (12 tools)
│   ├── os_eol_mcp_server.py          # OS EOL lookup (2 tools)
│   ├── inventory_mcp_server.py       # Inventory queries (7 tools)
│   └── azure_cli_executor_server.py  # Azure CLI executor (1 tool)
├── deploy/                           # Deployment configuration
│   ├── Dockerfile                    # Container image definition
│   ├── deploy-container.sh           # Azure Container Registry deployment
│   └── app-service-config/           # App Service settings
├── tests/                            # Unit and integration tests
├── tools/                            # Development and maintenance tools
├── main.py                           # FastAPI application entry point (2,876 lines)
├── requirements.txt                  # Python dependencies
├── web.config                        # IIS/App Service configuration
└── README.md                         # This file
```

**Recent Improvements (Phase 2 Refactoring)**:
- ✅ Created modular `api/` directory with 10 specialized routers
- ✅ Extracted 78 endpoints from monolithic main.py (19% size reduction)
- ✅ Improved code organization and maintainability
- ✅ Enhanced testability with isolated modules
- ✅ Maintained 100% backward compatibility
- ✅ Unified AsyncAzureOpenAI SDK for MCP orchestrator (replaces Agent Framework dependency)
- ✅ MCP orchestrator uses ReAct loop with configurable temperature/max tokens and lightweight request logging
- ✅ FastAPI app now uses lifespan context instead of deprecated on_event hooks
- ✅ Template rendering updated to new Jinja2 request-first signature

## ⚡ Quick Start

```bash
# 1. Clone and navigate
git clone <repository-url>
cd gcc-demo/app/agentic/eol

# 2. Install dependencies
pip install -r requirements.txt
playwright install chromium

# 3. Configure Azure authentication
az login
az account set --subscription <your-subscription-id>

# 4. Set required environment variables
export LOG_ANALYTICS_WORKSPACE_ID="your-workspace-id"
export AZURE_OPENAI_ENDPOINT="your-openai-endpoint"
export AZURE_OPENAI_API_KEY="your-api-key"

# 5. Run the application
uvicorn main:app --host 0.0.0.0 --port 8000 --reload

# 6. Access the dashboard
open http://localhost:8000
```

## 🚀 Getting Started

### Prerequisites

- **Azure Subscription**: Required for Log Analytics and OpenAI services
- **Python 3.11+**: Core runtime requirement (3.9+ supported)
- **Azure CLI**: For authentication and deployment
- **Log Analytics Workspace**: For inventory data with Azure Arc enabled machines
- **Azure OpenAI**: GPT-4 deployment for conversational AI
- **Azure Cosmos DB**: (Optional) For persistent caching and communication logs
- **Playwright**: For web scraping capabilities

### Environment Variables

Create a `.env` file or configure these in Azure App Service Application Settings:

```bash
# Azure Authentication (Managed Identity recommended for production)
AZURE_CLIENT_ID=your-client-id                    # Optional with Managed Identity
AZURE_CLIENT_SECRET=your-client-secret            # Optional with Managed Identity
AZURE_TENANT_ID=your-tenant-id

# Azure Log Analytics
LOG_ANALYTICS_WORKSPACE_ID=your-workspace-id      # Required for inventory data

# Azure OpenAI
AZURE_OPENAI_ENDPOINT=your-openai-endpoint        # Required for GPT-4 chat
AZURE_OPENAI_API_KEY=your-openai-key              # Required
AZURE_OPENAI_API_VERSION=2024-02-15-preview
AZURE_OPENAI_DEPLOYMENT_NAME=gpt-4                # GPT-4 deployment name
AZURE_OPENAI_MODEL=gpt-4                          # Model version
MCP_AGENT_TEMPERATURE=0.2                          # Optional temperature for MCP orchestrator
AZURE_OPENAI_CHAT_DEPLOYMENT_NAME=gpt-4o-mini     # Chat deployment for MCP orchestrator
INVENTORY_ASSISTANT_TEMPERATURE=0.2               # Optional override for inventory assistant
INVENTORY_ASSISTANT_MAX_TOKENS=900                # Optional override for inventory assistant
MCP_AGENT_MAX_TOKENS=900                          # Optional override for MCP orchestrator

# Azure Cosmos DB (Optional - for persistent caching and communications)
COSMOS_ENDPOINT=your-cosmos-endpoint
COSMOS_KEY=your-cosmos-key
COSMOS_DATABASE_NAME=eol-agentic                  # Default database name
COSMOS_CONTAINER_NAME=communications              # Default container name

# SRE MCP Server Configuration
SRE_ENABLED=true                                   # Enable/disable SRE MCP server
SUBSCRIPTION_ID=your-subscription-id               # Required for SRE operations
TEAMS_WEBHOOK_URL=https://outlook.office.com/webhook/...  # Primary Teams channel
TEAMS_CRITICAL_WEBHOOK_URL=https://outlook.office.com/webhook/...  # Optional critical channel
SRE_TEAMS_CHANNEL="SRE Incidents"                 # Teams channel name for reference
SRE_AUTO_TRIAGE_ENABLED=true                      # Enable automatic incident triage
SRE_MCP_LOG_LEVEL=INFO                            # Log level for SRE MCP server

# Alert Configuration (Optional - for email notifications)
SMTP_SERVER=smtp.office365.com
SMTP_PORT=587
SMTP_USERNAME=your-email@domain.com
SMTP_PASSWORD=your-smtp-password
ALERT_FROM_EMAIL=alerts@domain.com
ALERT_TO_EMAIL=admin@domain.com

# Application Configuration
ENVIRONMENT=production                             # production, development, or staging
PYTHONUNBUFFERED=1                                # Required for Azure App Service logging
WEBSITES_PORT=8000                                # Required for Azure App Service
WEBSITE_SITE_NAME=your-app-name                   # Auto-set by Azure App Service

# Performance Tuning (Optional)
CACHE_TTL_SECONDS=300                             # Cache TTL (default: 5 minutes)
AGENT_TIMEOUT_SECONDS=30                          # Agent timeout (default: 30s)
MAX_CONCURRENT_AGENTS=10                          # Max concurrent agents
```

### Installation

1. **Clone the repository**:
   ```bash
   git clone <repository-url>
   cd gcc-demo/app/agentic/eol
   ```

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure authentication**:
   ```bash
   az login
   az account set --subscription <your-subscription-id>
   ```

4. **Set environment variables** (or create `.env` file):
   ```bash
   export LOG_ANALYTICS_WORKSPACE_ID="your-workspace-id"
   export AZURE_OPENAI_ENDPOINT="your-openai-endpoint"
   export AZURE_OPENAI_API_KEY="your-openai-key"
   # Optional: Cosmos DB for persistence
   export COSMOS_ENDPOINT="your-cosmos-endpoint"
   export COSMOS_KEY="your-cosmos-key"
   ```

5. **Install Playwright browsers** (required for web scraping):
   ```bash
   playwright install chromium
   ```

6. **Run the application**:
   ```bash
   # Using uvicorn directly
   uvicorn main:app --host 0.0.0.0 --port 8000 --reload
   
   # Or using Python
   python main.py
   ```

7. **Access the web interface**:
   - Navigate to `http://localhost:8000`
   - Dashboard homepage with live statistics
   - Key interfaces:
     - `/` - Dashboard with real-time metrics
     - `/inventory` - Inventory management
     - `/eol-search` - EOL search interface
   - `/eol-searches` - Search history viewer
   - `/inventory-assistant` - Inventory assistant conversational interface
     - `/alerts` - Alert management
     - `/cache` - Cache statistics
     - `/agents` - Agent monitoring

## 🔧 Configuration

### Agent Configuration

The multi-agent system can be configured through environment variables:

```bash
# Agent Timeouts
AGENT_TIMEOUT_SECONDS=30
EOL_SEARCH_TIMEOUT=15

# Cache Configuration
CACHE_TTL_SECONDS=3600
MAX_CACHE_SIZE=1000

# MCP Orchestrator defaults
MCP_AGENT_TEMPERATURE=0.2
MCP_AGENT_MAX_ITERATIONS=50
MCP_AGENT_MAX_TOKENS=900
INVENTORY_ASSISTANT_TEMPERATURE=0.2
INVENTORY_ASSISTANT_MAX_TOKENS=900

# Concurrency Limits
MAX_CONCURRENT_AGENTS=10
MAX_PARALLEL_REQUESTS=5
```

### Smart Search Configuration

The intelligent EOL search system supports:

- **Confidence Thresholds**: Configurable minimum confidence levels
- **Early Termination**: High-confidence results stop additional searches
- **Agent Prioritization**: Vendor-specific agents prioritized over generic ones
- **Fallback Strategies**: Multiple search strategies for comprehensive coverage
- **Shared Chat Defaults**: Both inventory assistant and MCP orchestrator use the same ChatOptions builder for consistent temperature, max tokens, and tool-call settings

## 📊 API Endpoints

All API endpoints follow the **StandardResponse** format for consistency:

```json
{
  "success": true,
  "data": [...],           // Array of result objects
  "count": 1,              // Number of items in data array
  "cached": false,         // Whether result came from cache
  "timestamp": "2025-10-15T12:34:56.789Z",
  "metadata": {            // Optional metadata
    "agent": "endpoint_name",
    "execution_time_ms": 150
  },
  "error": null            // Error message if success=false
}
```

**Accessing API Documentation:**
- Interactive Swagger UI: `http://localhost:8000/docs`
- ReDoc UI: `http://localhost:8000/redoc`
- OpenAPI JSON Schema: `http://localhost:8000/openapi.json`

### Web Interface Routes
- `GET /` - Dashboard homepage with real-time statistics
- `GET /inventory` - Inventory management interface
- `GET /eol-search` - EOL search interface
- `GET /eol-searches` - EOL search history viewer
- `GET /inventory-assistant` - Inventory assistant conversational interface
- `GET /alerts` - Alert management interface
- `GET /cache` - Cache statistics dashboard
- `GET /agent-cache-details` - Detailed agent cache metrics
- `GET /agents` - Agent status monitoring

### Inventory Endpoints
- `GET /api/inventory` - Get enhanced software inventory with EOL data
- `GET /api/inventory/status` - Get inventory processing status
- `GET /api/os` - Get operating system inventory
- `GET /api/os/summary` - Get OS inventory summary
- `GET /api/inventory/raw/software` - Get raw software inventory from Log Analytics
- `GET /api/inventory/raw/os` - Get raw OS inventory from Log Analytics
- `POST /api/inventory/reload` - Force reload inventory from Log Analytics
- `POST /api/inventory/clear-cache` - Clear inventory caches

### EOL Analysis Endpoints
- `GET /api/eol` - Get EOL data with filters (software, version, vendor)
- `POST /api/analyze` - Comprehensive EOL risk analysis
- `POST /api/search/eol` - Search EOL data with smart routing
- `POST /api/verify-eol-result` - Verify EOL result accuracy
- `POST /api/cache-eol-result` - Cache EOL result to Cosmos DB
- `GET /api/eol-agent-responses` - Get EOL search history
- `POST /api/eol-agent-responses/clear` - Clear EOL search history

### Agent Management Endpoints
- `GET /api/agents/status` - Agent health and performance metrics
- `GET /api/status` - Application status overview

### Alert Management Endpoints
- `GET /api/alerts/config` - Get alert configuration
- `POST /api/alerts/config` - Save alert configuration
- `POST /api/alerts/config/reload` - Reload alert configuration
- `GET /api/alerts/preview` - Preview alerts without sending
- `POST /api/alerts/smtp/test` - Test SMTP configuration
- `POST /api/alerts/send` - Send EOL alerts via email

### Cache Management Endpoints
- `GET /api/cache/status` - Get cache status across all agents
- `GET /api/cache/inventory/stats` - Get inventory cache statistics
- `GET /api/cache/inventory/details` - Get detailed inventory cache data
- `GET /api/cache/webscraping/details` - Get web scraping cache details
- `GET /api/cache/stats/enhanced` - Get comprehensive cache statistics
- `GET /api/cache/stats/agents` - Get agent cache statistics
- `GET /api/cache/stats/performance` - Get cache performance summary
- `POST /api/cache/clear` - Clear inventory and alert caches
- `POST /api/cache/purge` - Purge all caches (inventory + EOL)
- `POST /api/cache/stats/reset` - Reset cache statistics

### Cosmos DB Cache Endpoints
- `GET /api/cache/cosmos/stats` - Get Cosmos DB cache statistics
- `GET /api/cache/cosmos/config` - Get Cosmos DB configuration
- `GET /api/cache/cosmos/debug` - Debug Cosmos DB cache state
- `POST /api/cache/cosmos/clear` - Clear Cosmos DB cache
- `POST /api/cache/cosmos/initialize` - Initialize Cosmos DB connection
- `POST /api/cache/cosmos/test` - Test Cosmos DB cache operations

### Communication History Endpoints
- `GET /api/communications/eol` - Get EOL orchestrator communications
- `GET /api/communications/inventory-assistant` - Get inventory assistant communications
- `POST /api/communications/clear` - Clear EOL communications
- `POST /api/communications/inventory-assistant/clear` - Clear inventory assistant communications

### Health & Monitoring Endpoints
- `GET /health` - Basic health check
- `GET /api/health/detailed` - Detailed health status with dependencies
- `GET /api/test-logging` - Test logging configuration
- `GET /api/cosmos/test` - Test Cosmos DB connectivity

### Inventory Assistant Endpoints
- `POST /api/inventory-assistant` - AI-powered conversational interface for inventory queries

### MCP Chat Endpoints
- `GET /azure-mcp` - Azure MCP co-pilot web interface (SSE-based chat)
- `POST /api/azure-mcp/chat` - MCP orchestrator chat endpoint (SSE streaming)

## 📐 Module Responsibilities

#### `api/health.py` - Health & Status
**Purpose**: Application health monitoring and status reporting  
**Endpoints**:
- `GET /health` - Basic health check (fast, no dependencies)
- `GET /api/health/detailed` - Comprehensive health with dependency checks
- `GET /api/status` - Application status overview

#### `api/cache.py` - Cache Management
**Purpose**: Comprehensive cache control and statistics  
**Endpoints**:
- `GET /api/cache/status` - Overall cache status
- `GET /api/cache/inventory/stats` - Inventory cache metrics
- `GET /api/cache/inventory/details` - Detailed inventory analysis
- `GET /api/cache/webscraping/details` - Per-agent web scraping cache
- `GET /api/cache/cosmos/stats` - Cosmos DB cache statistics
- `GET /api/cache/cosmos/config` - Cosmos configuration
- `GET /api/cache/cosmos/debug` - Cosmos debug information
- `GET /api/cache/stats/enhanced` - Comprehensive statistics
- `GET /api/cache/stats/agents` - Agent-level statistics
- `GET /api/cache/stats/performance` - Performance summary
- `POST /api/cache/clear` - Clear inventory caches
- `POST /api/cache/purge` - Purge EOL agent caches
- `POST /api/cache/cosmos/clear` - Clear Cosmos cache
- `POST /api/cache/cosmos/initialize` - Initialize Cosmos
- `POST /api/cache/cosmos/test` - Test cache operations
- `POST /api/cache/stats/reset` - Reset statistics
- `GET /api/cache/ui` - Cache management UI

#### `api/inventory.py` - Inventory Operations
**Purpose**: Software and OS inventory management  
**Endpoints**:
### Local Virtual Environment Setup
To run the tests using pytest, it is recommended to use a local virtual environment. Here’s how to set it up:
```bash
python -m venv .venv
source .venv/bin/activate  # On Windows use .venv\Scripts\activate
pip install -r requirements-dev.txt
pytest
```
If `requirements-dev.txt` is not present, install `pytest` (and `pytest-asyncio`) manually before running the suite.
- `GET /api/inventory` - Enhanced inventory with EOL data
- `GET /api/inventory/status` - Processing status
- `GET /api/os` - OS inventory data
- `GET /api/os/summary` - OS summary statistics
- `GET /api/inventory/raw/software` - Raw software from Log Analytics
- `GET /api/inventory/raw/os` - Raw OS from Log Analytics
- `POST /api/inventory/reload` - Force reload from Azure

#### `api/eol.py` - EOL Analysis
**Purpose**: End-of-life data search and analysis  
**Endpoints**:
- `GET /api/eol` - EOL data with filters
- `POST /api/analyze` - Comprehensive risk analysis
- `POST /api/search/eol` - Smart EOL search with routing
- `POST /api/verify-eol-result` - Verify result accuracy
- `GET /api/eol-agent-responses` - Search history

#### `api/cosmos.py` - Cosmos DB Operations
**Purpose**: Cosmos DB connectivity and data management  
**Endpoints**:
- `GET /api/cosmos/test` - Test connectivity
- `POST /api/cache-eol-result` - Cache EOL result
- `GET /api/cosmos/communications/count` - Communications count
- `GET /api/cosmos/communications/recent` - Recent communications
- `POST /api/cosmos/communications/cleanup` - Cleanup old data
- `GET /api/cosmos/health` - Database health check

#### `api/agents.py` - Agent Management
**Purpose**: Agent configuration and monitoring  
**Endpoints**:
- `GET /api/agents/status` - Agent health metrics
- `GET /api/agents/list` - List all agents
- `POST /api/agents/toggle` - Enable/disable agents
- `POST /api/agents/url/add` - Add custom URLs
- `DELETE /api/agents/url/remove` - Remove URLs

#### `api/alerts.py` - Alert Management
**Purpose**: EOL alert configuration and email notifications  
**Endpoints**:
- `GET /api/alerts/config` - Get alert configuration
- `POST /api/alerts/config` - Save configuration
- `POST /api/alerts/config/reload` - Reload from Cosmos
- `GET /api/alerts/preview` - Preview alerts
- `POST /api/alerts/smtp/test` - Test SMTP settings
- `POST /api/alerts/send` - Send email alerts

#### `api/communications.py` - Communication History
**Purpose**: Agent-to-agent communication tracking  
**Endpoints**:
- `GET /api/communications/eol` - EOL orchestrator history
- `GET /api/communications/inventory-assistant` - Inventory assistant history
- `POST /api/communications/clear` - Clear EOL history
- `POST /api/communications/inventory-assistant/clear` - Clear inventory assistant history
- `GET /api/agent-communications/{session_id}` - Session communications
- `GET /api/debug/agent-communications` - Debug all communications

#### `api/inventory_asst.py` - Inventory Assistant Interface
**Purpose**: AI-powered inventory assistant orchestration  
**Endpoints**:
- `POST /api/inventory-assistant` - AI-powered conversational queries

**Features**:
- Multi-agent orchestration (10+ specialized agents)
- Confirmation workflows for complex operations
- Full conversation transparency (200 messages, 100 communications)
- Timeout management (170s effective + 10s buffer)
- Inventory context caching (5-minute TTL)
- Response size limits (100k chars)
- JSON cleaning for large conversation data

#### `api/ui.py` - HTML Page Templates
**Purpose**: Web interface page rendering  
**Endpoints**:
- `GET /` - Homepage/dashboard
- `GET /inventory` - Inventory management UI
- `GET /eol-search` - EOL search interface
- `GET /eol-searches` - Search history viewer
- `GET /inventory-assistant` - Inventory assistant interface
- `GET /alerts` - Alert configuration UI
- `GET /cache` - Cache statistics dashboard
- `GET /agent-cache-details` - Detailed agent metrics
- `GET /agents` - Agent configuration UI
- `GET /azure-mcp` - Azure MCP co-pilot chat interface

#### `api/debug.py` - Debug Utilities
**Purpose**: Development and troubleshooting tools  
**Endpoints**:
- `POST /api/debug_tool_selection` - Test tool selection logic
- `GET /api/debug/cache` - Cache debugging information
- `GET /api/debug/config` - Configuration validation

#### `api/azure_mcp.py` - Azure MCP Co-pilot
**Purpose**: MCP orchestrator chat interface with SSE streaming  
**Endpoints**:
- `GET /azure-mcp` - Web-based chat UI for Azure MCP operations
- `POST /api/azure-mcp/chat` - SSE-streaming chat endpoint (300s timeout, 10s keepalive)

**Features**:
- Real-time SSE events: reasoning, action, observation, synthesis, error, done
- Hybrid orchestrator delegates monitor tasks to MonitorAgent sub-agent
- Hallucination guard blocks fabricated data before tools are called
- Conversation history with summarization for context window management

### Module Benefits

✅ **Separation of Concerns**: Each module handles a specific domain  
✅ **Improved Maintainability**: Easier to locate and update endpoint logic  
✅ **Better Testing**: Individual modules can be tested in isolation  
✅ **Reduced Complexity**: Main application file reduced from 3,569 to 2,876 lines (19% reduction)  
✅ **Clear Organization**: 78 endpoints organized across 10 specialized modules  
✅ **Enhanced Documentation**: Each module has comprehensive docstrings  

### Migration Notes

All endpoints maintain **backward compatibility** with existing clients. The refactoring only affects internal code organization, not the API contract.

## 🎯 Smart EOL Search

The application implements a sophisticated 3-strategy search approach:

### Strategy 1: Exact Match
- Precise product name and version matching
- Highest confidence results (95%+)
- Early termination for efficient processing

### Strategy 2: Name-Only Search
- Searches using product name without version
- Handles cases where version formats differ
- Medium confidence results (80-95%)

### Strategy 3: Normalized Search
- Fallback search with normalized product names
- Handles variations in naming conventions
- Lower confidence results (60-80%)

### Confidence-Based Early Return

- **≥90% Confidence**: Immediate return for vendor-specific agents
- **≥80% Confidence**: Early return for general searches
- **<80% Confidence**: Continue to next strategy
- **Multiple Agents**: Best result across all agents returned

## 🔍 Key Features Deep Dive

### 1. Real-time Dashboard
- **Live Statistics**: Active agents, cached items, AI sessions, database items
- **Performance Metrics**: Average response times, cache hit rates, system health
- **Recent Activity**: Real-time view of agent interactions and operations
- **Auto-refresh**: Updates every 2 minutes with manual refresh option

### 2. Intelligent Inventory Management
- **Product Extraction**: Intelligent parsing of Azure Log Analytics inventory data
- **Version Matching**: Precise product-to-line matching using name+version validation
- **EOL Integration**: Automatic enhancement of inventory with EOL information
- **Unified Cache**: Consolidated caching for software and OS inventory
- **Performance Optimization**: Parallel processing, multi-level caching (5-minute TTL)

### 3. Risk Assessment & Alerts
- **Risk Levels**:
  - **Critical**: Software already end-of-life
  - **High**: EOL within 6 months
  - **Medium**: EOL within 2 years
  - **Low**: Currently supported with long runway
- **Alert Management**: Configurable EOL alerts with customizable thresholds
- **SMTP Notifications**: Email alerts for critical and high-risk software
- **Alert Preview**: Preview alerts before sending to validate configuration

### 4. Advanced Caching System
- **Multi-level Caching**: In-memory + Cosmos DB persistence
- **Cache Statistics**: Real-time metrics for all agents and operations
- **Performance Tracking**: Request counts, hit rates, response times, error rates
- **Intelligent Expiration**: TTL-based cache with manual purge options
- **Agent-specific Caching**: Dedicated caches for inventory, EOL, and web scraping

### 5. Agent Orchestration & Monitoring
- **Performance Metrics**: Response times, success rates, cache hit ratios per agent
- **Health Checks**: Agent availability and error rates
- **Communication Logs**: Detailed interaction history stored in Cosmos DB
- **Agent Statistics**: Request counts, cache performance, URL-level metrics
- **Load Management**: Intelligent request distribution and timeout handling

### 6. Conversational AI (Azure OpenAI Integration)
- **Natural Language**: Ask questions about your software inventory using GPT-4o-mini
- **Multi-Agent Collaboration**: Specialized agents collaborate to provide insights
- **Context Awareness**: Maintains conversation context and history
- **Web Surfer Integration**: Dynamic web content retrieval for up-to-date information
- **Search History**: Track all EOL searches with timestamps and confidence scores
- **Actionable Insights**: Specific recommendations for EOL management

### 7. Web Scraping Capabilities
- **Playwright Agent**: Browser automation for JavaScript-rendered content
- **Azure AI Agent Service**: Modern intelligent web data extraction
- **Web Surfer Agent**: Optional legacy AutoGen-based dynamic content retrieval
- **Cache Management**: Separate cache for web scraping results

## 🚀 Deployment

### Azure App Service (Recommended)

The application is optimized for Azure App Service deployment with Managed Identity:

```bash
# Navigate to deployment directory
cd deploy/

# Deploy container to Azure Container Registry and App Service
./deploy-container.sh

# The script will:
# 1. Build the Docker image
# 2. Push to Azure Container Registry
# 3. Update App Service with new image
# 4. Configure application settings
```

**App Service Configuration Requirements:**
- **Runtime**: Python 3.11+ or Docker container
- **Plan**: At least B1 or higher (B2+ recommended for production)
- **Authentication**: Managed Identity enabled for Azure resource access
- **Application Settings**: Configure all required environment variables
- **Logging**: Enable Application Insights for monitoring
- **Always On**: Enable for production workloads

### Docker Deployment

```bash
# Build the container image
docker build -t eol-agentic-app:latest .

# Run locally for testing
docker run -p 8000:8000 \
  -e LOG_ANALYTICS_WORKSPACE_ID=your-workspace-id \
  -e AZURE_OPENAI_ENDPOINT=your-endpoint \
  -e AZURE_OPENAI_API_KEY=your-key \
  -e COSMOS_ENDPOINT=your-cosmos-endpoint \
  -e COSMOS_KEY=your-cosmos-key \
  eol-agentic-app:latest

# Push to Azure Container Registry
az acr login --name your-registry
docker tag eol-agentic-app:latest your-registry.azurecr.io/eol-agentic-app:latest
docker push your-registry.azurecr.io/eol-agentic-app:latest
```

### Azure Container Instances

```bash
# Deploy to Azure Container Instances
az container create \
  --resource-group your-rg \
  --name eol-agentic-app \
  --image your-registry.azurecr.io/eol-agentic-app:latest \
  --cpu 2 --memory 4 \
  --ports 8000 \
  --environment-variables \
    LOG_ANALYTICS_WORKSPACE_ID=your-workspace-id \
    AZURE_OPENAI_ENDPOINT=your-endpoint \
  --secure-environment-variables \
    AZURE_OPENAI_API_KEY=your-key \
    COSMOS_KEY=your-cosmos-key
```

### Configuration Files

- `deploy/Dockerfile` - Container image definition
- `deploy/deploy-container.sh` - Automated deployment script
- `web.config` - IIS/App Service configuration
- `.azure/` - Azure-specific configuration files

## 📈 Performance & Monitoring

### Real-time Metrics Dashboard
Access comprehensive metrics at `/cache` and `/`:
- **Active Agents**: Count of all registered agents
- **Cached Items**: Total cached items across all caches
- **AI Sessions**: Total Azure OpenAI conversation sessions
- **Database Items**: Cosmos DB operations count
- **Cache Hit Rates**: Per-agent and global cache efficiency
- **Response Times**: Average, min, max response times per agent
- **Error Rates**: Error tracking and alerting
- **Recent Activity**: Last 20 operations per agent

### Cache Statistics Manager
The `cache_stats_manager` provides comprehensive tracking:
- **Agent Statistics**: Per-agent request counts, cache hits/misses, response times
- **Inventory Statistics**: Unified inventory cache performance
- **Cosmos Statistics**: Database cache hit rates and response times
- **Performance Summary**: Overall system metrics including uptime and throughput
- **URL-level Metrics**: Granular tracking for specific API endpoints

### Optimization Features
- **Multi-level Caching**: In-memory (5-min TTL) + Cosmos DB persistence
- **Parallel Processing**: Concurrent agent execution with configurable limits
- **Smart Cache Expiration**: TTL-based with manual purge options
- **Early Termination**: Confidence-based search optimization (≥90% confidence)
- **Request Deduplication**: Prevent duplicate concurrent requests
- **Connection Pooling**: Efficient Azure service connections

### Monitoring Endpoints
- `GET /api/cache/stats/enhanced` - Comprehensive cache statistics
- `GET /api/cache/stats/agents` - Per-agent cache metrics
- `GET /api/cache/stats/performance` - Performance summary
- `GET /api/health/detailed` - Detailed health check with dependencies
- `GET /api/agents/status` - Agent health and availability

## ✅ Testing

The application includes a comprehensive pytest-based test suite with **63 tests** covering all 72 endpoints.

### Quick Start

```bash
# Run all tests
python3 tests/run_comprehensive_tests.py

# Run specific category
python3 tests/run_comprehensive_tests.py --category cache

# Run with coverage
python3 tests/run_comprehensive_tests.py --coverage

# Quick smoke test
python3 tests/run_comprehensive_tests.py --quick
```

### Test Suite Coverage

| Category | Tests | Coverage |
|----------|-------|----------|
| Health & Status | 5 | All health and monitoring endpoints |
| Inventory | 8 | Software & OS inventory operations |
| EOL Search | 4 | EOL analysis and search functionality |
| Cache Management | 15 | All cache operations and statistics |
| Alerts | 6 | Alert configuration and SMTP testing |
| Agent Management | 5 | Agent status and control |
| Cosmos DB | 7 | Database operations and caching |
| Communications | 6 | Email and notification systems |
| UI Routes | 7 | HTML page rendering |

**Total: 63 tests covering 72 endpoints (57 API + 15 UI)**

### Test Features

- ✅ **Mock Data**: 500+ software items, 50 OS entries - no Azure dependencies required
- ✅ **Async Testing**: Full async/await support with pytest-asyncio
- ✅ **StandardResponse Validation**: All API tests verify response format compliance
- ✅ **Category Organization**: Tests grouped by functional area
- ✅ **Selective Execution**: Run by category, marker, or individual test
- ✅ **Coverage Reports**: HTML and terminal coverage analysis
- ✅ **Detailed Reporting**: Pass/fail status with timing and error details
- ✅ **Resource Lifecycle**: `tests/test_eol_orchestrator.py` verifies dependency injection and cleanup semantics

### Using pytest directly

```bash
# Run all tests
pytest tests/ -v

# Run specific test file
pytest tests/test_cache_endpoints.py -v

# Run EOL orchestrator dependency injection tests
pytest tests/test_eol_orchestrator.py -v

# Run tests with specific marker
pytest -m cache -v

# Run with coverage
pytest tests/ --cov=. --cov-report=html
```

### Available Test Markers

- `@pytest.mark.api` - API endpoint tests
- `@pytest.mark.ui` - UI/HTML route tests
- `@pytest.mark.cache` - Cache functionality tests
- `@pytest.mark.eol` - EOL analysis tests
- `@pytest.mark.inventory` - Inventory tests
- `@pytest.mark.alerts` - Alert management tests

### Test Documentation

For detailed test information, see:
- **[tests/README.md](tests/README.md)** - Complete test suite documentation
- **[tests/TEST_RESULTS_SUMMARY.md](tests/TEST_RESULTS_SUMMARY.md)** - Test results and analysis

## �🤝 Contributing

### Development Setup

1. **Install development dependencies**:
   ```bash
   pip install -r requirements.txt
   pip install pytest pytest-asyncio
   ```

2. **Run tests**:
   ```bash
   pytest
   ```

3. **Code formatting**:
   ```bash
   black .
   isort .
   ```

### Adding New EOL Agents

To add a new EOL agent:

1. Create a new agent class inheriting from `BaseEOLAgent`.
2. Implement required methods: `get_eol_data()` (and optionally `search_eol()`).
3. Register the agent in `_create_default_agents()` so it participates in default orchestration.
4. Extend `DEFAULT_VENDOR_ROUTING` with vendor keywords to enable intelligent routing.
5. Add targeted tests (e.g. via `tests/test_eol_orchestrator.py`) to verify routing and cleanup behaviors.

### Architecture Guidelines

- **Async/Await**: All I/O operations must be asynchronous
- **Error Handling**: Comprehensive exception handling with graceful degradation
- **Logging**: Structured logging with correlation IDs
- **Caching**: Implement caching for expensive operations
- **Configuration**: Use environment variables for configuration

## 🆕 Recent Updates

### Hybrid Orchestrator Architecture (February 2026)
Major architectural overhaul: introduced hybrid orchestrator + sub-agent pattern.

**MonitorAgent Sub-Agent**:
- Created `agents/monitor_agent.py` — focused sub-agent with own system prompt and ReAct loop
- Only sees ~12 tools (monitor + CLI) vs 100+ in the orchestrator
- Eliminates tool confusion (e.g., ACR vs Container Apps) for monitor operations
- Streams events through orchestrator's SSE pipeline — frontend unchanged

**Dedicated Deploy Tools**:
- `deploy_query` — downloads .kql, strips comments, collapses newlines, deploys as saved search
- `deploy_alert` — downloads alert template, extracts KQL, deploys as scheduled query rule
- `deploy_workbook` — existing tool, deploys via ARM template
- All use `subprocess_exec` with argument lists (no shell escaping issues)

**CompositeMCPClient Enhancements**:
- `get_tools_by_sources()` / `get_tools_excluding_sources()` for sub-agent initialization
- In hybrid mode: monitor tools replaced with single `monitor_agent` meta-tool
- `_SOURCE_GUIDANCE` slimmed ~60%, routing detail moved to tool descriptions
- `_TOOL_DISAMBIGUATION` expanded (8 entries including deprecated tool redirects)

**Tool Description Overhaul**:
- All 19 local MCP tools updated with clear, actionable descriptions
- 3 legacy monitor tools marked DEPRECATED with redirect instructions
- Each tool description specifies when to use it, what it returns, and its parameters

**Orchestrator Improvements**:
- Unified to AsyncAzureOpenAI SDK (removed Microsoft Agent Framework dependency)
- Conversation summarization with safe boundary detection (prevents orphaned tool messages)
- Hallucination guard blocks fabricated data on first iteration
- SSE keepalive reduced to 10s, chat timeout increased to 300s
- Frontend: unlimited SSE reconnect retries, expanded HTML trust pattern, near-duplicate deduplication

**ResponseFormatter** (`utils/response_formatter.py`):
- Markdown → HTML conversion (tables, headers, lists, code blocks)
- Near-duplicate content deduplication with substring matching

### Major Refactoring - API Standardization (October 2025)
A comprehensive refactoring effort has modernized the codebase with significant improvements:

**Phase 1: Cache Consolidation** (3 commits)
- Consolidated cache operations into unified system
- Created `StandardResponse` models for consistent API responses
- Removed legacy code and redundant patterns
- **Net reduction**: -404 lines of code

**Phase 2: API Standardization** (16 commits across 8 sub-phases)
- Systematically refactored all **61 endpoints** with decorator pattern
- Added `@readonly_endpoint`, `@write_endpoint`, `@standard_endpoint` decorators
- Implemented automatic timeout handling (5-30s based on operation)
- Added comprehensive docstrings to every endpoint for OpenAPI documentation
- **Removed**: ~2,000 lines of boilerplate error handling code
- **Testing**: 100% success rate (8/8 endpoints validated with mock data)
- **Result**: Cleaner, more maintainable API with standardized responses

**Phase 3: Frontend Compatibility** (1 commit)
- Added `api.unwrapResponse()` JavaScript helper for StandardResponse handling
- Automatic unwrapping maintains backward compatibility
- Zero breaking changes to existing frontend code
- Smart detection works with both StandardResponse and legacy formats

**Refactoring Benefits:**
- ✅ **Consistent Error Handling**: All endpoints use standardized error responses
- ✅ **Automatic Timeouts**: Configurable per-endpoint with sensible defaults
- ✅ **Performance Tracking**: Built-in statistics for every endpoint
- ✅ **OpenAPI Documentation**: Comprehensive auto-generated API docs at `/docs`
- ✅ **Reduced Complexity**: -2,400 lines of code removed
- ✅ **Better Testability**: Mock data framework for comprehensive testing
- ✅ **Type Safety**: Full Pydantic validation on all responses

**API Documentation:**
- FastAPI automatically generates OpenAPI 3.1.0 documentation
- Interactive API explorer available at: `http://localhost:8000/docs`
- OpenAPI JSON schema at: `http://localhost:8000/openapi.json`
- All 66 endpoints fully documented with request/response schemas

### Dashboard & Statistics (October 2025)
- **Real-time Dashboard**: New homepage with live statistics and metrics
- **Enhanced Cache Statistics**: Comprehensive tracking with `cache_stats_manager`
- **Agent Performance Monitoring**: Per-agent metrics with URL-level granularity
- **Recent Activity Feed**: Live view of the last 20 operations across all agents
- **Auto-refresh**: Dashboard updates every 2 minutes automatically

### Alert Management System
- **Configurable Alerts**: JSON-based alert configuration with risk thresholds
- **SMTP Integration**: Email notifications for critical and high-risk software
- **Alert Preview**: Preview alerts before sending to validate configuration
- **Test Functionality**: Test SMTP settings without sending actual alerts

### Enhanced Caching Architecture
- **Multi-level Caching**: In-memory + Cosmos DB with intelligent TTL management
- **Unified Inventory Cache**: Consolidated caching for software and OS inventory
- **Web Scraping Cache**: Dedicated cache for Playwright and web surfer results
- **Cache Management UI**: Visual interface for cache statistics and purging

### Azure OpenAI + MCP Architecture
- **AsyncAzureOpenAI SDK**: Direct OpenAI SDK integration for MCP orchestrator (replaced Agent Framework)
- **Hybrid Architecture**: MCPOrchestratorAgent + MonitorAgent sub-agent for monitor resources
- **ReAct Loop**: Reasoning + Acting loop with hallucination guard and confirmation workflows

### Azure AI Integration
- **Azure AI Agent Service**: Modern replacement for deprecated Bing Search API
- **Playwright Automation**: Browser-based web scraping for JavaScript-rendered content
- **Enhanced Search**: Multiple search strategies with fallback mechanisms

## 📄 License

This project is part of the GCC Demo infrastructure automation toolkit.

## 🆘 Support & Troubleshooting

### Common Issues

1. **Azure Authentication Failures**:
   ```bash
   # Verify Azure CLI login
   az account show
   
   # Check Managed Identity status (for App Service)
   az webapp identity show --name your-app --resource-group your-rg
   
   # Validate environment variables
   curl http://localhost:8000/api/health/detailed
   ```

2. **Log Analytics Connection Issues**:
   - Verify workspace ID: Check `LOG_ANALYTICS_WORKSPACE_ID` environment variable
   - Ensure Managed Identity has "Log Analytics Reader" role on workspace
   - Test connectivity: `GET /api/inventory/raw/software`
   - Validate KQL queries in Azure portal first

3. **Cosmos DB Connection Issues**:
   ```bash
   # Test Cosmos DB connectivity
   curl -X POST http://localhost:8000/api/cache/cosmos/initialize
   
   # Check Cosmos DB debug info
   curl http://localhost:8000/api/cache/cosmos/debug
   
   # Verify Managed Identity has "Cosmos DB Account Contributor" role
   ```

4. **Agent Performance Issues**:
   - Check agent status: `GET /api/agents/status`
   - Review cache statistics: `GET /api/cache/stats/enhanced`
   - Monitor recent activity: Visit `/` dashboard
   - Check Application Insights for detailed traces

5. **Cache Not Working**:
   ```bash
   # Check cache status
   curl http://localhost:8000/api/cache/status
   
   # Clear and reinitialize caches
   curl -X POST http://localhost:8000/api/cache/purge
   curl -X POST http://localhost:8000/api/inventory/reload
   ```

6. **Playwright/Web Scraping Errors**:
   ```bash
   # Install Playwright browsers
   playwright install chromium
   
   # Check web scraping cache
   curl http://localhost:8000/api/cache/webscraping/details
   ```

### Performance Tuning

**Environment Variables**:
```bash
# Increase cache TTL for stable environments (default: 300s)
CACHE_TTL_SECONDS=600

# Adjust agent timeout based on network conditions (default: 30s)
AGENT_TIMEOUT_SECONDS=45

# Configure concurrency based on Azure quotas (default: 10)
MAX_CONCURRENT_AGENTS=15
```

**App Service Configuration**:
- Use B2 or higher for production workloads
- Enable "Always On" to prevent cold starts
- Configure auto-scaling rules based on CPU/memory
- Enable Application Insights for detailed monitoring

**Database Optimization**:
- Use Cosmos DB Serverless for variable workloads
- Configure appropriate RU/s for provisioned throughput
- Enable Cosmos DB caching for frequently accessed data

### Monitoring & Alerts

**Built-in Monitoring**:
- Dashboard (`/`): Real-time statistics and recent activity
- Cache Dashboard (`/cache`): Detailed cache metrics and performance
- Agent Monitor (`/agents`): Agent health and communication history
- Search History (`/eol-searches`): Track all EOL searches

**Azure Integration**:
- **Application Insights**: Automatic request tracking and performance monitoring
- **Log Stream**: Real-time application logs via Azure portal or CLI
- **Alerts**: Configure Azure Monitor alerts for critical metrics
- **Health Endpoints**: `/health` and `/api/health/detailed` for availability monitoring

**Structured Logging**:
All logs include correlation IDs and structured data for easy troubleshooting:
```bash
# View logs in Azure App Service
az webapp log tail --name your-app --resource-group your-rg

# Download logs
az webapp log download --name your-app --resource-group your-rg
```

---

For detailed deployment instructions and advanced configuration, see the [deployment README](deploy/README.md).
