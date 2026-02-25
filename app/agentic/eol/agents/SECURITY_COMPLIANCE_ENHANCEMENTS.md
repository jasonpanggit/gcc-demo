# SecurityComplianceAgent - Azure Resource Compliance Audit Enhancements

## Overview

The SecurityComplianceAgent has been enhanced with infrastructure-level Azure resource configuration audit capabilities. This enhancement adds resource-level compliance checks for network security, private endpoints, encryption, and public access.

## New Features

### 1. Network Security Compliance
- **Subnet NSG Association**: Validates all subnets have Network Security Groups
- **Internet Outbound Deny**: Checks NSG rules deny outbound internet by default
- **Firewall Routing**: Ensures route tables direct internet traffic through Azure Firewall

### 2. Private Endpoint Compliance
- **Storage Accounts**: Validates storage accounts use private endpoints
- **Key Vaults**: Checks Key Vaults use private endpoints
- **SQL Servers**: Validates SQL servers use private endpoints

### 3. Encryption Compliance
- **Storage Encryption**: Validates encryption at rest for storage accounts
- **SQL TDE**: Checks SQL databases have Transparent Data Encryption enabled

### 4. Public Access Compliance
- **Storage Public Access**: Validates storage accounts have public blob access disabled

## New Actions

The agent now supports the following additional actions:

```python
# Network compliance audit
result = await agent.handle_request({
    "action": "audit_network",
    "resource_group": "prod-rg"
})

# Private endpoint compliance audit
result = await agent.handle_request({
    "action": "audit_private_endpoints",
    "resource_group": "prod-rg"
})

# Encryption compliance audit
result = await agent.handle_request({
    "action": "audit_encryption",
    "resource_group": "prod-rg"
})

# Public access compliance audit
result = await agent.handle_request({
    "action": "audit_public_access",
    "resource_group": "prod-rg"
})

# Full Azure resource compliance audit (runs all phases in parallel)
result = await agent.handle_request({
    "action": "audit_azure_resources",
    "resource_group": "prod-rg"
})
```

## Response Format

All audit actions return a consistent response format:

```json
{
  "status": "success",
  "workflow_id": "network-audit-1234567890.123",
  "audit": {
    "type": "network",
    "scope": "prod-rg",
    "compliance_percentage": 75.5,
    "resources_checked": {
      "virtual_networks": 3,
      "subnets": 12,
      "network_security_groups": 8,
      "route_tables": 4
    },
    "violations": {
      "total": 5,
      "by_severity": {
        "critical": 0,
        "high": 2,
        "medium": 2,
        "low": 1,
        "informational": 0
      },
      "details": [
        {
          "rule": "subnets_require_nsg",
          "severity": "high",
          "resource_type": "subnet",
          "resource_id": "/subscriptions/.../subnets/subnet1",
          "resource_name": "vnet1/subnet1",
          "resource_group": "prod-rg",
          "violation": "Subnet does not have an NSG associated",
          "recommendation": "Associate an NSG with subnet subnet1"
        }
      ]
    },
    "timestamp": "2026-02-25T12:34:56.789Z"
  }
}
```

## Compliance Rules

### Network Rules
- `subnets_require_nsg` (high): All subnets must have NSGs
- `deny_internet_outbound` (medium): NSG rules should deny outbound internet
- `require_route_to_firewall` (high): Internet traffic must route through firewall

### Private Endpoint Rules
- `storage_private_endpoints` (high): Storage accounts require private endpoints
- `keyvault_private_endpoints` (high): Key Vaults require private endpoints
- `sql_private_endpoints` (medium): SQL servers require private endpoints

### Encryption Rules
- `storage_encryption_at_rest` (critical): Storage accounts must encrypt data at rest
- `sql_tde_enabled` (critical): SQL databases must have TDE enabled

### Public Access Rules
- `storage_disable_public_access` (high): Storage accounts should disable public blob access

## Severity Levels

| Severity | Priority | Score Impact | SLA Hours |
|----------|----------|--------------|-----------|
| Critical | 1 | -30 | 4 |
| High | 2 | -20 | 24 |
| Medium | 3 | -10 | 72 |
| Low | 4 | -5 | 168 |
| Informational | 5 | -1 | 720 |

## Query Strategy

The agent uses the **Azure CLI Executor** MCP client for querying resources:

- VNets: `az network vnet list`
- NSGs: `az network nsg list`
- NSG Rules: `az network nsg rule list`
- Route Tables: `az network route-table list`
- Private Endpoints: `az network private-endpoint list`
- Storage Accounts: `az storage account list`
- Key Vaults: `az keyvault list`
- SQL Servers: `az sql server list`

All responses are parsed from JSON and processed to identify violations.

## Integration with SRE Orchestrator

The SecurityComplianceAgent is already registered with the SRE orchestrator. Keyword routing automatically directs queries to this agent for:

- "security", "secure score", "vulnerability", "compliance", "policy"
- "network compliance", "private endpoint", "resource compliance"
- "azure compliance audit", "configuration audit"

Example orchestrator queries:

```python
# Via SRE orchestrator
result = await sre_orchestrator.execute({
    "query": "Audit network compliance for prod-rg",
    "context": {"resource_group": "prod-rg"}
})

# Via direct API call
curl -X POST http://localhost:8000/api/sre-orchestrator/execute \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Run a compliance audit on Azure resources in prod-rg",
    "context": {"resource_group": "prod-rg"}
  }'
```

## Testing

Comprehensive unit tests are provided in `tests/test_security_compliance_agent.py`:

```bash
# Run SecurityComplianceAgent tests
cd app/agentic/eol
pytest tests/test_security_compliance_agent.py -v

# Run with coverage
pytest tests/test_security_compliance_agent.py --cov=agents.security_compliance_agent -v
```

Test coverage includes:
- Agent initialization and rule definitions
- New action registration
- Violation categorization by severity
- Compliance status determination
- Mocked Azure CLI responses for all audit actions
- Backward compatibility with existing actions

## Backward Compatibility

All existing SecurityComplianceAgent actions remain fully functional:
- `scan_security`
- `check_compliance`
- `assess_vulnerabilities`
- `policy_check`
- `recommendations`
- `full`

No breaking changes were introduced. The enhancement is purely additive.

## Implementation Details

- **Lines of code added**: ~925 lines
  - Rule definitions: ~90 lines
  - Azure CLI query helpers: ~200 lines
  - Action handlers: ~650 lines
- **Modified files**: 1 (`security_compliance_agent.py`)
- **New test files**: 1 (`test_security_compliance_agent.py`)
- **No orchestrator changes required**: Agent was already registered

## Future Enhancements (Out of Scope)

- User-configurable rules via API
- Custom rule definitions in Cosmos DB
- Automated remediation triggers
- Compliance trend tracking over time
- Integration with Azure Policy for enforcement
- Dedicated API router for direct access
- HTML/PDF compliance report generation

## Version History

- **v2.0** (2026-02-25): Initial Azure resource compliance audit enhancement
  - Added network security compliance checks
  - Added private endpoint compliance checks
  - Added encryption compliance checks
  - Added public access compliance checks
  - Added comprehensive audit workflow

## Author

Enhanced by Claude Sonnet 4.5 (2026-02-25)

## References

- Plan document: `.claude/projects/.../plan.md`
- Implementation: `agents/security_compliance_agent.py`
- Tests: `tests/test_security_compliance_agent.py`
- Base agent: `agents/base_sre_agent.py`
