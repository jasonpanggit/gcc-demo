# Demo Configurations

This folder contains scenario-specific `tfvars` files used with the root Terraform stack.

## Available demos

- `agentic/eol-agentic-demo.tfvars`
- `agentic/eol-agentic-container-demo.tfvars`
- `arc/arc-demo.tfvars`
- `avd/avd-demo.tfvars`
- `eol-agentic/eol-agentic-demo.tfvars`
- `expressroute/expressroute-demo.tfvars`
- `hub-spoke/hub-onprem-basic-demo.tfvars`
- `hub-spoke/hub-non-gen-basic-demo.tfvars`
- `hub-spoke/hub-non-gen-gen-basic-demo.tfvars`
- `vpn/vpn-demo.tfvars`

## Usage

```bash
terraform plan  -var-file="credentials.tfvars" -var-file="demos/<scenario>/<file>.tfvars"
terraform apply -var-file="credentials.tfvars" -var-file="demos/<scenario>/<file>.tfvars"
```

Recommended interactive workflow:

```bash
./run-demo.sh
```

## Notes

- Each demo folder has a scoped README with scenario-specific guidance.
- Keep sensitive credentials only in `credentials.tfvars`.
- Always run `terraform destroy` for demo resources when finished.
