# ============================================================================
# FIREWALL MODULE
# ============================================================================
# This module manages Azure Firewall and related resources

# ============================================================================
# AZURE FIREWALL PUBLIC IP
# ============================================================================

resource "azurerm_public_ip" "pip_afw_hub" {
  count               = var.deploy_hub_vnet && var.deploy_hub_firewall ? 1 : 0
  name                = "pip-afw-${var.project_name}-${var.environment}"
  location            = var.location
  resource_group_name = var.resource_group_name
  allocation_method   = "Static"
  sku                 = "Standard"

  tags = var.tags

  depends_on = [
    var.firewall_subnet_id
  ]
}

# ============================================================================
# AZURE FIREWALL POLICY
# ============================================================================

resource "azurerm_firewall_policy" "afwp_hub" {
  count               = var.deploy_hub_vnet && var.deploy_hub_firewall ? 1 : 0
  name                = "afwp-${var.project_name}-${var.environment}"
  resource_group_name = var.resource_group_name
  location            = var.location

  # DNS Proxy Configuration
  dynamic "dns" {
    for_each = var.hub_firewall_dns_proxy_enabled ? [1] : []
    content {
      proxy_enabled = true
    }
  }

  # Explicit Proxy Configuration (when enabled)
  dynamic "explicit_proxy" {
    for_each = var.hub_firewall_explicit_proxy ? [1] : []
    content {
      enabled         = true
      http_port       = var.hub_firewall_explicit_proxy_http_port
      https_port      = var.hub_firewall_explicit_proxy_https_port
      enable_pac_file = false
    }
  }

  tags = var.tags
}

# ============================================================================
# AZURE FIREWALL POLICY RULE COLLECTION GROUP
# ============================================================================

