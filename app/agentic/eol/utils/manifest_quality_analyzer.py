"""Manifest quality scorecard analyzer.

Scans all tool manifests and generates a comprehensive quality scorecard
showing metadata completeness, gaps by severity, and prioritized
improvement recommendations.

Usage:
    # From app/agentic/eol directory:
    python -m utils.manifest_quality_analyzer
    python -m utils.manifest_quality_analyzer --format markdown
    python -m utils.manifest_quality_analyzer --format json
    python -m utils.manifest_quality_analyzer --format html --output report.html

    # From repository root:
    python -m app.agentic.eol.utils.manifest_quality_analyzer
"""
from __future__ import annotations

import argparse
import json
import sys
import textwrap
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    from utils.tool_manifest_index import (
        ToolAffordance,
        ToolManifest,
        ToolManifestIndex,
        get_tool_manifest_index,
    )
except ImportError:
    from app.agentic.eol.utils.tool_manifest_index import (  # type: ignore[import-not-found]
        ToolAffordance,
        ToolManifest,
        ToolManifestIndex,
        get_tool_manifest_index,
    )


# ---------------------------------------------------------------------------
# Quality rubric constants (shared with linter)
# ---------------------------------------------------------------------------

MIN_EXAMPLE_QUERY_CHARS = 10
MIN_EXAMPLE_QUERIES = 2
IDEAL_EXAMPLE_QUERIES = 3
MIN_TAGS = 1
IDEAL_TAGS = 3
MIN_TOTAL_EXAMPLE_TEXT = 50
QUALITY_TARGET = 80.0  # Overall quality target percentage


class Severity(str, Enum):
    CRITICAL = "critical"
    MAJOR = "major"
    MINOR = "minor"


@dataclass
class QualityIssue:
    """A single quality issue detected on a tool manifest."""
    tool_name: str
    field_name: str
    severity: str
    message: str
    recommendation: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tool_name": self.tool_name,
            "field": self.field_name,
            "severity": self.severity,
            "message": self.message,
            "recommendation": self.recommendation,
        }


@dataclass
class ToolScore:
    """Quality score for a single tool manifest."""
    tool_name: str
    source: str
    domains: List[str] = field(default_factory=list)
    score: int = 0
    max_score: int = 100
    issues: List[QualityIssue] = field(default_factory=list)

    @property
    def percentage(self) -> float:
        return round((self.score / self.max_score) * 100, 1) if self.max_score else 0.0

    @property
    def grade(self) -> str:
        if self.score >= 95:
            return "A+"
        elif self.score >= 90:
            return "A"
        elif self.score >= 80:
            return "B"
        elif self.score >= 65:
            return "C"
        elif self.score >= 50:
            return "D"
        return "F"

    @property
    def critical_issues(self) -> List[QualityIssue]:
        return [i for i in self.issues if i.severity == Severity.CRITICAL]

    @property
    def major_issues(self) -> List[QualityIssue]:
        return [i for i in self.issues if i.severity == Severity.MAJOR]

    @property
    def minor_issues(self) -> List[QualityIssue]:
        return [i for i in self.issues if i.severity == Severity.MINOR]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tool_name": self.tool_name,
            "source": self.source,
            "domains": self.domains,
            "score": self.score,
            "grade": self.grade,
            "issues": [i.to_dict() for i in self.issues],
            "issue_counts": {
                "critical": len(self.critical_issues),
                "major": len(self.major_issues),
                "minor": len(self.minor_issues),
            },
        }


@dataclass
class Scorecard:
    """Complete quality scorecard for the manifest catalog."""
    generated_at: str = ""
    total_tools: int = 0
    overall_score: float = 0.0
    overall_grade: str = ""
    quality_target: float = QUALITY_TARGET
    meets_target: bool = False
    tool_scores: List[ToolScore] = field(default_factory=list)
    by_source: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    by_domain: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    issue_summary: Dict[str, int] = field(default_factory=dict)
    top_gaps: List[Dict[str, Any]] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "generated_at": self.generated_at,
            "total_tools": self.total_tools,
            "overall_score": self.overall_score,
            "overall_grade": self.overall_grade,
            "quality_target": self.quality_target,
            "meets_target": self.meets_target,
            "by_source": self.by_source,
            "by_domain": self.by_domain,
            "issue_summary": self.issue_summary,
            "top_gaps": self.top_gaps,
            "recommendations": self.recommendations,
            "tool_scores": [s.to_dict() for s in self.tool_scores],
        }


