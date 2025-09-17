# EOL Agentic Application Demo

This demo deploys a complete End-of-Life (EOL) agentic application with all required infrastructure components including Azure Container Registry and Bing Search API for enhanced web search capabilities.

## 🎯 **What This Demo Deploys**

### **Core Infrastructure**
- **Hub Virtual Network** with Azure Firewall
- **Non-Gen Virtual Network** with subnets for application components
- **Log Analytics Workspace** for monitoring and logging

### **Agentic Application Components**
- **App Service Plan** (Linux, P1v3) for hosting the Python EOL application
- **Azure OpenAI** account with GPT-4o-mini deployment for AI capabilities
- **Azure Cosmos DB** (serverless) for EOL response caching
- **Application Insights** for telemetry and performance monitoring

### **Enhanced Search Capabilities**
- **Azure Container Registry** for storing container images
- **Bing Search API** (Cognitive Services) for reliable web search without browser dependencies

## 🚀 **Key Features**

### **Intelligent EOL Analysis**
- Multi-agent system with specialized agents for different technology stacks
- Static knowledge base with comprehensive EOL data for major software products
- Dynamic web search using Bing Search API as fallback

### **Reliable Search Architecture**
- **Primary**: Static EOL knowledge base (fast, reliable)
- **Secondary**: Bing Search API (no browser dependencies, works in containers)
- **Fallback**: WebSurfer with Playwright (legacy browser automation)

### **Production-Ready Infrastructure**
- Container-based deployment with Azure Container Registry
- Comprehensive monitoring and logging
- Secure networking with Azure Firewall
- Scalable serverless Cosmos DB for caching

## 📋 **Prerequisites**

1. **Azure Subscription** with sufficient permissions
2. **Terraform** >= 1.0
3. **Azure CLI** authenticated to your subscription
4. **Service Principal** with appropriate RBAC permissions

## 🛠️ **Deployment Instructions**

### 1. **Configure Variables**
Update the `terraform.tfvars` file with your specific values:

```hcl
# Required - Update these values
subscription_id = "your-subscription-id"
tenant_id      = "your-tenant-id"
client_id      = "your-service-principal-app-id"
client_secret  = "your-service-principal-secret"

# Optional - Customize as needed
project_name = "gcc-demo"
environment  = "prod"
location     = "Australia East"
```

### 2. **Deploy Infrastructure**
```bash
# Initialize Terraform
terraform init

# Plan deployment
terraform plan -var-file="demos/eol-agentic/eol-agentic-demo.tfvars"

# Apply deployment
terraform apply -var-file="demos/eol-agentic/eol-agentic-demo.tfvars"
```

### 3. **Generate Application Settings**
```bash
# Generate appsettings.json from Terraform outputs
cd app/agentic/eol/deploy
./generate-appsettings.sh
```

### 4. **Deploy Application**
```bash
# Build and deploy the container
./build-container.sh
./deploy-container.sh
```

## 📊 **Infrastructure Components**

| Component | SKU/Size | Purpose |
|-----------|----------|---------|
| App Service Plan | P1v3 | Host Python EOL application |
| Azure OpenAI | Standard | GPT-4o-mini for AI capabilities |
| Cosmos DB | Serverless | Cache EOL responses |
| Container Registry | Basic | Store container images |
| Bing Search API | S0 | Web search capabilities |
| Azure Firewall | Standard | Network security |

## 🔑 **Key Outputs**

After deployment, you'll get these important outputs:

```bash
# Application URLs
agentic_app_url                = "your-app.azurewebsites.net"
agentic_app_chat_url          = "https://your-app.azurewebsites.net/chat-ui"

# Container Registry
agentic_acr_name              = "acrggcdemo"
agentic_acr_login_server      = "acrggcdemo.azurecr.io"

# Search API (sensitive - use terraform output)
agentic_bing_search_endpoint  = "https://australiaeast.api.cognitive.microsoft.com/"
```

## 💰 **Cost Considerations**

**Estimated Monthly Cost (Australia East):**
- App Service Plan (P1v3): ~$73 AUD
- Azure OpenAI (GPT-4o-mini): ~$20 AUD (usage-based)
- Cosmos DB (Serverless): ~$5 AUD (usage-based)
- Container Registry (Basic): ~$6 AUD
- Bing Search API (S0): ~$375 AUD (3 TPS, 1000 TPM)
- Azure Firewall: ~$365 AUD
- **Total: ~$844 AUD/month**

## 🔒 **Security Features**

- **Network Isolation**: All resources deployed in private VNets
- **Azure Firewall**: Controls outbound traffic
- **Managed Identity**: Secure access to Azure resources
- **Private Endpoints**: Optional for enhanced security
- **Key Vault Integration**: Secure secret management

## 🐛 **Troubleshooting**

### Common Issues:

1. **Deployment Fails**
   - Verify service principal permissions
   - Check resource name conflicts
   - Ensure sufficient quota in target region

2. **Application Not Starting**
   - Check Application Insights logs
   - Verify environment variables in App Service
   - Review container deployment logs

3. **Search Not Working**
   - Confirm Bing Search API key is configured
   - Check network connectivity
   - Review application logs for API errors

## 📚 **Additional Resources**

- [Azure OpenAI Documentation](https://docs.microsoft.com/azure/cognitive-services/openai/)
- [Azure Cosmos DB Documentation](https://docs.microsoft.com/azure/cosmos-db/)
- [Bing Search API Documentation](https://docs.microsoft.com/azure/cognitive-services/bing-web-search/)
- [Azure Container Registry Documentation](https://docs.microsoft.com/azure/container-registry/)

## 🧹 **Cleanup**

To remove all deployed resources:

```bash
terraform destroy -var-file="demos/eol-agentic/eol-agentic-demo.tfvars"
```

**⚠️ Warning**: This will permanently delete all resources and data. Ensure you have backups if needed.