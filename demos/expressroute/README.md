# ExpressRoute Demo

Deploys ExpressRoute-focused connectivity resources via `modules/gateways` and related networking modules.

## File

- `expressroute-demo.tfvars`

## Deploy

```bash
terraform plan  -var-file="credentials.tfvars" -var-file="demos/expressroute/expressroute-demo.tfvars"
terraform apply -var-file="credentials.tfvars" -var-file="demos/expressroute/expressroute-demo.tfvars"
```

## Notes

- Requires a valid ExpressRoute circuit/provider setup for end-to-end connectivity.
- Demo settings can optionally combine VPN/Route Server depending on selected flags.
- Main gateway implementation lives in `modules/gateways`.
