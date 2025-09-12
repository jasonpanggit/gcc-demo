# Site-to-Site VPN Demonstration

This demonstration showcases complete Site-to-Site VPN connectivity between Azure and a simulated on-premises environment using **Windows Server 2016** with automated VPN configuration.

## 📋 Demo Overview

### Architecture Components
- **Azure Hub VNet** (10.0.0.0/16) with Azure Firewall and Bastion
- **VPN Gateway** (VpnGw1 SKU) with BGP enabled
- **On-premises VNet** (192.168.0.0/24) simulating real on-premises environment  
- **Windows Server 2016** with automated RRAS and VPN setup
- **Azure Arc** integration for hybrid management (optional)

### Key Features Demonstrated
- ✅ **IKEv2 Site-to-Site VPN** with pre-shared key authentication
- ✅ **BGP Routing** for dynamic route exchange using Windows Server 2016 IP (192.168.0.5)
- ✅ **PowerShell Automation** via Azure Custom Script Extension with IPv6 support
- ✅ **RRAS Configuration** with interface cleanup and connectivity testing
- ✅ **Network Segmentation** with Azure Firewall
- ✅ **Secure Management** via Azure Bastion

### Windows Server 2016 Optimizations
- **Public IP Assignment**: Ensures proper DNS resolution and connectivity
- **IPv6 Configuration**: Automated IPv6 prefix assignment (FE80::/64)
- **Interface Cleanup**: Removes conflicting network interfaces
- **Enhanced Connectivity**: DNS resolution and network adapter optimization

## 🚀 Quick Deployment

### Prerequisites
- Azure subscription with sufficient permissions
- Terraform installed and configured
- ~$1,250/month budget for full demo (see cost optimization below)

### Deploy Infrastructure
```bash
# From the root of the project
terraform init
terraform plan -var-file="demos/vpn/vpn-demo.tfvars"
terraform apply -var-file="demos/vpn/vpn-demo.tfvars"
```

### Monitor Deployment
```bash
# Check key outputs
terraform output vpn_gateway_public_ip
terraform output vpn_connection_status
terraform output vpn_automation_status
```

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
