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

## Cost Considerations

### Arc Server Costs
- **Arc-enabled Servers**: $6 per server per month
- **Extended Security Updates**: Additional cost for legacy OS
- **Azure Policy**: No additional cost for basic policies
- **Monitoring**: Additional cost if using Azure Monitor

### Private Link Costs
- **Private Endpoints**: $0.045/hour per endpoint (~$32/month)
- **Data Processing**: $0.045 per GB processed

### Management Tools
- **Update Management**: Included with Arc
- **Guest Configuration**: Included with Arc
- **Azure Security Center**: Additional cost for advanced features

### Cost Optimization
```hcl
# Disable private link for cost savings
deploy_arc_private_link = false  # Save ~$32/month per endpoint

# Use selective server onboarding
selective_arc_onboarding = true  # Only critical servers

# Leverage included monitoring
use_arc_included_monitoring = true  # vs premium monitoring
```

Estimated monthly cost per server: **$6-15** depending on monitoring and security features
