# Azure Virtual Desktop (AVD) Demo

This demo showcases a complete Azure Virtual Desktop deployment with enterprise features in a Non-Gen VNet environment.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                     Hub VNet (172.16.0.0/16)               │
│  ┌─────────────────┐    ┌─────────────────┐                │
│  │   Monitoring    │    │  Private        │                │
│  │   (Log Analytics│    │  Endpoints      │                │
│  │    Workspace)   │    │  Subnet         │                │
│  └─────────────────┘    └─────────────────┘                │
└─────────────────────┬───────────────────────────────────────┘
                      │ VNet Peering
                      ▼
┌─────────────────────────────────────────────────────────────┐
│                Non-Gen VNet (100.0.0.0/16)                 │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────────┐    ┌─────────────────┐                │
│  │   Azure         │    │   AVD Session   │                │
│  │   Firewall      │    │   Host Subnet   │                │
│  │   (100.0.0.0/25)│    │  (100.0.1.0/24) │                │
│  └─────────────────┘    └─────────────────┘                │
│                                                             │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │              AVD Session Hosts                          │ │
│  │  ┌───────────┐  ┌───────────┐                          │ │
│  │  │Session    │  │Session    │                          │ │
│  │  │Host 1     │  │Host 2     │                          │ │
│  │  │(AAD Join) │  │(AAD Join) │                          │ │
│  │  └───────────┘  └───────────┘                          │ │
│  └─────────────────────────────────────────────────────────┘ │
│                                                             │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │            Private Endpoint Subnet                     │ │
│  │  ┌─────────────────┐                                   │ │
│  │  │   FSLogix       │                                   │ │
│  │  │   Storage PE    │                                   │ │
│  │  └─────────────────┘                                   │ │
│  └─────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼ (Outbound Traffic)
                         Internet
```

## Features Demonstrated

### 🖥️ **Core AVD Components**
- **AVD Workspace**: Central management portal
- **Host Pool**: Pooled desktop environment  
- **Application Group**: Desktop access for users
- **Session Hosts**: Windows 11 multi-session VMs

### 🔐 **Enterprise Security**
- **Azure AD Join**: Modern authentication and device management
- **Non-Gen Firewall**: Secure outbound internet access
- **Private Endpoints**: Secure connectivity to Azure services
- **Network Security Groups**: Micro-segmentation

### 📁 **User Experience**
- **FSLogix Profile Containers**: Persistent user profiles
- **Premium File Storage**: High-performance profile storage
- **Auto-start VMs**: Cost optimization with on-demand scaling

### 📊 **Monitoring & Management**
- **Log Analytics Workspace**: Centralized logging
- **AVD Insights**: Built-in monitoring dashboards
- **Diagnostic Settings**: Comprehensive telemetry

## Prerequisites

1. **Azure Subscription** with sufficient quota:
   - 2x Standard_D2s_v3 VMs (4 vCPUs total)
   - Premium File Storage account
   - Azure Firewall Standard

2. **Azure Permissions**:
   - Contributor on target subscription
   - Azure AD permissions for device management

3. **Terraform Setup**:
   - Terraform v1.0+
   - Azure CLI authenticated
   - Service Principal with required permissions

## Quick Start

1. **Navigate to project root**:
   ```bash
   cd /path/to/LinkLandingZone
   ```

2. **Deploy AVD demo**:
   ```bash
   terraform plan -var-file="credentials.tfvars" -var-file="demos/avd/avd-demo.tfvars"
   terraform apply -var-file="credentials.tfvars" -var-file="demos/avd/avd-demo.tfvars"
   ```

3. **Deployment time**: ~45-60 minutes
   - Network infrastructure: ~10 minutes
   - Firewall deployment: ~15 minutes  
   - AVD components: ~20 minutes
   - Session host configuration: ~15 minutes

## Post-Deployment Configuration

### 1. User Assignment
```bash
# Assign users to AVD application group
az role assignment create \
  --assignee user@domain.com \
  --role "Desktop Virtualization User" \
  --scope "/subscriptions/{subscription-id}/resourceGroups/rg-avd-demo-demo/providers/Microsoft.DesktopVirtualization/applicationGroups/avd-ag-avd-demo-demo"
