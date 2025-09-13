# Site-to-Site VPN Demonstration

This demonstration showcases complete Site-to-Site VPN connectivity between Azure and a simulated on-premises environment using **Windows Server 2016** with automated RRAS configuration.

## 🎯 Demo Overview

### Architecture Components
- **Azure Hub VNet** (172.16.0.0/16) with Azure Firewall and optional Bastion
- **VPN Gateway** (VpnGw1 SKU) with BGP support
- **On-premises VNet** (192.168.0.0/16) simulating real on-premises environment  
- **Windows Server 2016** with automated RRAS and VPN setup
- **Local Network Gateway** representing on-premises network
- **Site-to-Site Connection** with pre-shared key authentication

### Key Features Demonstrated
- ✅ **IKEv2 Site-to-Site VPN** with pre-shared key authentication
- ✅ **BGP Routing** for dynamic route exchange (optional)
- ✅ **Automated RRAS Setup** via PowerShell Custom Script Extension
- ✅ **Network Segmentation** with Azure Firewall (optional)
- ✅ **Secure Management** via Azure Bastion (optional)
- ✅ **Hybrid Connectivity** testing and validation

### Windows Server 2016 Configuration
- **Public IP Assignment**: Enables external VPN connectivity
- **RRAS Role Installation**: Routing and Remote Access Service
- **VPN Interface Setup**: Automated S2S VPN configuration
- **BGP Configuration**: Dynamic routing protocol setup
- **Connectivity Testing**: Automated validation scripts

## 💰 Cost Analysis

### Monthly Operating Costs (~$150/month - Basic Configuration)
- **VPN Gateway (VpnGw1)**: ~$120/month
- **Windows Server 2016 VM**: ~$75/month (D2s_v3)
- **Public IP Addresses**: ~$6/month (2 static IPs)
- **Storage & Networking**: ~$5/month

### Full Configuration Costs (~$1,200/month)
- **Azure Firewall**: ~$800/month (if enabled)
- **Azure Bastion**: ~$150/month (if enabled)
- **VPN Gateway**: ~$120/month
- **Compute & Storage**: ~$80/month
- **Monitoring**: ~$20/month

### Cost Optimization Options
```hcl
# Minimal cost deployment (~$150/month)
deploy_hub_firewall = false      # Save ~$800/month
deploy_bastion = false           # Save ~$150/month
vpn_gateway_sku = "VpnGw1"      # Standard performance

# High performance deployment
vpn_gateway_sku = "VpnGw3"      # Higher throughput (+$1,000/month)
```

## ⏱️ Deployment Timeline

### Estimated Deployment Time: **20-30 minutes**
1. **Networking Setup** (5-8 minutes): VNets, subnets, NSGs
2. **VPN Gateway** (15-20 minutes): Longest component to deploy
3. **Virtual Machines** (3-5 minutes): Windows Server 2016
4. **VPN Configuration** (2-3 minutes): Connection setup and RRAS automation
5. **Validation** (1-2 minutes): Connectivity testing

## 🚀 Quick Start

### Prerequisites
```bash
# Verify Azure CLI access
az account show

# Check available VM sizes (optional)
az vm list-sizes --location eastus --output table
```

### Deploy the Demo
```bash
# 1. Set up credentials
cp credentials.tfvars.example credentials.tfvars
# Edit credentials.tfvars with your Azure values

# 2. Review configuration
cat demos/vpn/vpn-demo.tfvars

# 3. Deploy infrastructure
terraform init
terraform plan -var-file="credentials.tfvars" -var-file="demos/vpn/vpn-demo.tfvars"
terraform apply -var-file="credentials.tfvars" -var-file="demos/vpn/vpn-demo.tfvars"
```

### Alternative: Use Run Script
```bash
# Automated deployment with the provided script
./run-demo.sh demos/vpn/vpn-demo.tfvars credentials.tfvars
```

## 🔧 Configuration Options

