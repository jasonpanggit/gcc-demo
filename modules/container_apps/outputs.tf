# ============================================================================
# CONTAINER APPS MODULE OUTPUTS
# ============================================================================

output "container_app_id" {
  description = "Container App resource ID"
  value       = var.deploy_container_apps ? azurerm_container_app.app[0].id : null
}

output "container_app_fqdn" {
  description = "Container App FQDN"
  value       = var.deploy_container_apps ? azurerm_container_app.app[0].ingress[0].fqdn : null
}

output "container_app_url" {
  description = "Container App URL"
  value       = var.deploy_container_apps ? "https://${azurerm_container_app.app[0].ingress[0].fqdn}" : null
}

output "container_app_identity_principal_id" {
  description = "Container App managed identity principal ID"
  value       = var.deploy_container_apps ? azurerm_container_app.app[0].identity[0].principal_id : null
}

output "container_app_environment_id" {
  description = "Container Apps Environment ID"
  value       = var.deploy_container_apps ? azurerm_container_app_environment.cae[0].id : null
}

output "container_app_environment_static_ip" {
  description = "Container Apps Environment static IP address"
  value       = var.deploy_container_apps ? azurerm_container_app_environment.cae[0].static_ip_address : null
}

output "acr_id" {
  description = "Azure Container Registry ID"
  value       = var.deploy_container_apps && var.deploy_acr ? azurerm_container_registry.acr[0].id : null
}

output "acr_login_server" {
  description = "Azure Container Registry login server"
  value       = var.deploy_container_apps && var.deploy_acr ? azurerm_container_registry.acr[0].login_server : null
}

output "acr_admin_username" {
  description = "Azure Container Registry admin username"
  value       = var.deploy_container_apps && var.deploy_acr && var.acr_admin_enabled ? azurerm_container_registry.acr[0].admin_username : null
}

output "acr_admin_password" {
  description = "Azure Container Registry admin password"
  value       = var.deploy_container_apps && var.deploy_acr && var.acr_admin_enabled ? azurerm_container_registry.acr[0].admin_password : null
  sensitive   = true
}

output "aoai_id" {
  description = "Azure OpenAI resource ID"
  value       = var.deploy_container_apps && var.deploy_aoai ? azurerm_cognitive_account.aoai[0].id : null
}

output "aoai_endpoint" {
  description = "Azure OpenAI endpoint"
  value       = var.deploy_container_apps && var.deploy_aoai ? azurerm_cognitive_account.aoai[0].endpoint : null
}

output "cosmos_db_id" {
  description = "Cosmos DB account ID"
  value       = var.deploy_container_apps && var.deploy_cosmos_db ? azurerm_cosmosdb_account.cosmos[0].id : null
}

output "cosmos_db_endpoint" {
  description = "Cosmos DB endpoint"
  value       = var.deploy_container_apps && var.deploy_cosmos_db ? azurerm_cosmosdb_account.cosmos[0].endpoint : null
}

output "ai_project_id" {
  description = "Azure AI Foundry project ID"
  value       = var.deploy_container_apps && var.deploy_ai_foundry ? azurerm_cognitive_account.ai_project[0].id : null
}

output "ai_project_endpoint" {
  description = "Azure AI Foundry project endpoint"
  value       = var.deploy_container_apps && var.deploy_ai_foundry ? azurerm_cognitive_account.ai_project[0].endpoint : null
}

output "application_insights_id" {
  description = "Application Insights resource ID"
  value       = var.deploy_container_apps ? azurerm_application_insights.appi[0].id : null
}

output "application_insights_instrumentation_key" {
  description = "Application Insights instrumentation key"
  value       = var.deploy_container_apps ? azurerm_application_insights.appi[0].instrumentation_key : null
  sensitive   = true
}

output "application_insights_connection_string" {
  description = "Application Insights connection string"
  value       = var.deploy_container_apps ? azurerm_application_insights.appi[0].connection_string : null
  sensitive   = true
}

# ============================================================================
# FRIENDLY OUTPUT ALIASES (for compatibility with main.tf unified outputs)
# ============================================================================

output "container_app_name" {
  description = "Container App name (alias)"
  value       = var.deploy_container_apps ? azurerm_container_app.app[0].name : null
}

output "container_app_environment_name" {
  description = "Container Apps Environment name (alias)"
  value       = var.deploy_container_apps ? azurerm_container_app_environment.cae[0].name : null
}

output "fqdn" {
  description = "Container App FQDN (alias)"
  value       = var.deploy_container_apps ? azurerm_container_app.app[0].ingress[0].fqdn : null
}

output "app_url" {
  description = "Container App URL (alias)"
  value       = var.deploy_container_apps ? "https://${azurerm_container_app.app[0].ingress[0].fqdn}" : null
}

output "app_principal_id" {
  description = "Container App managed identity principal ID (alias)"
  value       = var.deploy_container_apps ? azurerm_container_app.app[0].identity[0].principal_id : null
}

output "acr_name" {
  description = "Azure Container Registry name (alias)"
  value       = var.deploy_container_apps && var.deploy_acr ? azurerm_container_registry.acr[0].name : null
}

output "aoai_deployment_name" {
  description = "Azure OpenAI deployment name (alias)"
  value       = var.deploy_container_apps && var.deploy_aoai ? var.aoai_deployment_name : null
}

output "cosmos_db_database_name" {
  description = "Cosmos DB database name (alias)"
  value       = var.deploy_container_apps && var.deploy_cosmos_db ? var.cosmos_db_database_name : null
}

output "cosmos_db_container_name" {
  description = "Cosmos DB container name (alias)"
  value       = var.deploy_container_apps && var.deploy_cosmos_db ? var.cosmos_db_container_name : null
}
