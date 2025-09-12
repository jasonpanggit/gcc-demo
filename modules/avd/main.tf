# ============================================================================
# DATA SOURCES
# ============================================================================

data "azurerm_client_config" "current" {}

data "azuread_client_config" "current" {}

data "azurerm_resource_group" "avd" {
  name = split("/", var.resource_group_id)[4]
}

# ============================================================================
# RANDOM RESOURCES FOR UNIQUE NAMING
# ============================================================================

resource "random_string" "storage_suffix" {
  length  = 8
  special = false
  upper   = false
}

resource "random_uuid" "host_pool_token" {}

# ============================================================================
# NETWORK SUBNETS
# ============================================================================

# Session Host Subnet
resource "azurerm_subnet" "session_hosts" {
  name                 = "snet-avd-hosts-${var.project_name}-${var.environment}"
  resource_group_name  = var.vnet_resource_group
  virtual_network_name = var.vnet_name
  address_prefixes     = [var.session_host_subnet_prefix]

  # Disable private endpoint network policies for better integration
  private_endpoint_network_policies = "Disabled"
}

# Private Endpoint Subnet
resource "azurerm_subnet" "private_endpoints" {
  count                = var.private_endpoints_enabled ? 1 : 0
  name                 = "snet-avd-pe-${var.project_name}-${var.environment}"
  resource_group_name  = var.vnet_resource_group
  virtual_network_name = var.vnet_name
  address_prefixes     = [var.private_endpoint_subnet_prefix]

  private_endpoint_network_policies = "Disabled"
}

// =========================================================================
// NETWORK SECURITY GROUPS - DISABLED
// =========================================================================
// The AVD NSG and association are intentionally disabled/commented out.
// If needed later, restore this block.
// resource "azurerm_network_security_group" "session_hosts" { ... }
// resource "azurerm_subnet_network_security_group_association" "session_hosts" { ... }

# ============================================================================
# ROUTE TABLE FOR NON-GEN FIREWALL ROUTING
# ============================================================================
# This route table ensures all outbound internet traffic from AVD session hosts
# is routed through the Non-Gen Azure Firewall for inspection and filtering.
# The firewall provides:
# - Application-level filtering for AVD service URLs
# - Network-level rules for required ports and protocols
# - Centralized logging and monitoring of all outbound traffic
# - Security compliance and threat protection

resource "azurerm_route_table" "session_hosts" {
  count               = var.deploy_nongen_firewall ? 1 : 0
  name                = "rt-avd-hosts-${var.project_name}-${var.environment}"
  location            = data.azurerm_resource_group.avd.location
  resource_group_name = data.azurerm_resource_group.avd.name

  # Route all internet traffic through Non-Gen firewall
  # This ensures AVD traffic is inspected and filtered
  route {
    name                   = "route-internet-via-firewall"
    address_prefix         = "0.0.0.0/0"
    next_hop_type          = "VirtualAppliance"
    next_hop_in_ip_address = var.nongen_firewall_ip
  }

  tags = var.tags
}

# Associate Route Table with Session Host Subnet
resource "azurerm_subnet_route_table_association" "session_hosts" {
  count          = var.deploy_nongen_firewall ? 1 : 0
  subnet_id      = azurerm_subnet.session_hosts.id
  route_table_id = azurerm_route_table.session_hosts[0].id
}

# ============================================================================
# AVD WORKSPACE
# ============================================================================

resource "azurerm_virtual_desktop_workspace" "main" {
  name                = "avd-ws-${var.project_name}-${var.environment}"
  location            = data.azurerm_resource_group.avd.location
  resource_group_name = data.azurerm_resource_group.avd.name
  friendly_name       = "AVD Workspace - ${var.project_name}"
  description         = "Azure Virtual Desktop workspace for ${var.project_name} project"

  tags = var.tags
}

# ============================================================================
# AVD HOST POOL
# ============================================================================

resource "azurerm_virtual_desktop_host_pool" "main" {
  name                = "avd-hp-${var.project_name}-${var.environment}"
  location            = data.azurerm_resource_group.avd.location
  resource_group_name = data.azurerm_resource_group.avd.name

  type                     = var.host_pool_type
  load_balancer_type       = var.host_pool_load_balancer_type
  maximum_sessions_allowed = var.host_pool_maximum_sessions
  start_vm_on_connect      = var.host_pool_start_vm_on_connect
  validate_environment     = false
  friendly_name            = "AVD Host Pool - ${var.project_name}"
  description              = "Azure Virtual Desktop host pool for ${var.project_name} project"

  tags = var.tags
}

# ============================================================================
# AVD HOST POOL REGISTRATION INFO
# ============================================================================

