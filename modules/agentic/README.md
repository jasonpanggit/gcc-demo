# Agentic Module

Deploys App Service-based agentic app infrastructure and related AI/data resources.

## Resources created (feature-flag dependent)

- App Service plan + Linux Web App
- Application Insights
- Azure OpenAI account
- Cosmos DB account/database/container
- Private endpoints + private DNS zones for AOAI/Cosmos
- App managed-identity role assignments
- Bot registration / Teams channel resources
- Optional ACR, Bing Search cognitive account, AI Foundry account

## Typical usage

```hcl
module "agentic" {
  source = "./modules/agentic"
  # pass project/environment/network/workspace vars from root
}
```

## Source of truth

- Inputs: `modules/agentic/variables.tf`
- Outputs: `modules/agentic/outputs.tf`
- Implementation: `modules/agentic/main.tf`
