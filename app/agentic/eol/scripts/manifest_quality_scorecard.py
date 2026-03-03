#!/usr/bin/env python3
"""Manifest quality scorecard analyzer for MCP tool manifests.

Generates a comprehensive quality scorecard showing per-tool and aggregate
quality metrics. Designed for CI integration and developer feedback.

Exit codes:
    0 - Scorecard generated successfully
    1 - Quality below threshold
    2 - Script error

Usage:
    python scripts/manifest_quality_scorecard.py [--json] [--min-score SCORE] [--top-gaps N]

    --json          Output results as JSON
    --min-score     Minimum overall score to pass (0-100, default: 50)
    --top-gaps N    Show top N tools needing improvement (default: 20)
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Add the app directory to sys.path for imports
_APP_DIR = Path(__file__).resolve().parent.parent
if str(_APP_DIR) not in sys.path:
    sys.path.insert(0, str(_APP_DIR))


@dataclass
class ToolScore:
    tool_name: str
    source: str
    total_score: float  # 0-100
    breakdown: Dict[str, float] = field(default_factory=dict)
    gaps: List[str] = field(default_factory=list)


@dataclass
class Scorecard:
    overall_score: float = 0.0
    tool_scores: List[ToolScore] = field(default_factory=list)
    distribution: Dict[str, int] = field(default_factory=dict)  # "excellent", "good", etc.
    by_source: Dict[str, float] = field(default_factory=dict)
    total_tools: int = 0
    common_gaps: List[Tuple[str, int]] = field(default_factory=list)  # (gap_description, count)


# ── Scoring weights ──────────────────────────────────────────────────────────

WEIGHTS = {
    "example_queries":   25,  # Diversity and quality of example queries
    "tags":              20,  # Semantic tag coverage
    "conflict_docs":     20,  # Conflict documentation quality
    "domains":           15,  # Domain classification completeness
    "metadata":          10,  # General metadata quality (source, affordance)
    "safety":            10,  # Safety annotations (confirmation for destructive ops)
}


def score_example_queries(manifest) -> Tuple[float, List[str]]:
    """Score example query quality (0-100)."""
    score = 0.0
    gaps: list[str] = []
    queries = manifest.example_queries

    # Count: 0 queries = 0, 1 = 20, 2 = 50, 3 = 75, 4+ = 100
    count_scores = {0: 0, 1: 20, 2: 50, 3: 75}
    score += count_scores.get(len(queries), 100) * 0.4

    # Diversity: check word overlap between queries
    if len(queries) >= 2:
        all_words = [set(q.lower().split()) for q in queries]
        common = all_words[0]
        for ws in all_words[1:]:
            common = common & ws
        unique_ratio = 1.0 - (len(common) / max(len(all_words[0]), 1))
        score += unique_ratio * 100 * 0.3
    elif len(queries) == 1:
        score += 0  # No diversity possible

    # Length: queries should be 3+ words on average
    if queries:
        avg_length = sum(len(q.split()) for q in queries) / len(queries)
        length_score = min(avg_length / 5.0, 1.0) * 100
        score += length_score * 0.3

    if len(queries) < 2:
        gaps.append("Add at least 2 example queries")
    if len(queries) < 4:
        gaps.append(f"Add more example queries (have {len(queries)}, target 4)")

    return min(score, 100), gaps


def score_tags(manifest) -> Tuple[float, List[str]]:
    """Score tag coverage (0-100)."""
    gaps: list[str] = []
    tag_count = len(manifest.tags)

    # Scoring: 0 tags = 0, 1 = 20, 2 = 50, 3 = 75, 4+ = 100
    count_scores = {0: 0, 1: 20, 2: 50, 3: 75}
    score = count_scores.get(tag_count, 100)

    if tag_count < 2:
        gaps.append("Add at least 2 semantic tags")
    if tag_count < 3:
        gaps.append(f"Add more tags for retrieval (have {tag_count}, target 3+)")

    return score, gaps


def score_conflict_docs(manifest) -> Tuple[float, List[str]]:
    """Score conflict documentation quality (0-100)."""
    gaps: list[str] = []

    has_conflicts = bool(manifest.conflicts_with)
    has_note = bool(manifest.conflict_note)
    has_preferred = bool(manifest.preferred_over)

    if not has_conflicts:
        # No conflicts defined - might be fine but could be missing
        # Give partial credit for tools that legitimately have no conflicts
        return 60.0, ["Consider documenting potential tool confusions"]

    score = 0.0

    # Has conflicts_with defined
    score += 30

    # Has conflict_note
    if has_note:
        score += 40
        # Note length quality
        if len(manifest.conflict_note) > 50:
            score += 15
        else:
            gaps.append("Expand conflict_note with more detail (>50 chars)")
    else:
        gaps.append("Add conflict_note explaining disambiguation")

    # Has preferred_over
    if has_preferred:
        score += 15
    else:
        gaps.append("Consider adding preferred_over for clearer priority")

    return score, gaps


def score_domains(manifest) -> Tuple[float, List[str]]:
    """Score domain classification (0-100)."""
    gaps: list[str] = []
    domain_count = len(manifest.domains)

    if domain_count == 0:
        return 0.0, ["Add at least one domain classification"]

    # Most tools should have 1-2 domains
    score = 100.0 if domain_count >= 1 else 0.0

    return score, gaps


def score_metadata(manifest) -> Tuple[float, List[str]]:
    """Score general metadata quality (0-100)."""
    gaps: list[str] = []
    score = 0.0

    # Has source
    if manifest.source:
        score += 50
    else:
        gaps.append("Set source field")

    # Has valid affordance
    score += 50  # Always set (enum)

    return score, gaps


def score_safety(manifest) -> Tuple[float, List[str]]:
    """Score safety annotations (0-100)."""
    from utils.tool_manifest_index import ToolAffordance

    gaps: list[str] = []

    if manifest.affordance in (ToolAffordance.DESTRUCTIVE, ToolAffordance.DEPLOY):
        if manifest.requires_confirmation:
            return 100.0, []
        else:
            return 0.0, ["DESTRUCTIVE/DEPLOY tools must set requires_confirmation=True"]

    if manifest.affordance == ToolAffordance.WRITE:
        if manifest.requires_confirmation:
            return 100.0, []
        else:
            return 70.0, ["Consider requires_confirmation=True for WRITE tools"]

    # READ tools don't need confirmation
    return 100.0, []


def generate_scorecard() -> Scorecard:
    """Generate a quality scorecard for all manifests."""
    from utils.tool_manifest_index import get_tool_manifest_index

    index = get_tool_manifest_index()
    scorecard = Scorecard(total_tools=len(index))

    all_scores: list[float] = []
    source_scores: Dict[str, list[float]] = {}
    gap_counter: Dict[str, int] = {}

    for name in index.all_tool_names():
        manifest = index.get(name)
        if manifest is None:
            continue

        breakdown: Dict[str, float] = {}
        all_gaps: list[str] = []

        # Score each dimension
        scorers = {
            "example_queries": score_example_queries,
            "tags": score_tags,
            "conflict_docs": score_conflict_docs,
            "domains": score_domains,
            "metadata": score_metadata,
            "safety": score_safety,
        }

        weighted_total = 0.0
        for dim, scorer in scorers.items():
            dim_score, dim_gaps = scorer(manifest)
            breakdown[dim] = round(dim_score, 1)
            weighted_total += dim_score * WEIGHTS[dim] / 100
            all_gaps.extend(dim_gaps)

        total_score = round(weighted_total, 1)

        tool_score = ToolScore(
            tool_name=name,
            source=manifest.source,
            total_score=total_score,
            breakdown=breakdown,
            gaps=all_gaps,
        )
        scorecard.tool_scores.append(tool_score)
        all_scores.append(total_score)

        # Track per-source
        if manifest.source not in source_scores:
            source_scores[manifest.source] = []
        source_scores[manifest.source].append(total_score)

        # Track common gaps
        for gap in all_gaps:
            gap_counter[gap] = gap_counter.get(gap, 0) + 1

    # Aggregate
    if all_scores:
        scorecard.overall_score = round(sum(all_scores) / len(all_scores), 1)

    # Distribution
    excellent = sum(1 for s in all_scores if s >= 80)
    good = sum(1 for s in all_scores if 60 <= s < 80)
    fair = sum(1 for s in all_scores if 40 <= s < 60)
    poor = sum(1 for s in all_scores if s < 40)
    scorecard.distribution = {
        "excellent_80_plus": excellent,
        "good_60_79": good,
        "fair_40_59": fair,
        "poor_below_40": poor,
    }

    # Source averages
    for source, scores in source_scores.items():
        scorecard.by_source[source] = round(sum(scores) / len(scores), 1)

    # Common gaps
    scorecard.common_gaps = sorted(gap_counter.items(), key=lambda x: -x[1])

    # Sort tool scores by total (ascending = worst first)
    scorecard.tool_scores.sort(key=lambda t: t.total_score)

    return scorecard


def format_text(scorecard: Scorecard, top_gaps: int = 20) -> str:
    """Format scorecard as human-readable text."""
    lines: list[str] = []
    lines.append("=" * 70)
    lines.append("  Manifest Quality Scorecard")
    lines.append("=" * 70)
    lines.append("")
    lines.append(f"  Overall Score:    {scorecard.overall_score}/100")
    lines.append(f"  Total Tools:      {scorecard.total_tools}")
    lines.append("")
    lines.append("  Distribution:")
    lines.append(f"    Excellent (80+):  {scorecard.distribution.get('excellent_80_plus', 0)}")
    lines.append(f"    Good (60-79):     {scorecard.distribution.get('good_60_79', 0)}")
    lines.append(f"    Fair (40-59):     {scorecard.distribution.get('fair_40_59', 0)}")
    lines.append(f"    Poor (<40):       {scorecard.distribution.get('poor_below_40', 0)}")
    lines.append("")

    # By source
    lines.append("  Average Score by Source:")
    for source, avg in sorted(scorecard.by_source.items(), key=lambda x: -x[1]):
        bar = "#" * int(avg / 5)
        lines.append(f"    {source:20s}  {avg:5.1f}  {bar}")
    lines.append("")

    # Top gaps
    lines.append(f"  Top {top_gaps} Tools Needing Improvement:")
    for i, ts in enumerate(scorecard.tool_scores[:top_gaps], 1):
        lines.append(f"    {i:2d}. {ts.tool_name:40s}  {ts.total_score:5.1f}/100  (source: {ts.source})")
        if ts.gaps:
            for gap in ts.gaps[:3]:  # Show top 3 gaps per tool
                lines.append(f"        - {gap}")
    lines.append("")

    # Common gaps
    if scorecard.common_gaps:
        lines.append("  Most Common Gaps:")
        for gap, count in scorecard.common_gaps[:10]:
            lines.append(f"    [{count:2d} tools] {gap}")
    lines.append("")

    lines.append("=" * 70)
    return "\n".join(lines)


def format_json(scorecard: Scorecard) -> str:
    """Format scorecard as JSON for CI artifacts."""
    data = {
        "overall_score": scorecard.overall_score,
        "total_tools": scorecard.total_tools,
        "distribution": scorecard.distribution,
        "by_source": scorecard.by_source,
        "common_gaps": [{"gap": g, "count": c} for g, c in scorecard.common_gaps],
        "tool_scores": [
            {
                "tool_name": ts.tool_name,
                "source": ts.source,
                "total_score": ts.total_score,
                "breakdown": ts.breakdown,
                "gaps": ts.gaps,
            }
            for ts in scorecard.tool_scores
        ],
    }
    return json.dumps(data, indent=2)


def format_github_summary(scorecard: Scorecard, top_gaps: int = 10) -> str:
    """Format scorecard as GitHub Actions step summary markdown."""
    lines: list[str] = []

    if scorecard.overall_score >= 80:
        icon = "🟢"
    elif scorecard.overall_score >= 60:
        icon = "🟡"
    else:
        icon = "🔴"

    lines.append(f"### {icon} Manifest Quality Score: {scorecard.overall_score}/100")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append(f"| Total tools | {scorecard.total_tools} |")
    lines.append(f"| Excellent (80+) | {scorecard.distribution.get('excellent_80_plus', 0)} |")
    lines.append(f"| Good (60-79) | {scorecard.distribution.get('good_60_79', 0)} |")
    lines.append(f"| Fair (40-59) | {scorecard.distribution.get('fair_40_59', 0)} |")
    lines.append(f"| Poor (<40) | {scorecard.distribution.get('poor_below_40', 0)} |")
    lines.append("")

    # Source breakdown
    lines.append("**Quality by Source:**")
    lines.append("")
    lines.append("| Source | Avg Score |")
    lines.append("|--------|-----------|")
    for source, avg in sorted(scorecard.by_source.items(), key=lambda x: -x[1]):
        lines.append(f"| {source} | {avg}/100 |")
    lines.append("")

    # Top gaps
    if scorecard.tool_scores:
        lines.append(f"<details>")
        lines.append(f"<summary>Top {top_gaps} tools needing improvement</summary>")
        lines.append("")
        lines.append("| # | Tool | Score | Top Gap |")
        lines.append("|---|------|-------|---------|")
        for i, ts in enumerate(scorecard.tool_scores[:top_gaps], 1):
            top_gap = ts.gaps[0] if ts.gaps else "None"
            lines.append(f"| {i} | `{ts.tool_name}` | {ts.total_score} | {top_gap} |")
        lines.append("")
        lines.append("</details>")

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate manifest quality scorecard")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--min-score", type=float, default=50.0,
                        help="Minimum overall score to pass (default: 50)")
    parser.add_argument("--top-gaps", type=int, default=20,
                        help="Show top N tools needing improvement (default: 20)")
    parser.add_argument("--github-summary", type=str, default=None,
                        help="Write GitHub step summary to this file path")
    args = parser.parse_args()

    scorecard = generate_scorecard()

    # Output results
    if args.json:
        print(format_json(scorecard))
    else:
        print(format_text(scorecard, top_gaps=args.top_gaps))

    # Write GitHub step summary if requested
    if args.github_summary:
        summary_path = Path(args.github_summary)
        summary_path.write_text(format_github_summary(scorecard, top_gaps=args.top_gaps))

    # Check threshold
    if scorecard.overall_score < args.min_score:
        print(f"\nFAIL: Overall score {scorecard.overall_score} < threshold {args.min_score}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