# Azure Firewall Policy Rule Collection Group for Azure Arc
resource "azurerm_firewall_policy_rule_collection_group" "afwprcg_azure_arc_rules" {
  count              = var.deploy_hub_vnet && var.deploy_hub_firewall && var.hub_firewall_arc_rules ? 1 : 0
  name               = "azure-arc-connectivity"
  firewall_policy_id = azurerm_firewall_policy.afwp_hub[0].id
  priority           = 1000

  # Network Rules for Azure Arc Agent
  network_rule_collection {
    name     = "azure-arc-network-rules"
    priority = 1100
    action   = "Allow"

    # Azure Arc agent core connectivity
    rule {
      name                  = "azure-arc-agent-core"
      protocols             = ["TCP"]
      source_addresses      = ["*"]
      destination_addresses = ["AzureCloud"]
      destination_ports     = ["443"]
    }

    # Azure Resource Manager
    rule {
      name                  = "azure-resource-manager"
      protocols             = ["TCP"]
      source_addresses      = ["*"]
      destination_addresses = ["AzureResourceManager"]
      destination_ports     = ["443"]
    }

    # Azure Active Directory
    rule {
      name                  = "azure-active-directory"
      protocols             = ["TCP"]
      source_addresses      = ["*"]
      destination_addresses = ["AzureActiveDirectory"]
      destination_ports     = ["443"]
    }

    # Azure Monitor (Log Analytics) - Enhanced for AMA
    rule {
      name                  = "azure-monitor-enhanced"
      protocols             = ["TCP"]
      source_addresses      = ["*"]
      destination_addresses = ["AzureMonitor"]
      destination_ports     = ["443", "80"]
    }

    # Data Collection Endpoints for Azure Monitor Agent
    rule {
      name                  = "azure-monitor-data-collection"
      protocols             = ["TCP"]
      source_addresses      = ["*"]
      destination_addresses = ["AzureCloud.AustraliaEast"]
      destination_ports     = ["443"]
    }

    # Guest Configuration service
    rule {
      name                  = "guest-configuration"
      protocols             = ["TCP"]
      source_addresses      = ["*"]
      destination_addresses = ["GuestAndHybridManagement"]
      destination_ports     = ["443"]
    }

    # Azure Arc Infrastructure
    rule {
      name                  = "azure-arc-infrastructure"
      protocols             = ["TCP"]
      source_addresses      = ["*"]
      destination_addresses = ["AzureArcInfrastructure"]
      destination_ports     = ["443"]
    }

    # Azure Storage (for extensions and downloads)
    rule {
      name                  = "azure-storage"
      protocols             = ["TCP"]
      source_addresses      = ["*"]
      destination_addresses = ["Storage"]
      destination_ports     = ["443"]
    }

    # Azure Traffic Manager
    rule {
      name                  = "azure-traffic-manager"
      protocols             = ["TCP"]
      source_addresses      = ["*"]
      destination_addresses = ["AzureTrafficManager"]
      destination_ports     = ["443"]
    }
  }

  # Application Rules for Azure Arc Agent
  application_rule_collection {
    name     = "azure-arc-application-rules"
    priority = 1200
    action   = "Allow"

    # Azure Arc authentication and tokens
    rule {
      name = "azure-arc-authentication"
      protocols {
        type = "Https"
        port = 443
      }
      source_addresses = ["*"]
      destination_fqdns = [
        "login.microsoftonline.com",
        "*.login.microsoft.com",
        "login.windows.net",
        "pas.windows.net"
      ]
    }

    # Azure Resource Manager endpoints
    rule {
      name = "azure-resource-manager-endpoints"
      protocols {
        type = "Https"
        port = 443
      }
      source_addresses = ["*"]
      destination_fqdns = [
        "management.azure.com"
      ]
    }

    # Azure Arc agent download and updates
    rule {
      name = "azure-arc-agent-download"
      protocols {
        type = "Https"
        port = 443
      }
      source_addresses = ["*"]
      destination_fqdns = [
        "download.microsoft.com",
        "packages.microsoft.com",
        "aka.ms",
        "gbl.his.arc.azure.com"
      ]
    }

    # Azure Arc configuration and metadata
    rule {
      name = "azure-arc-configuration"
      protocols {
        type = "Https"
        port = 443
      }
      source_addresses = ["*"]
      destination_fqdns = [
        "*.his.arc.azure.com",
        "*.guestconfiguration.azure.com",
        "gbl.his.arc.azure.com",
        "*.his.hybridcompute.azure-automation.net"
      ]
    }

    # Azure Instance Metadata Service and Notification Services
    rule {
      name = "azure-instance-metadata"
      protocols {
        type = "Https"
        port = 443
      }
      source_addresses = ["*"]
      destination_fqdns = [
        "*.his.hybridcompute.azure-automation.net",
        "*.agentsvc.azure-automation.net",
        "guestnotificationservice.azure.com",
        "*.guestnotificationservice.azure.com"
      ]
    }

    # Azure Service Bus (for notifications)
    rule {
      name = "azure-servicebus-notifications"
      protocols {
        type = "Https"
        port = 443
      }
      source_addresses = ["*"]
      destination_fqdns = [
        "*.servicebus.windows.net"
      ]
    }

    # Guest Configuration service endpoints
    rule {
      name = "guest-config-endpoints"
      protocols {
        type = "Https"
        port = 443
      }
      source_addresses = ["*"]
      destination_fqdns = [
        "*.guestconfiguration.azure.com",
        "*.guestnotificationservice.azure.com",
        "oaasguestnotificationservice.trafficmanager.net"
      ]
    }

    # Azure Blob Storage for extensions
    rule {
      name = "azure-blob-storage"
      protocols {
        type = "Https"
        port = 443
      }
      source_addresses = ["*"]
      destination_fqdns = [
        "*.blob.core.windows.net"
      ]
    }

    # Windows Admin Center (if using)
    rule {
      name = "windows-admin-center"
      protocols {
        type = "Https"
        port = 443
      }
      source_addresses = ["*"]
      destination_fqdns = [
        "*.waconazure.com"
      ]
    }

    # SQL Server enabled by Azure Arc
    rule {
      name = "azure-arc-sql-data-services"
      protocols {
        type = "Https"
        port = 443
      }
      source_addresses = ["*"]
      destination_fqdns = [
        "*.australiaeast.arcdataservices.com"
      ]
    }

    # Extended Security Updates (ESU) endpoints
    rule {
      name = "azure-arc-esu"
      protocols {
        type = "Http"
        port = 80
      }
      protocols {
        type = "Https"
        port = 443
      }
      source_addresses = ["*"]
      destination_fqdns = [
        "www.microsoft.com",
        "dls.microsoft.com"
      ]
    }

    # Azure Arc Kubernetes and Container Registry (if needed)
    rule {
      name = "azure-arc-kubernetes"
      protocols {
        type = "Https"
        port = 443
      }
      source_addresses = ["*"]
      destination_fqdns = [
        "mcr.microsoft.com",
        "*.data.mcr.microsoft.com",
        "azweus2shared.blob.core.windows.net"
      ]
    }

    # Azure Connected Machine Agent Updates and Telemetry
    rule {
      name = "azure-arc-agent-updates"
      protocols {
        type = "Https"
        port = 443
      }
      source_addresses = ["*"]
      destination_fqdns = [
        "dc.applicationinsights.microsoft.com",
        "dc.applicationinsights.azure.com",
        "dc.services.visualstudio.com"
      ]
    }

    # Azure Monitor Agent (AMA) and Data Collection Endpoints
    rule {
      name = "azure-monitor-agent-endpoints"
      protocols {
        type = "Https"
        port = 443
      }
      source_addresses = ["*"]
      destination_fqdns = [
        "global.handler.control.monitor.azure.com",
        "*.handler.control.monitor.azure.com",
        "*.ingest.monitor.azure.com",
        "*.metrics.ingest.monitor.azure.com",
        "*.ods.opinsights.azure.com",
        "*.oms.opinsights.azure.com",
        "scadvisorcontent.blob.core.windows.net",
        "scadvisorservice.accesscontrol.windows.net"
      ]
    }

    # Azure Monitor Private Link and Data Collection Rules
    rule {
      name = "azure-monitor-private-link"
      protocols {
        type = "Https"
        port = 443
      }
      source_addresses = ["*"]
      destination_fqdns = [
        "*.monitor.azure.com",
        "api.loganalytics.io",
        "*.api.loganalytics.io"
      ]
    }
  }

  # Microsoft security and telemetry endpoints (events + Defender for Endpoint)
  application_rule_collection {
    name     = "microsoft-security-telemetry"
    priority = 1250
    action   = "Allow"

    # Telemetry ingestion endpoints
    rule {
      name = "allow-events-data-microsoft"
      protocols {
        type = "Https"
        port = 443
      }
      source_addresses = ["*"]
      destination_fqdns = [
        "*.events.data.microsoft.com"
      ]
    }

    # Microsoft Defender for Endpoint portal/API
    rule {
      name = "allow-endpoint-security-microsoft"
      protocols {
        type = "Https"
        port = 443
      }
      source_addresses = ["*"]
      destination_fqdns = [
        "endpoint.security.microsoft.com"
      ]
    }
  }
}

