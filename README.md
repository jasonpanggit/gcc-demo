# GCC Demos, Modules & Automation

Opinionated Terraform landing zone for hybrid network + governance scenarios. Pick a demo, deploy with one command, tear it down when done. Modular building blocks let you evolve from a tiny hub to full hybrid (VPN / ExpressRoute / Arc) with optional routing & security layers.

## 🔑 What You Get (At a Glance)
| Capability | Provided By |
|------------|-------------|
| Hub / Spoke VNets, Subnets, Peering | networking module |
| Hybrid Connectivity (VPN / ER) | gateways module + Windows 2016 VPN script |
| Azure Firewall + Optional Explicit Proxy + NAT | firewall module |
| Azure Route Server + NVA (FRR) | networking + compute (linux) |
| Windows Servers (2016 VPN / 2025 Arc) | compute module + scripts |
| Azure Arc (Private Link Scope) | arc + identity modules + Arc script |
| Azure Monitor Private Link Scope | monitoring module |
| AI-Powered Agentic Applications | agentic module + EOL app |
| Azure Virtual Desktop (AVD) | avd module |
| Script & Extension Storage | storage module |

## 🧪 Demo Scenarios (demos/)
Each demo tfvars file toggles only the components needed for that scenario (cost + deployment time targets included in the interactive menu).

| Key | File | Focus | Approx Cost* | Deploy Time* |
|-----|------|-------|--------------|--------------|
| agentic-eol | `demos/agentic/eol-agentic-demo.tfvars` | AI-powered EOL analysis app with Azure OpenAI | ~$200/mo | 25-35m |
| arc | `demos/arc/arc-demo.tfvars` | Azure Arc onboarding (Win 2025) | ~$150/mo | 30-40m |
| vpn | `demos/vpn/vpn-demo.tfvars` | Site‑to‑Site VPN (Win 2016 RRAS) | ~$1,250/mo | 45-60m |
| expressroute | `demos/expressroute/expressroute-demo.tfvars` | ExpressRoute + Route Server | ~$800–2,000/mo | 30-45m (+ provider) |
| avd | `demos/avd/avd-demo.tfvars` | Azure Virtual Desktop environment | ~$500/mo | 20-30m |
| hub-onprem | `demos/hub-spoke/hub-onprem-basic-demo.tfvars` | Minimal hub + on‑prem simulation | ~$0 | <5m |
| hub-non-gen | `demos/hub-spoke/hub-non-gen-basic-demo.tfvars` | Basic hub + spoke | ~$0 | <5m |
| hub-non-gen-gen | `demos/hub-spoke/hub-non-gen-gen-basic-demo.tfvars` | Dual spokes (Gen / Non‑Gen) | ~$0 | <5m |

*Approximate: Depends on region/SKUs. Destroy when finished to avoid charges.

## 🚀 Deploy a Demo (Interactive Runner)
Recommended path: use the curated menu that shows cost + ETA before apply.

```bash
./run-demo.sh
```

Flow:
1. Script validates prerequisites (Terraform, Azure CLI, login, credentials.tfvars)
2. Choose a demo number
3. Select action: Plan | Apply | Destroy | State | Outputs
4. Apply auto-approves (cost warning shown first); destroy asks for confirmation

Non-interactive (manual) alternative:
```bash
cp credentials.tfvars.example credentials.tfvars
terraform init
terraform apply -var-file="credentials.tfvars" -var-file="demos/vpn/vpn-demo.tfvars" --auto-approve
```

## 🔄 Post-Deployment Setup

After deploying the arc-demo scenario, you can automatically configure the **Software End-of-Life (EOL) Analysis Solution** using actual Terraform output values:

```bash
# Run after successful arc-demo deployment
./workbooks/end-of-life/post-deploy-setup.sh
```

This script will:
- ✅ Extract actual Azure subscription ID, resource group names, and workspace names from Terraform outputs
- 🔧 Update all EOL solution configuration files with your environment values
- 📋 Generate a deployment summary with next steps
- 🚀 Prepare the EOL solution for immediate deployment

The EOL solution provides comprehensive software inventory analysis for Azure Arc-connected machines, checking end-of-life status using the endoflife.date API. See [`workbooks/end-of-life/README.md`](workbooks/end-of-life/README.md) for full details.

## 🧩 Terraform Modules (7)
| Module | Purpose | Highlights |
|--------|---------|-----------|
| networking | VNets, subnets, peering, route tables, Route Server | Hub / spokes, conditional subnets |
| compute | Windows & Linux VMs | Win 2016 (VPN), Win 2025 (Arc), NVA, Squid |
| gateways | VPN, ExpressRoute, Local Network Gateway | BGP ready, S2S + ER coexistence |
| firewall | Azure Firewall (optionally explicit proxy) | App/Net rules, Arc egress rules, NAT for external proxy access |
| storage | Script storage account + container (if enabled) | Script hosting for CSE |
| identity | Service Principal & role assignments | Least privilege for Arc onboarding |
| arc | Arc Private Link Scope & endpoints | Private control plane, Arc integration |

All modules are conditionally invoked via booleans in tfvars (e.g. `deploy_vpn_gateway`, `deploy_hub_firewall`).

## 🧰 Scripts (scripts/)
Automation pieces consumed by Custom Script Extensions or manual lab usage:

| Path | Purpose | Trigger |
|------|---------|--------|
| `scripts/vpn/` | Windows 2016 RRAS S2S VPN setup (IKEv2, logging) | `onprem_windows_vpn_setup = true` |
| `scripts/arc/` | Windows 2025 Azure Arc agent install & connect | `onprem_windows_arc_setup = true` + `deploy_onprem_windows_server_2025 = true` |
| `scripts/nva/` | Linux NVA routing bootstrap (IPv4 forward) | Future / manual wiring |
| `scripts/squid/` | Squid proxy quick config for egress tests | Future / manual wiring |

See each subfolder README for parameters & troubleshooting.

## ⚙️ Core Deployment Flags (Examples)
```hcl
# Hybrid connectivity
deploy_vpn_gateway              = true
deploy_expressroute_gateway     = false

# Security / routing
deploy_hub_firewall             = true
deploy_route_server             = true
deploy_linux_nva                = true

# Servers & automation
deploy_onprem_windows_server_2016 = true
onprem_windows_vpn_setup          = true
deploy_onprem_windows_server_2025 = true
onprem_windows_arc_setup          = true

# Storage for scripts
deploy_script_storage           = true
```

## 🔐 Credentials & Setup
1. Copy `credentials.tfvars.example` → `credentials.tfvars`
2. Populate subscription, tenant, SPN (for Arc) values
3. (Optional) Adjust demo tfvars or create a variant
4. Run `./run-demo.sh` and apply

## 🧹 Teardown
Always destroy when done:
```bash
./run-demo.sh   # choose demo -> Destroy
# or manually
terraform destroy -var-file="credentials.tfvars" -var-file="demos/vpn/vpn-demo.tfvars"
```

---
The rest of this document retains deeper architectural and configuration detail for advanced customization.

## 🔧 Modular Architecture

### Core Modules
1. **Agentic** - AI-powered applications with Azure OpenAI and multi-agent workflows
2. **Networking** - VNets, subnets, peering, Route Server
3. **Compute** - Windows Server 2016/2025 VMs with automation
4. **Gateways** - VPN Gateway, ExpressRoute Gateway, Local Network Gateway
5. **Firewall** - Azure Firewall with configurable DNS proxy and policies
6. **Storage** - Storage accounts for scripts and automation
7. **Arc** - Azure Arc private link scope and hybrid connectivity
8. **AVD** - Azure Virtual Desktop infrastructure and session hosts
9. **Monitoring** - Log Analytics, Application Insights, and private link scopes
10. **Routing** - Custom route tables and BGP configurations

### Windows Server Options
- **Windows Server 2016**: Optimized for Site-to-Site VPN scenarios
- **Windows Server 2025**: Enhanced for Azure Arc hybrid management
- **Automated Configuration**: PowerShell scripts for VPN, Arc agent, and networking

## 🧰 Script Automation

The `scripts/` directory contains automation used by Custom Script Extensions or for manual lab bootstrapping. Each script set has its own README with parameters, usage, and troubleshooting.

| Area | Path | Purpose |
|------|------|---------|
| Azure Arc | [`scripts/arc/`](scripts/arc/README.md) | Onboards Windows Server 2025 into Azure Arc (agent install, connect, Private Link support) |
| VPN (On-Prem) | [`scripts/vpn/`](scripts/vpn/README.md) | Configures Windows Server (lab) as Site-to-Site IKEv2 RRAS endpoint with logging |
| Network Virtual Appliance | [`scripts/nva/`](scripts/nva/README.md) | Minimal Linux routing / forwarding bootstrap (enable IPv4 forwarding, baseline rules) |
| Squid Proxy | [`scripts/squid/`](scripts/squid/README.md) | Sets up a lab HTTP/HTTPS forward proxy for controlled egress scenarios |

### Terraform Integration Flags (Examples)
```hcl
# Enable on-prem Windows VPN automation
onprem_windows_vpn_setup = true

# Enable Arc onboarding for Windows Server 2025
onprem_windows_arc_setup = true
deploy_onprem_windows_server_2025 = true

# (If you wire NVA or Squid scripts via extensions)
deploy_linux_nva     = true
deploy_squid_proxy   = true
```

### When to Use Which Script
- Use **VPN** script when demonstrating hybrid connectivity (S2S tunnel + BGP)
- Use **Arc** script for hybrid server governance, inventory, and policy demos
- Use **NVA** script to experiment with custom routing / BGP adjacencies
- Use **Squid** script to test egress restriction or Private Link scenarios

