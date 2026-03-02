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
