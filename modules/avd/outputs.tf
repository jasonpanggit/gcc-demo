# ============================================================================
# AVD WORKSPACE OUTPUTS
# ============================================================================

output "workspace_id" {
  description = "ID of the Azure Virtual Desktop workspace"
  value       = azurerm_virtual_desktop_workspace.main.id
}

output "workspace_name" {
  description = "Name of the Azure Virtual Desktop workspace"
  value       = azurerm_virtual_desktop_workspace.main.name
}

# ============================================================================
# AVD HOST POOL OUTPUTS
# ============================================================================

output "host_pool_id" {
  description = "ID of the Azure Virtual Desktop host pool"
  value       = azurerm_virtual_desktop_host_pool.main.id
}

output "host_pool_name" {
  description = "Name of the Azure Virtual Desktop host pool"
  value       = azurerm_virtual_desktop_host_pool.main.name
}

output "host_pool_token" {
  description = "Registration token for the host pool"
  value       = azurerm_virtual_desktop_host_pool_registration_info.main.token
  sensitive   = true
}

# ============================================================================
# AVD APPLICATION GROUP OUTPUTS
# ============================================================================

output "application_group_id" {
  description = "ID of the Azure Virtual Desktop application group"
  value       = azurerm_virtual_desktop_application_group.main.id
}

output "application_group_name" {
  description = "Name of the Azure Virtual Desktop application group"
  value       = azurerm_virtual_desktop_application_group.main.name
}

# ============================================================================
# SESSION HOST OUTPUTS
# ============================================================================

output "session_host_subnet_id" {
  description = "ID of the session host subnet"
  value       = azurerm_subnet.session_hosts.id
}

output "session_host_vm_ids" {
  description = "IDs of the session host virtual machines"
  value       = azurerm_windows_virtual_machine.session_hosts[*].id
}

output "session_host_vm_names" {
  description = "Names of the session host virtual machines"
  value       = azurerm_windows_virtual_machine.session_hosts[*].name
}

output "session_host_private_ips" {
  description = "Private IP addresses of the session host virtual machines"
  value       = azurerm_network_interface.session_hosts[*].ip_configuration[0].private_ip_address
}

# ============================================================================
# FSLOGIX OUTPUTS
# ============================================================================

output "fslogix_storage_account_id" {
  description = "ID of the FSLogix storage account"
  value       = var.fslogix_enabled ? azurerm_storage_account.fslogix[0].id : null
}

output "fslogix_storage_account_name" {
  description = "Name of the FSLogix storage account"
  value       = var.fslogix_enabled ? azurerm_storage_account.fslogix[0].name : null
}

output "fslogix_file_share_url" {
  description = "URL of the FSLogix file share"
  value       = var.fslogix_enabled ? "\\\\${azurerm_storage_account.fslogix[0].name}.file.core.windows.net\\${azurerm_storage_share.fslogix_profiles[0].name}" : null
}

output "fslogix_file_share_id" {
  description = "ID of the FSLogix file share"
  value       = var.fslogix_enabled ? azurerm_storage_share.fslogix_profiles[0].id : null
}

# ============================================================================
# PRIVATE ENDPOINT OUTPUTS
# ============================================================================

output "private_endpoint_subnet_id" {
  description = "ID of the private endpoint subnet"
  value       = var.private_endpoints_enabled ? azurerm_subnet.private_endpoints[0].id : null
}

output "fslogix_private_endpoint_id" {
  description = "ID of the FSLogix storage account private endpoint"
  value       = var.fslogix_enabled && var.private_endpoints_enabled ? azurerm_private_endpoint.fslogix_file[0].id : null
}

output "fslogix_private_endpoint_ip" {
  description = "Private IP address of the FSLogix storage account private endpoint"
  value       = var.fslogix_enabled && var.private_endpoints_enabled ? azurerm_private_endpoint.fslogix_file[0].private_service_connection[0].private_ip_address : null
}

# =========================================================================
# NETWORK SECURITY GROUP OUTPUTS - DISABLED
# =========================================================================
# NSG resources are disabled; omit NSG outputs to avoid invalid references.

# ============================================================================
# ROUTE TABLE OUTPUTS
# ============================================================================

output "session_host_route_table_id" {
  description = "ID of the session host route table (if deployed in Non-Gen VNet)"
  value       = var.nongen_firewall_ip != null ? azurerm_route_table.session_hosts[0].id : null
}

output "session_host_route_table_name" {
  description = "Name of the session host route table (if deployed in Non-Gen VNet)"
  value       = var.nongen_firewall_ip != null ? azurerm_route_table.session_hosts[0].name : null
}

# ============================================================================
# AVAILABILITY SET OUTPUTS
# ============================================================================

output "availability_set_id" {
  description = "ID of the session host availability set"
  value       = azurerm_availability_set.session_hosts.id
}

output "availability_set_name" {
  description = "Name of the session host availability set"
  value       = azurerm_availability_set.session_hosts.name
}

# ============================================================================
# MONITORING OUTPUTS
# ============================================================================

output "host_pool_diagnostic_setting_id" {
  description = "ID of the host pool diagnostic setting"
  value       = azurerm_monitor_diagnostic_setting.host_pool.id
}

output "workspace_diagnostic_setting_id" {
  description = "ID of the workspace diagnostic setting"
  value       = azurerm_monitor_diagnostic_setting.workspace.id
}

# ============================================================================
# CONFIGURATION OUTPUTS
# ============================================================================

output "aad_join_enabled" {
  description = "Whether Azure AD join is enabled"
  value       = var.aad_join_enabled
}

output "fslogix_enabled" {
  description = "Whether FSLogix is enabled"
  value       = var.fslogix_enabled
}

output "private_endpoints_enabled" {
  description = "Whether private endpoints are enabled"
  value       = var.private_endpoints_enabled
}
