# SRE UI Testing Improvements

## Summary

This document captures the journey from shallow DOM testing to comprehensive E2E testing, and the critical production bug discovered through proper testing methodology.

---

## Initial State: Shallow DOM Tests

### What Was Tested
- **File**: `tests/ui/pages/test_sre_assistant.py`
- **Approach**: Playwright tests checking for DOM element presence
- **Results**: ✅ 16/16 tests passing
- **Coverage**: UI elements only

### What Was NOT Tested
- ❌ Actual button functionality
- ❌ API endpoint responses
- ❌ Agent processing
- ❌ Error handling
- ❌ User experience flow

### False Confidence
The passing tests gave false confidence that the SRE Assistant was working, when in reality **every single query was failing in production**.

---

## E2E Testing Approach

### What Changed
Created true end-to-end tests that:
1. **Click** UI buttons (not just check they exist)
2. **Wait** for actual responses (not just DOM elements)
3. **Validate** content (keywords, structure, data quality)
4. **Test** error scenarios
5. **Verify** conversation flows

### New Test Files Created

#### 1. `tests/ui/e2e/test_sre_assistant_e2e.py`
Comprehensive E2E tests including:
- Quick prompt interaction with response validation
- Custom query input and response
- Agent communication panel visibility
- Clear chat functionality
- Multiple prompts in sequence
- Error handling for invalid queries
- Response structure validation

#### 2. `tests/ui/e2e/test_sre_debug.py`
Debug test to investigate issues:
- Captures HTML state
- Logs message counts and classes
- Takes screenshots
- Detects error messages
- Monitors input field state

---

## Critical Bug Discovered

### What E2E Tests Revealed

**Test Run Output**:
```
[DEBUG] Error message: Assistant
7:47:21 PM
Request failed
```

### Root Cause Analysis

**Step 1**: E2E test showed "Request failed" error
```python
# Test waited for agent response
self.page.wait_for_selector(".chat-message.agent", timeout=60000)
# Result: TimeoutError - no response after 60 seconds
```

**Step 2**: Backend logs investigation
```bash
az containerapp logs show --name azure-agentic-platform-vnet --resource-group rg-gcc-demo
```

**Found**:
```
ERROR: MCPHost.from_config() failed:
[Errno 2] No such file or directory: '/app/config/mcp_servers.yaml'
```

**Step 3**: Local file check
```bash
ls -la app/agentic/eol/config/
# File exists: mcp_servers.yaml (2656 bytes)
```

**Step 4**: Dockerfile analysis
```dockerfile
# Line 82-90: Files being copied
COPY api ./api
COPY agents ./agents
COPY utils ./utils
COPY mcp_servers ./mcp_servers
COPY static ./static
COPY templates ./templates
# ❌ MISSING: COPY config ./config
```

### Impact

**Severity**: **CRITICAL** 🔴

- **Affected Feature**: Entire SRE Assistant UI
- **User Impact**: 100% of SRE queries failing
- **Error Message**: Generic "Request failed" (poor UX)
- **Detection**: Only through E2E testing
- **Duration**: Unknown (shallow tests gave false confidence)

---

## The Fix

### Code Change

**File**: `deploy/Dockerfile`

**Added Line 86**:
```dockerfile
COPY config ./config
```

**Full Context**:
```dockerfile
# Copy application code from parent directory
COPY api ./api
COPY agents ./agents
COPY utils ./utils
COPY mcp_servers ./mcp_servers
COPY config ./config          # ← ADDED
COPY static ./static
COPY templates ./templates
COPY main.py ./
COPY *.py ./
COPY startup.txt ./
```

### Deployment

```bash
cd deploy
./deploy-container.sh
```

**Image**: `acreolggcdemo.azurecr.io/eol-app:v6b76e60`

---

## Test Comparison

### Before: Shallow Tests
```python
def test_sre_quick_prompts_categories(self):
    """Test quick prompts categories are present."""
    expect(self.page.get_by_text("Try asking…")).to_be_visible()
    expect(self.page.get_by_text("Health & Availability")).to_be_visible()
    # ✅ PASSES - but doesn't prove functionality works
```

