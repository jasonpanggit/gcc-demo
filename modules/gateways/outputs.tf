# ============================================================================
# GATEWAYS MODULE OUTPUTS
# ============================================================================

output "expressroute_gateway_id" {
  description = "The ID of the ExpressRoute gateway"
  value       = var.deploy_expressroute_gateway ? azurerm_virtual_network_gateway.vgw_er[0].id : null
}

output "expressroute_gateway_public_ip" {
  description = "The public IP of the ExpressRoute gateway"
  value       = var.deploy_expressroute_gateway ? azurerm_public_ip.pip_expressroute_gateway[0].ip_address : null
}

output "vpn_gateway_id" {
  description = "The ID of the VPN gateway"
  value       = var.deploy_vpn_gateway ? azurerm_virtual_network_gateway.vgw_vpn[0].id : null
}

output "vpn_gateway_public_ip" {
  description = "The public IP of the VPN gateway"
  value       = var.deploy_vpn_gateway ? azurerm_public_ip.pip_vpn_gateway[0].ip_address : null
}

output "expressroute_circuit_id" {
  description = "The ID of the ExpressRoute circuit"
  value       = var.deploy_expressroute_gateway ? azurerm_express_route_circuit.erc_hub[0].id : null
}

output "local_network_gateway_id" {
  description = "The ID of the local network gateway"
  value       = var.deploy_onprem_vnet && var.deploy_vpn_gateway && var.onprem_windows_vpn_setup ? azurerm_local_network_gateway.lng_onprem[0].id : null
}

output "onprem_vpn_public_ip" {
  description = "The public IP for on-premises VPN"
  value       = var.deploy_onprem_vnet && var.deploy_vpn_gateway && var.onprem_windows_vpn_setup ? azurerm_public_ip.pip_onprem_vpn[0].ip_address : null
}

output "onprem_vnet_id" {
  description = "The ID of the on-premises VNet"
  value       = null # Placeholder - this would be handled by a separate onprem module
}

output "onprem_workload_subnet_id" {
  description = "The ID of the on-premises workload subnet"
  value       = null # Placeholder - this would be handled by a separate onprem module
}
