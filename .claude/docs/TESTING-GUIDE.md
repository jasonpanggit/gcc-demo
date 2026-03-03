# Testing Guide - MCP Tool Selection Testing Infrastructure

Comprehensive guide for the EOL platform's testing infrastructure, including the
golden scenario system for validating MCP tool selection behavior.

---

## Table of Contents

1. [Overview](#overview)
2. [Testing Pyramid](#testing-pyramid)
3. [Quick Start](#quick-start)
4. [Golden Scenarios](#golden-scenarios)
   - [What Are Golden Scenarios?](#what-are-golden-scenarios)
   - [Writing a Golden Scenario](#writing-a-golden-scenario)
   - [Fixture File Format](#fixture-file-format)
   - [Contract Validation](#contract-validation)
5. [DeterministicMCPClient](#deterministicmcpclient)
6. [Running Tests Locally](#running-tests-locally)
7. [CI Pipeline Stages](#ci-pipeline-stages)
8. [Cost Management](#cost-management)
9. [Troubleshooting](#troubleshooting)
10. [Adding Tests for New Tools](#adding-tests-for-new-tools)
11. [Manifest Quality](#manifest-quality)
    - [Manifest Linter](#manifest-linter)
    - [Quality Scorecard](#quality-scorecard)
    - [Fixing Linter Errors](#fixing-linter-errors)
    - [Best Practices for Tool Metadata](#best-practices-for-tool-metadata)

---

## Overview

The EOL platform uses a layered testing strategy to validate MCP tool selection
behavior. The key insight is that tool selection is the most critical decision point
in the agentic pipeline: if the wrong tool is selected, all downstream work is wasted.

**Testing philosophy:**
- **Determinism over randomness** - Golden scenarios pin known-good tool selections
- **Fast feedback loops** - Unit tests run in <30s, integration in <2min
- **Cost awareness** - Use `gpt-4o-mini` for tests, reserve `gpt-4o` for production
- **Progressive gates** - Each CI stage catches issues at increasing fidelity

---

## Testing Pyramid

```
                    +------------------+
                    |     E2E Tests    |  ← Playwright browser tests (~10min)
                    |  (Stage 4 - CI)  |    Full user journeys through UI
                    +------------------+
                   /                    \
              +-------------------------+
              |     Smoke Tests         |  ← Against deployed app (~5min)
              |   (Stage 3 - CI)        |    Real Azure endpoints, subset of queries
              +-------------------------+
             /                            \
        +----------------------------------+
        |   Integration / Golden Scenarios  |  ← Azure OpenAI + fixtures (~2min)
        |         (Stage 2 - CI)            |    DeterministicMCPClient validates
        +----------------------------------+     tool selection contracts
       /                                    \
  +------------------------------------------+
  |  Manifest Quality (Stage 1.5 - CI)        |  ← Linter + scorecard (~30s)
  |  Runs in parallel with unit tests          |    Validates manifest metadata
  +------------------------------------------+
  |          Unit Tests (Stage 1 - CI)        |  ← Pure Python, no external calls (~30s)
  |  Mock everything, test routing logic only  |    AsyncMock, parametrized, fast
  +------------------------------------------+
```

### What Each Layer Tests

| Layer | Focus | External Deps | Speed | Cost |
|-------|-------|---------------|-------|------|
| **Unit** | Routing logic, domain classification, tool scoring | None | <30s | $0 |
| **Manifest Quality** | Manifest metadata: tags, examples, conflicts, safety | None | <30s | $0 |
| **Integration** | Tool selection against Azure OpenAI with fixtures | Azure OpenAI | <2min | ~$0.01/run |
| **Smoke** | Critical paths against deployed app | Full Azure stack | <5min | ~$0.05/run |
| **E2E** | Full user journeys via browser automation | Full stack + browser | <10min | ~$0.10/run |

---

## Quick Start

### Prerequisites

```bash
# Activate virtual environment
cd app/agentic/eol
source ../../../.venv/bin/activate
pip install -r requirements.txt
pip install pytest pytest-asyncio pytest-cov
```

### Run Unit Tests Only (fastest)

```bash
# From repo root
pytest app/agentic/eol/tests/ -m "unit" -v --tb=short

# Or using the run_tests.sh helper
cd app/agentic/eol/tests && ./run_tests.sh -m "unit"
```

### Run Golden Scenario Tests

```bash
# Requires AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_API_KEY
pytest app/agentic/eol/tests/ -m "golden" -v

# Run a specific scenario
pytest app/agentic/eol/tests/ -k "test_golden_eol_search" -v
```

### Run All Non-Remote Tests

```bash
cd app/agentic/eol/tests && ./run_tests.sh
```

### Run Remote / Smoke Tests

```bash
cd app/agentic/eol/tests && ./run_tests.sh --remote
```

---

## Golden Scenarios

### What Are Golden Scenarios?

A golden scenario captures a **known-good tool selection decision** as a test fixture.
It records:

1. **The user query** (natural language input)
2. **The expected tool(s)** that should be selected
3. **The expected domain** classification
4. **Mock tool responses** (so tests don't need real Azure resources)
5. **Validation contracts** (assertions about the selection behavior)

Golden scenarios are the primary regression safety net for tool selection changes.
When you modify tool metadata, routing logic, or add new tools, golden scenarios
catch unintended selection regressions.

### Writing a Golden Scenario

**Step 1: Create the fixture file**

Create a YAML file in `tests/fixtures/golden/`:

```yaml
# tests/fixtures/golden/eol_search_windows.yaml
scenario:
  id: "eol-search-windows-server"
  description: "User searches for Windows Server 2016 EOL status"
  category: "eol"
  priority: "high"

input:
  query: "When does Windows Server 2016 reach end of life?"
  context:
    conversation_history: []
    active_tools: null  # null = all tools available

expected:
  domain: "eol"
  tools:
    required:
      - "search_eol_data"
    preferred:
      - "get_eol_timeline"
    forbidden:
      - "container_app_list"
      - "check_container_app_health"
  min_confidence: 0.7

mock_responses:
  search_eol_data:
    status: "success"
    data:
      software: "Windows Server"
      version: "2016"
      eol_date: "2027-01-12"
      extended_support_end: "2027-01-12"
      status: "approaching_eol"

validation:
  tool_selection:
    strategy: "required_present"  # required tools must appear in selection
    max_tools: 5                   # at most 5 tools in final selection
  response_quality:
    must_contain: ["2027", "Windows Server", "end of life"]
```

**Step 2: Register in the test generator**

Golden scenarios are auto-discovered from the `tests/fixtures/golden/` directory.
The parametrized test generator loads all `.yaml` files and creates one test per
scenario.

**Step 3: Run and verify**

```bash
pytest app/agentic/eol/tests/ -k "test_golden_eol_search_windows" -v
```

### Fixture File Format

```yaml
scenario:             # Metadata about this test case
  id: string          # Unique identifier (kebab-case)
  description: string # Human-readable description
  category: string    # Domain: "eol", "sre", "inventory", "network", "patch"
  priority: string    # "critical", "high", "medium", "low"

input:                # What the system receives
  query: string       # The user's natural language query
  context:            # Optional conversation/state context
    conversation_history: list
    active_tools: list | null

expected:             # What we assert about the output
  domain: string      # Expected domain classification
  tools:
    required: list    # Tools that MUST be in the selection
    preferred: list   # Tools that SHOULD be in the selection (non-fatal)
    forbidden: list   # Tools that MUST NOT be in the selection
  min_confidence: float  # Minimum confidence score (0.0 - 1.0)

mock_responses:       # Deterministic tool responses for testing
  <tool_name>:        # One entry per tool that might be called
    status: string
    data: object

validation:           # How to validate the result
  tool_selection:
    strategy: string  # "required_present" | "exact_match" | "subset"
    max_tools: int
  response_quality:
    must_contain: list[string]
    must_not_contain: list[string]
```

### Contract Validation

The test generator validates three types of contracts:

#### 1. Tool Selection Contract

Ensures the right tools are selected for a given query.

```python
# "required_present" strategy
assert all(tool in selected_tools for tool in expected.tools.required)

# "exact_match" strategy
assert set(selected_tools) == set(expected.tools.required + expected.tools.preferred)

# All strategies check forbidden tools
assert not any(tool in selected_tools for tool in expected.tools.forbidden)
```

#### 2. Domain Classification Contract

Ensures queries are routed to the correct domain.

```python
assert classified_domain == expected.domain
```

#### 3. Response Quality Contract

Ensures the agent's response contains expected information.

```python
for keyword in validation.response_quality.must_contain:
    assert keyword.lower() in response.lower()
```

---

## DeterministicMCPClient

The `DeterministicMCPClient` replaces the real MCP client during golden scenario
tests. Instead of calling Azure OpenAI or real MCP servers, it returns pre-recorded
responses from fixture files.

### How It Works

```
User Query
    │
    ├─ Real MCP Client (production)
    │     └─ Azure OpenAI → tool selection → MCP server → real response
    │
    └─ DeterministicMCPClient (testing)
          └─ Fixture file → mock tool selection → mock response
```

### Usage in Tests

```python
import pytest
from tests.deterministic_mcp_client import DeterministicMCPClient

@pytest.fixture
def mock_client():
    """Create a DeterministicMCPClient with golden scenario fixtures."""
    client = DeterministicMCPClient()
    client.load_fixtures("tests/fixtures/golden/")
    return client

@pytest.mark.golden
@pytest.mark.asyncio
async def test_golden_eol_search(mock_client):
    """Validate tool selection for EOL search queries."""
    result = await mock_client.execute(
        query="When does Windows Server 2016 reach end of life?",
        scenario_id="eol-search-windows-server"
    )

    assert result.selected_tools_match(required=["search_eol_data"])
    assert result.domain == "eol"
    assert result.confidence >= 0.7
```

### Key Methods

| Method | Description |
|--------|-------------|
| `load_fixtures(path)` | Load all YAML fixtures from a directory |
| `execute(query, scenario_id)` | Run a query through the deterministic pipeline |
| `validate_contract(result, expected)` | Check selection against expected contract |
| `get_mock_response(tool_name)` | Return the pre-recorded response for a tool |

---

## Running Tests Locally

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `USE_MOCK_DATA` | No | `true` | Use mock data (no Azure) |
| `TESTING` | No | `true` | Enable test mode |
| `AZURE_OPENAI_ENDPOINT` | For golden | - | Azure OpenAI endpoint |
| `AZURE_OPENAI_API_KEY` | For golden | - | Azure OpenAI API key |
| `AZURE_OPENAI_DEPLOYMENT_NAME` | For golden | `gpt-4o-mini` | Model for tests |
| `MOCK_AGENT_DELAY_MS` | No | `0` (in tests) | Mock agent delay |
| `BASE_URL` | For remote | `http://localhost:8000` | App URL for testing |

### Test Markers

Use pytest markers to run specific test categories:

```bash
# Unit tests only
pytest -m "unit" -v

# Golden scenarios only
pytest -m "golden" -v

# Integration tests
pytest -m "integration" -v

# Exclude remote tests
pytest -m "not remote" -v

# MCP-related tests
pytest -m "mcp" -v

# SRE-specific tests
pytest -m "mcp_sre" -v

# Cache tests
pytest -m "cache" -v

# Multiple markers
pytest -m "unit or golden" -v
```

### Coverage Report

```bash
# Generate coverage report
pytest --cov=. --cov-report=html --cov-report=term -v

# View HTML report
open htmlcov/index.html
```

---

## CI Pipeline Stages

The CI pipeline (`.github/workflows/test-tool-selection.yml`) runs 5 progressive
stages. Each stage only runs if the previous one passes.

### Stage 1: Unit Tests (<30s)

- Runs all `@pytest.mark.unit` tests
- No external dependencies
- Tests routing logic, domain classification, tool scoring
- **Gate:** Must pass before Stage 2

### Stage 1.5: Manifest Quality (<30s)

- Runs manifest linter and quality scorecard
- No external dependencies (reads manifest Python files only)
- Validates metadata quality: tags, example queries, conflicts, safety annotations
- Runs **in parallel** with Stage 1 (does not wait for unit tests)
- Generates JSON artifacts for PR comment and trend tracking
- **Gate:** Advisory — does not block merge, but warnings shown in PR

### Stage 2: Integration / Golden Scenarios (<2min)

- Runs `@pytest.mark.golden` tests
- Uses Azure OpenAI with `gpt-4o-mini` for cost efficiency
- DeterministicMCPClient provides mock tool responses
- Validates tool selection contracts against fixture files
- **Gate:** Must pass before Stage 3

### Stage 3: Smoke Tests (<5min)

- Runs a subset of critical queries against the deployed app
- Validates real Azure endpoints respond correctly
- **Optional:** Skipped for draft PRs
- **Gate:** Must pass before Stage 4

### Stage 4: E2E Tests (<10min)

- Playwright browser tests for full user journeys
- Tests UI rendering, SSE streaming, interactive features
- **Optional:** Skipped for draft PRs
- Runs existing tests from `tests/ui/`

### PR Status Checks

The CI adds a summary comment to each PR showing results:

```
| Stage     | Status | Duration |
|-----------|--------|----------|
| Unit      | Pass   | 22s      |
| Golden    | Pass   | 1m 14s   |
| Smoke     | Skip   | (draft)  |
| E2E       | Skip   | (draft)  |
```

---

## Cost Management

### Azure OpenAI Costs

Golden scenario tests use Azure OpenAI for realistic tool selection validation.
Cost is managed through several strategies:

#### 1. Use `gpt-4o-mini` for Tests

Set in CI environment:
```yaml
AZURE_OPENAI_DEPLOYMENT_NAME: "gpt-4o-mini"
```

**Cost comparison per 1K tokens:**
| Model | Input | Output |
|-------|-------|--------|
| gpt-4o | $2.50 | $10.00 |
| gpt-4o-mini | $0.15 | $0.60 |

**Savings:** ~95% cost reduction using gpt-4o-mini for tests.

#### 2. Fixture-Based Responses

DeterministicMCPClient provides mock tool responses, so only the tool *selection*
step calls Azure OpenAI. Tool *execution* is entirely local.

#### 3. Progressive Gates

The CI pipeline only runs expensive stages (smoke, E2E) if cheap stages pass.
Failed unit tests short-circuit before any Azure OpenAI calls.

#### 4. Skip for Draft PRs

Smoke and E2E stages are skipped for draft PRs. Only unit + golden scenarios run
during active development.

#### 5. Cost Estimation

| Stage | Approx. Azure OpenAI Cost |
|-------|---------------------------|
| Unit | $0 (no API calls) |
| Golden (5 scenarios) | ~$0.01 |
| Golden (20 scenarios) | ~$0.04 |
| Smoke | ~$0.05 |
| E2E | ~$0.10 |

**Monthly estimate (20 PRs/month):**
- Unit + Golden only: ~$0.80/month
- Full pipeline: ~$3.00/month

---

## Troubleshooting

### Common Issues

#### Test import errors

```
ModuleNotFoundError: No module named 'agents'
```

**Fix:** Run tests from the repo root using `run_tests.sh` or ensure `pythonpath`
is set in `pytest.ini`:
```bash
cd app/agentic/eol/tests && ./run_tests.sh
# OR
cd <repo-root> && pytest app/agentic/eol/tests/ -v
```

#### Golden scenario fails with "connection error"

```
ConnectionError: Could not connect to Azure OpenAI
```

**Fix:** Set Azure OpenAI environment variables:
```bash
export AZURE_OPENAI_ENDPOINT="https://your-endpoint.openai.azure.com"
export AZURE_OPENAI_API_KEY="your-key"
export AZURE_OPENAI_DEPLOYMENT_NAME="gpt-4o-mini"
```

#### Golden scenario tool selection mismatch

```
AssertionError: Expected tool 'search_eol_data' in selection, got ['get_eol_timeline']
```

**Diagnosis:**
1. Check if tool metadata changed (name, description, tags)
2. Check if routing logic was modified
3. Run with verbose logging: `pytest -v -s --log-cli-level=DEBUG`
4. If the new selection is correct, update the fixture file

#### Async test hangs

```
<test hangs indefinitely>
```

**Fix:** Ensure `asyncio_mode = strict` in `pytest.ini` and all async tests use
`@pytest.mark.asyncio`:
```python
@pytest.mark.asyncio
async def test_something():
    result = await some_async_function()
```

#### Mock data not loading

```
KeyError: 'search_eol_data' not found in mock responses
```

**Fix:** Ensure the fixture YAML includes mock responses for all tools that might
be called:
```yaml
mock_responses:
  search_eol_data:
    status: "success"
    data: { ... }
```

### Debug Workflow

1. **Identify the failing layer:** Is it unit, golden, smoke, or E2E?
2. **Check environment:** `env | grep AZURE` and `env | grep MOCK`
3. **Run single test with debug output:**
   ```bash
   pytest -k "test_name" -v -s --log-cli-level=DEBUG --tb=long
   ```
4. **Check fixture file:** Does the YAML match the current tool names?
5. **Validate tool metadata:** Run `python -c "from utils.tool_manifest_index import ...; print(...)"` to verify tool definitions

---

## Adding Tests for New Tools

When you add a new MCP tool to the platform, follow this checklist:

### 1. Add Unit Tests

Create unit tests for the tool's routing/classification logic:

```python
# tests/routing/test_new_tool_routing.py
import pytest
from unittest.mock import AsyncMock, MagicMock

@pytest.mark.unit
def test_new_tool_domain_classification():
    """Verify the new tool is classified under the correct domain."""
    # Test domain classifier routes query to correct domain
    ...

@pytest.mark.unit
def test_new_tool_appears_in_retrieval():
    """Verify the new tool is retrievable by relevant queries."""
    # Test tool retriever finds the tool for expected queries
    ...
```

### 2. Create Golden Scenarios

Create at least 2 golden scenarios for the new tool:

```yaml
# tests/fixtures/golden/new_tool_basic.yaml
scenario:
  id: "new-tool-basic-query"
  description: "Basic query that should select the new tool"
  category: "<domain>"
  priority: "high"

input:
  query: "What is <natural language query for new tool>?"

expected:
  domain: "<domain>"
  tools:
    required: ["new_tool_name"]
    forbidden: ["wrong_tool_name"]
```

### 3. Add Negative Scenarios

Ensure the new tool is NOT selected for unrelated queries:

```yaml
# Update existing scenarios to add the new tool to 'forbidden' list
# where appropriate
```

### 4. Validate Locally

```bash
# Run the new golden scenarios
pytest -k "test_golden_new_tool" -v

# Run ALL golden scenarios to check for regressions
pytest -m "golden" -v

# Run the full unit suite
pytest -m "unit" -v
```

### 5. Update This Guide

If the new tool introduces a new domain or testing pattern, update this guide.

---

## Manifest Quality

The manifest quality system ensures MCP tool manifests meet minimum quality
standards for reliable tool selection. It runs in CI (Stage 1.5) and provides
developer feedback via linter rules and quality scores.

### Manifest Linter

The linter validates structural quality of each manifest:

```bash
# Run linter (from app/agentic/eol)
python scripts/manifest_linter.py

# Strict mode (warnings = errors)
python scripts/manifest_linter.py --strict

# JSON output for tooling
python scripts/manifest_linter.py --json
```

**Severity levels:**

| Level | CI Behavior | Example |
|-------|------------|---------|
| Critical | Blocks merge | Empty tool_name or source |
| Error | Blocks merge (default threshold) | Missing tags, no example queries |
| Warning | Reported but non-blocking | Short example queries, dangling references |

### Quality Scorecard

The scorecard provides per-tool quality scores across 6 dimensions:

```bash
# Run scorecard
python scripts/manifest_quality_scorecard.py

# Show top 10 tools needing improvement
python scripts/manifest_quality_scorecard.py --top-gaps 10

# Fail if overall score below 80
python scripts/manifest_quality_scorecard.py --min-score 80
```

**Scoring dimensions:**

| Dimension | Weight | What It Measures |
|-----------|--------|-----------------|
| Example queries | 25% | Count, diversity, and length of NL examples |
| Tags | 20% | Semantic tag count for retrieval |
| Conflict docs | 20% | conflict_note + preferred_over completeness |
| Domains | 15% | Domain classification presence |
| Metadata | 10% | Source field and affordance validity |
| Safety | 10% | requires_confirmation for destructive/deploy tools |

### Fixing Linter Errors

**TOOL-001 (Critical): Invalid tool_name**
```python
# Bad
tool_name=""
tool_name="My Tool!"

# Fix: Use snake_case
tool_name="check_resource_health"
```

**DOM-001 (Error): Empty domains**
```python
# Bad
domains=frozenset()

# Fix: Add at least one domain
domains=frozenset({"sre_health"})
```

**TAG-001 (Error): Too few tags**
```python
# Bad - only 1 tag
tags=frozenset({"health"})

# Fix - add 2+ diverse tags
tags=frozenset({"health", "container", "containerapp", "status"})
```

**EX-001 (Error): Too few example queries**
```python
# Bad - only 1 query
example_queries=("check health",)

# Fix - add 2+ diverse queries
example_queries=(
    "check health of my container app",
    "is my container app running",
    "container app health status",
)
```

**CONF-002 (Error): Missing conflict_note**
```python
# Bad - conflicts_with set but no note
conflicts_with=frozenset({"resourcehealth"})
conflict_note=""

# Fix - explain the disambiguation
conflicts_with=frozenset({"resourcehealth"})
conflict_note=(
    "check_resource_health provides deep SRE diagnostics. "
    "resourcehealth provides basic platform availability only."
)
```

**AFF-001 (Error): Missing confirmation for destructive tools**
```python
# Bad
affordance=ToolAffordance.DESTRUCTIVE
requires_confirmation=False

# Fix
affordance=ToolAffordance.DESTRUCTIVE
requires_confirmation=True
```

### Best Practices for Tool Metadata

1. **Write example queries like a user would speak.** Not "execute container app
   listing operation" but "show my container apps".

2. **Use 4 example queries** with diverse phrasing:
   - Imperative: "list container apps"
   - Question: "what container apps do I have?"
   - Descriptive: "show me all running container apps"
   - Action: "get container app status"

3. **Tags should include synonyms.** If the tool handles "VMs", tag with both
   `vm` and `virtual_machine`.

4. **Document conflicts proactively.** When you add a tool that overlaps with
   an existing one, update BOTH manifests' `conflicts_with` and `conflict_note`.

5. **Set `preferred_over`** when one tool is clearly better for the overlapping
   use case (e.g. `container_app_list` preferred over `azure_cli_execute_command`
   for listing container apps).

6. **Run the linter before committing:**
   ```bash
   cd app/agentic/eol
   python scripts/manifest_linter.py
   ```

For the full authoring guide with templates, see: `.claude/docs/MANIFEST-AUTHORING-GUIDE.md`

---

## Debugging Tool Selection (Phase 2)

Phase 2 adds observability tools that make debugging tool selection issues faster
and more systematic. For the full guide, see:
- **[Phase 2 Observability Guide](PHASE-2-OBSERVABILITY-GUIDE.md)** — Architecture, telemetry reference
- **[Debugging Tool Selection](DEBUGGING-TOOL-SELECTION.md)** — Step-by-step scenarios with example traces

### Quick Debugging Commands

```bash
cd app/agentic/eol

# Trace a query through the routing pipeline
python scripts/selection_reporter.py --query "your query here"

# Trace all golden scenarios and check for misroutes
python scripts/selection_reporter.py --golden-dir tests/fixtures/golden/

# Check what golden scenarios your manifest changes might break
python scripts/manifest_impact_analyzer.py --golden-dir tests/fixtures/golden/

# Get routing explanation without running full pipeline
python -c "
from utils.tool_router import ToolRouter
import json
r = ToolRouter()
print(json.dumps(r.explain('your query'), indent=2))
"
```

### CI Diagnostic Artifacts

When golden scenarios fail in CI, the **Stage 2.5: Diagnostics** job generates:

| Artifact | Description |
|----------|-------------|
| `selection-report.json` | Full routing traces for every golden query |
| `selection-report.txt` | Human-readable diagnostic output |
| `impact-report.json` | Risk assessment for manifest changes |
| `impact-report.txt` | Human-readable impact summary |

Download from **Actions tab → failed run → Artifacts → `tool-selection-diagnostics`**.

### Common Debugging Patterns

| Symptom | First Check | Likely Fix |
|---------|-------------|------------|
| Tool not selected | Trace the query | Improve manifest `example_queries` and `tags` |
| Wrong domain | Check `active_domains` in trace | Update domain patterns or manifest `domains` |
| Low confidence (<0.7) | Check query ambiguity | Add more diverse `example_queries` |
| Too many tools (>10) | Check `relevant_sources` | Add `conflicts_with` and `preferred_over` |
| Manifest change broke tests | Run impact analyzer | Fix manifest or update golden scenario YAML |

---

## File Reference

| File | Purpose |
|------|---------|
| `tests/conftest.py` | Shared fixtures and pytest configuration |
| `tests/run_tests.sh` | Test runner script (handles import paths) |
| `tests/run_pytest.py` | Python wrapper for import path fixes |
| `tests/mock_data.py` | Mock data generator for local testing |
| `tests/deterministic_mcp_client.py` | Fixture-based MCP client for golden tests |
| `tests/golden_loader.py` | YAML fixture loader and schema validator |
| `tests/test_golden_scenarios.py` | Parametrized test generator for golden tests |
| `tests/fixtures/golden/*.yaml` | Golden scenario fixture files |
| `scripts/manifest_linter.py` | Manifest quality linter (CI Stage 1.5) |
| `scripts/manifest_quality_scorecard.py` | Quality scorecard analyzer (CI Stage 1.5) |
| `scripts/selection_reporter.py` | Tool selection diagnostic reporter (CI Stage 2.5) |
| `scripts/manifest_impact_analyzer.py` | Manifest change impact analyzer (CI Stage 2.5) |
| `.github/workflows/test-tool-selection.yml` | CI pipeline with 7 stages |
| `.claude/docs/MANIFEST-AUTHORING-GUIDE.md` | Guide for writing quality manifests |
| `.claude/docs/PHASE-1-BASELINE-REPORT.md` | Phase 1 quality baseline measurements |
| `.claude/docs/PHASE-2-OBSERVABILITY-GUIDE.md` | Phase 2 observability features |
| `.claude/docs/DEBUGGING-TOOL-SELECTION.md` | Practical debugging scenarios |
| `pytest.ini` | Pytest configuration (markers, paths, etc.) |

---

**Version:** 1.2 (Updated 2026-03-03)
**Covers:** Testing pyramid, golden scenarios, DeterministicMCPClient, CI pipeline (7 stages), manifest quality, cost management, Phase 2 observability and debugging
