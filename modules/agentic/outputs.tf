# ============================================================================
# AGENTIC APP MODULE OUTPUTS
# ============================================================================

output "app_service_url" {
  description = "Primary URL of the web app"
  value       = var.deploy_agentic_app ? azurerm_linux_web_app.app[0].default_hostname : null
}

# Alias for backwards compatibility
output "app_url" {
  description = "Primary URL of the web app (alias for app_service_url)"
  value       = var.deploy_agentic_app ? azurerm_linux_web_app.app[0].default_hostname : null
}

# Alias for backwards compatibility  
output "app_hostname" {
  description = "Hostname of the web app (alias for app_service_url)"
  value       = var.deploy_agentic_app ? azurerm_linux_web_app.app[0].default_hostname : null
}

output "app_service_id" {
  description = "ID of the web app"
  value       = var.deploy_agentic_app ? azurerm_linux_web_app.app[0].id : null
}


output "aoai_endpoint" {
  description = "Azure OpenAI endpoint"
  value       = var.deploy_agentic_app && var.deploy_aoai ? azurerm_cognitive_account.aoai[0].endpoint : null
}

# ============================================================================
# COSMOS DB OUTPUTS
# ============================================================================

output "cosmos_db_endpoint" {
  description = "Azure Cosmos DB endpoint"
  value       = var.deploy_agentic_app && var.deploy_cosmos_db ? azurerm_cosmosdb_account.cosmos[0].endpoint : null
}

output "cosmos_db_name" {
  description = "Azure Cosmos DB account name"
  value       = var.deploy_agentic_app && var.deploy_cosmos_db ? azurerm_cosmosdb_account.cosmos[0].name : null
}

output "cosmos_db_database_name" {
  description = "Azure Cosmos DB database name"
  value       = var.deploy_agentic_app && var.deploy_cosmos_db ? var.cosmos_db_database_name : null
}

output "cosmos_db_container_name" {
  description = "Azure Cosmos DB container name"
  value       = var.deploy_agentic_app && var.deploy_cosmos_db ? var.cosmos_db_container_name : null
}

output "cosmos_db_id" {
  description = "Azure Cosmos DB account ID"
  value       = var.deploy_agentic_app && var.deploy_cosmos_db ? azurerm_cosmosdb_account.cosmos[0].id : null
}



output "app_service_name" {
  description = "Name of the web app"
  value       = var.deploy_agentic_app ? azurerm_linux_web_app.app[0].name : null
}

output "app_service_principal_id" {
  description = "Principal ID of the web app's managed identity"
  value       = var.deploy_agentic_app ? azurerm_linux_web_app.app[0].identity[0].principal_id : null
}

# Alias for backwards compatibility
output "app_principal_id" {
  description = "Principal ID of the web app's managed identity (alias)"
  value       = var.deploy_agentic_app ? azurerm_linux_web_app.app[0].identity[0].principal_id : null
}

output "application_insights_connection_string" {
  description = "Application Insights connection string"
  value       = var.deploy_agentic_app ? azurerm_application_insights.appi[0].connection_string : null
  sensitive   = true
}

output "aoai_deployment_name" {
  description = "Azure OpenAI deployment name"
  value       = var.deploy_agentic_app && var.deploy_aoai ? var.aoai_deployment_name : null
}

output "vnet_integration_subnet_id" {
  description = "Subnet ID used for VNet integration"
  value       = var.deploy_agentic_app ? coalesce(var.nongen_appsvc_integration_subnet_id, var.nongen_app_subnet_id) : null
}

output "app_chat_url" {
  description = "URL for the AI chat interface"
  value       = var.deploy_agentic_app ? "https://${azurerm_linux_web_app.app[0].default_hostname}/chat-ui" : null
}

# ============================================================================
# AZURE CONTAINER REGISTRY OUTPUTS
# ============================================================================

output "acr_name" {
  description = "Azure Container Registry name"
  value       = var.deploy_agentic_app && var.deploy_acr ? azurerm_container_registry.acr[0].name : null
}

output "acr_login_server" {
  description = "Azure Container Registry login server URL"
  value       = var.deploy_agentic_app && var.deploy_acr ? azurerm_container_registry.acr[0].login_server : null
}

output "acr_admin_username" {
  description = "Azure Container Registry admin username"
  value       = var.deploy_agentic_app && var.deploy_acr && var.acr_admin_enabled ? azurerm_container_registry.acr[0].admin_username : null
}

output "acr_admin_password" {
  description = "Azure Container Registry admin password"
  value       = var.deploy_agentic_app && var.deploy_acr && var.acr_admin_enabled ? azurerm_container_registry.acr[0].admin_password : null
  sensitive   = true
}

# ============================================================================
# BING SEARCH API OUTPUTS - DEPRECATED
# ============================================================================

output "bing_search_name" {
  description = "Bing Search Cognitive Services account name (DEPRECATED)"
  value       = var.deploy_agentic_app && var.deploy_bing_search ? azurerm_cognitive_account.bing_search[0].name : null
}

output "bing_search_endpoint" {
  description = "Bing Search Cognitive Services endpoint (DEPRECATED)"
  value       = var.deploy_agentic_app && var.deploy_bing_search ? azurerm_cognitive_account.bing_search[0].endpoint : null
}

# ============================================================================
# AZURE AI AGENT SERVICE OUTPUTS
# ============================================================================

output "azure_ai_foundry_name" {
  description = "Azure AI Foundry service name"
  value       = var.deploy_agentic_app && var.deploy_azure_ai_agent ? azurerm_cognitive_account.ai_foundry[0].name : null
}

output "azure_ai_foundry_endpoint" {
  description = "Azure AI Foundry service endpoint"
  value       = var.deploy_agentic_app && var.deploy_azure_ai_agent ? azurerm_cognitive_account.ai_foundry[0].endpoint : null
}

output "azure_ai_foundry_id" {
  description = "Azure AI Foundry service resource ID"
  value       = var.deploy_agentic_app && var.deploy_azure_ai_agent ? azurerm_cognitive_account.ai_foundry[0].id : null
}

# ============================================================================
# AZURE AI SRE AGENT OUTPUTS
# ============================================================================

output "azure_ai_sre_agent_name" {
  description = "Azure AI SRE agent name (gccsreagent)"
  value       = var.azure_ai_sre_agent_name
}

output "azure_ai_sre_agent_id" {
  description = "Azure AI SRE agent resource ID"
  value       = var.azure_ai_sre_agent_id
}
