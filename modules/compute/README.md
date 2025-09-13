# Compute Module

This module manages virtual machines and related compute resources for network virtual appliances, on-premises simulation, and specialized workloads.

## Features

- **Network Virtual Appliance (NVA)**: Ubuntu-based routing appliance with FRRouting
- **Squid Proxy**: HTTP/HTTPS forward proxy for controlled egress
- **Windows Server VMs**: On-premises simulation with Server 2016 and 2025
- **Custom Script Extensions**: Automated configuration via PowerShell and Bash scripts
- **Managed Identity**: System-assigned identities for Azure integrations
- **IP Forwarding**: Enabled for routing scenarios

## Architecture

### Network Virtual Appliance (Ubuntu 20.04 LTS)
- **Purpose**: BGP routing with Azure Route Server
- **BGP ASN**: 65001 (configurable)
- **Features**: FRRouting daemon, IP forwarding, custom routing
- **Size**: Standard_B2s (2 vCPU, 4GB RAM)

### Squid Proxy (Ubuntu 20.04 LTS)  
- **Purpose**: HTTP/HTTPS forward proxy for controlled internet access
- **Configuration**: Basic proxy setup with access controls
- **Size**: Standard_B1s (1 vCPU, 1GB RAM)

### Windows Server VMs
- **Server 2016**: Optimized for VPN scenarios and RRAS configuration
- **Server 2025**: Enhanced for Azure Arc hybrid management
- **Features**: Custom Script Extensions, automated domain joining
- **Size**: Standard_D4s_v5 (4 vCPU, 16GB RAM)

## Usage

```hcl
module "compute" {
  source = "./modules/compute"
  
  project_name        = var.project_name
  environment         = var.environment
  location            = var.location
  resource_group_name = azurerm_resource_group.main.name
  
  # Network Virtual Appliance
  deploy_route_server = var.deploy_route_server
  deploy_linux_nva    = var.deploy_linux_nva
  nva_subnet_id       = module.networking.hub_nva_subnet_id
  route_server_ip1    = module.networking.route_server_ip1
  route_server_ip2    = module.networking.route_server_ip2
  
  # Squid Proxy
  deploy_squid_proxy  = var.deploy_squid_proxy
  squid_subnet_id     = module.networking.squid_subnet_id
  
  # On-Premises Windows Servers
  deploy_onprem_vnet                    = var.deploy_onprem_vnet
  deploy_onprem_windows_server_2016     = var.deploy_onprem_windows_server_2016
  deploy_onprem_windows_server_2025     = var.deploy_onprem_windows_server_2025
  onprem_subnet_id                      = module.networking.onprem_subnet_id
  
  # Automation Configuration
  onprem_windows_vpn_setup              = var.onprem_windows_vpn_setup
  onprem_windows_arc_setup              = var.onprem_windows_arc_setup
  storage_account_name                  = module.storage.storage_account_name
  container_name                        = module.storage.container_name
  
  # Windows Server Credentials
  windows_server_admin_username         = var.windows_server_admin_username
  windows_server_admin_password         = var.windows_server_admin_password
  
  # VPN Configuration
  vpn_onprem_gateway_public_ip          = var.vpn_onprem_gateway_public_ip
  vpn_shared_key                        = var.vpn_shared_key
  hub_vnet_address_space                = var.hub_vnet_address_space
  
  # Azure Arc Configuration
  azure_tenant_id                       = var.azure_tenant_id
  azure_subscription_id                 = var.azure_subscription_id
  arc_spn_client_id                     = var.arc_spn_client_id
  arc_spn_client_secret                 = var.arc_spn_client_secret
  arc_resource_group_name               = var.arc_resource_group_name
  
  tags = var.tags
}
```

## Virtual Machine Configurations

### NVA Configuration
```hcl
# BGP Configuration
nva_bgp_asn = 65001
route_server_ip1 = "172.16.3.4"  # From Route Server
route_server_ip2 = "172.16.3.5"

# Custom routes to advertise
nva_advertised_routes = [
  "192.168.100.0/24",
  "10.10.0.0/16"
]
```

### Windows Server Configuration
```hcl
# Windows Server 2016 for VPN scenarios
deploy_onprem_windows_server_2016 = true
onprem_windows_vpn_setup = true

# Windows Server 2025 for Azure Arc
deploy_onprem_windows_server_2025 = true
onprem_windows_arc_setup = true

# Credentials
windows_server_admin_username = "localadmin"
windows_server_admin_password = "SecurePassword123!"
```

## Custom Script Extensions

### VPN Setup (Windows Server 2016)
- **Script**: `scripts/vpn/windows-server-2016-vpn-setup.ps1`
- **Purpose**: Configure RRAS for Site-to-Site VPN
- **Features**: IKEv2 support, PSK authentication, logging

### Azure Arc Setup (Windows Server 2025)
- **Script**: `scripts/arc/windows-server-2025-arc-setup.ps1`
- **Purpose**: Install and configure Azure Arc agent
- **Features**: Private link support, automated onboarding

### NVA Setup (Ubuntu)
- **Script**: `scripts/nva/nva-config.sh`
- **Purpose**: Configure FRRouting and BGP
- **Features**: IP forwarding, BGP peering, route advertisement

### Squid Setup (Ubuntu)
- **Script**: `scripts/squid/squid-config.sh`
- **Purpose**: Install and configure Squid proxy
- **Features**: Access controls, logging, basic authentication

## Outputs

| Name | Description |
|------|-------------|
| `nva_private_ip` | Private IP address of the NVA |
| `nva_public_ip` | Public IP address of the NVA |
| `squid_private_ip` | Private IP address of the Squid proxy |
| `onprem_windows_2016_private_ip` | Private IP of Windows Server 2016 |
| `onprem_windows_2025_private_ip` | Private IP of Windows Server 2025 |
| `onprem_windows_2016_public_ip` | Public IP of Windows Server 2016 |
| `onprem_windows_2025_public_ip` | Public IP of Windows Server 2025 |

## Dependencies

- **Networking Module**: Requires subnet IDs for VM placement
- **Storage Module**: Script storage for Custom Script Extensions
- **Azure Resource Group**: Target resource group

## Cost Considerations

### Virtual Machine Sizes and Costs
- **NVA (Standard_B2s)**: ~$30-40 per month
- **Squid (Standard_B1s)**: ~$15-20 per month  
- **Windows Server 2016 (Standard_D4s_v5)**: ~$150-200 per month
- **Windows Server 2025 (Standard_D4s_v5)**: ~$150-200 per month

### Additional Costs
- **Public IPs**: ~$3 per month per static IP
- **Storage**: Minimal cost for scripts and logs
- **Data Transfer**: Varies based on usage

### Cost Optimization
```hcl
# Use smaller VM sizes for testing
nva_vm_size = "Standard_B1s"          # ~$15/month
windows_vm_size = "Standard_D2s_v5"   # ~$75/month

# Disable public IPs when not needed
assign_public_ip = false
```

Estimated monthly cost: **$200-500** depending on VM sizes and configurations
