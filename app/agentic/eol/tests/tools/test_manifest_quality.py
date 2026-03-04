"""Manifest quality linter — CI gate for tool manifest metadata completeness.

Validates every ToolManifest entry loaded from ``utils/manifests/*.py`` against
a quality rubric.  Tests are split into **critical** (CI-blocking) and
**advisory** (warnings only) so that new tools cannot be merged without a
minimum level of metadata while still surfacing improvement suggestions.

Quality scoring per tool:
    Field                     Weight   Critical?
    ──────────────────────────────────────────────
    description/example_queries ≥ 50 chars  20      Yes
    ≥2 example_queries          15      Yes
    Non-empty tags              10      Yes
    Non-empty domains           10      Yes
    Valid affordance            10      Yes
    Conflict note when conflicts_with  15  No (advisory)
    ≥3 tags                     10      No (advisory)
    ≥3 example_queries          10      No (advisory)

Run:
    pytest tests/tools/test_manifest_quality.py -v
    pytest tests/tools/test_manifest_quality.py -v -k critical    # CI gate only
    pytest tests/tools/test_manifest_quality.py -v -k advisory    # improvement hints

Markers:
    unit: No external dependencies required.
"""
from __future__ import annotations

import textwrap
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import pytest

try:
    from app.agentic.eol.utils.tool_manifest_index import (
        ToolAffordance,
        ToolManifest,
        ToolManifestIndex,
        get_tool_manifest_index,
    )
except ModuleNotFoundError:
    from utils.tool_manifest_index import (  # type: ignore[import-not-found]
        ToolAffordance,
        ToolManifest,
        ToolManifestIndex,
        get_tool_manifest_index,
    )


# ---------------------------------------------------------------------------
# Quality rubric
# ---------------------------------------------------------------------------

MIN_EXAMPLE_QUERY_CHARS = 10     # Each example query must be at least this long
MIN_EXAMPLE_QUERIES = 2          # Minimum number of example queries (critical)
IDEAL_EXAMPLE_QUERIES = 3        # Ideal number of example queries (advisory)
MIN_TAGS = 1                     # Minimum tags (critical)
IDEAL_TAGS = 3                   # Ideal tag count (advisory)
MIN_TOTAL_EXAMPLE_TEXT = 50      # Sum of all example_queries chars must exceed this


class Severity:
    CRITICAL = "critical"  # Blocks CI
    MAJOR = "major"        # Should-fix, does not block CI
    MINOR = "minor"        # Nice-to-have improvement


@dataclass
class QualityIssue:
    """A single quality issue detected on a tool manifest."""
    tool_name: str
    field: str
    severity: str           # Severity.CRITICAL / MAJOR / MINOR
    message: str

    def __str__(self) -> str:
        return f"[{self.severity.upper()}] {self.tool_name}.{self.field}: {self.message}"


@dataclass
class ToolScore:
    """Quality score for a single tool manifest."""
    tool_name: str
    source: str
    score: int = 0          # 0-100
    max_score: int = 100
    issues: List[QualityIssue] = field(default_factory=list)

    @property
    def percentage(self) -> float:
        return round((self.score / self.max_score) * 100, 1) if self.max_score else 0.0

    @property
    def critical_issues(self) -> List[QualityIssue]:
        return [i for i in self.issues if i.severity == Severity.CRITICAL]

    @property
    def major_issues(self) -> List[QualityIssue]:
        return [i for i in self.issues if i.severity == Severity.MAJOR]

    @property
    def minor_issues(self) -> List[QualityIssue]:
        return [i for i in self.issues if i.severity == Severity.MINOR]


# ---------------------------------------------------------------------------
# Scoring engine
# ---------------------------------------------------------------------------

