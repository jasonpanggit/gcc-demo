#!/usr/bin/env python3
"""Manifest quality linter for MCP tool manifests.

Validates that all tool manifests meet minimum quality standards for
reliable tool selection. Designed to run in CI to gate PRs.

Exit codes:
    0 - All checks pass (or only warnings)
    1 - Critical issues found (blocks merge)
    2 - Script error

Usage:
    python scripts/manifest_linter.py [--strict] [--json] [--fail-threshold LEVEL]

    --strict          Treat warnings as errors
    --json            Output results as JSON (for CI artifact upload)
    --fail-threshold  Minimum severity to fail: critical, error, warning (default: error)
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field, asdict
from enum import IntEnum
from pathlib import Path
from typing import List, Optional

# Add the app directory to sys.path for imports
_APP_DIR = Path(__file__).resolve().parent.parent
if str(_APP_DIR) not in sys.path:
    sys.path.insert(0, str(_APP_DIR))


class Severity(IntEnum):
    WARNING = 1
    ERROR = 2
    CRITICAL = 3


@dataclass
class LintIssue:
    tool_name: str
    severity: Severity
    rule: str
    message: str
    fix_hint: str = ""


@dataclass
class LintResult:
    total_manifests: int = 0
    issues: List[LintIssue] = field(default_factory=list)
    passed: int = 0
    warnings: int = 0
    errors: int = 0
    criticals: int = 0

    @property
    def has_critical(self) -> bool:
        return self.criticals > 0

    @property
    def has_errors(self) -> bool:
        return self.errors > 0

    def add(self, issue: LintIssue) -> None:
        self.issues.append(issue)
        if issue.severity == Severity.WARNING:
            self.warnings += 1
        elif issue.severity == Severity.ERROR:
            self.errors += 1
        elif issue.severity == Severity.CRITICAL:
            self.criticals += 1


def lint_manifests() -> LintResult:
    """Load all manifests and lint each one."""
    from utils.tool_manifest_index import get_tool_manifest_index, ToolAffordance

    index = get_tool_manifest_index()
    result = LintResult(total_manifests=len(index))

    all_names = index.all_tool_names()
    all_names_set = set(all_names)

    for name in all_names:
        manifest = index.get(name)
        if manifest is None:
            continue

        issues_before = len(result.issues)

        # ---- Rule 1: tool_name must be non-empty and snake_case ----
        if not name or not name.replace("_", "").replace("-", "").isalnum():
            result.add(LintIssue(
                tool_name=name,
                severity=Severity.CRITICAL,
                rule="TOOL-001",
                message="tool_name is empty or contains invalid characters",
                fix_hint="Use snake_case: lowercase letters, digits, underscores only",
            ))

        # ---- Rule 2: source must be non-empty ----
        if not manifest.source:
            result.add(LintIssue(
                tool_name=name,
                severity=Severity.CRITICAL,
                rule="SRC-001",
                message="source field is empty",
                fix_hint='Set source to one of: "azure", "sre", "network", "compute", "storage", "monitor", "inventory", "os_eol", "azure_cli", "azure_mcp"',
            ))

        # ---- Rule 3: domains must have at least one entry ----
        if not manifest.domains:
            result.add(LintIssue(
                tool_name=name,
                severity=Severity.ERROR,
                rule="DOM-001",
                message="domains is empty",
                fix_hint="Add at least one domain classification (e.g. sre_health, azure_management, network)",
            ))

        # ---- Rule 4: tags must have at least 2 entries ----
        if len(manifest.tags) < 2:
            result.add(LintIssue(
                tool_name=name,
                severity=Severity.ERROR,
                rule="TAG-001",
                message=f"tags has {len(manifest.tags)} entries (minimum 2)",
                fix_hint="Add semantic tags that help with retrieval (e.g. health, container, aks)",
            ))

        # ---- Rule 5: example_queries must have at least 2 entries ----
        if len(manifest.example_queries) < 2:
            result.add(LintIssue(
                tool_name=name,
                severity=Severity.ERROR,
                rule="EX-001",
                message=f"example_queries has {len(manifest.example_queries)} entries (minimum 2)",
                fix_hint="Add 2-4 natural language queries a user would ask to trigger this tool",
            ))

        # ---- Rule 6: example_queries should be unique ----
        lower_queries = [q.lower().strip() for q in manifest.example_queries]
        if len(lower_queries) != len(set(lower_queries)):
            result.add(LintIssue(
                tool_name=name,
                severity=Severity.WARNING,
                rule="EX-002",
                message="example_queries contains duplicate entries",
                fix_hint="Remove duplicate queries and add diverse phrasing",
            ))

        # ---- Rule 7: example_queries should be at least 5 words ----
        for i, query in enumerate(manifest.example_queries):
            if len(query.split()) < 3:
                result.add(LintIssue(
                    tool_name=name,
                    severity=Severity.WARNING,
                    rule="EX-003",
                    message=f'example_queries[{i}] is too short: "{query}"',
                    fix_hint="Queries should be natural language phrases (3+ words)",
                ))
                break  # Only report once per tool

        # ---- Rule 8: conflicts_with references must exist in index ----
        for conflict_name in manifest.conflicts_with:
            if conflict_name not in all_names_set:
                result.add(LintIssue(
                    tool_name=name,
                    severity=Severity.WARNING,
                    rule="CONF-001",
                    message=f'conflicts_with references non-existent tool: "{conflict_name}"',
                    fix_hint=f"Either add a manifest for '{conflict_name}' or remove it from conflicts_with",
                ))

        # ---- Rule 9: preferred_over references must exist in index ----
        for pref_name in manifest.preferred_over:
            if pref_name not in all_names_set:
                result.add(LintIssue(
                    tool_name=name,
                    severity=Severity.WARNING,
                    rule="PREF-001",
                    message=f'preferred_over references non-existent tool: "{pref_name}"',
                    fix_hint=f"Either add a manifest for '{pref_name}' or remove it from preferred_over",
                ))

        # ---- Rule 10: conflicts_with should have conflict_note when non-empty ----
        if manifest.conflicts_with and not manifest.conflict_note:
            result.add(LintIssue(
                tool_name=name,
                severity=Severity.ERROR,
                rule="CONF-002",
                message="conflicts_with is set but conflict_note is empty",
                fix_hint="Add a conflict_note explaining when to use this tool vs its conflicts",
            ))

        # ---- Rule 11: DESTRUCTIVE/DEPLOY tools should require confirmation ----
        if manifest.affordance in (ToolAffordance.DESTRUCTIVE, ToolAffordance.DEPLOY):
            if not manifest.requires_confirmation:
                result.add(LintIssue(
                    tool_name=name,
                    severity=Severity.ERROR,
                    rule="AFF-001",
                    message=f"{manifest.affordance.value} tool does not require confirmation",
                    fix_hint="Set requires_confirmation=True for destructive/deploy tools",
                ))

        # ---- Rule 12: tool_name should not contain uppercase ----
        if name != name.lower():
            result.add(LintIssue(
                tool_name=name,
                severity=Severity.WARNING,
                rule="TOOL-002",
                message="tool_name contains uppercase characters",
                fix_hint="Use lowercase snake_case for tool names",
            ))

        if len(result.issues) == issues_before:
            result.passed += 1

    return result


def format_text(result: LintResult) -> str:
    """Format lint results as human-readable text."""
    lines: list[str] = []
    lines.append("=" * 70)
    lines.append("  Manifest Quality Linter Results")
    lines.append("=" * 70)
    lines.append("")
    lines.append(f"  Total manifests:  {result.total_manifests}")
    lines.append(f"  Passed:           {result.passed}")
    lines.append(f"  Warnings:         {result.warnings}")
    lines.append(f"  Errors:           {result.errors}")
    lines.append(f"  Critical:         {result.criticals}")
    lines.append("")

    if not result.issues:
        lines.append("  All manifests pass quality checks.")
        lines.append("")
        return "\n".join(lines)

    # Group by severity
    for severity in (Severity.CRITICAL, Severity.ERROR, Severity.WARNING):
        severity_issues = [i for i in result.issues if i.severity == severity]
        if not severity_issues:
            continue
        label = severity.name
        lines.append(f"  --- {label} ({len(severity_issues)}) ---")
        for issue in severity_issues:
            lines.append(f"    [{issue.rule}] {issue.tool_name}: {issue.message}")
            if issue.fix_hint:
                lines.append(f"           Fix: {issue.fix_hint}")
        lines.append("")

    lines.append("=" * 70)
    return "\n".join(lines)


def format_json(result: LintResult) -> str:
    """Format lint results as JSON for CI artifacts."""
    data = {
        "total_manifests": result.total_manifests,
        "passed": result.passed,
        "warnings": result.warnings,
        "errors": result.errors,
        "criticals": result.criticals,
        "pass_rate": round(result.passed / max(result.total_manifests, 1) * 100, 1),
        "issues": [
            {
                "tool_name": i.tool_name,
                "severity": i.severity.name.lower(),
                "rule": i.rule,
                "message": i.message,
                "fix_hint": i.fix_hint,
            }
            for i in result.issues
        ],
    }
    return json.dumps(data, indent=2)


def format_github_summary(result: LintResult) -> str:
    """Format results as GitHub Actions step summary markdown."""
    lines: list[str] = []
    pass_rate = round(result.passed / max(result.total_manifests, 1) * 100, 1)

    if result.has_critical:
        status_icon = "🔴"
        status_text = "Critical issues found"
    elif result.has_errors:
        status_icon = "🟡"
        status_text = "Errors found"
    elif result.warnings > 0:
        status_icon = "🟢"
        status_text = "Warnings only"
    else:
        status_icon = "✅"
        status_text = "All checks pass"

    lines.append(f"### {status_icon} Manifest Linter: {status_text}")
    lines.append("")
    lines.append(f"| Metric | Value |")
    lines.append(f"|--------|-------|")
    lines.append(f"| Total manifests | {result.total_manifests} |")
    lines.append(f"| Pass rate | {pass_rate}% |")
    lines.append(f"| Passed | {result.passed} |")
    lines.append(f"| Warnings | {result.warnings} |")
    lines.append(f"| Errors | {result.errors} |")
    lines.append(f"| Critical | {result.criticals} |")
    lines.append("")

    if result.issues:
        lines.append("<details>")
        lines.append("<summary>Issues found</summary>")
        lines.append("")
        lines.append("| Severity | Tool | Rule | Issue |")
        lines.append("|----------|------|------|-------|")
        for issue in sorted(result.issues, key=lambda i: -i.severity):
            sev_icon = {"CRITICAL": "🔴", "ERROR": "🟡", "WARNING": "⚪"}.get(issue.severity.name, "")
            lines.append(f"| {sev_icon} {issue.severity.name} | `{issue.tool_name}` | {issue.rule} | {issue.message} |")
        lines.append("")
        lines.append("</details>")

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Lint MCP tool manifests")
    parser.add_argument("--strict", action="store_true", help="Treat warnings as errors")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--github-summary", type=str, default=None,
                        help="Write GitHub step summary to this file path")
    parser.add_argument("--fail-threshold", choices=["critical", "error", "warning"],
                        default="error", help="Minimum severity to fail (default: error)")
    args = parser.parse_args()

    result = lint_manifests()

    # Output results
    if args.json:
        print(format_json(result))
    else:
        print(format_text(result))

    # Write GitHub step summary if requested
    if args.github_summary:
        summary_path = Path(args.github_summary)
        summary_path.write_text(format_github_summary(result))

    # Determine exit code
    if args.fail_threshold == "critical":
        return 1 if result.has_critical else 0
    elif args.fail_threshold == "error" and not args.strict:
        return 1 if (result.has_critical or result.has_errors) else 0
    else:  # warning or strict mode
        return 1 if (result.has_critical or result.has_errors or result.warnings > 0) else 0


if __name__ == "__main__":
    sys.exit(main())