> For production adaptations, harden each script (auth, logging, least privilege) beyond the lab defaults documented in their respective READMEs.

## Variable Configuration

### Configuration Files
- **`terraform.tfvars`**: Complete configuration file with all 65+ variables organized by functional sections
- **`terraform.tfvars.example`**: Template file showing all available variables with defaults
- **Demo Files**: Specialized configurations for specific scenarios
  - `vnet-demo.tfvars`: VNet peering demonstration
  - `arc-demo.tfvars`: Azure Arc onboarding demo

### Variable Organization
Variables are organized into logical sections for better management:

1. **General Configuration**: Basic Azure settings (location, environment, project)
2. **Hub VNet**: Core hub virtual network configuration
3. **Subnets**: Address space allocation for all hub subnets
4. **Hub Services**: Azure Firewall, Bastion, Route Server, NVA
5. **Azure Firewall**: Advanced firewall features and proxy settings
6. **Azure Arc**: Arc service principal and private link configuration
7. **Azure Monitor**: Log Analytics and private link scope settings
8. **On-Premises**: Simulated on-premises environment
9. **Additional VNets**: Gen and Non-Gen virtual networks
10. **VNet Peering**: Cross-VNet connectivity configuration
11. **Storage**: Script storage for VM extensions
12. **ExpressRoute**: Circuit and gateway configuration
13. **Advanced BGP**: Custom routing scenarios

### Quick Start
1. Copy the example file: `cp terraform.tfvars.example terraform.tfvars`
2. Edit `terraform.tfvars` to match your requirements
3. Deploy: `terraform init && terraform apply`

### Cost Optimization
Use deployment flags to control costs:
```hcl
# Minimal hub deployment
deploy_hub_vnet = true
deploy_hub_firewall = false      # Save ~$1,200/month
deploy_bastion = false           # Save ~$140/month
deploy_expressroute_gateway = false  # Save ~$200/month
deploy_script_storage = false    # Save ~$20/month
```

## Architecture Components

### 1. Hub VNet Infrastructure (Optional)
- **Address Space**: 172.16.0.0/16
- **ExpressRoute Gateway** for private connectivity
- **Azure Firewall** with optional force tunneling
- **Route Server** for BGP routing with NVA
- **Linux NVA** for advanced routing scenarios
- **Azure Bastion** for secure management access

### 2. Gen VNet Infrastructure (Optional)
- **Address Space**: 10.0.0.0/16
- **Gen Workload Subnet** for generative AI workloads
- **Conditional Routing**: Option to route traffic through Non-Gen firewall
- **VNet Peering**: Optional connectivity to Non-Gen VNet

### 3. Non-Gen VNet Infrastructure (Optional)
- **Address Space**: 100.0.0.0/16
- **Azure Firewall** for non-generative workload security
- **Simplified Architecture**: Dedicated firewall for non-gen workloads
- **VNet Peering**: Connectivity to Hub and optionally Gen VNets

### 4. Network Virtual Appliance (NVA)
- **Ubuntu 20.04 LTS** with FRRouting for BGP
- **BGP Configuration**: ASN 65001 with route advertisement
- **Custom Routes**: Configurable route advertisement
- **High Availability**: Configurable for redundancy

### 5. Windows Server 2025 with Azure Arc (Optional)
- **Windows Server 2025** Datacenter Azure Edition
- **Enhanced Arc Onboarding**: Automated preparation and configuration
- **IMDS Blocking**: Prevents Azure VM metadata service access
- **Proxy Support**: Integration with Azure Firewall explicit proxy
- **Comprehensive Monitoring**: Azure Monitor and Log Analytics integration
- **Policy Compliance**: Azure Policy and Guest Configuration support

> 📖 **Detailed Guide**: See [WINDOWS-ARC-GUIDE.md](./WINDOWS-ARC-GUIDE.md) for comprehensive Windows Server 2025 Azure Arc onboarding documentation.

## Network Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                    Hub VNet (172.16.0.0/16)                    │
│                        [Optional]                              │
├─────────────────────────────────────────────────────────────────┤
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐  │
│  │   Gateway       │  │  Azure Firewall │  │  Route Server   │  │
│  │   Subnet        │  │     Subnet      │  │    Subnet       │  │
│  │ 172.16.1.0/24   │  │ 172.16.2.0/24   │  │ 172.16.4.0/24   │  │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘  │
│                                                                 │
│  ┌─────────────────┐  ┌─────────────────┐                      │
│  │   NVA Subnet    │  │Azure Bastion    │                      │
│  │                 │  │   Subnet        │                      │
│  │ 172.16.5.0/24   │  │ 172.16.6.0/24   │                      │
│  └─────────────────┘  └─────────────────┘                      │
└─────────────────────────────────────────────────────────────────┘
           │                       │
    ┌──────▼──────┐        ┌──────▼──────┐
    │ ExpressRoute│        │Azure Route  │
    │  Gateway    │        │   Server    │◄──────┐
    │             │        │(BGP: 65515) │       │
    └─────────────┘        └─────┬───────┘       │
           │                     │               │
           │              ┌──────▼──────┐        │
           │              │   BGP       │        │
           │              │  Peering    │        │
           │              └──────┬──────┘        │
           │                     │               │
    ┌──────▼──────┐        ┌─────▼─────┐         │
    │Local Network│        │Linux NVA  │         │
    │  Gateway    │        │(BGP:65001)│         │
    │(On-Premises)│        └───────────┘         │
    └──────┬──────┘                              │
           │                                     │
    ┌──────▼──────┐                      ┌──────▼──────┐
    │On-Premises  │                      │   BGP       │
    │   Network   │◄─────ExpressRoute────┤ Connection  │
    │192.168.0.0/16│                      └─────────────┘
    └─────────────┘

┌─────────────────────────────────────┐    ┌─────────────────────────────────────┐
│        Gen VNet (10.0.0.0/16)      │    │     Non-Gen VNet (100.0.0.0/16)    │
│           [Optional]                │    │           [Optional]                │
├─────────────────────────────────────┤    ├─────────────────────────────────────┤
│  ┌─────────────────────────────────┐ │    │  ┌─────────────────────────────────┐ │
│  │     Gen Workload Subnet         │ │    │  │     Azure Firewall Subnet      │ │
│  │       10.0.1.0/24               │ │    │  │        100.0.1.0/24            │ │
│  │                                 │ │    │  │                                 │ │
│  │  [Routes to Non-Gen Firewall]   │ │    │  │    [Non-Gen Azure Firewall]    │ │
│  └─────────────────────────────────┘ │    │  └─────────────────────────────────┘ │
└─────────────────────────────────────┘    └─────────────────────────────────────┘
           │                                             │
           └─────────────────────────────────────────────┘
                      [Optional VNet Peering]
```

## Key Features

### Modular Deployment Options
All major infrastructure components are conditionally deployed based on variables:

```hcl
# Hub VNet and its components
deploy_hub_vnet             = false  # Hub VNet with all subnets
deploy_expressroute_gateway = false  # ExpressRoute Gateway
deploy_hub_firewall         = false  # Hub Azure Firewall
deploy_route_server         = false  # Azure Route Server
deploy_linux_nva            = false  # Linux NVA with BGP
deploy_bastion              = false  # Azure Bastion
deploy_squid_proxy          = false  # Linux Squid proxy VM in hub

# Hub Firewall Advanced Features
hub_firewall_explicit_proxy            = false  # Explicit proxy functionality
hub_firewall_explicit_proxy_nat        = false  # NAT rules for external proxy access
hub_firewall_explicit_proxy_http_port  = 8080   # HTTP proxy port
hub_firewall_explicit_proxy_https_port = 8443   # HTTPS proxy port
hub_firewall_arc_rules                 = false  # Azure Arc connectivity rules
deploy_arc_private_endpoint      = false  # Azure Arc private endpoints

# Azure Monitor Private Link Scope
deploy_azure_monitor_private_link_scope                 = false  # Azure Monitor Private Link Scope
log_analytics_workspace_retention_days     = 30     # Log Analytics retention (30-730 days)
log_analytics_workspace_sku                = "PerGB2018"  # Log Analytics pricing tier

# Gen VNet and routing
deploy_gen_vnet                    = false  # Gen VNet with workload subnet
route_internet_to_nongen_firewall  = false  # Route Gen internet traffic through Non-Gen firewall

# Non-Gen VNet
deploy_nongen_vnet = false  # Non-Gen VNet with firewall

# VNet Peering
deploy_gen_nongen_peering = false  # Peering between Gen and Non-Gen VNets
```

### Standardized Variable Naming
All hub-related variables use the `hub_` prefix for better organization:

```hcl
# Hub VNet Configuration
hub_vnet_address_space       = ["172.16.0.0/16"]
hub_gateway_subnet_prefix    = "172.16.1.0/24"
hub_firewall_subnet_prefix   = "172.16.2.0/24"
hub_route_server_subnet_prefix = "172.16.4.0/24"
hub_nva_subnet_prefix        = "172.16.5.0/24"
hub_bastion_subnet_prefix    = "172.16.6.0/24"
```

### Advanced Routing Configuration

#### Gen VNet Routing Options
- **Default Routing**: Standard Azure routing
- **Non-Gen Firewall Routing**: Route all traffic (0.0.0.0/0) through Non-Gen firewall for inspection

#### Route Tables
- **Gateway Route Table**: Routes BGP advertised networks through Hub firewall
- **Gen Workload Route Table**: Optional routing through Non-Gen firewall
- **Non-Gen Firewall Route Table**: Routes on-premises and hub traffic through Hub firewall

### VNet Peering Architecture
- **Hub-to-Non-Gen**: Conditional peering with gateway transit options
- **Gen-to-Non-Gen**: Optional direct peering for workload communication

## BGP Configuration

The infrastructure implements BGP routing between Azure components:
```
On-Premises Network
    ↕ ExpressRoute