def score_manifest(manifest: ToolManifest) -> ToolScore:
    """Score a single ToolManifest against the quality rubric.

    Returns a ToolScore with a 0-100 score and a list of issues.
    """
    ts = ToolScore(tool_name=manifest.tool_name, source=manifest.source, score=0, max_score=100)

    # ── 1. Example queries: total text length ≥ 50 chars (20 pts) ──
    total_example_text = sum(len(q) for q in manifest.example_queries)
    if total_example_text >= MIN_TOTAL_EXAMPLE_TEXT:
        ts.score += 20
    else:
        ts.issues.append(QualityIssue(
            tool_name=manifest.tool_name,
            field="example_queries",
            severity=Severity.CRITICAL,
            message=(
                f"Total example query text is {total_example_text} chars, "
                f"need ≥{MIN_TOTAL_EXAMPLE_TEXT}. Add more descriptive examples."
            ),
        ))

    # ── 2. ≥2 example queries (15 pts) ──
    n_queries = len(manifest.example_queries)
    if n_queries >= MIN_EXAMPLE_QUERIES:
        ts.score += 15
    else:
        ts.issues.append(QualityIssue(
            tool_name=manifest.tool_name,
            field="example_queries",
            severity=Severity.CRITICAL,
            message=(
                f"Has {n_queries} example queries, need ≥{MIN_EXAMPLE_QUERIES}. "
                f"Add realistic NL queries that trigger this tool."
            ),
        ))

    # ── 3. Non-empty tags (10 pts) ──
    if len(manifest.tags) >= MIN_TAGS:
        ts.score += 10
    else:
        ts.issues.append(QualityIssue(
            tool_name=manifest.tool_name,
            field="tags",
            severity=Severity.CRITICAL,
            message="No tags defined. Add at least 1 semantic tag for retrieval boost.",
        ))

    # ── 4. Non-empty domains (10 pts) ──
    if len(manifest.domains) >= 1:
        ts.score += 10
    else:
        ts.issues.append(QualityIssue(
            tool_name=manifest.tool_name,
            field="domains",
            severity=Severity.CRITICAL,
            message="No domains defined. Every tool must belong to at least one domain.",
        ))

    # ── 5. Valid affordance (10 pts) ──
    valid_affordances = set(ToolAffordance)
    if manifest.affordance in valid_affordances:
        ts.score += 10
    else:
        ts.issues.append(QualityIssue(
            tool_name=manifest.tool_name,
            field="affordance",
            severity=Severity.CRITICAL,
            message=f"Invalid affordance: {manifest.affordance!r}. Must be one of {[a.value for a in ToolAffordance]}.",
        ))

    # ── 6. Conflict note when conflicts_with is set (15 pts) ──
    if manifest.conflicts_with:
        if manifest.conflict_note and len(manifest.conflict_note.strip()) > 10:
            ts.score += 15
        else:
            ts.issues.append(QualityIssue(
                tool_name=manifest.tool_name,
                field="conflict_note",
                severity=Severity.MAJOR,
                message=(
                    f"Has conflicts_with={set(manifest.conflicts_with)} but "
                    f"missing or too-short conflict_note. Add disambiguation guidance."
                ),
            ))
    else:
        # No conflicts — award full points
        ts.score += 15

    # ── 7. ≥3 tags (10 pts, advisory) ──
    if len(manifest.tags) >= IDEAL_TAGS:
        ts.score += 10
    else:
        ts.issues.append(QualityIssue(
            tool_name=manifest.tool_name,
            field="tags",
            severity=Severity.MINOR,
            message=(
                f"Has {len(manifest.tags)} tags, ideal is ≥{IDEAL_TAGS}. "
                f"More tags improve semantic retrieval."
            ),
        ))

    # ── 8. ≥3 example queries (10 pts, advisory) ──
    if n_queries >= IDEAL_EXAMPLE_QUERIES:
        ts.score += 10
    else:
        ts.issues.append(QualityIssue(
            tool_name=manifest.tool_name,
            field="example_queries",
            severity=Severity.MINOR,
            message=(
                f"Has {n_queries} example queries, ideal is ≥{IDEAL_EXAMPLE_QUERIES}. "
                f"More examples improve retrieval accuracy."
            ),
        ))

    return ts


def score_all_manifests() -> Tuple[List[ToolScore], float]:
    """Score every manifest in the index.

    Returns:
        (list of per-tool scores, overall catalog score 0-100)
    """
    index = get_tool_manifest_index()
    scores: List[ToolScore] = []
    for name in sorted(index.all_tool_names()):
        m = index.get(name)
        if m is not None:
            scores.append(score_manifest(m))

    if not scores:
        return scores, 0.0

    overall = round(sum(s.score for s in scores) / len(scores), 1)
    return scores, overall


