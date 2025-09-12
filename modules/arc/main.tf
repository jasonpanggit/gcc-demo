# ============================================================================
# AZURE ARC RESOURCES
# ============================================================================

# Azure AD Application for Arc Onboarding
locals {
  # Extract the resource group name from an ID like:
  # /subscriptions/<sub>/resourceGroups/<rg-name>
  # Works even if additional segments follow (we always pick the element after 'resourceGroups').
  _rg_tokens              = split("/", var.resource_group_id)
  arc_resource_group_name = local._rg_tokens[index(local._rg_tokens, "resourceGroups") + 1]
}
resource "azuread_application" "arc_onboarding" {
  count            = 1
  display_name     = "sp-arc-onboarding-${var.project_name}-${var.environment}"
  sign_in_audience = "AzureADMyOrg"

  tags = [
    "Environment:${var.environment}",
    "Project:${var.project_name}",
    "Purpose:AzureArcOnboarding"
  ]
}

# Service Principal for the Arc Onboarding Application
resource "azuread_service_principal" "arc_onboarding" {
  count     = 1
  client_id = azuread_application.arc_onboarding[0].client_id

  tags = [
    "Environment:${var.environment}",
    "Project:${var.project_name}",
    "Purpose:AzureArcOnboarding"
  ]
}

# Generate password for the service principal
resource "azuread_application_password" "arc_onboarding" {
  count          = 1
  application_id = azuread_application.arc_onboarding[0].id
  display_name   = "Arc Onboarding Secret"

  end_date = "2026-12-31T23:59:59Z" # Expires on December 31, 2026
}

# Role assignment for Azure Connected Machine Onboarding at resource group level
resource "azurerm_role_assignment" "arc_onboarding_rg" {
  count                = 1
  scope                = var.resource_group_id
  role_definition_name = "Azure Connected Machine Onboarding"
  principal_id         = azuread_service_principal.arc_onboarding[0].object_id
}

# Optional: Role assignment at subscription level (if enabled)
resource "azurerm_role_assignment" "arc_onboarding_subscription" {
  count                = var.arc_service_principal_subscription_scope ? 1 : 0
  scope                = "/subscriptions/${var.subscription_id}"
  role_definition_name = "Azure Connected Machine Onboarding"
  principal_id         = azuread_service_principal.arc_onboarding[0].object_id
}

# Arc Private Link Scope (if enabled)
resource "azurerm_arc_private_link_scope" "arc_pls_hub" {
  count               = var.deploy_arc_private_link_scope ? 1 : 0
  name                = "arc-pls-${var.project_name}-${var.environment}"
  resource_group_name = local.arc_resource_group_name
  # Use provided region (must be one of the supported Arc PLS regions; 'Global' is invalid)
  location = var.location

  tags = {
    Environment = var.environment
    Project     = var.project_name
  }
}

# Private DNS Zone for Azure Arc Guest Configuration
resource "azurerm_private_dns_zone" "pdz_arc_guestconfig" {
  count               = var.deploy_hub_vnet && var.deploy_arc_private_link_scope ? 1 : 0
  name                = "privatelink.guestconfiguration.azure.com"
  resource_group_name = local.arc_resource_group_name

  tags = {
    Environment = var.environment
    Project     = var.project_name
    Purpose     = "Azure Arc Private DNS"
  }
}

# Private DNS Zone for Azure Arc Hybrid Compute
resource "azurerm_private_dns_zone" "pdz_arc_hybridcompute" {
  count               = var.deploy_hub_vnet && var.deploy_arc_private_link_scope ? 1 : 0
  name                = "privatelink.his.arc.azure.com"
  resource_group_name = local.arc_resource_group_name

  tags = {
    Environment = var.environment
    Project     = var.project_name
    Purpose     = "Azure Arc Private DNS"
  }
}

# Private DNS Zone for Azure Arc Download
resource "azurerm_private_dns_zone" "pdz_arc_download" {
  count               = var.deploy_hub_vnet && var.deploy_arc_private_link_scope ? 1 : 0
  name                = "privatelink.dp.kubernetesconfiguration.azure.com"
  resource_group_name = local.arc_resource_group_name

  tags = {
    Environment = var.environment
    Project     = var.project_name
    Purpose     = "Azure Arc Private DNS"
  }
}

# Private DNS Zone VNet Link for Guest Configuration
resource "azurerm_private_dns_zone_virtual_network_link" "pdzvl_arc_guestconfig_hub" {
  count                 = var.deploy_hub_vnet && var.deploy_arc_private_link_scope ? 1 : 0
  name                  = "arc-guestconfig-hub-link"
  resource_group_name   = local.arc_resource_group_name
  private_dns_zone_name = azurerm_private_dns_zone.pdz_arc_guestconfig[0].name
  virtual_network_id    = var.hub_vnet_id
  registration_enabled  = false

  tags = {
    Environment = var.environment
    Project     = var.project_name
  }
}

