# Networking Module

Builds core VNet/subnet topology and peering for hub, gen, non-gen, and on-prem patterns.

## Resources created (feature-flag dependent)

- Hub, gen, non-gen, and on-prem virtual networks
- Subnets for gateway/firewall/route server/bastion/NVA/apps/private-endpoints
- Route Server and Bastion dependencies
- NSGs for NVA/Squid/on-prem paths
- VNet peering links across enabled networks

## Source of truth

- Inputs: `modules/networking/variables.tf`
- Outputs: `modules/networking/outputs.tf`
- Implementation: `modules/networking/main.tf`