ExpressRoute Gateway (ASN: 65515)
    ↕ BGP Peering
Azure Route Server (ASN: 65515)
    ↕ BGP Peering  
Linux NVA (ASN: 65001)
```

#### **BGP Configuration Variables:**
```hcl
# On-premises settings (optional)
onpremises_address_space = []              # On-premises networks for firewall rules

# Azure BGP settings (automatic)
# ExpressRoute Gateway ASN: 65515 (Azure default)
# Route Server ASN: 65515 (Azure default)
# NVA ASN: 65001 (configurable)
```

#### **Route Advertisement Flow:**
1. **On-premises → Azure**: Routes learned via ExpressRoute are advertised to Route Server
2. **Route Server → NVA**: Route Server shares learned routes with NVA via BGP
3. **NVA → Route Server**: NVA advertises custom routes back to Route Server
4. **Azure → On-premises**: All Azure routes are advertised back via ExpressRoute

#### **Key BGP Features:**
- **Automatic Route Learning**: Dynamic discovery of on-premises networks via ExpressRoute
- **Route Propagation**: Seamless route sharing between all BGP speakers
- **Custom Routes**: NVA can inject custom routes into the topology
- **Traffic Engineering**: Route preferences via BGP attributes

#### **BGP Monitoring:**
```bash
# Check BGP status on NVA (access via Bastion or private connectivity)
ssh azureuser@<nva-private-ip>
sudo vtysh -c "show bgp summary"
sudo vtysh -c "show ip route bgp"

# Azure CLI commands for Route Server
az network routeserver peering list-learned-routes --routeserver rs-linklandingzone-prod --resource-group rg-linklandingzone-prod --name bgp-nva-linklandingzone-prod
az network routeserver peering list-advertised-routes --routeserver rs-linklandingzone-prod --resource-group rg-linklandingzone-prod --name bgp-nva-linklandingzone-prod
```emises
- **Route Advertisement**: Automatic route learning and propagation
- **Dual Connectivity**: Works alongside ExpressRoute for redundancy

### 5. Azure Firewall Server & NVA

This Terraform configuration creates a comprehensive Azure network infrastructure including:

- **Virtual Network** with multiple specialized subnets
- **Azure Firewall** for network security and traffic inspection
- **ExpressRoute Gateway** for hybrid connectivity
- **Azure Route Server** for dynamic routing
- **Linux NVA (Network Virtual Appliance)** with BGP support

## Architecture Overview

**Hub-and-Spoke Network Architecture with Optional Non-Gen VNet**

The infrastructure implements a hub-and-spoke topology with a central hub VNet (172.16.0.0/16) and an optional Non-Gen spoke VNet (100.0.0.0/16). The Non-Gen VNet connects via VNet peering without gateway transit, maintaining network isolation while allowing inter-VNet communication.

```
┌─────────────────────────────────────────────────────────────────┐
│                  Virtual Network (172.16.0.0/16)               │
├─────────────────────────────────────────────────────────────────┤
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐  │
│  │   Gateway       │  │  Azure Firewall │  │ Firewall Mgmt   │  │
│  │   Subnet        │  │     Subnet      │  │    Subnet       │  │
│  │ 172.16.1.0/24   │  │ 172.16.2.0/24   │  │ 172.16.3.0/24   │  │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘  │
│                                                                 │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐  │
│  │  Route Server   │  │   NVA Subnet    │  │Azure Bastion    │  │
│  │    Subnet       │  │                 │  │   Subnet        │  │
│  │ 172.16.4.0/24   │  │ 172.16.5.0/24   │  │ 172.16.6.0/24   │  │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
           │                       │
    ┌──────▼──────┐        ┌──────▼──────┐
    │ ExpressRoute│        │Azure Route  │
    │  Gateway    │        │   Server    │◄──────┐
    │             │        │(BGP: 65515) │       │
    └─────────────┘        └─────┬───────┘       │
           │                     │               │
           │              ┌──────▼──────┐        │
           │              │   BGP       │        │
           │              │  Peering    │        │
           │              └──────┬──────┘        │
           │                     │               │
    ┌──────▼──────┐        ┌─────▼─────┐         │
    │Local Network│        │Linux NVA  │         │
    │  Gateway    │        │(BGP:65001)│         │
    │(On-Premises)│        └───────────┘         │
    └──────┬──────┘                              │
           │                                     │
    ┌──────▼──────┐                      ┌──────▼──────┐
    │On-Premises  │                      │   BGP       │
    │   Network   │◄─────ExpressRoute────┤ Connection  │
    │192.168.0.0/16│                      └─────────────┘
    └─────────────┘
```

## Components

### 1. Virtual Network & Subnets
- **Hub VNet**: 172.16.0.0/16
  - **GatewaySubnet**: 172.16.1.0/24 (ExpressRoute Gateway)
  - **AzureFirewallSubnet**: 172.16.2.0/24 (Azure Firewall)
  - **AzureFirewallManagementSubnet**: 172.16.3.0/24 (Firewall Management)
  - **RouteServerSubnet**: 172.16.4.0/24 (Azure Route Server)
  - **NVA Subnet**: 172.16.5.0/24 (Linux NVA)
  - **AzureBastionSubnet**: 172.16.6.0/24 (Azure Bastion - Optional)
- **Non-Gen VNet**: 100.0.0.0/16 (Optional)
  - **AzureFirewallSubnet**: 100.0.1.0/24 (Azure Firewall)

### 2. Azure Firewall
- **Standard SKU** with dedicated management subnet
- **Application Rules**: Allow Azure services, Windows Update
- **Network Rules**: Allow DNS, NTP, internal traffic, on-premises traffic
- **ICMP Support**: Enabled for connectivity testing
- **Force Tunneling**: Configurable option to route all internet traffic back to on-premises

### 3. ExpressRoute Gateway
- **Standard SKU** ExpressRoute Gateway
- **Circuit**: Configurable bandwidth and provider
- **Private Peering**: Configured for on-premises connectivity
- **Route Table**: Gateway subnet has routes for BGP advertised networks via Azure Firewall

### 4. Azure Route Server
- **Standard SKU** with configurable branch-to-branch traffic
- **BGP ASN**: 65515 (Azure default)
- **High Availability**: Two virtual router IPs
- **Branch-to-Branch Traffic**: Configurable via `route_server_branch_to_branch` variable (default: enabled)

### 5. Linux NVA
- **Ubuntu 20.04 LTS** with FRR (Free Range Routing)
- **BGP Configuration**: Peers with Azure Route Server
- **IP Forwarding**: Enabled for traffic transit
- **Custom Scripts**: Included for BGP management
- **Network Access**: Private IP only - access via Azure Bastion or private connectivity

### 7. Azure Bastion (Optional)
- **Standard SKU** for secure RDP/SSH access
- **Browser-based Access**: No need for VPN or public IPs on VMs
- **Conditional Deployment**: Controlled by `deploy_bastion` variable
- **Dedicated Subnet**: Uses AzureBastionSubnet (172.16.6.0/24)

### 8. Non-Gen VNet (Optional)
- **Address Space**: 100.0.0.0/16
- **Azure Firewall**: Standard SKU with dedicated management subnet
- **VNet Peering**: Connected to Hub VNet without gateway transit
- **Network Isolation**: Separate firewall policies for non-gen workloads
- **Conditional Deployment**: Controlled by `deploy_nongen_vnet` variable
- **Force Tunneling**: Supports same force tunneling configuration as hub firewall

## Prerequisites

## Prerequisites

1. **Azure Subscription** with appropriate permissions
2. **Service Principal** for Terraform authentication
3. **ExpressRoute Circuit** provisioning with your service provider (if using ExpressRoute)
4. **Terraform** >= 1.0
5. **Azure CLI** (optional, for management)

## Quick Start

### 1. Clone and Configure

```bash
git clone <repository>
cd LinkLandingZone
```

### 2. Configure Variables

Copy the example variables file and update with your values:

```bash
cp terraform.tfvars.example terraform.tfvars
```

### 3. Example Configuration

Here's a basic configuration to get started:

```hcl
# Azure Provider Configuration
subscription_id = "your-subscription-id"
tenant_id       = "your-tenant-id"
client_id       = "your-client-id"
client_secret   = "your-client-secret"

# General Configuration
location     = "East US 2"
environment  = "prod"
project_name = "linklandingzone"

# Start with just the resource group (all components disabled)
deploy_hub_vnet             = false
deploy_gen_vnet             = false
deploy_nongen_vnet          = false
deploy_expressroute_gateway = false
deploy_hub_firewall         = false
deploy_route_server         = false
deploy_linux_nva            = false
deploy_bastion              = false
deploy_gen_nongen_peering   = false
route_internet_to_nongen_firewall = false

# Hub Firewall Advanced Features (disabled by default)
hub_firewall_explicit_proxy            = false
hub_firewall_explicit_proxy_nat        = false
hub_firewall_explicit_proxy_http_port  = 8080
hub_firewall_explicit_proxy_https_port = 8443
hub_firewall_arc_rules                 = false
deploy_arc_private_endpoint      = false
```

### 4. Deploy Infrastructure

```bash
# Initialize Terraform
terraform init

# Plan deployment (should show only resource group creation)
terraform plan

