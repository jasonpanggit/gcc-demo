# ============================================================================
# COMPUTE MODULE
# ============================================================================
# This module manages virtual machines and related compute resources

# ============================================================================
# NETWORK INTERFACES
# ============================================================================

# Network Interface for NVA
resource "azurerm_network_interface" "nic_nva" {
  count                 = var.deploy_route_server && var.deploy_linux_nva ? 1 : 0
  name                  = "nic-nva-${var.project_name}-${var.environment}"
  location              = var.location
  resource_group_name   = var.resource_group_name
  ip_forwarding_enabled = true

  ip_configuration {
    name                          = "internal"
    subnet_id                     = var.nva_subnet_id
    private_ip_address_allocation = "Dynamic"
  }

  tags = var.tags
}

# Network Interface for Squid Proxy
resource "azurerm_network_interface" "nic_squid" {
  count               = var.deploy_squid_proxy ? 1 : 0
  name                = "nic-squid-${var.project_name}-${var.environment}"
  location            = var.location
  resource_group_name = var.resource_group_name

  ip_configuration {
    name                          = "internal"
    subnet_id                     = var.squid_subnet_id
    private_ip_address_allocation = "Dynamic"
  }

  tags = var.tags
}

# Network Interface for On-premises Windows Server 2025
resource "azurerm_network_interface" "nic_onprem_windows_2025" {
  count               = var.deploy_onprem_vnet && var.deploy_onprem_windows_server_2025 ? 1 : 0
  name                = "nic-onprem-windows-2025-${var.project_name}-${var.environment}"
  location            = var.location
  resource_group_name = var.resource_group_name

  ip_configuration {
    name                          = "internal"
    subnet_id                     = var.onprem_workload_subnet_id
    private_ip_address_allocation = "Dynamic"
  }

  tags = var.tags
}

# Public IP for Windows Server 2016 VM
resource "azurerm_public_ip" "pip_onprem_windows_2016" {
  count               = var.deploy_onprem_vnet && var.deploy_onprem_windows_server_2016 ? 1 : 0
  name                = "pip-onprem-windows-2016-${var.project_name}-${var.environment}"
  location            = var.location
  resource_group_name = var.resource_group_name
  allocation_method   = "Static"
  sku                 = "Standard"

  tags = merge(var.tags, {
    Purpose = "Windows Server 2016 VM Access"
  })
}

# Network Interface for On-premises Windows Server 2016
resource "azurerm_network_interface" "nic_onprem_windows_2016" {
  count               = var.deploy_onprem_vnet && var.deploy_onprem_windows_server_2016 ? 1 : 0
  name                = "nic-onprem-windows-2016-${var.project_name}-${var.environment}"
  location            = var.location
  resource_group_name = var.resource_group_name

  ip_configuration {
    name                          = "internal"
    subnet_id                     = var.onprem_workload_subnet_id
    private_ip_address_allocation = "Dynamic"
    public_ip_address_id          = azurerm_public_ip.pip_onprem_windows_2016[0].id
  }

  tags = var.tags
}

# ============================================================================
# NETWORK SECURITY GROUP ASSOCIATIONS
# ============================================================================

# Associate NSG to NVA Network Interface
resource "azurerm_network_interface_security_group_association" "nsg_nic_nva" {
  count                     = (var.deploy_route_server && var.deploy_linux_nva && length(var.nva_nsg_id) > 0) ? 1 : 0
  network_interface_id      = azurerm_network_interface.nic_nva[0].id
  network_security_group_id = var.nva_nsg_id
}

# Associate NSG to Squid Network Interface
resource "azurerm_network_interface_security_group_association" "nsg_nic_squid" {
  count                     = (var.deploy_squid_proxy && length(var.squid_nsg_id) > 0) ? 1 : 0
  network_interface_id      = azurerm_network_interface.nic_squid[0].id
  network_security_group_id = var.squid_nsg_id
}

# Associate NSG to On-premises Windows 2025 Network Interface
resource "azurerm_network_interface_security_group_association" "nsg_nic_onprem_windows_2025" {
  count                     = (var.deploy_onprem_vnet && var.deploy_onprem_windows_server_2025 && length(var.onprem_windows_nsg_id) > 0) ? 1 : 0
  network_interface_id      = azurerm_network_interface.nic_onprem_windows_2025[0].id
  network_security_group_id = var.onprem_windows_nsg_id
}

# Associate NSG to On-premises Windows 2016 Network Interface
resource "azurerm_network_interface_security_group_association" "nsg_nic_onprem_windows_2016" {
  count                     = (var.deploy_onprem_vnet && var.deploy_onprem_windows_server_2016 && length(var.onprem_windows_nsg_id) > 0) ? 1 : 0
  network_interface_id      = azurerm_network_interface.nic_onprem_windows_2016[0].id
  network_security_group_id = var.onprem_windows_nsg_id
}

# ============================================================================
# LINUX VIRTUAL MACHINES
# ============================================================================

