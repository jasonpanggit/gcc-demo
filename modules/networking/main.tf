# ============================================================================
# HUB VIRTUAL NETWORK AND SUBNETS
# ============================================================================

# Virtual Network
resource "azurerm_virtual_network" "vnet_hub" {
  name                = "vnet-hub-${var.project_name}-${var.environment}"
  location            = var.location
  resource_group_name = var.resource_group_name
  address_space       = var.hub_vnet_address_space

  tags = {
    Environment = var.environment
    Project     = var.project_name
  }
}

# Gateway Subnet
resource "azurerm_subnet" "snet_gateway" {
  count                = (var.deploy_expressroute_gateway || var.deploy_vpn_gateway) ? 1 : 0
  name                 = "GatewaySubnet"
  resource_group_name  = var.resource_group_name
  virtual_network_name = azurerm_virtual_network.vnet_hub.name
  address_prefixes     = [var.hub_gateway_subnet_prefix]
}

# Azure Firewall Subnet
resource "azurerm_subnet" "snet_afw_hub" {
  count                = var.deploy_hub_firewall ? 1 : 0
  name                 = "AzureFirewallSubnet"
  resource_group_name  = var.resource_group_name
  virtual_network_name = azurerm_virtual_network.vnet_hub.name
  address_prefixes     = [var.hub_firewall_subnet_prefix]
}

# Route Server Subnet
resource "azurerm_subnet" "snet_rs" {
  count                = var.deploy_route_server ? 1 : 0
  name                 = "RouteServerSubnet"
  resource_group_name  = var.resource_group_name
  virtual_network_name = azurerm_virtual_network.vnet_hub.name
  address_prefixes     = [var.hub_route_server_subnet_prefix]
}

# NVA Subnet
resource "azurerm_subnet" "snet_nva" {
  count                = var.deploy_linux_nva ? 1 : 0
  name                 = "snet-nva-${var.project_name}-${var.environment}"
  resource_group_name  = var.resource_group_name
  virtual_network_name = azurerm_virtual_network.vnet_hub.name
  address_prefixes     = [var.hub_nva_subnet_prefix]
}

# Azure Bastion Subnet
resource "azurerm_subnet" "snet_bastion" {
  count                = var.deploy_bastion ? 1 : 0
  name                 = "AzureBastionSubnet"
  resource_group_name  = var.resource_group_name
  virtual_network_name = azurerm_virtual_network.vnet_hub.name
  address_prefixes     = [var.hub_bastion_subnet_prefix]
}

# Squid Proxy Subnet
resource "azurerm_subnet" "snet_squid" {
  count                = var.deploy_squid_proxy ? 1 : 0
  name                 = "snet-squid-${var.project_name}-${var.environment}"
  resource_group_name  = var.resource_group_name
  virtual_network_name = azurerm_virtual_network.vnet_hub.name
  address_prefixes     = [var.hub_squid_subnet_prefix]
}

# Private Endpoint Subnet
resource "azurerm_subnet" "snet_pe" {
  count                = var.deploy_arc_private_link_scope || var.deploy_azure_monitor_private_link_scope ? 1 : 0
  name                 = "snet-pe-${var.project_name}-${var.environment}"
  resource_group_name  = var.resource_group_name
  virtual_network_name = azurerm_virtual_network.vnet_hub.name
  address_prefixes     = [var.hub_private_endpoint_subnet_prefix]
}

# ============================================================================
# ROUTE SERVER
# ============================================================================

# Public IP for Route Server
resource "azurerm_public_ip" "pip_rs" {
  count               = var.deploy_hub_vnet && var.deploy_route_server ? 1 : 0
  name                = "pip-rs-${var.project_name}-${var.environment}"
  location            = var.location
  resource_group_name = var.resource_group_name
  allocation_method   = "Static"
  sku                 = "Standard"

  tags = {
    Environment = var.environment
    Project     = var.project_name
  }

  depends_on = [
    azurerm_subnet.snet_rs
  ]
}

