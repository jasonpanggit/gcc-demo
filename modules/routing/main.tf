# ============================================================================
# ROUTING MODULE - Route Tables and Associations
# ============================================================================
# This module handles all route table configurations that depend on firewall
# IP addresses. It's deployed after the firewall module to use actual IPs.
# ============================================================================

# ============================================================================
# GATEWAY SUBNET ROUTE TABLE
# ============================================================================

# Route Table for Gateway Subnet
resource "azurerm_route_table" "rt_gateway" {
  count               = var.deploy_hub_vnet && (var.deploy_expressroute_gateway || var.deploy_vpn_gateway) ? 1 : 0
  name                = "rt-gateway-${var.project_name}-${var.environment}"
  location            = var.location
  resource_group_name = var.resource_group_name

  # For hub-spoke scenario by using azure route server to advertise routes via bgp using linux nva
  dynamic "route" {
    for_each = var.deploy_hub_firewall && var.deploy_nongen_vnet && var.deploy_nongen_firewall ? var.nva_bgp_advertised_routes : []
    content {
      name                   = "route-${replace(replace(route.value, "/", "-"), ".", "-")}"
      address_prefix         = route.value
      next_hop_type          = "VirtualAppliance"
      next_hop_in_ip_address = var.hub_firewall_private_ip
    }
  }

  # Route Non-Gen VNet traffic through hub firewall
  dynamic "route" {
    for_each = var.deploy_hub_firewall && var.deploy_nongen_vnet && var.deploy_nongen_firewall ? var.nongen_vnet_address_space : []
    content {
      name                   = "route-nongen-${replace(replace(route.value, "/", "-"), ".", "-")}"
      address_prefix         = route.value
      next_hop_type          = "VirtualAppliance"
      next_hop_in_ip_address = var.hub_firewall_private_ip
    }
  }

  # Route Gen VNet traffic through hub firewall
  dynamic "route" {
    for_each = var.deploy_hub_firewall && var.deploy_nongen_vnet && var.deploy_nongen_firewall && var.deploy_gen_vnet ? var.gen_vnet_address_space : []
    content {
      name                   = "route-gen-${replace(replace(route.value, "/", "-"), ".", "-")}"
      address_prefix         = route.value
      next_hop_type          = "VirtualAppliance"
      next_hop_in_ip_address = var.hub_firewall_private_ip
    }
  }

  tags = {
    Environment = var.environment
    Project     = var.project_name
    Purpose     = "Gateway Subnet Routing"
  }
}

# Route Table Association for Gateway Subnet
resource "azurerm_subnet_route_table_association" "srta_gateway" {
  count          = var.deploy_hub_vnet && var.deploy_expressroute_gateway ? 1 : 0
  subnet_id      = var.gateway_subnet_id
  route_table_id = azurerm_route_table.rt_gateway[0].id
}

# ============================================================================
# AZURE FIREWALL SUBNET ROUTE TABLE (FORCE TUNNELING)
# ============================================================================

# Route Table for Azure Firewall (Force Tunneling)
resource "azurerm_route_table" "rt_afw_hub" {
  count               = var.deploy_hub_vnet && var.deploy_hub_firewall && var.hub_firewall_force_tunneling ? 1 : 0
  name                = "rt-firewall-${var.project_name}-${var.environment}"
  location            = var.location
  resource_group_name = var.resource_group_name

  # Azure Firewall subnet requires a default route to Internet when force tunneling is enabled
  route {
    name           = "default-to-internet"
    address_prefix = "0.0.0.0/0"
    next_hop_type  = "Internet"
  }

  tags = {
    Environment = var.environment
    Project     = var.project_name
    Purpose     = "Azure Firewall Force Tunneling"
  }
}

# Associate Route Table with Azure Firewall Subnet (Force Tunneling)
resource "azurerm_subnet_route_table_association" "srta_afw_hub" {
  count          = var.deploy_hub_vnet && var.deploy_hub_firewall && var.hub_firewall_force_tunneling ? 1 : 0
  subnet_id      = var.firewall_subnet_id
  route_table_id = azurerm_route_table.rt_afw_hub[0].id
}

# ============================================================================
# SQUID PROXY SUBNET ROUTE TABLE
# ============================================================================

# Squid Proxy Route Table - Route internet traffic through Hub Firewall
resource "azurerm_route_table" "rt_squid" {
  count               = var.deploy_squid_proxy && var.deploy_hub_firewall ? 1 : 0
  name                = "rt-squid-${var.project_name}-${var.environment}"
  location            = var.location
  resource_group_name = var.resource_group_name

  # Route internet traffic through Hub Firewall
  route {
    name                   = "internet-via-hub-firewall"
    address_prefix         = "0.0.0.0/0"
    next_hop_type          = "VirtualAppliance"
    next_hop_in_ip_address = var.hub_firewall_private_ip
  }

  tags = {
    Environment = var.environment
    Project     = var.project_name
    Purpose     = "Squid Proxy Routing"
  }
}