```

### 2. Access AVD
- **Web Client**: https://rdweb.wvd.microsoft.com/arm/webclient
- **Windows Client**: Download from Microsoft Store
- **Mobile Apps**: Available for iOS and Android

### 3. Verify FSLogix
```powershell
# On session host, check FSLogix configuration
Get-ItemProperty "HKLM:\SOFTWARE\FSLogix\Profiles" -Name "Enabled"
Get-ItemProperty "HKLM:\SOFTWARE\FSLogix\Profiles" -Name "VHDLocations"
```

## Configuration Options

### Scaling Options
```hcl
# Production scaling
avd_session_host_count = 5
avd_session_host_vm_size = "Standard_D4s_v3"

# Cost optimization
avd_session_host_count = 1
avd_session_host_vm_size = "Standard_B2s"
```

### Storage Options
```hcl
# High performance
avd_fslogix_storage_account_tier = "Premium"
avd_fslogix_storage_account_replication = "ZRS"

# Cost optimized
avd_fslogix_storage_account_tier = "Standard"
avd_fslogix_storage_account_replication = "LRS"
```

## Monitoring

### Built-in Dashboards
- **AVD Insights**: Azure portal > AVD workspace > Insights
- **Session Host Health**: Monitor CPU, memory, disk usage
- **User Sessions**: Track connection quality and performance

### Log Analytics Queries
```kusto
// Session connection events
WVDConnections
| where TimeGenerated > ago(24h)
| summarize ConnectionCount = count() by UserName
| order by ConnectionCount desc

// Session host performance
WVDAgentHealthStatus
| where TimeGenerated > ago(1h)
| summarize by SessionHostName, Status
```

## Troubleshooting

### Common Issues

1. **Session hosts not appearing in host pool**
   - Check NSG rules allow AVD service traffic
   - Verify firewall rules permit required FQDNs
   - Review registration token expiration

2. **FSLogix profile issues**
   - Verify storage account permissions
   - Check private endpoint DNS resolution
   - Validate SMB connectivity

3. **Performance issues**
   - Review VM sizing for workload requirements
   - Check storage performance metrics
   - Monitor network latency

### Diagnostic Commands
```bash
# Check session host status
az desktopvirtualization sessionhost list \
  --host-pool-name "avd-hp-avd-demo-demo" \
  --resource-group "rg-avd-demo-demo"

# Verify storage connectivity
nslookup stavdfslogix{random}.file.core.windows.net

# Test firewall rules
az network firewall policy show \
  --name "afwp-avd-demo-avd-demo-demo" \
  --resource-group "rg-avd-demo-demo"
```

## Cost Management

### Cost Optimization Tips
1. **Enable Start VM on Connect** to reduce running time
2. **Right-size VMs** based on actual usage patterns
3. **Use Standard storage** for non-critical workloads
4. **Implement auto-shutdown** policies
5. **Monitor with Azure Cost Management**

### Estimated Monthly Costs (Australia East)
- **2x Standard_D2s_v3 VMs**: ~$350 USD (if running 24/7)
- **Premium File Storage**: ~$50 USD (1TB)
- **Azure Firewall**: ~$650 USD
- **Networking**: ~$20 USD
- **Total**: ~$1,070 USD/month

*Costs significantly reduced with auto-shutdown and Start VM on Connect*

## Security Considerations

### Production Hardening
1. **Conditional Access**: Implement Azure AD policies
2. **MFA**: Require multi-factor authentication
3. **Privileged Access**: Use Azure AD PIM
4. **Compliance**: Enable Azure Policy
5. **Monitoring**: Configure security alerts

### Network Security
- All outbound traffic routes through firewall
- Private endpoints for storage access
- NSGs provide micro-segmentation
- No direct internet access from session hosts

## Cleanup

To remove all resources:
```bash
terraform destroy -var-file="credentials.tfvars" -var-file="demos/avd/avd-demo.tfvars"
```

**Warning**: This will permanently delete all AVD resources and user data!

## Support

For issues with this demo:
1. Check [troubleshooting section](#troubleshooting)
2. Review [Azure AVD documentation](https://docs.microsoft.com/en-us/azure/virtual-desktop/)
3. Validate network connectivity and firewall rules
4. Check Azure service health status
