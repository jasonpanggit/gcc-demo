# ============================================================================
# COMPUTE MODULE OUTPUTS
# ============================================================================

output "nva_vm_id" {
  description = "The ID of the NVA virtual machine"
  value       = var.deploy_route_server && var.deploy_linux_nva ? azurerm_linux_virtual_machine.vm_nva[0].id : null
}

output "nva_private_ip" {
  description = "The private IP address of the NVA"
  value       = var.deploy_route_server && var.deploy_linux_nva ? azurerm_network_interface.nic_nva[0].private_ip_address : null
}

output "squid_vm_id" {
  description = "The ID of the Squid proxy virtual machine"
  value       = var.deploy_squid_proxy ? azurerm_linux_virtual_machine.vm_squid[0].id : null
}

output "squid_private_ip" {
  description = "The private IP address of the Squid proxy"
  value       = var.deploy_squid_proxy ? azurerm_network_interface.nic_squid[0].private_ip_address : null
}

output "onprem_windows_vm_id" {
  description = "The ID of the on-premises Windows virtual machine"
  value       = var.deploy_onprem_vnet && var.deploy_onprem_windows_server_2025 ? azurerm_windows_virtual_machine.vm_onprem_windows_2025[0].id : null
}

output "onprem_windows_private_ip" {
  description = "The private IP address of the on-premises Windows VM"
  value       = var.deploy_onprem_vnet && var.deploy_onprem_windows_server_2025 ? azurerm_network_interface.nic_onprem_windows_2025[0].private_ip_address : null
}

output "onprem_windows_vm_identity" {
  description = "The system assigned identity of the on-premises Windows VM"
  value       = var.deploy_onprem_vnet && var.deploy_onprem_windows_server_2025 ? azurerm_windows_virtual_machine.vm_onprem_windows_2025[0].identity[0].principal_id : null
}

# Windows Server 2016 Outputs
output "onprem_windows_2016_vm_id" {
  description = "The ID of the on-premises Windows Server 2016 virtual machine"
  value       = var.deploy_onprem_vnet && var.deploy_onprem_windows_server_2016 ? azurerm_windows_virtual_machine.vm_onprem_windows_2016[0].id : null
}

output "onprem_windows_2016_private_ip" {
  description = "The private IP address of the on-premises Windows Server 2016 VM"
  value       = var.deploy_onprem_vnet && var.deploy_onprem_windows_server_2016 ? azurerm_network_interface.nic_onprem_windows_2016[0].private_ip_address : null
}

output "onprem_windows_2016_public_ip" {
  description = "The public IP address of the on-premises Windows Server 2016 VM"
  value       = var.deploy_onprem_vnet && var.deploy_onprem_windows_server_2016 ? azurerm_public_ip.pip_onprem_windows_2016[0].ip_address : null
}

output "onprem_windows_2016_vm_identity" {
  description = "The system assigned identity of the on-premises Windows Server 2016 VM"
  value       = var.deploy_onprem_vnet && var.deploy_onprem_windows_server_2016 ? azurerm_windows_virtual_machine.vm_onprem_windows_2016[0].identity[0].principal_id : null
}
