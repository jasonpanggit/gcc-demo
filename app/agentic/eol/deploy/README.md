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

- `deploy-app.sh` - Quick deployment without package building (legacy)
- `deploy-app-with-build.sh` - Deployment with proper Python package installation (recommended)

### App Settings Configuration

- `appsettings.json` - Default app settings
- `appsettings.production.json` - Production environment settings
- `appsettings.development.json` - Development environment settings

#### Build Configuration
- `SCM_DO_BUILD_DURING_DEPLOYMENT=true` - Enables building Python packages during deployment
- `ENABLE_ORYX_BUILD=true` - Enables Azure's Oryx build system for Python
- `WEBSITE_RUN_FROM_PACKAGE=0` - Disables package mode to allow package installation

#### Runtime Configuration
- `WEBSITES_PORT=8000` - Port for the web application
- `PYTHONUNBUFFERED=1` - Enables real-time Python logging
- `PYTHON_ENABLE_GUNICORN_MULTIWORKERS=true` - Enables multiple workers (production only)
- `WEBSITES_ENABLE_APP_SERVICE_STORAGE=false` - Disables persistent storage

### Usage

#### Deploy to Production
```bash
./deploy-app-with-build.sh production
# or simply
./deploy-app-with-build.sh
```

#### Deploy to Development
```bash
./deploy-app-with-build.sh development
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
├── Dockerfile                # Container configuration
├── .python-version           # Python version specification
├── deploy-agentic-eol.sh     # Automated deployment script
├── cleanup-agentic-eol.sh    # Resource cleanup script
└── README.md                 # This file
```

## 🛠 Quick Deployment

### Automated Deployment (Recommended)

Use the automated deployment script for a complete end-to-end deployment:

```bash
# Navigate to the app directory
cd app/agentic/eol/

# Run the deployment script
./deploy-agentic-eol.sh
```

The script will:
1. Deploy Azure infrastructure (25-35 minutes)
2. Set up Azure OpenAI model deployment
3. Deploy the FastAPI application
4. Configure environment variables
5. Verify deployment and provide endpoints

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

### AI Chat Interface
```http
POST /chat
Content-Type: application/json

{
  "query": "What software in our inventory is approaching end-of-life?"
}
```
AI-powered analysis of software inventory and EOL status.

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