# Apply configuration
terraform apply
```

## 🚀 Interactive Demo Script

For an easier way to explore and deploy demos, use the interactive script:

### Quick Demo Deployment

```bash
# Run the interactive demo script
./run-demo.sh
```

The script provides:
- **✅ Interactive Menu**: Choose from available demos
- **✅ Prerequisites Check**: Validates Azure CLI, Terraform, and credentials
- **✅ Cost Warnings**: Shows estimated costs before deployment
- **✅ Safe Operations**: Confirmation prompts for apply/destroy actions
- **✅ State Management**: View current resources and outputs

### Available Demo Actions

1. **Plan** - Preview changes without deploying
2. **Apply** - Deploy the demo infrastructure
3. **Destroy** - Remove all demo resources
4. **Show State** - Display current Terraform state
5. **Show Outputs** - Display Terraform outputs

### Demo Options

| Demo | Description | Cost | Time |
|------|-------------|------|------|
| **Arc** | Azure Arc hybrid management | ~$150/month | 30-40 min |
| **VPN** | Site-to-Site VPN connectivity | ~$1,250/month | 45-60 min |
| **ExpressRoute** | Private connectivity (requires circuit) | ~$800-2,000/month | 30-45 min |
| **Hub-Spoke** | Network architecture with segmentation | ~$1,000/month | 30-45 min |

### Script Features

- **🔍 Prerequisites Validation**: Checks Azure CLI login, Terraform installation, and credentials
- **💰 Cost Transparency**: Shows estimated monthly costs before deployment
- **🛡️ Safety Confirmations**: Requires explicit confirmation for apply/destroy operations
- **📊 State Visibility**: Easy access to current infrastructure state and outputs
- **🎨 Colored Output**: Clear visual feedback for different operations

### Example Usage

```bash
# Start the interactive script
./run-demo.sh

# The script will guide you through:
# 1. Prerequisites check
# 2. Demo selection
# 3. Action selection (plan/apply/destroy)
# 4. Cost warnings and confirmations
# 5. Terraform execution with progress feedback
```

### 5. Incremental Deployment

Enable components as needed by updating `terraform.tfvars`:

```hcl
# Enable Hub VNet first
deploy_hub_vnet = true

# Then add other components
deploy_hub_firewall = true
deploy_route_server = true

# Enable Azure Arc connectivity (choose one or both)
hub_firewall_arc_rules = true              # Public connectivity with firewall rules
deploy_arc_private_endpoint = true   # Private endpoint connectivity

# Enable explicit proxy functionality
hub_firewall_explicit_proxy = true
hub_firewall_explicit_proxy_http_port = 8080
hub_firewall_explicit_proxy_https_port = 8443

# Windows Server 2025 with Azure Arc onboarding
deploy_onprem_windows_server = true        # Deploy Windows Server 2025
onprem_windows_arc_onboarding = true       # Enable Arc onboarding
onprem_windows_arc_auto_upgrade = true     # Enable automatic agent upgrades

# Add additional components as needed
deploy_bastion = true
deploy_linux_nva = true
deploy_squid_proxy = true  # Add Squid proxy for HTTP/HTTPS proxy services
# ... etc
```

## Configuration Examples

### Hub-Only Configuration
```hcl
# Enable only Hub VNet with basic components
deploy_hub_vnet     = true
deploy_hub_firewall = true
deploy_bastion      = true

# Keep other components disabled
deploy_gen_vnet    = false
deploy_nongen_vnet = false
```

### Hub with Azure Arc Public Connectivity
```hcl
# Hub VNet with Azure Arc firewall rules
deploy_hub_vnet = true
deploy_hub_firewall = true
hub_firewall_arc_rules = true

# Keep Arc private endpoints disabled for public connectivity
deploy_arc_private_endpoint = false
```

### Hub with Azure Arc Private Connectivity
```hcl
# Hub VNet with Azure Arc private endpoints
deploy_hub_vnet = true
deploy_hub_firewall = true
deploy_arc_private_endpoint = true

# Optional: Enable firewall rules for additional security
hub_firewall_arc_rules = true
```

### Windows Server 2025 with Azure Arc Onboarding
```hcl
# Complete setup for Windows Server 2025 Arc onboarding
deploy_hub_vnet = true
deploy_hub_firewall = true
deploy_onprem_vnet = true
deploy_onprem_windows_server = true

# Enable Azure Arc connectivity and firewall rules
hub_firewall_arc_rules = true
onprem_windows_arc_onboarding = true
onprem_windows_arc_auto_upgrade = true

# Optional: Enable explicit proxy for Arc traffic
hub_firewall_explicit_proxy = true
hub_firewall_explicit_proxy_http_port = 3128

# Enable monitoring and management
deploy_azure_monitor_private_link_scope = true
deploy_windows_dce_dcr = true
deploy_bastion = true  # For secure VM access
```

### Hub with Explicit Proxy
```hcl
# Hub VNet with explicit proxy functionality
deploy_hub_vnet = true
deploy_hub_firewall = true
hub_firewall_explicit_proxy = true
hub_firewall_explicit_proxy_http_port = 8080
hub_firewall_explicit_proxy_https_port = 8443
```

### Hub with Squid Proxy
```hcl
# Hub VNet with Linux Squid proxy VM
deploy_hub_vnet = true
deploy_hub_firewall = true
deploy_squid_proxy = true
deploy_bastion = true  # For secure proxy management
```

### Hub with Azure Arc and AMPLS
```hcl
# Hub VNet with Arc connectivity and monitoring
deploy_hub_vnet = true
deploy_hub_firewall = true
deploy_arc_private_endpoint = true
deploy_azure_monitor_private_link_scope = true
log_analytics_workspace_retention_days = 90
```

### Multi-VNet with Gen Routing
```hcl
# Enable all VNets
deploy_hub_vnet    = true
deploy_gen_vnet    = true
deploy_nongen_vnet = true

# Enable Gen-to-Non-Gen routing through firewall
route_internet_to_nongen_firewall = true

# Enable VNet peering
deploy_gen_nongen_peering = true
```

### Full Enterprise Configuration
```hcl
# Enable all components
deploy_hub_vnet             = true
deploy_gen_vnet             = true
deploy_nongen_vnet          = true
deploy_expressroute_gateway = true
deploy_hub_firewall         = true
deploy_route_server         = true
deploy_linux_nva            = true
deploy_bastion              = true
deploy_gen_nongen_peering   = true
route_internet_to_nongen_firewall = true

# Enable BGP routing
enable_expressroute_gateway_bgp = true
```

### Enterprise with Azure Arc and Explicit Proxy
```hcl
# Full enterprise setup with Arc connectivity and explicit proxy
deploy_hub_vnet             = true
deploy_gen_vnet             = true
deploy_nongen_vnet          = true
deploy_expressroute_gateway = true
deploy_hub_firewall         = true
deploy_route_server         = true
deploy_linux_nva            = true
deploy_bastion              = true
deploy_squid_proxy          = true  # Add Squid proxy for additional proxy services
deploy_gen_nongen_peering   = true
route_internet_to_nongen_firewall = true

# Azure Arc connectivity options
hub_firewall_arc_rules = true
deploy_arc_private_endpoint = true

# Azure Monitor Private Link Scope
deploy_azure_monitor_private_link_scope = true
log_analytics_workspace_retention_days = 90

# Explicit proxy configuration
hub_firewall_explicit_proxy = true
hub_firewall_explicit_proxy_http_port = 8080
hub_firewall_explicit_proxy_https_port = 8443

