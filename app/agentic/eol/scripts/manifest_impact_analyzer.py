#!/usr/bin/env python3
"""Manifest change impact analyzer for MCP tool manifests.

Compares manifest state between two git refs (or HEAD vs working tree)
to show which tools changed and how those changes affect golden scenario
routing. Designed for CI PR comments.

Exit codes:
    0 - Analysis complete, no regressions detected
    1 - Potential regressions detected (golden scenarios affected)
    2 - Script error

Usage:
    python scripts/manifest_impact_analyzer.py
    python scripts/manifest_impact_analyzer.py --base main --head HEAD
    python scripts/manifest_impact_analyzer.py --golden-dir tests/fixtures/golden/
    python scripts/manifest_impact_analyzer.py --json
    python scripts/manifest_impact_analyzer.py --github-summary "$GITHUB_STEP_SUMMARY"
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

# Add the app directory to sys.path for imports
_APP_DIR = Path(__file__).resolve().parent.parent
if str(_APP_DIR) not in sys.path:
    sys.path.insert(0, str(_APP_DIR))


# Manifest file paths relative to repo root
MANIFEST_PATHS = [
    "app/agentic/eol/utils/manifests/azure_manifests.py",
    "app/agentic/eol/utils/manifests/cli_manifests.py",
    "app/agentic/eol/utils/manifests/compute_manifests.py",
    "app/agentic/eol/utils/manifests/inventory_manifests.py",
    "app/agentic/eol/utils/manifests/monitor_manifests.py",
    "app/agentic/eol/utils/manifests/network_manifests.py",
    "app/agentic/eol/utils/manifests/sre_manifests.py",
    "app/agentic/eol/utils/manifests/storage_manifests.py",
]


@dataclass
class ManifestChange:
    """A single manifest file change."""
    file_path: str
    change_type: str  # "added", "modified", "deleted"
    diff_summary: str = ""  # Short summary of what changed
    lines_added: int = 0
    lines_removed: int = 0


@dataclass
class ToolImpact:
    """Impact assessment for a specific tool."""
    tool_name: str
    source: str
    fields_changed: List[str] = field(default_factory=list)
    risk_level: str = "low"  # "low", "medium", "high"
    affected_scenarios: List[str] = field(default_factory=list)
    notes: str = ""


@dataclass
class ImpactReport:
    """Complete impact analysis report."""
    manifest_changes: List[ManifestChange] = field(default_factory=list)
    tool_impacts: List[ToolImpact] = field(default_factory=list)
    total_manifests_changed: int = 0
    total_tools_affected: int = 0
    high_risk_count: int = 0
    medium_risk_count: int = 0
    low_risk_count: int = 0
    scenarios_at_risk: List[str] = field(default_factory=list)
    has_regressions: bool = False


def detect_manifest_changes(base: str = "main", head: str = "HEAD") -> List[ManifestChange]:
    """Detect which manifest files changed between two git refs."""
    changes: List[ManifestChange] = []

    # Get repo root
    try:
        repo_root = subprocess.check_output(
            ["git", "rev-parse", "--show-toplevel"],
            text=True, stderr=subprocess.DEVNULL
        ).strip()
    except subprocess.CalledProcessError:
        # Not in a git repo, check for uncommitted changes
        return _detect_changes_no_git()

    for manifest_path in MANIFEST_PATHS:
        full_path = Path(repo_root) / manifest_path
        if not full_path.exists():
            continue

        # Check if file changed between base and head
        try:
            result = subprocess.run(
                ["git", "diff", "--stat", f"{base}...{head}", "--", manifest_path],
                capture_output=True, text=True, cwd=repo_root
            )
            if result.stdout.strip():
                # Get line counts
                diff_result = subprocess.run(
                    ["git", "diff", "--numstat", f"{base}...{head}", "--", manifest_path],
                    capture_output=True, text=True, cwd=repo_root
                )
                lines_added, lines_removed = 0, 0
                if diff_result.stdout.strip():
                    parts = diff_result.stdout.strip().split("\t")
                    if len(parts) >= 2:
                        lines_added = int(parts[0]) if parts[0] != "-" else 0
                        lines_removed = int(parts[1]) if parts[1] != "-" else 0

                changes.append(ManifestChange(
                    file_path=manifest_path,
                    change_type="modified",
                    diff_summary=result.stdout.strip().split("\n")[0],
                    lines_added=lines_added,
                    lines_removed=lines_removed,
                ))
        except subprocess.CalledProcessError:
            pass

    # Also check for working tree changes (uncommitted)
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only"],
            capture_output=True, text=True, cwd=repo_root
        )
        for line in result.stdout.splitlines():
            line = line.strip()
            if line in [m for m in MANIFEST_PATHS]:
                # Check if already tracked from ref comparison
                if not any(c.file_path == line for c in changes):
                    changes.append(ManifestChange(
                        file_path=line,
                        change_type="modified (uncommitted)",
                    ))
    except subprocess.CalledProcessError:
        pass

    return changes


def _detect_changes_no_git() -> List[ManifestChange]:
    """Fallback: just report all manifest files as present (no git)."""
    changes = []
    for manifest_path in MANIFEST_PATHS:
        if Path(manifest_path).exists() or Path(_APP_DIR / manifest_path.replace("app/agentic/eol/", "")).exists():
            changes.append(ManifestChange(
                file_path=manifest_path,
                change_type="present (no git)",
            ))
    return changes


def analyze_tool_impacts(changes: List[ManifestChange]) -> List[ToolImpact]:
    """Analyze which tools are affected by manifest changes."""
    impacts: List[ToolImpact] = []

    # Load current manifest index to find tools from changed files
    try:
        from utils.tool_manifest_index import get_tool_manifest_index
        index = get_tool_manifest_index()
    except Exception:
        return impacts

    # Map source files to source names
    file_to_source = {
        "azure_manifests.py": "azure",
        "cli_manifests.py": "azure_cli",
        "compute_manifests.py": "compute",
        "inventory_manifests.py": "inventory",
        "monitor_manifests.py": "monitor",
        "network_manifests.py": "network",
        "sre_manifests.py": "sre",
        "storage_manifests.py": "storage",
    }

    affected_sources: Set[str] = set()
    for change in changes:
        filename = Path(change.file_path).name
        if filename in file_to_source:
            affected_sources.add(file_to_source[filename])

    # Find all tools from affected sources
    for name in index.all_tool_names():
        manifest = index.get(name)
        if manifest is None:
            continue
        if manifest.source in affected_sources:
            # Assess risk based on what fields are typically important
            risk = "low"
            fields: list[str] = []
            notes = ""

            # High-risk fields: example_queries, tags, domains (affect retrieval)
            if manifest.example_queries:
                fields.append("example_queries")
            if manifest.tags:
                fields.append("tags")
            if manifest.domains:
                fields.append("domains")

            # Medium-risk: conflicts_with, preferred_over (affect disambiguation)
            if manifest.conflicts_with:
                fields.append("conflicts_with")
                risk = "medium"
            if manifest.preferred_over:
                fields.append("preferred_over")

            # Without git diff of individual fields, flag based on change magnitude
            for change in changes:
                if Path(change.file_path).name == f"{manifest.source}_manifests.py":
                    if change.lines_added + change.lines_removed > 20:
                        risk = "high"
                        notes = f"Large change: +{change.lines_added}/-{change.lines_removed} lines"
                    elif change.lines_added + change.lines_removed > 5:
                        risk = "medium"

            impacts.append(ToolImpact(
                tool_name=name,
                source=manifest.source,
                fields_changed=fields,
                risk_level=risk,
                notes=notes,
            ))

    return impacts


def find_affected_scenarios(
    impacts: List[ToolImpact],
    golden_dir: str,
) -> List[str]:
    """Find golden scenarios that reference any affected tool."""
    affected: List[str] = []
    affected_tools = {i.tool_name for i in impacts}

    golden_path = Path(golden_dir)
    if not golden_path.exists():
        return affected

    try:
        import yaml
    except ImportError:
        return affected

    for yaml_file in sorted(golden_path.glob("*.yaml")):
        try:
            with open(yaml_file) as f:
                scenario = yaml.safe_load(f)
            if not scenario:
                continue

            scenario_id = scenario.get("scenario", {}).get("id", yaml_file.stem)
            expected_tools = set()

            tools_section = scenario.get("expected", {}).get("tools", {})
            for key in ("required", "preferred", "forbidden"):
                expected_tools.update(tools_section.get(key, []))

            if affected_tools & expected_tools:
                affected.append(scenario_id)
                # Update impacts with scenario references
                for impact in impacts:
                    if impact.tool_name in expected_tools:
                        impact.affected_scenarios.append(scenario_id)
        except Exception:
            pass

    return affected


def generate_impact_report(
    base: str = "main",
    head: str = "HEAD",
    golden_dir: Optional[str] = None,
) -> ImpactReport:
    """Generate a complete impact analysis report."""
    report = ImpactReport()

    # Step 1: Detect manifest changes
    report.manifest_changes = detect_manifest_changes(base, head)
    report.total_manifests_changed = len(report.manifest_changes)

    if not report.manifest_changes:
        return report

    # Step 2: Analyze tool impacts
    report.tool_impacts = analyze_tool_impacts(report.manifest_changes)
    report.total_tools_affected = len(report.tool_impacts)

    # Step 3: Find affected scenarios
    if golden_dir:
        report.scenarios_at_risk = find_affected_scenarios(
            report.tool_impacts, golden_dir
        )

    # Step 4: Count risk levels
    for impact in report.tool_impacts:
        if impact.risk_level == "high":
            report.high_risk_count += 1
        elif impact.risk_level == "medium":
            report.medium_risk_count += 1
        else:
            report.low_risk_count += 1

    report.has_regressions = report.high_risk_count > 0 or len(report.scenarios_at_risk) > 0

    return report


def format_text(report: ImpactReport) -> str:
    """Format report as human-readable text."""
    lines: list[str] = []
    lines.append("=" * 78)
    lines.append("  Manifest Change Impact Analysis")
    lines.append("=" * 78)
    lines.append("")

    if not report.manifest_changes:
        lines.append("  No manifest changes detected.")
        lines.append("")
        return "\n".join(lines)

    lines.append(f"  Manifests changed:    {report.total_manifests_changed}")
    lines.append(f"  Tools affected:       {report.total_tools_affected}")
    lines.append(f"  High risk:            {report.high_risk_count}")
    lines.append(f"  Medium risk:          {report.medium_risk_count}")
    lines.append(f"  Low risk:             {report.low_risk_count}")
    lines.append(f"  Scenarios at risk:    {len(report.scenarios_at_risk)}")
    lines.append("")

    # Changed files
    lines.append("  Changed Manifest Files:")
    for change in report.manifest_changes:
        lines.append(f"    [{change.change_type}] {change.file_path}")
        if change.lines_added or change.lines_removed:
            lines.append(f"      +{change.lines_added}/-{change.lines_removed} lines")
    lines.append("")

    # High-risk tools
    high_risk = [i for i in report.tool_impacts if i.risk_level == "high"]
    if high_risk:
        lines.append("  HIGH RISK Tools:")
        for imp in high_risk:
            lines.append(f"    {imp.tool_name} ({imp.source})")
            if imp.notes:
                lines.append(f"      Note: {imp.notes}")
            if imp.affected_scenarios:
                lines.append(f"      Scenarios: {', '.join(imp.affected_scenarios)}")
        lines.append("")

    # Scenarios at risk
    if report.scenarios_at_risk:
        lines.append("  Golden Scenarios at Risk:")
        for scenario in report.scenarios_at_risk:
            lines.append(f"    - {scenario}")
        lines.append("")

    lines.append("=" * 78)
    return "\n".join(lines)


def format_json(report: ImpactReport) -> str:
    """Format report as JSON."""
    data = {
        "total_manifests_changed": report.total_manifests_changed,
        "total_tools_affected": report.total_tools_affected,
        "high_risk_count": report.high_risk_count,
        "medium_risk_count": report.medium_risk_count,
        "low_risk_count": report.low_risk_count,
        "has_regressions": report.has_regressions,
        "scenarios_at_risk": report.scenarios_at_risk,
        "manifest_changes": [
            {
                "file_path": c.file_path,
                "change_type": c.change_type,
                "lines_added": c.lines_added,
                "lines_removed": c.lines_removed,
            }
            for c in report.manifest_changes
        ],
        "tool_impacts": [
            {
                "tool_name": i.tool_name,
                "source": i.source,
                "risk_level": i.risk_level,
                "fields_changed": i.fields_changed,
                "affected_scenarios": i.affected_scenarios,
                "notes": i.notes,
            }
            for i in report.tool_impacts
        ],
    }
    return json.dumps(data, indent=2)


def format_github_summary(report: ImpactReport) -> str:
    """Format as GitHub Actions step summary."""
    lines: list[str] = []

    if not report.manifest_changes:
        lines.append("### ℹ️ No manifest changes detected")
        return "\n".join(lines)

    if report.has_regressions:
        icon = "⚠️"
        status = f"{report.high_risk_count} high-risk changes, {len(report.scenarios_at_risk)} scenarios at risk"
    else:
        icon = "✅"
        status = "No regressions detected"

    lines.append(f"### {icon} Manifest Impact: {status}")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append(f"| Manifests changed | {report.total_manifests_changed} |")
    lines.append(f"| Tools affected | {report.total_tools_affected} |")
    lines.append(f"| High risk | {report.high_risk_count} |")
    lines.append(f"| Medium risk | {report.medium_risk_count} |")
    lines.append(f"| Low risk | {report.low_risk_count} |")
    lines.append(f"| Scenarios at risk | {len(report.scenarios_at_risk)} |")
    lines.append("")

    # Changed files
    lines.append("**Changed files:**")
    for change in report.manifest_changes:
        delta = ""
        if change.lines_added or change.lines_removed:
            delta = f" (+{change.lines_added}/-{change.lines_removed})"
        lines.append(f"- `{Path(change.file_path).name}` [{change.change_type}]{delta}")
    lines.append("")

    # High risk details
    high_risk = [i for i in report.tool_impacts if i.risk_level == "high"]
    if high_risk:
        lines.append("<details>")
        lines.append("<summary>High-risk tool changes</summary>")
        lines.append("")
        lines.append("| Tool | Source | Scenarios | Notes |")
        lines.append("|------|--------|-----------|-------|")
        for imp in high_risk:
            scenarios = ", ".join(imp.affected_scenarios) or "none"
            lines.append(f"| `{imp.tool_name}` | {imp.source} | {scenarios} | {imp.notes} |")
        lines.append("")
        lines.append("</details>")

    if report.scenarios_at_risk:
        lines.append("")
        lines.append(f"**Run golden scenarios to verify:** `pytest -m golden -k \"{' or '.join(report.scenarios_at_risk[:5])}\" -v`")

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Manifest change impact analyzer")
    parser.add_argument("--base", type=str, default="main",
                        help="Base git ref (default: main)")
    parser.add_argument("--head", type=str, default="HEAD",
                        help="Head git ref (default: HEAD)")
    parser.add_argument("--golden-dir", type=str, default=None,
                        help="Golden scenario fixture directory")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--github-summary", type=str, default=None,
                        help="Write GitHub step summary to file path")
    args = parser.parse_args()

    try:
        report = generate_impact_report(
            base=args.base,
            head=args.head,
            golden_dir=args.golden_dir,
        )
    except Exception as e:
        print(f"Error generating impact report: {e}", file=sys.stderr)
        return 2

    if args.json:
        print(format_json(report))
    else:
        print(format_text(report))

    if args.github_summary:
        Path(args.github_summary).write_text(format_github_summary(report))

    return 1 if report.has_regressions else 0


if __name__ == "__main__":
    sys.exit(main())
