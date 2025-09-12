# ============================================================================
# ROUTING MODULE OUTPUTS
# ============================================================================

output "gateway_route_table_id" {
  description = "The ID of the gateway route table"
  value       = var.deploy_hub_vnet && (var.deploy_expressroute_gateway || var.deploy_vpn_gateway) ? azurerm_route_table.rt_gateway[0].id : null
}

output "firewall_route_table_id" {
  description = "The ID of the Azure Firewall route table (force tunneling)"
  value       = var.deploy_hub_vnet && var.deploy_hub_firewall && var.hub_firewall_force_tunneling ? azurerm_route_table.rt_afw_hub[0].id : null
}

output "squid_route_table_id" {
  description = "The ID of the Squid proxy route table"
  value       = var.deploy_squid_proxy && var.deploy_hub_firewall ? azurerm_route_table.rt_squid[0].id : null
}

output "gen_workload_route_table_id" {
  description = "The ID of the Gen workload route table"
  value       = var.deploy_gen_vnet && var.deploy_nongen_vnet && var.deploy_nongen_firewall && var.route_internet_to_nongen_firewall ? azurerm_route_table.rt_gen_workload[0].id : null
}