# Enable BGP routing
enable_expressroute_gateway_bgp = true
```

## Network Addressing

### Default Address Spaces
- **Hub VNet**: 172.16.0.0/16
- **Gen VNet**: 10.0.0.0/16
- **Non-Gen VNet**: 100.0.0.0/16

### Subnet Allocation
#### Hub VNet Subnets
- **Gateway Subnet**: 172.16.1.0/24
- **Azure Firewall Subnet**: 172.16.2.0/24
- **Route Server Subnet**: 172.16.4.0/24
- **NVA Subnet**: 172.16.5.0/24
- **Azure Bastion Subnet**: 172.16.6.0/24

#### Gen VNet Subnets
- **Workload Subnet**: 10.0.1.0/24

#### Non-Gen VNet Subnets
- **Azure Firewall Subnet**: 100.0.1.0/24

## Security Features

### Azure Firewall Integration
- **Hub Firewall**: Protects hub infrastructure and on-premises traffic
- **Non-Gen Firewall**: Dedicated firewall for non-generative workloads
- **Force Tunneling**: Optional configuration to route all traffic through on-premises

### Network Segmentation
- **VNet Isolation**: Separate VNets for different workload types
- **Subnet Segmentation**: Dedicated subnets for specific functions
- **Firewall Rules**: Granular control over traffic flows

### Access Control
- **Azure Bastion**: Secure management access without public IPs
- **Private Endpoints**: All management traffic through private connectivity
- **NSG Rules**: Network-level security controls

## Azure Arc Connectivity Features

The infrastructure provides comprehensive Azure Arc connectivity options for hybrid cloud scenarios, including both public and private connectivity methods.

### Azure Arc Firewall Rules

Enable Azure Arc connectivity through firewall rules for public endpoints:

```hcl
# Enable Azure Arc firewall rules for public connectivity
hub_firewall_arc_rules = true
```

When `hub_firewall_arc_rules = true`, the infrastructure creates comprehensive firewall rules for Azure Arc agent connectivity:

#### Network Rules
- **Azure Arc Agent Core**: Connectivity to Azure Arc management endpoints (443/TCP)
- **Azure Resource Manager**: Access to Azure management APIs (443/TCP)
- **Azure Active Directory**: Authentication and authorization (443/TCP)
- **Windows Update**: Agent updates via Microsoft endpoints (80/TCP, 443/TCP)

#### Application Rules
- **Agent Download**: Download and updates from `*.servicebus.windows.net`, `*.core.windows.net`
- **Configuration Services**: Access to `*.guestconfiguration.azure.com`, `*.his.hybridcompute.azure-automation.net`
- **Azure Services**: Connectivity to core Azure Arc services and endpoints
- **Microsoft Downloads**: Agent binaries and updates from Microsoft CDN

### Azure Arc Private Endpoints

Enable Azure Arc private endpoint connectivity for enhanced security:

```hcl
# Enable Azure Arc private endpoints for private connectivity
deploy_arc_private_endpoint = true
```

When `deploy_arc_private_endpoint = true`, the infrastructure creates:

#### Private DNS Zones
- **Guest Configuration**: `privatelink.guestconfiguration.azure.com`
- **Hybrid Compute**: `privatelink.his.hybridcompute.azure-automation.net`  
- **Download Services**: `privatelink.dp.kubernetesconfiguration.azure.com`

#### VNet Links
- **Hub VNet Integration**: Links private DNS zones to Hub VNet for name resolution
- **Automatic DNS**: Resolves Azure Arc service names to private endpoint IPs
- **Security Enhancement**: All Arc traffic remains within private network

### Azure Arc Connectivity Options

The infrastructure supports three Azure Arc connectivity patterns:

#### 1. Public Connectivity (Default)
```hcl
hub_firewall_arc_rules = false
deploy_arc_private_endpoint = false
```
- Azure Arc agents connect directly to public endpoints
- No special firewall configuration required
- Suitable for basic hybrid scenarios

#### 2. Firewall-Enabled Public Connectivity
```hcl
hub_firewall_arc_rules = true
deploy_arc_private_endpoint = false
```
- Azure Arc traffic inspected by Azure Firewall
- Comprehensive firewall rules for all Arc services
- Enhanced security while maintaining public connectivity
- Ideal for environments requiring traffic inspection

#### 3. Private Endpoint Connectivity
```hcl
hub_firewall_arc_rules = false  # Optional: can be enabled for additional security
deploy_arc_private_endpoint = true
```
- All Azure Arc traffic uses private endpoints
- Private DNS zones for service name resolution
- Maximum security with network isolation
- Required for highly secure environments

### Hub Firewall Explicit Proxy

Enable explicit proxy functionality on Azure Firewall for web traffic filtering:

```hcl
# Enable explicit proxy with custom ports
hub_firewall_explicit_proxy = true
hub_firewall_explicit_proxy_http_port = 8080   # Default: 8080
hub_firewall_explicit_proxy_https_port = 8443  # Default: 8443
```

#### Explicit Proxy Features
- **HTTP/HTTPS Proxy**: Dedicated proxy ports for web traffic
- **Configurable Ports**: Customize proxy ports based on requirements
- **TLS Inspection**: Enhanced visibility into HTTPS traffic
- **Policy Enforcement**: Apply web filtering and security policies

#### Use Cases
- **Corporate Proxy**: Replace traditional proxy appliances
- **Web Filtering**: Control and monitor internet access
- **Compliance**: Meet regulatory requirements for web traffic inspection
- **Zero Trust**: Enhanced security for outbound internet traffic

#### Configuration Example
```hcl
# Hub Firewall with explicit proxy enabled
deploy_hub_firewall = true
hub_firewall_explicit_proxy = true
hub_firewall_explicit_proxy_http_port = 8080
hub_firewall_explicit_proxy_https_port = 8443

# Optional: Combine with Arc connectivity
hub_firewall_arc_rules = true
deploy_arc_private_endpoint = true
```

### Recommended Configurations

#### Standard Enterprise Setup
```hcl
# Hub Firewall with Arc connectivity and explicit proxy
deploy_hub_firewall = true
hub_firewall_explicit_proxy = true
hub_firewall_arc_rules = true
deploy_arc_private_endpoint = false
```

#### High-Security Environment
```hcl
# Maximum security with private endpoints
deploy_hub_firewall = true
hub_firewall_explicit_proxy = true
hub_firewall_arc_rules = true  # Optional additional layer
deploy_arc_private_endpoint = true
```

#### Basic Hybrid Cloud
```hcl
# Simple setup without additional Arc features
deploy_hub_firewall = true
hub_firewall_explicit_proxy = false
hub_firewall_arc_rules = false
deploy_arc_private_endpoint = false
```

## Linux Squid Proxy

The infrastructure provides an optional Linux Squid proxy VM in the Hub VNet for HTTP/HTTPS proxy services:

```hcl
# Enable Squid proxy VM in hub
deploy_squid_proxy = true
```

### Squid Proxy Features

When `deploy_squid_proxy = true`, the infrastructure creates:

#### Infrastructure Components
- **Dedicated Subnet**: `172.16.7.0/24` (default) in Hub VNet
- **Ubuntu 20.04 VM**: Standard_B2s size (configurable)
- **Network Security Group**: Allow SSH (22) and Squid proxy (3128) traffic
- **Route Table**: Routes internet traffic through Hub Firewall for inspection

#### Squid Configuration
- **Proxy Port**: 3128 (standard Squid port)
- **HTTPS Intercept Port**: 3129 (SSL bump functionality)
- **SSL Bump**: Self-signed CA certificate for HTTPS inspection
- **Access Control**: Allows access from Hub VNet, Gen VNet, Non-Gen VNet, and on-premises networks
- **Caching**: 100MB disk cache with 256MB memory cache
- **Logging**: Comprehensive access and cache logging
- **DNS**: Uses Azure DNS (168.63.129.16)
- **Certificate Management**: Automatic generation and management of SSL certificates

#### Security Integration
- **Hub Firewall Routing**: All internet traffic routed through Hub Firewall for inspection
- **Network Segmentation**: Dedicated subnet with NSG protection
- **Access Control**: Limited to internal networks only
- **Management Access**: SSH access via Azure Bastion or private connectivity
- **SSL Bump**: HTTPS traffic inspection with self-signed CA certificate
- **Certificate Security**: Protected sites list to prevent bumping sensitive domains

#### SSL Bump Features
- **HTTPS Inspection**: Deep packet inspection of encrypted traffic
- **Self-Signed CA**: Automatically generated certificate authority
- **Protected Sites**: Banking and government sites excluded from bumping
- **Certificate Management**: Automatic certificate generation and rotation
- **Client Configuration**: CA certificate must be installed on client machines

#### Configuration Variables
```hcl
# Squid Proxy Configuration
deploy_squid_proxy          = true           # Enable Squid proxy deployment
hub_squid_subnet_prefix     = "172.16.7.0/24" # Squid proxy subnet
squid_vm_size              = "Standard_B2s"   # VM size
squid_admin_username       = "azureuser"      # Admin username
squid_admin_password       = "YourPassword"   # Admin password (sensitive)
```

### Use Cases

#### Corporate Proxy Services
- **Web Filtering**: Control and monitor internet access
- **Content Caching**: Improve performance for frequently accessed content
- **Bandwidth Management**: Optimize internet bandwidth usage
- **Compliance**: Meet regulatory requirements for web traffic monitoring
- **SSL Inspection**: Deep packet inspection of HTTPS traffic
- **Data Loss Prevention**: Monitor and prevent sensitive data exfiltration

#### Hybrid Cloud Integration
- **Centralized Proxy**: Single proxy point for all Azure workloads
- **On-premises Integration**: Extend existing proxy policies to Azure
- **Traffic Inspection**: All proxy traffic inspected by Hub Firewall
- **Secure Browsing**: Enhanced security for web traffic

#### External Proxy Access (Azure Firewall NAT)
When `hub_firewall_explicit_proxy_nat = true` is enabled, Azure Firewall provides external access to its explicit proxy via NAT rules:

- **Branch Office Integration**: Remote offices can use Azure Firewall as their internet proxy
- **Remote Worker Access**: Home users and mobile workers can route traffic through corporate firewall
- **Partner Network Access**: Business partners can use your proxy for controlled internet access
- **Development Environment**: External development teams can test through production-like proxy
- **Centralized Policy Enforcement**: All external users subject to same firewall policies

**Configuration Example:**
```hcl
# Enable Azure Firewall with external proxy access
deploy_hub_firewall                    = true
hub_firewall_explicit_proxy            = true
hub_firewall_explicit_proxy_nat        = true
hub_firewall_explicit_proxy_http_port  = 8080
hub_firewall_explicit_proxy_https_port = 8443
```

**Client Configuration (External Users):**
```bash
# Linux/macOS
export http_proxy="http://<firewall-public-ip>:8080"
export https_proxy="http://<firewall-public-ip>:8443"

# Windows (PowerShell)
netsh winhttp set proxy proxy-server="<firewall-public-ip>:8080"
```

**Security Considerations:**
- NAT rules allow access from any source (`*`) - consider restricting in production
- Monitor firewall logs for unauthorized proxy usage
- Implement additional authentication if required
- Consider Network Security Groups for additional access control

### Management and Monitoring

#### Status Monitoring
```bash
# Connect via Bastion or private connectivity
ssh azureuser@<squid-vm-private-ip>

# Check Squid status
sudo systemctl status squid

# Use built-in monitoring script
./check_squid.sh

# Export CA certificate for client installation
./export_ca_cert.sh
```

#### Log Analysis
```bash
# View access logs
sudo tail -f /var/log/squid/access.log

# View cache logs
sudo tail -f /var/log/squid/cache.log

