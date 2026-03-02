# Routing Module

Creates route tables and subnet associations that steer traffic through hub/non-gen firewalls based on enabled scenarios.

## Resources created (feature-flag dependent)

- Gateway subnet route table and association
- Hub firewall force-tunneling route table and association
- Squid subnet route table and association
- Gen workload route table and association
- Non-gen App Service integration route table and association
- Non-gen Container Apps subnet route table and association

## Source of truth

- Inputs: `modules/routing/variables.tf`
- Outputs: `modules/routing/outputs.tf`
- Implementation: `modules/routing/main.tf`
