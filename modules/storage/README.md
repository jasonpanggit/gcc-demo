# Storage Module

This module manages Azure Storage accounts and containers for storing automation scripts, VM extensions, and configuration files used throughout the infrastructure deployment.

## Features

- **Script Storage**: Dedicated storage for PowerShell and Bash scripts
- **Public Access**: Configured for VM Custom Script Extension access
- **Blob Containers**: Organized storage for different script types
- **LRS Replication**: Locally redundant storage for cost optimization
- **SAS Tokens**: Secure access to private scripts when needed

## Architecture

### Storage Account
- **Tier**: Standard storage tier for general purpose use
- **Replication**: Locally Redundant Storage (LRS) for cost efficiency
- **Access**: Public network access enabled for VM extensions
- **Containers**: Organized by script type and purpose

### Container Structure
- **scripts**: General automation scripts
- **arc**: Azure Arc onboarding scripts
- **vpn**: VPN configuration scripts
- **nva**: Network Virtual Appliance scripts
- **squid**: Proxy configuration scripts

## Usage

```hcl
module "storage" {
  source = "./modules/storage"
  
  project_name        = var.project_name
  environment         = var.environment
  location            = var.location
  resource_group_name = azurerm_resource_group.main.name
  
  # Storage Configuration
  deploy_script_storage = var.deploy_script_storage
  
  # Script Types
  onprem_windows_arc_onboarding = var.onprem_windows_arc_setup
  onprem_windows_vpn_setup      = var.onprem_windows_vpn_setup
  deploy_linux_nva              = var.deploy_linux_nva
  deploy_squid_proxy            = var.deploy_squid_proxy
  
  tags = var.tags
}
```

## Storage Configuration

### Basic Configuration
```hcl
# Enable script storage
deploy_script_storage = true

# Script types to support
onprem_windows_arc_setup = true
onprem_windows_vpn_setup = true
deploy_linux_nva = true
deploy_squid_proxy = true
```

### Advanced Configuration
```hcl
# Storage account settings
storage_account_tier = "Standard"
storage_replication_type = "LRS"
public_network_access_enabled = true
allow_nested_items_to_be_public = true
```

## Script Storage Structure

### PowerShell Scripts (Windows)
```
scripts/
├── arc/
│   └── windows-server-2025-arc-setup.ps1
├── vpn/
│   └── windows-server-2016-vpn-setup.ps1
└── common/
    └── windows-utilities.ps1
```

### Bash Scripts (Linux)
```
scripts/
├── nva/
│   └── nva-config.sh
├── squid/
│   └── squid-config.sh
└── common/
    └── linux-utilities.sh
```

## Integration with VM Extensions

### Custom Script Extension (Windows)
```hcl
# Example usage in VM configuration
resource "azurerm_virtual_machine_extension" "arc_setup" {
  name                 = "ArcSetup"
  virtual_machine_id   = azurerm_windows_virtual_machine.vm.id
  publisher            = "Microsoft.Compute"
  type                 = "CustomScriptExtension"
  type_handler_version = "1.9"

  settings = jsonencode({
    fileUris = [
      "https://${module.storage.storage_account_name}.blob.core.windows.net/scripts/arc/windows-server-2025-arc-setup.ps1"
    ]
    commandToExecute = "powershell -ExecutionPolicy Unrestricted -File windows-server-2025-arc-setup.ps1 -TenantId ${var.azure_tenant_id} -SubscriptionId ${var.azure_subscription_id}"
  })
}
```

### Custom Script Extension (Linux)
```hcl
# Example usage for Linux VMs
resource "azurerm_virtual_machine_extension" "nva_config" {
  name                 = "NVAConfig"
  virtual_machine_id   = azurerm_linux_virtual_machine.nva.id
  publisher            = "Microsoft.Azure.Extensions"
  type                 = "CustomScript"
  type_handler_version = "2.1"

  settings = jsonencode({
    fileUris = [
      "https://${module.storage.storage_account_name}.blob.core.windows.net/scripts/nva/nva-config.sh"
    ]
    commandToExecute = "bash nva-config.sh"
  })
}
```

## Security Considerations

### Public Access
- Storage configured for public blob access to support VM extensions
- Individual containers can be configured for private access
- SAS tokens available for additional security when needed

### Access Control
```hcl
# Container with private access
resource "azurerm_storage_container" "private_scripts" {
  name                  = "private-scripts"
  storage_account_name  = azurerm_storage_account.sa_scripts[0].name
  container_access_type = "private"
}

# Generate SAS token for private access
data "azurerm_storage_account_blob_container_sas" "scripts_sas" {
  connection_string = azurerm_storage_account.sa_scripts[0].primary_connection_string
  container_name    = azurerm_storage_container.private_scripts.name
  https_only        = true
  
  start  = timestamp()
  expiry = timeadd(timestamp(), "24h")
  
  permissions {
    read   = true
    add    = false
    create = false
    write  = false
    delete = false
    list   = true
  }
}
```

## Outputs

| Name | Description |
|------|-------------|
| `storage_account_id` | Resource ID of the storage account |
| `storage_account_name` | Name of the storage account |
| `primary_blob_endpoint` | Primary blob service endpoint |
| `primary_access_key` | Primary access key for the storage account |
| `container_name` | Name of the scripts container |
| `script_storage_url` | Base URL for accessing scripts |

## Dependencies

- **Azure Resource Group**: Target resource group
- **Network Access**: Public network access for VM extension downloads

## Cost Considerations

### Storage Costs
- **Storage Account**: No base cost for Standard tier
- **Data Storage**: ~$0.02 per GB per month (LRS)
- **Transactions**: ~$0.0004 per 10,000 transactions
- **Data Transfer**: Outbound data transfer charges apply

### Typical Usage
- **Script Files**: Usually < 1 GB total
- **Transactions**: Low volume (VM extensions only)
- **Transfer**: Minimal for script downloads

### Cost Optimization
```hcl
# Use LRS replication for lower cost
account_replication_type = "LRS"  # vs GRS/ZRS

# Disable when not using automation
deploy_script_storage = false

# Use lifecycle policies for cleanup
lifecycle_rule {
  enabled = true
  
  blob_types = ["blockBlob"]
  
  actions {
    base_blob {
      delete_after_days_since_modification_greater_than = 90
    }
  }
}
```

Estimated monthly cost: **$2-10** depending on storage usage and transfer
