# GCC Demo Platform

Terraform-based demo platform for hybrid connectivity, security, Azure Arc, AVD, and the EOL agentic application.

## What is in this repo

- Root deployment entry points: `main.tf`, `variables.tf`, `outputs.tf`, `run-demo.sh`
- Demo configurations: `demos/*/*.tfvars`
- Reusable modules: `modules/*`
- EOL application: `app/agentic/eol`
- VM/bootstrap scripts: `scripts/*`
- Workbook automation: `workbooks/end-of-life`

## Quick start

```bash
cp credentials.tfvars.example credentials.tfvars
# edit credentials.tfvars

./run-demo.sh
```

Manual plan/apply example:

```bash
terraform init
terraform plan  -var-file="credentials.tfvars" -var-file="demos/arc/arc-demo.tfvars"
terraform apply -var-file="credentials.tfvars" -var-file="demos/arc/arc-demo.tfvars"
```

## Active demo tfvars

- `demos/agentic/eol-agentic-demo.tfvars`
- `demos/agentic/eol-agentic-container-demo.tfvars`
- `demos/arc/arc-demo.tfvars`
- `demos/avd/avd-demo.tfvars`
- `demos/eol-agentic/eol-agentic-demo.tfvars`
- `demos/expressroute/expressroute-demo.tfvars`
- `demos/hub-spoke/hub-onprem-basic-demo.tfvars`
- `demos/hub-spoke/hub-non-gen-basic-demo.tfvars`
- `demos/hub-spoke/hub-non-gen-gen-basic-demo.tfvars`
- `demos/vpn/vpn-demo.tfvars`

## Modules in use

- `modules/networking`
- `modules/routing`
- `modules/firewall`
- `modules/gateways`
- `modules/compute`
- `modules/storage`
- `modules/monitoring`
- `modules/arc`
- `modules/agentic`
- `modules/container_apps`
- `modules/avd`

## EOL app and workbook flow

1. Deploy a demo (typically Arc or Agentic).
2. Run `workbooks/end-of-life/post-deploy-setup.sh`.
3. For app runtime/deploy details, see `app/agentic/eol/README.md` and `app/agentic/eol/deploy/README.md`.

## Cleanup

```bash
terraform destroy -var-file="credentials.tfvars" -var-file="demos/arc/arc-demo.tfvars"
```