# Route Server
resource "azurerm_route_server" "rs_hub" {
  count                            = var.deploy_hub_vnet && var.deploy_route_server ? 1 : 0
  name                             = "rs-${var.project_name}-${var.environment}"
  resource_group_name              = var.resource_group_name
  location                         = var.location
  sku                              = "Standard"
  public_ip_address_id             = azurerm_public_ip.pip_rs[0].id
  subnet_id                        = azurerm_subnet.snet_rs[0].id
  branch_to_branch_traffic_enabled = var.route_server_branch_to_branch

  tags = {
    Environment = var.environment
    Project     = var.project_name
  }

  depends_on = [
    azurerm_subnet.snet_rs
  ]
}

# ============================================================================
# AZURE BASTION
# ============================================================================

# Azure Bastion Public IP
resource "azurerm_public_ip" "pip_bastion" {
  count               = var.deploy_bastion ? 1 : 0
  name                = "pip-bastion-${var.project_name}-${var.environment}"
  location            = var.location
  resource_group_name = var.resource_group_name
  allocation_method   = "Static"
  sku                 = "Standard"

  tags = {
    Environment = var.environment
    Project     = var.project_name
  }
}

# Azure Bastion Host
resource "azurerm_bastion_host" "bas_hub" {
  count               = var.deploy_bastion ? 1 : 0
  name                = "bas-${var.project_name}-${var.environment}"
  location            = var.location
  resource_group_name = var.resource_group_name
  sku                 = "Standard"

  ip_configuration {
    name                 = "configuration"
    subnet_id            = azurerm_subnet.snet_bastion[0].id
    public_ip_address_id = azurerm_public_ip.pip_bastion[0].id
  }

  tags = {
    Environment = var.environment
    Project     = var.project_name
  }

  depends_on = [
    azurerm_subnet.snet_bastion
  ]
}

# ============================================================================
# NETWORK SECURITY GROUPS
# ============================================================================

# Network Security Group for NVA
resource "azurerm_network_security_group" "nsg_nva" {
  # NSG creation disabled
  count               = 0
  name                = "nsg-nva-${var.project_name}-${var.environment}"
  location            = var.location
  resource_group_name = var.resource_group_name

  security_rule {
    name                       = "AllowSSH"
    priority                   = 1001
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "22"
    source_address_prefix      = "VirtualNetwork"
    destination_address_prefix = "*"
  }

  security_rule {
    name                       = "AllowBGP"
    priority                   = 1002
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "179"
    source_address_prefix      = "VirtualNetwork"
    destination_address_prefix = "*"
  }

  security_rule {
    name                       = "AllowICMP"
    priority                   = 1003
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Icmp"
    source_port_range          = "*"
    destination_port_range     = "*"
    source_address_prefix      = "VirtualNetwork"
    destination_address_prefix = "*"
  }

  tags = {
    Environment = var.environment
    Project     = var.project_name
  }
}

# Network Security Group for Squid Proxy
resource "azurerm_network_security_group" "nsg_squid" {
  # NSG creation disabled
  count               = 0
  name                = "nsg-squid-${var.project_name}-${var.environment}"
  location            = var.location
  resource_group_name = var.resource_group_name

  security_rule {
    name                       = "Allow_SSH"
    priority                   = 100
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "22"
    source_address_prefix      = "VirtualNetwork"
    destination_address_prefix = "*"
  }

  security_rule {
    name                       = "Allow_Squid_Proxy"
    priority                   = 110
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "3128"
    source_address_prefix      = "VirtualNetwork"
    destination_address_prefix = "*"
  }

  security_rule {
    name                       = "Allow_ICMP"
    priority                   = 120
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Icmp"
    source_port_range          = "*"
    destination_port_range     = "*"
    source_address_prefix      = "VirtualNetwork"
    destination_address_prefix = "*"
  }

  tags = {
    Environment = var.environment
    Project     = var.project_name
  }
}

# NSG-Subnet Associations
resource "azurerm_subnet_network_security_group_association" "snsga_nva" {
  # NSG association disabled
  count                     = 0
  subnet_id                 = azurerm_subnet.snet_nva[0].id
  network_security_group_id = azurerm_network_security_group.nsg_nva[0].id
}

resource "azurerm_subnet_network_security_group_association" "snsga_squid" {
  # NSG association disabled
  count                     = 0
  subnet_id                 = azurerm_subnet.snet_squid[0].id
  network_security_group_id = azurerm_network_security_group.nsg_squid[0].id
}