### After: E2E Tests
```python
def test_quick_prompt_health_check_interaction(self):
    """Test clicking health check prompt and receiving response."""
    # Click the prompt
    health_prompt = self.page.get_by_role(
        "button", name="What is the health of my container apps?"
    )
    health_prompt.click()

    # Wait for user message
    self.page.wait_for_selector(".chat-message.user", timeout=5000)

    # Wait for agent response
    self.page.wait_for_selector(".chat-message.agent", timeout=60000)

    # Validate response content
    agent_messages = self.page.locator(".chat-message.agent")
    response_text = agent_messages.first.inner_text().lower()
    assert any(
        keyword in response_text
        for keyword in ["container", "app", "health", "status", "running"]
    )
    # ❌ FAILS - reveals production bug
```

---

## Lessons Learned

### 1. DOM Presence ≠ Functionality
Just because a button exists doesn't mean clicking it works.

### 2. Speed Indicates Depth
- Shallow tests: ~55 seconds for 16 tests
- E2E tests: ~65 seconds for 1 test (with 60s timeout)
- If tests run too fast, they're probably not testing enough

### 3. Production Parity Matters
Tests should run against:
- ✅ Local environment
- ✅ Remote deployment
- ✅ Production-like configuration

### 4. Error Messages Should Be Specific
"Request failed" is not helpful. Better error would be:
```
"Configuration error: MCP server config file not found.
Please contact support with error code: CONFIG_MISSING_001"
```

### 5. Test Pyramid Was Inverted
We had:
- 16 UI presence tests (too many shallow tests)
- 0 E2E functional tests (missing critical layer)

Should be:
- Many unit tests (fast, isolated)
- Some integration tests (API endpoints)
- Few E2E tests (critical user flows)

---

## Recommendations

### 1. Always Include E2E Tests for Critical Paths
Especially for:
- User authentication flows
- Primary feature interactions
- Payment/transaction flows
- Data submission forms

### 2. Use Playwright MCP for Richer Testing
The Playwright MCP server can provide:
- Browser screenshots
- Network request inspection
- Console log capture
- Performance metrics

### 3. Test Against Remote Deployments
```bash
BASE_URL=https://your-app.azurecontainerapps.io pytest tests/ui/e2e/
```

### 4. Monitor Real User Behavior
- Add application insights
- Track error rates
- Monitor API response times
- Alert on failures

### 5. Improve Error Messages
User-facing errors should:
- Be specific about what failed
- Suggest next steps
- Include error codes for support
- Log detailed info server-side

---

## Test Execution

### Run Shallow Tests (Quick Validation)
```bash
cd tests
pytest ui/pages/test_sre_assistant.py -v
```

### Run E2E Tests (Comprehensive Validation)
```bash
cd tests
pytest ui/e2e/test_sre_assistant_e2e.py -v
```

### Run Against Remote
```bash
BASE_URL=https://azure-agentic-platform-vnet.jollywater-179e4f4a.australiaeast.azurecontainerapps.io \
pytest ui/e2e/test_sre_assistant_e2e.py -v
```

### Debug Mode
```bash
pytest ui/e2e/test_sre_debug.py -v -s
# Check /tmp/sre_debug.png for screenshot
```

---

## Conclusion

**The Right Way to Test**:
1. ✅ Unit tests for logic
2. ✅ Integration tests for APIs
3. ✅ E2E tests for user flows
4. ✅ Test against real deployments
5. ✅ Validate actual functionality, not just DOM presence

**This Case Study**:
- Shallow tests: 16/16 passing ✅ (false confidence)
- E2E tests: Immediately revealed critical bug 🔴
- Root cause: Missing config file in deployment
- Impact: 100% of SRE queries failing in production
- Detection method: Only through E2E testing

**Value of E2E Testing**: Immeasurable - caught a production-breaking bug that shallow tests completely missed.

---

**Date**: 2026-03-02
**Author**: Testing improvements based on user feedback
**Status**: Fixed and deployed (v6b76e60)
