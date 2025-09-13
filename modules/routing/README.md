# Routing Module

This module manages Azure route tables, custom routes, and route associations for controlling traffic flow between virtual networks, on-premises networks, and through network virtual appliances.

## Features

- **Route Tables**: Custom route tables for different subnets
- **User-Defined Routes**: Custom routing through firewalls and NVAs
- **BGP Route Propagation**: Integration with Azure Route Server and NVAs
- **Force Tunneling**: Route all traffic through security appliances
- **Hub-Spoke Routing**: Centralized routing through hub infrastructure
- **Multi-VNet Routing**: Complex routing between Gen, Non-Gen, and Hub VNets
- **On-Premises Integration**: Routes for hybrid connectivity scenarios

## Architecture

### Route Table Types
- **Gateway Route Table**: Routes for VPN and ExpressRoute gateways
- **Workload Route Tables**: Routes for application subnets
- **Firewall Route Tables**: Routes for firewall subnets
- **NVA Route Tables**: Routes for network virtual appliances

### Routing Scenarios
- **Hub-Spoke**: Central hub with firewall routing
- **Multi-Hub**: Multiple hubs with inter-hub connectivity
- **Hybrid**: On-premises integration via VPN/ExpressRoute
- **DMZ**: Dedicated DMZ routing through firewalls

## Usage

```hcl
module "routing" {
  source = "./modules/routing"
  
  project_name        = var.project_name
  environment         = var.environment
  location            = var.location
  resource_group_name = azurerm_resource_group.main.name
  
  # Network Configuration
  deploy_hub_vnet               = var.deploy_hub_vnet
  deploy_gen_vnet               = var.deploy_gen_vnet
  deploy_nongen_vnet            = var.deploy_nongen_vnet
  deploy_onprem_vnet            = var.deploy_onprem_vnet
  
  # Gateway Configuration
  deploy_expressroute_gateway   = var.deploy_expressroute_gateway
  deploy_vpn_gateway            = var.deploy_vpn_gateway
  
  # Firewall Configuration
  deploy_hub_firewall           = var.deploy_hub_firewall
  deploy_nongen_firewall        = var.deploy_nongen_firewall
  hub_firewall_private_ip       = module.firewall.hub_firewall_private_ip
  nongen_firewall_private_ip    = module.firewall.nongen_firewall_private_ip
  
  # NVA Configuration
  deploy_linux_nva              = var.deploy_linux_nva
  nva_private_ip                = module.compute.nva_private_ip
  nva_bgp_advertised_routes     = var.nva_bgp_advertised_routes
  
  # Address Spaces
  hub_vnet_address_space        = var.hub_vnet_address_space
  gen_vnet_address_space        = var.gen_vnet_address_space
  nongen_vnet_address_space     = var.nongen_vnet_address_space
  onprem_vnet_address_space     = var.onprem_vnet_address_space
  
  # Subnet IDs
  hub_gateway_subnet_id         = module.networking.hub_gateway_subnet_id
  gen_workload_subnet_id        = module.networking.gen_workload_subnet_id
  nongen_workload_subnet_id     = module.networking.nongen_workload_subnet_id
  onprem_subnet_id              = module.networking.onprem_subnet_id
  
  tags = var.tags
}
```

## Route Table Configurations

### Gateway Route Table
```hcl
# Routes for VPN/ExpressRoute Gateway subnet
resource "azurerm_route_table" "rt_gateway" {
  name                = "rt-gateway-${var.project_name}-${var.environment}"
  location            = var.location
  resource_group_name = var.resource_group_name

  # Route Non-Gen traffic through hub firewall
  route {
    name                   = "route-nongen-vnet"
    address_prefix         = "100.0.0.0/16"
    next_hop_type          = "VirtualAppliance"
    next_hop_in_ip_address = var.hub_firewall_private_ip
  }
  
  # Route Gen traffic through hub firewall
  route {
    name                   = "route-gen-vnet"
    address_prefix         = "10.0.0.0/16"
    next_hop_type          = "VirtualAppliance"
    next_hop_in_ip_address = var.hub_firewall_private_ip
  }
}
```

### Workload Route Table
```hcl
# Routes for application workload subnets
resource "azurerm_route_table" "rt_workload" {
  name                = "rt-workload-${var.project_name}-${var.environment}"
  location            = var.location
  resource_group_name = var.resource_group_name
  
  # Default route through firewall
  route {
    name                   = "default-via-firewall"
    address_prefix         = "0.0.0.0/0"
    next_hop_type          = "VirtualAppliance"
    next_hop_in_ip_address = var.hub_firewall_private_ip
  }
  
  # On-premises routes
  route {
    name                   = "onprem-networks"
    address_prefix         = "192.168.0.0/16"
    next_hop_type          = "VirtualAppliance"
    next_hop_in_ip_address = var.hub_firewall_private_ip
  }
}
```

## BGP and Dynamic Routing