# ============================================================================
# ROUTE TABLES
# ============================================================================
# ROUTE TABLES MOVED TO ROUTING MODULE
# ============================================================================
# All route table configurations have been moved to the routing module
# to resolve dependency issues with firewall IP addresses.
# The routing module is deployed after the firewall module to use actual IPs.

# ============================================================================
# SPOKE NETWORKS - NON-GEN VNET
# ============================================================================

# Non-Gen Virtual Network
resource "azurerm_virtual_network" "vnet_nongen" {
  count               = var.deploy_nongen_vnet ? 1 : 0
  name                = "vnet-nongen-${var.project_name}-${var.environment}"
  location            = var.location
  resource_group_name = var.resource_group_name
  address_space       = var.nongen_vnet_address_space

  tags = {
    Environment = var.environment
    Project     = var.project_name
    Purpose     = "Non-Gen Network"
  }
}

# Non-Gen Azure Firewall Subnet
resource "azurerm_subnet" "snet_afw_nongen" {
  count                = var.deploy_nongen_vnet && var.deploy_nongen_firewall ? 1 : 0
  name                 = "AzureFirewallSubnet"
  resource_group_name  = var.resource_group_name
  virtual_network_name = azurerm_virtual_network.vnet_nongen[0].name
  address_prefixes     = [var.nongen_firewall_subnet_prefix]
}

# Non-Gen Azure Firewall Subnet
resource "azurerm_subnet" "snet_avd_nongen" {
  count                = var.deploy_nongen_vnet && var.deploy_nongen_avd ? 1 : 0
  name                 = "AvdSubnet"
  resource_group_name  = var.resource_group_name
  virtual_network_name = azurerm_virtual_network.vnet_nongen[0].name
  address_prefixes     = [var.nongen_avd_subnet_prefix]
}

# Non-Gen Private Endpoint Subnet (shared for PEs like AOAI/Search)
resource "azurerm_subnet" "snet_nongen_pe" {
  count                             = (var.deploy_nongen_vnet && var.deploy_agentic_app) ? 1 : 0
  name                              = "snet-nongen-pe-${var.project_name}-${var.environment}"
  resource_group_name               = var.resource_group_name
  virtual_network_name              = azurerm_virtual_network.vnet_nongen[0].name
  address_prefixes                  = [var.nongen_private_endpoint_subnet_prefix]
  private_endpoint_network_policies = "Disabled"
}

# Non-Gen App Service VNet Integration Subnet
resource "azurerm_subnet" "snet_nongen_appsvc" {
  count                = (var.deploy_nongen_vnet && var.deploy_agentic_app) ? 1 : 0
  name                 = "snet-nongen-appsvc-${var.project_name}-${var.environment}"
  resource_group_name  = var.resource_group_name
  virtual_network_name = azurerm_virtual_network.vnet_nongen[0].name
  address_prefixes     = [var.nongen_app_subnet_prefix]
  service_endpoints    = ["Microsoft.CognitiveServices"]
  delegation {
    name = "appservice-delegation"
    service_delegation {
      name = "Microsoft.Web/serverFarms"
      actions = [
        "Microsoft.Network/virtualNetworks/subnets/action",
      ]
    }
  }
}

# Non-Gen Container Apps Subnet
resource "azurerm_subnet" "snet_nongen_container_apps" {
  count                = (var.deploy_nongen_vnet && var.deploy_container_apps) ? 1 : 0
  name                 = "snet-nongen-containerapps-${var.project_name}-${var.environment}"
  resource_group_name  = var.resource_group_name
  virtual_network_name = azurerm_virtual_network.vnet_nongen[0].name
  address_prefixes     = [var.nongen_container_apps_subnet_prefix]
  
  # Delegation required for Container Apps Environment
  delegation {
    name = "containerapps-delegation"
    service_delegation {
      name = "Microsoft.App/environments"
      actions = [
        "Microsoft.Network/virtualNetworks/subnets/join/action",
      ]
    }
  }
}

# Non-Gen API Management Subnet (reserved for future use)
resource "azurerm_subnet" "snet_nongen_apim" {
  count                = (var.deploy_nongen_vnet && var.deploy_agentic_app && var.nongen_apim_subnet_prefix != null) ? 1 : 0
  name                 = "snet-nongen-apim-${var.project_name}-${var.environment}"
  resource_group_name  = var.resource_group_name
  virtual_network_name = azurerm_virtual_network.vnet_nongen[0].name
  address_prefixes     = [var.nongen_apim_subnet_prefix]
}

