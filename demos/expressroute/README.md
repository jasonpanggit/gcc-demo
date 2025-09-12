# ExpressRoute Private Connectivity Demonstration

This demonstration showcases ExpressRoute capabilities for high-speed, private connectivity between on-premises infrastructure and Azure, bypassing the public internet for enhanced security and performance.

## 📋 Demo Overview

### Architecture Components
- **Azure Hub VNet** (10.0.0.0/16) with ExpressRoute Gateway
- **ExpressRoute Circuit** (requires service provider provisioning)
- **ExpressRoute Gateway** (UltraPerformance SKU) with BGP routing
- **Azure Route Server** for advanced routing scenarios
- **Modular Terraform Architecture** with dedicated gateways module
- **Hub-spoke topology** with optimized routing

### Key Features Demonstrated
- ✅ **ExpressRoute Gateway** deployment and configuration with modular approach
- ✅ **BGP Routing** with custom ASN configuration and Route Server integration
- ✅ **Private Connectivity** without internet traversal for enhanced security
- ✅ **High Bandwidth** options (100 Mbps to 100 Gbps) based on circuit requirements
- ✅ **Route Server** integration for complex multi-path routing scenarios
- ✅ **Multiple Peering** support (Private, Microsoft) through gateway module
- ✅ **Cost Optimization** through conditional deployment of components

### Modular Infrastructure Benefits
- **Gateways Module**: Dedicated ExpressRoute Gateway management
- **Networking Module**: Hub VNet and subnet configuration
- **Route Server Integration**: Advanced BGP routing capabilities
- **Conditional Deployment**: Deploy only required components for cost control

## 🚀 Quick Deployment

### Prerequisites
- Azure subscription with ExpressRoute permissions
- **ExpressRoute Circuit** provisioned by service provider
- Terraform installed and configured
- ~$500-2000/month budget depending on bandwidth

### Deploy Infrastructure
```bash
# From the root of the project
terraform init
terraform plan -var-file="demos/expressroute/expressroute-demo.tfvars"
terraform apply -var-file="demos/expressroute/expressroute-demo.tfvars"
```

## ⚠️ Important Prerequisites

### ExpressRoute Circuit Requirements
**This demo requires an actual ExpressRoute circuit from a service provider.**

Common providers include:
- **Equinix** - Global data centers
- **Megaport** - Software-defined networking
- **InterCloud** - Microsoft partnership
- **AT&T** - Enterprise connectivity
- **Verizon** - Business fiber services

### Circuit Configuration
```hcl
# Update these values in expressroute-demo.tfvars
express_route_circuit_bandwidth = "100"  # Mbps
express_route_circuit_peering_location = "Singapore"
express_route_circuit_service_provider = "Equinix"
```

## 📊 Expected Results

After successful deployment (~30-45 minutes), you should have:

### ✅ ExpressRoute Infrastructure
- ExpressRoute Gateway deployed in Gateway subnet
- Circuit connection configured (pending provider setup)
- BGP routing configured with custom ASN
- Azure Route Server (if enabled) for advanced routing

### ✅ Network Topology
- Hub VNet ready for ExpressRoute connectivity
- Optimized routing for on-premises traffic
- Network segmentation with Azure Firewall
- Spoke VNets configured for ExpressRoute transit

## 📁 Files in This Demo

| File | Purpose |
|------|---------|
| `expressroute-demo.tfvars` | Terraform configuration for ExpressRoute |
| `README.md` | This overview file |

## 🔧 Demo Configuration

### Core ExpressRoute Settings
```hcl
# ExpressRoute Gateway
deploy_expressroute_gateway = true
expressroute_gateway_sku = "ErGw1AZ"  # Zone-redundant
enable_expressroute_gateway_bgp = true

# Circuit configuration (update with your values)
express_route_circuit_bandwidth = "100"
express_route_circuit_peering_location = "Singapore"
express_route_circuit_service_provider = "Equinix"

# BGP routing
expressroute_gateway_bgp_asn = 65515
```

### Advanced Routing (Optional)
```hcl
# Enable Route Server for complex scenarios
deploy_route_server = true

# Multiple gateway scenario
deploy_vpn_gateway = true  # Hybrid VPN + ExpressRoute
enable_vpn_gateway_bgp = true
vpn_gateway_bgp_asn = 65516
```

## 🔍 Circuit Provisioning Process

### 1. Request Circuit from Provider
Contact your chosen ExpressRoute provider to:
- Request circuit at desired location
- Specify bandwidth requirements
- Obtain **Service Key** for Azure configuration

### 2. Configure Azure Side
```bash
# Create ExpressRoute circuit
az network express-route create \
  --name "er-circuit-demo" \
  --resource-group "rg-hub-gcc-demo" \
  --bandwidth 100 \
  --location "Australia East" \
  --peering-location "Singapore" \
  --provider "Equinix"
```