### VPN Gateway Settings
```hcl
# Basic VPN Gateway (lowest cost)
vpn_gateway_sku = "VpnGw1"       # Up to 650 Mbps, 30 tunnels
enable_vpn_gateway_bgp = false   # Static routing

# Advanced VPN Gateway (higher performance)
vpn_gateway_sku = "VpnGw2"       # Up to 1 Gbps, 30 tunnels
enable_vpn_gateway_bgp = true    # Dynamic BGP routing
```

### Network Configuration
```hcl
# Custom IP address spaces
hub_vnet_address_space = ["172.16.0.0/16"]
onprem_vnet_address_space = ["192.168.0.0/16"]

# VPN connection settings
vpn_shared_key = "YourSecureSharedKey123!"
```

### Windows Server Settings
```hcl
# VM configuration
onprem_windows_vm_size = "Standard_D2s_v3"    # 2 vCPU, 8GB RAM
windows_server_admin_username = "azureuser"
windows_server_admin_password = "SecurePassword123!"

# Automation features
onprem_windows_vpn_setup = true               # Automated RRAS setup
```

## 📊 Expected Results

### After Successful Deployment (20-30 minutes)
- ✅ **VPN Tunnel Status**: "Connected" in Azure portal
- ✅ **Network Connectivity**: Ping between Azure (172.16.x.x) and on-premises (192.168.x.x)
- ✅ **BGP Routes**: Dynamic route exchange (if enabled)
- ✅ **RRAS Configuration**: Windows Server 2016 acting as VPN endpoint
- ✅ **DNS Resolution**: Bidirectional name resolution

### Key Verification Points
```powershell
# On Windows Server 2016 (via RDP or Bastion)
Get-VpnS2SInterface
Get-RemoteAccess
Get-BgpPeer  # If BGP enabled
ping 172.16.1.4  # Test connectivity to Azure
```

## 🔍 Testing and Validation

### Automated Tests
The deployment includes automated testing scripts:
```powershell
# VPN connection verification
$vpnStatus = Get-VpnS2SInterface -Name "Azure-S2S-VPN"
Write-Output "VPN Status: $($vpnStatus.ConnectionState)"

# Network connectivity test
Test-NetConnection -ComputerName "172.16.1.4" -Port 80
```

### Manual Validation Steps
1. **Azure Portal**: Check VPN Gateway connection status
2. **Windows Server**: Verify RRAS configuration via Server Manager
3. **Network Testing**: Ping tests between environments
4. **Route Tables**: Verify route propagation (if BGP enabled)

### Troubleshooting Common Issues
```bash
# Check VPN Gateway status
az network vnet-gateway show --name vgw-vpn-demo --resource-group demo-rg

# Review connection logs
az network vpn-connection show --name conn-vpn-demo --resource-group demo-rg

# Monitor custom script extension
az vm extension show --vm-name vm-onprem-win2016 --name CustomScriptExtension --resource-group demo-rg
```

## 🔐 Security Considerations

### Network Security
- **Pre-Shared Key**: Strong PSK for VPN authentication
- **Private Networks**: RFC 1918 address spaces only
- **Firewall Rules**: Azure Firewall policies (if enabled)
- **NSG Rules**: Network Security Group restrictions

### Access Control
- **VM Access**: RDP via Bastion or public IP (configurable)
- **Azure Resources**: RBAC for management access
- **VPN Configuration**: Secured via Azure Key Vault (optional)

## 📚 Advanced Scenarios

### Multi-Site Configuration
```hcl
# Add additional on-premises sites
additional_onprem_sites = [
  {
    name = "branch-office"
    address_space = ["192.168.100.0/24"]
    gateway_ip = "203.0.113.10"
  }
]
```

### High Availability
```hcl
# Active-Active VPN Gateway
vpn_gateway_type = "VpnGw1"
vpn_gateway_active_active = true
```

### Integration with ExpressRoute
```hcl
# Coexistence with ExpressRoute
deploy_expressroute_gateway = true
enable_expressroute_vpn_coexistence = true
```

## 📁 Demo Files

| File | Purpose |
|------|---------|
| `vpn-demo.tfvars` | Complete Terraform configuration |
| `README.md` | This overview and deployment guide |