# ============================================================================
# SPOKE NETWORKS - GEN VNET
# ============================================================================

# Gen Virtual Network
resource "azurerm_virtual_network" "vnet_gen" {
  count               = var.deploy_gen_vnet ? 1 : 0
  name                = "vnet-gen-${var.project_name}-${var.environment}"
  location            = var.location
  resource_group_name = var.resource_group_name
  address_space       = var.gen_vnet_address_space

  tags = {
    Environment = var.environment
    Project     = var.project_name
    Purpose     = "Gen Network"
  }
}

# Gen Workload Subnet
resource "azurerm_subnet" "snet_gen_workload" {
  count                = var.deploy_gen_vnet ? 1 : 0
  name                 = "snet-workload-gen-${var.project_name}-${var.environment}"
  resource_group_name  = var.resource_group_name
  virtual_network_name = azurerm_virtual_network.vnet_gen[0].name
  address_prefixes     = [var.gen_workload_subnet_prefix]
}

# ============================================================================
# SPOKE NETWORKS - ON-PREMISES VNET
# ============================================================================

# On-premises Virtual Network (simulation)
resource "azurerm_virtual_network" "vnet_onprem" {
  count               = var.deploy_onprem_vnet ? 1 : 0
  name                = "vnet-onprem-${var.project_name}-${var.environment}"
  location            = var.location
  resource_group_name = var.resource_group_name
  address_space       = var.onprem_vnet_address_space

  tags = {
    Environment = var.environment
    Project     = var.project_name
    Purpose     = "On-premises Simulation"
  }
}

# On-premises Workload Subnet
resource "azurerm_subnet" "snet_onprem_workload" {
  count                = var.deploy_onprem_vnet ? 1 : 0
  name                 = "snet-workload-onprem-${var.project_name}-${var.environment}"
  resource_group_name  = var.resource_group_name
  virtual_network_name = azurerm_virtual_network.vnet_onprem[0].name
  address_prefixes     = [var.onprem_workload_subnet_prefix]
}

# Network Security Group for on-premises Windows Server
resource "azurerm_network_security_group" "nsg_onprem_windows" {
  # NSG creation disabled
  count               = 0
  name                = "nsg-onprem-windows-${var.project_name}-${var.environment}"
  location            = var.location
  resource_group_name = var.resource_group_name

  # INBOUND RULES - Only allow from internal networks
  security_rule {
    name                       = "Allow-RDP-From-Bastion"
    priority                   = 1001
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "3389"
    source_address_prefix      = var.hub_bastion_subnet_prefix
    destination_address_prefix = "*"
  }

  security_rule {
    name                       = "Allow-RDP-From-OnPrem"
    priority                   = 1002
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "3389"
    source_address_prefix      = var.onprem_vnet_address_space[0]
    destination_address_prefix = "*"
  }

  security_rule {
    name                       = "Allow-WinRM-From-OnPrem"
    priority                   = 1003
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_ranges    = ["5985", "5986"]
    source_address_prefix      = var.onprem_vnet_address_space[0]
    destination_address_prefix = "*"
  }

  security_rule {
    name                       = "Allow-ICMP-From-Internal"
    priority                   = 1004
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Icmp"
    source_port_range          = "*"
    destination_port_range     = "*"
    source_address_prefixes    = concat(var.hub_vnet_address_space, var.onprem_vnet_address_space)
    destination_address_prefix = "*"
  }

  security_rule {
    name                       = "Deny-All-Internet-Inbound"
    priority                   = 4000
    direction                  = "Inbound"
    access                     = "Deny"
    protocol                   = "*"
    source_port_range          = "*"
    destination_port_range     = "*"
    source_address_prefix      = "Internet"
    destination_address_prefix = "*"
  }

  # OUTBOUND RULES - Only allow to internal networks and specific Azure services
  security_rule {
    name                         = "Allow-DNS-To-Hub"
    priority                     = 1001
    direction                    = "Outbound"
    access                       = "Allow"
    protocol                     = "Udp"
    source_port_range            = "*"
    destination_port_range       = "53"
    source_address_prefix        = "*"
    destination_address_prefixes = var.hub_vnet_address_space
  }

  security_rule {
    name                         = "Allow-Internal-Communication"
    priority                     = 1002
    direction                    = "Outbound"
    access                       = "Allow"
    protocol                     = "*"
    source_port_range            = "*"
    destination_port_range       = "*"
    source_address_prefix        = "*"
    destination_address_prefixes = concat(var.hub_vnet_address_space, var.onprem_vnet_address_space)
  }

  security_rule {
    name                       = "Allow-HTTPS-To-Firewall-Proxy"
    priority                   = 1003
    direction                  = "Outbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_ranges    = ["443", "8443"]
    source_address_prefix      = "*"
    destination_address_prefix = var.hub_firewall_subnet_prefix
  }

  security_rule {
    name                       = "Allow-All-To-Firewall-Proxy"
    priority                   = 1004
    direction                  = "Outbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_ranges    = ["80", "443", "8080", "8443"]
    source_address_prefix      = "*"
    destination_address_prefix = var.hub_firewall_subnet_prefix
  }

  security_rule {
    name                       = "Allow-HTTP-Internet-Outbound"
    priority                   = 1005
    direction                  = "Outbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "80"
    source_address_prefix      = "*"
    destination_address_prefix = "Internet"
  }

  security_rule {
    name                       = "Allow-HTTPS-Internet-Outbound"
    priority                   = 1006
    direction                  = "Outbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "443"
    source_address_prefix      = "*"
    destination_address_prefix = "Internet"
  }

  security_rule {
    name                       = "Allow-All-Azure-Services"
    priority                   = 1007
    direction                  = "Outbound"
    access                     = "Allow"
    protocol                   = "*"
    source_port_range          = "*"
    destination_port_range     = "*"
    source_address_prefix      = "*"
    destination_address_prefix = "AzureCloud"
  }

  tags = {
    Environment = var.environment
    Project     = var.project_name
    Purpose     = "On-premises Windows Server Security - No Internet Access"
  }
}

