# Windows Server 2025 VPN Setup Scripts

This directory contains PowerShell scripts for configuring Site-to-Site VPN connectivity between on-premises Windows Server 2025 and Azure VPN Gateway.

## Files

### `windows-server-2025-vpn-setup.ps1`
Comprehensive PowerShell script that configures Windows Server 2025 as a VPN endpoint for Site-to-Site connectivity with Azure VPN Gateway.

## Script Features

### ✅ RRAS (Routing and Remote Access Service) Configuration
- Installs and configures RemoteAccess feature
- Installs Routing feature  
- Installs DirectAccess-VPN feature
- Configures RRAS for Site-to-Site VPN

### ✅ IKEv2 VPN Connection Setup
- Creates Site-to-Site VPN interface
- Configures IKEv2 protocol with PSK authentication
- Sets up persistent connection with Azure VPN Gateway
- Configures connection timeouts and retry parameters

### ✅ Routing Configuration
- Adds static routes for Azure network traffic
- Configures route metrics for optimal traffic flow
- Handles automatic route configuration on VPN connect

### ✅ Windows Firewall Configuration
- Opens required ports for IKE (UDP 500)
- Opens required ports for IKEv2 (UDP 4500)
- Allows ESP protocol (Protocol 50) for IPsec
- Configures rules for all network profiles

### ✅ Connection Management
- Automatically connects to Azure VPN Gateway
- Monitors connection establishment
- Provides connection status and troubleshooting information

### ✅ Comprehensive Logging
- Detailed execution logs at C:\vpn-setup.log
- Phase-by-phase progress tracking
- Error handling and troubleshooting information
- PowerShell transcript logging

## Script Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `AzureVpnGatewayPublicIP` | String | ✅ Yes | - | Public IP address of Azure VPN Gateway |
| `SharedKey` | String | ✅ Yes | - | Pre-shared key for VPN authentication |
| `AzureNetworkCIDR` | String | ❌ No | 172.16.0.0/16 | Azure network CIDR range |
| `LocalNetworkCIDR` | String | ❌ No | 192.168.0.0/16 | On-premises network CIDR range |
| `ConnectionName` | String | ❌ No | Azure-S2S-VPN | Name for the VPN connection |

## Usage Examples

### Automatic Deployment
When `onprem_windows_vpn_setup = true` in Terraform variables, the script is automatically deployed and executed via Azure Custom Script Extension.

### Manual Execution
```powershell
# Basic usage with required parameters
.\windows-server-2025-vpn-setup.ps1 -AzureVpnGatewayPublicIP "20.1.2.3" -SharedKey "YourSecretKey123!"

# Advanced usage with custom network ranges
.\windows-server-2025-vpn-setup.ps1 `
    -AzureVpnGatewayPublicIP "20.1.2.3" `
    -SharedKey "YourSecretKey123!" `
    -AzureNetworkCIDR "10.0.0.0/16" `
    -LocalNetworkCIDR "192.168.0.0/24" `
    -ConnectionName "MyAzureVPN"
```

## Prerequisites

### System Requirements
- ✅ Windows Server 2025
- ✅ Administrator privileges
- ✅ PowerShell 5.1 or later
- ✅ Internet connectivity

### Network Requirements
- ✅ Public IP address or NAT for on-premises endpoint
- ✅ Firewall rules allowing UDP 500, UDP 4500, and ESP (Protocol 50)
- ✅ Azure VPN Gateway deployed and configured

## Terraform Integration

The script integrates seamlessly with the Landing Zone Terraform configuration:

### Configuration Variables
```hcl
# Enable VPN setup automation
onprem_windows_vpn_setup = true

# Configure VPN shared key
onprem_vpn_shared_key = "YourSecretKey123!"

