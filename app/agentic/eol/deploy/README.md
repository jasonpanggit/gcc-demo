# Agentic EOL Analysis Application

A comprehensive software End-of-Life (EOL) analysis application built with FastAPI and Azure OpenAI. This application provides intelligent software inventory management, EOL tracking, and AI-powered analysis capabilities.

## 🚀 Features

### Core Capabilities
- **Software Inventory Management**: Retrieve and analyze software inventory from Azure Log Analytics
- **EOL Date Tracking**: Lookup software end-of-life dates using the endoflife.date API
- **AI-Powered Analysis**: Chat interface using Azure OpenAI for intelligent software lifecycle insights
- **AutoGen Multi-Agent Framework**: Advanced multi-agent conversations for comprehensive analysis
- **RESTful API**: Comprehensive API endpoints for integration with other systems
- **Private Networking**: Secure deployment with VNet integration and private endpoints

### Technical Features
- **FastAPI Framework**: High-performance async web framework
- **Azure Integration**: Native integration with Azure services
- **AutoGen Framework**: Multi-agent AI conversations for complex analysis
- **Containerized Deployment**: Docker support for consistent deployments
- **Health Monitoring**: Built-in health checks and monitoring capabilities

## 🔧 Configuration Management

### Generate appsettings.json from Terraform

This directory includes `generate-appsettings.sh` to automatically create configuration files from Terraform outputs.

#### Prerequisites
- Terraform installed and project deployed
- jq installed (`brew install jq` on macOS)
- Agentic module deployed (`deploy_agentic_app = true`)

#### Usage
```bash
# Generate appsettings.json
./generate-appsettings.sh

# Generate to custom location
./generate-appsettings.sh appsettings.production.json
```

The script maps Terraform outputs to application settings:
- Azure subscription and resource group information
- Azure OpenAI endpoint and deployment details
- Cosmos DB connection information
- Log Analytics workspace configuration

#### Files
- `generate-appsettings.sh` - Generation script
- `appsettings.json.example` - Template structure
- Generated files are ignored by Git for security
- **Scalable Architecture**: Designed for enterprise-scale deployments

## 📦 Deployment Configuration

### Deployment Scripts

- `deploy-container.sh` - Build and push the Docker image, then update Azure Container Apps
- `generate-appsettings.sh` - Emit appsettings from Terraform outputs (writes `appsettings.json`)
- `show-logs.sh` - Stream logs from Container Apps or App Service based on appsettings
- `update_mcp_tool_metadata.py` - Refresh cached Azure MCP tool metadata used by the UI
- `update_monitor_community_metadata.py` - Scrape Azure Monitor Community repository and generate metadata

### Metadata Generation Scripts

#### Azure MCP Tool Metadata

Run the metadata refresh script inside the project virtual environment to update Azure MCP tool documentation:

```bash
source ../../../../.venv/bin/activate
python update_mcp_tool_metadata.py
```

The script writes to `../static/data/azure_mcp_tool_metadata.json`, which the web app reads at runtime.

#### Azure Monitor Community Metadata

Generate metadata for Azure Monitor Community resources (workbooks, alerts, queries) by scraping the GitHub repository:

```bash
python update_monitor_community_metadata.py
```

The script:
- **Uses HTML scraping** (no GitHub API token needed)
- Scrapes all 64 Azure service categories
- Recursively explores subdirectories to find all resources
- Generates: `../static/data/azure_monitor_community_metadata.json`
- Takes 3-5 minutes to complete (scrapes ~200+ HTTP requests)

This metadata file can be used by the UI to load resources instantly without making API calls on every page load.

### App Settings Configuration

- `appsettings.json` - Primary settings consumed by deployment scripts
- `appsettings.production.json` / `appsettings.development.json` - Optional overlays for convenience

Key runtime settings baked by the container script:
- `WEBSITES_PORT=8000`
- `PYTHONUNBUFFERED=1`
- `CONTAINER_MODE=true`
- `ENVIRONMENT=production`

**Note**: GitHub token configuration is no longer required. Azure Monitor Community resources now use HTML scraping instead of the GitHub API, eliminating rate limits and authentication requirements.

### Usage