# ============================================================================
# VNET PEERINGS
# ============================================================================

# VNet Peering from Hub to Non-Gen
resource "azurerm_virtual_network_peering" "peer_hub_to_nongen" {
  count                        = var.deploy_hub_vnet && var.deploy_nongen_vnet && var.deploy_hub_nongen_peering ? 1 : 0
  name                         = "peer-hub-to-nongen-${var.project_name}-${var.environment}"
  resource_group_name          = var.resource_group_name
  virtual_network_name         = azurerm_virtual_network.vnet_hub.name
  remote_virtual_network_id    = azurerm_virtual_network.vnet_nongen[0].id
  allow_virtual_network_access = true
  allow_forwarded_traffic      = true
  allow_gateway_transit        = var.deploy_expressroute_gateway ? true : false

  depends_on = [
    azurerm_virtual_network.vnet_nongen
  ]
}

# VNet Peering from Non-Gen to Hub
resource "azurerm_virtual_network_peering" "peer_nongen_to_hub" {
  count                        = var.deploy_hub_vnet && var.deploy_nongen_vnet && var.deploy_hub_nongen_peering ? 1 : 0
  name                         = "peer-nongen-to-hub-${var.project_name}-${var.environment}"
  resource_group_name          = var.resource_group_name
  virtual_network_name         = azurerm_virtual_network.vnet_nongen[0].name
  remote_virtual_network_id    = azurerm_virtual_network.vnet_hub.id
  allow_virtual_network_access = true
  allow_forwarded_traffic      = true
  use_remote_gateways          = var.deploy_expressroute_gateway ? true : false

  depends_on = [
    azurerm_virtual_network_peering.peer_hub_to_nongen,
    azurerm_virtual_network.vnet_nongen
  ]
}

# VNet Peering from Gen to Non-Gen
resource "azurerm_virtual_network_peering" "peer_gen_to_nongen" {
  count                        = var.deploy_gen_vnet && var.deploy_nongen_vnet && var.deploy_gen_nongen_peering ? 1 : 0
  name                         = "peer-gen-to-nongen-${var.project_name}-${var.environment}"
  resource_group_name          = var.resource_group_name
  virtual_network_name         = azurerm_virtual_network.vnet_gen[0].name
  remote_virtual_network_id    = azurerm_virtual_network.vnet_nongen[0].id
  allow_virtual_network_access = true
  allow_forwarded_traffic      = true
  allow_gateway_transit        = false

  depends_on = [
    azurerm_virtual_network.vnet_gen,
    azurerm_virtual_network.vnet_nongen
  ]
}

