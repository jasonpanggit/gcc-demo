# Hub-Spoke Demos

This folder contains three hub/spoke variants.

## Files

- `hub-onprem-basic-demo.tfvars`
- `hub-non-gen-basic-demo.tfvars`
- `hub-non-gen-gen-basic-demo.tfvars`

## Deploy example

```bash
terraform plan  -var-file="credentials.tfvars" -var-file="demos/hub-spoke/hub-non-gen-basic-demo.tfvars"
terraform apply -var-file="credentials.tfvars" -var-file="demos/hub-spoke/hub-non-gen-basic-demo.tfvars"
```

## Scope

- Hub networking (`modules/networking`)
- Route tables (`modules/routing`)
- Optional firewall and gateway combinations (`modules/firewall`, `modules/gateways`)
