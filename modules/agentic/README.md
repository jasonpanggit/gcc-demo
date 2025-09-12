# Agentic App Module

This module deploys an AI-powered agentic application with Azure OpenAI integration, Cosmos DB caching, and comprehensive monitoring capabilities.

## Overview

The agentic module provides a complete infrastructure setup for deploying intelligent applications that can interact with Azure OpenAI services through a secure, private network configuration. The module includes:

- **Azure App Service**: Linux-based web application hosting with Python 3.11 runtime
- **Azure OpenAI**: GPT-4 deployment for AI chat functionality
- **Azure Cosmos DB**: High-performance caching for EOL response data (80%+ confidence responses)
- **Application Insights**: Comprehensive application monitoring and logging
- **Private Endpoints**: Secure, private connectivity to Azure services
- **VNet Integration**: Isolated network access for enhanced security
- **Role-Based Access Control**: Managed identity authentication for service-to-service communication

## Architecture

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   App Service   │────│  Private Endpoint │────│  Azure OpenAI   │
│  (VNet Integrated)   │    │   (VNet)         │    │                 │
└─────────────────┘    └──────────────────┘    └─────────────────┘
         │                                              
         │              ┌──────────────────┐    ┌─────────────────┐
         ├──────────────│  Private Endpoint │────│   Cosmos DB     │
         │              │    (VNet)         │    │  (EOL Cache)    │
         │              └──────────────────┘    └─────────────────┘
         │                                              
         │              ┌──────────────────┐    ┌─────────────────┐
         └──────────────│  Private Endpoint │────│  Log Analytics  │
                        │    (VNet)         │    │                 │
                        └──────────────────┘    └─────────────────┘
```

## Key Features

### 🔐 **Security First**
- Private endpoint connectivity for all Azure services
- VNet integration for isolated network access
- Managed identity authentication (no hardcoded secrets)
- Role-based access control with least-privilege principles

### 🚀 **Production Ready**
- Comprehensive error handling and logging
- Application Insights integration for monitoring
- Optimized startup configuration with pinned dependencies
- Always-on functionality for consistent availability
- High-performance caching with Cosmos DB (80%+ confidence responses)

### 🤖 **AI-Powered**
- Azure OpenAI GPT-4 integration for intelligent conversations
- Software inventory analysis and reporting
- Intelligent EOL response caching with confidence-based storage
- Extensible chat interface for various use cases

### 💾 **Smart Caching**
- **Cosmos DB Integration**: Automatic caching of high-confidence EOL responses (≥80%)
- **Performance Optimization**: Significantly reduced response times for repeated queries
- **Intelligent Storage**: Only caches validated, high-quality EOL data
- **Automatic Cleanup**: TTL-based expiration for cache freshness

## Prerequisites

- **VNet Integration**: A dedicated subnet for App Service VNet integration is required
- **Private Endpoints**: A subnet for private endpoints in the target VNet
- **Log Analytics Workspace**: For application monitoring and data queries
- **Azure OpenAI Access**: Appropriate subscription and regional availability

## Usage

```hcl
module "agentic" {
  source = "./modules/agentic"
  
  # Basic Configuration
  project_name         = "myproject"
  environment         = "prod"
  location           = "East US"
  resource_group_name = "rg-myproject-prod"
  
  # Deployment Flags
  deploy_agentic_app = true
  deploy_aoai       = true
  deploy_cosmos_db  = true  # Enable high-performance EOL caching
  
  # Cosmos DB Configuration (Optional)
  cosmos_db_serverless         = true    # Use serverless for cost optimization
  cosmos_db_consistency_level  = "Session"
  cosmos_db_automatic_failover = true
  
  # Network Configuration (REQUIRED)
  nongen_vnet_id                      = "/subscriptions/.../virtualNetworks/vnet-hub"
  nongen_private_endpoint_subnet_id   = "/subscriptions/.../subnets/snet-pe"
  nongen_appsvc_integration_subnet_id = "/subscriptions/.../subnets/snet-integration"
  
