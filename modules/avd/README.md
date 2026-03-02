# AVD Module

Creates Azure Virtual Desktop resources for the demo stack.

## Resources created

- AVD workspace, host pool, app group, and association
- Host pool registration token info
- Session host/private endpoint subnets and route table association
- FSLogix storage account + share + private endpoint + private DNS
- Session host VMs and AVD/AAD extensions
- Diagnostic settings for AVD components

## Source of truth

- Inputs: `modules/avd/variables.tf`
- Outputs: `modules/avd/outputs.tf`
- Implementation: `modules/avd/main.tf`

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
