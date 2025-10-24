# Container Apps Module

This Terraform module deploys Azure Container Apps with multi-container support and private networking.

## Features

- **Multi-Container Support**: Main application + Azure MCP Server sidecar
- **Private Networking**: VNet integration and private endpoints
- **Managed Identity**: System-assigned identity for secure authentication
- **Azure Services Integration**: Azure OpenAI, Cosmos DB, AI Foundry
- **Firewall Egress**: Route traffic through Azure Firewall
- **Container Registry**: Optional ACR deployment with private endpoints

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  Container Apps Environment (VNet Integrated)               │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  Container App                                        │  │
│  │  ┌─────────────────┐  ┌──────────────────────────┐   │  │
│  │  │ Main App        │  │ Azure MCP Sidecar        │   │  │
│  │  │ (FastAPI)       │──│ (Microsoft Official)     │   │  │
│  │  │ Port: 8000      │  │ Port: 5001 (localhost)   │   │  │
│  │  └─────────────────┘  └──────────────────────────┘   │  │
│  │  Managed Identity: System-Assigned                   │  │
│  └───────────────────────────────────────────────────────┘  │
│  Static IP: For firewall rules                              │
└─────────────────────────────────────────────────────────────┘
              │
              │ All egress traffic
              ▼
┌─────────────────────────────────────────────────────────────┐
│  Azure Firewall (Non-Gen VNet)                              │
│  - Application rules for Azure services                     │
│  - Network rules for internet access                        │
│  - DNS proxy enabled                                        │
└─────────────────────────────────────────────────────────────┘
              │
              │ Allowed traffic
              ▼
        Internet / Azure Services
```

## Usage

```hcl
module "container_apps" {
  source = "./modules/container_apps"

  project_name        = "gcc"
  environment         = "demo"
  location            = "Australia East"
  resource_group_name = azurerm_resource_group.rg.name

  # Networking
  container_apps_subnet_id     = module.networking.container_apps_subnet_id
  private_endpoint_subnet_id   = module.networking.private_endpoint_subnet_id
  internal_load_balancer_enabled = true

  # Container Images
  app_container_image = "acreolggcdemo.azurecr.io/eol-app:latest"
  mcp_container_image = "mcr.microsoft.com/azure-sdk/azure-mcp:latest"

  # Azure Services
  deploy_aoai        = true
  deploy_cosmos_db   = true
  deploy_ai_foundry  = true
  deploy_acr         = true

  # Private Endpoints
  deploy_private_endpoints = true

  # Log Analytics
  workspace_resource_id = module.monitoring.workspace_id
  workspace_guid        = module.monitoring.workspace_guid

  tags = {
    Environment = "demo"
    Project     = "gcc"
  }
}
```

## Container Communication

The multi-container setup uses **localhost** for inter-container communication:

- Main app connects to MCP server at `http://localhost:5001`
- Both containers share the same network namespace
- No service mesh or external networking required

## Firewall Egress

The Container Apps subnet is configured with a User-Defined Route (UDR) to force all traffic through the Azure Firewall:

```hcl
# Route table applied to container_apps_subnet
resource "azurerm_route" "container_apps_to_firewall" {
  name                   = "container-apps-to-firewall"
  resource_group_name    = var.resource_group_name
  route_table_name       = var.route_table_name
  address_prefix         = "0.0.0.0/0"
  next_hop_type          = "VirtualAppliance"
  next_hop_in_ip_address = var.firewall_private_ip
}
```

## Required Firewall Rules

The following firewall rules are required for Container Apps:

### Application Rules
- Azure Container Registry: `*.azurecr.io` (HTTPS)
- Microsoft Container Registry: `mcr.microsoft.com` (HTTPS)
- Azure OpenAI: `*.openai.azure.com` (HTTPS)
- Azure Resource Manager: `management.azure.com` (HTTPS)
- Azure Active Directory: `login.microsoftonline.com` (HTTPS)

### Network Rules
- Azure services: AzureCloud service tag (TCP 443)
- Container Apps control plane: Based on region

## Inputs

| Name | Description | Type | Default | Required |
|------|-------------|------|---------|----------|
| deploy_container_apps | Whether to deploy Container Apps | bool | false | no |
| container_apps_subnet_id | Subnet ID for Container Apps infrastructure | string | n/a | yes |
| private_endpoint_subnet_id | Subnet ID for private endpoints | string | n/a | yes |
| app_container_image | Main application container image | string | n/a | yes |
| deploy_aoai | Deploy Azure OpenAI | bool | true | no |
| deploy_cosmos_db | Deploy Cosmos DB | bool | true | no |
| deploy_private_endpoints | Deploy private endpoints | bool | true | no |

## Outputs

| Name | Description |
|------|-------------|
| container_app_url | Container App URL |
| container_app_identity_principal_id | Managed identity principal ID |
| acr_login_server | Azure Container Registry login server |
| aoai_endpoint | Azure OpenAI endpoint |
| cosmos_db_endpoint | Cosmos DB endpoint |

## Managed Identity Permissions

The Container App's managed identity is automatically granted:

- **Reader** on subscription (for Azure MCP)
- **Contributor** on resource group (for Azure MCP)
- **Cognitive Services User** on Azure OpenAI
- **Cosmos DB Account Contributor** on Cosmos DB
- **AcrPull** on Azure Container Registry

## Private Endpoints

When `deploy_private_endpoints = true`, the module creates private endpoints for:

- Azure OpenAI (`account` subresource)
- Cosmos DB (`Sql` subresource)
- Azure Container Registry (`registry` subresource)
- Azure AI Foundry (`account` subresource)

## Deployment

See the [deployment script](../../../app/agentic/eol/deploy/deploy-container-apps.sh) for automated deployment.
