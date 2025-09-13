# Gateways Module

This module manages VPN and ExpressRoute gateway resources for hybrid connectivity scenarios, enabling secure connections between Azure and on-premises environments.

## Features

- **ExpressRoute Gateway**: High-performance private connectivity to Azure
- **VPN Gateway**: Site-to-site and point-to-site VPN connections
- **Local Network Gateway**: On-premises network representation
- **Route Server**: BGP route exchange with network virtual appliances
- **Multiple SKUs**: Performance tiers for different requirements
- **Active-Active**: High availability configurations

## Architecture

### ExpressRoute Gateway
- **Purpose**: Private connectivity via ExpressRoute circuits
- **SKUs**: Standard, HighPerformance, UltraPerformance, ErGw1Az-3Az
- **Features**: Private peering, Microsoft peering, BGP routing
- **Bandwidth**: Up to 40 Gbps depending on SKU

### VPN Gateway
- **Purpose**: Site-to-site and point-to-site VPN connectivity
- **SKUs**: Basic, VpnGw1-5, VpnGw1Az-5Az (availability zone support)
- **VPN Types**: Route-based and policy-based
- **Protocols**: IKEv2, SSTP, OpenVPN

### Local Network Gateway
- **Purpose**: Represents on-premises network in Azure
- **Configuration**: Public IP and address spaces
- **BGP Support**: Dynamic routing capabilities

### Route Server
- **Purpose**: BGP route exchange between Azure and NVAs
- **Features**: Route reflection, multi-homing support
- **Integration**: Works with third-party NVAs and SD-WAN

## Usage

```hcl
module "gateways" {
  source = "./modules/gateways"
  
  project_name        = var.project_name
  environment         = var.environment
  location            = var.location
  resource_group_name = azurerm_resource_group.main.name
  
  # Gateway Subnet
  gateway_subnet_id = module.networking.hub_gateway_subnet_id
  route_server_subnet_id = module.networking.hub_route_server_subnet_id
  
  # ExpressRoute Gateway
  deploy_hub_vnet             = var.deploy_hub_vnet
  deploy_expressroute_gateway = var.deploy_expressroute_gateway
  expressroute_gateway_sku    = var.expressroute_gateway_sku
  
  # VPN Gateway
  deploy_vpn_gateway = var.deploy_vpn_gateway
  vpn_gateway_sku    = var.vpn_gateway_sku
  vpn_gateway_type   = var.vpn_gateway_type
  
  # Local Network Gateway
  deploy_local_network_gateway = var.deploy_local_network_gateway
  onprem_gateway_public_ip     = var.onprem_gateway_public_ip
  onprem_address_spaces        = var.onprem_address_spaces
  
  # Route Server
  deploy_route_server = var.deploy_route_server
  
  # VPN Connection
  deploy_vpn_connection = var.deploy_vpn_connection
  vpn_shared_key       = var.vpn_shared_key
  
  # BGP Configuration
  enable_bgp           = var.enable_bgp
  bgp_asn              = var.bgp_asn
  bgp_peering_address  = var.bgp_peering_address
  
  tags = var.tags
}
```

## Gateway SKUs and Performance

### ExpressRoute Gateway SKUs
```hcl
# Standard SKU - Up to 2 Gbps
expressroute_gateway_sku = "Standard"

# High Performance SKU - Up to 10 Gbps  
expressroute_gateway_sku = "HighPerformance"

# Ultra Performance SKU - Up to 40 Gbps
expressroute_gateway_sku = "UltraPerformance"

# Zone-redundant SKUs
expressroute_gateway_sku = "ErGw1Az"  # Up to 1 Gbps with AZ support
expressroute_gateway_sku = "ErGw2Az"  # Up to 2 Gbps with AZ support
expressroute_gateway_sku = "ErGw3Az"  # Up to 10 Gbps with AZ support
```

### VPN Gateway SKUs
```hcl
# Basic SKU - Up to 100 Mbps, 10 tunnels
vpn_gateway_sku = "Basic"

# Standard SKUs
vpn_gateway_sku = "VpnGw1"   # Up to 650 Mbps, 30 tunnels
vpn_gateway_sku = "VpnGw2"   # Up to 1 Gbps, 30 tunnels
vpn_gateway_sku = "VpnGw3"   # Up to 1.25 Gbps, 30 tunnels
vpn_gateway_sku = "VpnGw4"   # Up to 5 Gbps, 100 tunnels
vpn_gateway_sku = "VpnGw5"   # Up to 10 Gbps, 100 tunnels

# Zone-redundant SKUs
vpn_gateway_sku = "VpnGw1Az" # Same performance with AZ support
```

## BGP Configuration

### Route Server BGP
```hcl
# Enable Route Server for BGP with NVAs
deploy_route_server = true

# BGP Configuration
enable_bgp = true
bgp_asn = 65515  # Azure default ASN
```

### VPN BGP Configuration
```hcl
# Enable BGP on VPN Gateway
enable_bgp = true
bgp_asn = 65001
bgp_peering_address = "169.254.21.1"

# On-premises BGP settings
onprem_bgp_asn = 65002
onprem_bgp_peering_address = "169.254.21.2"
```

## Connection Types

### Site-to-Site VPN
```hcl
deploy_vpn_connection = true
vpn_shared_key = "YourSecureSharedKey123!"
connection_protocol = "IKEv2"
```

### ExpressRoute Connection
```hcl
# ExpressRoute circuit connection
expressroute_circuit_id = "/subscriptions/.../microsoft.network/expressroutecircuits/circuit-name"
```

## Outputs

| Name | Description |
|------|-------------|
| `expressroute_gateway_id` | Resource ID of the ExpressRoute gateway |
| `vpn_gateway_id` | Resource ID of the VPN gateway |
| `vpn_gateway_public_ip` | Public IP address of the VPN gateway |
| `local_network_gateway_id` | Resource ID of the local network gateway |
| `route_server_id` | Resource ID of the Route Server |
| `route_server_ips` | IP addresses of the Route Server |
| `vpn_connection_id` | Resource ID of the VPN connection |

## Dependencies

- **Networking Module**: Requires GatewaySubnet and RouteServerSubnet
- **Azure Resource Group**: Target resource group
- **Public IP**: Required for gateway external connectivity

## Cost Considerations

### ExpressRoute Gateway Costs
- **Standard**: ~$200 per month
- **HighPerformance**: ~$200 per month  
- **UltraPerformance**: ~$200 per month
- **Zone-redundant**: Additional ~$100 per month

### VPN Gateway Costs
- **Basic**: ~$25 per month
- **VpnGw1**: ~$120 per month
- **VpnGw2**: ~$360 per month
- **VpnGw3**: ~$1,200 per month
- **VpnGw4**: ~$1,500 per month
- **VpnGw5**: ~$3,000 per month

### Route Server Costs
- **Route Server**: ~$450 per month
- **Data Processing**: ~$0.20 per million routes

### Additional Costs
- **Public IP**: ~$3 per month per static IP
- **Data Transfer**: Varies based on usage
- **ExpressRoute Circuit**: Separate billing from Microsoft or partner

### Cost Optimization
```hcl
# Use lower SKUs for testing
vpn_gateway_sku = "VpnGw1"              # vs VpnGw3+
expressroute_gateway_sku = "Standard"    # vs UltraPerformance

# Disable when not needed
deploy_route_server = false             # Save ~$450/month
deploy_expressroute_gateway = false     # Save ~$200/month
```

Estimated monthly cost: **$25-3,500** depending on gateway types and SKUs
