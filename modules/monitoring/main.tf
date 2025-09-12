# ============================================================================
# AZURE MONITOR PRIVATE LINK SCOPE MODULE
# ============================================================================

# Log Analytics Workspace
resource "azurerm_log_analytics_workspace" "law_hub" {
  count               = var.deploy_hub_vnet && var.deploy_azure_monitor_private_link_scope ? 1 : 0
  name                = "log-${var.project_name}-${var.environment}"
  location            = var.location
  resource_group_name = var.resource_group_name
  sku                 = var.log_analytics_workspace_sku
  retention_in_days   = var.log_analytics_workspace_retention_days

  tags = {
    Environment = var.environment
    Project     = var.project_name
  }
}

# Data Collection Endpoint
resource "azurerm_monitor_data_collection_endpoint" "dce_hub" {
  count                         = var.deploy_hub_vnet && var.deploy_azure_monitor_private_link_scope ? 1 : 0
  name                          = "dce-${var.project_name}-${var.environment}"
  location                      = var.location
  resource_group_name           = var.resource_group_name
  kind                          = "Windows"
  public_network_access_enabled = false

  tags = {
    Environment = var.environment
    Project     = var.project_name
    Purpose     = "Data Collection Endpoint"
  }
}

# Azure Monitor Private Link Scope
resource "azurerm_monitor_private_link_scope" "ampls_hub" {
  count                 = var.deploy_hub_vnet && var.deploy_azure_monitor_private_link_scope ? 1 : 0
  name                  = "pls-monitor-${var.project_name}-${var.environment}"
  resource_group_name   = var.resource_group_name
  ingestion_access_mode = "Open"
  query_access_mode     = "Open"

  tags = {
    Environment = var.environment
    Project     = var.project_name
  }
}

# Link Log Analytics Workspace to Private Link Scope
resource "azurerm_monitor_private_link_scoped_service" "amplss_law" {
  count               = var.deploy_hub_vnet && var.deploy_azure_monitor_private_link_scope ? 1 : 0
  name                = "plss-log-${var.project_name}-${var.environment}"
  resource_group_name = var.resource_group_name
  scope_name          = azurerm_monitor_private_link_scope.ampls_hub[0].name
  linked_resource_id  = azurerm_log_analytics_workspace.law_hub[0].id
}

# Link Data Collection Endpoint to Private Link Scope
resource "azurerm_monitor_private_link_scoped_service" "amplss_dce" {
  count               = var.deploy_hub_vnet && var.deploy_azure_monitor_private_link_scope ? 1 : 0
  name                = "plss-dce-${var.project_name}-${var.environment}"
  resource_group_name = var.resource_group_name
  scope_name          = azurerm_monitor_private_link_scope.ampls_hub[0].name
  linked_resource_id  = azurerm_monitor_data_collection_endpoint.dce_hub[0].id
}

# Private DNS Zones for Azure Monitor
resource "azurerm_private_dns_zone" "pdz_monitor" {
  count               = var.deploy_hub_vnet && var.deploy_azure_monitor_private_link_scope ? 1 : 0
  name                = "privatelink.monitor.azure.com"
  resource_group_name = var.resource_group_name

  tags = {
    Environment = var.environment
    Project     = var.project_name
  }
}

resource "azurerm_private_dns_zone" "pdz_oms" {
  count               = var.deploy_hub_vnet && var.deploy_azure_monitor_private_link_scope ? 1 : 0
  name                = "privatelink.oms.opinsights.azure.com"
  resource_group_name = var.resource_group_name

  tags = {
    Environment = var.environment
    Project     = var.project_name
  }
}

resource "azurerm_private_dns_zone" "pdz_ods" {
  count               = var.deploy_hub_vnet && var.deploy_azure_monitor_private_link_scope ? 1 : 0
  name                = "privatelink.ods.opinsights.azure.com"
  resource_group_name = var.resource_group_name

  tags = {
    Environment = var.environment
    Project     = var.project_name
  }
}

