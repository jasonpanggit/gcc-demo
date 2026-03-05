#!/usr/bin/env python3
"""
log_test_failures.py — SRE example test failure logger.

Reads pytest JSON output (generated with --json-report) and appends new failures
to tests/ui/test-results/issue-log.json and issue-log.md.

Usage:
    # Run tests with JSON report, then log failures
    pytest tests/ui/pages/test_sre_assistant.py --json-report --json-report-file=tests/ui/test-results/pytest-report.json -v
    python tests/ui/log_test_failures.py tests/ui/test-results/pytest-report.json

    # Dry run (show what would be logged without writing)
    python tests/ui/log_test_failures.py --dry-run tests/ui/test-results/pytest-report.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).parent
TEST_RESULTS_DIR = SCRIPT_DIR / "test-results"
ISSUE_LOG_JSON = TEST_RESULTS_DIR / "issue-log.json"
ISSUE_LOG_MD = TEST_RESULTS_DIR / "issue-log.md"


# ---------------------------------------------------------------------------
# Category mapping (pytest test class → issue category)
# ---------------------------------------------------------------------------

CLASS_TO_CATEGORY: Dict[str, str] = {
    "TestHealthAvailability": "health_availability",
    "TestIncidentTriage": "incident_triage",
    "TestNetworkDiagnostics": "network_diagnostics",
    "TestSecurityCompliance": "security_compliance",
    "TestInventoryCost": "inventory_cost",
    "TestPerformanceSlo": "performance_slo",
    "TestResourceValidation": "resource_validation",
}

PHASE_MARKERS: Dict[str, int] = {
    "phase1": 1,
    "phase2": 2,
    "phase3": 3,
    "phase4": 4,
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _next_issue_id(existing_issues: List[Dict[str, Any]]) -> str:
    """Generate the next ISSUE-NNN identifier."""
    if not existing_issues:
        return "ISSUE-001"
    ids = [
        int(i["id"].split("-")[1])
        for i in existing_issues
        if re.match(r"^ISSUE-\d{3}$", i.get("id", ""))
    ]
    return f"ISSUE-{(max(ids, default=0) + 1):03d}"


def _extract_prompt_from_test_name(test_name: str) -> str:
    """Extract prompt from parametrized test name like test_health_prompt[What is...]."""
    m = re.search(r"\[(.+)\]$", test_name)
    return m.group(1) if m else test_name


def _extract_category(test_node_id: str) -> str:
    """Determine issue category from test node ID."""
    for class_name, category in CLASS_TO_CATEGORY.items():
        if class_name in test_node_id:
            return category
    return "health_availability"  # default


def _extract_phase(markers: List[str]) -> Optional[int]:
    """Extract fix phase from test markers."""
    for marker in markers:
        if marker in PHASE_MARKERS:
            return PHASE_MARKERS[marker]
    return None


def _load_issue_log() -> Dict[str, Any]:
    """Load existing issue log or return empty structure."""
    if ISSUE_LOG_JSON.exists():
        with open(ISSUE_LOG_JSON) as f:
            raw = json.load(f)
            # Strip JSON Schema fields if present
            return raw if "issues" in raw else {"meta": {}, "issues": []}
    return {
        "meta": {
            "sprint": "Phase 5 E2E Validation",
            "environment": "remote",
            "base_url": "",
            "last_run": datetime.now(timezone.utc).isoformat(),
            "total_prompts": 40,
            "pass_count": 0,
            "fail_count": 0,
            "partial_count": 0,
            "skip_count": 0,
        },
        "issues": [],
    }


def _save_issue_log(log: Dict[str, Any]) -> None:
    """Write updated issue log to disk."""
    TEST_RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(ISSUE_LOG_JSON, "w") as f:
        json.dump(log, f, indent=2, default=str)


def _append_to_markdown(issue: Dict[str, Any]) -> None:
    """Append a new issue entry to the markdown issue log."""
    if not ISSUE_LOG_MD.exists():
        return

    content = ISSUE_LOG_MD.read_text()

    entry = (
        f"\n## {issue['id']}\n"
        f"- **Prompt:** `{issue['prompt']}`\n"
        f"- **Category:** {issue['category']}\n"
        f"- **Result:** {issue['result'].upper()}\n"
        f"- **Expected:** {issue.get('expected', '—')}\n"
        f"- **Actual:** {issue.get('actual', '—')}\n"
        f"- **Root Cause:** {issue.get('root_cause', 'Under investigation')}\n"
        f"- **Phase:** {issue.get('fix_phase', '?')}\n"
        f"- **Logged:** {issue['logged']}\n"
    )

    # Insert before "## Resolved Issues" section
    if "## Resolved Issues" in content:
        content = content.replace("## Resolved Issues", entry + "\n---\n\n## Resolved Issues")
    else:
        content += entry

    ISSUE_LOG_MD.write_text(content)


# ---------------------------------------------------------------------------
# Main processing
# ---------------------------------------------------------------------------

def process_report(report_path: Path, dry_run: bool = False) -> int:
    """Process a pytest JSON report and log new failures.

    Returns the number of new issues logged.
    """
    with open(report_path) as f:
        report = json.load(f)

    log = _load_issue_log()
    existing_prompts = {i["prompt"] for i in log["issues"]}

    # Update meta stats
    summary = report.get("summary", {})
    log["meta"]["last_run"] = datetime.now(timezone.utc).isoformat()
    log["meta"]["pass_count"] = summary.get("passed", 0)
    log["meta"]["fail_count"] = summary.get("failed", 0)
    log["meta"]["skip_count"] = summary.get("skipped", 0)

    new_issues: List[Dict[str, Any]] = []
    now = datetime.now(timezone.utc).isoformat()

    for test in report.get("tests", []):
        if test.get("outcome") not in {"failed", "error"}:
            continue

        node_id: str = test.get("nodeid", "")
        prompt = _extract_prompt_from_test_name(node_id.split("::")[-1])
        category = _extract_category(node_id)
        markers = [m["name"] for m in test.get("markers", [])]
        phase = _extract_phase(markers)

        # Skip if already logged
        if prompt in existing_prompts:
            print(f"  [skip] Already logged: {prompt[:60]}")
            continue

        # Extract failure message
        call = test.get("call", {})
        longrepr = call.get("longrepr", "") or ""
        actual = longrepr[:300] if longrepr else "See pytest output"

        issue_id = _next_issue_id(log["issues"] + new_issues)
        issue: Dict[str, Any] = {
            "id": issue_id,
            "prompt": prompt,
            "category": category,
            "result": "fail",
            "expected": "Structured HTML response without error content",
            "actual": actual,
            "root_cause": "Under investigation",
            "fix_phase": phase,
            "fix_description": None,
            "tools_called": [],
            "tools_expected": [],
            "response_time_ms": None,
            "logged": now,
            "resolved": None,
            "status": "open",
        }
        new_issues.append(issue)
        print(f"  [new]  {issue_id}: {prompt[:60]}")

    if not new_issues:
        print("No new failures to log.")
        return 0

    if dry_run:
        print(f"\n[dry-run] Would log {len(new_issues)} new issue(s):")
        for i in new_issues:
            print(f"  {i['id']}: {i['prompt'][:70]}")
        return len(new_issues)

    log["issues"].extend(new_issues)
    _save_issue_log(log)

    for issue in new_issues:
        _append_to_markdown(issue)

    print(f"\nLogged {len(new_issues)} new issue(s) to {ISSUE_LOG_JSON}")
    return len(new_issues)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Log SRE test failures to issue log")
    parser.add_argument("report", type=Path, help="Path to pytest JSON report file")
    parser.add_argument(
        "--dry-run", action="store_true", help="Show what would be logged without writing"
    )
    args = parser.parse_args()

    if not args.report.exists():
        print(f"Error: Report file not found: {args.report}", file=sys.stderr)
        sys.exit(1)

    count = process_report(args.report, dry_run=args.dry_run)
    sys.exit(0 if count >= 0 else 1)


if __name__ == "__main__":
    main()