# ---------------------------------------------------------------------------
# Scoring engine
# ---------------------------------------------------------------------------

def _score_manifest(manifest: ToolManifest) -> ToolScore:
    """Score a single ToolManifest against the quality rubric."""
    ts = ToolScore(
        tool_name=manifest.tool_name,
        source=manifest.source,
        domains=sorted(manifest.domains),
        score=0,
        max_score=100,
    )

    total_example_text = sum(len(q) for q in manifest.example_queries)
    n_queries = len(manifest.example_queries)
    valid_affordances = set(ToolAffordance)

    # ── 1. Example queries: total text length ≥50 chars (20 pts) ──
    if total_example_text >= MIN_TOTAL_EXAMPLE_TEXT:
        ts.score += 20
    else:
        ts.issues.append(QualityIssue(
            tool_name=manifest.tool_name,
            field_name="example_queries",
            severity=Severity.CRITICAL,
            message=f"Total example text is {total_example_text} chars (need ≥{MIN_TOTAL_EXAMPLE_TEXT})",
            recommendation=f"Add longer or more diverse example queries. Current: {list(manifest.example_queries)}",
        ))

    # ── 2. ≥2 example queries (15 pts) ──
    if n_queries >= MIN_EXAMPLE_QUERIES:
        ts.score += 15
    else:
        ts.issues.append(QualityIssue(
            tool_name=manifest.tool_name,
            field_name="example_queries",
            severity=Severity.CRITICAL,
            message=f"Has {n_queries} example queries (need ≥{MIN_EXAMPLE_QUERIES})",
            recommendation="Add realistic NL queries that users would type to trigger this tool.",
        ))

    # ── 3. Non-empty tags (10 pts) ──
    if len(manifest.tags) >= MIN_TAGS:
        ts.score += 10
    else:
        ts.issues.append(QualityIssue(
            tool_name=manifest.tool_name,
            field_name="tags",
            severity=Severity.CRITICAL,
            message="No tags defined",
            recommendation="Add semantic tags (e.g. 'health', 'storage', 'list') for retrieval boost.",
        ))

    # ── 4. Non-empty domains (10 pts) ──
    if len(manifest.domains) >= 1:
        ts.score += 10
    else:
        ts.issues.append(QualityIssue(
            tool_name=manifest.tool_name,
            field_name="domains",
            severity=Severity.CRITICAL,
            message="No domains defined",
            recommendation="Assign to at least one domain (e.g. 'sre_health', 'network', 'azure_management').",
        ))

    # ── 5. Valid affordance (10 pts) ──
    if manifest.affordance in valid_affordances:
        ts.score += 10
    else:
        ts.issues.append(QualityIssue(
            tool_name=manifest.tool_name,
            field_name="affordance",
            severity=Severity.CRITICAL,
            message=f"Invalid affordance: {manifest.affordance!r}",
            recommendation=f"Set to one of: {[a.value for a in ToolAffordance]}",
        ))

    # ── 6. Conflict note when conflicts_with is set (15 pts) ──
    if manifest.conflicts_with:
        if manifest.conflict_note and len(manifest.conflict_note.strip()) > 10:
            ts.score += 15
        else:
            ts.issues.append(QualityIssue(
                tool_name=manifest.tool_name,
                field_name="conflict_note",
                severity=Severity.MAJOR,
                message=f"Has conflicts_with={set(manifest.conflicts_with)} but missing/short conflict_note",
                recommendation="Add disambiguation guidance explaining when to use this tool vs. the conflicting tool.",
            ))
    else:
        ts.score += 15

    # ── 7. ≥3 tags (10 pts, advisory) ──
    if len(manifest.tags) >= IDEAL_TAGS:
        ts.score += 10
    else:
        ts.issues.append(QualityIssue(
            tool_name=manifest.tool_name,
            field_name="tags",
            severity=Severity.MINOR,
            message=f"Has {len(manifest.tags)} tags (ideal ≥{IDEAL_TAGS})",
            recommendation="Add more semantic tags to improve matching diversity.",
        ))

    # ── 8. ≥3 example queries (10 pts, advisory) ──
    if n_queries >= IDEAL_EXAMPLE_QUERIES:
        ts.score += 10
    else:
        ts.issues.append(QualityIssue(
            tool_name=manifest.tool_name,
            field_name="example_queries",
            severity=Severity.MINOR,
            message=f"Has {n_queries} example queries (ideal ≥{IDEAL_EXAMPLE_QUERIES})",
            recommendation="Add more diverse example queries for better embedding coverage.",
        ))

    # ── Extra checks (no score impact, advisory) ──
    if manifest.affordance in (ToolAffordance.DESTRUCTIVE, ToolAffordance.DEPLOY):
        if not manifest.requires_confirmation:
            ts.issues.append(QualityIssue(
                tool_name=manifest.tool_name,
                field_name="requires_confirmation",
                severity=Severity.MAJOR,
                message=f"Affordance is {manifest.affordance.value} but requires_confirmation=False",
                recommendation="Set requires_confirmation=True for DESTRUCTIVE/DEPLOY tools.",
            ))

    return ts