# Private DNS Zone VNet Link for Hybrid Compute
resource "azurerm_private_dns_zone_virtual_network_link" "pdzvl_arc_hybridcompute_hub" {
  count                 = var.deploy_hub_vnet && var.deploy_arc_private_link_scope ? 1 : 0
  name                  = "arc-hybridcompute-hub-link"
  resource_group_name   = local.arc_resource_group_name
  private_dns_zone_name = azurerm_private_dns_zone.pdz_arc_hybridcompute[0].name
  virtual_network_id    = var.hub_vnet_id
  registration_enabled  = false

  tags = {
    Environment = var.environment
    Project     = var.project_name
  }
}

# Private DNS Zone VNet Link for Download
resource "azurerm_private_dns_zone_virtual_network_link" "pdzvl_arc_download_hub" {
  count                 = var.deploy_hub_vnet && var.deploy_arc_private_link_scope ? 1 : 0
  name                  = "arc-download-hub-link"
  resource_group_name   = local.arc_resource_group_name
  private_dns_zone_name = azurerm_private_dns_zone.pdz_arc_download[0].name
  virtual_network_id    = var.hub_vnet_id
  registration_enabled  = false

  tags = {
    Environment = var.environment
    Project     = var.project_name
  }
}

# Optional: Private DNS Zone VNet Links for On-Prem Simulated VNet
resource "azurerm_private_dns_zone_virtual_network_link" "pdzvl_arc_guestconfig_onprem" {
  count                 = var.deploy_onprem_vnet && var.deploy_arc_private_link_scope ? 1 : 0
  name                  = "arc-guestconfig-onprem-link"
  resource_group_name   = local.arc_resource_group_name
  private_dns_zone_name = azurerm_private_dns_zone.pdz_arc_guestconfig[0].name
  virtual_network_id    = var.onprem_vnet_id
  registration_enabled  = false

  tags = {
    Environment = var.environment
    Project     = var.project_name
  }
}

resource "azurerm_private_dns_zone_virtual_network_link" "pdzvl_arc_hybridcompute_onprem" {
  count                 = var.deploy_onprem_vnet && var.deploy_arc_private_link_scope ? 1 : 0
  name                  = "arc-hybridcompute-onprem-link"
  resource_group_name   = local.arc_resource_group_name
  private_dns_zone_name = azurerm_private_dns_zone.pdz_arc_hybridcompute[0].name
  virtual_network_id    = var.onprem_vnet_id
  registration_enabled  = false

  tags = {
    Environment = var.environment
    Project     = var.project_name
  }
}

resource "azurerm_private_dns_zone_virtual_network_link" "pdzvl_arc_download_onprem" {
  count                 = var.deploy_onprem_vnet && var.deploy_arc_private_link_scope ? 1 : 0
  name                  = "arc-download-onprem-link"
  resource_group_name   = local.arc_resource_group_name
  private_dns_zone_name = azurerm_private_dns_zone.pdz_arc_download[0].name
  virtual_network_id    = var.onprem_vnet_id
  registration_enabled  = false

  tags = {
    Environment = var.environment
    Project     = var.project_name
  }
}

# Private Endpoint for Azure Arc
resource "azurerm_private_endpoint" "pe_arc" {
  count               = var.deploy_hub_vnet && var.deploy_arc_private_link_scope ? 1 : 0
  name                = "pe-arc-${var.project_name}-${var.environment}"
  location            = var.location
  resource_group_name = local.arc_resource_group_name
  subnet_id           = var.private_endpoint_subnet_id

  private_service_connection {
    name                           = "psc-arc"
    private_connection_resource_id = azurerm_arc_private_link_scope.arc_pls_hub[0].id
    is_manual_connection           = false
    subresource_names              = ["hybridcompute"]
  }

  private_dns_zone_group {
    name = "arc-dns-zone-group"
    private_dns_zone_ids = [
      azurerm_private_dns_zone.pdz_arc_hybridcompute[0].id,
      azurerm_private_dns_zone.pdz_arc_guestconfig[0].id,
      azurerm_private_dns_zone.pdz_arc_download[0].id
    ]
  }

  tags = {
    Environment = var.environment
    Project     = var.project_name
    Purpose     = "Azure Arc Private Endpoint"
  }

  depends_on = [
    azurerm_arc_private_link_scope.arc_pls_hub,
    azurerm_private_dns_zone.pdz_arc_hybridcompute,
    azurerm_private_dns_zone.pdz_arc_guestconfig,
    azurerm_private_dns_zone.pdz_arc_download
  ]
}
