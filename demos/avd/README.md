# AVD Demo

Deploys Azure Virtual Desktop resources via the shared root stack and `modules/avd`.

## File

- `avd-demo.tfvars`

## Deploy

```bash
terraform plan  -var-file="credentials.tfvars" -var-file="demos/avd/avd-demo.tfvars"
terraform apply -var-file="credentials.tfvars" -var-file="demos/avd/avd-demo.tfvars"
```

## Includes

- AVD workspace, host pool, and app group
- Session host subnet and private endpoint subnet
- FSLogix storage account and share path
- Diagnostic settings to Log Analytics (when enabled in tfvars)

Module implementation: `modules/avd`.
