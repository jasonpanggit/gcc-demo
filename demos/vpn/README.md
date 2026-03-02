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
