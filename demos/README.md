# Demonstration Configurations

This folder contains ready-to-deploy demonstration configurations for various Azure Landing Zone scenarios. Each demo includes a complete `.tfvars` configuration file and deployment guide.

# Demonstration Configurations

This folder contains ready-to-deploy demonstration configurations for various Azure Landing Zone scenarios. Each demo includes a complete `.tfvars` configuration file and deployment guide.

## 📁 Available Demonstrations

### 🤖 Agentic AI Applications (`agentic/`)
**AI-powered applications with Azure OpenAI and multi-agent workflows**
- **Configuration**: `agentic/eol-agentic-demo.tfvars`
- **Scenario**: End-of-life software analysis with AI agents
- **Components**: Azure OpenAI, App Service, Cosmos DB, Application Insights
- **Features**: Multi-agent workflows, private endpoints, monitoring
- **Cost**: ~$200/month
- **Deploy Time**: 25-35 minutes

**Quick Deploy:**
```bash
terraform apply -var-file="credentials.tfvars" -var-file="demos/agentic/eol-agentic-demo.tfvars"
```

### 🔵 Azure Arc Hybrid Management (`arc/`)
**Azure Arc hybrid server management demonstration**
- **Configuration**: `arc/arc-demo.tfvars`
- **Scenario**: On-premises Windows Server 2025 with Azure Arc onboarding
- **Components**: Azure Arc agents, private link scope, monitoring
- **Features**: Hybrid management, VM insights, dependency mapping
- **Cost**: ~$50/month
- **Deploy Time**: 15-20 minutes

**Quick Deploy:**
```bash
terraform apply -var-file="credentials.tfvars" -var-file="demos/arc/arc-demo.tfvars"
```

### �️ Azure Virtual Desktop (`avd/`)
**Azure Virtual Desktop infrastructure demonstration**
- **Configuration**: `avd/avd-demo.tfvars`
- **Scenario**: Multi-session Windows 11 desktop environment
- **Components**: Host pools, session hosts, FSLogix storage, workspace
- **Features**: Auto-scaling, private endpoints, monitoring
- **Cost**: ~$500/month
- **Deploy Time**: 30-40 minutes

**Quick Deploy:**
```bash
terraform apply -var-file="credentials.tfvars" -var-file="demos/avd/avd-demo.tfvars"
```

### 🌐 ExpressRoute Private Connectivity (`expressroute/`)
**High-speed private connectivity demonstration**
- **Configuration**: `expressroute/expressroute-demo.tfvars`
- **Scenario**: Dedicated connection between on-premises and Azure
- **Components**: ExpressRoute Gateway, circuit simulation, BGP routing
- **Features**: High-bandwidth, low-latency private connectivity
- **Cost**: ~$800-2000/month (requires ExpressRoute circuit)
- **Deploy Time**: 45-60 minutes
- **Note**: Requires ExpressRoute circuit provisioning

**Quick Deploy:**
```bash
terraform apply -var-file="credentials.tfvars" -var-file="demos/expressroute/expressroute-demo.tfvars"
```

### 🏢 Hub-Spoke Architecture (`hub-spoke/`)
**Centralized hub-spoke network architecture demonstration**
- **Configuration**: `hub-spoke/hub-non-gen-basic-demo.tfvars`
- **Scenario**: Hub VNet with spoke connectivity and centralized firewall
- **Components**: Hub VNet, Azure Firewall, spoke VNets with peering
- **Features**: Network segmentation, centralized security, traffic routing
- **Cost**: ~$1,000/month
- **Deploy Time**: 35-45 minutes

**Quick Deploy:**
```bash
terraform apply -var-file="credentials.tfvars" -var-file="demos/hub-spoke/hub-non-gen-basic-demo.tfvars"
```

### 🔗 VPN Connectivity (`vpn/`)
**Site-to-Site VPN connectivity demonstration**
- **Configuration**: `vpn/vpn-demo.tfvars`
- **Scenario**: Secure VPN tunnel between Azure and simulated on-premises
- **Components**: VPN Gateway, Local Network Gateway, Windows Server 2016 RRAS
- **Features**: IKEv2 protocol, PSK authentication, automated setup
- **Cost**: ~$150/month
- **Deploy Time**: 20-30 minutes

**Quick Deploy:**
```bash
terraform apply -var-file="credentials.tfvars" -var-file="demos/vpn/vpn-demo.tfvars"
```
- **Scenario**: Hub VNet with spoke connectivity for non-generative workloads
- **Components**: Hub VNet, Azure Firewall, spoke VNet with peering
- **Features**: Network segmentation, centralized security, traffic routing
- **Cost**: ~$1,000/month

