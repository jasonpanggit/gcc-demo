# Software Inventory End-of-Life Analysis

This solution provides comprehensive End-of-Life (EOL) analysis for software installed on Azure Arc-connected machines using Azure Monitor Workbooks and the endoflife.date API.

## 📋 Overview

The solution consists of:

1. **Azure Monitor Workbook** - Interactive dashboard for EOL analysis
2. **PowerShell Script** - Automated EOL checking and reporting  
3. **Deployment Script** - Easy workbook deployment to Azure

## 🏗️ Architecture

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Azure Arc     │───▶│  Log Analytics   │───▶│ Azure Monitor   │
│   Machines      │    │   Workspace      │    │   Workbook      │
│                 │    │                  │    │                 │
│ • Software      │    │ • ConfigData     │    │ • EOL Analysis  │
│   Inventory     │    │ • Telemetry      │    │ • Risk Reports  │
│ • Telemetry     │    │ • Retention      │    │ • Trends        │
└─────────────────┘    └──────────────────┘    └─────────────────┘
                                │                        │
                                ▼                        ▼
                       ┌──────────────────┐    ┌─────────────────┐
                       │   PowerShell     │    │  endoflife.date │
                       │     Script       │◄───┤      API        │
                       │                  │    │                 │
                       │ • Automated      │    │ • EOL Data      │
                       │   Reporting      │    │ • Product Info  │
                       │ • CSV/JSON/HTML  │    │ • Versions      │
                       └──────────────────┘    └─────────────────┘
```

## 🚀 Quick Start

### Prerequisites

1. **Azure Arc-connected machines** with software inventory enabled
2. **Log Analytics workspace** receiving Arc data
3. **Azure PowerShell** module installed
4. **Azure permissions** to create workbooks and query Log Analytics

### 🔄 Automated Setup (Recommended)

If you deployed this solution as part of the arc-demo Terraform scenario, you can automatically configure all settings:

```bash
# Run from the Terraform workspace root after successful deployment
./workbooks/end-of-life/post-deploy-setup.sh
```

This script will:
- ✅ Extract actual Azure subscription ID, resource group, and workspace names from Terraform outputs
- 🔧 Update all configuration files with your environment values
- 📋 Generate deployment summary and next steps
- 🚀 Prepare the solution for immediate deployment

## 📁 Solution Files

| File | Purpose | Type |
|------|---------|------|
| `README.md` | Complete solution documentation | Documentation |
| `software-inventory-eol-report.json` | Azure Monitor Workbook definition | JSON |
| `deploy-eol-solution.sh` | End-to-end deployment automation | Executable Script |
| `Deploy-SoftwareEOLWorkbook.ps1` | PowerShell workbook deployment | PowerShell |
| `Get-SoftwareEOLReport.ps1` | PowerShell EOL report generator | PowerShell |
| `post-deploy-setup.sh` | Post-Terraform configuration | Executable Script |
| `update-eol-config-from-terraform.sh` | Terraform config updater | Executable Script |

### Step 1: Deploy the Workbook

```powershell
# Deploy the workbook to Azure Monitor
.\workbooks\end-of-life\Deploy-SoftwareEOLWorkbook.ps1 `
    -WorkbookPath ".\workbooks\end-of-life\software-inventory-eol-report.json" `
    -ResourceGroupName "rg-gcc-demo" `
    -WorkbookName "Software-EOL-Report" `
    -SubscriptionId "your-subscription-id"
```

### Step 2: Configure the Workbook

1. Navigate to **Azure Monitor** > **Workbooks**
2. Find your deployed workbook: **Software-EOL-Report**
3. Open the workbook and configure parameters:
   - **Time Range**: Select data collection period
   - **Resource Group**: Filter by resource groups
   - **Machine**: Select specific machines (optional)

### Step 3: Run Automated Reports

```powershell
# Generate comprehensive EOL report
.\workbooks\end-of-life\Get-SoftwareEOLReport.ps1 `
    -WorkspaceName "log-gcc-demo" `
    -ResourceGroupName "rg-gcc-demo" `
    -SubscriptionId "your-subscription-id" `
    -OutputPath "C:\Reports\EOL-Report.csv" `
    -ExportFormat "CSV"
```

## 📊 Workbook Features

### 🎛️ Interactive Dashboard

