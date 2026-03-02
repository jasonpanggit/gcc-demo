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
# Firewall Module

Creates hub/non-gen Azure Firewall resources and policy rule collection groups.

## Resources created (feature-flag dependent)

- Hub and non-gen public IPs
- Firewall policies
- Rule collection groups (Arc, agentic, SMTP, container apps, AVD, explicit proxy)
- Hub and non-gen Azure Firewall instances
- Route table association for non-gen firewall subnet path

## Source of truth

- Inputs: `modules/firewall/variables.tf`
- Outputs: `modules/firewall/outputs.tf`
- Implementation: `modules/firewall/main.tf`
  environment         = var.environment