# Agentic App comprehensive firewall rules for App Service and multi-agent EOL analysis
resource "azurerm_firewall_policy_rule_collection_group" "afwprcg_agentic_rules" {
  count              = var.deploy_nongen_vnet && var.deploy_nongen_firewall && var.nongen_firewall_agentic_rules ? 1 : 0
  name               = "agentic-egress"
  firewall_policy_id = azurerm_firewall_policy.afwp_nongen[0].id
  priority           = 1300

  # Application rules for agentic app requirements
  application_rule_collection {
    name     = "agentic-core-egress"
    priority = 100
    action   = "Allow"

    # EndOfLife.date API - primary EOL data source
    rule {
      name = "endoflife-date"
      protocols {
        type = "Https"
        port = 443
      }
      source_addresses = ["*"]
      destination_fqdns = [
        "endoflife.date",
        "*.endoflife.date"
      ]
    }

    # Azure core services - authentication and management
    rule {
      name = "azure-core"
      protocols {
        type = "Https"
        port = 443
      }
      source_addresses = ["*"]
      destination_fqdns = [
        "login.microsoftonline.com",
        "management.azure.com"
      ]
    }

    # Python PyPI package installation - critical for App Service deployments
    rule {
      name = "python-pypi"
      protocols {
        type = "Https"
        port = 443
      }
      source_addresses = ["*"]
      destination_fqdns = [
        "pypi.org",
        "*.pypi.org",
        "files.pythonhosted.org",
        "*.files.pythonhosted.org"
      ]
    }

    # Azure App Service management and deployment
    rule {
      name = "azure-appservice"
      protocols {
        type = "Https"
        port = 443
      }
      source_addresses = ["*"]
      destination_fqdns = [
        "*.azurewebsites.net",
        "*.scm.azurewebsites.net",
        "*.appservice.azure.com"
      ]
    }

    # Microsoft vendor EOL information sources
    rule {
      name = "microsoft-vendor"
      protocols {
        type = "Https"
        port = 443
      }
      source_addresses = ["*"]
      destination_fqdns = [
        "learn.microsoft.com",
        "docs.microsoft.com",
        "support.microsoft.com",
        "www.microsoft.com",
        "techcommunity.microsoft.com"
      ]
    }

    # Red Hat and Ubuntu vendor EOL information sources
    rule {
      name = "linux-vendors"
      protocols {
        type = "Https"
        port = 443
      }
      source_addresses = ["*"]
      destination_fqdns = [
        "access.redhat.com",
        "www.redhat.com",
        "ubuntu.com",
        "wiki.ubuntu.com",
        "canonical.com",
        "*.canonical.com"
      ]
    }

    # Azure Monitor and Application Insights
    rule {
      name = "azure-monitoring"
      protocols {
        type = "Https"
        port = 443
      }
      source_addresses = ["*"]
      destination_fqdns = [
        "dc.applicationinsights.microsoft.com",
        "dc.applicationinsights.azure.com",
        "dc.services.visualstudio.com",
        "*.ods.opinsights.azure.com",
        "*.oms.opinsights.azure.com",
        "*.monitoring.azure.com",
        "api.loganalytics.io",
        "*.api.loganalytics.io"
      ]
    }

    # Agent Framework dependencies - GitHub and NPM repositories
    rule {
      name = "agent-framework-deps"
      protocols {
        type = "Https"
        port = 443
      }
      source_addresses = ["*"]
      destination_fqdns = [
        "github.com",
        "*.github.com",
        "raw.githubusercontent.com",
        "*.githubusercontent.com",
        "api.github.com",
        "registry.npmjs.org",
        "*.registry.npmjs.org"
      ]
    }

    # SMTP Email Services - Gmail and other providers
    rule {
      name = "smtp-email-services"
      protocols {
        type = "Https"
        port = 443
      }
      source_addresses = ["*"]
      destination_fqdns = [
        "smtp.gmail.com",
        "smtp-mail.outlook.com",
        "smtp.mail.yahoo.com",
        "smtp.office365.com"
      ]
    }
  }

  # Microsoft Oryx SDK CDN - Critical for Azure App Service Python builds
  application_rule_collection {
    name     = "agentic-oryx-egress"
    priority = 150
    action   = "Allow"

    rule {
      name = "microsoft-oryx-sdk"
      protocols {
        type = "Https"
        port = 443
      }
      source_addresses = ["*"]
      destination_fqdns = [
        "oryxsdks-cdn.azureedge.net",
        "*.azureedge.net",
        "oryx-cdn.microsoft.io",
        "*.oryx-cdn.microsoft.io"
      ]
    }
  }
}