#### Build and deploy to Azure Container Apps
```bash
# 1) Generate settings from Terraform outputs (run from deploy/)
./generate-appsettings.sh appsettings.json

# 2) Build, push, and deploy the container (from deploy/)
./deploy-container.sh               # auto-tag from git SHA
# optional: ./deploy-container.sh v1.2.3  # manual tag
# optional: ./deploy-container.sh "" true # build-only, no deploy

# 3) Stream logs (uses appsettings.json to resolve RG/app name)
./show-logs.sh
```

### Key Benefits of File-Based Configuration

1. **Version Control**: All settings are tracked in git
2. **Environment Consistency**: Same settings applied every time
3. **Transparency**: Easy to see what's being configured
4. **Automation**: No manual CLI configuration needed
5. **Environment Specific**: Different settings for dev/prod

## 📁 Project Structure

```
app/agentic/eol/
├── main.py                    # FastAPI application
├── requirements.txt           # Python dependencies
├── deploy/                    # Deployment assets (this folder)
│   ├── Dockerfile             # Container build for Azure Container Apps
│   ├── generate-appsettings.sh# Produce appsettings from Terraform outputs
│   ├── deploy-container.sh    # Build/push image and update Container Apps
│   ├── show-logs.sh           # Stream logs (Container Apps/App Service)
│   └── update_mcp_tool_metadata.py # Refresh cached MCP metadata
├── .python-version            # Python version specification
└── README.md                  # Platform overview
```

## 🛠 Quick Deployment

### Automated Deployment (Container Apps)

Use the container pipeline for end-to-end deployment:

```bash
# From repo root
cp demos/agentic/eol-agentic-demo.tfvars terraform.tfvars
terraform init && terraform apply -auto-approve

# Generate settings (writes deploy/appsettings.json)
cd app/agentic/eol/deploy
./generate-appsettings.sh appsettings.json

# Build/push image and update Container Apps
./deploy-container.sh

# Stream logs after deploy
./show-logs.sh
```

What it does:
1. Uses Terraform outputs to populate appsettings
2. Builds and pushes the container to ACR with the current git SHA tag
3. Updates the Azure Container App revision with required env vars
4. Streams logs for quick validation

Post-deploy checks:
- Application URL from `Deployment.ContainerApp.Url` in appsettings.json
- `https://<app>/healthz` for liveness
- `https://<app>/api/eol-cache-stats` and `/api/eol-latency` for cache/latency telemetry
- `https://<app>/healthz` for liveness
- `https://<app>/docs` for API docs
- `https://<app>/api/eol-cache-stats` and `/api/eol-latency` for cache/latency telemetry

### Manual Setup

If you prefer manual deployment:

1. **Deploy Infrastructure**:
```bash
# From project root
cp demos/agentic/eol-agentic-demo.tfvars terraform.tfvars
terraform init
terraform plan
terraform apply
```

2. **Install Dependencies**:
```bash
pip install -r requirements.txt
```

3. **Set Environment Variables**:
```bash
export AOAI_ENDPOINT="https://your-openai-service.openai.azure.com/"
export AOAI_DEPLOYMENT="gpt-4o-mini"
<!-- SEARCH_ENDPOINT removed: Azure AI Search no longer used -->
<!-- SEARCH_API_KEY removed: Azure AI Search no longer used -->
export LOG_ANALYTICS_WORKSPACE_ID="your-workspace-id"
```

4. **Run Locally**:
```bash
uvicorn main:app --reload
```

## 🌐 API Endpoints

### Health Check
```http
GET /healthz
```
Returns application health status.

**Response:**
```json
{"status": "ok"}
```

### Software Inventory
```http
GET /inventory?limit=50
```
Retrieves software inventory from Azure Log Analytics.

**Parameters:**
- `limit` (optional): Number of items to return (default: 50)

**Response:**
```json
[
  {
    "computer": "SERVER01",
    "name": "Microsoft Office",
    "version": "16.0",
    "publisher": "Microsoft Corporation"
  }
]
```

### EOL Lookup
```http
GET /eol?name=ubuntu&version=20.04
```
Checks end-of-life status for specified software.

**Parameters:**
- `name`: Software product name
- `version` (optional): Software version

**Response:**
```json
{
  "source": "endoflife.date",
  "data": {
    "cycle": "20.04",
    "eol": "2025-05-31",
    "latest": "20.04.6",
    "lts": true
  }
}
```

### Inventory Assistant API
```http
POST /inventory-assistant
Content-Type: application/json

{
  "message": "What software in our inventory is approaching end-of-life?"
}
```
AI-powered analysis of software inventory and EOL status powered by the Microsoft Agent Framework inventory assistant.

