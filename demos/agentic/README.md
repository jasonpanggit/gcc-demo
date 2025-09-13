# Agentic AI Applications Demo

This demo deploys a comprehensive agentic AI application ecosystem that demonstrates advanced Azure OpenAI integration, multi-agent workflows, and secure private deployment patterns.

## 🎯 Demo Overview

### End-of-Life (EOL) Software Analysis Agent
**Primary Application**: Intelligent software lifecycle management
- **Data Sources**: Azure Arc software inventory via Log Analytics
- **AI Processing**: Multi-agent workflows for EOL analysis
- **Knowledge Base**: Integration with endoflife.date API
- **Interface**: Chat-based interaction powered by Azure OpenAI
- **Security**: Fully private deployment with private endpoints

### Architecture Highlights
- **Private Deployment**: All services isolated in Non-Gen VNet
- **Secure Egress**: Traffic routed through Non-Gen Azure Firewall
- **Multi-Agent System**: Coordinated AI agents for complex analysis
- **Real-Time Chat**: Interactive interface for software analysis
- **Comprehensive Monitoring**: Application Insights and Log Analytics integration

## 🏗️ Infrastructure Components

### Core AI Services
- **Azure OpenAI Service**: GPT-4 and embedding models
- **App Service**: Python Flask application hosting
- **Cosmos DB**: Agent conversation and state storage
- **Application Insights**: Performance and usage monitoring

### Data & Analytics
- **Log Analytics Workspace**: Azure Arc inventory data source
- **Azure Monitor**: Infrastructure monitoring and alerting
- **Private Link Scope**: Secure monitoring connectivity

### Networking & Security
- **Non-Gen VNet**: Isolated network for non-generative workloads
- **Private Endpoints**: Secure service connectivity
- **Azure Firewall**: Controlled egress and security policies
- **Network Security Groups**: Subnet-level security controls

## 💰 Cost Analysis

### Monthly Operating Costs (~$200/month)
- **Azure OpenAI**: ~$100/month (based on usage)
- **App Service (P1v3)**: ~$75/month
- **Cosmos DB**: ~$25/month (1000 RU/s)
- **Private Endpoints**: ~$32/month (multiple endpoints)
- **Application Insights**: ~$10/month (basic monitoring)
- **Storage & Networking**: ~$5/month

### Cost Variables
- **AI Usage**: Varies significantly based on query volume
- **Compute Tier**: App Service plan can be scaled up/down
- **Database Throughput**: Cosmos DB RU/s adjustable
- **Monitoring Level**: Application Insights data retention

## ⏱️ Deployment Timeline

### Estimated Deployment Time: **25-35 minutes**
1. **Networking Setup** (8-12 minutes): VNet, subnets, NSGs
2. **AI Services** (10-15 minutes): Azure OpenAI, Cosmos DB
3. **App Services** (5-8 minutes): App Service plan and web app
4. **Private Endpoints** (3-5 minutes): Secure connectivity
5. **Application Deployment** (2-3 minutes): Code deployment and configuration

## 🚀 Quick Start

### Prerequisites
```bash
# Required Azure CLI extensions
az extension add --name azure-firewall
az extension add --name application-insights

# Verify Azure OpenAI access
az cognitiveservices account list-skus --kind OpenAI --location eastus
```

### Deploy the Demo
```bash
# 1. Set up credentials
cp credentials.tfvars.example credentials.tfvars
# Edit credentials.tfvars with your Azure values

# 2. Deploy infrastructure
terraform init
terraform apply -var-file="credentials.tfvars" -var-file="demos/agentic/eol-agentic-demo.tfvars"

# 3. Generate application configuration
cd app/agentic/eol/deploy
./generate-appsettings.sh
```

### Alternative: Use Run Script
```bash
# Automated deployment with the provided script
./run-demo.sh demos/agentic/eol-agentic-demo.tfvars credentials.tfvars
```

## 🔧 Configuration Options

### Azure OpenAI Settings
```hcl
# Model deployments
azure_openai_deployments = [
  {
    name    = "gpt-4"
    model   = "gpt-4"
    version = "1106-Preview"
  },
  {
    name    = "text-embedding-ada-002"
    model   = "text-embedding-ada-002"
    version = "2"
  }
]

# Capacity and scaling
azure_openai_sku_name = "S0"  # Standard tier
```

### Application Configuration
```hcl
# App Service settings
app_service_sku_name = "P1v3"        # Production tier
app_service_sku_tier = "PremiumV3"   # Premium features

# Cosmos DB settings
cosmos_db_throughput = 1000          # RU/s (adjustable)
cosmos_db_consistency = "Session"    # Consistency level
```

