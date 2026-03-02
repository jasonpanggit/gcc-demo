# Gateways Module

Creates VPN/ExpressRoute connectivity components.

## Resources created (feature-flag dependent)

- Public IPs for gateways
- ExpressRoute virtual network gateway
- VPN virtual network gateway
- ExpressRoute circuit and peering
- ExpressRoute and S2S gateway connections
- Local network gateway

## Source of truth

- Inputs: `modules/gateways/variables.tf`
- Outputs: `modules/gateways/outputs.tf`
- Implementation: `modules/gateways/main.tf`