**Response:**
```json
{
  "answer": "Based on your current inventory, the following software items are approaching end-of-life..."
}
```

## 🏗 Architecture

### Azure Resources
- **App Service**: Hosts the FastAPI application with VNet integration
- **Azure OpenAI**: Provides GPT-4o-mini model for AI analysis
<!-- Azure AI Search removed -->
- **Log Analytics**: Software inventory data source
- **Virtual Network**: Private networking with firewall protection
- **Private Endpoints**: Secure connectivity to Azure services

### Network Security
- VNet integration for App Service
- Private endpoints for Azure services
- Azure Firewall for outbound traffic control
- NSG rules for subnet protection

### Data Flow
1. App Service queries Log Analytics for inventory data
2. External API calls to endoflife.date for EOL information
3. Azure OpenAI processes queries for intelligent analysis
4. All traffic flows through secure private networking

## 🔧 Configuration

### Environment Variables
| Variable | Description | Example |
|----------|-------------|---------|
| `AOAI_ENDPOINT` | Azure OpenAI endpoint URL | `https://your-service.openai.azure.com/` |
| `AOAI_DEPLOYMENT` | OpenAI model deployment name | `gpt-4o-mini` |
<!-- SEARCH_ENDPOINT removed -->
<!-- SEARCH_API_KEY removed -->
| `LOG_ANALYTICS_WORKSPACE_ID` | Log Analytics workspace ID | `workspace-guid` |

### Terraform Variables
Key configuration options in `eol-agentic-demo.tfvars`:
- `location`: Azure region (default: "Australia East")
- `environment`: Environment tag (default: "demo")
- `deploy_agentic_private_endpoints`: Enable private endpoints
- `aoai_sku_name`: Azure OpenAI SKU (default: "S0")

## 📊 Monitoring

### Health Monitoring
- Application health endpoint at `/healthz`
- Azure App Service built-in monitoring
- Log Analytics for application logs

### Performance Monitoring
- Azure Monitor integration
- Application Insights telemetry
- Custom metrics and alerts

## 🧹 Cleanup

To remove all deployed resources:

```bash
./cleanup-agentic-eol.sh
```

This will:
- Destroy all Azure infrastructure
- Remove Terraform state files
- Clean up local artifacts

## 💰 Cost Estimation

**Monthly Costs (approximate):**
- App Service (B1): $15-20
- Azure OpenAI (S0): $150-200
<!-- Azure AI Search cost removed -->
- Log Analytics: $20-30
- Networking: $30-50
- **Total: ~$300/month**

## 🔒 Security Considerations

- **Identity-First Auth**: Managed identity preferred; no Search API keys required

## 📈 Scaling

### Horizontal Scaling
- App Service can scale out to multiple instances
- Azure OpenAI supports rate limiting and scaling
- Load balancer distributes traffic

### Performance Optimization
- Connection pooling for Azure services
- Async operations for improved throughput
- Caching for frequently accessed data

## 🤝 Integration

### Teams Bot Integration
Placeholder endpoint for Microsoft Teams bot integration:
```http
POST /api/messages
```

### API Integration
RESTful endpoints support integration with:
- ServiceNow
- Microsoft System Center
- Custom inventory systems
- Monitoring platforms

## 📚 Dependencies

See `requirements.txt` for complete list:
- `fastapi`: Web framework
- `uvicorn`: ASGI server
- `azure-identity`: Azure authentication
- `azure-monitor-query`: Log Analytics client
<!-- azure-search-documents removed -->
- `openai`: Azure OpenAI client
- `requests`: HTTP client for external APIs

## 🐛 Troubleshooting

### Common Issues

**Application won't start:**
- Check environment variables are set
- Verify Azure credentials
- Review App Service logs

**Inventory endpoint returns 500:**
- Verify Log Analytics workspace ID
- Check managed identity permissions
- Confirm VNet integration

**EOL endpoint not working:**
- Verify firewall rules allow endoflife.date
- Check network connectivity
- Review application logs

### Debugging
1. Enable detailed logging in App Service
2. Use Azure Monitor for diagnostics
3. Check Kudu console for application state
4. Review network security group rules

## 📝 License

This project is licensed under the MIT License - see the project root for details.

## 🤝 Contributing

Contributions are welcome! Please read the contributing guidelines in the project root.