resource "azurerm_virtual_desktop_host_pool_registration_info" "main" {
  hostpool_id     = azurerm_virtual_desktop_host_pool.main.id
  expiration_date = timeadd(timestamp(), "48h")
}

# ============================================================================
# AVD APPLICATION GROUP
# ============================================================================

resource "azurerm_virtual_desktop_application_group" "main" {
  name                = "avd-ag-${var.project_name}-${var.environment}"
  location            = data.azurerm_resource_group.avd.location
  resource_group_name = data.azurerm_resource_group.avd.name

  type          = "Desktop"
  host_pool_id  = azurerm_virtual_desktop_host_pool.main.id
  friendly_name = "AVD Desktop Application Group - ${var.project_name}"
  description   = "Azure Virtual Desktop desktop application group for ${var.project_name} project"

  tags = var.tags
}

# ============================================================================
# WORKSPACE APPLICATION GROUP ASSOCIATION
# ============================================================================

resource "azurerm_virtual_desktop_workspace_application_group_association" "main" {
  workspace_id         = azurerm_virtual_desktop_workspace.main.id
  application_group_id = azurerm_virtual_desktop_application_group.main.id
}

# ============================================================================
# FSLOGIX STORAGE ACCOUNT
# ============================================================================

resource "azurerm_storage_account" "fslogix" {
  count                    = var.fslogix_enabled ? 1 : 0
  name                     = "stavdfslogix${random_string.storage_suffix.result}"
  resource_group_name      = data.azurerm_resource_group.avd.name
  location                 = data.azurerm_resource_group.avd.location
  account_tier             = var.fslogix_storage_account_tier
  account_replication_type = var.fslogix_storage_account_replication
  account_kind             = "FileStorage"

  # Enable Azure AD authentication
  azure_files_authentication {
    directory_type = "AADDS"
  }

  network_rules {
    default_action = var.private_endpoints_enabled ? "Deny" : "Allow"
    bypass         = ["AzureServices"]

    # Allow access from session host subnet
    virtual_network_subnet_ids = [azurerm_subnet.session_hosts.id]
  }

  tags = var.tags
}

# FSLogix File Share
resource "azurerm_storage_share" "fslogix_profiles" {
  count              = var.fslogix_enabled ? 1 : 0
  name               = "fslogix-profiles"
  storage_account_id = azurerm_storage_account.fslogix[0].id
  quota              = var.fslogix_file_share_quota_gb
  enabled_protocol   = "SMB"

  acl {
    id = "GhostedRule"
    access_policy {
      permissions = "rcwd"
    }
  }
}

# ============================================================================
# PRIVATE ENDPOINTS FOR FSLOGIX STORAGE
# ============================================================================

resource "azurerm_private_endpoint" "fslogix_file" {
  count               = var.fslogix_enabled && var.private_endpoints_enabled ? 1 : 0
  name                = "pe-fslogix-file-${var.project_name}-${var.environment}"
  location            = data.azurerm_resource_group.avd.location
  resource_group_name = data.azurerm_resource_group.avd.name
  subnet_id           = azurerm_subnet.private_endpoints[0].id

  private_service_connection {
    name                           = "psc-fslogix-file"
    private_connection_resource_id = azurerm_storage_account.fslogix[0].id
    subresource_names              = ["file"]
    is_manual_connection           = false
  }

  private_dns_zone_group {
    name                 = "pdz-group-file"
    private_dns_zone_ids = [azurerm_private_dns_zone.file[0].id]
  }

  tags = var.tags
}

# ============================================================================
# PRIVATE DNS ZONES
# ============================================================================

resource "azurerm_private_dns_zone" "file" {
  count               = var.private_endpoints_enabled ? 1 : 0
  name                = "privatelink.file.core.windows.net"
  resource_group_name = data.azurerm_resource_group.avd.name

  tags = var.tags
}

resource "azurerm_private_dns_zone_virtual_network_link" "file" {
  count                 = var.private_endpoints_enabled ? 1 : 0
  name                  = "pdz-link-file-${var.project_name}-${var.environment}"
  resource_group_name   = data.azurerm_resource_group.avd.name
  private_dns_zone_name = azurerm_private_dns_zone.file[0].name
  virtual_network_id    = var.vnet_id
  registration_enabled  = false

  tags = var.tags
}

# ============================================================================
# AVAILABILITY SET FOR SESSION HOSTS
# ============================================================================

resource "azurerm_availability_set" "session_hosts" {
  name                = "avs-avd-hosts-${var.project_name}-${var.environment}"
  location            = data.azurerm_resource_group.avd.location
  resource_group_name = data.azurerm_resource_group.avd.name

  platform_fault_domain_count  = 2
  platform_update_domain_count = 5
  managed                      = true

  tags = var.tags
}

