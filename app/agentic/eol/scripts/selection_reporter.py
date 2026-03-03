#!/usr/bin/env python3
"""Tool selection reporter for diagnosing query→tool routing decisions.

Generates detailed reports showing how queries are routed through the
tool selection pipeline. Designed for CI diagnostic output and
developer debugging.

Exit codes:
    0 - Report generated successfully
    1 - One or more queries had unexpected routing
    2 - Script error

Usage:
    python scripts/selection_reporter.py --query "show my container apps"
    python scripts/selection_reporter.py --queries-file failed_queries.txt
    python scripts/selection_reporter.py --golden-dir tests/fixtures/golden/
    python scripts/selection_reporter.py --json
    python scripts/selection_reporter.py --github-summary "$GITHUB_STEP_SUMMARY"
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

# Add the app directory to sys.path for imports
_APP_DIR = Path(__file__).resolve().parent.parent
if str(_APP_DIR) not in sys.path:
    sys.path.insert(0, str(_APP_DIR))


@dataclass
class ToolSelectionTrace:
    """Full trace of a single query through the routing pipeline."""
    query: str
    domain: str
    confidence: float
    strategy: str
    orchestrator: str
    tools_selected: List[str]
    tool_count: int
    classification_time_ms: float
    secondary_domains: List[str]
    # From ToolRouter.explain()
    active_domains: List[str]
    relevant_sources: List[str]
    # Optional validation against expected
    expected_tools: Optional[List[str]] = None
    expected_domain: Optional[str] = None
    tools_match: Optional[bool] = None
    domain_match: Optional[bool] = None
    missing_tools: List[str] = field(default_factory=list)
    unexpected_tools: List[str] = field(default_factory=list)


@dataclass
class SelectionReport:
    """Aggregated report for multiple queries."""
    total_queries: int = 0
    traces: List[ToolSelectionTrace] = field(default_factory=list)
    pass_count: int = 0
    fail_count: int = 0
    total_time_ms: float = 0.0
    avg_tools_per_query: float = 0.0
    domain_distribution: Dict[str, int] = field(default_factory=dict)
    strategy_distribution: Dict[str, int] = field(default_factory=dict)


async def trace_query(
    query: str,
    expected_tools: Optional[List[str]] = None,
    expected_domain: Optional[str] = None,
    strategy: str = "fast",
) -> ToolSelectionTrace:
    """Trace a single query through the routing pipeline."""
    from utils.unified_router import get_unified_router
    from utils.legacy.tool_router import ToolRouter

    router = get_unified_router()
    plan = await router.route(query, strategy=strategy)

    # Get ToolRouter explanation for domain/source detail
    tool_router = ToolRouter()
    explanation = tool_router.explain(query)

    trace = ToolSelectionTrace(
        query=query,
        domain=plan.domain.value if hasattr(plan.domain, "value") else str(plan.domain),
        confidence=plan.confidence,
        strategy=plan.strategy_used,
        orchestrator=plan.orchestrator,
        tools_selected=plan.tools,
        tool_count=len(plan.tools),
        classification_time_ms=plan.classification_time_ms,
        secondary_domains=[
            d.value if hasattr(d, "value") else str(d)
            for d in plan.secondary_domains
        ],
        active_domains=explanation.get("active_domains", []),
        relevant_sources=explanation.get("relevant_sources", []),
        expected_tools=expected_tools,
        expected_domain=expected_domain,
    )

    # Validate against expected if provided
    if expected_tools is not None:
        selected_set = set(plan.tools)
        expected_set = set(expected_tools)
        trace.missing_tools = sorted(expected_set - selected_set)
        trace.unexpected_tools = sorted(selected_set - expected_set)
        trace.tools_match = len(trace.missing_tools) == 0

    if expected_domain is not None:
        trace.domain_match = trace.domain == expected_domain

    return trace


async def generate_report(
    queries: List[Dict[str, Any]],
    strategy: str = "fast",
) -> SelectionReport:
    """Generate a selection report for multiple queries.

    Args:
        queries: List of dicts with keys:
            - query (str, required)
            - expected_tools (list[str], optional)
            - expected_domain (str, optional)
        strategy: Routing strategy to use.
    """
    report = SelectionReport(total_queries=len(queries))
    total_tools = 0

    for q in queries:
        trace = await trace_query(
            query=q["query"],
            expected_tools=q.get("expected_tools"),
            expected_domain=q.get("expected_domain"),
            strategy=strategy,
        )
        report.traces.append(trace)
        total_tools += trace.tool_count
        report.total_time_ms += trace.classification_time_ms

        # Track domain distribution
        report.domain_distribution[trace.domain] = (
            report.domain_distribution.get(trace.domain, 0) + 1
        )
        report.strategy_distribution[trace.strategy] = (
            report.strategy_distribution.get(trace.strategy, 0) + 1
        )

        # Pass/fail counting
        if trace.tools_match is not None:
            if trace.tools_match and (trace.domain_match is None or trace.domain_match):
                report.pass_count += 1
            else:
                report.fail_count += 1

    if report.total_queries > 0:
        report.avg_tools_per_query = round(total_tools / report.total_queries, 1)

    return report


def load_golden_queries(golden_dir: str) -> List[Dict[str, Any]]:
    """Load queries from golden scenario YAML files."""
    import yaml

    queries = []
    golden_path = Path(golden_dir)
    if not golden_path.exists():
        return queries

    for yaml_file in sorted(golden_path.glob("*.yaml")):
        try:
            with open(yaml_file) as f:
                scenario = yaml.safe_load(f)
            if not scenario:
                continue

            query_entry: Dict[str, Any] = {
                "query": scenario.get("input", {}).get("query", ""),
                "scenario_id": scenario.get("scenario", {}).get("id", yaml_file.stem),
            }

            expected = scenario.get("expected", {})
            if expected.get("tools", {}).get("required"):
                query_entry["expected_tools"] = expected["tools"]["required"]
            if expected.get("domain"):
                query_entry["expected_domain"] = expected["domain"]

            if query_entry["query"]:
                queries.append(query_entry)
        except Exception as e:
            print(f"Warning: Could not load {yaml_file}: {e}", file=sys.stderr)

    return queries


def format_text(report: SelectionReport) -> str:
    """Format report as human-readable text."""
    lines: list[str] = []
    lines.append("=" * 78)
    lines.append("  Tool Selection Diagnostic Report")
    lines.append("=" * 78)
    lines.append("")
    lines.append(f"  Total queries:      {report.total_queries}")
    lines.append(f"  Passed:             {report.pass_count}")
    lines.append(f"  Failed:             {report.fail_count}")
    lines.append(f"  Avg tools/query:    {report.avg_tools_per_query}")
    lines.append(f"  Total routing time: {report.total_time_ms:.1f}ms")
    lines.append("")

    # Domain distribution
    if report.domain_distribution:
        lines.append("  Domain Distribution:")
        for domain, count in sorted(report.domain_distribution.items(), key=lambda x: -x[1]):
            lines.append(f"    {domain:25s}  {count}")
        lines.append("")

    # Per-query traces
    for i, trace in enumerate(report.traces, 1):
        status = ""
        if trace.tools_match is not None:
            passed = trace.tools_match and (trace.domain_match is None or trace.domain_match)
            status = " PASS" if passed else " FAIL"

        lines.append(f"  --- Query {i}{status} ---")
        lines.append(f"  Query:        {trace.query}")
        lines.append(f"  Domain:       {trace.domain} (confidence: {trace.confidence:.2f})")
        lines.append(f"  Orchestrator: {trace.orchestrator}")
        lines.append(f"  Strategy:     {trace.strategy}")
        lines.append(f"  Time:         {trace.classification_time_ms:.1f}ms")
        lines.append(f"  Tools ({trace.tool_count}):")
        for tool in trace.tools_selected:
            lines.append(f"    - {tool}")

        if trace.active_domains:
            lines.append(f"  Active domains: {', '.join(trace.active_domains)}")
        if trace.relevant_sources:
            lines.append(f"  Relevant sources: {', '.join(trace.relevant_sources)}")
        if trace.secondary_domains:
            lines.append(f"  Secondary domains: {', '.join(trace.secondary_domains)}")

        if trace.expected_tools is not None:
            lines.append(f"  Expected tools: {', '.join(trace.expected_tools)}")
            if trace.missing_tools:
                lines.append(f"  MISSING tools:  {', '.join(trace.missing_tools)}")
            if trace.unexpected_tools:
                lines.append(f"  EXTRA tools:    {', '.join(trace.unexpected_tools)}")

        if trace.expected_domain is not None:
            match_str = "YES" if trace.domain_match else "NO"
            lines.append(f"  Domain match:   {match_str} (expected: {trace.expected_domain})")

        lines.append("")

    lines.append("=" * 78)
    return "\n".join(lines)


def format_json(report: SelectionReport) -> str:
    """Format report as JSON."""
    data = {
        "total_queries": report.total_queries,
        "pass_count": report.pass_count,
        "fail_count": report.fail_count,
        "avg_tools_per_query": report.avg_tools_per_query,
        "total_time_ms": round(report.total_time_ms, 1),
        "domain_distribution": report.domain_distribution,
        "strategy_distribution": report.strategy_distribution,
        "traces": [asdict(t) for t in report.traces],
    }
    return json.dumps(data, indent=2)


def format_github_summary(report: SelectionReport) -> str:
    """Format report as GitHub Actions step summary."""
    lines: list[str] = []

    if report.fail_count > 0:
        icon = "🔴"
        status = f"{report.fail_count} routing mismatches"
    elif report.pass_count > 0:
        icon = "✅"
        status = "All queries routed correctly"
    else:
        icon = "ℹ️"
        status = "Diagnostic report (no expectations set)"

    lines.append(f"### {icon} Tool Selection Diagnostics: {status}")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append(f"| Total queries | {report.total_queries} |")
    lines.append(f"| Passed | {report.pass_count} |")
    lines.append(f"| Failed | {report.fail_count} |")
    lines.append(f"| Avg tools/query | {report.avg_tools_per_query} |")
    lines.append(f"| Total routing time | {report.total_time_ms:.1f}ms |")
    lines.append("")

    # Show failures prominently
    failures = [t for t in report.traces if t.tools_match is False or t.domain_match is False]
    if failures:
        lines.append("#### Failed Queries")
        lines.append("")
        lines.append("| Query | Domain | Expected Tools | Got | Missing |")
        lines.append("|-------|--------|----------------|-----|---------|")
        for t in failures:
            expected = ", ".join(t.expected_tools or [])
            got = ", ".join(t.tools_selected[:5])
            missing = ", ".join(t.missing_tools)
            lines.append(f"| {t.query[:60]} | {t.domain} | `{expected}` | `{got}` | `{missing}` |")
        lines.append("")

    # Domain distribution
    if report.domain_distribution:
        lines.append("<details>")
        lines.append("<summary>Domain distribution</summary>")
        lines.append("")
        lines.append("| Domain | Count |")
        lines.append("|--------|-------|")
        for domain, count in sorted(report.domain_distribution.items(), key=lambda x: -x[1]):
            lines.append(f"| {domain} | {count} |")
        lines.append("")
        lines.append("</details>")

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Tool selection diagnostic reporter")
    parser.add_argument("--query", type=str, help="Single query to trace")
    parser.add_argument("--queries-file", type=str,
                        help="File with one query per line")
    parser.add_argument("--golden-dir", type=str,
                        help="Directory of golden scenario YAML files")
    parser.add_argument("--strategy", choices=["fast", "quality", "comprehensive"],
                        default="fast", help="Routing strategy (default: fast)")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--github-summary", type=str, default=None,
                        help="Write GitHub step summary to file path")
    args = parser.parse_args()

    # Build query list
    queries: List[Dict[str, Any]] = []

    if args.query:
        queries.append({"query": args.query})

    if args.queries_file:
        qpath = Path(args.queries_file)
        if qpath.exists():
            for line in qpath.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    queries.append({"query": line})

    if args.golden_dir:
        queries.extend(load_golden_queries(args.golden_dir))

    if not queries:
        print("Error: No queries provided. Use --query, --queries-file, or --golden-dir",
              file=sys.stderr)
        return 2

    # Generate report
    try:
        report = asyncio.run(generate_report(queries, strategy=args.strategy))
    except Exception as e:
        print(f"Error generating report: {e}", file=sys.stderr)
        return 2

    # Output
    if args.json:
        print(format_json(report))
    else:
        print(format_text(report))

    # GitHub summary
    if args.github_summary:
        Path(args.github_summary).write_text(format_github_summary(report))

    # Exit code: 1 if any failures
    return 1 if report.fail_count > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
