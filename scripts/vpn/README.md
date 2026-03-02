# VPN Script

This folder contains VPN bootstrap automation for the on-prem simulation VM.

## File

- `windows-server-2016-vpn-setup.ps1`

## Terraform usage path

This script is used in the Windows Server 2016 VPN demo path when enabled:

```hcl
deploy_onprem_windows_server_2016 = true
onprem_windows_vpn_setup          = true
deploy_vpn_gateway                = true
```

Related components:

- `modules/compute`
- `modules/gateways`
- `demos/vpn/vpn-demo.tfvars`
