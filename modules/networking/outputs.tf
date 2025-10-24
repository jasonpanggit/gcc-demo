output "vnet_id" {
  description = "The ID of the hub virtual network"
  value       = azurerm_virtual_network.vnet_hub.id
}

output "vnet_name" {
  description = "The name of the hub virtual network"
  value       = azurerm_virtual_network.vnet_hub.name
}

output "gateway_subnet_id" {
  description = "The ID of the gateway subnet"
  value       = length(azurerm_subnet.snet_gateway) > 0 ? azurerm_subnet.snet_gateway[0].id : null
}

output "firewall_subnet_id" {
  description = "The ID of the firewall subnet"
  value       = length(azurerm_subnet.snet_afw_hub) > 0 ? azurerm_subnet.snet_afw_hub[0].id : null
}

output "bastion_subnet_id" {
  description = "The ID of the bastion subnet"
  value       = length(azurerm_subnet.snet_bastion) > 0 ? azurerm_subnet.snet_bastion[0].id : null
}

output "private_endpoint_subnet_id" {
  description = "The ID of the private endpoint subnet"
  value       = length(azurerm_subnet.snet_pe) > 0 ? azurerm_subnet.snet_pe[0].id : null
}

# Additional outputs for new resources
output "route_server_id" {
  description = "The ID of the route server"
  value       = length(azurerm_route_server.rs_hub) > 0 ? azurerm_route_server.rs_hub[0].id : null
}

output "route_server_virtual_router_ips" {
  description = "The virtual router IPs of the route server"
  value       = length(azurerm_route_server.rs_hub) > 0 ? azurerm_route_server.rs_hub[0].virtual_router_ips : []
}

output "bastion_host_id" {
  description = "The ID of the bastion host"
  value       = length(azurerm_bastion_host.bas_hub) > 0 ? azurerm_bastion_host.bas_hub[0].id : null
}

output "nva_subnet_id" {
  description = "The ID of the NVA subnet"
  value       = length(azurerm_subnet.snet_nva) > 0 ? azurerm_subnet.snet_nva[0].id : null
}

output "squid_subnet_id" {
  description = "The ID of the Squid subnet"
  value       = length(azurerm_subnet.snet_squid) > 0 ? azurerm_subnet.snet_squid[0].id : null
}

// NSG outputs disabled (NSGs not created)

# ============================================================================
# SPOKE NETWORKS OUTPUTS
# ============================================================================

# Non-Gen VNet outputs
output "nongen_vnet_id" {
  description = "The ID of the Non-Gen virtual network"
  value       = length(azurerm_virtual_network.vnet_nongen) > 0 ? azurerm_virtual_network.vnet_nongen[0].id : null
}

output "nongen_vnet_name" {
  description = "The name of the Non-Gen virtual network"
  value       = length(azurerm_virtual_network.vnet_nongen) > 0 ? azurerm_virtual_network.vnet_nongen[0].name : null
}

output "nongen_firewall_subnet_id" {
  description = "The ID of the Non-Gen firewall subnet"
  value       = length(azurerm_subnet.snet_afw_nongen) > 0 ? azurerm_subnet.snet_afw_nongen[0].id : null
}

output "nongen_private_endpoint_subnet_id" {
  description = "The ID of the Non-Gen private endpoint subnet"
  value       = length(azurerm_subnet.snet_nongen_pe) > 0 ? azurerm_subnet.snet_nongen_pe[0].id : null
}

output "nongen_appsvc_integration_subnet_id" {
  description = "The ID of the Non-Gen App Service VNet integration subnet"
  value       = length(azurerm_subnet.snet_nongen_appsvc) > 0 ? azurerm_subnet.snet_nongen_appsvc[0].id : null
}

output "nongen_apim_subnet_id" {
  description = "The ID of the Non-Gen API Management subnet"
  value       = length(azurerm_subnet.snet_nongen_apim) > 0 ? azurerm_subnet.snet_nongen_apim[0].id : null
}

output "nongen_container_apps_subnet_id" {
  description = "The ID of the Non-Gen Container Apps subnet"
  value       = length(azurerm_subnet.snet_nongen_container_apps) > 0 ? azurerm_subnet.snet_nongen_container_apps[0].id : null
}

# Gen VNet outputs
output "gen_vnet_id" {
  description = "The ID of the Gen virtual network"
  value       = length(azurerm_virtual_network.vnet_gen) > 0 ? azurerm_virtual_network.vnet_gen[0].id : null
}

output "gen_vnet_name" {
  description = "The name of the Gen virtual network"
  value       = length(azurerm_virtual_network.vnet_gen) > 0 ? azurerm_virtual_network.vnet_gen[0].name : null
}

output "gen_workload_subnet_id" {
  description = "The ID of the Gen workload subnet"
  value       = length(azurerm_subnet.snet_gen_workload) > 0 ? azurerm_subnet.snet_gen_workload[0].id : null
}

# On-premises VNet outputs
output "onprem_vnet_id" {
  description = "The ID of the on-premises virtual network"
  value       = length(azurerm_virtual_network.vnet_onprem) > 0 ? azurerm_virtual_network.vnet_onprem[0].id : null
}

output "onprem_vnet_name" {
  description = "The name of the on-premises virtual network"
  value       = length(azurerm_virtual_network.vnet_onprem) > 0 ? azurerm_virtual_network.vnet_onprem[0].name : null
}

output "onprem_workload_subnet_id" {
  description = "The ID of the on-premises workload subnet"
  value       = length(azurerm_subnet.snet_onprem_workload) > 0 ? azurerm_subnet.snet_onprem_workload[0].id : null
}

output "onprem_windows_nsg_id" {
  description = "The ID of the on-premises Windows NSG"
  value       = length(azurerm_network_security_group.nsg_onprem_windows) > 0 ? azurerm_network_security_group.nsg_onprem_windows[0].id : null
}
