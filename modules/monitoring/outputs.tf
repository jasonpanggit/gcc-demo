# ============================================================================
# MONITORING MODULE OUTPUTS
# ============================================================================

output "log_analytics_workspace_id" {
  description = "The ID of the Log Analytics Workspace"
  value       = length(azurerm_log_analytics_workspace.law_hub) > 0 ? azurerm_log_analytics_workspace.law_hub[0].id : null
}

output "log_analytics_workspace_guid" {
  description = "The workspace ID (GUID) of the Log Analytics Workspace"
  value       = length(azurerm_log_analytics_workspace.law_hub) > 0 ? azurerm_log_analytics_workspace.law_hub[0].workspace_id : null
}

output "log_analytics_workspace_name" {
  description = "The name of the Log Analytics Workspace"
  value       = length(azurerm_log_analytics_workspace.law_hub) > 0 ? azurerm_log_analytics_workspace.law_hub[0].name : null
}

output "data_collection_endpoint_id" {
  description = "The ID of the Data Collection Endpoint"
  value       = length(azurerm_monitor_data_collection_endpoint.dce_hub) > 0 ? azurerm_monitor_data_collection_endpoint.dce_hub[0].id : null
}

output "monitor_private_link_scope_id" {
  description = "The ID of the Azure Monitor Private Link Scope"
  value       = length(azurerm_monitor_private_link_scope.ampls_hub) > 0 ? azurerm_monitor_private_link_scope.ampls_hub[0].id : null
}

output "monitor_private_dns_zone_ids" {
  description = "The IDs of the Azure Monitor private DNS zones"
  value = {
    monitor  = length(azurerm_private_dns_zone.pdz_monitor) > 0 ? azurerm_private_dns_zone.pdz_monitor[0].id : null
    oms      = length(azurerm_private_dns_zone.pdz_oms) > 0 ? azurerm_private_dns_zone.pdz_oms[0].id : null
    ods      = length(azurerm_private_dns_zone.pdz_ods) > 0 ? azurerm_private_dns_zone.pdz_ods[0].id : null
    agentsvc = length(azurerm_private_dns_zone.pdz_agentsvc) > 0 ? azurerm_private_dns_zone.pdz_agentsvc[0].id : null
    blob     = length(azurerm_private_dns_zone.pdz_blob) > 0 ? azurerm_private_dns_zone.pdz_blob[0].id : null
  }
}

output "monitor_private_endpoint_id" {
  description = "The ID of the Azure Monitor private endpoint"
  value       = length(azurerm_private_endpoint.pe_monitor) > 0 ? azurerm_private_endpoint.pe_monitor[0].id : null
}