# Associate Route Table with Squid Proxy Subnet
resource "azurerm_subnet_route_table_association" "srta_squid" {
  count          = var.deploy_squid_proxy && var.deploy_hub_firewall ? 1 : 0
  subnet_id      = var.squid_subnet_id
  route_table_id = azurerm_route_table.rt_squid[0].id
}

# ============================================================================
# GEN WORKLOAD SUBNET ROUTE TABLE
# ============================================================================

# Route Table for Gen Workload Subnet
resource "azurerm_route_table" "rt_gen_workload" {
  count               = var.deploy_gen_vnet && var.deploy_nongen_vnet && var.deploy_nongen_firewall && var.route_internet_to_nongen_firewall ? 1 : 0
  name                = "rt-gen-workload-${var.project_name}-${var.environment}"
  location            = var.location
  resource_group_name = var.resource_group_name

  # Route all traffic through Non-Gen firewall
  route {
    name                   = "default-internet-to-nongen-firewall"
    address_prefix         = "0.0.0.0/0"
    next_hop_type          = "VirtualAppliance"
    next_hop_in_ip_address = var.nongen_firewall_private_ip
  }

  tags = {
    Environment = var.environment
    Project     = var.project_name
    Purpose     = "Gen Workload Routing"
  }
}

# Associate Route Table with Gen Workload Subnet
resource "azurerm_subnet_route_table_association" "srta_gen_workload" {
  count          = var.deploy_gen_vnet && var.deploy_nongen_vnet && var.deploy_nongen_firewall && var.route_internet_to_nongen_firewall ? 1 : 0
  subnet_id      = var.gen_workload_subnet_id
  route_table_id = azurerm_route_table.rt_gen_workload[0].id
}

# ============================================================================
# NONGEN APPSVC INTEGRATION SUBNET ROUTE TABLE
# ============================================================================

resource "azurerm_route_table" "rt_nongen_appsvc" {
  count               = var.deploy_nongen_vnet && var.deploy_nongen_firewall && length(var.nongen_appsvc_integration_subnet_id) > 0 ? 1 : 0
  name                = "rt-nongen-appsvc-${var.project_name}-${var.environment}"
  location            = var.location
  resource_group_name = var.resource_group_name

  route {
    name                   = "default-to-nongen-firewall"
    address_prefix         = "0.0.0.0/0"
    next_hop_type          = "VirtualAppliance"
    next_hop_in_ip_address = var.nongen_firewall_private_ip
  }

  tags = {
    Environment = var.environment
    Project     = var.project_name
    Purpose     = "Non-Gen App Service Egress"
  }
}

resource "azurerm_subnet_route_table_association" "srta_nongen_appsvc" {
  count          = var.deploy_nongen_vnet && var.deploy_nongen_firewall && length(var.nongen_appsvc_integration_subnet_id) > 0 ? 1 : 0
  subnet_id      = var.nongen_appsvc_integration_subnet_id
  route_table_id = azurerm_route_table.rt_nongen_appsvc[0].id
}

# ============================================================================
# NONGEN CONTAINER APPS SUBNET ROUTE TABLE
# ============================================================================

resource "azurerm_route_table" "rt_nongen_container_apps" {
  count               = var.deploy_nongen_vnet && var.deploy_nongen_firewall && length(var.nongen_container_apps_subnet_id) > 0 ? 1 : 0
  name                = "rt-nongen-containerapps-${var.project_name}-${var.environment}"
  location            = var.location
  resource_group_name = var.resource_group_name

  route {
    name                   = "default-to-nongen-firewall"
    address_prefix         = "0.0.0.0/0"
    next_hop_type          = "VirtualAppliance"
    next_hop_in_ip_address = var.nongen_firewall_private_ip
  }

  tags = {
    Environment = var.environment
    Project     = var.project_name
    Purpose     = "Non-Gen Container Apps Egress"
  }
}

resource "azurerm_subnet_route_table_association" "srta_nongen_container_apps" {
  count          = var.deploy_nongen_vnet && var.deploy_nongen_firewall && length(var.nongen_container_apps_subnet_id) > 0 ? 1 : 0
  subnet_id      = var.nongen_container_apps_subnet_id
  route_table_id = azurerm_route_table.rt_nongen_container_apps[0].id
}