# ---------------------------------------------------------------------------
# Scorecard builder
# ---------------------------------------------------------------------------

def build_scorecard() -> Scorecard:
    """Build a complete quality scorecard for all manifests."""
    index = get_tool_manifest_index()
    sc = Scorecard(
        generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
    )

    # Score every tool
    for name in sorted(index.all_tool_names()):
        m = index.get(name)
        if m is not None:
            sc.tool_scores.append(_score_manifest(m))

    sc.total_tools = len(sc.tool_scores)

    if not sc.tool_scores:
        return sc

    # Overall score
    sc.overall_score = round(sum(s.score for s in sc.tool_scores) / len(sc.tool_scores), 1)
    if sc.overall_score >= 95:
        sc.overall_grade = "A+"
    elif sc.overall_score >= 90:
        sc.overall_grade = "A"
    elif sc.overall_score >= 80:
        sc.overall_grade = "B"
    elif sc.overall_score >= 65:
        sc.overall_grade = "C"
    elif sc.overall_score >= 50:
        sc.overall_grade = "D"
    else:
        sc.overall_grade = "F"

    sc.meets_target = sc.overall_score >= sc.quality_target

    # By source
    source_groups: Dict[str, List[ToolScore]] = defaultdict(list)
    for s in sc.tool_scores:
        source_groups[s.source].append(s)

    for source, tools in sorted(source_groups.items()):
        avg = round(sum(t.score for t in tools) / len(tools), 1)
        critical = sum(len(t.critical_issues) for t in tools)
        sc.by_source[source] = {
            "tool_count": len(tools),
            "avg_score": avg,
            "critical_issues": critical,
            "tools": [t.tool_name for t in tools],
        }

    # By domain
    domain_groups: Dict[str, List[ToolScore]] = defaultdict(list)
    for s in sc.tool_scores:
        for d in s.domains:
            domain_groups[d].append(s)

    for domain, tools in sorted(domain_groups.items()):
        avg = round(sum(t.score for t in tools) / len(tools), 1)
        sc.by_domain[domain] = {
            "tool_count": len(tools),
            "avg_score": avg,
        }

    # Issue summary
    all_issues = [i for s in sc.tool_scores for i in s.issues]
    sc.issue_summary = {
        "total": len(all_issues),
        "critical": sum(1 for i in all_issues if i.severity == Severity.CRITICAL),
        "major": sum(1 for i in all_issues if i.severity == Severity.MAJOR),
        "minor": sum(1 for i in all_issues if i.severity == Severity.MINOR),
    }

    # Top gaps: tools with worst scores
    worst = sorted(sc.tool_scores, key=lambda x: x.score)[:10]
    sc.top_gaps = [
        {
            "tool_name": s.tool_name,
            "source": s.source,
            "score": s.score,
            "grade": s.grade,
            "critical_count": len(s.critical_issues),
            "top_issue": s.issues[0].message if s.issues else "N/A",
        }
        for s in worst
    ]

    # Recommendations
    sc.recommendations = _generate_recommendations(sc)

    return sc


