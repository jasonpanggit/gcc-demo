# EOL Agentic App Demo

This demo deploys an agentic application that:
- Extracts Azure Arc software inventory (via Log Analytics)
- Resolves software end-of-life (EOL) from endoflife.date
- Offers a chat interface powered by Azure OpenAI
- Runs fully private via Private Endpoints in a Non-Gen VNet
- Egresses via the Non-Gen firewall

## How to run

Use the provided `run-demo.sh` at repo root with the tfvars file path:

```
./run-demo.sh demos/eol-agentic/eol-agentic-demo.tfvars credentials.tfvars
```

Requirements:
- Set your credentials in `credentials.tfvars`
- Ensure `deploy_hub_firewall` and `deploy_nongen_firewall` are true so outbound is routed via firewall
- Azure subscription allowlist for Azure OpenAI
