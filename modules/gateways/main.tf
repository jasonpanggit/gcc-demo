# ============================================================================
# GATEWAYS MODULE
# ============================================================================
# This module manages VPN and ExpressRoute gateway resources

# ============================================================================
# EXPRESSROUTE GATEWAY
# ============================================================================

# Public IP for ExpressRoute Gateway
resource "azurerm_public_ip" "pip_expressroute_gateway" {
  count               = var.deploy_hub_vnet && var.deploy_expressroute_gateway ? 1 : 0
  name                = "pip-vgw-er-${var.project_name}-${var.environment}"
  location            = var.location
  resource_group_name = var.resource_group_name
  allocation_method   = "Static"
  sku                 = "Standard"

  tags = merge(var.tags, {
    Purpose = "ExpressRoute Gateway"
  })
}

resource "azurerm_virtual_network_gateway" "vgw_er" {
  count               = var.deploy_hub_vnet && var.deploy_expressroute_gateway ? 1 : 0
  name                = "vgw-er-${var.project_name}-${var.environment}"
  location            = var.location
  resource_group_name = var.resource_group_name

  type     = "ExpressRoute"
  vpn_type = "RouteBased"
  sku      = var.expressroute_gateway_sku

  ip_configuration {
    name                          = "vnetGatewayConfig"
    public_ip_address_id          = azurerm_public_ip.pip_expressroute_gateway[0].id
    private_ip_address_allocation = "Dynamic"
    subnet_id                     = var.gateway_subnet_id
  }

  dynamic "bgp_settings" {
    for_each = var.enable_expressroute_gateway_bgp ? [1] : []
    content {
      asn = var.expressroute_gateway_bgp_asn
    }
  }

  # Explicit timeouts for operations
  timeouts {
    create = "1h30m"
    update = "2h"
    delete = "30m"
  }

  tags = var.tags
}

# ============================================================================
# VPN GATEWAY
# ============================================================================

# Public IP for VPN Gateway
resource "azurerm_public_ip" "pip_vpn_gateway" {
  count               = var.deploy_hub_vnet && var.deploy_vpn_gateway ? 1 : 0
  name                = "pip-vpn-${var.project_name}-${var.environment}"
  location            = var.location
  resource_group_name = var.resource_group_name
  allocation_method   = "Static"
  sku                 = "Standard"

  tags = var.tags
}

# Site-to-Site VPN Virtual Network Gateway
resource "azurerm_virtual_network_gateway" "vgw_vpn" {
  count               = var.deploy_hub_vnet && var.deploy_vpn_gateway ? 1 : 0
  name                = "vgw-vpn-${var.project_name}-${var.environment}"
  location            = var.location
  resource_group_name = var.resource_group_name

  type     = "Vpn"
  vpn_type = "RouteBased"
  sku      = var.vpn_gateway_sku

  ip_configuration {
    name                          = "vnetGatewayConfig"
    public_ip_address_id          = azurerm_public_ip.pip_vpn_gateway[0].id
    private_ip_address_allocation = "Dynamic"
    subnet_id                     = var.gateway_subnet_id
  }

  dynamic "bgp_settings" {
    for_each = var.enable_vpn_gateway_bgp && var.vpn_gateway_sku != "Basic" ? [1] : []
    content {
      asn = var.vpn_gateway_bgp_asn
    }
  }

  # Explicit timeouts for operations
  timeouts {
    create = "1h30m"
    update = "2h"
    delete = "30m"
  }

  tags = var.tags
}

# ============================================================================
# EXPRESSROUTE CIRCUIT
# ============================================================================

# ExpressRoute Circuit
resource "azurerm_express_route_circuit" "erc_hub" {
  count                 = var.deploy_expressroute_gateway ? 1 : 0
  name                  = "erc-${var.project_name}-${var.environment}"
  resource_group_name   = var.resource_group_name
  location              = var.location
  service_provider_name = var.express_route_circuit_service_provider
  peering_location      = var.express_route_circuit_peering_location
  bandwidth_in_mbps     = var.express_route_circuit_bandwidth

  sku {
    tier   = "Standard"
    family = "MeteredData"
  }

  tags = var.tags
}