# SMTP Network Rules for Email Services
resource "azurerm_firewall_policy_rule_collection_group" "afwprcg_smtp_network_rules" {
  count              = var.deploy_nongen_vnet && var.deploy_nongen_firewall && var.nongen_firewall_agentic_rules ? 1 : 0
  name               = "agentic-smtp-network"
  firewall_policy_id = azurerm_firewall_policy.afwp_nongen[0].id
  priority           = 1350

  # Network rules for SMTP TCP traffic
  network_rule_collection {
    name     = "smtp-tcp-egress"
    priority = 100
    action   = "Allow"

    # SMTP TCP traffic for Gmail and other providers
    # smtp.gmail.com resolves to different IPs hence Azure Firewall has a problem with using FQDNs
    rule {
      name                  = "allow-smtp-tcp"
      protocols             = ["TCP"]
      source_addresses      = ["*"]
      destination_addresses = ["*"]
      destination_ports     = ["587", "465", "25"]
    }
  }
}

# ============================================================================
# CONTAINER APPS FIREWALL RULES
# ============================================================================

# Container Apps comprehensive firewall rules for multi-container deployment
resource "azurerm_firewall_policy_rule_collection_group" "afwprcg_container_apps_rules" {
  count              = var.deploy_nongen_vnet && var.deploy_nongen_firewall && var.nongen_firewall_container_apps_rules ? 1 : 0
  name               = "container-apps-egress"
  firewall_policy_id = azurerm_firewall_policy.afwp_nongen[0].id
  priority           = 1400

  # Application rules for Container Apps environment and container images
  application_rule_collection {
    name     = "container-apps-core"
    priority = 100
    action   = "Allow"

    # Azure Container Registry - pull container images
    rule {
      name = "acr-pull"
      protocols {
        type = "Https"
        port = 443
      }
      source_addresses = ["*"]
      destination_fqdns = [
        "*.azurecr.io",
        "*.blob.core.windows.net"
      ]
    }

    # Microsoft Container Registry - Azure MCP sidecar image
    rule {
      name = "mcr-pull"
      protocols {
        type = "Https"
        port = 443
      }
      source_addresses = ["*"]
      destination_fqdns = [
        "mcr.microsoft.com",
        "*.mcr.microsoft.com",
        "*.data.mcr.microsoft.com"
      ]
    }

    # Azure Container Apps control plane
    rule {
      name = "container-apps-control"
      protocols {
        type = "Https"
        port = 443
      }
      source_addresses = ["*"]
      destination_fqdns = [
        "*.azurecontainerapps.io",
        "*.containerapp.io"
      ]
    }

    # Azure Resource Manager and Authentication
    rule {
      name = "azure-management"
      protocols {
        type = "Https"
        port = 443
      }
      source_addresses = ["*"]
      destination_fqdns = [
        "management.azure.com",
        "login.microsoftonline.com",
        "*.login.microsoft.com"
      ]
    }

    # Azure OpenAI and Cognitive Services
    rule {
      name = "azure-openai"
      protocols {
        type = "Https"
        port = 443
      }
      source_addresses = ["*"]
      destination_fqdns = [
        "*.openai.azure.com",
        "*.cognitiveservices.azure.com"
      ]
    }

    # Azure Cosmos DB
    rule {
      name = "cosmos-db"
      protocols {
        type = "Https"
        port = 443
      }
      source_addresses = ["*"]
      destination_fqdns = [
        "*.documents.azure.com"
      ]
    }

    # Azure Monitor and Application Insights
    rule {
      name = "azure-monitor"
      protocols {
        type = "Https"
        port = 443
      }
      source_addresses = ["*"]
      destination_fqdns = [
        "*.monitor.azure.com",
        "*.applicationinsights.azure.com",
        "*.ods.opinsights.azure.com",
        "*.oms.opinsights.azure.com"
      ]
    }

    # EndOfLife.date API - EOL data source
    rule {
      name = "endoflife-api"
      protocols {
        type = "Https"
        port = 443
      }
      source_addresses = ["*"]
      destination_fqdns = [
        "endoflife.date",
        "*.endoflife.date"
      ]
    }
  }

  # Network rules for Container Apps control plane
  network_rule_collection {
    name     = "container-apps-network"
    priority = 200
    action   = "Allow"

    # Azure services network connectivity
    rule {
      name                  = "azure-services"
      protocols             = ["TCP"]
      source_addresses      = ["*"]
      destination_addresses = ["AzureCloud"]
      destination_ports     = ["443"]
    }
  }
}

