# Phase 2 Observability Guide - MCP Tool Selection

Comprehensive guide to the Phase 2 observability features for diagnosing and
debugging MCP tool selection behavior in the EOL platform.

---

## Table of Contents

1. [Overview](#overview)
2. [Observability Features](#observability-features)
3. [Reading Tool Selection Traces](#reading-tool-selection-traces)
4. [Using the Selection Reporter](#using-the-selection-reporter)
5. [Using the Manifest Impact Analyzer](#using-the-manifest-impact-analyzer)
6. [CI Pipeline Integration](#ci-pipeline-integration)
7. [Debugging Workflow](#debugging-workflow)
8. [Telemetry Reference](#telemetry-reference)
9. [Common Issues Catalog](#common-issues-catalog)
10. [Related Documentation](#related-documentation)

---

## Overview

Phase 2 adds **observability instrumentation** to the tool selection pipeline,
enabling developers to understand *why* a query routes to specific tools, and
*what changes* when manifests are modified.

### What's New in Phase 2

| Feature | Purpose | Location |
|---------|---------|----------|
| **Selection Reporter** | Traces query→tool routing decisions | `scripts/selection_reporter.py` |
| **Manifest Impact Analyzer** | Shows change risk for manifest edits | `scripts/manifest_impact_analyzer.py` |
| **CI Stage 2.5: Diagnostics** | Automatic diagnostic reports in CI | `.github/workflows/test-tool-selection.yml` |
| **Routing telemetry** | Structured log fields on every route() call | `utils/unified_router.py` |

### Architecture

```
User Query
    │
    ├── UnifiedRouter.route()
    │     ├── Stage 1: Domain Classification  ── emits domain + confidence
    │     ├── Stage 2: Orchestrator Selection  ── emits orchestrator choice
    │     └── Stage 3: Tool Retrieval          ── emits tool list + timing
    │                                               │
    │                                               ▼
    │                                         RoutingPlan
    │                                         (structured trace)
    │
    ├── Selection Reporter (diagnostic tool)
    │     └── Aggregates traces → report
    │
    └── Manifest Impact Analyzer (change detection)
          └── Git diff → affected tools → risk assessment
```

---

## Observability Features

### 1. RoutingPlan Telemetry

Every call to `UnifiedRouter.route()` produces a `RoutingPlan` dataclass with
full routing metadata:

```python
@dataclass
class RoutingPlan:
    orchestrator: str               # "mcp" or "sre"
    domain: DomainLabel             # Primary domain classification
    tools: List[str]                # Selected tool names
    confidence: float               # Classification confidence [0.0, 1.0]
    strategy_used: RoutingStrategy  # "fast" | "quality" | "comprehensive"
    classification_time_ms: float   # Wall-clock routing time
    secondary_domains: List[DomainLabel]  # Additional detected domains
```

### 2. ToolRouter.explain()

The `ToolRouter.explain()` method provides a diagnostic view of domain/source
classification without running the full pipeline:

```python
router = ToolRouter()
explanation = router.explain("show my container apps")
# Returns:
# {
#   "query": "show my container apps",
#   "domains": {"sre_health": True, "azure_management": False, ...},
#   "active_domains": ["sre_health"],
#   "relevant_sources": ["sre"],
#   "prior_tool_names": [],
#   "would_filter": True
# }
```

### 3. Selection Reporter

CLI tool that traces queries through the full routing pipeline and generates
structured reports.

### 4. Manifest Impact Analyzer

CLI tool that detects manifest file changes and assesses their impact on
existing golden scenarios.

---

## Reading Tool Selection Traces

A tool selection trace captures the complete routing decision for one query.
Here's how to read each field:

### Example Trace

```json
{
  "query": "show my container apps",
  "domain": "sre_health",
  "confidence": 0.85,
  "strategy": "fast",
  "orchestrator": "mcp",
  "tools_selected": ["container_app_list", "check_container_app_health"],
  "tool_count": 2,
  "classification_time_ms": 4.2,
  "secondary_domains": ["azure_management"],
  "active_domains": ["sre_health"],
  "relevant_sources": ["sre"],
  "expected_tools": ["container_app_list"],
  "tools_match": true,
  "missing_tools": [],
  "unexpected_tools": ["check_container_app_health"]
}
```

### Field-by-Field Guide

| Field | What It Tells You |
|-------|-------------------|
| `domain` | Primary domain the query was classified to |
| `confidence` | How confident the classifier is (>0.7 is good) |
| `strategy` | Which routing strategy was used ("fast" = keyword, "quality" = semantic) |
| `orchestrator` | Which orchestrator handles execution ("mcp" or "sre") |
| `tools_selected` | The actual tools the pipeline chose |
| `classification_time_ms` | How long routing took (target: <10ms for "fast") |
| `secondary_domains` | Other domains detected (may explain tool selection) |
| `active_domains` | Domains from keyword/pattern matching |
| `relevant_sources` | Which manifest sources contribute tools |
| `expected_tools` | What the golden scenario expected (if applicable) |
| `tools_match` | Whether required expected tools are present |
| `missing_tools` | Expected tools that weren't selected |
| `unexpected_tools` | Selected tools that weren't in expected list |

### Reading Confidence Scores

| Range | Meaning | Action |
|-------|---------|--------|
| 0.9+ | High confidence | Routing is reliable |
| 0.7-0.9 | Moderate | Usually correct, may need more examples |
| 0.5-0.7 | Low | Ambiguous query, may misroute |
| <0.5 | Very low | Query doesn't match any domain well |

---

## Using the Selection Reporter

### Quick Start

```bash
cd app/agentic/eol
source ../../../.venv/bin/activate

# Trace a single query
python scripts/selection_reporter.py --query "show my container apps"

# Trace all golden scenarios
python scripts/selection_reporter.py --golden-dir tests/fixtures/golden/

# JSON output for tooling
python scripts/selection_reporter.py --golden-dir tests/fixtures/golden/ --json

# Trace queries from a file (one per line)
python scripts/selection_reporter.py --queries-file my_queries.txt
```

### Output Formats

**Text output** (default): Human-readable diagnostic report with per-query traces.

**JSON output** (`--json`): Machine-readable for CI integration and analysis.

**GitHub summary** (`--github-summary`): Markdown table for CI step summaries.

### Interpreting Results

The reporter outputs a summary section plus per-query traces:

```
==============================================================================
  Tool Selection Diagnostic Report
==============================================================================

  Total queries:      5
  Passed:             4
  Failed:             1
  Avg tools/query:    3.2
  Total routing time: 21.5ms

  --- Query 1 PASS ---
  Query:        show my container apps
  Domain:       sre_health (confidence: 0.85)
  Orchestrator: mcp
  Tools (2):
    - container_app_list
    - check_container_app_health

  --- Query 3 FAIL ---
  Query:        check storage account health
  Domain:       azure_management (confidence: 0.62)
  Expected tools: check_storage_health
  MISSING tools:  check_storage_health
  ...
```

**PASS** means all required expected tools were selected.
**FAIL** means one or more required tools were missing from the selection.

---

## Using the Manifest Impact Analyzer

### Quick Start

```bash
cd app/agentic/eol
source ../../../.venv/bin/activate

# Analyze changes vs main branch
python scripts/manifest_impact_analyzer.py

# Analyze specific refs
python scripts/manifest_impact_analyzer.py --base main --head HEAD

# Include golden scenario impact
python scripts/manifest_impact_analyzer.py --golden-dir tests/fixtures/golden/

# JSON output
python scripts/manifest_impact_analyzer.py --json
```

### Risk Levels

The analyzer classifies tool impacts by risk:

| Level | Trigger | What It Means |
|-------|---------|---------------|
| **High** | >20 lines changed in manifest file | Large change, likely affects retrieval |
| **Medium** | 5-20 lines changed, or conflict fields present | Moderate change, check scenarios |
| **Low** | <5 lines changed | Small change, low regression risk |

### Scenario Impact

When `--golden-dir` is provided, the analyzer cross-references changed tools
against golden scenario fixture files to identify which tests may break:

```
  HIGH RISK Tools:
    container_app_list (sre)
      Note: Large change: +25/-10 lines
      Scenarios: sre-container-list, sre-health-check

  Golden Scenarios at Risk:
    - sre-container-list
    - sre-health-check
```

---

## CI Pipeline Integration

### Stage 2.5: Tool Selection Diagnostics

The CI pipeline now includes a diagnostic stage that runs after golden scenarios:

```
Stage 1: Unit Tests        ──┐
Stage 1.5: Manifest Quality ─┤
                              ├─→ Stage 2: Golden Scenarios
                              │         │
                              │         ├─→ Stage 2.5: Diagnostics (always runs)
                              │         │     ├── Selection reporter on golden fixtures
                              │         │     ├── Manifest impact analyzer
                              │         │     └── Upload artifacts (30-day retention)
                              │         │
                              │         └─→ Stage 3: Smoke Tests
                              │                   └─→ Stage 4: E2E Tests
                              │
                              └─→ Test Summary (aggregates all stages)
```

### What CI Produces

| Artifact | Filename | Description |
|----------|----------|-------------|
| Selection report (JSON) | `selection-report.json` | Full routing traces for all golden queries |
| Selection report (text) | `selection-report.txt` | Human-readable diagnostic output |
| Impact report (JSON) | `impact-report.json` | Manifest change risk assessment |
| Impact report (text) | `impact-report.txt` | Human-readable impact summary |

**Artifact retention:** 30 days (downloadable from Actions tab).

### Reading CI Output

1. **PR Comment**: Shows stage results table with pass/fail for each stage
2. **Step Summary**: When golden scenarios fail, the diagnostics step writes
   a summary showing which queries misrouted and why
3. **Artifacts**: Download `tool-selection-diagnostics` for full trace data

### When Diagnostics Trigger

- **Always** runs after golden scenarios (even if they fail)
- Generates selection report from golden fixture files
- Generates impact report comparing HEAD vs base branch
- On golden scenario **failure**: writes detailed summary to GitHub step summary
- Does **not** block merge (advisory stage)

---

## Debugging Workflow

### Step-by-Step: Fixing a Failed Golden Scenario

1. **Read the CI failure message**
   - Check which golden scenario(s) failed
   - Note the expected vs actual tools

2. **Download diagnostic artifacts**
   - Go to Actions → failed run → Artifacts → `tool-selection-diagnostics`
   - Open `selection-report.json` or `selection-report.txt`

3. **Find the failing trace**
   - Search for `"tools_match": false` in JSON
   - Or look for `FAIL` markers in text output

4. **Identify the root cause**
   - `missing_tools` → Expected tool not retrieved. Check its manifest metadata.
   - `domain_match: false` → Query classified to wrong domain. Check domain patterns.
   - Low `confidence` → Ambiguous query. Add more example_queries to manifest.

5. **Fix the issue**
   - If manifest metadata: Update tags, example_queries, domains in the manifest file
   - If routing logic: Modify domain classifier or tool router
   - If fixture outdated: Update the golden scenario YAML

6. **Verify locally**
   ```bash
   cd app/agentic/eol

   # Trace the specific query
   python scripts/selection_reporter.py --query "the failing query here"

   # Run all golden scenarios
   pytest tests/ -m "golden" -v

   # Check manifest quality
   python scripts/manifest_linter.py
   ```

7. **Push and verify CI**
   - The diagnostic stage will confirm the fix

### Quick Debugging Commands

```bash
# "Why was this tool not selected for this query?"
python scripts/selection_reporter.py --query "your query here"

# "What tools are affected by my manifest changes?"
python scripts/manifest_impact_analyzer.py --golden-dir tests/fixtures/golden/

# "Which golden scenarios might break from my changes?"
python scripts/manifest_impact_analyzer.py --golden-dir tests/fixtures/golden/ --json | \
  python -c "import sys,json; r=json.load(sys.stdin); print('\n'.join(r['scenarios_at_risk']))"

# "Show the full routing explanation for a query"
python -c "
from utils.tool_router import ToolRouter
import json
r = ToolRouter()
print(json.dumps(r.explain('your query here'), indent=2))
"

# "Run the manifest linter to check my changes"
python scripts/manifest_linter.py

# "What's my manifest quality score?"
python scripts/manifest_quality_scorecard.py --top-gaps 5
```

---

## Telemetry Reference

### Log Fields

All routing calls emit structured log entries. Key fields:

| Field | Type | Source | Description |
|-------|------|--------|-------------|
| `query` | string | UnifiedRouter | First 80 chars of user query |
| `domain` | string | DomainClassification | Primary domain label |
| `orchestrator` | string | UnifiedRouter | "mcp" or "sre" |
| `tools` | int | UnifiedRouter | Number of tools selected |
| `strategy` | string | UnifiedRouter | Routing strategy used |
| `elapsed_ms` | float | UnifiedRouter | Wall-clock routing time |
| `confidence` | float | DomainClassification | Classification confidence |
| `secondary_domains` | list | DomainClassification | Additional detected domains |
| `active_domains` | list | ToolRouter.explain() | Keyword-matched domains |
| `relevant_sources` | list | ToolRouter.explain() | Contributing manifest sources |

### RoutingPlan Fields

| Field | Type | Range | Description |
|-------|------|-------|-------------|
| `orchestrator` | str | "mcp", "sre" | Which orchestrator processes the query |
| `domain` | DomainLabel | enum | Primary domain classification |
| `tools` | List[str] | 0-N | Tool names passed to orchestrator |
| `confidence` | float | 0.0-1.0 | Classification confidence score |
| `strategy_used` | str | "fast", "quality", "comprehensive" | Routing strategy applied |
| `classification_time_ms` | float | 0+ | Total route() wall-clock time in ms |
| `secondary_domains` | List[DomainLabel] | 0-N | Additional domains detected |

### Selection Reporter Output Fields

| Field | Type | Description |
|-------|------|-------------|
| `total_queries` | int | Number of queries analyzed |
| `pass_count` | int | Queries where required tools matched |
| `fail_count` | int | Queries where required tools were missing |
| `avg_tools_per_query` | float | Average tool count per query |
| `total_time_ms` | float | Sum of all routing times |
| `domain_distribution` | dict | Count of queries per domain |
| `traces` | list | Per-query ToolSelectionTrace objects |

### Impact Analyzer Output Fields

| Field | Type | Description |
|-------|------|-------------|
| `total_manifests_changed` | int | Number of manifest files with changes |
| `total_tools_affected` | int | Tools from changed manifest sources |
| `high_risk_count` | int | Tools with high-risk changes |
| `has_regressions` | bool | Whether high-risk or scenario impact detected |
| `scenarios_at_risk` | list | Golden scenario IDs potentially affected |

---

## Common Issues Catalog

### Issue: Tool not selected for expected query

**Symptoms:** `missing_tools` in selection trace. Golden scenario fails.

**Root causes:**
1. Missing or weak `example_queries` in manifest
2. Missing `tags` that match query keywords
3. Wrong `domains` classification
4. Another tool's `preferred_over` or `conflicts_with` winning

**Fix:** Improve manifest metadata. Run linter to check quality score.

### Issue: Wrong domain classification

**Symptoms:** `domain_match: false` in trace. Query routed to wrong orchestrator.

**Root causes:**
1. Query matches patterns for multiple domains
2. Keyword overlap with another domain
3. Missing domain pattern in `QueryPatterns`

**Fix:** Check `active_domains` in trace. Add disambiguation patterns or update domain classifier.

### Issue: Too many tools selected

**Symptoms:** `tool_count` very high (>10). Slow orchestrator response.

**Root causes:**
1. Broad domain classification returning too many sources
2. Missing `conflicts_with` to narrow selection
3. Overly generic tags

**Fix:** Add conflict documentation. Narrow tags. Check `relevant_sources` in trace.

### Issue: Low confidence routing

**Symptoms:** `confidence < 0.5`. Inconsistent routing for similar queries.

**Root causes:**
1. Query is genuinely ambiguous
2. Manifest metadata doesn't differentiate domains well
3. Multiple tools compete without clear winner

**Fix:** Add more `example_queries` with diverse phrasing. Add `conflict_note` to disambiguate.

### Issue: Manifest change breaks golden scenarios

**Symptoms:** Impact analyzer shows `scenarios_at_risk`. CI golden scenarios fail after manifest edit.

**Root causes:**
1. Changed `example_queries` no longer match scenario expectations
2. Modified `tags` or `domains` alter retrieval ranking
3. New `preferred_over` changes tool priority

**Fix:** Run `selection_reporter.py --golden-dir tests/fixtures/golden/` locally before pushing.
Update golden scenario YAML if the new routing is correct.

---

## Related Documentation

| Document | Description |
|----------|-------------|
| [Testing Guide](TESTING-GUIDE.md) | Full testing infrastructure documentation |
| [Debugging Tool Selection](DEBUGGING-TOOL-SELECTION.md) | Practical debugging scenarios with examples |
| [Manifest Authoring Guide](MANIFEST-AUTHORING-GUIDE.md) | How to write quality tool manifests |
| [Phase 1 Baseline Report](PHASE-1-BASELINE-REPORT.md) | Quality baseline measurements |

---

**Version:** 1.0 (Created 2026-03-03)
**Covers:** Selection reporter, manifest impact analyzer, CI diagnostics stage, telemetry reference, debugging workflow