def _generate_recommendations(sc: Scorecard) -> List[str]:
    """Generate prioritized improvement recommendations."""
    recs: List[str] = []

    critical_count = sc.issue_summary.get("critical", 0)
    if critical_count > 0:
        recs.append(
            f"FIX {critical_count} critical issue(s) FIRST. These block CI and indicate "
            f"tools with insufficient metadata for reliable retrieval."
        )

    # Find sources with low scores
    low_sources = [
        (src, info) for src, info in sc.by_source.items()
        if info["avg_score"] < QUALITY_TARGET
    ]
    if low_sources:
        for src, info in low_sources:
            recs.append(
                f"Source '{src}' averages {info['avg_score']}% ({info['tool_count']} tools). "
                f"Focus on adding example queries and tags to these tools."
            )

    # Find tools with short example text
    short_example_tools = [
        s for s in sc.tool_scores
        if any(i.field_name == "example_queries" and i.severity == Severity.CRITICAL for i in s.issues)
    ]
    if short_example_tools:
        names = [t.tool_name for t in short_example_tools[:5]]
        recs.append(
            f"{len(short_example_tools)} tool(s) have insufficient example query text. "
            f"Priority: {', '.join(names)}"
            + (f" + {len(short_example_tools) - 5} more" if len(short_example_tools) > 5 else "")
        )

    # Confirmation mismatch
    confirm_issues = [
        s for s in sc.tool_scores
        if any(i.field_name == "requires_confirmation" for i in s.issues)
    ]
    if confirm_issues:
        names = [t.tool_name for t in confirm_issues]
        recs.append(
            f"Safety concern: {len(confirm_issues)} DESTRUCTIVE/DEPLOY tool(s) missing "
            f"requires_confirmation=True: {', '.join(names)}"
        )

    # Tag diversity
    low_tags = sum(
        1 for s in sc.tool_scores
        if any(i.field_name == "tags" and i.severity == Severity.MINOR for i in s.issues)
    )
    if low_tags > 0:
        recs.append(
            f"{low_tags} tool(s) have fewer than {IDEAL_TAGS} tags. "
            f"Adding more tags improves semantic retrieval accuracy."
        )

    if not recs:
        recs.append("All quality targets met! Consider raising the bar.")

    return recs


# ---------------------------------------------------------------------------
# Output formatters
# ---------------------------------------------------------------------------

def format_json(sc: Scorecard) -> str:
    """Render scorecard as JSON."""
    return json.dumps(sc.to_dict(), indent=2, default=str)


def format_markdown(sc: Scorecard) -> str:
    """Render scorecard as Markdown."""
    lines: List[str] = []

    lines.append("# Manifest Quality Scorecard")
    lines.append("")
    lines.append(f"**Generated:** {sc.generated_at}")
    lines.append(f"**Tools Analyzed:** {sc.total_tools}")
    lines.append(f"**Overall Score:** {sc.overall_score}% (Grade: {sc.overall_grade})")
    lines.append(f"**Quality Target:** {sc.quality_target}% {'PASS' if sc.meets_target else 'FAIL'}")
    lines.append("")

    # Issue summary
    lines.append("## Issue Summary")
    lines.append("")
    lines.append(f"| Severity | Count |")
    lines.append(f"|----------|-------|")
    lines.append(f"| Critical | {sc.issue_summary.get('critical', 0)} |")
    lines.append(f"| Major    | {sc.issue_summary.get('major', 0)} |")
    lines.append(f"| Minor    | {sc.issue_summary.get('minor', 0)} |")
    lines.append(f"| **Total** | **{sc.issue_summary.get('total', 0)}** |")
    lines.append("")

    # Score by source
    lines.append("## Score by MCP Source")
    lines.append("")
    lines.append("| Source | Tools | Avg Score | Critical |")
    lines.append("|--------|-------|-----------|----------|")
    for source, info in sorted(sc.by_source.items()):
        lines.append(
            f"| {source} | {info['tool_count']} | {info['avg_score']}% | {info['critical_issues']} |"
        )
    lines.append("")

    # Score by domain
    lines.append("## Score by Domain")
    lines.append("")
    lines.append("| Domain | Tools | Avg Score |")
    lines.append("|--------|-------|-----------|")
    for domain, info in sorted(sc.by_domain.items()):
        lines.append(f"| {domain} | {info['tool_count']} | {info['avg_score']}% |")
    lines.append("")

    # Top gaps
    lines.append("## Top 10 Gaps (Lowest Scores)")
    lines.append("")
    lines.append("| Tool | Source | Score | Grade | Critical | Top Issue |")
    lines.append("|------|--------|-------|-------|----------|-----------|")
    for gap in sc.top_gaps:
        lines.append(
            f"| {gap['tool_name']} | {gap['source']} | {gap['score']}% | {gap['grade']} "
            f"| {gap['critical_count']} | {gap['top_issue']} |"
        )
    lines.append("")

    # Recommendations
    lines.append("## Recommendations")
    lines.append("")
    for i, rec in enumerate(sc.recommendations, 1):
        lines.append(f"{i}. {rec}")
    lines.append("")

    # Per-tool details
    lines.append("## Per-Tool Scores")
    lines.append("")
    lines.append("| Tool | Source | Score | Grade | Critical | Major | Minor |")
    lines.append("|------|--------|-------|-------|----------|-------|-------|")
    for s in sorted(sc.tool_scores, key=lambda x: x.score):
        lines.append(
            f"| {s.tool_name} | {s.source} | {s.score}% | {s.grade} "
            f"| {len(s.critical_issues)} | {len(s.major_issues)} | {len(s.minor_issues)} |"
        )
    lines.append("")

    # Critical issues detail
    all_critical = [i for s in sc.tool_scores for i in s.critical_issues]
    if all_critical:
        lines.append("## Critical Issues Detail")
        lines.append("")
        for issue in all_critical:
            lines.append(f"- **{issue.tool_name}** `{issue.field_name}`: {issue.message}")
            if issue.recommendation:
                lines.append(f"  - Fix: {issue.recommendation}")
        lines.append("")

    return "\n".join(lines)