  # Log Analytics Integration
  workspace_resource_id = "/subscriptions/.../workspaces/law-monitoring"
  workspace_guid       = "12345678-1234-5678-9012-123456789012"
}
```

## Critical Configuration Notes

### 🚨 **VNet Integration Requirements**

The `nongen_appsvc_integration_subnet_id` parameter is **critical** for proper functionality:

- **Required for Private Endpoint Access**: Without VNet integration, the App Service cannot communicate with Azure services through private endpoints
- **Network Isolation**: Ensures all Azure service communication stays within your private network
- **Firewall Compatibility**: Enables proper routing through hub firewalls and proxy configurations

### 🔑 **Authentication Strategy**

The module implements a dual authentication approach:

1. **Primary**: Managed Identity (recommended for production)
2. **Fallback**: API Key (for development and troubleshooting)

This ensures reliability while maintaining security best practices.

### 📊 **Role Assignments**

The module automatically creates the following role assignments for the App Service managed identity:

- `Cognitive Services OpenAI User`: Access to Azure OpenAI services
- `Log Analytics Reader`: Query access to workspace data
- `Cosmos DB Built-in Data Contributor`: Read/write access to Cosmos DB for caching (when enabled)
  

## Application Features

### Chat Interface

The deployed application provides:

- **Interactive Chat**: AI-powered conversations at `/chat-ui`
- **API Endpoint**: RESTful chat API at `/chat`
- **Software Inventory**: EOL software analysis and reporting
- **Health Monitoring**: Built-in health checks and logging
- **Cache Management**: Cosmos DB cache statistics and management at `/cache/cosmos/stats`

### Monitoring and Observability

- **Application Insights**: Automatic request tracking and error reporting
- **Custom Logging**: Structured logging with correlation IDs
- **Performance Metrics**: Response times, failure rates, and usage analytics
- **Error Tracking**: Detailed exception tracking with stack traces
- **Cache Analytics**: Cosmos DB cache hit rates and performance metrics

## Outputs

The module provides the following outputs for integration with other components:

```hcl
# Application URLs
app_url                 # Main application URL
app_chat_url           # Direct chat interface URL
app_hostname           # Application hostname

# Service Information
app_name               # App Service name
app_id                 # App Service resource ID
app_principal_id       # Managed identity principal ID

# Azure Services
aoai_endpoint          # Azure OpenAI endpoint URL
cosmos_db_endpoint     # Azure Cosmos DB endpoint URL (when enabled)
cosmos_db_name         # Azure Cosmos DB account name (when enabled)
aoai_deployment_name   # OpenAI model deployment name

# Monitoring
app_insights_connection_string  # Application Insights connection
vnet_integration_subnet_id     # VNet integration subnet ID
```

## Cosmos DB Configuration Options

The module provides extensive configuration options for Cosmos DB caching:

```hcl
# Basic Cosmos DB deployment
deploy_cosmos_db = true

# Serverless configuration (recommended for variable workloads)
cosmos_db_serverless = true

# Provisioned throughput configuration
cosmos_db_serverless = false
cosmos_db_throughput = 400  # RU/s

# Consistency and reliability
cosmos_db_consistency_level    = "Session"     # Session, Strong, Eventual, etc.
cosmos_db_automatic_failover   = true          # Enable automatic failover
cosmos_db_geo_location        = "West US"      # Additional region for DR

# Container settings
cosmos_db_database_name = "eol_cache"      # Database name
cosmos_db_container_name = "eol_responses"  # Container name for cached responses
```

## Troubleshooting

### Common Issues

1. **Chat Not Working**: Verify VNet integration and private endpoint connectivity
2. **Authentication Errors**: Check role assignments and managed identity configuration
3. **Startup Failures**: Review Application Insights logs for dependency issues
4. **Network Connectivity**: Ensure proper subnet configuration and NSG rules

### Debugging Steps

1. **Check Application Logs**: Use Application Insights to review error messages
2. **Verify VNet Integration**: Confirm App Service is properly integrated
3. **Test Private Endpoints**: Validate connectivity to Azure services
4. **Review Role Assignments**: Ensure managed identity has required permissions

### Useful Commands

```bash
# Check App Service configuration
az webapp config show --name <app-name> --resource-group <rg-name>

# Review VNet integration
az webapp vnet-integration list --name <app-name> --resource-group <rg-name>

# Test private endpoint connectivity
az network private-endpoint list --resource-group <rg-name>
```

## Version History

- **v1.0**: Initial release with basic AI chat functionality
- **v1.1**: Added VNet integration and private endpoint support
- **v1.2**: Enhanced role assignments and authentication
- **v1.3**: Production optimizations and monitoring improvements

## Contributing

When modifying this module:

1. **Test VNet Integration**: Always verify private endpoint connectivity
2. **Update Role Assignments**: Ensure new Azure services have proper permissions
3. **Document Changes**: Update this README with any configuration changes
4. **Validate Outputs**: Test all module outputs in dependent configurations

## Security Considerations

- **No Hardcoded Secrets**: All authentication uses managed identities or Key Vault references
- **Private Network Only**: All Azure service communication uses private endpoints
- **Least Privilege**: Role assignments follow minimal required permissions
- **Monitoring**: Comprehensive logging for security auditing

## Support

For issues related to this module:

1. Check Application Insights for application-level errors
2. Review Terraform plan output for configuration issues
3. Validate network connectivity and role assignments
4. Consult Azure service health for platform issues
