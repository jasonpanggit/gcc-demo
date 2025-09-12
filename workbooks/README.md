# Azure Monitor Workbooks

This directory contains Azure Monitor Workbooks and related automation tools for various monitoring and analysis scenarios.

## 📁 Directory Structure

```
workbooks/
├── end-of-life/                          # Software End-of-Life Analysis
│   ├── software-inventory-eol-report.json   # Azure Monitor Workbook
│   ├── Get-SoftwareEOLReport.ps1           # PowerShell automation script
│   ├── Deploy-SoftwareEOLWorkbook.ps1      # Workbook deployment script  
│   ├── deploy-eol-solution.sh              # Complete solution deployment
│   └── README.md                           # Detailed documentation
└── README.md                               # This file
```

## 🚀 Available Solutions

### 📊 Software End-of-Life Analysis
**Location**: `end-of-life/`

Comprehensive solution for analyzing software inventory from Azure Arc-connected machines and checking End-of-Life status using the endoflife.date API.

**Features:**
- Interactive Azure Monitor Workbook
- Automated EOL checking via PowerShell
- Risk assessment and prioritization
- Multiple export formats (CSV, JSON, HTML)
- Real-time EOL data integration

**Automated Setup (Recommended):**
```bash
# Run after successful arc-demo Terraform deployment
./workbooks/end-of-life/post-deploy-setup.sh
```

**Quick Start:**
```bash
cd workbooks/end-of-life/
chmod +x deploy-eol-solution.sh
./deploy-eol-solution.sh
```

**Manual Deployment:**
```powershell
# Deploy workbook
.\workbooks\end-of-life\Deploy-SoftwareEOLWorkbook.ps1 `
    -WorkbookPath ".\workbooks\end-of-life\software-inventory-eol-report.json" `
    -ResourceGroupName "rg-monitoring" `
    -WorkbookName "Software-EOL-Report" `
    -SubscriptionId "your-subscription-id"

# Generate report
.\workbooks\end-of-life\Get-SoftwareEOLReport.ps1 `
    -WorkspaceName "log-analytics-workspace" `
    -ResourceGroupName "rg-monitoring" `
    -SubscriptionId "your-subscription-id"
```

## 🔧 Prerequisites

- **Azure Arc** agents with software inventory enabled
- **Log Analytics workspace** receiving Arc data
- **Azure PowerShell** module installed
- **Azure permissions** for creating workbooks and querying Log Analytics

## 📚 Documentation

Each solution directory contains comprehensive documentation including:
- Architecture diagrams
- Implementation guides
- Configuration options
- Troubleshooting guides
- Best practices

## 🤝 Contributing

To add new workbook solutions:

1. Create a new directory under `workbooks/`
2. Include the workbook JSON file
3. Add automation scripts (PowerShell/Bash)
4. Create comprehensive README documentation
5. Update this main README with the new solution

## 🔗 Related Resources

- [Azure Monitor Workbooks Documentation](https://docs.microsoft.com/azure/azure-monitor/visualize/workbooks-overview)
- [Azure Arc Documentation](https://docs.microsoft.com/azure/azure-arc/)
- [Log Analytics KQL Reference](https://docs.microsoft.com/azure/data-explorer/kusto/query/)
- [Azure PowerShell Documentation](https://docs.microsoft.com/powershell/azure/)

---

💡 **Tip**: Start with the end-of-life solution to establish baseline software inventory management and risk assessment capabilities.