- **Software Inventory Overview** - Total packages, machines, inventory freshness
- **Critical Software Analysis** - High-risk software requiring EOL checks  
- **EOL Status Checking** - Direct links to endoflife.date API
- **Risk Assessment** - Color-coded priority levels
- **Distribution Analysis** - Software spread across machines
- **Trend Analysis** - Inventory changes over time

### 🔍 Key Queries

The workbook includes pre-built KQL queries for:

```kusto
// Critical Software needing EOL Check
ConfigurationData
| where ConfigDataType == "Software"
| extend SoftwareName = tostring(ConfigData.SoftwareName)
| extend SoftwareVersion = tostring(ConfigData.SoftwareVersion)
| where isnotempty(SoftwareName)
| extend ProductKey = case(
    SoftwareName contains "Windows" and SoftwareName contains "Server", "windows-server",
    SoftwareName contains "SQL" and SoftwareName contains "Server", "sql-server",
    // ... more mappings
)
| summarize MachineCount = dcount(Computer) by ProductKey, SoftwareName
| extend EOL_API_URL = strcat("https://endoflife.date/api/", ProductKey, ".json")
```

### 🎨 Visualizations

- **Tiles** - Key metrics overview
- **Tables** - Detailed software listings with risk levels
- **Charts** - Trend analysis and distribution
- **Links** - Direct access to EOL API endpoints

## 🤖 PowerShell Automation

### Features

- **Comprehensive Product Mapping** - Maps 30+ common software products to EOL API
- **Intelligent Version Matching** - Finds closest version matches in API data
- **Risk Assessment** - Calculates risk levels based on EOL proximity
- **Multiple Export Formats** - CSV, JSON, and HTML reports
- **Progress Tracking** - Real-time progress for large inventories
- **Error Handling** - Graceful handling of API timeouts and errors

### Supported Software Products

The script automatically maps these products to EOL data:

| Category | Products |
|----------|----------|
| **Operating Systems** | Windows Server, Windows Client |
| **Databases** | SQL Server, MySQL, PostgreSQL, MongoDB, Redis |
| **Web Servers** | IIS, Apache, nginx |
| **Development** | .NET Framework, Java, Node.js, Python, PHP |
| **Infrastructure** | Docker, Kubernetes, VMware ESXi |
| **Office Suite** | Microsoft Office, Exchange, SharePoint |
| **Browsers** | Chrome, Firefox, Edge, Safari |
| **Other** | Elasticsearch, Terraform, Ansible |

### Sample Output

```
📈 EOL Report Summary
==============================
🔴 Critical Risk: 5
🟡 High Risk: 12
⚫ End of Life: 3
✅ Supported: 45
📊 Total Products: 65

⚠️  Top Risk Products:
SoftwareName              RiskLevel  EOLStatus    MachineCount  DaysUntilEOL
------------              ---------  ---------    ------------  ------------
Windows Server 2012 R2   Critical   End of Life  25           -180
SQL Server 2014          Critical   End of Life  8            -45
Exchange Server 2016      High       Supported    12           90
```

## 📅 Implementation Timeline

### Week 1: Foundation
- [ ] Deploy workbook to Azure Monitor
- [ ] Configure Log Analytics workspace access
- [ ] Test basic software inventory queries
- [ ] Validate Arc agent software collection

### Week 2: Analysis
- [ ] Run initial EOL assessment
- [ ] Identify critical and high-risk software
- [ ] Map additional custom software products
- [ ] Create baseline inventory report

### Week 3: Automation
- [ ] Schedule PowerShell script execution
- [ ] Set up automated reporting (weekly/monthly)
- [ ] Configure alerts for new EOL software
- [ ] Establish remediation processes

### Week 4: Optimization
- [ ] Fine-tune risk assessment criteria
- [ ] Add custom software product mappings
- [ ] Optimize query performance
- [ ] Train team on workbook usage

## 🔧 Configuration Options

### Workbook Parameters

```json
{
  "TimeRange": "Last 7 days",
  "ResourceGroup": "All or specific RGs",
  "Machine": "All or specific machines"
}
```

### Script Parameters

```powershell
# Extensive configuration options
-DaysBack 30                    # Look back period
-ExportFormat "HTML"            # Output format
-OutputPath "C:\Reports\"       # Export location
```

### Custom Product Mapping

Add custom software products to the mapping:

```powershell
$productMapping = @{
    "Your Custom Software" = "custom-product-key"
    "Internal Application" = "internal-app"
}
```