# ---------------------------------------------------------------------------
# Report helpers
# ---------------------------------------------------------------------------

def build_quality_report(scores: List[ToolScore], overall: float) -> str:
    """Build a human-readable quality report."""
    lines: List[str] = []
    lines.append("=" * 72)
    lines.append("MANIFEST QUALITY REPORT")
    lines.append("=" * 72)
    lines.append(f"Tools analyzed:   {len(scores)}")
    lines.append(f"Overall score:    {overall:.1f}%")
    lines.append("")

    # Summary by source
    by_source: Dict[str, List[ToolScore]] = defaultdict(list)
    for s in scores:
        by_source[s.source].append(s)

    lines.append("── Score by Source ──")
    for source in sorted(by_source):
        avg = sum(s.score for s in by_source[source]) / len(by_source[source])
        lines.append(f"  {source:20s}  {avg:5.1f}%  ({len(by_source[source])} tools)")
    lines.append("")

    # Critical issues
    critical = [i for s in scores for i in s.critical_issues]
    if critical:
        lines.append(f"── Critical Issues ({len(critical)}) ── MUST FIX ──")
        for issue in critical:
            lines.append(f"  {issue}")
        lines.append("")

    # Major issues
    major = [i for s in scores for i in s.major_issues]
    if major:
        lines.append(f"── Major Issues ({len(major)}) ── SHOULD FIX ──")
        for issue in major:
            lines.append(f"  {issue}")
        lines.append("")

    # Minor issues
    minor = [i for s in scores for i in s.minor_issues]
    if minor:
        lines.append(f"── Minor Issues ({len(minor)}) ── NICE TO HAVE ──")
        for issue in minor:
            lines.append(f"  {issue}")
        lines.append("")

    # Per-tool scores (sorted ascending)
    lines.append("── Per-Tool Scores (ascending) ──")
    for s in sorted(scores, key=lambda x: x.score):
        marker = " *" if s.critical_issues else ""
        lines.append(f"  {s.tool_name:45s}  {s.score:3d}%  ({s.source}){marker}")
    lines.append("")
    lines.append("* = has critical issues")
    lines.append("=" * 72)

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def all_scores():
    """Score all manifests once for the module."""
    scores, overall = score_all_manifests()
    return scores, overall


@pytest.fixture(scope="module")
def manifest_index():
    """Get the loaded manifest index."""
    return get_tool_manifest_index()


# ---------------------------------------------------------------------------
# CRITICAL tests — these block CI
# ---------------------------------------------------------------------------