# ============================================================================
# AZURE FIREWALL NAT RULES FOR EXPLICIT PROXY
# ============================================================================

# Azure Firewall Policy Rule Collection Group for Explicit Proxy NAT Rules
resource "azurerm_firewall_policy_rule_collection_group" "afwprcg_explicit_proxy_nat" {
  count              = var.deploy_hub_vnet && var.deploy_hub_firewall && var.hub_firewall_explicit_proxy && var.hub_firewall_explicit_proxy_nat ? 1 : 0
  name               = "explicit-proxy-nat-rules"
  firewall_policy_id = azurerm_firewall_policy.afwp_hub[0].id
  priority           = 500

  # NAT Rules for Explicit Proxy
  nat_rule_collection {
    name     = "explicit-proxy-nat"
    priority = 510
    action   = "Dnat"

    # NAT rule for HTTP proxy port
    rule {
      name                = "proxy-http-nat"
      protocols           = ["TCP"]
      source_addresses    = ["*"]
      destination_address = azurerm_public_ip.pip_afw_hub[0].ip_address
      destination_ports   = [tostring(var.hub_firewall_explicit_proxy_http_port)]
      translated_address  = azurerm_firewall.afw_hub[0].ip_configuration[0].private_ip_address
      translated_port     = var.hub_firewall_explicit_proxy_http_port
    }

    # NAT rule for HTTPS proxy port
    rule {
      name                = "proxy-https-nat"
      protocols           = ["TCP"]
      source_addresses    = ["*"]
      destination_address = azurerm_public_ip.pip_afw_hub[0].ip_address
      destination_ports   = [tostring(var.hub_firewall_explicit_proxy_https_port)]
      translated_address  = azurerm_firewall.afw_hub[0].ip_configuration[0].private_ip_address
      translated_port     = var.hub_firewall_explicit_proxy_https_port
    }
  }
}

# ============================================================================
# AZURE FIREWALL
# ============================================================================

resource "azurerm_firewall" "afw_hub" {
  count               = var.deploy_hub_vnet && var.deploy_hub_firewall ? 1 : 0
  name                = "afw-${var.project_name}-${var.environment}"
  location            = var.location
  resource_group_name = var.resource_group_name
  sku_name            = "AZFW_VNet"
  sku_tier            = "Standard"
  firewall_policy_id  = azurerm_firewall_policy.afwp_hub[0].id

  # Azure Firewall always requires at least one public IP
  ip_configuration {
    name                 = "configuration"
    subnet_id            = var.firewall_subnet_id
    public_ip_address_id = azurerm_public_ip.pip_afw_hub[0].id
  }

  tags = var.tags
}

# ============================================================================
# NON-GEN FIREWALL RESOURCES
# ============================================================================

# Non-Gen Public IP for Azure Firewall
resource "azurerm_public_ip" "pip_afw_nongen" {
  count               = var.deploy_nongen_vnet && var.deploy_nongen_firewall ? 1 : 0
  name                = "pip-afw-nongen-${var.project_name}-${var.environment}"
  location            = var.location
  resource_group_name = var.resource_group_name
  allocation_method   = "Static"
  sku                 = "Standard"

  tags = {
    Environment = var.environment
    Project     = var.project_name
    Purpose     = "Non-Gen Firewall"
  }
}

# Non-Gen Azure Firewall Policy
resource "azurerm_firewall_policy" "afwp_nongen" {
  count               = var.deploy_nongen_vnet && var.deploy_nongen_firewall ? 1 : 0
  name                = "afwp-nongen-${var.project_name}-${var.environment}"
  resource_group_name = var.resource_group_name
  location            = var.location

  # DNS Proxy Configuration
  dynamic "dns" {
    for_each = var.nongen_firewall_dns_proxy_enabled ? [1] : []
    content {
      proxy_enabled = true
    }
  }

  # Threat Intel Mode - Alert to match deployed configuration
  threat_intelligence_mode = "Alert"

  tags = {
    Environment = var.environment
    Project     = var.project_name
    Purpose     = "Non-Gen Firewall Policy"
  }
}

# ============================================================================
# AZURE VIRTUAL DESKTOP FIREWALL RULES (Non-Gen)
# ============================================================================