### 3. Provider Configuration
- Provide **Service Key** to ExpressRoute provider
- Provider configures their side of connection
- Circuit state changes to "Provisioned"

### 4. Create Virtual Network Gateway Connection
```bash
# Link gateway to circuit
az network vpn-connection create \
  --name "er-connection" \
  --resource-group "rg-hub-gcc-demo" \
  --vnet-gateway1 "vgw-er-hub-gcc-demo" \
  --express-route-circuit2 "er-circuit-demo"
```

## 🔧 BGP Configuration

### ExpressRoute BGP Settings
```powershell
# On-premises router BGP configuration example
router bgp 65001
 neighbor 169.254.21.1 remote-as 65515
 neighbor 169.254.21.1 description "Azure ExpressRoute Primary"
 neighbor 169.254.21.5 remote-as 65515  
 neighbor 169.254.21.5 description "Azure ExpressRoute Secondary"
 
 address-family ipv4
  network 192.168.0.0 mask 255.255.0.0
  neighbor 169.254.21.1 activate
  neighbor 169.254.21.5 activate
 exit-address-family
```

### Azure Route Verification
```bash
# Check learned routes
az network express-route list-route-tables \
  --name "er-circuit-demo" \
  --resource-group "rg-hub-gcc-demo" \
  --peering-name "AzurePrivatePeering" \
  --path "primary"
```

## 💰 Cost Considerations

### Monthly Cost Breakdown
- **ExpressRoute Gateway (ErGw1AZ)**: ~$300/month
- **ExpressRoute Circuit (100 Mbps)**: ~$500/month
- **Data Transfer**: $0.025/GB outbound
- **Azure Route Server**: ~$350/month (if enabled)
- **Total**: ~$800-1200/month

### Bandwidth Options and Costs
| Bandwidth | Monthly Cost | Use Case |
|-----------|--------------|----------|
| 50 Mbps | ~$300 | Small office |
| 100 Mbps | ~$500 | Branch office |
| 1 Gbps | ~$2000 | Data center |
| 10 Gbps | ~$8000 | Enterprise |

## 🔍 Testing and Verification

### Circuit Status Check
```bash
# Check circuit provisioning state
az network express-route show \
  --name "er-circuit-demo" \
  --resource-group "rg-hub-gcc-demo" \
  --query "circuitProvisioningState"
```

### BGP Session Verification
```bash
# Check BGP neighbors
az network express-route peering show \
  --circuit-name "er-circuit-demo" \
  --name "AzurePrivatePeering" \
  --resource-group "rg-hub-gcc-demo"
```

### Connectivity Testing
```powershell
# From on-premises
tracert 172.16.1.4  # Should show ExpressRoute path
ping 172.16.1.4     # Test connectivity to Azure

# Bandwidth testing
iperf3 -c 172.16.1.4 -t 60  # Sustained throughput test
```

## 🆘 Troubleshooting

### Common Issues

#### Circuit Not Provisioning
- Verify service provider has completed their configuration
- Check Service Key is correct
- Confirm peering location matches provider capability

#### BGP Session Down
```bash
# Check BGP configuration
az network express-route peering show \
  --circuit-name "er-circuit-demo" \
  --name "AzurePrivatePeering" \
  --resource-group "rg-hub-gcc-demo"

# Verify IP addresses and ASN numbers
```

#### Poor Performance
- Check circuit utilization in Azure Portal
- Verify QoS settings with provider
- Test during off-peak hours
- Consider bandwidth upgrade

## 🧹 Cleanup

```bash
# Destroy Azure infrastructure
terraform destroy -var-file="demos/expressroute/expressroute-demo.tfvars"

# Contact provider to deprovision circuit
# Note: Circuits may have minimum terms and early termination fees
```

## 💡 Learning Outcomes

After completing this demo, you will understand:
- ExpressRoute architecture and components
- Circuit provisioning process with service providers
- BGP configuration for ExpressRoute
- Gateway SKU selection and performance characteristics
- Cost optimization strategies for ExpressRoute
- Monitoring and troubleshooting ExpressRoute connections

## 📚 Additional Resources

- [ExpressRoute documentation](https://docs.microsoft.com/azure/expressroute/)
- [ExpressRoute partners and locations](https://docs.microsoft.com/azure/expressroute/expressroute-locations)
- [ExpressRoute pricing](https://azure.microsoft.com/pricing/details/expressroute/)
- [BGP routing optimization](https://docs.microsoft.com/azure/expressroute/expressroute-optimize-routing)

---

**⚠️ Important**: ExpressRoute circuits involve contractual commitments with service providers. Review terms, costs, and cancellation policies before provisioning production circuits.
