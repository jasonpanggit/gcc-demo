# Monitoring Module

Creates Log Analytics and monitor private-link resources used across demos.

## Resources created (feature-flag dependent)

- Log Analytics workspace
- Data collection endpoint
- Monitor Private Link Scope and scoped services
- Private endpoint + monitor private DNS zones + VNet links

## Source of truth

- Inputs: `modules/monitoring/variables.tf`
- Outputs: `modules/monitoring/outputs.tf`
- Implementation: `modules/monitoring/main.tf`
