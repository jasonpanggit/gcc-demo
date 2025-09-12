# ============================================================================
# MAIN TERRAFORM OUTPUTS
# ============================================================================

# Azure Context Information
output "subscription_id" {
  description = "Current Azure subscription ID"
  value       = data.azurerm_client_config.current.subscription_id
}

output "tenant_id" {
  description = "Current Azure tenant ID"
  value       = data.azurerm_client_config.current.tenant_id
}

# Infrastructure Configuration
output "location" {
  description = "Primary Azure region"
  value       = var.location
}

output "environment" {
  description = "Environment name"
  value       = var.environment
}

output "project_name" {
  description = "Project name"
  value       = var.project_name
}

# Resource Groups
output "hub_resource_group_name" {
  description = "Hub resource group name"
  value       = azurerm_resource_group.rg_hub.name
}

output "hub_resource_group_id" {
  description = "Hub resource group ID"
  value       = azurerm_resource_group.rg_hub.id
}

# Monitoring Resources
output "log_analytics_workspace_name" {
  description = "Log Analytics workspace name"
  value       = var.deploy_azure_monitor_private_link_scope ? module.monitoring[0].log_analytics_workspace_name : null
}

output "log_analytics_workspace_id" {
  description = "Log Analytics workspace ID"
  value       = var.deploy_azure_monitor_private_link_scope ? module.monitoring[0].log_analytics_workspace_id : null
}

output "log_analytics_workspace_guid" {
  description = "Log Analytics workspace GUID (for application configuration)"
  value       = var.deploy_azure_monitor_private_link_scope ? module.monitoring[0].log_analytics_workspace_guid : null
}

# Arc Configuration (if deployed)
output "arc_private_link_scope_id" {
  description = "Azure Arc private link scope ID"
  value       = var.deploy_arc_private_link_scope ? module.arc[0].private_link_scope_id : null
}

output "arc_service_principal_client_id" {
  description = "Azure Arc service principal client ID"
  value       = var.deploy_arc_private_link_scope ? module.arc[0].service_principal_client_id : null
  sensitive   = true
}

output "arc_service_principal_secret" {
  description = "Azure Arc service principal client secret"
  value       = var.deploy_arc_private_link_scope ? module.arc[0].service_principal_secret : null
  sensitive   = true
}

# Agentic App Configuration (if deployed)
output "agentic_app_url" {
  description = "Agentic application URL"
  value       = var.deploy_agentic_app ? module.agentic[0].app_url : null
}

output "agentic_app_chat_url" {
  description = "Agentic application chat interface URL"
  value       = var.deploy_agentic_app ? module.agentic[0].app_chat_url : null
}

output "agentic_app_hostname" {
  description = "Agentic application hostname"
  value       = var.deploy_agentic_app ? module.agentic[0].app_hostname : null
}

output "agentic_app_principal_id" {
  description = "Agentic application managed identity principal ID"
  value       = var.deploy_agentic_app ? module.agentic[0].app_principal_id : null
}

output "agentic_aoai_endpoint" {
  description = "Azure OpenAI endpoint URL"
  value       = var.deploy_agentic_app && var.deploy_aoai ? module.agentic[0].aoai_endpoint : null
}

output "agentic_aoai_deployment_name" {
  description = "Azure OpenAI deployment name"
  value       = var.deploy_agentic_app && var.deploy_aoai ? module.agentic[0].aoai_deployment_name : null
}

output "agentic_app_service_name" {
  description = "Agentic application service name"
  value       = var.deploy_agentic_app ? module.agentic[0].app_service_name : null
}

output "agentic_cosmos_db_endpoint" {
  description = "Agentic Cosmos DB endpoint"
  value       = var.deploy_agentic_app && var.deploy_cosmos_db ? module.agentic[0].cosmos_db_endpoint : null
}

output "agentic_cosmos_db_database_name" {
  description = "Agentic Cosmos DB database name"
  value       = var.deploy_agentic_app && var.deploy_cosmos_db ? module.agentic[0].cosmos_db_database_name : null
}

output "agentic_cosmos_db_container_name" {
  description = "Agentic Cosmos DB container name"
  value       = var.deploy_agentic_app && var.deploy_cosmos_db ? module.agentic[0].cosmos_db_container_name : null
}

# EOL Solution Configuration
output "eol_solution_config" {
  description = "Configuration parameters for EOL solution deployment"
  value = {
    subscription_id     = data.azurerm_client_config.current.subscription_id
    resource_group_name = azurerm_resource_group.rg_hub.name
    workspace_name      = var.deploy_azure_monitor_private_link_scope ? module.monitoring[0].log_analytics_workspace_name : null
    location            = var.location
    environment         = var.environment
    project_name        = var.project_name
  }
}