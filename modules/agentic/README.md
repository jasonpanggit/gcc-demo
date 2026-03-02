# Agentic Module

Deploys App Service-based agentic app infrastructure and related AI/data resources.

## Resources created (feature-flag dependent)

- App Service plan + Linux Web App
- Application Insights
- Azure OpenAI account
- Cosmos DB account/database/container
- Private endpoints + private DNS zones for AOAI/Cosmos
- App managed-identity role assignments
- Bot registration / Teams channel resources
- Optional ACR, Bing Search cognitive account, AI Foundry account

## Typical usage

```hcl
module "agentic" {
  source = "./modules/agentic"
  # pass project/environment/network/workspace vars from root
}
```

## Source of truth

- Inputs: `modules/agentic/variables.tf`
- Outputs: `modules/agentic/outputs.tf`
- Implementation: `modules/agentic/main.tf`
# Check App Service configuration
az webapp config show --name <app-name> --resource-group <rg-name>

# Review VNet integration
az webapp vnet-integration list --name <app-name> --resource-group <rg-name>

# Test private endpoint connectivity
az network private-endpoint list --resource-group <rg-name>
```

## Version History

- **v1.0**: Initial release with basic AI chat functionality
- **v1.1**: Added VNet integration and private endpoint support
- **v1.2**: Enhanced role assignments and authentication
- **v1.3**: Production optimizations and monitoring improvements

## Contributing

When modifying this module:

1. **Test VNet Integration**: Always verify private endpoint connectivity
2. **Update Role Assignments**: Ensure new Azure services have proper permissions
3. **Document Changes**: Update this README with any configuration changes
4. **Validate Outputs**: Test all module outputs in dependent configurations

## Security Considerations

- **No Hardcoded Secrets**: All authentication uses managed identities or Key Vault references
- **Private Network Only**: All Azure service communication uses private endpoints
- **Least Privilege**: Role assignments follow minimal required permissions
- **Monitoring**: Comprehensive logging for security auditing

## Support

For issues related to this module:

1. Check Application Insights for application-level errors
2. Review Terraform plan output for configuration issues
3. Validate network connectivity and role assignments
4. Consult Azure service health for platform issues
