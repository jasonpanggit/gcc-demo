output "service_principal_client_id" {
  description = "The client ID of the Arc onboarding service principal"
  value       = length(azuread_application.arc_onboarding) > 0 ? azuread_application.arc_onboarding[0].client_id : null
}

output "service_principal_secret" {
  description = "The secret of the Arc onboarding service principal"
  value       = length(azuread_application_password.arc_onboarding) > 0 ? azuread_application_password.arc_onboarding[0].value : null
  sensitive   = true
}

output "private_link_scope_id" {
  description = "The ID of the Arc private link scope"
  value       = length(azurerm_arc_private_link_scope.arc_pls_hub) > 0 ? azurerm_arc_private_link_scope.arc_pls_hub[0].id : null
}

output "arc_private_dns_zone_ids" {
  description = "The IDs of the Arc private DNS zones"
  value = {
    guestconfig   = length(azurerm_private_dns_zone.pdz_arc_guestconfig) > 0 ? azurerm_private_dns_zone.pdz_arc_guestconfig[0].id : null
    hybridcompute = length(azurerm_private_dns_zone.pdz_arc_hybridcompute) > 0 ? azurerm_private_dns_zone.pdz_arc_hybridcompute[0].id : null
    download      = length(azurerm_private_dns_zone.pdz_arc_download) > 0 ? azurerm_private_dns_zone.pdz_arc_download[0].id : null
  }
}

output "arc_private_endpoint_id" {
  description = "The ID of the Arc private endpoint"
  value       = length(azurerm_private_endpoint.pe_arc) > 0 ? azurerm_private_endpoint.pe_arc[0].id : null
}