# NVA Linux Virtual Machine
resource "azurerm_linux_virtual_machine" "vm_nva" {
  count               = var.deploy_route_server && var.deploy_linux_nva ? 1 : 0
  name                = "vm-nva-${var.project_name}-${var.environment}"
  location            = var.location
  resource_group_name = var.resource_group_name
  size                = var.nva_vm_size
  admin_username      = var.nva_admin_username

  disable_password_authentication = false

  network_interface_ids = [
    azurerm_network_interface.nic_nva[0].id,
  ]

  os_disk {
    caching              = "ReadWrite"
    storage_account_type = "Standard_LRS"
  }

  source_image_reference {
    publisher = "Canonical"
    offer     = "0001-com-ubuntu-server-focal"
    sku       = "20_04-lts-gen2"
    version   = "latest"
  }

  admin_password = var.nva_admin_password

  custom_data = base64encode(templatefile("${path.root}/scripts/nva/nva-config.sh", {
    bgp_asn               = var.nva_bgp_asn
    route_server_ip_1     = var.route_server_ip_1
    route_server_ip_2     = var.route_server_ip_2
    nva_private_ip        = azurerm_network_interface.nic_nva[0].private_ip_address
    bgp_advertised_routes = join(" ", var.nva_bgp_advertised_routes)
    nva_admin_username    = var.nva_admin_username
  }))

  tags = var.tags
}

# Squid Proxy Linux Virtual Machine
resource "azurerm_linux_virtual_machine" "vm_squid" {
  count               = var.deploy_squid_proxy ? 1 : 0
  name                = "vm-squid-${var.project_name}-${var.environment}"
  location            = var.location
  resource_group_name = var.resource_group_name
  size                = var.squid_vm_size
  admin_username      = var.squid_admin_username

  disable_password_authentication = false

  network_interface_ids = [
    azurerm_network_interface.nic_squid[0].id,
  ]

  os_disk {
    caching              = "ReadWrite"
    storage_account_type = "Standard_LRS"
  }

  source_image_reference {
    publisher = "Canonical"
    offer     = "0001-com-ubuntu-server-focal"
    sku       = "20_04-lts-gen2"
    version   = "latest"
  }

  admin_password = var.squid_admin_password

  custom_data = base64encode(templatefile("${path.root}/scripts/squid/squid-config.sh", {
    squid_admin_username = var.squid_admin_username
  }))

  tags = var.tags

  depends_on = [
    azurerm_network_interface.nic_squid
  ]
}

# ============================================================================
# WINDOWS VIRTUAL MACHINES
# ============================================================================

# On-premises Windows Server Virtual Machine
resource "azurerm_windows_virtual_machine" "vm_onprem_windows_2025" {
  count               = var.deploy_onprem_vnet && var.deploy_onprem_windows_server_2025 ? 1 : 0
  name                = "vm-onprem-win2025-${var.project_name}-${var.environment}"
  computer_name       = "WIN2025"
  location            = var.location
  resource_group_name = var.resource_group_name
  size                = var.onprem_windows_vm_size
  admin_username      = var.onprem_windows_admin_username
  admin_password      = var.onprem_windows_admin_password

  # Windows Server 2025 Azure Edition requires AutomaticByPlatform for hotpatching
  patch_mode          = "AutomaticByPlatform"
  hotpatching_enabled = true

  network_interface_ids = [
    azurerm_network_interface.nic_onprem_windows_2025[0].id,
  ]

  os_disk {
    caching              = "ReadWrite"
    storage_account_type = "Standard_LRS"
  }

  source_image_reference {
    publisher = "MicrosoftWindowsServer"
    offer     = "WindowsServer"
    sku       = "2025-datacenter-azure-edition"
    version   = "latest"
  }

  identity {
    type = "SystemAssigned"
  }

  tags = var.tags
}

# On-premises Windows Server 2016 Virtual Machine
resource "azurerm_windows_virtual_machine" "vm_onprem_windows_2016" {
  count               = var.deploy_onprem_vnet && var.deploy_onprem_windows_server_2016 ? 1 : 0
  name                = "vm-onprem-win2016-${var.project_name}-${var.environment}"
  computer_name       = "WIN2016"
  location            = var.location
  resource_group_name = var.resource_group_name
  size                = var.onprem_windows_vm_size
  admin_username      = var.onprem_windows_admin_username
  admin_password      = var.onprem_windows_admin_password

  network_interface_ids = [
    azurerm_network_interface.nic_onprem_windows_2016[0].id,
  ]

  os_disk {
    caching              = "ReadWrite"
    storage_account_type = "Standard_LRS"
  }

  source_image_reference {
    publisher = "MicrosoftWindowsServer"
    offer     = "WindowsServer"
    sku       = "2016-Datacenter"
    version   = "latest"
  }

  identity {
    type = "SystemAssigned"
  }

  tags = var.tags
}

# ============================================================================
# VIRTUAL MACHINE EXTENSIONS
# ============================================================================