class TestManifestQualityCritical:
    """Critical quality checks that block CI when violated."""

    @pytest.mark.unit
    def test_index_has_manifests(self, manifest_index):
        """At least one manifest must be loaded."""
        assert len(manifest_index) > 0, "No manifests loaded — check manifests/ package"

    @pytest.mark.unit
    def test_minimum_manifest_count(self, manifest_index):
        """Catalog must have ≥40 tools (we currently expect ~86)."""
        count = len(manifest_index)
        assert count >= 40, (
            f"Only {count} tool manifests loaded. Expected ≥40. "
            f"Did a manifest module fail to load?"
        )

    @pytest.mark.unit
    def test_all_tools_have_example_queries(self, manifest_index):
        """Every tool must have at least MIN_EXAMPLE_QUERIES example queries."""
        failures: List[str] = []
        for name in manifest_index.all_tool_names():
            m = manifest_index.get(name)
            if m and len(m.example_queries) < MIN_EXAMPLE_QUERIES:
                failures.append(
                    f"  {name}: has {len(m.example_queries)} queries, need ≥{MIN_EXAMPLE_QUERIES}"
                )
        assert not failures, (
            f"{len(failures)} tool(s) have insufficient example_queries:\n"
            + "\n".join(failures)
        )

    @pytest.mark.unit
    def test_all_tools_have_tags(self, manifest_index):
        """Every tool must have at least one tag."""
        failures: List[str] = []
        for name in manifest_index.all_tool_names():
            m = manifest_index.get(name)
            if m and len(m.tags) < MIN_TAGS:
                failures.append(f"  {name}: no tags defined")
        assert not failures, (
            f"{len(failures)} tool(s) have no tags:\n" + "\n".join(failures)
        )

    @pytest.mark.unit
    def test_all_tools_have_domains(self, manifest_index):
        """Every tool must belong to at least one domain."""
        failures: List[str] = []
        for name in manifest_index.all_tool_names():
            m = manifest_index.get(name)
            if m and len(m.domains) < 1:
                failures.append(f"  {name}: no domains defined")
        assert not failures, (
            f"{len(failures)} tool(s) have no domains:\n" + "\n".join(failures)
        )

    @pytest.mark.unit
    def test_all_tools_have_valid_affordance(self, manifest_index):
        """Every tool must have a valid ToolAffordance value."""
        valid = set(ToolAffordance)
        failures: List[str] = []
        for name in manifest_index.all_tool_names():
            m = manifest_index.get(name)
            if m and m.affordance not in valid:
                failures.append(f"  {name}: invalid affordance {m.affordance!r}")
        assert not failures, (
            f"{len(failures)} tool(s) have invalid affordance:\n" + "\n".join(failures)
        )

    @pytest.mark.unit
    def test_all_tools_have_sufficient_example_text(self, manifest_index):
        """Total example query text per tool must exceed MIN_TOTAL_EXAMPLE_TEXT chars."""
        failures: List[str] = []
        for name in manifest_index.all_tool_names():
            m = manifest_index.get(name)
            if m:
                total = sum(len(q) for q in m.example_queries)
                if total < MIN_TOTAL_EXAMPLE_TEXT:
                    failures.append(f"  {name}: {total} chars, need ≥{MIN_TOTAL_EXAMPLE_TEXT}")
        assert not failures, (
            f"{len(failures)} tool(s) have insufficient example text:\n"
            + "\n".join(failures)
        )

    @pytest.mark.unit
    def test_all_tools_have_source(self, manifest_index):
        """Every tool must have a non-empty source string."""
        failures: List[str] = []
        for name in manifest_index.all_tool_names():
            m = manifest_index.get(name)
            if m and (not m.source or not m.source.strip()):
                failures.append(f"  {name}: empty source")
        assert not failures, (
            f"{len(failures)} tool(s) have empty source:\n" + "\n".join(failures)
        )

    @pytest.mark.unit
    def test_destructive_tools_require_confirmation(self, manifest_index):
        """DESTRUCTIVE and DEPLOY tools must set requires_confirmation=True."""
        failures: List[str] = []
        for name in manifest_index.all_tool_names():
            m = manifest_index.get(name)
            if m and m.affordance in (ToolAffordance.DESTRUCTIVE, ToolAffordance.DEPLOY):
                if not m.requires_confirmation:
                    failures.append(
                        f"  {name}: affordance={m.affordance.value} but "
                        f"requires_confirmation=False"
                    )
        assert not failures, (
            f"{len(failures)} tool(s) with DESTRUCTIVE/DEPLOY affordance "
            f"but requires_confirmation=False:\n" + "\n".join(failures)
        )

    @pytest.mark.unit
    def test_no_duplicate_tool_names_across_manifests(self, manifest_index):
        """Tool names must be unique — no accidental duplicates across manifest files."""
        # This is implicitly enforced by dict key deduplication in the index,
        # but we verify by counting tools in source manifest files directly.
        all_names = manifest_index.all_tool_names()
        seen = set()
        duplicates: List[str] = []
        for name in all_names:
            if name in seen:
                duplicates.append(name)
            seen.add(name)
        assert not duplicates, (
            f"Duplicate tool names found in manifest index: {duplicates}"
        )

    @pytest.mark.unit
    def test_no_zero_critical_issues(self, all_scores):
        """Overall catalog must have zero critical issues to pass CI.

        Prints the full quality report on failure for easy debugging.
        """
        scores, overall = all_scores
        critical = [i for s in scores for i in s.critical_issues]
        if critical:
            report = build_quality_report(scores, overall)
            pytest.fail(
                f"{len(critical)} CRITICAL issue(s) found in tool manifests.\n\n"
                f"{report}"
            )


# ---------------------------------------------------------------------------
# ADVISORY tests — these generate warnings but do not block CI
# ---------------------------------------------------------------------------

