# Hub-Spoke Network Architecture Demo

Basic hub-spoke network topology with centralized security and workload isolation.

## 🎯 Architecture Overview

### Core Components
- **Hub VNet** (10.0.0.0/16) - Azure Firewall, Bastion, core services
- **Spoke VNet** (192.168.0.0/16) - Workload deployment
- **VNet Peering** - Hub-spoke connectivity with UDR routing
- **Azure Firewall Premium** - Centralized security and internet access

### Key Features
- ✅ Hub-spoke topology with centralized security
- ✅ Azure Firewall Premium with threat intelligence
- ✅ Network segmentation and workload isolation
- ✅ Secure management via Azure Bastion
- ✅ Modular Terraform architecture (7 modules)

## 🚀 Quick Deployment

```bash
# Deploy hub-spoke infrastructure
terraform init
terraform plan -var-file="credentials.tfvars" -var-file="demos/hub-spoke/hub-non-gen-basic-demo.tfvars"
terraform apply -var-file="credentials.tfvars" -var-file="demos/hub-spoke/hub-non-gen-basic-demo.tfvars"
```

**Prerequisites:** Azure subscription, Terraform, ~$800/month budget

## 📊 Network Traffic Flow

**Internet Access:** Spoke VM → UDR → Hub Firewall → Internet  
**Management:** Administrator → Azure Bastion → Spoke VM (no public IPs)  
**Inter-Spoke:** Future capability when multiple spokes deployed

## 🔧 Configuration Highlights

```hcl
# Core Settings
deploy_hub_vnet = true
deploy_hub_firewall = true
deploy_bastion = true
deploy_nongen_vnet = true
deploy_hub_nongen_peering = true

# Network Addressing
hub_vnet_address_space = ["10.0.0.0/16"]
nongen_vnet_address_space = ["192.168.0.0/16"]
```

## 🔍 Verification Commands

```bash
# Check VNet peering status
az network vnet peering list --resource-group "rg-gcc-demo" --vnet-name "vnet-hub-gcc-demo"

# Verify firewall rules
az network firewall policy rule-collection-group list --policy-name "afwp-hub-gcc-demo" --resource-group "rg-gcc-demo"

# Test connectivity from spoke VM
nslookup microsoft.com  # Should use firewall DNS proxy
```

## � Cost & Cleanup

**Monthly Costs:**
- Azure Firewall Premium: ~$800
- Azure Bastion: ~$150  
- VNet Peering: ~$10-50
- **Total: ~$1,000/month**

**Cleanup:**
```bash
terraform destroy -var-file="credentials.tfvars" -var-file="demos/hub-spoke/hub-non-gen-basic-demo.tfvars"
```

## � Resources

- [Hub-spoke architecture](https://docs.microsoft.com/azure/architecture/reference-architectures/hybrid-networking/hub-spoke)
- [Azure Firewall documentation](https://docs.microsoft.com/azure/firewall/)
- [VNet peering overview](https://docs.microsoft.com/azure/virtual-network/virtual-network-peering-overview)

---
**⚠️ Demo Environment:** For production, implement additional security controls and compliance requirements.