# Configuration validation
sudo squid -k parse
```

#### Configuration Updates
```bash
# Edit Squid configuration
sudo nano /etc/squid/squid.conf

# Test configuration
sudo squid -k parse

# Reload configuration
sudo systemctl reload squid

# Edit protected sites (no SSL bump)
sudo nano /etc/squid/nobump_sites.txt

# Check SSL certificate database
ls -la /var/lib/squid/ssl_db/

# View CA certificate
openssl x509 -in /etc/squid/ssl_cert/squid-ca-cert.pem -text -noout
```

#### Client Configuration for SSL Bump
```bash
# Export CA certificate
./export_ca_cert.sh

# Copy certificate to client machines and install:
# Windows: Import into 'Trusted Root Certification Authorities'
# Linux: Copy to /usr/local/share/ca-certificates/ and run update-ca-certificates
# macOS: Add to Keychain and mark as trusted

# Configure client proxy settings:
# HTTP Proxy: <squid-ip>:3128
# HTTPS Proxy: <squid-ip>:3128 (or 3129 for direct intercept)
```

### Traffic Flow

#### Internet Access Pattern
```
Client → Squid Proxy (3128/3129) → Hub Firewall → Internet
  ↓           ↓                       ↓
[Request]  [Caching/SSL Bump]    [Inspection]
```

#### SSL Bump Flow
```
HTTPS Request → Squid (3129) → SSL Bump → Certificate Generation → Inspection → Hub Firewall → Internet
      ↓              ↓             ↓               ↓                ↓              ↓
[Client Cert]  [CA Signing]  [Content Scan]  [Policy Check]  [Network Filter]  [External]
```

#### Network Routing
- **Squid Subnet**: Uses route table directing internet traffic to Hub Firewall
- **Firewall Inspection**: All outbound traffic inspected by firewall rules
- **Return Traffic**: Cached responses served directly from Squid

### Recommended Configurations

#### Basic Proxy Setup
```hcl
# Simple proxy with firewall integration
deploy_hub_firewall = true
deploy_squid_proxy = true
```

#### Enterprise Proxy with Monitoring
```hcl
# Full proxy setup with management access
deploy_hub_firewall = true
deploy_squid_proxy = true
deploy_bastion = true  # For secure management access
```

#### High-Security Proxy Environment
```hcl
# Maximum security with Arc integration
deploy_hub_firewall = true
deploy_squid_proxy = true
deploy_bastion = true
hub_firewall_explicit_proxy = true
hub_firewall_arc_rules = true
```

## Azure Monitor Private Link Scope (AMPLS)

The infrastructure provides secure monitoring for Azure Arc enabled servers through Azure Monitor Private Link Scope:

```hcl
# Enable Azure Monitor Private Link Scope
deploy_azure_monitor_private_link_scope = true
```

### AMPLS Features

When `deploy_azure_monitor_private_link_scope = true`, the infrastructure creates:

#### Core Components
- **Log Analytics Workspace**: Centralized logging and monitoring for Arc servers
- **Azure Monitor Private Link Scope**: Security boundary for monitoring services
- **Private Endpoints**: Secure connectivity to Azure Monitor services
- **Private DNS Zones**: Name resolution for monitoring endpoints

#### Private DNS Zones Created
- `privatelink.monitor.azure.com` - Azure Monitor API endpoints
- `privatelink.oms.opinsights.azure.com` - Log Analytics operations
- `privatelink.ods.opinsights.azure.com` - Data collection endpoints
- `privatelink.agentsvc.azure-automation.net` - Agent service endpoints
- `privatelink.blob.core.windows.net` - Storage for monitoring data

#### Security Benefits
- **Network Isolation**: All monitoring traffic stays within Azure backbone
- **Data Protection**: Encrypted transmission with private endpoint connectivity
- **Access Control**: Controlled through private link scope boundaries
- **Compliance**: Meets strict security requirements for monitoring data

### Arc Server Integration

#### VM Insights for Arc Servers
- **Performance Monitoring**: CPU, memory, disk, and network metrics
- **Dependency Mapping**: Application and service dependencies
- **Log Collection**: System and application logs
- **Alert Integration**: Proactive monitoring and notifications

#### Configuration Variables
```hcl
# AMPLS Configuration
deploy_azure_monitor_private_link_scope             = true           # Enable AMPLS
log_analytics_workspace_retention_days = 90             # Log retention (30-730 days)
log_analytics_workspace_sku            = "PerGB2018"    # Pricing tier
```

#### Supported Workspace SKUs
- `Free` - 500MB daily limit
- `Standard` - Legacy pricing tier
- `Premium` - Legacy pricing tier with advanced features
- `PerNode` - Per node pricing
- `PerGB2018` - Pay-as-you-go (recommended)
- `Standalone` - Standalone pricing
- `CapacityReservation` - Reserved capacity pricing

### Use Cases

#### Enterprise Monitoring
- **Hybrid Infrastructure**: Monitor on-premises and Azure Arc servers
- **Centralized Logging**: Single pane of glass for all server monitoring
- **Security Monitoring**: Security events and compliance tracking
- **Performance Optimization**: Identify bottlenecks and optimize performance

#### Compliance and Security
- **Data Sovereignty**: Keep monitoring data within specific regions
- **Network Security**: No internet exposure for monitoring traffic
- **Audit Requirements**: Comprehensive logging for compliance
- **Zero Trust**: Align with zero trust security principles

### Arc Agent Configuration

#### Automatic Configuration
When AMPLS is deployed, Arc agents can be configured to use private endpoints:

```bash
# Arc agents automatically detect private endpoints when configured
# Use Azure Policy or ARM templates to configure workspace settings
```

#### Manual Configuration
```powershell
# PowerShell example for Windows Arc servers
$workspaceId = "<workspace-id>"
$workspaceKey = "<workspace-key>"

# Install monitoring agent with private endpoint configuration
```

```bash
# Linux Arc servers
sudo wget https://raw.githubusercontent.com/Microsoft/OMS-Agent-for-Linux/master/installer/scripts/onboard_agent.sh
sudo sh onboard_agent.sh -w $WORKSPACE_ID -s $WORKSPACE_KEY -d opinsights.azure.com
```

## Monitoring and Management

### BGP Monitoring
```bash
# Check BGP status on NVA
ssh azureuser@<nva-private-ip>
sudo vtysh -c "show bgp summary"
sudo vtysh -c "show ip route bgp"
```

### Azure CLI Commands
```bash
# Route Server monitoring
az network routeserver peering list-learned-routes \
  --routeserver rs-linklandingzone-prod \
  --resource-group rg-linklandingzone-prod \
  --name bgp-nva-linklandingzone-prod

# Firewall monitoring
az network firewall show \
  --resource-group rg-linklandingzone-prod \
  --name afw-linklandingzone-prod
```

## Cost Optimization

### Public IP Reduction
- **Conditional Deployment**: Deploy only needed components
- **Shared Resources**: Single Bastion for multiple VNets
- **Force Tunneling**: Reduce firewall public IPs when possible

### Resource Sizing
- **Standard SKUs**: Balanced performance and cost
- **Conditional Components**: Disable unused features
- **Auto-shutdown**: Configure VM auto-shutdown for dev environments

## Troubleshooting

### Common Issues

#### Terraform Validation Errors
```bash
# Check syntax
terraform validate

# Format code
terraform fmt
```

#### BGP Connectivity Issues
```bash
# Check NVA status
systemctl status frr

# Restart FRR if needed
sudo systemctl restart frr
```

#### Firewall Rule Issues
- Check firewall logs in Azure Monitor
- Verify route table configurations
- Test connectivity with Network Watcher

### Support

For issues and questions:
1. Check Azure Monitor logs
2. Review Terraform state
3. Validate network connectivity
4. Check BGP status and routes

## Variables Reference

### Core Variables
```hcl
# Required - Azure Provider
subscription_id = "your-subscription-id"
tenant_id       = "your-tenant-id"
client_id       = "your-client-id"
client_secret   = "your-client-secret"

# Required - General
location     = "East US 2"
environment  = "prod"
project_name = "linklandingzone"

# Optional - Feature Flags (all default to false)
deploy_hub_vnet             = false
deploy_gen_vnet             = false
deploy_nongen_vnet          = false
deploy_expressroute_gateway = false
deploy_hub_firewall         = false
deploy_route_server         = false
deploy_linux_nva            = false
deploy_bastion              = false
deploy_squid_proxy          = false  # Linux Squid proxy VM in hub
deploy_gen_nongen_peering   = false
route_internet_to_nongen_firewall = false

# Optional - Hub Firewall Advanced Features
hub_firewall_explicit_proxy            = false  # Enable explicit proxy functionality
hub_firewall_explicit_proxy_nat        = false  # Enable NAT rules for external proxy access
hub_firewall_explicit_proxy_http_port  = 8080   # HTTP proxy port (default: 8080)
hub_firewall_explicit_proxy_https_port = 8443   # HTTPS proxy port (default: 8443)
hub_firewall_arc_rules                 = false  # Enable Azure Arc firewall rules
deploy_arc_private_endpoint      = false  # Enable Azure Arc private endpoints

# Optional - Azure Monitor Private Link Scope
deploy_azure_monitor_private_link_scope                 = false     # Enable Azure Monitor Private Link Scope
log_analytics_workspace_retention_days     = 30        # Log retention period (30-730 days)
log_analytics_workspace_sku                = "PerGB2018"  # Workspace pricing tier
```

### Network Configuration
```hcl
# Hub VNet
hub_vnet_address_space       = ["172.16.0.0/16"]
hub_gateway_subnet_prefix    = "172.16.1.0/24"
hub_firewall_subnet_prefix   = "172.16.2.0/24"
hub_route_server_subnet_prefix = "172.16.4.0/24"
hub_nva_subnet_prefix        = "172.16.5.0/24"
hub_bastion_subnet_prefix    = "172.16.6.0/24"
hub_squid_subnet_prefix      = "172.16.7.0/24"

