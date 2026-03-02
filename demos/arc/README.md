# Arc Demo

Deploys hybrid-management focused infrastructure with Arc onboarding support.

## File

- `arc-demo.tfvars`

## Deploy

```bash
terraform plan  -var-file="credentials.tfvars" -var-file="demos/arc/arc-demo.tfvars"
terraform apply -var-file="credentials.tfvars" -var-file="demos/arc/arc-demo.tfvars"
```

## Related components

- `modules/arc` for Arc service principal and Arc Private Link Scope
- `modules/compute` for Windows Server 2025 VM path used by Arc script onboarding
- `scripts/arc/windows-server-2025-arc-setup.ps1`
- `modules/monitoring` for Log Analytics and optional monitor private link

For post-deployment workbook alignment with Terraform outputs, run:

```bash
./workbooks/end-of-life/post-deploy-setup.sh
```