### Security Settings
```hcl
# Private endpoint configuration
deploy_private_endpoints = true

# Network isolation
app_subnet_address_prefix = "100.0.2.0/24"
private_endpoint_subnet_prefix = "100.0.3.0/24"

# Firewall rules
agentic_app_allowed_urls = [
  "endoflife.date",
  "api.github.com",
  "*.openai.azure.com"
]
```

## 🔍 Application Features

### Multi-Agent Architecture
```python
# Agent coordination example
class EOLAnalysisOrchestrator:
    def __init__(self):
        self.inventory_agent = InventoryAgent()
        self.eol_lookup_agent = EOLLookupAgent()
        self.analysis_agent = AnalysisAgent()
        self.chat_agent = ChatAgent()
    
    async def analyze_software_eol(self, software_list):
        # Coordinate multiple agents for comprehensive analysis
        inventory_data = await self.inventory_agent.fetch_data()
        eol_data = await self.eol_lookup_agent.check_eol_status(software_list)
        analysis = await self.analysis_agent.generate_report(inventory_data, eol_data)
        return analysis
```

### Chat Interface
- **Natural Language Queries**: Ask about software EOL status
- **Interactive Analysis**: Drill down into specific software packages
- **Report Generation**: Automated EOL compliance reports
- **Recommendation Engine**: Upgrade and migration suggestions

### Data Sources
- **Azure Arc Inventory**: Real-time software inventory from managed servers
- **endoflife.date API**: Comprehensive EOL database
- **Custom Knowledge Base**: Organization-specific software policies
- **Historical Analysis**: Trend analysis and predictions

## 📊 Monitoring & Observability

### Application Insights Integration
```python
# Telemetry and monitoring
from applicationinsights import TelemetryClient

tc = TelemetryClient(instrumentation_key=app_insights_key)
tc.track_event('EOLAnalysisRequested', {'software_count': len(software_list)})
tc.track_metric('AnalysisLatency', analysis_time_ms)
```

### Log Analytics Queries
```kql
// EOL analysis requests
AppRequests
| where Name contains "eol-analysis"
| summarize count() by bin(TimeGenerated, 1h)
| render timechart

// Application performance
AppMetrics
| where Name == "AnalysisLatency"
| summarize avg(Value) by bin(TimeGenerated, 5m)
```

## 🔐 Security Considerations

### Network Security
- **Private VNet**: All resources isolated in dedicated virtual network
- **Private Endpoints**: Secure connectivity to PaaS services
- **Firewall Rules**: Controlled outbound access to required APIs
- **NSG Rules**: Subnet-level traffic controls

### Data Protection
- **Encryption in Transit**: HTTPS/TLS for all communications
- **Encryption at Rest**: Azure-managed keys for data storage
- **Access Controls**: Azure AD integration and RBAC
- **Secret Management**: Azure Key Vault for sensitive data

### Compliance Features
- **Audit Logging**: Comprehensive activity tracking
- **Data Residency**: Configurable data location requirements
- **Access Reviews**: Regular permission auditing
- **Incident Response**: Automated alerting and response procedures

## 🛠️ Troubleshooting

### Common Issues
1. **Azure OpenAI Access**: Ensure subscription is allowlisted
2. **Private Endpoint DNS**: Verify private DNS zone configuration
3. **Firewall Rules**: Check outbound connectivity rules
4. **App Service Deployment**: Monitor deployment logs

### Validation Steps
```bash
# Test application deployment
curl -k https://your-app-service.azurewebsites.net/health

# Verify private endpoint connectivity
nslookup your-openai-service.openai.azure.com

# Check firewall logs
az monitor log-analytics query --workspace workspace-id --analytics-query "AzureDiagnostics | where Category == 'AzureFirewallApplicationRule'"
```

## 📚 Next Steps

### Customization Options
- **Additional AI Models**: Deploy specialized models for domain analysis
- **Custom Agents**: Develop organization-specific analysis agents
- **Integration APIs**: Connect to existing ITSM and CMDB systems
- **Advanced Analytics**: Implement ML models for predictive analysis

### Scaling Considerations
- **Multi-Region Deployment**: Geographic distribution for global organizations
- **High Availability**: Multi-zone deployment for critical workloads
- **Performance Optimization**: Caching and optimization strategies
- **Cost Optimization**: Reserved instances and consumption-based scaling

---

For detailed technical documentation, see the [agentic module README](../../modules/agentic/README.md).
