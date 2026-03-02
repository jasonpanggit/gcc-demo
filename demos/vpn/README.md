# VPN Demo

Deploys site-to-site VPN-focused infrastructure and optional Windows RRAS bootstrap.

## File

- `vpn-demo.tfvars`

## Deploy

```bash
terraform plan  -var-file="credentials.tfvars" -var-file="demos/vpn/vpn-demo.tfvars"
terraform apply -var-file="credentials.tfvars" -var-file="demos/vpn/vpn-demo.tfvars"
```

## Related components

- `modules/gateways` for VPN gateway, local network gateway, and VPN connection
- `modules/compute` for Windows Server 2016 VM path
- `scripts/vpn/windows-server-2016-vpn-setup.ps1` for RRAS automation

Destroy when done:

```bash
terraform destroy -var-file="credentials.tfvars" -var-file="demos/vpn/vpn-demo.tfvars"
```
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
