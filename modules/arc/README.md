# Arc Module

Provides Arc onboarding identity and private-link plumbing.

## Resources created (flag dependent)

- Azure AD application, service principal, and password
- Role assignments for Arc onboarding scope
- Arc Private Link Scope
- Arc private DNS zones and VNet links
- Arc private endpoint

## Source of truth

- Inputs: `modules/arc/variables.tf`
- Outputs: `modules/arc/outputs.tf`
- Implementation: `modules/arc/main.tf`