### Azure Route Server Integration
```hcl
# Enable BGP route propagation
enable_bgp_route_propagation = true

# BGP advertised routes from NVA
nva_bgp_advertised_routes = [
  "192.168.100.0/24",  # On-premises network 1
  "192.168.200.0/24",  # On-premises network 2
  "10.10.0.0/16"       # Additional private network
]
```

### NVA Routing Configuration
```hcl
# Routes through Network Virtual Appliance
route {
  name                   = "nva-advertised-route"
  address_prefix         = "192.168.100.0/24"
  next_hop_type          = "VirtualAppliance"
  next_hop_in_ip_address = var.nva_private_ip
}
```

## Force Tunneling Scenarios

### Hub Firewall Force Tunneling
```hcl
# Force all traffic through hub firewall
resource "azurerm_route_table" "rt_force_tunnel" {
  name                = "rt-force-tunnel-${var.project_name}-${var.environment}"
  location            = var.location
  resource_group_name = var.resource_group_name
  
  route {
    name           = "default-route"
    address_prefix = "0.0.0.0/0"
    next_hop_type  = "VirtualAppliance"
    next_hop_in_ip_address = var.hub_firewall_private_ip
  }
  
  route {
    name           = "internet-route"
    address_prefix = "168.63.129.16/32"  # Azure metadata service
    next_hop_type  = "Internet"
  }
}
```

### On-Premises Force Tunneling
```hcl
# Route internet traffic through on-premises
route {
  name           = "internet-via-onprem"
  address_prefix = "0.0.0.0/0"
  next_hop_type  = "VirtualNetworkGateway"
}
```

## Multi-VNet Routing

### Gen to Non-Gen Communication
```hcl
# Route Gen VNet traffic to Non-Gen through firewall
route {
  name                   = "gen-to-nongen"
  address_prefix         = "100.0.0.0/16"  # Non-Gen VNet
  next_hop_type          = "VirtualAppliance"
  next_hop_in_ip_address = var.hub_firewall_private_ip
}
```

### Hub-Spoke Communication
```hcl
# Route spoke traffic through hub
route {
  name                   = "spoke-to-hub"
  address_prefix         = "172.16.0.0/16"  # Hub VNet
  next_hop_type          = "VNetPeering"
}
```

## Route Table Associations

### Subnet Associations
```hcl
# Associate route table with subnet
resource "azurerm_subnet_route_table_association" "workload" {
  subnet_id      = var.workload_subnet_id
  route_table_id = azurerm_route_table.rt_workload.id
}

# Associate with multiple subnets
resource "azurerm_subnet_route_table_association" "gateway" {
  subnet_id      = var.gateway_subnet_id
  route_table_id = azurerm_route_table.rt_gateway.id
}
```

## Outputs

| Name | Description |
|------|-------------|
| `gateway_route_table_id` | Resource ID of the gateway route table |
| `gen_workload_route_table_id` | Resource ID of the Gen workload route table |
| `nongen_workload_route_table_id` | Resource ID of the Non-Gen workload route table |
| `onprem_route_table_id` | Resource ID of the on-premises route table |
| `hub_firewall_route_table_id` | Resource ID of the hub firewall route table |
| `route_table_associations` | List of route table association IDs |

## Advanced Routing Scenarios

### Conditional Routing
```hcl
# Conditional routes based on deployment flags
dynamic "route" {
  for_each = var.deploy_hub_firewall ? [1] : []
  content {
    name                   = "conditional-firewall-route"
    address_prefix         = "0.0.0.0/0"
    next_hop_type          = "VirtualAppliance"
    next_hop_in_ip_address = var.hub_firewall_private_ip
  }
}
```

### Multi-Region Routing
```hcl
# Cross-region routes
route {
  name           = "cross-region-route"
  address_prefix = "10.1.0.0/16"  # Remote region VNet
  next_hop_type  = "VirtualNetworkGateway"
}
```

## Dependencies

- **Networking Module**: Requires VNets and subnets
- **Firewall Module**: Requires firewall private IP addresses
- **Compute Module**: Optional NVA private IP addresses
- **Gateways Module**: Optional gateway resources

## Cost Considerations

### Route Table Costs
- **Route Tables**: No direct cost
- **Routes**: No direct cost (up to 400 routes per table)
- **Associations**: No direct cost

### Data Transfer Costs
- **Cross-VNet Traffic**: ~$0.01 per GB for peered VNets
- **Cross-Region Traffic**: ~$0.02-0.05 per GB
- **Internet Traffic**: Outbound data transfer charges apply

### Firewall Data Processing
- **Hub Firewall**: ~$0.016 per GB processed
- **Data Inspection**: Additional costs for advanced features

### Cost Optimization
```hcl
# Minimize cross-region traffic
optimize_regional_routing = true

# Use VNet peering for direct communication when possible
prefer_vnet_peering = true

# Consolidate route tables where possible
shared_route_tables = true
```

Estimated monthly cost: **$0-100** (primarily data transfer costs)
