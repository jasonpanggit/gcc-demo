# End-of-Life Workbook Solution

Workbook and scripts for software inventory EOL analysis using Log Analytics data and endoflife.date lookups.

## Key files

- `software-inventory-eol-report.json`
- `Deploy-SoftwareEOLWorkbook.ps1`
- `Get-SoftwareEOLReport.ps1`
- `deploy-eol-solution.sh`
- `post-deploy-setup.sh`
- `update-eol-config-from-terraform.sh`

## Recommended flow

1. Deploy Terraform scenario (typically Arc or Agentic).
2. Run:

```bash
./workbooks/end-of-life/post-deploy-setup.sh
```

3. Deploy workbook/report tooling:

```bash
cd workbooks/end-of-life
./deploy-eol-solution.sh
```

## Manual PowerShell options

```powershell
.\workbooks\end-of-life\Deploy-SoftwareEOLWorkbook.ps1
.\workbooks\end-of-life\Get-SoftwareEOLReport.ps1
```

Use this folder as the source of truth for workbook JSON, KQL helpers, and deployment scripts.

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