# VNet Peering from Non-Gen to Gen
resource "azurerm_virtual_network_peering" "peer_nongen_to_gen" {
  count                        = var.deploy_gen_vnet && var.deploy_nongen_vnet && var.deploy_gen_nongen_peering ? 1 : 0
  name                         = "peer-nongen-to-gen-${var.project_name}-${var.environment}"
  resource_group_name          = var.resource_group_name
  virtual_network_name         = azurerm_virtual_network.vnet_nongen[0].name
  remote_virtual_network_id    = azurerm_virtual_network.vnet_gen[0].id
  allow_virtual_network_access = true
  allow_forwarded_traffic      = true
  use_remote_gateways          = false

  depends_on = [
    azurerm_virtual_network_peering.peer_gen_to_nongen,
    azurerm_virtual_network.vnet_gen,
    azurerm_virtual_network.vnet_nongen
  ]
}

# VNet Peering from Hub to Gen
resource "azurerm_virtual_network_peering" "peer_hub_to_gen" {
  count                        = var.deploy_hub_vnet && var.deploy_gen_vnet && var.deploy_hub_gen_peering ? 1 : 0
  name                         = "peer-hub-to-gen-${var.project_name}-${var.environment}"
  resource_group_name          = var.resource_group_name
  virtual_network_name         = azurerm_virtual_network.vnet_hub.name
  remote_virtual_network_id    = azurerm_virtual_network.vnet_gen[0].id
  allow_virtual_network_access = true
  allow_forwarded_traffic      = true
  allow_gateway_transit        = var.deploy_expressroute_gateway ? true : false

  depends_on = [
    azurerm_virtual_network.vnet_gen
  ]
}

# VNet Peering from Gen to Hub
resource "azurerm_virtual_network_peering" "peer_gen_to_hub" {
  count                        = var.deploy_hub_vnet && var.deploy_gen_vnet && var.deploy_hub_gen_peering ? 1 : 0
  name                         = "peer-gen-to-hub-${var.project_name}-${var.environment}"
  resource_group_name          = var.resource_group_name
  virtual_network_name         = azurerm_virtual_network.vnet_gen[0].name
  remote_virtual_network_id    = azurerm_virtual_network.vnet_hub.id
  allow_virtual_network_access = true
  allow_forwarded_traffic      = true
  use_remote_gateways          = var.deploy_expressroute_gateway ? true : false

  depends_on = [
    azurerm_virtual_network_peering.peer_hub_to_gen,
    azurerm_virtual_network.vnet_gen
  ]
}

# VNet Peering from Hub to On-premises
resource "azurerm_virtual_network_peering" "peer_hub_to_onprem" {
  count                        = var.deploy_hub_vnet && var.deploy_onprem_vnet && var.deploy_hub_onprem_peering ? 1 : 0
  name                         = "peer-hub-to-onprem-${var.project_name}-${var.environment}"
  resource_group_name          = var.resource_group_name
  virtual_network_name         = azurerm_virtual_network.vnet_hub.name
  remote_virtual_network_id    = azurerm_virtual_network.vnet_onprem[0].id
  allow_virtual_network_access = true
  allow_forwarded_traffic      = true
  allow_gateway_transit        = var.deploy_expressroute_gateway ? true : false

  depends_on = [
    azurerm_virtual_network.vnet_onprem
  ]
}

# VNet Peering from On-premises to Hub
resource "azurerm_virtual_network_peering" "peer_onprem_to_hub" {
  count                        = var.deploy_hub_vnet && var.deploy_onprem_vnet && var.deploy_hub_onprem_peering ? 1 : 0
  name                         = "peer-onprem-to-hub-${var.project_name}-${var.environment}"
  resource_group_name          = var.resource_group_name
  virtual_network_name         = azurerm_virtual_network.vnet_onprem[0].name
  remote_virtual_network_id    = azurerm_virtual_network.vnet_hub.id
  allow_virtual_network_access = true
  allow_forwarded_traffic      = true
  use_remote_gateways          = var.deploy_expressroute_gateway ? true : false

  depends_on = [
    azurerm_virtual_network_peering.peer_hub_to_onprem,
    azurerm_virtual_network.vnet_onprem
  ]
}