resource "azurerm_private_dns_zone" "pdz_agentsvc" {
  count               = var.deploy_hub_vnet && var.deploy_azure_monitor_private_link_scope ? 1 : 0
  name                = "privatelink.agentsvc.azure-automation.net"
  resource_group_name = var.resource_group_name

  tags = {
    Environment = var.environment
    Project     = var.project_name
  }
}

resource "azurerm_private_dns_zone" "pdz_blob" {
  count               = var.deploy_hub_vnet && var.deploy_azure_monitor_private_link_scope ? 1 : 0
  name                = "privatelink.blob.core.windows.net"
  resource_group_name = var.resource_group_name

  tags = {
    Environment = var.environment
    Project     = var.project_name
  }
}

# Private Endpoint for Azure Monitor
resource "azurerm_private_endpoint" "pe_monitor" {
  count               = var.deploy_hub_vnet && var.deploy_azure_monitor_private_link_scope ? 1 : 0
  name                = "pe-monitor-${var.project_name}-${var.environment}"
  location            = var.location
  resource_group_name = var.resource_group_name
  subnet_id           = var.private_endpoint_subnet_id

  private_service_connection {
    name                           = "psc-monitor"
    private_connection_resource_id = azurerm_monitor_private_link_scope.ampls_hub[0].id
    is_manual_connection           = false
    subresource_names              = ["azuremonitor"]
  }

  private_dns_zone_group {
    name = "default"
    private_dns_zone_ids = [
      azurerm_private_dns_zone.pdz_monitor[0].id,
      azurerm_private_dns_zone.pdz_oms[0].id,
      azurerm_private_dns_zone.pdz_ods[0].id,
      azurerm_private_dns_zone.pdz_agentsvc[0].id,
      azurerm_private_dns_zone.pdz_blob[0].id
    ]
  }

  tags = {
    Environment = var.environment
    Project     = var.project_name
  }
}

# VNet Links for Monitor Private DNS Zones
resource "azurerm_private_dns_zone_virtual_network_link" "pdzvl_monitor_hub" {
  count                 = var.deploy_hub_vnet && var.deploy_azure_monitor_private_link_scope ? 1 : 0
  name                  = "monitor-hub-link"
  resource_group_name   = var.resource_group_name
  private_dns_zone_name = azurerm_private_dns_zone.pdz_monitor[0].name
  virtual_network_id    = var.hub_vnet_id
  registration_enabled  = false

  tags = {
    Environment = var.environment
    Project     = var.project_name
  }
}

resource "azurerm_private_dns_zone_virtual_network_link" "pdzvl_oms_hub" {
  count                 = var.deploy_hub_vnet && var.deploy_azure_monitor_private_link_scope ? 1 : 0
  name                  = "oms-hub-link"
  resource_group_name   = var.resource_group_name
  private_dns_zone_name = azurerm_private_dns_zone.pdz_oms[0].name
  virtual_network_id    = var.hub_vnet_id
  registration_enabled  = false

  tags = {
    Environment = var.environment
    Project     = var.project_name
  }
}

resource "azurerm_private_dns_zone_virtual_network_link" "pdzvl_ods_hub" {
  count                 = var.deploy_hub_vnet && var.deploy_azure_monitor_private_link_scope ? 1 : 0
  name                  = "ods-hub-link"
  resource_group_name   = var.resource_group_name
  private_dns_zone_name = azurerm_private_dns_zone.pdz_ods[0].name
  virtual_network_id    = var.hub_vnet_id
  registration_enabled  = false

  tags = {
    Environment = var.environment
    Project     = var.project_name
  }
}

