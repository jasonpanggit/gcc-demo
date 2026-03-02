# Agentic Demo

This demo focuses on the agentic EOL app running with App Service and related AI/data services.

## Files

- `eol-agentic-demo.tfvars`
- `eol-agentic-container-demo.tfvars`

## Typical deployment

```bash
terraform plan  -var-file="credentials.tfvars" -var-file="demos/agentic/eol-agentic-demo.tfvars"
terraform apply -var-file="credentials.tfvars" -var-file="demos/agentic/eol-agentic-demo.tfvars"
```

## What this scenario enables

- Agentic app infrastructure (`modules/agentic`)
- Azure OpenAI and App Insights integration
- Cosmos DB cache for EOL workflows (when enabled)
- Private endpoint and VNet integration options from tfvars

For application runtime/deploy details, see `app/agentic/eol/README.md` and `app/agentic/eol/deploy/README.md`.

---

For detailed technical documentation, see the [agentic module README](../../modules/agentic/README.md).
