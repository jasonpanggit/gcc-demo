# MCP Tool Testing Issues

**Test Start Date:** 2026-02-13
**Last Updated:** 2026-02-13

---

## Tools Tested

| MCP Server | Tools Identified | Tools Tested | Pass | Fail |
|-----------|------------------|--------------|------|------|
| Azure MCP | ~85 | 0 | 0 | 0 |
| Azure CLI Executor | 1 | 0 | 0 | 0 |
| OS EOL | 2 | 0 | 0 | 0 |
| Inventory | 7 | 0 | 0 | 0 |
| Monitor | TBD | 0 | 0 | 0 |
| SRE | 24 | 0 | 0 | 0 |
| **Total** | **~137** | **6** | **0** | **1** | **0** | **0** | **0** |

---


## Open Issues

### Critical Issues
*(Issues that prevent core functionality)*

#### Issue #1: EOL API KeyError - 'primary_source' missing
- **Tool**: `/api/eol` endpoint
- **Severity**: Critical
- **Description**: KeyError: 'primary_source' when calling /api/eol?name=Windows+Server+2016
- **Details**: main.py line 901 assumes eol_data["primary_source"] exists, but EOL orchestrator doesn't return this field
- **Root Cause**: Missing safe dict access with fallback
- **Fix**: Changed `eol_data["primary_source"]` to `eol_data.get("primary_source") or eol_data.get("agent_used") or "unknown"`
- **File Modified**: main.py line 901
- **Status**: ✅ FIXED - Ready for deployment
- **Detected**: 2026-02-13T12:50:09

### High Priority Issues
*(Issues affecting important features)*

*None identified yet*

### Low Priority Issues
*(Minor issues, cosmetic problems)*

*None identified*

## Fixed Issues

### Issue #1: [EXAMPLE - DELETE THIS]
- **Tool**: `azure-vm-list`
- **Severity**: High
- **Description**: Tool fails with authentication error when using Service Principal
- **Root Cause**: Missing AZURE_SP_CLIENT_SECRET environment variable
- **Fix**: Updated deploy-container.sh to include all SP credentials
- **Tested**: ✅ Verified in production on 2026-02-13
- **Status**: RESOLVED

---

## Test Status Summary

**Overall Progress**: 0%
**Test Phase**: Discovery
**Blocking Issues**: None
**Ready for Deployment**: ❌ No

### Test Coverage by Category
- **Resource Management**: 0/~30 tools tested
- **Networking**: 0/~15 tools tested
- **Compute**: 0/~10 tools tested
- **Storage**: 0/~8 tools tested
- **Monitoring**: 0/~12 tools tested
- **EOL Analysis**: 0/9 tools tested
- **Inventory**: 0/7 tools tested
- **SRE Operations**: 0/24 tools tested

### Next Steps
1. Complete tool discovery across all MCP servers
2. Begin systematic testing starting with Azure MCP tools
3. Document all issues found with reproduction steps
4. Prioritize fixes based on severity and user impact

---

## Testing Methodology

### Test Approach
1. **Discovery**: Identify all tools from MCP server source code
2. **Unit Testing**: Test each tool individually with valid inputs
3. **Integration Testing**: Test tool combinations and workflows
4. **Error Testing**: Test with invalid inputs and edge cases
5. **Production Testing**: Verify fixes in deployed Container App

### Issue Severity Levels
- **Critical**: Prevents deployment or breaks core functionality
- **High**: Affects important features, significant user impact
- **Medium**: Affects non-critical features, moderate impact
- **Low**: Minor issues, cosmetic problems, limited impact

### Resolution Criteria
Issues are removed from this file when:
1. Fix has been implemented and tested locally
2. Application has been redeployed to Azure Container Apps
3. Fix has been verified working in production environment
4. No regression issues detected in related functionality

---

## Notes

- All MCP servers communicate via stdio subprocess protocol
- Azure MCP uses @azure/mcp npm package (~85 tools auto-discovered)
- SRE MCP server requires Service Principal authentication
- Monitor MCP accessed via MonitorAgent sub-agent delegation pattern
- Tool metadata stored in `static/data/azure_mcp_tool_metadata.json`

**Testing Team**: mcp-testing
**Team Lead**: team-lead@mcp-testing
