# Demonstration Configurations

This folder contains ready-to-deploy demonstration configurations for various Azure Landing Zone scenarios. Each demo includes a complete `.tfvars` configuration file and deployment guide.

## 📁 Available Demonstrations

### 🔗 VPN Connectivity (`vpn/`)
**Complete Site-to-Site VPN connectivity demonstration**


**Key Changes:**

**Quick Deploy:**
```bash
terraform apply -var-file="credentials.tfvars" -var-file="demos/vpn/vpn-demo.tfvars"
```

### New
- EOL Agentic: private agentic app with AOAI and Teams-ready hooks (`demos/eol-agentic/eol-agentic-demo.tfvars`)

### 🔵 Azure Arc Hybrid Management (`arc/`)
**Azure Arc hybrid management demonstration**
- **Cost**: ~$50/month

- VM Insights and dependency mapping

**Quick Deploy:**
```bash
terraform apply -var-file="credentials.tfvars" -var-file="demos/arc/arc-demo.tfvars"
```

### 🌐 ExpressRoute Private Connectivity (`expressroute/`)
**High-speed private connectivity demonstration**

- **Configuration**: `expressroute/expressroute-demo.tfvars`
- **Scenario**: Dedicated connection between on-premises and Azure
- **Components**: ExpressRoute Gateway, circuit simulation
- **Features**: High-bandwidth, low-latency private connectivity
- **Cost**: ~$800-2000/month (requires ExpressRoute circuit)
- **Note**: Requires ExpressRoute circuit provisioning

**Quick Deploy:**
```bash
terraform apply -var-file="credentials.tfvars" -var-file="demos/expressroute/expressroute-demo.tfvars"
```

### 🏢 Hub-Spoke Architecture (`hub-spoke/`)
**Basic hub-spoke network architecture demonstration**

- **Configuration**: `hub-spoke/hub-non-gen-basic-demo.tfvars`
- **Scenario**: Hub VNet with spoke connectivity for non-generative workloads
- **Components**: Hub VNet, Azure Firewall, spoke VNet with peering
- **Features**: Network segmentation, centralized security, traffic routing
- **Cost**: ~$1,000/month

**Quick Deploy:**
```bash
terraform apply -var-file="credentials.tfvars" -var-file="demos/hub-spoke/hub-non-gen-basic-demo.tfvars"
```

## 🎯 Demo Categories

### Network Connectivity
- **VPN Demo**: Site-to-Site VPN with Windows Server 2025
- *Future*: ExpressRoute simulation
- *Future*: Multi-hub networking

### Security & Governance
- *Future*: Zero Trust network architecture
- *Future*: Azure Policy enforcement demo
- *Future*: Private Link comprehensive setup

### Hybrid Cloud
- **VPN Demo**: Includes Azure Arc onboarding
- *Future*: Hybrid identity with AD Connect
- *Future*: Hybrid monitoring with Azure Monitor

### Cost Optimization
- *Future*: Minimal cost deployment scenarios
- *Future*: Auto-scaling demonstrations
- *Future*: Resource lifecycle management

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