**Quick Deploy:**
```bash
terraform apply -var-file="credentials.tfvars" -var-file="demos/hub-spoke/hub-non-gen-basic-demo.tfvars"
```

## 🎯 Demo Categories

### AI & Machine Learning
- **Agentic Demo**: Multi-agent AI workflows with Azure OpenAI
- **EOL Analysis**: Software end-of-life detection and reporting

### Virtual Desktop Infrastructure
- **AVD Demo**: Windows 11 multi-session desktop environment
- **FSLogix**: User profile and application containerization

### Network Connectivity
- **VPN Demo**: Site-to-Site VPN with Windows Server RRAS
- **ExpressRoute Demo**: High-speed private connectivity simulation
- **Hub-Spoke Demo**: Centralized network architecture

### Hybrid Cloud Management
- **Azure Arc Demo**: On-premises server management from Azure
- **Hybrid Monitoring**: Azure Monitor integration
- **Private Link**: Secure service connectivity

### Security & Compliance
- **Network Segmentation**: Traffic isolation with Azure Firewall
- **Private Endpoints**: Service isolation and security
- **Monitoring**: Comprehensive logging and alerting

## 📋 Demo Usage Instructions

### 1. Setup Credentials
```bash
# Copy the credentials template
cp credentials.tfvars.example credentials.tfvars

# Edit credentials.tfvars with your Azure values:
# - subscription_id: Your Azure subscription ID
# - tenant_id: Your Azure AD tenant ID  
# - client_id: Service principal application ID
# - client_secret: Service principal secret

# SECURITY: Never commit credentials.tfvars to version control!
```

### 2. Choose Your Demo
Each demo folder contains:
- `*.tfvars` - Terraform variables configuration
- `README.md` - Demo overview and detailed guide
- Any additional demo-specific files

### 3. Deploy Demo
```bash
# Review the demo configuration
cat demos/demo-folder/demo-name.tfvars

# Plan the deployment
terraform plan -var-file="credentials.tfvars" -var-file="demos/demo-folder/demo-name.tfvars"

# Deploy the demo
terraform apply -var-file="credentials.tfvars" -var-file="demos/demo-folder/demo-name.tfvars"
```

### 4. Follow Demo Guide
Each demo folder contains:
- ✅ `README.md` - Demo overview and quick start
- ✅ `*.tfvars` - Complete Terraform configuration
- ✅ Additional guides for complex scenarios
- ✅ Post-deployment verification steps
- ✅ Testing procedures and troubleshooting tips

### 5. Clean Up
```bash
# Always destroy demo resources when finished
terraform destroy -var-file="credentials.tfvars" -var-file="demos/demo-folder/demo-name.tfvars"
```

## 💰 Cost Considerations

### Demo Cost Ranges
- **Azure Arc Demo**: ~$150/month (minimal infrastructure)
- **Hub-Spoke Demo**: ~$1,000/month (Azure Firewall Premium)
- **VPN Demo**: ~$1,250/month (production-ready components)
- **ExpressRoute Demo**: ~$800-2,000/month (depends on circuit bandwidth)

### Cost Optimization Tips
- Use demos for learning and testing only
- Destroy resources immediately after testing
- Consider Basic SKUs for shorter demonstrations
- Monitor Azure Cost Management during demos

## 🔒 Security Guidelines

### Demo Environment Security
- ✅ Use strong passwords (included in configurations)
- ✅ Limit demo deployment time
- ✅ Don't use production credentials
- ✅ Review firewall rules before deployment

### Credential Management
- Never commit credentials to version control
- Use separate `credentials.tfvars` for sensitive data
- Consider Azure Key Vault for production scenarios

## 🛠️ Customization

### Adapting Demos
Each demo can be customized by:
1. **Copying the configuration**: `cp demos/vpn/vpn-demo.tfvars my-custom-demo.tfvars`
2. **Modifying variables**: Edit network ranges, SKUs, features
3. **Adding components**: Enable/disable additional services
4. **Changing regions**: Update `location` variable

### Creating New Demos
To contribute a new demo:
1. Create new folder under `demos/`
2. Add descriptive `README.md` and `.tfvars` files
3. Write comprehensive deployment documentation
4. Test thoroughly in multiple regions
5. Document cost implications and cleanup procedures

## 📞 Support and Resources

### Documentation Links
- **Main README**: `../README.md` - Complete project documentation
- **Variables Reference**: `../variables.tf` - All available configuration options
- **Terraform Docs**: `../terraform.tfvars.example` - Variable examples

### Community
- Report issues with demos via GitHub Issues
- Contribute new demo scenarios via Pull Requests
- Share your demo customizations and experiences

---

**⚠️ Important**: These are demonstration environments designed for learning and testing. For production deployments, implement additional security hardening, monitoring, backup procedures, and compliance requirements specific to your organization.
