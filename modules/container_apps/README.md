# Container Apps Module

Deploys Container Apps-based runtime and supporting AI/data services.

## Resources created (feature-flag dependent)

- ACR, Container Apps Environment, and Container App
- Log Analytics workspace + App Insights
- Azure OpenAI and deployment
- Cosmos DB account/database/container
- AI project cognitive account
- Managed-identity role assignments
- Private endpoints for enabled services

## Source of truth

- Inputs: `modules/container_apps/variables.tf`
- Outputs: `modules/container_apps/outputs.tf`
- Implementation: `modules/container_apps/main.tf`
