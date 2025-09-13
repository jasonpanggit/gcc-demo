# Monitoring Module

This module manages Azure Monitor, Log Analytics, and private link scope resources for centralized monitoring and observability across the infrastructure.

## Features

- **Log Analytics Workspace**: Centralized logging and analytics
- **Azure Monitor Private Link Scope**: Secure private connectivity to Azure Monitor
- **Data Collection Endpoints**: Secure data ingestion points
- **Application Insights**: Application performance monitoring
- **Private Endpoints**: Private connectivity to monitoring services
- **Data Collection Rules**: Structured data collection configuration
- **Retention Policies**: Configurable log retention periods

## Architecture

### Log Analytics Workspace
- **Purpose**: Central repository for logs and metrics
- **SKUs**: Free, PerGB2018, PerNode, Premium, Standalone, Unlimited
- **Retention**: Configurable retention periods (30-730 days)
- **Ingestion**: Support for multiple data sources

### Azure Monitor Private Link Scope (AMPLS)
- **Purpose**: Private connectivity to Azure Monitor services
- **Access Modes**: Private-only, open, or mixed access
- **Components**: Log Analytics, Application Insights, Data Collection Endpoints
- **Security**: Network isolation for monitoring data

### Data Collection Endpoints
- **Purpose**: Secure ingestion points for monitoring data
- **Types**: Windows and Linux endpoints
- **Network**: Private endpoint connectivity
- **Authentication**: Azure AD and managed identity support

## Usage

```hcl
module "monitoring" {
  source = "./modules/monitoring"
  
  project_name        = var.project_name
  environment         = var.environment
  location            = var.location
  resource_group_name = azurerm_resource_group.main.name
  
  # Core Configuration
  deploy_hub_vnet                             = var.deploy_hub_vnet
  deploy_azure_monitor_private_link_scope     = var.deploy_azure_monitor_private_link_scope
  
  # Log Analytics Configuration
  log_analytics_workspace_sku                 = var.log_analytics_workspace_sku
  log_analytics_workspace_retention_days      = var.log_analytics_workspace_retention_days
  
  # Private Link Configuration
  azure_monitor_ingestion_access_mode         = var.azure_monitor_ingestion_access_mode
  azure_monitor_query_access_mode             = var.azure_monitor_query_access_mode
  
  # Application Insights
  deploy_application_insights                 = var.deploy_application_insights
  application_insights_type                   = var.application_insights_type
  
  # Networking
  hub_vnet_id                                = module.networking.hub_vnet_id
  monitoring_subnet_id                       = module.networking.monitoring_subnet_id
  
  tags = var.tags
}
```

## Configuration Options

### Log Analytics Workspace
```hcl
# Workspace SKU options
log_analytics_workspace_sku = "PerGB2018"  # Pay-per-GB (most common)
log_analytics_workspace_sku = "Free"       # 500MB/day limit
log_analytics_workspace_sku = "Premium"    # Enhanced features

# Retention configuration
log_analytics_workspace_retention_days = 30   # Minimum retention
log_analytics_workspace_retention_days = 90   # Standard retention
log_analytics_workspace_retention_days = 365  # Long-term retention
```

### Private Link Scope Access Modes
```hcl
# Ingestion access modes
azure_monitor_ingestion_access_mode = "Private"    # Private-only access
azure_monitor_ingestion_access_mode = "Open"       # Public access allowed
azure_monitor_ingestion_access_mode = "PrivateOnly" # Strict private access

# Query access modes  
azure_monitor_query_access_mode = "Private"        # Private-only queries
azure_monitor_query_access_mode = "Open"           # Public queries allowed
```

### Application Insights
```hcl
# Enable Application Insights
deploy_application_insights = true
application_insights_type = "web"                  # Web applications
application_insights_type = "other"                # Other application types
```

## Private Endpoint Configuration

### Monitor Private Endpoint
```hcl
# Private endpoint for Azure Monitor
resource "azurerm_private_endpoint" "pe_monitor" {
  name                = "pe-monitor-${var.project_name}-${var.environment}"
  location            = var.location
  resource_group_name = var.resource_group_name
  subnet_id           = var.monitoring_subnet_id

  private_service_connection {
    name                           = "psc-monitor"
    private_connection_resource_id = azurerm_monitor_private_link_scope.ampls_hub[0].id
    subresource_names              = ["azuremonitor"]
    is_manual_connection           = false
  }
}
```

## Data Collection Rules

