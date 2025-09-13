# Arc Module

This module manages Azure Arc resources for hybrid server management, including service principals, role assignments, and private link configurations for secure Azure Arc connectivity.

## Features

- **Service Principal**: Automated creation for Arc onboarding
- **Role Assignments**: Proper RBAC for Arc servers
- **Private Link Support**: Secure connectivity via private endpoints
- **Hybrid Connectivity**: On-premises server management from Azure
- **Automated Onboarding**: Scripts for streamlined server registration
- **Resource Group Scope**: Targeted permissions for Arc resources

## Architecture

### Azure Arc Service Principal
- **Purpose**: Authentication for Arc agent installation and management
- **Permissions**: Azure Connected Machine Onboarding role
- **Scope**: Resource group level access
- **Credentials**: Automatically generated client secret

### Role Assignments
- **Azure Connected Machine Onboarding**: Required for Arc agent registration
- **Reader**: Optional read access for monitoring and inventory
- **Custom Roles**: Support for custom Arc-specific permissions

### Private Link (Optional)
- **Private Endpoints**: Secure connectivity to Arc services
- **Network Isolation**: Traffic stays within private networks
- **Hybrid Connectivity**: Works with ExpressRoute and VPN

## Usage

```hcl
module "arc" {
  source = "./modules/arc"
  
  project_name        = var.project_name
  environment         = var.environment
  resource_group_id   = azurerm_resource_group.main.id
  
  # Service Principal Configuration
  create_arc_service_principal = var.create_arc_service_principal
  
  # Role Assignment Configuration
  arc_onboarding_role_assignment = var.arc_onboarding_role_assignment
  
  # Private Link Configuration (Optional)
  deploy_arc_private_link = var.deploy_arc_private_link
  arc_private_link_subnet_id = module.networking.arc_subnet_id
  
  tags = var.tags
}
```

## Service Principal Configuration

### Basic Configuration
```hcl
# Create Arc service principal
create_arc_service_principal = true

# Assign Arc onboarding role
arc_onboarding_role_assignment = true

# Service principal settings
arc_sp_display_name = "sp-arc-onboarding-${var.project_name}-${var.environment}"
```

### Advanced Configuration
```hcl
# Custom role assignments
arc_custom_roles = [
  "Azure Connected Machine Onboarding",
  "Reader",
  "Log Analytics Reader"
]

# Specific resource scope
arc_role_scope = "/subscriptions/${var.subscription_id}/resourceGroups/${var.resource_group_name}"
```

## Private Link Configuration

### Arc Private Link Scope
```hcl
# Enable Arc private link
deploy_arc_private_link = true

# Private link scope configuration
resource "azurerm_arc_private_link_scope" "arc_pls" {
  name                = "arc-pls-${var.project_name}-${var.environment}"
  resource_group_name = var.resource_group_name
  location            = var.location
  
  public_network_access_enabled = false
}

# Private endpoint for Arc services
resource "azurerm_private_endpoint" "arc_pe" {
  name                = "pe-arc-${var.project_name}-${var.environment}"
  location            = var.location
  resource_group_name = var.resource_group_name
  subnet_id           = var.arc_private_link_subnet_id

  private_service_connection {
    name                           = "psc-arc"
    private_connection_resource_id = azurerm_arc_private_link_scope.arc_pls.id
    subresource_names              = ["hybridcompute"]
    is_manual_connection           = false
  }
}
```

## Server Onboarding

### Windows Server Onboarding
```powershell
# Example PowerShell script for Arc onboarding
$ServicePrincipalId = "sp-client-id-from-terraform-output"
$ServicePrincipalSecret = "sp-secret-from-terraform-output"
$TenantId = "your-tenant-id"
$SubscriptionId = "your-subscription-id"
$ResourceGroup = "your-resource-group"
$Location = "eastus"

# Download and install Arc agent
Invoke-WebRequest -Uri "https://aka.ms/AzureConnectedMachineAgent" -OutFile "AzureConnectedMachineAgent.msi"
Start-Process msiexec.exe -ArgumentList "/i AzureConnectedMachineAgent.msi /quiet" -Wait

# Connect to Azure Arc
& "$env:ProgramFiles\AzureConnectedMachineAgent\azcmagent.exe" connect `
  --service-principal-id $ServicePrincipalId `
  --service-principal-secret $ServicePrincipalSecret `
  --tenant-id $TenantId `
  --subscription-id $SubscriptionId `
  --resource-group $ResourceGroup `
  --location $Location
```

