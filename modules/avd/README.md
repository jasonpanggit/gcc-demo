# AVD (Azure Virtual Desktop) Module

This module manages Azure Virtual Desktop infrastructure including host pools, workspaces, application groups, session hosts, and supporting services for virtual desktop environments.

## Features

- **Host Pools**: Pooled and personal desktop configurations
- **Session Hosts**: Windows 11/10 Enterprise multi-session VMs
- **Application Groups**: Desktop and RemoteApp application publishing
- **Workspaces**: User access portals for published resources
- **FSLogix Storage**: User profile containers and Office containers
- **Private Endpoints**: Secure connectivity for AVD services
- **Auto-scaling**: Cost optimization through session host scaling
- **Monitoring**: Integration with Azure Monitor and Log Analytics

## Architecture

### Host Pool Types
- **Pooled**: Shared desktop sessions for multiple users
- **Personal**: Dedicated desktop sessions per user
- **Multi-session**: Windows 11/10 Enterprise multi-session support
- **Validation Environment**: Testing environment for updates

### Session Hosts
- **VM Configuration**: Standard_D4s_v5 (4 vCPU, 16GB RAM) by default
- **OS Images**: Windows 11/10 Enterprise multi-session
- **Domain Join**: Azure AD or hybrid domain join support
- **Auto-scaling**: Scheduled and load-based scaling

### Storage (FSLogix)
- **Profile Containers**: User profile storage
- **Office Containers**: Office 365 data containers
- **Premium Storage**: SSD storage for performance
- **Private Endpoints**: Secure storage access

## Usage

```hcl
module "avd" {
  source = "./modules/avd"
  
  project_name        = var.project_name
  environment         = var.environment
  location            = var.location
  resource_group_id   = azurerm_resource_group.main.id
  
  # Virtual Network Configuration
  vnet_resource_group        = module.networking.hub_vnet_resource_group
  vnet_name                  = module.networking.hub_vnet_name
  session_host_subnet_prefix = var.avd_session_host_subnet_prefix
  private_endpoint_subnet_prefix = var.avd_private_endpoint_subnet_prefix
  
  # Host Pool Configuration
  host_pool_name              = var.avd_host_pool_name
  host_pool_type              = var.avd_host_pool_type
  host_pool_load_balancer_type = var.avd_host_pool_load_balancer_type
  host_pool_max_sessions      = var.avd_host_pool_max_sessions
  
  # Session Host Configuration
  session_host_count          = var.avd_session_host_count
  session_host_vm_size        = var.avd_session_host_vm_size
  session_host_vm_sku         = var.avd_session_host_vm_sku
  
  # Domain Configuration
  domain_name                 = var.avd_domain_name
  domain_user_upn             = var.avd_domain_user_upn
  domain_password             = var.avd_domain_password
  ou_path                     = var.avd_ou_path
  
  # FSLogix Configuration
  enable_fslogix              = var.avd_enable_fslogix
  fslogix_storage_sku         = var.avd_fslogix_storage_sku
  
  # Private Endpoint Configuration
  deploy_private_endpoints    = var.avd_deploy_private_endpoints
  
  # Monitoring
  log_analytics_workspace_id  = module.monitoring.log_analytics_workspace_id
  
  tags = var.tags
}
```

## Host Pool Configuration

### Pooled Desktop Configuration
```hcl
# Pooled host pool for shared desktops
host_pool_type = "Pooled"
host_pool_load_balancer_type = "BreadthFirst"  # or "DepthFirst"
host_pool_max_sessions = 16  # Max users per session host

# Session host settings
session_host_count = 3
session_host_vm_size = "Standard_D4s_v5"
session_host_vm_sku = "win11-22h2-ent"
```

### Personal Desktop Configuration
```hcl
# Personal host pool for dedicated desktops
host_pool_type = "Personal"
host_pool_assignment_type = "Automatic"  # or "Direct"

# Session host settings
session_host_count = 5
session_host_vm_size = "Standard_D2s_v5"
session_host_vm_sku = "win11-22h2-ent"
```

## Session Host SKUs

### Available VM SKUs
```hcl
# Windows 11 Enterprise Multi-session
session_host_vm_sku = "win11-22h2-ent"     # Windows 11 22H2
session_host_vm_sku = "win11-21h2-ent"     # Windows 11 21H2

# Windows 10 Enterprise Multi-session  
session_host_vm_sku = "win10-22h2-ent-g2"  # Windows 10 22H2 Gen2
session_host_vm_sku = "win10-21h2-ent-g2"  # Windows 10 21H2 Gen2
```

### VM Size Recommendations
```hcl
# Light workloads (2-4 users per core)
session_host_vm_size = "Standard_D2s_v5"   # 2 vCPU, 8GB RAM

# Standard workloads (1-2 users per core)
session_host_vm_size = "Standard_D4s_v5"   # 4 vCPU, 16GB RAM

# Heavy workloads (1 user per core)
session_host_vm_size = "Standard_D8s_v5"   # 8 vCPU, 32GB RAM

# GPU workloads
session_host_vm_size = "Standard_NV12s_v3" # 12 vCPU, 112GB RAM, GPU
```

