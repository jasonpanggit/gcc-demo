# ============================================================================
# STORAGE MODULE OUTPUTS
# ============================================================================

output "storage_account_id" {
  description = "The ID of the storage account"
  value       = var.deploy_script_storage ? azurerm_storage_account.sa_scripts[0].id : null
}

output "storage_account_name" {
  description = "The name of the storage account"
  value       = var.deploy_script_storage ? azurerm_storage_account.sa_scripts[0].name : null
}

output "storage_container_name" {
  description = "The name of the storage container"
  value       = var.deploy_script_storage && (var.onprem_windows_arc_onboarding || var.onprem_windows_vpn_setup) ? azurerm_storage_container.sc_scripts[0].name : null
}

output "scripts_sas_token" {
  description = "SAS token for script access"
  value       = var.deploy_script_storage && (var.onprem_windows_arc_onboarding || var.onprem_windows_vpn_setup) ? data.azurerm_storage_account_blob_container_sas.scripts[0].sas : null
  sensitive   = true
}

output "storage_account_primary_connection_string" {
  description = "Primary connection string for the storage account"
  value       = var.deploy_script_storage ? azurerm_storage_account.sa_scripts[0].primary_connection_string : null
  sensitive   = true
}
