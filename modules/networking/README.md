# Networking Module

This module creates the foundational networking infrastructure including virtual networks, subnets, and peering relationships for hub-spoke and multi-VNet architectures.

## Features

- **Hub Virtual Network**: Central hub VNet with configurable address space
- **Specialized Subnets**: Gateway, Firewall, Route Server, Bastion, and NVA subnets
- **Gen Virtual Network**: Dedicated VNet for generative AI workloads
- **Non-Gen Virtual Network**: Dedicated VNet for non-generative workloads
- **On-Premises Simulation**: Simulated on-premises VNet for hybrid scenarios
- **VNet Peering**: Hub-spoke and mesh peering configurations
- **Private DNS**: Private DNS zones for Azure services
- **Network Security Groups**: Basic NSG configurations for subnets

## Architecture

### Hub VNet (172.16.0.0/16)
- **GatewaySubnet**: For VPN and ExpressRoute gateways
- **AzureFirewallSubnet**: For Azure Firewall deployment
- **RouteServerSubnet**: For Azure Route Server
- **AzureBastionSubnet**: For Azure Bastion service
- **snet-nva**: For Network Virtual Appliances

### Gen VNet (10.0.0.0/16)
- **snet-gen-workload**: For generative AI workloads and applications

### Non-Gen VNet (100.0.0.0/16)
- **snet-nongen-workload**: For non-generative workloads

### On-Premises VNet (192.168.0.0/16)
- **snet-onprem**: Simulated on-premises subnet

## Usage

```hcl
module "networking" {
  source = "./modules/networking"
  
  project_name        = var.project_name
  environment         = var.environment
  location            = var.location
  resource_group_name = azurerm_resource_group.main.name
  
  # Hub VNet Configuration
  hub_vnet_address_space           = ["172.16.0.0/16"]
  hub_gateway_subnet_prefix        = "172.16.1.0/24"
  hub_firewall_subnet_prefix       = "172.16.2.0/24"
  hub_route_server_subnet_prefix   = "172.16.3.0/24"
  hub_bastion_subnet_prefix        = "172.16.4.0/24"
  hub_nva_subnet_prefix           = "172.16.5.0/24"
  
  # Gen VNet Configuration
  gen_vnet_address_space          = ["10.0.0.0/16"]
  gen_workload_subnet_prefix      = "10.0.1.0/24"
  
  # Non-Gen VNet Configuration
  nongen_vnet_address_space       = ["100.0.0.0/16"]
  nongen_workload_subnet_prefix   = "100.0.1.0/24"
  
  # On-Premises VNet Configuration
  onprem_vnet_address_space       = ["192.168.0.0/16"]
  onprem_subnet_prefix            = "192.168.1.0/24"
  
  # Deployment Flags
  deploy_expressroute_gateway     = var.deploy_expressroute_gateway
  deploy_vpn_gateway              = var.deploy_vpn_gateway
  deploy_hub_firewall             = var.deploy_hub_firewall
  deploy_route_server             = var.deploy_route_server
  deploy_bastion                  = var.deploy_bastion
  deploy_linux_nva                = var.deploy_linux_nva
  deploy_gen_vnet                 = var.deploy_gen_vnet
  deploy_nongen_vnet              = var.deploy_nongen_vnet
  deploy_onprem_vnet              = var.deploy_onprem_vnet
  
  # Peering Configuration
  enable_hub_to_gen_peering       = var.enable_hub_to_gen_peering
  enable_hub_to_nongen_peering    = var.enable_hub_to_nongen_peering
  enable_hub_to_onprem_peering    = var.enable_hub_to_onprem_peering
  enable_gen_to_nongen_peering    = var.enable_gen_to_nongen_peering
}
```

## Outputs

| Name | Description |
|------|-------------|
| `hub_vnet_id` | Resource ID of the hub virtual network |
| `hub_vnet_name` | Name of the hub virtual network |
| `gen_vnet_id` | Resource ID of the gen virtual network |
| `nongen_vnet_id` | Resource ID of the non-gen virtual network |
| `onprem_vnet_id` | Resource ID of the on-premises virtual network |
| `hub_gateway_subnet_id` | Resource ID of the gateway subnet |
| `hub_firewall_subnet_id` | Resource ID of the firewall subnet |
| `hub_route_server_subnet_id` | Resource ID of the route server subnet |
| `hub_bastion_subnet_id` | Resource ID of the bastion subnet |
| `hub_nva_subnet_id` | Resource ID of the NVA subnet |
| `gen_workload_subnet_id` | Resource ID of the gen workload subnet |
| `nongen_workload_subnet_id` | Resource ID of the non-gen workload subnet |
| `onprem_subnet_id` | Resource ID of the on-premises subnet |

## Dependencies

This module has no external module dependencies but requires:
- Azure Resource Group
- Appropriate Azure permissions for networking resources

## Cost Considerations

- **VNets**: No direct cost, pay for resources deployed within them
- **VNet Peering**: ~$0.01 per GB for cross-region peering
- **Private DNS Zones**: ~$0.50 per zone per month
- **Network Security Groups**: No additional cost

Estimated monthly cost: **$5-15** (depending on data transfer and number of DNS zones)
