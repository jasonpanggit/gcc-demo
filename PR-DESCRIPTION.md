# Pull Request: Fix Failing SRE Template Examples - Cost Analysis & Diagnostic Logging

## Summary

Implements deterministic workflows for cost analysis and diagnostic logging queries to fix SRE template examples that were failing with unhelpful "ask in MCP chat" redirects or raw Azure API errors.

## Problem Statement

**Before this PR:**
- ❌ Cost analysis queries (30-day spend, resource group breakdown, etc.) redirected users to "ask in MCP chat"
- ❌ Diagnostic logging queries failed with unclear error messages
- ❌ Users received unhelpful Log Analytics or Azure API errors when resources didn't exist
- ❌ No pre-execution validation for cost/diagnostic queries

**After this PR:**
- ✅ Cost queries execute deterministically with proper validation
- ✅ Diagnostic queries provide helpful resource examples with CLI commands
- ✅ Friendly HTML-formatted messages for missing resources/data
- ✅ Consistent with existing VM health workflow pattern

## Implementation Approach

Follows the proven **VM health deterministic workflow pattern**:

```
User Query
    ↓
Detection Method (_is_cost_analysis_query)
    ↓
Inventory Check (_discover_resources_by_type)
    ↓
    ├─→ No Resources → Friendly "No Resources" Message
    ├─→ No Data → Friendly "No Data" Message
    └─→ Data Found → Execute Tool → Format Results
```

## Changes Made

### 1. Query Detection (2 methods)
- `_is_cost_analysis_query()` - Detects 14 cost-related keywords
- `_is_diagnostic_logging_query()` - Detects 6 diagnostic-related keywords

### 2. Routing Logic
Updated `_run_via_sre_sub_agent()` to route before expensive LLM execution:
```python
if self._is_cost_analysis_query(query):
    return await self._run_cost_analysis_deterministic_workflow(...)

if self._is_diagnostic_logging_query(query):
    return await self._run_diagnostic_logging_deterministic_workflow(...)
```

### 3. Cost Analysis Workflow (6 methods)
- `_run_cost_analysis_deterministic_workflow()` - Main orchestration
- `_execute_cost_by_resource_group()` - 30-day spend by resource group
- `_execute_orphaned_resources_check()` - Find idle/orphaned resources
- `_execute_cost_recommendations()` - Azure Advisor recommendations
- `_execute_cost_anomaly_analysis()` - Detect spending anomalies
- `_extract_subscription_id()` - Parse subscription ID from resource IDs

### 4. Diagnostic Logging Workflow (2 methods)
- `_run_diagnostic_logging_deterministic_workflow()` - Main orchestration
- `_format_diagnostic_logging_examples()` - Generate CLI examples

### 5. HTML Formatting Helpers (10 methods)
- `_format_no_resources_message()` - When no resources deployed
- `_format_no_data_message()` - When data unavailable
- `_format_success_message()` - Positive outcomes
- `_format_error_message()` - Errors with tips
- `_format_info_message()` - Informational notices
- `_format_cost_analysis_results()` - Cost breakdown tables
- `_format_orphaned_resources_results()` - Orphaned resource lists
- `_format_cost_recommendations_results()` - Recommendation cards
- `_format_cost_anomaly_results()` - Anomaly tables
- `_format_diagnostic_logging_examples()` - CLI examples

### 6. Response Builder Helper (1 method)
- `_build_deterministic_response()` - Standardized response format

## Testing

### Automated Tests
✅ **9/9 tests passing** - All detection logic verified:
- 5 cost analysis queries correctly detected
- 2 diagnostic logging queries correctly detected
- 2 negative cases correctly ignored (no false positives)

### Manual Testing Checklist

**Cost Analysis Examples:**
- [ ] "What is my total Azure spend trend for the past 30 days?"
- [ ] "Show my cost breakdown by resource group"
- [ ] "Find orphaned or idle resources wasting budget"
- [ ] "What are my top Azure Advisor cost recommendations?"
- [ ] "Are there any spending anomalies this month?"

**Diagnostic Logging Example:**
- [ ] "Enable diagnostic logging on my App Service"

**Edge Cases:**
- [ ] Empty subscription (no resources deployed)
- [ ] New subscription (no cost data)
- [ ] Missing inventory access

## Code Quality

- **Syntax:** ✅ Valid Python (verified with `py_compile`)
- **Pattern:** ✅ Follows existing VM health workflow
- **Documentation:** ✅ Comprehensive docstrings
- **Error Handling:** ✅ Graceful fallbacks with user-friendly messages
- **HTML Formatting:** ✅ Bootstrap-compatible alerts and tables

## Code Statistics

- **File Modified:** `app/agentic/eol/agents/sre_orchestrator.py`
- **Lines Added:** 737
- **Lines Removed:** 2
- **Methods Added:** 20 new methods
- **Detection Keywords:** 20 total (14 cost + 6 diagnostic)

## Files Changed

```
app/agentic/eol/agents/sre_orchestrator.py | 739 ++++++++++++++++++++++++++++-
1 file changed, 737 insertions(+), 2 deletions(-)
```

## Rollback Plan

If issues arise, the changes are isolated and can be easily reverted:

1. **Disable detection:** Return `False` from detection methods
2. **Remove routing:** Comment out routing branches in `_run_via_sre_sub_agent()`
3. **Git revert:** `git revert 59f5207`

Rollback does not affect existing functionality - queries fall back to SRESubAgent.

## Future Extensibility

This pattern can be extended to other domains:

| Domain | Example Queries | New Workflow Method |
|--------|-----------------|---------------------|
| Security | "security recommendations", "vulnerability scan" | `_run_security_deterministic_workflow()` |
| Performance | "identify bottlenecks", "slow queries" | `_run_performance_deterministic_workflow()` |
| Compliance | "audit compliance status", "policy violations" | `_run_compliance_deterministic_workflow()` |

## Related Issues

Fixes failing SRE template examples:
- Cost analysis queries returning "ask in MCP chat" redirect
- Diagnostic logging queries failing with unclear errors
- Poor user experience with raw API errors

## Deployment Notes

- **Zero Breaking Changes** - All changes are additive
- **Backward Compatible** - Existing queries route through unchanged
- **No Configuration Required** - Works with existing SRE MCP server setup
- **Performance Improvement** - Avoids expensive LLM calls for deterministic queries

## Screenshots

N/A - Backend implementation only. UI testing required to verify formatted output.

## Checklist

- [x] Code follows existing patterns (VM health workflow)
- [x] All detection tests passing (9/9)
- [x] Python syntax validated
- [x] Comprehensive documentation added
- [x] Error handling implemented
- [x] HTML formatting helpers added
- [ ] Manual testing in SRE Assistant UI (pending)
- [ ] Code review completed (pending)

## Reviewers

@jasonpang - Please review and test in SRE Assistant UI

## Merge Strategy

**Recommended:** Squash and merge
- Clean commit history
- Single atomic change
- Easy to revert if needed

---

**Implementation by:** Claude Opus 4.6
**Branch:** `fix/sre-cost-diagnostic-workflows`
**Commit:** `59f5207`
**Status:** ✅ Ready for review and testing