# Gen VNet
gen_vnet_address_space      = ["10.0.0.0/16"]
gen_workload_subnet_prefix  = "10.0.1.0/24"

# Non-Gen VNet
nongen_vnet_address_space      = ["100.0.0.0/16"]
nongen_firewall_subnet_prefix  = "100.0.1.0/24"
```

This modular infrastructure provides a robust foundation for Azure networking with the flexibility to deploy only the components you need while maintaining the ability to scale and add functionality over time.  
deploy_linux_nva = true

# Configure Route Server branch-to-branch traffic
route_server_branch_to_branch = true  # Default: true
```

### Azure Bastion
```hcl
# Enable/disable Azure Bastion deployment
deploy_bastion = false  # Default: disabled to save costs
```

### Azure Firewall Force Tunneling
```hcl
# Enable/disable force tunneling on Azure Firewall
firewall_force_tunneling = false  # Default: disabled
```

### Non-Gen VNet
```hcl
# Enable/disable Non-Gen VNet deployment
deploy_nongen_vnet = true  # Default: enabled
```

When `deploy_bastion = true`:
- Creates AzureBastionSubnet (172.16.6.0/24)
- Deploys Azure Bastion Standard SKU
- Provides secure browser-based access to VMs
- No need for public IPs on target VMs

### Azure Firewall Force Tunneling

The `firewall_force_tunneling` variable controls whether Azure Firewall routes all internet-bound traffic back to on-premises:

- **Disabled (`false`)**: Default behavior - Azure Firewall has a public IP and routes internet traffic directly
- **Enabled (`true`)**: All internet traffic is routed back to on-premises through VPN/ExpressRoute Gateway

When `firewall_force_tunneling = true`:
- **No Public IP**: Azure Firewall operates without a public IP for its main configuration
- **Route Table**: Creates a route table for AzureFirewallSubnet with default route (0.0.0.0/0) pointing to VirtualNetworkGateway
- **Traffic Flow**: All internet-bound traffic from Azure subnets is sent back to on-premises for inspection
- **Compliance**: Helps meet regulatory requirements for internet traffic inspection
- **Security**: Ensures all traffic passes through on-premises security appliances

**Use Cases for Force Tunneling:**
- **Regulatory Compliance**: Meet requirements for all traffic inspection on-premises
- **Corporate Policy**: Enforce internet access through corporate proxies/filters
- **Hybrid Security**: Centralize internet security controls in on-premises infrastructure
- **Audit Requirements**: Maintain complete visibility of internet access patterns

### Non-Gen VNet Configuration

The `deploy_nongen_vnet` variable controls whether to deploy a separate Non-Gen VNet with its own Azure Firewall:

- **Enabled (`true`)**: Creates a dedicated Non-Gen VNet with Azure Firewall
- **Disabled (`false`)**: Only the hub VNet is deployed

When `deploy_nongen_vnet = true`:
- **Separate Network**: Creates 100.0.0.0/16 address space for non-gen workloads
- **Dedicated Firewall**: Independent Azure Firewall with its own policies
- **VNet Peering**: Automatic peering with hub VNet without gateway transit
- **Network Isolation**: Separate security policies for non-gen and hub workloads
- **Direct Connectivity**: No reliance on hub VNet gateways for on-premises access

**Benefits of Non-Gen VNet:**
- **Security Isolation**: Separate firewall policies and rules
- **Network Segmentation**: Clear separation between different workload types
- **Independent Management**: Separate firewall configurations and monitoring
- **Compliance**: Meet requirements for workload separation

### Non-Gen VNet Transit Routing

The Non-Gen VNet implements a transit routing pattern for enhanced security:

**Traffic Flow Pattern:**
```
On-Premises ──► Hub Firewall ──► Non-Gen Firewall ──► Internet
             │                 │
             ▼                 ▼
        [Security Inspection] [Additional Filtering]
```

**Key Features:**
- **No Force Tunneling**: Non-Gen firewall has direct internet connectivity with public IP
- **Transit Inspection**: On-premises traffic is first inspected by hub firewall
- **Dual Firewall Protection**: Traffic passes through both hub and Non-Gen firewalls
- **Policy Layering**: Different security policies can be applied at each firewall layer

**Implementation Details:**
- Route table `rt-nongen-firewall` directs on-premises traffic (10.0.0.0/8) through hub firewall
- Hub firewall network rules allow transit traffic between on-premises and Non-Gen VNet
- Gateway route table routes Non-Gen VNet traffic through hub firewall for return path
- Non-Gen firewall maintains direct internet access for outbound traffic

### Hub Firewall Force Tunneling with Non-Gen VNet

When both hub force tunneling and Non-Gen VNet are enabled, the infrastructure implements a sophisticated routing pattern:

**Combined Force Tunneling Flow:**
```
Hub VNet Traffic ──► Hub Firewall ──► Non-Gen Firewall ──► Internet
                   │ (Force Tunnel) │                    │
                   ▼                ▼                    ▼
              [Policy Inspection] [Secondary Filter] [Direct Access]
```

**Behavior:**
- **Hub Force Tunneling Enabled + Non-Gen VNet**: Hub firewall routes internet traffic (0.0.0.0/0) to Non-Gen firewall
- **Hub Force Tunneling Enabled + No Non-Gen VNet**: Hub firewall routes internet traffic to on-premises via ExpressRoute Gateway
- **Hub Force Tunneling Disabled**: Hub firewall has direct internet access via public IP

**Benefits:**
- **Centralized Egress**: All hub internet traffic flows through Non-Gen firewall for consistent policy
- **Dual Security Layers**: Traffic inspected by both hub and Non-Gen firewalls
- **Flexibility**: Can disable Non-Gen VNet to revert to traditional force tunneling

### VNet Peering Configuration

The Non-Gen VNet connects to the hub VNet through VNet peering with specific settings for network isolation:

**Peering Settings:**
- **Hub to Non-Gen**: `allow_gateway_transit = false` - Hub does not share its gateways
- **Non-Gen to Hub**: `use_remote_gateways = false` - Non-Gen cannot use hub gateways
- **Forwarded Traffic**: `allow_forwarded_traffic = true` - Enables transit routing through firewalls
- **Virtual Network Access**: `allow_virtual_network_access = true` - Basic connectivity enabled

**Benefits:**
- **Network Isolation**: Non-Gen VNet cannot access on-premises through hub gateways
- **Security Boundary**: Traffic must flow through firewalls for inspection
- **Independent Routing**: Each VNet maintains its own routing decisions
- **Simplified Management**: No complex gateway dependencies between VNets

### Route Server Branch-to-Branch Traffic

The `route_server_branch_to_branch` variable controls whether the Azure Route Server allows direct communication between branches/spokes:

- **Enabled (`true`)**: Allows direct branch-to-branch communication through the Route Server
- **Disabled (`false`)**: Forces all inter-branch traffic through the hub (more restrictive security model)

This setting is useful for implementing different network topologies and security models:
- **Hub-and-spoke with branch isolation**: Set to `false` to force all traffic through the Azure Firewall
- **Full mesh connectivity**: Set to `true` for direct branch-to-branch communication

## Management

### NVA Management

Connect to the NVA for troubleshooting and configuration:

```bash
# Connect to NVA via Azure Bastion (if deployed)
# Use Azure Portal -> Virtual Machines -> vm-nva-linklandingzone-prod -> Connect -> Bastion

# OR connect via private connectivity (VPN/ExpressRoute)
ssh azureuser@<nva-private-ip>

# Check BGP status
./check_bgp.sh

# Access FRR shell
sudo vtysh

# View FRR configuration
sudo cat /etc/frr/frr.conf

# Restart FRR service
sudo systemctl restart frr
```

### Route Server Monitoring

Monitor BGP routes learned by the Route Server:

```bash
# Azure CLI commands
az network routeserver show --name rs-linklandingzone-prod --resource-group rg-linklandingzone-prod
az network routeserver peering show --routeserver rs-linklandingzone-prod --resource-group rg-linklandingzone-prod --name bgp-nva-linklandingzone-prod
```

### Firewall Monitoring

Monitor firewall logs and metrics:

```bash
# Azure CLI commands
az monitor log-analytics query --workspace <workspace-id> --analytics-query "AzureDiagnostics | where Category == 'AzureFirewallNetworkRule'"
```

## Customization

### Scaling

To scale the infrastructure:

1. **Upgrade Gateway SKU** for higher throughput
2. **Add additional NVAs** for redundancy
3. **Implement Load Balancer** for NVA high availability
4. **Add more subnets** as needed

## Troubleshooting

### Common Issues

1. **BGP Not Establishing**
   - Check NSG rules allow BGP (port 179)
   - Verify Route Server and NVA IP addresses
   - Check FRR service status on NVA

2. **ExpressRoute Connection Issues**
   - Verify circuit provisioning with provider
   - Check gateway and circuit configuration
   - Validate peering configuration

3. **Firewall Blocking Traffic**
   - Review firewall rules
   - Check firewall logs for denied traffic
   - Verify route table configurations

4. **Force Tunneling Issues**
   - Verify VPN/ExpressRoute Gateway is operational
   - Check route table association with AzureFirewallSubnet
   - Ensure on-premises can handle additional internet traffic
   - Validate default route (0.0.0.0/0) is pointing to VirtualNetworkGateway