# Azure Virtual Desktop Firewall Policy Rule Collection Group for Non-Gen
resource "azurerm_firewall_policy_rule_collection_group" "afwprcg_avd_rules_nongen" {
  count              = var.deploy_nongen_vnet && var.deploy_nongen_firewall && var.nongen_firewall_avd_rules ? 1 : 0
  name               = "azure-virtual-desktop-connectivity"
  firewall_policy_id = azurerm_firewall_policy.afwp_nongen[0].id
  priority           = 2000

  # Network Rules for Azure Virtual Desktop
  network_rule_collection {
    name     = "avd-network-rules"
    priority = 2100
    action   = "Allow"

    # AVD Service Traffic - Core connectivity for session hosts
    rule {
      name                  = "avd-service-traffic"
      protocols             = ["TCP"]
      source_addresses      = ["*"]
      destination_addresses = ["WindowsVirtualDesktop"]
      destination_ports     = ["443"]
    }

    # Azure Instance Metadata Service
    rule {
      name                  = "azure-instance-metadata"
      protocols             = ["TCP"]
      source_addresses      = ["*"]
      destination_addresses = ["169.254.169.254"]
      destination_ports     = ["80"]
    }

    # Windows Activation (KMS)
    rule {
      name                  = "windows-activation"
      protocols             = ["TCP"]
      source_addresses      = ["*"]
      destination_addresses = ["23.102.135.246"]
      destination_ports     = ["1688"]
    }

    # Azure AD Authentication
    rule {
      name                  = "azure-ad-auth"
      protocols             = ["TCP"]
      source_addresses      = ["*"]
      destination_addresses = ["AzureActiveDirectory"]
      destination_ports     = ["443", "80"]
    }

    # Azure Resource Manager for management operations
    rule {
      name                  = "azure-resource-manager"
      protocols             = ["TCP"]
      source_addresses      = ["*"]
      destination_addresses = ["AzureResourceManager"]
      destination_ports     = ["443"]
    }

    # Azure Monitor for diagnostics and monitoring
    rule {
      name                  = "azure-monitor"
      protocols             = ["TCP"]
      source_addresses      = ["*"]
      destination_addresses = ["AzureMonitor"]
      destination_ports     = ["443"]
    }

    # Azure Storage for profile containers and logs
    rule {
      name                  = "azure-storage"
      protocols             = ["TCP"]
      source_addresses      = ["*"]
      destination_addresses = ["Storage"]
      destination_ports     = ["443", "445"]
    }

    # Azure Key Vault for secrets and certificates
    rule {
      name                  = "azure-key-vault"
      protocols             = ["TCP"]
      source_addresses      = ["*"]
      destination_addresses = ["AzureKeyVault"]
      destination_ports     = ["443"]
    }

    # Time synchronization
    rule {
      name                  = "ntp-time-sync"
      protocols             = ["UDP"]
      source_addresses      = ["*"]
      destination_addresses = ["*"]
      destination_ports     = ["123"]
    }

    # DNS resolution
    rule {
      name                  = "dns-resolution"
      protocols             = ["UDP"]
      source_addresses      = ["*"]
      destination_addresses = ["*"]
      destination_ports     = ["53"]
    }
  }

  # Application Rules for Azure Virtual Desktop
  application_rule_collection {
    name     = "avd-application-rules"
    priority = 2200
    action   = "Allow"

    # AVD Web Client and RDP Broker connectivity
    rule {
      name = "avd-web-client"
      protocols {
        type = "Https"
        port = 443
      }
      source_addresses = ["*"]
      destination_fqdns = [
        "rdweb.wvd.microsoft.com",
        "rdbroker.wvd.microsoft.com",
        "rdgateway.wvd.microsoft.com"
      ]
    }

    # Windows Update and Microsoft services
    rule {
      name = "windows-update"
      protocols {
        type = "Https"
        port = 443
      }
      protocols {
        type = "Http"
        port = 80
      }
      source_addresses = ["*"]
      destination_fqdns = [
        "*.windowsupdate.microsoft.com",
        "*.update.microsoft.com",
        "*.microsoft.com",
        "download.microsoft.com",
        "*.download.windowsupdate.com"
      ]
    }

    # Microsoft Certificate Revocation Lists
    rule {
      name = "certificate-revocation"
      protocols {
        type = "Http"
        port = 80
      }
      source_addresses = ["*"]
      destination_fqdns = [
        "*.crl.microsoft.com",
        "*.ocsp.microsoft.com",
        "crl.microsoft.com"
      ]
    }

    # Microsoft Store and Office connectivity
    rule {
      name = "microsoft-store-office"
      protocols {
        type = "Https"
        port = 443
      }
      source_addresses = ["*"]
      destination_fqdns = [
        "*.microsoft.com",
        "*.microsoftonline.com",
        "*.office.com",
        "*.office365.com",
        "*.live.com"
      ]
    }

    # FSLogix and profile container services
    rule {
      name = "fslogix-services"
      protocols {
        type = "Https"
        port = 443
      }
      source_addresses = ["*"]
      destination_fqdns = [
        "*.blob.core.windows.net",
        "*.file.core.windows.net",
        "*.queue.core.windows.net",
        "*.table.core.windows.net"
      ]
    }

    # Azure Arc and hybrid connectivity (if enabled)
    rule {
      name = "azure-arc-hybrid"
      protocols {
        type = "Https"
        port = 443
      }
      source_addresses = ["*"]
      destination_fqdns = [
        "*.guestconfiguration.azure.com",
        "*.his.arc.azure.com",
        "*.waconazure.com"
      ]
    }

    # Microsoft Defender and security services
    rule {
      name = "microsoft-defender"
      protocols {
        type = "Https"
        port = 443
      }
      source_addresses = ["*"]
      destination_fqdns = [
        "*.wdcp.microsoft.com",
        "*.wd.microsoft.com",
        "*.defender.microsoft.com"
      ]
    }
  }
}