### Linux Server Onboarding
```bash
# Example bash script for Arc onboarding
SERVICE_PRINCIPAL_ID="sp-client-id-from-terraform-output"
SERVICE_PRINCIPAL_SECRET="sp-secret-from-terraform-output"
TENANT_ID="your-tenant-id"
SUBSCRIPTION_ID="your-subscription-id"
RESOURCE_GROUP="your-resource-group"
LOCATION="eastus"

# Download and install Arc agent
wget https://aka.ms/azcmagent -O ~/install_linux_azcmagent.sh
bash ~/install_linux_azcmagent.sh

# Connect to Azure Arc
sudo azcmagent connect \
  --service-principal-id "$SERVICE_PRINCIPAL_ID" \
  --service-principal-secret "$SERVICE_PRINCIPAL_SECRET" \
  --tenant-id "$TENANT_ID" \
  --subscription-id "$SUBSCRIPTION_ID" \
  --resource-group "$RESOURCE_GROUP" \
  --location "$LOCATION"
```

## Integration with Automation

### Custom Script Extension
```hcl
# Windows VM with Arc onboarding
resource "azurerm_virtual_machine_extension" "arc_onboarding" {
  name                 = "ArcOnboarding"
  virtual_machine_id   = azurerm_windows_virtual_machine.server.id
  publisher            = "Microsoft.Compute"
  type                 = "CustomScriptExtension"
  type_handler_version = "1.9"

  settings = jsonencode({
    fileUris = [
      "https://${module.storage.storage_account_name}.blob.core.windows.net/scripts/arc/windows-server-arc-setup.ps1"
    ]
    commandToExecute = "powershell -ExecutionPolicy Unrestricted -File windows-server-arc-setup.ps1 -TenantId ${var.azure_tenant_id} -SubscriptionId ${var.azure_subscription_id} -ServicePrincipalId ${module.arc.service_principal_client_id} -ServicePrincipalSecret ${module.arc.service_principal_client_secret}"
  })
}
```

## Monitoring and Management

### Azure Policy for Arc
```hcl
# Policy to auto-install monitoring agent
resource "azurerm_policy_assignment" "arc_monitoring" {
  name                 = "arc-monitoring-policy"
  scope                = azurerm_resource_group.main.id
  policy_definition_id = "/providers/Microsoft.Authorization/policyDefinitions/d69b1763-b96d-40b8-a2d9-ca31e9fd0d3e"
  
  parameters = jsonencode({
    logAnalytics = {
      value = module.monitoring.log_analytics_workspace_id
    }
  })
}
```

## Outputs

| Name | Description |
|------|-------------|
| `service_principal_client_id` | Client ID of the Arc service principal |
| `service_principal_client_secret` | Client secret of the Arc service principal |
| `service_principal_object_id` | Object ID of the Arc service principal |
| `arc_private_link_scope_id` | Resource ID of the Arc private link scope |
| `arc_private_endpoint_id` | Resource ID of the Arc private endpoint |

## Dependencies

- **Azure AD**: For service principal creation
- **Azure Resource Group**: Target for Arc servers
- **Networking Module**: Optional private link subnet
- **RBAC Permissions**: User must have rights to create service principals

## Cost Considerations

### Arc Server Costs
- **Arc-enabled Servers**: $6 per server per month
- **Extended Security Updates**: Additional cost for legacy OS
- **Azure Policy**: No additional cost for basic policies
- **Monitoring**: Additional cost if using Azure Monitor

### Private Link Costs
- **Private Endpoints**: $0.045/hour per endpoint (~$32/month)
- **Data Processing**: $0.045 per GB processed

### Management Tools
- **Update Management**: Included with Arc
- **Guest Configuration**: Included with Arc
- **Azure Security Center**: Additional cost for advanced features

### Cost Optimization
```hcl
# Disable private link for cost savings
deploy_arc_private_link = false  # Save ~$32/month per endpoint

# Use selective server onboarding
selective_arc_onboarding = true  # Only critical servers

# Leverage included monitoring
use_arc_included_monitoring = true  # vs premium monitoring
```

Estimated monthly cost per server: **$6-15** depending on monitoring and security features
