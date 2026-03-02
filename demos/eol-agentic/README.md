# EOL Agentic Demo (Legacy Folder)

This folder keeps a scenario-specific `eol-agentic-demo.tfvars` plus notes.

## Files

- `eol-agentic-demo.tfvars`
- `terraform.tfvars`
- `arc-optional-notes.txt`

## Deploy

```bash
terraform plan  -var-file="credentials.tfvars" -var-file="demos/eol-agentic/eol-agentic-demo.tfvars"
terraform apply -var-file="credentials.tfvars" -var-file="demos/eol-agentic/eol-agentic-demo.tfvars"
```

If you are using current agentic demos, prefer `demos/agentic/*`.