# ============================================================================
# AGENTIC APPLICATION FIREWALL RULES (Non-Gen)
# ============================================================================

# Agentic Egress Rules - Priority 1300 to match deployed configuration
resource "azurerm_firewall_policy_rule_collection_group" "afwprcg_agentic_egress" {
  count              = var.deploy_nongen_vnet && var.deploy_nongen_firewall && var.deploy_agentic_app ? 1 : 0
  name               = "agentic-egress"
  firewall_policy_id = azurerm_firewall_policy.afwp_nongen[0].id
  priority           = 1300

  # Core Agentic Application Rules
  application_rule_collection {
    name     = "agentic-core-egress"
    priority = 100
    action   = "Allow"

    # End of Life API
    rule {
      name = "endoflife-date"
      protocols {
        type = "Https"
        port = 443
      }
      source_addresses = ["*"]
      destination_fqdns = [
        "endoflife.date",
        "*.endoflife.date"
      ]
    }

    # Azure Core Services
    rule {
      name = "azure-core"
      protocols {
        type = "Https"
        port = 443
      }
      source_addresses = ["*"]
      destination_fqdns = [
        "login.microsoftonline.com",
        "management.azure.com"
      ]
    }

    # Python PyPI
    rule {
      name = "python-pypi"
      protocols {
        type = "Https"
        port = 443
      }
      source_addresses = ["*"]
      destination_fqdns = [
        "pypi.org",
        "*.pypi.org",
        "files.pythonhosted.org",
        "*.files.pythonhosted.org"
      ]
    }

    # Azure App Service
    rule {
      name = "azure-appservice"
      protocols {
        type = "Https"
        port = 443
      }
      source_addresses = ["*"]
      destination_fqdns = [
        "*.azurewebsites.net",
        "*.scm.azurewebsites.net",
        "*.appservice.azure.com"
      ]
    }

    # Microsoft Vendor Sites
    rule {
      name = "microsoft-vendor"
      protocols {
        type = "Https"
        port = 443
      }
      source_addresses = ["*"]
      destination_fqdns = [
        "learn.microsoft.com",
        "docs.microsoft.com",
        "support.microsoft.com",
        "www.microsoft.com",
        "techcommunity.microsoft.com"
      ]
    }

    # Linux Vendors
    rule {
      name = "linux-vendors"
      protocols {
        type = "Https"
        port = 443
      }
      source_addresses = ["*"]
      destination_fqdns = [
        "access.redhat.com",
        "www.redhat.com",
        "ubuntu.com",
        "wiki.ubuntu.com",
        "canonical.com",
        "*.canonical.com"
      ]
    }

    # Azure Monitoring Services
    rule {
      name = "azure-monitoring"
      protocols {
        type = "Https"
        port = 443
      }
      source_addresses = ["*"]
      destination_fqdns = [
        "dc.applicationinsights.microsoft.com",
        "dc.applicationinsights.azure.com",
        "dc.services.visualstudio.com",
        "*.ods.opinsights.azure.com",
        "*.oms.opinsights.azure.com",
        "*.monitoring.azure.com",
        "api.loganalytics.io",
        "*.api.loganalytics.io"
      ]
    }

    # Agent Framework development dependencies
    rule {
      name = "agent-framework-deps"
      protocols {
        type = "Https"
        port = 443
      }
      source_addresses = ["*"]
      destination_fqdns = [
        "github.com",
        "*.github.com",
        "raw.githubusercontent.com",
        "*.githubusercontent.com",
        "api.github.com",
        "registry.npmjs.org",
        "*.registry.npmjs.org"
      ]
    }

    # Testing and Development APIs
    rule {
      name = "testing-apis"
      protocols {
        type = "Https"
        port = 443
      }
      source_addresses = ["*"]
      destination_fqdns = [
        "httpbin.org",
        "*.httpbin.org"
      ]
    }
  }

  # Microsoft Oryx SDK Rules
  application_rule_collection {
    name     = "agentic-oryx-egress"
    priority = 150
    action   = "Allow"

    rule {
      name = "microsoft-oryx-sdk"
      protocols {
        type = "Https"
        port = 443
      }
      source_addresses = ["*"]
      destination_fqdns = [
        "oryxsdks-cdn.azureedge.net",
        "*.azureedge.net",
        "oryx-cdn.microsoft.io",
        "*.oryx-cdn.microsoft.io"
      ]
    }
  }

  # SMTP Egress (placeholder with dummy rule - matches deployed config structure)
  application_rule_collection {
    name     = "agentic-smtp-egress"
    priority = 160
    action   = "Allow"
    
    # Placeholder rule - empty in actual deployment but required by Terraform
    rule {
      name = "placeholder-rule"
      protocols {
        type = "Https"
        port = 443
      }
      source_addresses = ["127.0.0.1"]  # Localhost only - effectively disabled
      destination_fqdns = ["localhost"]
    }
  }
}