# Enable VPN Gateway deployment
deploy_vpn_gateway = true
vpn_gateway_sku = "VpnGw1"
```

### Automatic Deployment Flow
1. **Storage Upload**: Script uploaded to Azure Storage Account
2. **Custom Script Extension**: Deployed to Windows Server VM
3. **Automatic Execution**: Script runs with Azure VPN Gateway parameters
4. **Connection Establishment**: VPN tunnel automatically configured

## Monitoring and Troubleshooting

### Connection Status
```powershell
# Check VPN connection status
Get-VpnS2SInterface -Name "Azure-S2S-VPN"

# View detailed connection information
Get-VpnS2SInterface | Format-List *

# Check routing table
Get-NetRoute | Where-Object {$_.DestinationPrefix -like "*172.16.*"}
```

### Reconnection
```powershell
# Manually reconnect VPN if needed
Connect-VpnS2SInterface -Name "Azure-S2S-VPN"

# Disconnect VPN
Disconnect-VpnS2SInterface -Name "Azure-S2S-VPN"
```

### Log Analysis
```powershell
# View setup logs
Get-Content C:\vpn-setup.log -Tail 50

# Check Windows Event Logs for RRAS
Get-WinEvent -LogName "System" | Where-Object {$_.ProviderName -eq "RemoteAccess"}
```

## Security Considerations

### ✅ Authentication
- Uses IKEv2 with Pre-Shared Key (PSK) authentication
- Shared key should be complex and unique
- Consider using certificates for production environments

### ✅ Encryption
- IPsec encryption for all VPN traffic
- ESP protocol for data encryption
- IKE protocol for key exchange

### ✅ Firewall Rules
- Minimal required ports opened
- Rules configured for all network profiles
- Can be customized based on security requirements

## Supported Azure VPN Gateway SKUs

| SKU | Tunnels | Throughput | BGP Support |
|-----|---------|------------|-------------|
| Basic | 10 | 100 Mbps | ❌ No |
| VpnGw1 | 30 | 650 Mbps | ✅ Yes |
| VpnGw2 | 30 | 1 Gbps | ✅ Yes |
| VpnGw3 | 30 | 1.25 Gbps | ✅ Yes |
| VpnGw1AZ | 30 | 650 Mbps | ✅ Yes |
| VpnGw2AZ | 30 | 1 Gbps | ✅ Yes |
| VpnGw3AZ | 30 | 1.25 Gbps | ✅ Yes |

## Error Codes and Solutions

### Common Issues

#### RRAS Service Won't Start
```powershell
# Check service status
Get-Service RemoteAccess

# Restart service manually
Restart-Service RemoteAccess -Force

# Check event logs
Get-WinEvent -LogName System | Where-Object {$_.ProviderName -eq "Service Control Manager" -and $_.Message -like "*RemoteAccess*"}
```

#### VPN Connection Fails
```powershell
# Verify Azure VPN Gateway is running
# Check shared key matches Azure configuration
# Verify firewall rules on both ends
# Check routing configuration

# Test connectivity to Azure VPN Gateway
Test-NetConnection -ComputerName "AzureVpnGatewayIP" -Port 500 -InformationLevel Detailed
```

#### Routing Issues
```powershell
# Check current routes
Get-NetRoute | Format-Table DestinationPrefix, NextHop, InterfaceAlias

# Add manual route if needed
New-NetRoute -DestinationPrefix "172.16.0.0/16" -InterfaceAlias "Azure-S2S-VPN" -Metric 1
```

## Support and Documentation

- **Azure VPN Gateway Documentation**: [Microsoft Docs](https://docs.microsoft.com/azure/vpn-gateway/)
- **Windows Server RRAS**: [Microsoft Docs](https://docs.microsoft.com/windows-server/remote/remote-access/)
- **PowerShell RemoteAccess Module**: [Microsoft Docs](https://docs.microsoft.com/powershell/module/remoteaccess/)

---
**Note**: This script is designed for lab and development environments. For production deployments, consider additional security hardening, monitoring, and backup procedures.