resource "azurerm_private_dns_zone_virtual_network_link" "pdzvl_agentsvc_hub" {
  count                 = var.deploy_hub_vnet && var.deploy_azure_monitor_private_link_scope ? 1 : 0
  name                  = "agentsvc-hub-link"
  resource_group_name   = var.resource_group_name
  private_dns_zone_name = azurerm_private_dns_zone.pdz_agentsvc[0].name
  virtual_network_id    = var.hub_vnet_id
  registration_enabled  = false

  tags = {
    Environment = var.environment
    Project     = var.project_name
  }
}

resource "azurerm_private_dns_zone_virtual_network_link" "pdzvl_blob_hub" {
  count                 = var.deploy_hub_vnet && var.deploy_azure_monitor_private_link_scope ? 1 : 0
  name                  = "blob-hub-link"
  resource_group_name   = var.resource_group_name
  private_dns_zone_name = azurerm_private_dns_zone.pdz_blob[0].name
  virtual_network_id    = var.hub_vnet_id
  registration_enabled  = false

  tags = {
    Environment = var.environment
    Project     = var.project_name
  }
}

resource "azurerm_private_dns_zone_virtual_network_link" "pdzvl_blob_onprem" {
  count                 = var.deploy_onprem_vnet && var.deploy_azure_monitor_private_link_scope && var.onprem_windows_arc_onboarding ? 1 : 0
  name                  = "blob-onprem-link"
  resource_group_name   = var.resource_group_name
  private_dns_zone_name = azurerm_private_dns_zone.pdz_blob[0].name
  virtual_network_id    = var.onprem_vnet_id
  registration_enabled  = false

  tags = {
    Environment = var.environment
    Project     = var.project_name
    Purpose     = "Blob Storage DNS for On-premises"
  }

  depends_on = [
    azurerm_private_dns_zone.pdz_blob
  ]
}

# Additional on-prem links for other Azure Monitor private DNS zones
resource "azurerm_private_dns_zone_virtual_network_link" "pdzvl_monitor_onprem" {
  count                 = var.deploy_onprem_vnet && var.deploy_azure_monitor_private_link_scope ? 1 : 0
  name                  = "monitor-onprem-link"
  resource_group_name   = var.resource_group_name
  private_dns_zone_name = azurerm_private_dns_zone.pdz_monitor[0].name
  virtual_network_id    = var.onprem_vnet_id
  registration_enabled  = false

  tags = {
    Environment = var.environment
    Project     = var.project_name
  }
}

resource "azurerm_private_dns_zone_virtual_network_link" "pdzvl_oms_onprem" {
  count                 = var.deploy_onprem_vnet && var.deploy_azure_monitor_private_link_scope ? 1 : 0
  name                  = "oms-onprem-link"
  resource_group_name   = var.resource_group_name
  private_dns_zone_name = azurerm_private_dns_zone.pdz_oms[0].name
  virtual_network_id    = var.onprem_vnet_id
  registration_enabled  = false

  tags = {
    Environment = var.environment
    Project     = var.project_name
  }
}

resource "azurerm_private_dns_zone_virtual_network_link" "pdzvl_ods_onprem" {
  count                 = var.deploy_onprem_vnet && var.deploy_azure_monitor_private_link_scope ? 1 : 0
  name                  = "ods-onprem-link"
  resource_group_name   = var.resource_group_name
  private_dns_zone_name = azurerm_private_dns_zone.pdz_ods[0].name
  virtual_network_id    = var.onprem_vnet_id
  registration_enabled  = false

  tags = {
    Environment = var.environment
    Project     = var.project_name
  }
}

resource "azurerm_private_dns_zone_virtual_network_link" "pdzvl_agentsvc_onprem" {
  count                 = var.deploy_onprem_vnet && var.deploy_azure_monitor_private_link_scope ? 1 : 0
  name                  = "agentsvc-onprem-link"
  resource_group_name   = var.resource_group_name
  private_dns_zone_name = azurerm_private_dns_zone.pdz_agentsvc[0].name
  virtual_network_id    = var.onprem_vnet_id
  registration_enabled  = false

  tags = {
    Environment = var.environment
    Project     = var.project_name
  }
}