5. **Azure Arc Connectivity Issues**
   - **Public Connectivity**: Verify `hub_firewall_arc_rules = true` if using firewall
   - **Private Endpoints**: Check private DNS zone configuration and VNet links
   - **DNS Resolution**: Ensure Arc service names resolve to correct endpoints
   - **Firewall Rules**: Verify Azure Arc firewall rules are properly configured

6. **Explicit Proxy Issues**
   - **Port Configuration**: Verify HTTP/HTTPS proxy ports are correctly configured
   - **Client Configuration**: Ensure clients are configured to use proxy endpoints
   - **TLS Inspection**: Check if TLS inspection is properly configured for HTTPS traffic

7. **Azure Monitor AMPLS Issues**
   - **Private Endpoint Connectivity**: Verify private endpoints are properly configured
   - **DNS Resolution**: Check private DNS zones resolve to correct private IPs
   - **Workspace Configuration**: Ensure Log Analytics workspace is linked to private link scope
   - **Agent Configuration**: Verify Arc agents are configured to use private endpoints

### Diagnostic Commands

```bash
# On NVA
sudo vtysh -c "show bgp summary"
sudo vtysh -c "show ip route bgp"
ip route show
systemctl status frr

# Azure CLI
az network vnet-gateway list-bgp-peer-status --name vgw-er-linklandingzone-prod --resource-group rg-linklandingzone-prod
az network routeserver peering list-learned-routes --routeserver rs-linklandingzone-prod --resource-group rg-linklandingzone-prod --name bgp-nva-linklandingzone-prod

# Force Tunneling Diagnostics
az network route-table show --name rt-firewall-linklandingzone-prod --resource-group rg-linklandingzone-prod
az network route-table route list --route-table-name rt-firewall-linklandingzone-prod --resource-group rg-linklandingzone-prod
az network nic show-effective-route-table --name <vm-nic-name> --resource-group rg-linklandingzone-prod

# Azure Arc Diagnostics
# Check firewall policy rules for Azure Arc
az network firewall policy rule-collection-group show \
  --policy-name afwp-linklandingzone-prod \
  --resource-group rg-linklandingzone-prod \
  --name azure-arc-connectivity

# Check private DNS zones for Azure Arc (if using private endpoints)
az network private-dns zone show \
  --resource-group rg-linklandingzone-prod \
  --name privatelink.guestconfiguration.azure.com

az network private-dns zone show \
  --resource-group rg-linklandingzone-prod \
  --name privatelink.his.hybridcompute.azure-automation.net

az network private-dns zone show \
  --resource-group rg-linklandingzone-prod \
  --name privatelink.dp.kubernetesconfiguration.azure.com

# Check VNet links for private DNS zones
az network private-dns link vnet list \
  --resource-group rg-linklandingzone-prod \
  --zone-name privatelink.guestconfiguration.azure.com

# Verify firewall explicit proxy configuration
az network firewall policy show \
  --name afwp-linklandingzone-prod \
  --resource-group rg-linklandingzone-prod \
  --query "explicitProxy"

# Check firewall logs for Arc traffic (requires Log Analytics workspace)
az monitor log-analytics query \
  --workspace <workspace-id> \
  --analytics-query "AzureDiagnostics | where Category == 'AzureFirewallApplicationRule' | where msg_s contains 'guestconfiguration' or msg_s contains 'hybridcompute'"

# Azure Monitor AMPLS Diagnostics
# Check Log Analytics workspace
az monitor log-analytics workspace show \
  --resource-group rg-linklandingzone-prod \
  --workspace-name law-linklandingzone-prod

# Check Azure Monitor Private Link Scope
az monitor private-link-scope show \
  --resource-group rg-linklandingzone-prod \
  --scope-name ampls-linklandingzone-prod

# Check private endpoint for monitoring
az network private-endpoint show \
  --resource-group rg-linklandingzone-prod \
  --name pe-monitor-linklandingzone-prod

# Check private DNS zones for monitoring
az network private-dns zone show \
  --resource-group rg-linklandingzone-prod \
  --name privatelink.monitor.azure.com

az network private-dns zone show \
  --resource-group rg-linklandingzone-prod \
  --name privatelink.oms.opinsights.azure.com

# Test DNS resolution for monitoring endpoints
nslookup <region>.oms.opinsights.azure.com
nslookup <region>.ods.opinsights.azure.com
```

## Security Considerations

1. **NSG Rules**: Implement least-privilege access
2. **Firewall Rules**: Regularly review and update rules
3. **VM Security**: Keep NVA updated and patched
4. **Key Management**: Rotate passwords and keys regularly
5. **Monitoring**: Enable logging and monitoring for all components
6. **Network Isolation**: Linux NVA uses private IP only for enhanced security - access via Azure Bastion or private connectivity

## Cost Optimization

1. **Gateway SKU**: Use appropriate SKU for bandwidth needs
2. **Firewall SKU**: Consider Basic SKU for non-production
3. **VM Size**: Right-size NVA based on traffic requirements
4. **ExpressRoute**: Choose appropriate bandwidth tier

## Resources Created

This template creates the following Azure resources:

- 1 Resource Group
- 1-2 Virtual Networks (Hub + Non-Gen if enabled)
- 6-9 Subnets (Hub: 6-8 if Bastion and/or Squid enabled, Non-Gen: 2 if enabled)
- 1 ExpressRoute Gateway
- 1 ExpressRoute Circuit
- 1-2 Azure Firewalls + Policies (Hub + Non-Gen if enabled)
- 1 Azure Route Server (optional)
- 1 Linux NVA VM (optional)
- 1 Linux Squid Proxy VM (optional)
- 1 Azure Bastion (optional)
- 3-6 Public IPs (ExpressRoute Gateway, Hub Firewall [if force tunneling disabled], Hub Firewall Management, Non-Gen Firewall [if enabled], Route Server, Bastion - depending on optional components)
- 1-2 Network Security Groups (Hub + Squid if enabled)
- 3-5 Route Tables (Gateway subnet, Hub Firewall subnet [if force tunneling enabled], Squid subnet [if enabled], Non-Gen routing via peering)
- VNet Peering connections (if Non-Gen VNet enabled)
- Multiple BGP connections and peerings

### Azure Arc Resources (Optional)
When Azure Arc features are enabled, additional resources are created:

- **Azure Firewall Policy Rule Collection Group** (if `hub_firewall_arc_rules = true`)
  - Comprehensive network and application rules for Azure Arc connectivity
  - Support for Arc agent, Guest Configuration, Hybrid Compute, and extension services
  
- **Private DNS Zones** (if `deploy_arc_private_endpoint = true`)
  - `privatelink.guestconfiguration.azure.com` - Guest Configuration service
  - `privatelink.his.hybridcompute.azure-automation.net` - Hybrid Compute service
  - `privatelink.dp.kubernetesconfiguration.azure.com` - Download service
  
- **VNet Links for Private DNS Zones** (if `deploy_arc_private_endpoint = true`)
  - Links private DNS zones to Hub VNet for name resolution
  - Enables private endpoint connectivity for Azure Arc services

### Azure Monitor AMPLS Resources (Optional)
When Azure Monitor Private Link Scope is enabled, additional resources are created:

- **Log Analytics Workspace** (if `deploy_azure_monitor_private_link_scope = true`)
  - Centralized logging and monitoring for Arc servers
  - Configurable retention period (30-730 days)
  - Selectable pricing tier for cost optimization

- **Azure Monitor Private Link Scope** (if `deploy_azure_monitor_private_link_scope = true`)
  - Security boundary for monitoring services
  - Links Log Analytics workspace for secure access

- **Private Endpoints for Monitoring** (if `deploy_azure_monitor_private_link_scope = true`)
  - Secure connectivity to Azure Monitor services
  - Private endpoint in hub firewall subnet

- **Private DNS Zones for Monitoring** (if `deploy_azure_monitor_private_link_scope = true`)
  - `privatelink.monitor.azure.com` - Azure Monitor API
  - `privatelink.oms.opinsights.azure.com` - Log Analytics operations
  - `privatelink.ods.opinsights.azure.com` - Data collection
  - `privatelink.agentsvc.azure-automation.net` - Agent services
  - `privatelink.blob.core.windows.net` - Storage for monitoring data

- **VNet Links for Monitor DNS Zones** (if `deploy_azure_monitor_private_link_scope = true`)
  - Links monitoring DNS zones to Hub VNet
  - Enables name resolution for monitoring endpoints

### Hub Firewall Advanced Features (Optional)
When advanced firewall features are enabled:

- **Explicit Proxy Configuration** (if `hub_firewall_explicit_proxy = true`)
  - HTTP proxy endpoint on configurable port (default: 8080)
  - HTTPS proxy endpoint on configurable port (default: 8443)
  - Enhanced web traffic filtering capabilities
  - Internal access via Azure Firewall private IP

- **Explicit Proxy NAT Rules** (if `hub_firewall_explicit_proxy_nat = true`)
  - NAT rules for external access to proxy ports
  - Allows external clients to use Azure Firewall as proxy
  - Maps public IP proxy ports to internal firewall proxy services
  - Enables branch office and remote client proxy access
  - **External Access URLs**:
    - HTTP: `http://<firewall-public-ip>:8080`
    - HTTPS: `http://<firewall-public-ip>:8443`
  - **Security Note**: Consider restricting source networks in production

- Various network interfaces and associations

## Support

For issues and questions:

1. Check the troubleshooting section
2. Review Azure documentation
3. Check Terraform provider documentation
4. Submit issues to the repository

## License

This project is licensed under the MIT License - see the LICENSE file for details.
