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
