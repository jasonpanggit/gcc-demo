# Azure Arc Hybrid Management Demonstration

This demonstration showcases Azure Arc capabilities for managing on-premises Windows servers from Azure, including policy enforcement, monitoring, and security management using **Windows Server 2025**.

## 📋 Demo Overview

### Architecture Components
- **On-premises Windows Server 2025** simulated in Azure (optimized for Arc scenarios)
- **Azure Arc Private Link Scope (AMPLS)** for secure connectivity
- **Azure Arc Service Principal** for automated onboarding
- **Azure Monitor Private Link Scope** for secure monitoring
- **Log Analytics Workspace** for centralized logging
- **Azure Policy** for compliance and governance

### Key Features Demonstrated
- ✅ **Automated Arc Onboarding** via PowerShell scripts with Windows Server 2025
- ✅ **Private Link Connectivity** for secure communication with AMPLS
- ✅ **VM Insights Integration** with performance monitoring and dependency mapping
- ✅ **Secure Monitoring** through Azure Monitor Private Link Scope
- ✅ **Policy Enforcement** on hybrid servers
- ✅ **Centralized Logging** with private DNS zone integration
- ✅ **Security Management** through Azure Security Center

### Windows Server 2025 Enhancements
- **Enhanced Arc Agent Support**: Optimized compatibility with latest Arc features
- **Improved Monitoring**: Better integration with Azure Monitor and VM Insights
- **Security Features**: Enhanced security baseline for hybrid connectivity
- **Performance Optimization**: Better resource utilization for Arc workloads

## 🚀 Quick Deployment

### Prerequisites
- Azure subscription with Arc registration permissions
- Terraform installed and configured
- ~$150/month budget for basic Arc demo

### Deploy Infrastructure
```bash
# From the root of the project
terraform init
terraform plan -var-file="demos/azure-arc/arc-demo.tfvars"
terraform apply -var-file="demos/azure-arc/arc-demo.tfvars"
```

## 📊 Expected Results

After successful deployment (~30-40 minutes), you should have:

### ✅ Arc-Enabled Server
- Windows Server visible in Azure Arc blade
- Server metadata synchronized to Azure
- Azure Resource Manager integration

### ✅ Policy Compliance
- Azure policies applied to on-premises server
- Compliance status visible in Azure Policy
- Automatic remediation capabilities

### ✅ Monitoring Integration
- Azure Monitor agent installed and configured
- Log Analytics workspace collecting server logs
- Performance metrics available in Azure

## 📁 Files in This Demo

| File | Purpose |
|------|---------|
| `arc-demo.tfvars` | Terraform configuration for Arc demo |
| `README.md` | This overview file |

## 🔧 Demo Configuration

### Core Components Enabled
```hcl
# Arc-specific settings
deploy_arc_private_link_scope = true
deploy_arc_service_principal = true
onprem_windows_arc_onboarding = true

# Monitoring integration
deploy_azure_monitor_private_link_scope = true
log_analytics_workspace_retention_days = 30

# Minimal infrastructure for cost optimization
deploy_hub_firewall = false
deploy_bastion = false
deploy_vpn_gateway = false
```

### Customization Options
```hcl
# Enable additional monitoring
log_analytics_workspace_retention_days = 90

# Add network security
deploy_hub_firewall = true
hub_firewall_arc_rules = true

# Enable service principal at subscription scope
arc_service_principal_subscription_scope = true
```

## 🔍 Testing and Verification

### Verify Arc Registration
```powershell
# On the Arc-enabled server
azcmagent show
azcmagent check

# Check connectivity
azcmagent show --json | ConvertFrom-Json
```

### Azure Portal Verification
1. Navigate to **Azure Arc** → **Servers**
2. Find your on-premises server
3. Review **Overview**, **Properties**, and **Extensions**
4. Check **Azure Policy** compliance status

### Monitor Data Collection
1. Go to **Azure Monitor** → **Logs**
2. Query for server data:
   ```kusto
   Heartbeat
   | where Computer contains "onprem"
   | summarize count() by Computer, bin(TimeGenerated, 1h)
   ```

## 🔧 Arc Management Tasks

### Install Extensions
```bash
# Via Azure CLI
az connectedmachine extension create \
  --machine-name "vm-onprem-windows" \
  --resource-group "rg-hub-gcc-demo" \
  --name "MicrosoftMonitoringAgent" \
  --publisher "Microsoft.EnterpriseCloud.Monitoring" \
  --type "MicrosoftMonitoringAgent"
```

### Apply Policies
```bash
# Assign built-in policy for Arc servers
az policy assignment create \
  --name "audit-arc-servers" \
  --policy "/providers/Microsoft.Authorization/policyDefinitions/audit-vm-unmanaged-disks" \
  --scope "/subscriptions/{subscription-id}/resourceGroups/rg-hub-gcc-demo"
```

### Monitor Compliance
1. **Azure Policy** → **Compliance**
2. Filter by **Arc-enabled servers**
3. Review compliance status and remediation tasks

## 💰 Cost Optimization

### Monthly Cost Breakdown
- **Arc License**: Free for first 3 servers
- **Azure Monitor**: ~$2-5 per GB ingested
- **VM Infrastructure**: ~$100-150/month
- **Total**: ~$150/month for basic setup

### Cost-Saving Tips
```hcl
# Minimal monitoring
log_analytics_workspace_retention_days = 7
deploy_azure_monitor_private_link_scope = false

# Disable expensive components
deploy_hub_firewall = false
deploy_bastion = false
```

## 🆘 Troubleshooting

### Arc Agent Issues
```powershell
# Check agent status
azcmagent show
Get-Service himds

# Restart agent
Restart-Service himds
azcmagent disconnect
azcmagent connect --resource-group "rg-hub-gcc-demo" --tenant-id "your-tenant-id"
```

### Connectivity Problems
```powershell
# Test Arc endpoints
azcmagent check
Test-NetConnection -ComputerName "guestconfiguration.azure.com" -Port 443
```

### Policy Application Issues
1. Check **Azure Policy** → **Assignments**
2. Verify resource scope includes Arc servers
3. Review **Compliance** for error details

## 🧹 Cleanup

```bash
# Destroy demo infrastructure
terraform destroy -var-file="demos/azure-arc/arc-demo.tfvars"

# Verify Arc server is removed from Azure Portal
```

## 💡 Learning Outcomes

After completing this demo, you will understand:
- Azure Arc server onboarding process
- Private Link configuration for secure Arc connectivity
- Policy management for hybrid infrastructure
- Monitoring setup for on-premises servers
- Cost considerations for Arc-enabled servers
- Troubleshooting common Arc connectivity issues

## 📚 Additional Resources

- [Azure Arc documentation](https://docs.microsoft.com/azure/azure-arc/)
- [Arc-enabled servers overview](https://docs.microsoft.com/azure/azure-arc/servers/)
- [Azure Policy for Arc servers](https://docs.microsoft.com/azure/governance/policy/concepts/guest-configuration)

---

**⚠️ Important**: This is a demonstration environment. For production use, implement proper RBAC, security policies, and monitoring according to your organization's requirements.