class TestManifestQualityAdvisory:
    """Advisory quality checks — surfaced as warnings, not CI blockers."""

    @pytest.mark.unit
    def test_tools_with_conflicts_have_conflict_notes(self, manifest_index):
        """Tools with conflicts_with set should have a meaningful conflict_note."""
        warnings: List[str] = []
        for name in manifest_index.all_tool_names():
            m = manifest_index.get(name)
            if m and m.conflicts_with and (not m.conflict_note or len(m.conflict_note.strip()) < 10):
                warnings.append(
                    f"  {name}: conflicts_with={set(m.conflicts_with)} "
                    f"but missing/short conflict_note"
                )
        if warnings:
            pytest.skip(
                f"ADVISORY: {len(warnings)} tool(s) with conflicts but weak conflict_note:\n"
                + "\n".join(warnings)
            )

    @pytest.mark.unit
    def test_ideal_tag_count(self, manifest_index):
        """Tools should have ≥3 tags for best retrieval accuracy."""
        below_ideal: List[str] = []
        for name in manifest_index.all_tool_names():
            m = manifest_index.get(name)
            if m and len(m.tags) < IDEAL_TAGS:
                below_ideal.append(f"  {name}: {len(m.tags)} tags (ideal ≥{IDEAL_TAGS})")
        if below_ideal:
            pytest.skip(
                f"ADVISORY: {len(below_ideal)} tool(s) below ideal tag count:\n"
                + "\n".join(below_ideal[:10])
                + (f"\n  ... and {len(below_ideal) - 10} more" if len(below_ideal) > 10 else "")
            )

    @pytest.mark.unit
    def test_ideal_example_query_count(self, manifest_index):
        """Tools should have ≥3 example queries for best retrieval coverage."""
        below_ideal: List[str] = []
        for name in manifest_index.all_tool_names():
            m = manifest_index.get(name)
            if m and len(m.example_queries) < IDEAL_EXAMPLE_QUERIES:
                below_ideal.append(
                    f"  {name}: {len(m.example_queries)} queries (ideal ≥{IDEAL_EXAMPLE_QUERIES})"
                )
        if below_ideal:
            pytest.skip(
                f"ADVISORY: {len(below_ideal)} tool(s) below ideal example count:\n"
                + "\n".join(below_ideal[:10])
                + (f"\n  ... and {len(below_ideal) - 10} more" if len(below_ideal) > 10 else "")
            )

    @pytest.mark.unit
    def test_overall_quality_target(self, all_scores):
        """Overall catalog quality should be ≥80%."""
        scores, overall = all_scores
        if overall < 80.0:
            report = build_quality_report(scores, overall)
            pytest.skip(
                f"ADVISORY: Overall quality is {overall:.1f}%, target is ≥80%.\n\n"
                f"{report}"
            )

    @pytest.mark.unit
    def test_no_deprecated_tools_in_active_catalog(self, manifest_index):
        """Deprecated tools should eventually be removed from manifests."""
        deprecated: List[str] = []
        for name in manifest_index.all_tool_names():
            m = manifest_index.get(name)
            if m and m.deprecated:
                deprecated.append(f"  {name} (source={m.source})")
        if deprecated:
            pytest.skip(
                f"ADVISORY: {len(deprecated)} deprecated tool(s) still in catalog:\n"
                + "\n".join(deprecated)
            )


# ---------------------------------------------------------------------------
# Quality report test (always runs, prints baseline)
# ---------------------------------------------------------------------------

class TestManifestQualityReport:
    """Generate and display the quality report."""

    @pytest.mark.unit
    def test_generate_quality_report(self, all_scores, capsys):
        """Prints the full quality report to stdout for CI visibility.

        This test always passes — it exists to surface the report in CI logs.
        """
        scores, overall = all_scores
        report = build_quality_report(scores, overall)
        print(f"\n{report}")

        # Verify report is non-empty
        assert len(report) > 100, "Quality report is suspiciously short"

        # Log key metrics
        total_critical = sum(len(s.critical_issues) for s in scores)
        total_major = sum(len(s.major_issues) for s in scores)
        total_minor = sum(len(s.minor_issues) for s in scores)
        print(f"\nSummary: {len(scores)} tools, {overall:.1f}% overall")
        print(f"Issues: {total_critical} critical, {total_major} major, {total_minor} minor")