def format_html(sc: Scorecard) -> str:
    """Render scorecard as a standalone HTML page."""
    md = format_markdown(sc)

    # Build a simple HTML wrapper with basic styling
    html_parts: List[str] = []
    html_parts.append("<!DOCTYPE html>")
    html_parts.append("<html lang='en'><head>")
    html_parts.append("<meta charset='utf-8'>")
    html_parts.append("<title>Manifest Quality Scorecard</title>")
    html_parts.append("<style>")
    html_parts.append(textwrap.dedent("""\
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
               max-width: 1200px; margin: 40px auto; padding: 0 20px; color: #333; }
        h1 { color: #1a73e8; border-bottom: 2px solid #1a73e8; padding-bottom: 10px; }
        h2 { color: #333; margin-top: 2em; }
        table { border-collapse: collapse; width: 100%; margin: 1em 0; }
        th, td { border: 1px solid #ddd; padding: 8px 12px; text-align: left; }
        th { background: #f5f5f5; font-weight: 600; }
        tr:nth-child(even) { background: #fafafa; }
        .score-high { color: #0d652d; font-weight: bold; }
        .score-mid { color: #b45309; font-weight: bold; }
        .score-low { color: #dc2626; font-weight: bold; }
        .badge { display: inline-block; padding: 2px 8px; border-radius: 4px;
                 font-size: 0.85em; font-weight: 600; }
        .badge-pass { background: #d1fae5; color: #065f46; }
        .badge-fail { background: #fee2e2; color: #991b1b; }
        ul { padding-left: 1.5em; }
        li { margin: 0.3em 0; }
        code { background: #f3f4f6; padding: 2px 6px; border-radius: 3px; font-size: 0.9em; }
    """))
    html_parts.append("</style></head><body>")

    # Header
    status_class = "badge-pass" if sc.meets_target else "badge-fail"
    status_text = "PASS" if sc.meets_target else "FAIL"
    html_parts.append(f"<h1>Manifest Quality Scorecard</h1>")
    html_parts.append(f"<p><strong>Generated:</strong> {sc.generated_at} | ")
    html_parts.append(f"<strong>Tools:</strong> {sc.total_tools} | ")
    html_parts.append(f"<strong>Score:</strong> {sc.overall_score}% ({sc.overall_grade}) | ")
    html_parts.append(f"<strong>Target:</strong> {sc.quality_target}% ")
    html_parts.append(f"<span class='badge {status_class}'>{status_text}</span></p>")

    # Issue summary
    html_parts.append("<h2>Issue Summary</h2>")
    html_parts.append("<table><tr><th>Severity</th><th>Count</th></tr>")
    html_parts.append(f"<tr><td>Critical</td><td class='score-low'>{sc.issue_summary.get('critical', 0)}</td></tr>")
    html_parts.append(f"<tr><td>Major</td><td class='score-mid'>{sc.issue_summary.get('major', 0)}</td></tr>")
    html_parts.append(f"<tr><td>Minor</td><td>{sc.issue_summary.get('minor', 0)}</td></tr>")
    html_parts.append(f"<tr><td><strong>Total</strong></td><td><strong>{sc.issue_summary.get('total', 0)}</strong></td></tr>")
    html_parts.append("</table>")

    # Score by source
    html_parts.append("<h2>Score by MCP Source</h2>")
    html_parts.append("<table><tr><th>Source</th><th>Tools</th><th>Avg Score</th><th>Critical Issues</th></tr>")
    for source, info in sorted(sc.by_source.items()):
        score_cls = "score-high" if info['avg_score'] >= 90 else ("score-mid" if info['avg_score'] >= 80 else "score-low")
        html_parts.append(
            f"<tr><td>{source}</td><td>{info['tool_count']}</td>"
            f"<td class='{score_cls}'>{info['avg_score']}%</td><td>{info['critical_issues']}</td></tr>"
        )
    html_parts.append("</table>")

    # Top gaps
    html_parts.append("<h2>Top 10 Gaps</h2>")
    html_parts.append("<table><tr><th>Tool</th><th>Source</th><th>Score</th><th>Grade</th><th>Top Issue</th></tr>")
    for gap in sc.top_gaps:
        score_cls = "score-high" if gap['score'] >= 90 else ("score-mid" if gap['score'] >= 80 else "score-low")
        html_parts.append(
            f"<tr><td>{gap['tool_name']}</td><td>{gap['source']}</td>"
            f"<td class='{score_cls}'>{gap['score']}%</td><td>{gap['grade']}</td>"
            f"<td>{gap['top_issue']}</td></tr>"
        )
    html_parts.append("</table>")

    # Recommendations
    html_parts.append("<h2>Recommendations</h2><ol>")
    for rec in sc.recommendations:
        html_parts.append(f"<li>{rec}</li>")
    html_parts.append("</ol>")

    # Per-tool scores
    html_parts.append("<h2>Per-Tool Scores</h2>")
    html_parts.append("<table><tr><th>Tool</th><th>Source</th><th>Score</th><th>Grade</th>"
                       "<th>Critical</th><th>Major</th><th>Minor</th></tr>")
    for s in sorted(sc.tool_scores, key=lambda x: x.score):
        score_cls = "score-high" if s.score >= 90 else ("score-mid" if s.score >= 80 else "score-low")
        html_parts.append(
            f"<tr><td>{s.tool_name}</td><td>{s.source}</td>"
            f"<td class='{score_cls}'>{s.score}%</td><td>{s.grade}</td>"
            f"<td>{len(s.critical_issues)}</td><td>{len(s.major_issues)}</td>"
            f"<td>{len(s.minor_issues)}</td></tr>"
        )
    html_parts.append("</table>")

    html_parts.append("</body></html>")
    return "\n".join(html_parts)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """Run the manifest quality analyzer from the command line."""
    parser = argparse.ArgumentParser(
        description="Analyze tool manifest quality and generate scorecards",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
        Examples:
          python -m utils.manifest_quality_analyzer              # Markdown to stdout
          python -m utils.manifest_quality_analyzer --format json # JSON to stdout
          python -m utils.manifest_quality_analyzer -o report.md  # Markdown to file
          python -m utils.manifest_quality_analyzer --format html -o report.html
        """),
    )
    parser.add_argument(
        "--format", "-f",
        choices=["markdown", "json", "html"],
        default="markdown",
        help="Output format (default: markdown)",
    )
    parser.add_argument(
        "--output", "-o",
        help="Output file path (default: stdout)",
    )
    parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="Only output the scorecard, suppress progress messages",
    )

    args = parser.parse_args()

    if not args.quiet:
        print("Analyzing tool manifests...", file=sys.stderr)

    scorecard = build_scorecard()

    if not args.quiet:
        print(
            f"Analyzed {scorecard.total_tools} tools. "
            f"Overall: {scorecard.overall_score}% ({scorecard.overall_grade}). "
            f"Issues: {scorecard.issue_summary.get('critical', 0)} critical, "
            f"{scorecard.issue_summary.get('major', 0)} major, "
            f"{scorecard.issue_summary.get('minor', 0)} minor.",
            file=sys.stderr,
        )

    # Format output
    if args.format == "json":
        output = format_json(scorecard)
    elif args.format == "html":
        output = format_html(scorecard)
    else:
        output = format_markdown(scorecard)

    # Write output
    if args.output:
        Path(args.output).write_text(output, encoding="utf-8")
        if not args.quiet:
            print(f"Report written to: {args.output}", file=sys.stderr)
    else:
        print(output)


if __name__ == "__main__":
    main()
