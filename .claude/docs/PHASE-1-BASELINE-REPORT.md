# Phase 1 Baseline Report - MCP Tool Selection Quality

Captured 2026-03-03 as baseline before Phase 1 improvements.

---

## Executive Summary

| Metric | Value |
|--------|-------|
| **Overall Quality Score** | **83.9/100** |
| Total tool manifests | 103 |
| Manifest linter pass rate | 93.2% (96/103 pass) |
| Critical issues | 0 |
| Errors | 1 |
| Warnings | 6 |

---

## Quality Distribution

| Grade | Count | Percentage |
|-------|-------|------------|
| Excellent (80+) | 77 | 74.8% |
| Good (60-79) | 26 | 25.2% |
| Fair (40-59) | 0 | 0% |
| Poor (<40) | 0 | 0% |

**Interpretation:** The majority of manifests score well (74.8% excellent), but 25.2%
have room for improvement. No manifests are in poor condition.

---

## Quality by Source

| Source | Avg Score | Tools | Notes |
|--------|-----------|-------|-------|
| compute | 99.7 | 1 | Best quality - well-documented conflicts |
| storage | 96.9 | 1 | Strong conflict documentation |
| network | 91.8 | 17 | Phase 3 tools well-authored |
| azure_mcp | 88.5 | 2 | CLI tools with good step-ref docs |
| azure_cli | 88.5 | 1 | Good safety annotations |
| inventory | 88.2 | 2 | Adequate for domain scope |
| os_eol | 85.8 | 2 | Adequate for domain scope |
| monitor | 82.6 | 5 | Could benefit from more conflict docs |
| sre | 81.9 | 43 | Largest set, many tools need more examples |
| azure | 80.2 | 19 | Some tools lack conflict notes |

---

## Linter Issues

### Errors (1)

| Tool | Rule | Issue |
|------|------|-------|
| `azd` | AFF-001 | DEPLOY tool does not require confirmation |

**Fix required:** Set `requires_confirmation=True` in `azure_manifests.py`.

### Warnings (6)

| Tool | Rule | Issue |
|------|------|-------|
| `subscriptions` | EX-003 | Example query too short: "show subscriptions" |
| `storage` | CONF-001 | conflicts_with references non-existent tool "storagesync" |
| `speech` | EX-003 | Example query too short: "configure speech-to-text" |
| `predict_resource_exhaustion` | EX-003 | Example query too short: "capacity forecast" |
| `get_security_score` | EX-003 | Example query too short: "security posture" |
| `calculate_mttr_metrics` | EX-003 | Example query too short: "calculate MTTR" |

---

## Top 20 Tools Needing Improvement

| # | Tool | Score | Source | Top Gap |
|---|------|-------|--------|---------|
| 1 | `send_teams_alert` | 73.2 | sre | Add more example queries (have 2, target 4) |
| 2 | `groups` | 73.5 | azure | Add more tags (have 2, target 3+) |
| 3 | `app_service` | 74.0 | azure | Add more example queries + tags |
| 4 | `function_app` | 74.0 | azure | Add more example queries + tags |
| 5 | `app_configuration` | 74.8 | azure | Add more example queries + tags |
| 6 | `applicationinsights` | 74.8 | azure | Add preferred_over for clarity |
| 7 | `get_diagnostic_logs` | 75.0 | sre | Add more tags + example queries |
| 8 | `send_teams_notification` | 75.0 | sre | Consider requires_confirmation for WRITE |
| 9 | `list_monitor_categories` | 75.5 | monitor | Add more example queries + tags |
| 10 | `send_sre_status_update` | 76.4 | sre | Consider requires_confirmation for WRITE |
| 11 | `os_eol_check` | 76.5 | os_eol | Add more example queries |
| 12 | `get_resource_content` | 76.8 | monitor | Add more example queries + tags |
| 13 | `search_categories` | 77.0 | monitor | Add more example queries |
| 14 | `container_registries` | 77.0 | azure | Add more example queries + tags |
| 15 | `deploy_workbook` | 77.2 | monitor | Add more example queries |
| 16 | `describe_capabilities` | 77.5 | sre | Add more example queries |
| 17 | `detect_metric_anomalies` | 78.1 | sre | Document potential confusions |
| 18 | `compare_baseline_metrics` | 78.3 | sre | Document potential confusions |
| 19 | `predict_resource_exhaustion` | 78.5 | sre | Short example queries |
| 20 | `azure_deploy` | 78.8 | azure | Document potential confusions |

---

## Most Common Gaps Across All Tools

| # | Gap | Affected Tools |
|---|-----|---------------|
| 1 | No documented tool confusions | 79 tools (77%) |
| 2 | Only 3 example queries (target 4) | 54 tools (52%) |
| 3 | Only 2 example queries (target 4) | 35 tools (34%) |
| 4 | Missing preferred_over | 19 tools (18%) |
| 5 | Only 2 tags (target 3+) | 10 tools (10%) |
| 6 | WRITE tools without confirmation | 4 tools (4%) |
| 7 | DEPLOY tool without confirmation | 1 tool (1%) |

---

## Scoring Methodology

Quality scores are calculated as a weighted average across 6 dimensions:

| Dimension | Weight | What It Measures |
|-----------|--------|-----------------|
| Example queries | 25% | Count, diversity, and length of NL examples |
| Tags | 20% | Semantic tag count for retrieval |
| Conflict docs | 20% | conflict_note + preferred_over completeness |
| Domains | 15% | Domain classification presence |
| Metadata | 10% | Source field and affordance validity |
| Safety | 10% | requires_confirmation for destructive/deploy tools |

---

## Improvement Targets (Phase 1 Goals)

| Target | Current | Goal | Impact |
|--------|---------|------|--------|
| Overall score | 83.9 | 90+ | Better tool selection accuracy |
| Linter pass rate | 93.2% | 100% | Zero critical/error issues |
| Tools with 4+ examples | ~15% | 50% | More retrieval signal |
| Tools with conflict docs | ~23% | 60% | Fewer confusions |
| DEPLOY tools with confirmation | 80% | 100% | Safety compliance |

---

## How to Run These Reports

```bash
# Activate virtual environment
cd app/agentic/eol
source ../../../.venv/bin/activate

# Run manifest linter
python scripts/manifest_linter.py

# Run quality scorecard
python scripts/manifest_quality_scorecard.py

# Get JSON output for tooling
python scripts/manifest_linter.py --json > lint-results.json
python scripts/manifest_quality_scorecard.py --json > scorecard.json
```

---

**Version:** 1.0 (Baseline captured 2026-03-03)
**Next review:** After Phase 1 manifest improvements are applied