# ============================================================================
# SESSION HOST VIRTUAL MACHINES
# ============================================================================

# Network Interfaces for Session Hosts
resource "azurerm_network_interface" "session_hosts" {
  count               = var.session_host_count
  name                = "nic-avd-host-${count.index + 1}-${var.project_name}-${var.environment}"
  location            = data.azurerm_resource_group.avd.location
  resource_group_name = data.azurerm_resource_group.avd.name

  ip_configuration {
    name                          = "internal"
    subnet_id                     = azurerm_subnet.session_hosts.id
    private_ip_address_allocation = "Dynamic"
  }

  tags = var.tags
}

# Session Host Virtual Machines
resource "azurerm_windows_virtual_machine" "session_hosts" {
  count               = var.session_host_count
  name                = "vm-avd-host-${count.index + 1}-${var.project_name}-${var.environment}"
  location            = data.azurerm_resource_group.avd.location
  resource_group_name = data.azurerm_resource_group.avd.name
  size                = var.session_host_vm_size
  admin_username      = var.session_host_admin_username
  admin_password      = var.session_host_admin_password
  availability_set_id = azurerm_availability_set.session_hosts.id

  # Enable Azure AD join
  identity {
    type = "SystemAssigned"
  }

  network_interface_ids = [
    azurerm_network_interface.session_hosts[count.index].id,
  ]

  os_disk {
    caching              = "ReadWrite"
    storage_account_type = "Premium_LRS"
  }

  source_image_reference {
    publisher = var.session_host_image_publisher
    offer     = var.session_host_image_offer
    sku       = var.session_host_image_sku
    version   = "latest"
  }

  tags = var.tags
}

# ============================================================================
# AZURE AD JOIN EXTENSION
# ============================================================================

resource "azurerm_virtual_machine_extension" "aad_join" {
  count                = var.aad_join_enabled ? var.session_host_count : 0
  name                 = "AADLoginForWindows"
  virtual_machine_id   = azurerm_windows_virtual_machine.session_hosts[count.index].id
  publisher            = "Microsoft.Azure.ActiveDirectory"
  type                 = "AADLoginForWindows"
  type_handler_version = "1.0"

  tags = var.tags

  depends_on = [azurerm_windows_virtual_machine.session_hosts]
}

# ============================================================================
# AVD AGENT EXTENSIONS
# ============================================================================

# AVD Agent Extension
resource "azurerm_virtual_machine_extension" "avd_agent" {
  count                = var.session_host_count
  name                 = "AVDAgent"
  virtual_machine_id   = azurerm_windows_virtual_machine.session_hosts[count.index].id
  publisher            = "Microsoft.Powershell"
  type                 = "DSC"
  type_handler_version = "2.73"

  settings = jsonencode({
    modulesUrl            = "https://wvdportalstorageblob.blob.core.windows.net/galleryartifacts/Configuration_09-08-2022.zip"
    configurationFunction = "Configuration.ps1\\AddSessionHost"
    properties = {
      hostPoolName          = azurerm_virtual_desktop_host_pool.main.name
      registrationInfoToken = azurerm_virtual_desktop_host_pool_registration_info.main.token
      aadJoin               = var.aad_join_enabled
    }
  })

  tags = var.tags

  depends_on = [
    azurerm_virtual_machine_extension.aad_join,
    azurerm_windows_virtual_machine.session_hosts
  ]
}

# ============================================================================
# DIAGNOSTIC SETTINGS
# ============================================================================

# Host Pool Diagnostic Settings
resource "azurerm_monitor_diagnostic_setting" "host_pool" {
  name                       = "diag-hp-${var.project_name}-${var.environment}"
  target_resource_id         = azurerm_virtual_desktop_host_pool.main.id
  log_analytics_workspace_id = var.log_analytics_workspace_id

  enabled_log {
    category = "Checkpoint"
  }

  enabled_log {
    category = "Error"
  }

  enabled_log {
    category = "Management"
  }

  enabled_log {
    category = "Connection"
  }

  enabled_log {
    category = "HostRegistration"
  }

  enabled_log {
    category = "AgentHealthStatus"
  }
}

# Workspace Diagnostic Settings
resource "azurerm_monitor_diagnostic_setting" "workspace" {
  name                       = "diag-ws-${var.project_name}-${var.environment}"
  target_resource_id         = azurerm_virtual_desktop_workspace.main.id
  log_analytics_workspace_id = var.log_analytics_workspace_id

  enabled_log {
    category = "Checkpoint"
  }

  enabled_log {
    category = "Error"
  }

  enabled_log {
    category = "Management"
  }

  enabled_log {
    category = "Feed"
  }
}