## 🛠️ Cleanup

### Destroy Resources
```bash
# Destroy all demo resources
terraform destroy -var-file="credentials.tfvars" -var-file="demos/vpn/vpn-demo.tfvars"

# Or use the run script
./run-demo.sh demos/vpn/vpn-demo.tfvars credentials.tfvars destroy
```

---

For detailed technical documentation, see the [gateways module README](../../modules/gateways/README.md) and [compute module README](../../modules/compute/README.md).

## 📊 Expected Results

After successful deployment (~45-60 minutes), you should have:

### ✅ Network Connectivity
- Site-to-Site VPN tunnel in "Connected" state
- Ping from 192.168.x.x (on-premises) to 172.16.x.x (Azure)
- BGP routes exchanged between environments
- DNS resolution working bidirectionally

### ✅ Azure Arc Integration
- Windows Server visible in Azure Arc blade
- Azure policies applied to on-premises server
- Azure Monitor collecting logs and metrics

### ✅ Management Capabilities
- Azure Bastion access to all VMs
- Azure Firewall controlling network traffic
- PowerShell scripts deployed and executed automatically

## 📁 Files in This Demo

| File | Purpose |
|------|---------|
| `vpn-demo.tfvars` | Complete Terraform configuration |
| `VPN-DEMO-GUIDE.md` | Detailed deployment and testing guide |
| `README.md` | This overview file |

## 🔧 Customization Options

### Cost Optimization (~$200/month)
```hcl
# Edit vpn-demo.tfvars for budget-friendly setup
deploy_hub_firewall = false      # Save ~$800/month
deploy_bastion = false           # Save ~$150/month
vpn_gateway_sku = "Basic"        # Save ~$100/month (no BGP)
enable_vpn_gateway_bgp = false
```

### Network Customization
```hcl
# Custom IP ranges
hub_vnet_address_space = ["10.0.0.0/16"]
onprem_vnet_address_space = ["10.1.0.0/16"]

# Different VPN Gateway SKU
vpn_gateway_sku = "VpnGw2"  # Higher performance
```

### Feature Toggles
```hcl
# Disable specific features
onprem_windows_arc_onboarding = false   # Skip Arc onboarding
deploy_azure_monitor_private_link_scope = false  # Skip monitoring
```

## 🔍 Testing and Verification

### Post-Deployment Tests
Detailed testing procedures are in `VPN-DEMO-GUIDE.md`, including:

1. **VPN Connection Verification**
   ```powershell
   Get-VpnS2SInterface -Name "Azure-S2S-VPN"
   ```

2. **Network Connectivity Tests**
   ```powershell
   ping 172.16.1.4  # Azure Firewall IP
   Test-NetConnection -ComputerName 172.16.1.4 -Port 80
   ```

3. **BGP Status Check**
   ```powershell
   Get-BgpPeer
   Get-NetRoute | Where-Object {$_.Protocol -eq "BGP"}
   ```

## 🆘 Troubleshooting

### Common Issues
- **VPN won't connect**: Check shared key and firewall rules
- **No network connectivity**: Verify routing and Azure Firewall rules
- **PowerShell script fails**: Check execution logs at `C:\vpn-setup.log`

### Support Resources
- Full troubleshooting guide in `VPN-DEMO-GUIDE.md`
- Azure VPN Gateway documentation
- Windows RRAS configuration guides

## 🧹 Cleanup

```bash
# Always destroy demo resources when finished
terraform destroy -var-file="demos/vpn/vpn-demo.tfvars"

# Confirm all resources are deleted in Azure Portal
```

## 💡 Learning Outcomes

After completing this demo, you will understand:
- How to deploy Azure VPN Gateway with Terraform
- Windows Server RRAS configuration for Site-to-Site VPN
- BGP routing in hybrid cloud scenarios
- Azure Arc onboarding automation
- PowerShell script deployment via Custom Script Extensions
- Cost optimization strategies for VPN infrastructure

---

**⚠️ Important**: This is a demonstration environment. For production use, implement additional security hardening, monitoring, and compliance requirements.