# Agentic SMTP Network Rules - Priority 1350 to match deployed configuration
resource "azurerm_firewall_policy_rule_collection_group" "afwprcg_agentic_smtp_network" {
  count              = var.deploy_nongen_vnet && var.deploy_nongen_firewall && var.deploy_agentic_app ? 1 : 0
  name               = "agentic-smtp-network"
  firewall_policy_id = azurerm_firewall_policy.afwp_nongen[0].id
  priority           = 1350

  # SMTP Network Rules
  network_rule_collection {
    name     = "smtp-tcp-egress"
    priority = 100
    action   = "Allow"

    # SMTP over TLS (port 587)
    rule {
      name                  = "allow-smtp-tcp"
      protocols             = ["TCP"]
      source_addresses      = ["*"]
      destination_fqdns     = [
        "smtp.gmail.com",
        "smtp-mail.outlook.com",
        "smtp.mail.yahoo.com",
        "smtp.office365.com"
      ]
      destination_ports     = ["587"]
    }

    # SMTP SSL (port 465)
    rule {
      name                  = "allow-smtp-ssl-tcp"
      protocols             = ["TCP"]
      source_addresses      = ["*"]
      destination_fqdns     = [
        "smtp.gmail.com",
        "smtp-mail.outlook.com",
        "smtp.mail.yahoo.com",
        "smtp.office365.com"
      ]
      destination_ports     = ["465"]
    }

    # SMTP to any IP (catch-all for SMTP services)
    rule {
      name                  = "allow-smtp-ip-tcp"
      protocols             = ["TCP"]
      source_addresses      = ["*"]
      destination_addresses = ["*"]
      destination_ports     = ["587"]
    }
  }
}

# Non-Gen Azure Firewall
resource "azurerm_firewall" "afw_nongen" {
  count               = var.deploy_nongen_vnet && var.deploy_nongen_firewall ? 1 : 0
  name                = "afw-nongen-${var.project_name}-${var.environment}"
  location            = var.location
  resource_group_name = var.resource_group_name
  sku_name            = "AZFW_VNet"
  sku_tier            = "Standard"
  firewall_policy_id  = azurerm_firewall_policy.afwp_nongen[0].id

  ip_configuration {
    name                 = "configuration"
    subnet_id            = var.nongen_firewall_subnet_id
    public_ip_address_id = azurerm_public_ip.pip_afw_nongen[0].id
  }

  tags = {
    Environment = var.environment
    Project     = var.project_name
    Purpose     = "Non-Gen Firewall"
  }
}

# Route Table for Non-Gen Firewall Subnet
resource "azurerm_route_table" "rt_afw_nongen" {
  count               = var.deploy_nongen_vnet && var.deploy_nongen_firewall ? 1 : 0
  name                = "rt-nongen-firewall-${var.project_name}-${var.environment}"
  location            = var.location
  resource_group_name = var.resource_group_name

  # Default route to Internet
  route {
    name           = "default-to-internet"
    address_prefix = "0.0.0.0/0"
    next_hop_type  = "Internet"
  }

  # Route on-premises traffic through hub firewall
  dynamic "route" {
    for_each = var.deploy_hub_vnet && var.deploy_hub_firewall && length(var.onprem_vnet_address_space) > 0 ? var.onprem_vnet_address_space : []
    content {
      name                   = "route-onprem-via-hub-${replace(replace(route.value, "/", "-"), ".", "-")}"
      address_prefix         = route.value
      next_hop_type          = "VirtualAppliance"
      next_hop_in_ip_address = azurerm_firewall.afw_hub[0].ip_configuration[0].private_ip_address
    }
  }

  # Route traffic back to hub VNet through hub firewall
  dynamic "route" {
    for_each = var.deploy_hub_vnet && var.deploy_hub_firewall ? var.hub_vnet_address_space : []
    content {
      name                   = "route-hub-via-hub-firewall-${replace(replace(route.value, "/", "-"), ".", "-")}"
      address_prefix         = route.value
      next_hop_type          = "VirtualAppliance"
      next_hop_in_ip_address = azurerm_firewall.afw_hub[0].ip_configuration[0].private_ip_address
    }
  }

  tags = {
    Environment = var.environment
    Project     = var.project_name
    Purpose     = "Non-Gen Firewall Routing"
  }
}

# Associate Route Table with Non-Gen Firewall Subnet
resource "azurerm_subnet_route_table_association" "srta_afw_nongen" {
  count          = var.deploy_nongen_vnet && var.deploy_nongen_firewall ? 1 : 0
  subnet_id      = var.nongen_firewall_subnet_id
  route_table_id = azurerm_route_table.rt_afw_nongen[0].id
}
