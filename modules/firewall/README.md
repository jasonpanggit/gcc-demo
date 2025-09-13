# Firewall Module

This module manages Azure Firewall and Azure Firewall Policy configurations for both hub and non-gen environments, providing advanced network security and traffic filtering capabilities.

## Features

- **Azure Firewall**: Premium tier firewall with advanced security features
- **Firewall Policies**: Centralized policy management with rule collections
- **DNS Proxy**: Configurable DNS proxy functionality
- **Explicit Proxy**: Optional explicit proxy configuration
- **Force Tunneling**: Support for forced tunneling scenarios
- **IDPS**: Intrusion Detection and Prevention System
- **TLS Inspection**: SSL/TLS traffic inspection capabilities
- **Rule Collections**: Application, network, and NAT rule collections
- **Threat Intelligence**: Microsoft threat intelligence integration

## Architecture

### Hub Firewall
- **SKU**: Premium tier for advanced security features
- **DNS Proxy**: Configurable DNS proxy with custom settings
- **Explicit Proxy**: Optional HTTP/HTTPS proxy functionality
- **Threat Intelligence**: Alert and deny modes available
- **IDPS**: Signature-based threat detection

### Non-Gen Firewall
- **Dedicated Firewall**: Separate firewall for non-generative workloads
- **Simplified Configuration**: Focused on non-gen specific rules
- **DNS Proxy**: Configurable DNS proxy support

## Usage

```hcl
module "firewall" {
  source = "./modules/firewall"
  
  project_name        = var.project_name
  environment         = var.environment
  location            = var.location
  resource_group_name = azurerm_resource_group.main.name
  
  # Subnet Configuration
  firewall_subnet_id         = module.networking.hub_firewall_subnet_id
  nongen_firewall_subnet_id  = module.networking.nongen_firewall_subnet_id
  
  # Hub Firewall Configuration
  deploy_hub_vnet                           = var.deploy_hub_vnet
  deploy_hub_firewall                       = var.deploy_hub_firewall
  hub_firewall_sku_tier                     = var.hub_firewall_sku_tier
  hub_firewall_dns_proxy_enabled            = var.hub_firewall_dns_proxy_enabled
  hub_firewall_explicit_proxy               = var.hub_firewall_explicit_proxy
  hub_firewall_explicit_proxy_http_port     = var.hub_firewall_explicit_proxy_http_port
  hub_firewall_explicit_proxy_https_port    = var.hub_firewall_explicit_proxy_https_port
  hub_firewall_threat_intel_mode            = var.hub_firewall_threat_intel_mode
  hub_firewall_idps_mode                    = var.hub_firewall_idps_mode
  hub_firewall_force_tunneling              = var.hub_firewall_force_tunneling
  
  # Non-Gen Firewall Configuration
  deploy_nongen_vnet                        = var.deploy_nongen_vnet
  deploy_nongen_firewall                    = var.deploy_nongen_firewall
  nongen_firewall_sku_tier                  = var.nongen_firewall_sku_tier
  nongen_firewall_dns_proxy_enabled         = var.nongen_firewall_dns_proxy_enabled
  nongen_firewall_threat_intel_mode         = var.nongen_firewall_threat_intel_mode
  
  # Agentic Application Rules
  deploy_agentic_app                        = var.deploy_agentic_app
  agentic_app_allowed_urls                  = var.agentic_app_allowed_urls
  
  tags = var.tags
}
```

## Configuration Options

### DNS Proxy Configuration
```hcl
# Enable DNS proxy on hub firewall
hub_firewall_dns_proxy_enabled = true

# Enable DNS proxy on non-gen firewall  
nongen_firewall_dns_proxy_enabled = true
```

### Explicit Proxy Configuration
```hcl
# Enable explicit proxy on hub firewall
hub_firewall_explicit_proxy = true
hub_firewall_explicit_proxy_http_port = 8080
hub_firewall_explicit_proxy_https_port = 8443
```

### Security Features
```hcl
# Threat intelligence configuration
hub_firewall_threat_intel_mode = "Alert"  # Alert, Deny, Off

# IDPS configuration
hub_firewall_idps_mode = "Alert"  # Alert, Deny, Off

# Force tunneling (requires management subnet)
hub_firewall_force_tunneling = false
```

## Rule Collections

### Application Rule Collections
- **Allow-Azure-Services**: Access to core Azure services
- **Allow-Agentic-URLs**: Specific URLs for agentic applications
- **Allow-Windows-Update**: Windows Update and security updates

### Network Rule Collections
- **Allow-DNS**: DNS resolution rules
- **Allow-Internal**: Internal network communication
- **Allow-Azure-Services**: Azure service communication

### NAT Rule Collections
- **DNAT-Rules**: Destination NAT for inbound traffic

## Outputs

| Name | Description |
|------|-------------|
| `hub_firewall_id` | Resource ID of the hub Azure Firewall |
| `hub_firewall_private_ip` | Private IP address of the hub firewall |
| `hub_firewall_public_ip` | Public IP address of the hub firewall |
| `nongen_firewall_id` | Resource ID of the non-gen Azure Firewall |
| `nongen_firewall_private_ip` | Private IP address of the non-gen firewall |
| `hub_firewall_policy_id` | Resource ID of the hub firewall policy |
| `nongen_firewall_policy_id` | Resource ID of the non-gen firewall policy |

## Dependencies

- **Networking Module**: Requires firewall subnets
- **Azure Resource Group**: Target resource group
- **Public IP**: For firewall external connectivity

## Cost Considerations

- **Azure Firewall Premium**: ~$1,200-1,500 per month per firewall
- **Data Processing**: ~$0.016 per GB processed
- **Public IP**: ~$3 per month per static IP
- **Firewall Policy**: No additional cost

### Cost Optimization Options
```hcl
# Use Standard tier for lower cost
hub_firewall_sku_tier = "Standard"  # ~$800/month vs Premium ~$1,200/month

# Disable features not needed
hub_firewall_explicit_proxy = false
hub_firewall_dns_proxy_enabled = false
```

Estimated monthly cost per firewall: **$800-1,500** depending on tier and data processing