## 🔒 Security Considerations

### Required Permissions

- **Log Analytics Reader** - Query software inventory data
- **Workbook Contributor** - Deploy and modify workbooks  
- **Arc Machine Reader** - Access Arc machine information

### Data Privacy

- Software inventory data remains in your Log Analytics workspace
- EOL API calls are made to public endoflife.date service
- No sensitive data is transmitted to external services

### Network Requirements

- Outbound HTTPS access to `endoflife.date` (443/TCP)
- Azure Management API access for authentication
- Log Analytics workspace connectivity

## 📊 Monitoring & Maintenance

### Regular Tasks

| Frequency | Task | Description |
|-----------|------|-------------|
| **Daily** | Monitor Alerts | Check for new EOL software |
| **Weekly** | Review Reports | Analyze high-risk software |
| **Monthly** | Update Mappings | Add new software products |
| **Quarterly** | Assess Coverage | Verify Arc agent deployment |

### Performance Optimization

```kusto
// Optimize queries for large datasets
ConfigurationData
| where TimeGenerated >= ago(7d)  // Limit time range
| where ConfigDataType == "Software"
| summarize by Computer, SoftwareName  // Reduce data volume
| take 1000  // Limit results for testing
```

### Troubleshooting

#### Common Issues

1. **No Data in Workbook**
   - Verify Arc agents have software inventory enabled
   - Check Log Analytics workspace permissions
   - Confirm ConfigurationData table exists

2. **API Timeouts**
   - Reduce batch size in PowerShell script
   - Add retry logic for failed API calls
   - Consider API rate limiting

3. **Slow Query Performance**
   - Optimize time range parameters
   - Use specific machine filters
   - Consider data retention policies

## 🚀 Advanced Features

### Custom Alerts

Create Log Analytics alerts for EOL software:

```kusto
ConfigurationData
| where TimeGenerated >= ago(1d)
| where ConfigDataType == "Software"
| where SoftwareName contains "Windows Server 2012"
| summarize Machines = dcount(Computer)
| where Machines > 0
```

### Integration Options

- **Azure Logic Apps** - Automated workflows
- **Power BI** - Executive dashboards  
- **ServiceNow** - Ticket creation
- **Teams** - Alert notifications

### API Extensions

Extend the solution with additional EOL data sources:

```powershell
# Add custom EOL API sources
$customAPIs = @{
    "vendor-name" = "https://api.vendor.com/eol"
    "internal-products" = "https://internal.company.com/eol"
}
```

## 📚 Resources

### Documentation Links

- [Azure Arc Software Inventory](https://docs.microsoft.com/azure/azure-arc/servers/manage-software-inventory)
- [Azure Monitor Workbooks](https://docs.microsoft.com/azure/azure-monitor/visualize/workbooks-overview)
- [endoflife.date API](https://endoflife.date/docs/api)
- [Log Analytics KQL Reference](https://docs.microsoft.com/azure/data-explorer/kusto/query/)

### API Reference

The endoflife.date API provides comprehensive EOL data:

```bash
# Get all products
curl https://endoflife.date/api/all.json

# Get specific product
curl https://endoflife.date/api/windows-server.json

# Get single cycle
curl https://endoflife.date/api/windows-server/2019.json
```

### Sample API Response

```json
{
  "cycle": "2019",
  "release": "2018-11-13",
  "eol": "2029-01-09",
  "latest": "10.0.17763.5458",
  "support": "2024-01-09",
  "lts": true
}
```

## 🤝 Contributing

### Adding New Software Products

1. Identify the product name pattern in your inventory
2. Find the corresponding product key on endoflife.date
3. Add mapping to the PowerShell script
4. Test with sample data
5. Update documentation

### Improving Queries

1. Optimize for performance with large datasets
2. Add new visualization types
3. Include additional risk factors
4. Enhance filtering capabilities

## 📞 Support

### Getting Help

1. **Documentation** - Check this README and inline comments
2. **Issues** - Create issues for bugs or feature requests
3. **Community** - Share improvements and best practices

### Known Limitations

- EOL data availability depends on endoflife.date API coverage
- Software name matching requires manual mapping for new products
- Large inventories may require query optimization
- API rate limits may affect bulk processing

---

**🎯 Start your software EOL management journey today and keep your infrastructure secure and compliant!**