## FSLogix Configuration

### Profile Containers
```hcl
# Enable FSLogix profile containers
enable_fslogix = true
fslogix_storage_sku = "Premium_LRS"  # Premium SSD for performance

# Storage configuration
fslogix_storage_size_gb = 1024      # 1TB storage
fslogix_container_type = "Profile"   # Profile containers only
```

### Office Containers
```hcl
# Enable both profile and Office containers
fslogix_container_type = "ProfileOffice"
fslogix_office_container_size_gb = 30  # 30GB for Office data
```

## Auto-scaling Configuration

### Scheduled Scaling
```hcl
# Auto-scaling plan
resource "azurerm_virtual_desktop_scaling_plan" "scaling" {
  name                = "avd-scaling-${var.project_name}-${var.environment}"
  location            = var.location
  resource_group_name = var.resource_group_name
  friendly_name       = "AVD Auto-scaling Plan"
  description         = "Scaling plan for AVD session hosts"
  time_zone           = "Eastern Standard Time"

  schedule {
    name                                 = "weekdays_schedule"
    days_of_week                        = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
    ramp_up_start_time                  = "05:00"
    ramp_up_load_balancing_algorithm    = "BreadthFirst"
    ramp_up_minimum_hosts_percent       = 20
    ramp_up_capacity_threshold_percent  = 60

    peak_start_time                     = "09:00"
    peak_load_balancing_algorithm       = "DepthFirst"

    ramp_down_start_time                = "18:00"
    ramp_down_load_balancing_algorithm  = "DepthFirst"
    ramp_down_minimum_hosts_percent     = 10
    ramp_down_capacity_threshold_percent = 90
    
    off_peak_start_time                 = "20:00"
    off_peak_load_balancing_algorithm   = "DepthFirst"
  }
}
```

## Private Endpoint Configuration

### AVD Service Private Endpoints
```hcl
# Enable private endpoints for AVD services
deploy_private_endpoints = true

# Private endpoints created:
# - Host Pool (workspace feed)
# - Workspace (user access)
# - Storage Account (FSLogix)
```

## Outputs

| Name | Description |
|------|-------------|
| `host_pool_id` | Resource ID of the AVD host pool |
| `host_pool_name` | Name of the AVD host pool |
| `workspace_id` | Resource ID of the AVD workspace |
| `application_group_id` | Resource ID of the desktop application group |
| `session_host_ids` | Resource IDs of the session hosts |
| `fslogix_storage_account_id` | Resource ID of the FSLogix storage account |
| `fslogix_file_share_url` | URL of the FSLogix file share |
| `private_endpoint_ids` | Resource IDs of the private endpoints |

## User Assignment

### Application Group Assignment
```hcl
# Assign users to desktop application group
resource "azurerm_role_assignment" "avd_users" {
  scope                = azurerm_virtual_desktop_application_group.desktop.id
  role_definition_name = "Desktop Virtualization User"
  principal_id         = data.azuread_group.avd_users.object_id
}
```

## Dependencies

- **Networking Module**: Requires VNet and subnet configuration
- **Monitoring Module**: Optional Log Analytics integration
- **Azure AD**: For user and group assignments
- **Domain Services**: For domain join (Azure AD DS or on-premises AD)

## Cost Considerations

### Session Host Costs (per VM)
- **Standard_D2s_v5**: ~$90-120/month (2 vCPU, 8GB)
- **Standard_D4s_v5**: ~$180-240/month (4 vCPU, 16GB)
- **Standard_D8s_v5**: ~$360-480/month (8 vCPU, 32GB)
- **Standard_NV12s_v3**: ~$1,200-1,500/month (GPU)

### Storage Costs
- **FSLogix Premium Storage**: ~$0.15/GB/month
- **Standard Storage**: ~$0.045/GB/month
- **File Share**: ~$0.60/GB/month for Premium

### Additional Costs
- **AVD Access Rights**: Included with Microsoft 365 or $6/user/month
- **Windows 11/10 Enterprise**: Included with eligible licenses
- **Private Endpoints**: ~$32/month per endpoint

### Sample Configurations
```hcl
# Small deployment (25 users)
session_host_count = 2
session_host_vm_size = "Standard_D4s_v5"
# Cost: ~$400-500/month

# Medium deployment (100 users)  
session_host_count = 6
session_host_vm_size = "Standard_D4s_v5"
# Cost: ~$1,200-1,500/month

# Large deployment (500 users)
session_host_count = 25
session_host_vm_size = "Standard_D8s_v5"
# Cost: ~$9,000-12,000/month
```

### Cost Optimization
```hcl
# Use auto-scaling to reduce costs
enable_auto_scaling = true

# Use spot instances for dev/test
session_host_spot_instances = true  # 60-90% savings

# Optimize storage
fslogix_storage_sku = "Standard_LRS"  # vs Premium_LRS
```

Estimated monthly cost: **$200-10,000+** depending on user count and VM sizes
