# Arc Script

This folder contains Azure Arc onboarding automation for Windows Server 2025.

## File

- `windows-server-2025-arc-setup.ps1`

## Terraform usage path

Used by the compute deployment path when Arc setup is enabled in tfvars:

```hcl
deploy_onprem_windows_server_2025 = true
onprem_windows_arc_setup          = true
```

Related module/script flow:

- `modules/compute`
- `modules/arc`
- `demos/arc/arc-demo.tfvars`
