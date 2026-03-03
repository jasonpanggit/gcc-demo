# Debugging Tool Selection - Practical Guide

Step-by-step debugging scenarios for MCP tool selection issues in the EOL platform.
Use this guide when golden scenarios fail, users report wrong tool selection, or
after making manifest changes.

---

## Table of Contents

1. [Quick Decision Tree](#quick-decision-tree)
2. [Scenario 1: Golden Scenario Fails in CI](#scenario-1-golden-scenario-fails-in-ci)
3. [Scenario 2: User Reports Wrong Tool](#scenario-2-user-reports-wrong-tool)
4. [Scenario 3: New Tool Not Getting Selected](#scenario-3-new-tool-not-getting-selected)
5. [Scenario 4: Manifest Change Caused Regression](#scenario-4-manifest-change-caused-regression)
6. [Scenario 5: Ambiguous Query Routes Inconsistently](#scenario-5-ambiguous-query-routes-inconsistently)
7. [Scenario 6: Too Many Tools Selected](#scenario-6-too-many-tools-selected)
8. [Example Traces with Annotations](#example-traces-with-annotations)
9. [Manifest Improvement Workflow](#manifest-improvement-workflow)
10. [Tool Reference](#tool-reference)

---

## Quick Decision Tree

```
Start: Something wrong with tool selection
    │
    ├── CI golden scenario failed?
    │   └── Go to Scenario 1
    │
    ├── User says "it picked the wrong tool"?
    │   └── Go to Scenario 2
    │
    ├── Added a new tool and it's not being selected?
    │   └── Go to Scenario 3
    │
    ├── Changed a manifest and tests broke?
    │   └── Go to Scenario 4
    │
    ├── Same query gives different tools each time?
    │   └── Go to Scenario 5
    │
    └── Response is slow / too many tools?
        └── Go to Scenario 6
```

---

## Scenario 1: Golden Scenario Fails in CI

**Situation:** CI reports golden scenario failure. PR blocked.

### Step 1: Read the CI failure (30 seconds)

Look at the PR comment or Actions summary:
```
Stage 2: Golden Scenarios ❌ failure
```

### Step 2: Download diagnostic artifacts (1 minute)

1. Go to Actions tab → failed workflow run
2. Download `tool-selection-diagnostics` artifact
3. Open `selection-report.txt`

### Step 3: Find the failing query (30 seconds)

Search for `FAIL` in the text report:

```
  --- Query 3 FAIL ---
  Query:        check storage account health
  Domain:       azure_management (confidence: 0.62)
  Orchestrator: mcp
  Strategy:     fast
  Time:         5.1ms
  Tools (4):
    - storage_account_list
    - get_storage_metrics
    - azure_cli_execute_command
    - check_resource_health
  Expected tools: check_storage_health
  MISSING tools:  check_storage_health       ← THIS IS THE PROBLEM
  Active domains: azure_management, sre_health
  Relevant sources: azure, sre
```

### Step 4: Diagnose the root cause (2 minutes)

**Q: Is the expected tool in the selection at all?**
- NO → The tool's manifest metadata doesn't match the query. Fix the manifest.
- YES but wrong position → Another tool may be winning via `preferred_over`.

**Q: Is the domain correct?**
- NO → Domain classifier misrouted. Check `active_domains` for clues.
- YES → Tool retrieval within the domain isn't finding the right tool.

**Q: Is confidence low (<0.7)?**
- YES → Ambiguous query. Add more example_queries to the target tool.

In this example: `check_storage_health` is missing. The query hits `azure_management`
and `sre_health` domains, but the expected tool's manifest likely has weak metadata
for the "storage account health" phrasing.

### Step 5: Fix (2-5 minutes)

```bash
cd app/agentic/eol

# Check the tool's manifest
python -c "
from utils.tool_manifest_index import get_tool_manifest_index
idx = get_tool_manifest_index()
m = idx.get('check_storage_health')
if m:
    print(f'Source: {m.source}')
    print(f'Domains: {m.domains}')
    print(f'Tags: {m.tags}')
    print(f'Examples: {m.example_queries}')
else:
    print('Tool not found in index!')
"
```

If the tool exists but has weak metadata, improve it:
- Add `"check storage account health"` to `example_queries`
- Add `"storage"`, `"health"` to `tags`
- Ensure `domains` includes the right classification

### Step 6: Verify locally (1 minute)

```bash
# Re-trace the query
python scripts/selection_reporter.py --query "check storage account health"

# Run the specific golden scenario
pytest tests/ -k "storage_health" -m "golden" -v

# Run all golden scenarios for regressions
pytest tests/ -m "golden" -v
```

### Step 7: Push and confirm CI passes

---

## Scenario 2: User Reports Wrong Tool

**Situation:** User says "I asked for X but it did Y."

### Step 1: Get the exact query

Ask for or find the exact query text the user entered.

### Step 2: Trace the query locally

```bash
cd app/agentic/eol
python scripts/selection_reporter.py --query "the user's exact query"
```

### Step 3: Read the trace

```
  --- Query 1 ---
  Query:        restart my container app
  Domain:       sre_health (confidence: 0.78)
  Orchestrator: mcp
  Tools (3):
    - container_app_list
    - azure_cli_execute_command     ← User expected a specific restart tool
    - describe_capabilities
  Active domains: sre_health
  Relevant sources: sre, azure_cli
```

### Step 4: Identify why the wrong tool was selected

Common patterns:
- **No specific tool for the action** → Need to create a new tool or manifest
- **Correct tool exists but wasn't retrieved** → Improve manifest metadata
- **CLI fallback won over specific tool** → Add `preferred_over` to the specific tool

### Step 5: Fix and add a golden scenario

Fix the manifest, then add a golden scenario to prevent regression:

```yaml
# tests/fixtures/golden/restart_container_app.yaml
scenario:
  id: "restart-container-app"
  description: "User requests container app restart"
  category: "sre"
  priority: "high"

input:
  query: "restart my container app"

expected:
  domain: "sre_health"
  tools:
    required: ["container_app_restart"]
    forbidden: ["azure_cli_execute_command"]
```

---

## Scenario 3: New Tool Not Getting Selected

**Situation:** You added a new tool with a manifest but queries don't select it.

### Step 1: Verify the tool is in the index

```bash
cd app/agentic/eol
python -c "
from utils.tool_manifest_index import get_tool_manifest_index
idx = get_tool_manifest_index()
m = idx.get('your_new_tool_name')
if m:
    print('Found in index')
    print(f'Source: {m.source}')
    print(f'Domains: {m.domains}')
    print(f'Tags: {m.tags}')
    print(f'Examples: {m.example_queries}')
else:
    print('NOT FOUND - check manifest registration')
"
```

If not found: The manifest isn't registered in the index. Check that it's in the
correct `*_manifests.py` file and included in the `__init__.py` exports.

### Step 2: Check manifest quality

```bash
python scripts/manifest_linter.py 2>&1 | grep "your_new_tool"
python scripts/manifest_quality_scorecard.py 2>&1 | grep "your_new_tool"
```

### Step 3: Trace queries that should select it

```bash
python scripts/selection_reporter.py --query "a query that should select your tool"
```

Check:
- Is the domain correct? → If not, add the right domain to the manifest.
- Is the source in `relevant_sources`? → If not, domain→source mapping needs updating.
- Are other tools winning? → Check `conflicts_with` and `preferred_over`.

### Step 4: Improve metadata iteratively

```bash
# After each metadata change, re-trace
python scripts/selection_reporter.py --query "your query"

# Check that you haven't broken other scenarios
pytest tests/ -m "golden" -v
```

---

## Scenario 4: Manifest Change Caused Regression

**Situation:** You edited a manifest file and golden scenarios started failing.

### Step 1: Run impact analyzer

```bash
cd app/agentic/eol
python scripts/manifest_impact_analyzer.py --golden-dir tests/fixtures/golden/
```

Output shows which scenarios are at risk:

```
  Manifests changed:    1
  Tools affected:       43
  High risk:            2
  Scenarios at risk:    3

  HIGH RISK Tools:
    container_app_list (sre)
      Note: Large change: +25/-10 lines
      Scenarios: sre-container-list, sre-health-check

  Golden Scenarios at Risk:
    - sre-container-list
    - sre-health-check
    - sre-restart-container
```

### Step 2: Run the at-risk scenarios

```bash
pytest tests/ -m "golden" -k "sre_container_list or sre_health_check or sre_restart" -v
```

### Step 3: For each failure, trace the query

```bash
python scripts/selection_reporter.py --golden-dir tests/fixtures/golden/
```

### Step 4: Decide: fix the manifest or update the fixture

- If the new routing is **correct**: Update the golden scenario YAML
- If the new routing is **wrong**: Revert or adjust the manifest change

### Step 5: Verify no other regressions

```bash
pytest tests/ -m "golden" -v
python scripts/manifest_linter.py
```

---

## Scenario 5: Ambiguous Query Routes Inconsistently

**Situation:** The same or similar queries give different tool selections.

### Step 1: Trace multiple phrasings

Create a file `test_queries.txt`:
```
check health of my container apps
are my container apps healthy
container app health status
what is the health of my container apps
```

```bash
python scripts/selection_reporter.py --queries-file test_queries.txt
```

### Step 2: Compare traces

Look for:
- Different `domain` classifications across similar queries
- Different `confidence` levels
- Different `tools_selected` sets

### Step 3: Find the divergence point

If domains differ: The keyword patterns match differently for each phrasing.
Add more consistent patterns to `QueryPatterns`.

If tools differ within the same domain: The retrieval ranking varies.
Add more `example_queries` to the target tool covering all phrasings.

### Step 4: Add golden scenarios for each phrasing

Capture the expected routing for all common phrasings as golden scenarios
to prevent future regression.

---

## Scenario 6: Too Many Tools Selected

**Situation:** Queries return 10+ tools, causing slow orchestrator responses.

### Step 1: Trace the query

```bash
python scripts/selection_reporter.py --query "the problematic query"
```

### Step 2: Check tool count and sources

```
  Tools (15):
    - tool_a
    - tool_b
    - ...
  Active domains: sre_health, azure_management, network
  Relevant sources: sre, azure, network
```

**Multiple active domains** is the most common cause of tool explosion.

### Step 3: Narrow the routing

Options:
1. **Add `conflicts_with`** to competing tools so the router can disambiguate
2. **Add `preferred_over`** to let one tool win over similar ones
3. **Narrow `domains`** on tools that are too broadly classified
4. **Add deterministic override** for high-frequency queries (last resort)

---

## Example Traces with Annotations

### Trace 1: Successful routing (ideal case)

```json
{
  "query": "list all virtual machines in my subscription",
  // Domain correctly identified as azure_management
  "domain": "azure_management",
  "confidence": 0.92,              // High confidence = reliable routing
  "strategy": "fast",              // Keyword match was sufficient
  "orchestrator": "mcp",
  "tools_selected": [
    "virtual_machines"             // Exactly the right tool
  ],
  "tool_count": 1,                 // Minimal tool set = fast execution
  "classification_time_ms": 2.1,   // Very fast routing
  "active_domains": ["azure_management"],
  "relevant_sources": ["azure"],
  "tools_match": true              // Matches golden scenario
}
```

**Why this works well:** Clear query, high confidence, single domain, one tool.

### Trace 2: Routing failure (missing tool)

```json
{
  "query": "what patches are available for my ubuntu servers",
  "domain": "inventory",           // WRONG - should be "patch"
  "confidence": 0.55,              // Low confidence = ambiguous
  "strategy": "fast",
  "orchestrator": "mcp",
  "tools_selected": [
    "list_inventory_items",        // Wrong tools selected
    "search_inventory"
  ],
  "tool_count": 2,
  "classification_time_ms": 3.8,
  "active_domains": ["inventory"],  // Only inventory matched
  "relevant_sources": ["inventory"],
  "expected_tools": ["check_available_patches"],
  "tools_match": false,
  "missing_tools": ["check_available_patches"],  // The problem
  "domain_match": false            // Domain also wrong
}
```

**Root cause:** "ubuntu servers" triggered inventory domain patterns but not patch
domain. Fix: Add "patches available" and "ubuntu" patterns to patch domain keywords.

### Trace 3: Correct tools but from unexpected path

```json
{
  "query": "show me the health of container app myapp",
  "domain": "sre_health",
  "confidence": 0.88,
  "strategy": "fast",
  "orchestrator": "mcp",
  "tools_selected": [
    "container_app_list",             // Step 1: list first
    "check_container_app_health"      // Step 2: then check health
  ],
  "tool_count": 2,
  "secondary_domains": ["azure_management"],  // Also matched azure
  "tools_match": true,
  "unexpected_tools": []
}
```

**This is the deterministic health chain:** `container_app_list` -> `check_container_app_health`.
This is the expected pattern per the EOL tool selection policy.

---

## Manifest Improvement Workflow

When you need to improve a tool's routing accuracy:

### 1. Identify the problem

```bash
python scripts/selection_reporter.py --query "the problematic query"
```

### 2. Check current manifest quality

```bash
python scripts/manifest_linter.py 2>&1 | grep "tool_name"
python scripts/manifest_quality_scorecard.py 2>&1 | grep "tool_name"
```

### 3. Edit the manifest

Update the manifest file in `utils/manifests/<source>_manifests.py`:
- Add diverse `example_queries` (target 4+)
- Add semantic `tags` (target 3+)
- Document `conflicts_with` and `conflict_note`
- Set `preferred_over` if this tool should win over similar ones

### 4. Validate changes

```bash
# Check quality improved
python scripts/manifest_linter.py
python scripts/manifest_quality_scorecard.py --top-gaps 5

# Verify routing improved
python scripts/selection_reporter.py --query "the problematic query"

# Check no regressions
python scripts/manifest_impact_analyzer.py --golden-dir tests/fixtures/golden/
pytest tests/ -m "golden" -v
```

### 5. Add golden scenario if needed

If this is a high-value query pattern, pin it with a golden scenario.

---

## Tool Reference

### Selection Reporter

```bash
python scripts/selection_reporter.py [OPTIONS]

Options:
  --query TEXT          Single query to trace
  --queries-file PATH  File with one query per line
  --golden-dir PATH    Golden scenario YAML directory
  --strategy CHOICE    fast|quality|comprehensive (default: fast)
  --json               Output as JSON
  --github-summary PATH  Write GitHub step summary
```

### Manifest Impact Analyzer

```bash
python scripts/manifest_impact_analyzer.py [OPTIONS]

Options:
  --base TEXT           Base git ref (default: main)
  --head TEXT           Head git ref (default: HEAD)
  --golden-dir PATH    Golden scenario fixture directory
  --json               Output as JSON
  --github-summary PATH  Write GitHub step summary
```

### Manifest Linter

```bash
python scripts/manifest_linter.py [OPTIONS]

Options:
  --strict             Treat warnings as errors
  --json               Output as JSON
  --fail-threshold     critical|error|warning (default: error)
  --github-summary PATH  Write GitHub step summary
```

### Quality Scorecard

```bash
python scripts/manifest_quality_scorecard.py [OPTIONS]

Options:
  --json               Output as JSON
  --min-score FLOAT    Minimum passing score (default: 50)
  --top-gaps INT       Show top N tools needing improvement (default: 20)
  --github-summary PATH  Write GitHub step summary
```

---

**Version:** 1.0 (Created 2026-03-03)
**Related:** [Phase 2 Observability Guide](PHASE-2-OBSERVABILITY-GUIDE.md) | [Testing Guide](TESTING-GUIDE.md)
