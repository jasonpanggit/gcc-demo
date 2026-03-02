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
- **Virtual Network**: For private endpoint connectivity

## Cost Considerations

### Log Analytics Workspace
- **Free Tier**: 500MB/day included, then $2.30/GB
- **PerGB2018**: $2.30/GB ingested
- **Retention**: $0.10/GB per month for retention beyond 31 days

### Application Insights
- **Data Ingestion**: $2.30/GB beyond 5GB/month free tier
- **Data Retention**: $0.25/GB per month beyond 90 days

### Private Link Scope
- **Private Endpoints**: $0.045/hour per endpoint (~$32/month)
- **Data Processing**: $0.045 per GB processed

### Cost Optimization
```hcl
# Use shorter retention for cost savings
log_analytics_workspace_retention_days = 30  # vs 365 days

# Use Free tier for small environments (500MB/day limit)
log_analytics_workspace_sku = "Free"

# Disable Application Insights if not needed
deploy_application_insights = false
```

### Sample Monthly Costs
- **Basic Monitoring**: ~$50-100 (1GB/day ingestion)
- **Medium Environment**: ~$200-400 (5GB/day ingestion)
- **Enterprise**: ~$500+ (10GB+/day ingestion)

Estimated monthly cost: **$50-500+** depending on data volume and retention
