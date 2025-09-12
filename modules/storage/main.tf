# ============================================================================
# STORAGE MODULE
# ============================================================================
# This module manages storage accounts and related resources for scripts

# ============================================================================
# STORAGE ACCOUNT FOR SCRIPTS
# ============================================================================

resource "azurerm_storage_account" "sa_scripts" {
  count                           = var.deploy_script_storage ? 1 : 0
  name                            = "sademovmextscripts"
  resource_group_name             = var.resource_group_name
  location                        = var.location
  account_tier                    = "Standard"
  account_replication_type        = "LRS"
  allow_nested_items_to_be_public = true
  public_network_access_enabled   = true

  tags = var.tags
}

# ============================================================================
# STORAGE CONTAINER FOR SCRIPTS
# ============================================================================

# Storage Container for Arc Scripts
resource "azurerm_storage_container" "sc_scripts" {
  count              = var.deploy_script_storage && (var.onprem_windows_arc_onboarding || var.onprem_windows_vpn_setup) ? 1 : 0
  name               = "scripts"
  storage_account_id = azurerm_storage_account.sa_scripts[0].id
}

# ============================================================================
# SCRIPT BLOBS
# ============================================================================

# Arc Setup Script Blob
resource "azurerm_storage_blob" "sb_arc_setup" {
  count                  = var.deploy_script_storage && var.onprem_windows_arc_onboarding ? 1 : 0
  name                   = "arc/windows-server-2025-arc-setup.ps1"
  storage_account_name   = azurerm_storage_account.sa_scripts[0].name
  storage_container_name = azurerm_storage_container.sc_scripts[0].name
  type                   = "Block"
  source                 = "${path.root}/scripts/arc/windows-server-2025-arc-setup.ps1"
  metadata = {
    version = filesha256("${path.root}/scripts/arc/windows-server-2025-arc-setup.ps1")
  }
}

# VPN Setup Script Blob
resource "azurerm_storage_blob" "sb_vpn_setup_script" {
  count                  = var.deploy_script_storage && var.onprem_windows_vpn_setup && var.deploy_vpn_gateway ? 1 : 0
  name                   = "vpn/windows-server-2016-vpn-setup.ps1"
  storage_account_name   = azurerm_storage_account.sa_scripts[0].name
  storage_container_name = azurerm_storage_container.sc_scripts[0].name
  type                   = "Block"
  source                 = "${path.root}/scripts/vpn/windows-server-2016-vpn-setup.ps1"
}

# ============================================================================
# SAS TOKEN FOR SCRIPT ACCESS
# ============================================================================

# SAS token for script access
data "azurerm_storage_account_blob_container_sas" "scripts" {
  count             = var.deploy_script_storage && (var.onprem_windows_arc_onboarding || var.onprem_windows_vpn_setup) ? 1 : 0
  connection_string = azurerm_storage_account.sa_scripts[0].primary_connection_string
  container_name    = azurerm_storage_container.sc_scripts[0].name
  https_only        = true

  start  = "2024-01-01T00:00:00Z"
  expiry = "2026-12-31T23:59:59Z"

  permissions {
    read   = true
    add    = false
    create = false
    write  = false
    delete = false
    list   = true
  }

  depends_on = [
    azurerm_storage_container.sc_scripts
  ]
}