### Windows Data Collection
```hcl
# Data Collection Rule for Windows servers
resource "azurerm_monitor_data_collection_rule" "dcr_windows" {
  name                = "dcr-windows-${var.project_name}-${var.environment}"
  resource_group_name = var.resource_group_name
  location            = var.location

  destinations {
    log_analytics {
      workspace_resource_id = azurerm_log_analytics_workspace.law_hub[0].id
      name                  = "destination-log"
    }
  }

  data_flow {
    streams      = ["Microsoft-Event", "Microsoft-WindowsEvent", "Microsoft-Perf"]
    destinations = ["destination-log"]
  }

  data_sources {
    windows_event_log {
      streams = ["Microsoft-WindowsEvent"]
      name    = "eventLogsDataSource"
      x_path_queries = [
        "Application!*[System[(Level=1 or Level=2 or Level=3)]]",
        "System!*[System[(Level=1 or Level=2 or Level=3)]]"
      ]
    }

    performance_counter {
      streams                       = ["Microsoft-Perf"]
      name                         = "perfCountersDataSource"
      sampling_frequency_in_seconds = 60
      counter_specifiers = [
        "\\Processor(_Total)\\% Processor Time",
        "\\Memory\\Available Bytes",
        "\\Network Interface(*)\\Bytes Total/sec"
      ]
    }
  }
}
```

## Outputs

| Name | Description |
|------|-------------|
| `log_analytics_workspace_id` | Resource ID of the Log Analytics workspace |
| `log_analytics_workspace_guid` | GUID of the Log Analytics workspace |
| `log_analytics_workspace_primary_shared_key` | Primary shared key for workspace access |
| `azure_monitor_private_link_scope_id` | Resource ID of the private link scope |
| `data_collection_endpoint_id` | Resource ID of the data collection endpoint |
| `application_insights_id` | Resource ID of Application Insights |
| `application_insights_instrumentation_key` | Instrumentation key for Application Insights |
| `monitor_private_endpoint_id` | Resource ID of the monitor private endpoint |

## Integration Examples

### VM Monitoring Agent
```hcl
# Azure Monitor Agent extension
resource "azurerm_virtual_machine_extension" "ama" {
  name                 = "AzureMonitorWindowsAgent"
  virtual_machine_id   = azurerm_windows_virtual_machine.vm.id
  publisher            = "Microsoft.Azure.Monitor"
  type                 = "AzureMonitorWindowsAgent"
  type_handler_version = "1.0"
  auto_upgrade_minor_version = true

  settings = jsonencode({
    workspaceId = module.monitoring.log_analytics_workspace_guid
  })

  protected_settings = jsonencode({
    workspaceKey = module.monitoring.log_analytics_workspace_primary_shared_key
  })
}
```

### Application Monitoring
```hcl
# Application settings for App Service
app_settings = {
  "APPINSIGHTS_INSTRUMENTATIONKEY"        = module.monitoring.application_insights_instrumentation_key
  "APPLICATIONINSIGHTS_CONNECTION_STRING" = module.monitoring.application_insights_connection_string
  "ApplicationInsightsAgent_EXTENSION_VERSION" = "~3"
}
```

## Dependencies

- **Networking Module**: Requires monitoring subnet for private endpoints
- **Azure Resource Group**: Target resource group
- **Virtual Network**: For private endpoint connectivity

## Cost Considerations

### Log Analytics Workspace
- **Free Tier**: 500MB/day included, then $2.30/GB
- **PerGB2018**: $2.30/GB ingested
- **Retention**: $0.10/GB per month for retention beyond 31 days

### Application Insights
- **Data Ingestion**: $2.30/GB beyond 5GB/month free tier
- **Data Retention**: $0.25/GB per month beyond 90 days

### Private Link Scope
- **Private Endpoints**: $0.045/hour per endpoint (~$32/month)
- **Data Processing**: $0.045 per GB processed

### Cost Optimization
```hcl
# Use shorter retention for cost savings
log_analytics_workspace_retention_days = 30  # vs 365 days

# Use Free tier for small environments (500MB/day limit)
log_analytics_workspace_sku = "Free"

# Disable Application Insights if not needed
deploy_application_insights = false
```

### Sample Monthly Costs
- **Basic Monitoring**: ~$50-100 (1GB/day ingestion)
- **Medium Environment**: ~$200-400 (5GB/day ingestion)
- **Enterprise**: ~$500+ (10GB+/day ingestion)

Estimated monthly cost: **$50-500+** depending on data volume and retention
