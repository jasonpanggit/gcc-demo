# ============================================================================
# FIREWALL MODULE OUTPUTS
# ============================================================================

output "firewall_id" {
  description = "The ID of the Azure Firewall"
  value       = var.deploy_hub_firewall ? azurerm_firewall.afw_hub[0].id : null
}

output "firewall_private_ip" {
  description = "The private IP address of the Azure Firewall"
  value       = var.deploy_hub_firewall ? azurerm_firewall.afw_hub[0].ip_configuration[0].private_ip_address : null
}

output "firewall_public_ip" {
  description = "The public IP address of the Azure Firewall"
  value       = var.deploy_hub_firewall ? azurerm_public_ip.pip_afw_hub[0].ip_address : null
}

output "firewall_policy_id" {
  description = "The ID of the Azure Firewall Policy"
  value       = var.deploy_hub_firewall ? azurerm_firewall_policy.afwp_hub[0].id : null
}

output "firewall_proxy_url" {
  description = "The proxy URL for Azure Firewall explicit proxy (if enabled)"
  value       = var.deploy_hub_firewall && var.hub_firewall_explicit_proxy ? "http://${azurerm_firewall.afw_hub[0].ip_configuration[0].private_ip_address}:${var.hub_firewall_explicit_proxy_https_port}" : null
}

output "firewall_explicit_proxy_nat_enabled" {
  description = "Whether NAT rules for explicit proxy are enabled"
  value       = var.deploy_hub_firewall && var.hub_firewall_explicit_proxy_nat
}

output "firewall_explicit_proxy_external_http_url" {
  description = "External HTTP proxy URL (via NAT) for Azure Firewall explicit proxy (if NAT is enabled)"
  value       = var.deploy_hub_firewall && var.hub_firewall_explicit_proxy_nat ? "http://${azurerm_public_ip.pip_afw_hub[0].ip_address}:${var.hub_firewall_explicit_proxy_http_port}" : null
}

output "firewall_explicit_proxy_external_https_url" {
  description = "External HTTPS proxy URL (via NAT) for Azure Firewall explicit proxy (if NAT is enabled)"
  value       = var.deploy_hub_firewall && var.hub_firewall_explicit_proxy_nat ? "http://${azurerm_public_ip.pip_afw_hub[0].ip_address}:${var.hub_firewall_explicit_proxy_https_port}" : null
}

# ============================================================================
# NON-GEN FIREWALL OUTPUTS
# ============================================================================

output "nongen_firewall_id" {
  description = "The ID of the Non-Gen Azure Firewall"
  value       = var.deploy_nongen_firewall ? azurerm_firewall.afw_nongen[0].id : null
}

output "nongen_firewall_private_ip" {
  description = "The private IP address of the Non-Gen Azure Firewall"
  value       = var.deploy_nongen_firewall ? azurerm_firewall.afw_nongen[0].ip_configuration[0].private_ip_address : null
}

output "nongen_firewall_public_ip" {
  description = "The public IP address of the Non-Gen Azure Firewall"
  value       = var.deploy_nongen_firewall ? azurerm_public_ip.pip_afw_nongen[0].ip_address : null
}

output "nongen_firewall_policy_id" {
  description = "The ID of the Non-Gen Azure Firewall Policy"
  value       = var.deploy_nongen_firewall ? azurerm_firewall_policy.afwp_nongen[0].id : null
}

output "nongen_firewall_route_table_id" {
  description = "The ID of the Non-Gen firewall route table"
  value       = var.deploy_nongen_firewall ? azurerm_route_table.rt_afw_nongen[0].id : null
}