# ExpressRoute Circuit Peering
resource "azurerm_express_route_circuit_peering" "ercp_hub" {
  count                         = var.deploy_expressroute_gateway ? 1 : 0
  peering_type                  = "AzurePrivatePeering"
  express_route_circuit_name    = azurerm_express_route_circuit.erc_hub[0].name
  resource_group_name           = var.resource_group_name
  peer_asn                      = 100
  primary_peer_address_prefix   = "192.168.1.0/30"
  secondary_peer_address_prefix = "192.168.2.0/30"
  vlan_id                       = 100
}

# ExpressRoute Connection
resource "azurerm_virtual_network_gateway_connection" "conn_er" {
  count               = var.deploy_expressroute_gateway && var.deploy_expressroute_connection ? 1 : 0
  name                = "conn-er-${var.project_name}-${var.environment}"
  location            = var.location
  resource_group_name = var.resource_group_name

  type                       = "ExpressRoute"
  virtual_network_gateway_id = azurerm_virtual_network_gateway.vgw_er[0].id
  express_route_circuit_id   = azurerm_express_route_circuit.erc_hub[0].id

  tags = var.tags

  depends_on = [
    azurerm_express_route_circuit_peering.ercp_hub
  ]
}

# ============================================================================
# SITE-TO-SITE VPN CONNECTION
# ============================================================================

# Public IP for on-premises VPN (simulated)
resource "azurerm_public_ip" "pip_onprem_vpn" {
  count               = var.deploy_onprem_vnet && var.deploy_vpn_gateway && var.onprem_windows_vpn_setup ? 1 : 0
  name                = "pip-onprem-vpn-${var.project_name}-${var.environment}"
  location            = var.location
  resource_group_name = var.resource_group_name
  allocation_method   = "Static"
  sku                 = "Standard"

  tags = var.tags
}

# Local Network Gateway (represents on-premises VPN endpoint)
resource "azurerm_local_network_gateway" "lng_onprem" {
  count               = var.deploy_onprem_vnet && var.deploy_vpn_gateway && var.onprem_windows_vpn_setup ? 1 : 0
  name                = "lng-onprem-${var.project_name}-${var.environment}"
  location            = var.location
  resource_group_name = var.resource_group_name
  gateway_address     = azurerm_public_ip.pip_onprem_vpn[0].ip_address
  address_space       = var.onprem_vnet_address_space

  dynamic "bgp_settings" {
    for_each = var.enable_local_network_gateway_bgp ? [1] : []
    content {
      asn                 = var.local_network_gateway_bgp_asn
      bgp_peering_address = var.onprem_windows_2016_private_ip
    }
  }

  tags = var.tags

  depends_on = [
    azurerm_public_ip.pip_onprem_vpn
  ]
}

# Site-to-Site VPN Connection
resource "azurerm_virtual_network_gateway_connection" "conn_s2s_vpn" {
  count               = var.deploy_onprem_vnet && var.deploy_vpn_gateway && var.onprem_windows_vpn_setup ? 1 : 0
  name                = "conn-s2s-vpn-${var.project_name}-${var.environment}"
  location            = var.location
  resource_group_name = var.resource_group_name

  type                       = "IPsec"
  virtual_network_gateway_id = azurerm_virtual_network_gateway.vgw_vpn[0].id
  local_network_gateway_id   = azurerm_local_network_gateway.lng_onprem[0].id
  shared_key                 = var.onprem_vpn_shared_key
  enable_bgp                 = var.enable_local_network_gateway_bgp

  # IPSec Policy for IKEv2/PSK compatibility with Windows Server 2025
  #   ipsec_policy {
  #     dh_group         = "DHGroup14"
  #     ike_encryption   = "AES256"
  #     ike_integrity    = "SHA256"
  #     ipsec_encryption = "AES256"
  #     ipsec_integrity  = "SHA256"
  #     pfs_group        = "PFS2048"
  #     sa_datasize      = 102400000
  #     sa_lifetime      = 28800
  #   }

  tags = var.tags

  depends_on = [
    azurerm_virtual_network_gateway.vgw_vpn,
    azurerm_local_network_gateway.lng_onprem
  ]
}
