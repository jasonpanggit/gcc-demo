"""Unit tests for the manifest quality scorecard analyzer.

Verifies:
- Scoring engine produces correct scores for known manifests
- Scorecard builder aggregates correctly
- Output formatters produce valid content (Markdown, JSON, HTML)
- Recommendations are generated based on actual gaps

Markers:
    unit: No external dependencies required.
"""
from __future__ import annotations

import json

import pytest

try:
    from app.agentic.eol.utils.manifest_quality_analyzer import (
        QualityIssue,
        Scorecard,
        Severity,
        ToolScore,
        _score_manifest,
        build_scorecard,
        format_html,
        format_json,
        format_markdown,
    )
    from app.agentic.eol.utils.tool_manifest_index import (
        ToolAffordance,
        ToolManifest,
    )
except ModuleNotFoundError:
    from utils.manifest_quality_analyzer import (  # type: ignore[import-not-found]
        QualityIssue,
        Scorecard,
        Severity,
        ToolScore,
        _score_manifest,
        build_scorecard,
        format_html,
        format_json,
        format_markdown,
    )
    from utils.tool_manifest_index import (  # type: ignore[import-not-found]
        ToolAffordance,
        ToolManifest,
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _perfect_manifest() -> ToolManifest:
    """Create a manifest that should score 100%."""
    return ToolManifest(
        tool_name="perfect_tool",
        source="sre",
        domains=frozenset({"sre_health"}),
        tags=frozenset({"health", "diagnostics", "resource"}),
        affordance=ToolAffordance.READ,
        example_queries=(
            "check health of my container app",
            "is my VM healthy right now",
            "what is the health status of my AKS cluster",
        ),
        conflicts_with=frozenset(),
        conflict_note="",
        preferred_over=frozenset(),
    )


def _minimal_manifest() -> ToolManifest:
    """Create a manifest with bare minimum to test gap detection."""
    return ToolManifest(
        tool_name="minimal_tool",
        source="azure",
        domains=frozenset({"azure_management"}),
        tags=frozenset({"vm"}),
        affordance=ToolAffordance.READ,
        example_queries=("list VMs",),
        conflicts_with=frozenset(),
        conflict_note="",
        preferred_over=frozenset(),
    )


def _conflict_no_note_manifest() -> ToolManifest:
    """Create a manifest with conflicts_with but no conflict_note."""
    return ToolManifest(
        tool_name="conflict_no_note",
        source="sre",
        domains=frozenset({"sre_health"}),
        tags=frozenset({"health", "diagnostics", "check"}),
        affordance=ToolAffordance.READ,
        example_queries=(
            "check health of my resource",
            "is my container app healthy",
            "diagnose my AKS cluster",
        ),
        conflicts_with=frozenset({"resourcehealth"}),
        conflict_note="",
        preferred_over=frozenset(),
    )


def _destructive_no_confirm_manifest() -> ToolManifest:
    """DESTRUCTIVE tool without requires_confirmation."""
    return ToolManifest(
        tool_name="unsafe_restart",
        source="sre",
        domains=frozenset({"sre_remediation"}),
        tags=frozenset({"restart", "destructive", "remediation"}),
        affordance=ToolAffordance.DESTRUCTIVE,
        example_queries=(
            "restart my container app immediately",
            "force restart the service",
            "reboot my production VM right now",
        ),
        conflicts_with=frozenset(),
        conflict_note="",
        preferred_over=frozenset(),
        requires_confirmation=False,
    )


# ---------------------------------------------------------------------------
# Score engine tests
# ---------------------------------------------------------------------------

class TestScoreManifest:

    @pytest.mark.unit
    def test_perfect_manifest_scores_100(self):
        ts = _score_manifest(_perfect_manifest())
        assert ts.score == 100
        assert ts.grade == "A+"
        assert len(ts.issues) == 0

    @pytest.mark.unit
    def test_minimal_manifest_has_critical_issues(self):
        ts = _score_manifest(_minimal_manifest())
        assert ts.score < 100
        assert len(ts.critical_issues) > 0
        # Should flag: insufficient example text, too few queries
        issue_fields = {i.field_name for i in ts.critical_issues}
        assert "example_queries" in issue_fields

    @pytest.mark.unit
    def test_minimal_manifest_has_minor_issues(self):
        ts = _score_manifest(_minimal_manifest())
        assert len(ts.minor_issues) > 0
        # Should flag: too few tags, too few queries
        minor_fields = {i.field_name for i in ts.minor_issues}
        assert "tags" in minor_fields or "example_queries" in minor_fields

    @pytest.mark.unit
    def test_conflict_without_note_is_major(self):
        ts = _score_manifest(_conflict_no_note_manifest())
        assert len(ts.major_issues) > 0
        major_fields = {i.field_name for i in ts.major_issues}
        assert "conflict_note" in major_fields

    @pytest.mark.unit
    def test_destructive_without_confirmation_flagged(self):
        ts = _score_manifest(_destructive_no_confirm_manifest())
        confirm_issues = [i for i in ts.issues if i.field_name == "requires_confirmation"]
        assert len(confirm_issues) == 1
        assert confirm_issues[0].severity == Severity.MAJOR

    @pytest.mark.unit
    def test_score_has_valid_grade(self):
        ts = _score_manifest(_perfect_manifest())
        assert ts.grade in ("A+", "A", "B", "C", "D", "F")

    @pytest.mark.unit
    def test_tool_score_to_dict(self):
        ts = _score_manifest(_perfect_manifest())
        d = ts.to_dict()
        assert "tool_name" in d
        assert "score" in d
        assert "grade" in d
        assert "issues" in d
        assert "issue_counts" in d

    @pytest.mark.unit
    def test_score_percentage(self):
        ts = ToolScore(tool_name="test", source="sre", score=85, max_score=100)
        assert ts.percentage == 85.0


# ---------------------------------------------------------------------------
# Scorecard builder tests (integration with real manifests)
# ---------------------------------------------------------------------------

class TestBuildScorecard:

    @pytest.mark.unit
    def test_scorecard_has_tools(self):
        sc = build_scorecard()
        assert sc.total_tools > 0

    @pytest.mark.unit
    def test_scorecard_has_overall_score(self):
        sc = build_scorecard()
        assert 0 <= sc.overall_score <= 100

    @pytest.mark.unit
    def test_scorecard_has_sources(self):
        sc = build_scorecard()
        assert len(sc.by_source) > 0
        assert "sre" in sc.by_source

    @pytest.mark.unit
    def test_scorecard_has_domains(self):
        sc = build_scorecard()
        assert len(sc.by_domain) > 0

    @pytest.mark.unit
    def test_scorecard_has_recommendations(self):
        sc = build_scorecard()
        assert len(sc.recommendations) > 0

    @pytest.mark.unit
    def test_scorecard_has_top_gaps(self):
        sc = build_scorecard()
        assert len(sc.top_gaps) > 0
        assert len(sc.top_gaps) <= 10

    @pytest.mark.unit
    def test_scorecard_issue_summary(self):
        sc = build_scorecard()
        assert "total" in sc.issue_summary
        assert "critical" in sc.issue_summary
        assert sc.issue_summary["total"] == (
            sc.issue_summary["critical"]
            + sc.issue_summary["major"]
            + sc.issue_summary["minor"]
        )

    @pytest.mark.unit
    def test_scorecard_to_dict(self):
        sc = build_scorecard()
        d = sc.to_dict()
        assert "generated_at" in d
        assert "total_tools" in d
        assert "overall_score" in d
        assert "tool_scores" in d
        assert isinstance(d["tool_scores"], list)

    @pytest.mark.unit
    def test_scorecard_generated_at_is_set(self):
        sc = build_scorecard()
        assert len(sc.generated_at) > 0
        assert "UTC" in sc.generated_at


# ---------------------------------------------------------------------------
# Output formatter tests
# ---------------------------------------------------------------------------

class TestFormatters:

    @pytest.fixture(scope="class")
    def scorecard(self):
        return build_scorecard()

    @pytest.mark.unit
    def test_format_json_valid(self, scorecard):
        output = format_json(scorecard)
        parsed = json.loads(output)
        assert parsed["total_tools"] == scorecard.total_tools
        assert parsed["overall_score"] == scorecard.overall_score

    @pytest.mark.unit
    def test_format_markdown_has_headers(self, scorecard):
        output = format_markdown(scorecard)
        assert "# Manifest Quality Scorecard" in output
        assert "## Issue Summary" in output
        assert "## Score by MCP Source" in output
        assert "## Recommendations" in output

    @pytest.mark.unit
    def test_format_markdown_has_tool_count(self, scorecard):
        output = format_markdown(scorecard)
        assert str(scorecard.total_tools) in output

    @pytest.mark.unit
    def test_format_html_is_valid(self, scorecard):
        output = format_html(scorecard)
        assert "<!DOCTYPE html>" in output
        assert "<h1>Manifest Quality Scorecard</h1>" in output
        assert "</html>" in output

    @pytest.mark.unit
    def test_format_html_has_tables(self, scorecard):
        output = format_html(scorecard)
        assert "<table>" in output
        assert "</table>" in output

    @pytest.mark.unit
    def test_format_json_roundtrip(self, scorecard):
        """JSON output must round-trip cleanly."""
        output = format_json(scorecard)
        parsed = json.loads(output)
        # Re-serialize and re-parse to ensure clean round-trip
        output2 = json.dumps(parsed, indent=2)
        parsed2 = json.loads(output2)
        assert parsed == parsed2
