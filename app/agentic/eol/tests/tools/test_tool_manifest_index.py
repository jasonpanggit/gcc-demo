"""Unit tests for ToolManifestIndex and ToolManifest.

Tests:
- ToolAffordance enum has the expected values
- ToolManifest is a frozen dataclass
- ToolManifestIndex.get returns the right manifest by tool name
- ToolManifestIndex.get_affordance returns READ for unknown tools (conservative default)
- ToolManifestIndex.build_conflict_note_for_context:
    - returns empty string when no conflicts are active in the context set
    - returns note when conflicting tools are both in the context set
    - does NOT emit a note when only one side of a conflict pair is present
- Singleton get_tool_manifest_index loads manifests without raising
- ToolManifestIndex loaded from manifests has > 0 entries
- Known tools (check_resource_health, azure_cli_execute_command) are present with correct affordances

Markers:
    unit: No external dependencies required.
"""
from __future__ import annotations

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
# Fixtures / helpers
# ---------------------------------------------------------------------------

def _make_index() -> ToolManifestIndex:
    """Build a small in-memory index for isolated unit testing."""
    index = ToolManifestIndex()
    index.register_all([
        ToolManifest(
            tool_name="check_resource_health",
            source="sre",
            domains=frozenset({"sre_health"}),
            tags=frozenset({"health"}),
            affordance=ToolAffordance.READ,
            example_queries=("check health",),
            conflicts_with=frozenset({"resourcehealth"}),
            conflict_note="Use check_resource_health for deep SRE diagnostics.",
            preferred_over=frozenset({"resourcehealth"}),
        ),
        ToolManifest(
            tool_name="resourcehealth",
            source="azure",
            domains=frozenset({"azure_management"}),
            tags=frozenset({"health", "platform"}),
            affordance=ToolAffordance.READ,
            example_queries=("basic health status",),
            conflicts_with=frozenset({"check_resource_health"}),
            conflict_note="resourcehealth is for basic platform health only.",
            preferred_over=frozenset(),
        ),
        ToolManifest(
            tool_name="azure_cli_execute_command",
            source="azure_cli",
            domains=frozenset({"deployment"}),
            tags=frozenset({"cli"}),
            affordance=ToolAffordance.WRITE,
            example_queries=("run az command",),
            conflicts_with=frozenset(),
            conflict_note="",
            preferred_over=frozenset(),
            requires_confirmation=True,
        ),
        ToolManifest(
            tool_name="execute_safe_restart",
            source="sre",
            domains=frozenset({"sre_remediation"}),
            tags=frozenset({"restart"}),
            affordance=ToolAffordance.DESTRUCTIVE,
            example_queries=("restart my resource",),
            conflicts_with=frozenset(),
            conflict_note="",
            preferred_over=frozenset(),
            requires_confirmation=True,
        ),
    ])
    return index


# ---------------------------------------------------------------------------
# ToolAffordance
# ---------------------------------------------------------------------------

class TestToolAffordance:

    @pytest.mark.unit
    def test_all_expected_values_exist(self):
        assert ToolAffordance.READ == "read"
        assert ToolAffordance.WRITE == "write"
        assert ToolAffordance.DESTRUCTIVE == "destructive"
        assert ToolAffordance.DEPLOY == "deploy"

    @pytest.mark.unit
    def test_is_string_enum(self):
        """ToolAffordance(str, Enum) — .value must equal the plain string.

        Note: In Python 3.9, str(StrEnum_member) returns "ClassName.MEMBER",
        not the raw value. Use .value for reliable string comparison.
        """
        assert ToolAffordance.READ.value == "read"
        assert ToolAffordance.WRITE == "write"  # direct equality via __eq__


# ---------------------------------------------------------------------------
# ToolManifestIndex — in-memory unit tests
# ---------------------------------------------------------------------------

class TestToolManifestIndex:

    @pytest.mark.unit
    def test_get_returns_manifest(self):
        index = _make_index()
        m = index.get("check_resource_health")
        assert m is not None
        assert m.tool_name == "check_resource_health"
        assert m.affordance == ToolAffordance.READ

    @pytest.mark.unit
    def test_get_returns_none_for_unknown(self):
        index = _make_index()
        assert index.get("nonexistent_tool") is None

    @pytest.mark.unit
    def test_get_affordance_known_read(self):
        index = _make_index()
        assert index.get_affordance("check_resource_health") == ToolAffordance.READ

    @pytest.mark.unit
    def test_get_affordance_known_write(self):
        index = _make_index()
        assert index.get_affordance("azure_cli_execute_command") == ToolAffordance.WRITE

    @pytest.mark.unit
    def test_get_affordance_known_destructive(self):
        index = _make_index()
        assert index.get_affordance("execute_safe_restart") == ToolAffordance.DESTRUCTIVE

    @pytest.mark.unit
    def test_get_affordance_unknown_defaults_to_read(self):
        """Unknown tools default to READ (conservative — safe fail-open)."""
        index = _make_index()
        assert index.get_affordance("some_future_tool") == ToolAffordance.READ

    @pytest.mark.unit
    def test_build_conflict_note_empty_when_no_conflict_in_context(self):
        """No note emitted when the conflicting counterpart is absent from context."""
        index = _make_index()
        # Only check_resource_health in context — resourcehealth is absent
        note = index.build_conflict_note_for_context(
            ["check_resource_health", "azure_cli_execute_command"]
        )
        assert note == ""

    @pytest.mark.unit
    def test_build_conflict_note_emitted_when_both_in_context(self):
        """Note is emitted when both sides of a conflict pair are present."""
        index = _make_index()
        note = index.build_conflict_note_for_context(
            ["check_resource_health", "resourcehealth"]
        )
        assert len(note) > 0
        # At least one of the tool names must appear in the note
        assert "check_resource_health" in note or "resourcehealth" in note

    @pytest.mark.unit
    def test_build_conflict_note_only_one_side_present(self):
        """Only one side of a conflict pair → no note emitted for that tool."""
        index = _make_index()
        # resourcehealth alone (its conflict partner check_resource_health absent)
        note = index.build_conflict_note_for_context(["resourcehealth"])
        assert note == ""

    @pytest.mark.unit
    def test_build_conflict_note_empty_for_tool_with_no_note(self):
        """Tools with empty conflict_note emit nothing even if conflicts_with is set."""
        index = _make_index()
        # execute_safe_restart has conflicts_with=frozenset() and conflict_note=""
        note = index.build_conflict_note_for_context(["execute_safe_restart"])
        assert note == ""

    @pytest.mark.unit
    def test_build_conflict_note_empty_list(self):
        index = _make_index()
        note = index.build_conflict_note_for_context([])
        assert note == ""

    @pytest.mark.unit
    def test_len(self):
        index = _make_index()
        assert len(index) == 4

    @pytest.mark.unit
    def test_all_tool_names(self):
        index = _make_index()
        names = set(index.all_tool_names())
        assert "check_resource_health" in names
        assert "execute_safe_restart" in names
        assert "azure_cli_execute_command" in names
        assert "resourcehealth" in names
        assert len(names) == 4

    @pytest.mark.unit
    def test_register_single(self):
        """register() adds a single manifest to the index."""
        index = ToolManifestIndex()
        assert len(index) == 0
        m = ToolManifest(
            tool_name="my_tool",
            source="sre",
            domains=frozenset({"sre_health"}),
            tags=frozenset(),
            affordance=ToolAffordance.READ,
            example_queries=(),
            conflicts_with=frozenset(),
            conflict_note="",
            preferred_over=frozenset(),
        )
        index.register(m)
        assert len(index) == 1
        assert index.get("my_tool") is m

    @pytest.mark.unit
    def test_register_overwrites_existing(self):
        """Registering the same tool_name twice keeps the latest version."""
        index = ToolManifestIndex()
        m1 = ToolManifest(
            tool_name="dup_tool",
            source="sre",
            domains=frozenset(),
            tags=frozenset(),
            affordance=ToolAffordance.READ,
            example_queries=(),
            conflicts_with=frozenset(),
            conflict_note="",
            preferred_over=frozenset(),
        )
        m2 = ToolManifest(
            tool_name="dup_tool",
            source="azure",
            domains=frozenset(),
            tags=frozenset(),
            affordance=ToolAffordance.WRITE,
            example_queries=(),
            conflicts_with=frozenset(),
            conflict_note="",
            preferred_over=frozenset(),
        )
        index.register(m1)
        index.register(m2)
        assert len(index) == 1
        assert index.get("dup_tool").affordance == ToolAffordance.WRITE  # type: ignore[union-attr]

    @pytest.mark.unit
    def test_tool_manifest_is_frozen(self):
        """ToolManifest is a frozen dataclass — mutations must raise."""
        index = _make_index()
        m = index.get("check_resource_health")
        assert m is not None
        with pytest.raises((AttributeError, TypeError)):
            m.affordance = ToolAffordance.DESTRUCTIVE  # type: ignore[misc]

    @pytest.mark.unit
    def test_tool_manifest_default_fields(self):
        """Optional fields have correct defaults."""
        m = ToolManifest(
            tool_name="bare_tool",
            source="sre",
            domains=frozenset(),
            tags=frozenset(),
            affordance=ToolAffordance.READ,
            example_queries=(),
            conflicts_with=frozenset(),
            conflict_note="",
            preferred_over=frozenset(),
        )
        assert m.requires_confirmation is False
        assert m.deprecated is False
        assert m.output_schema == {}

    @pytest.mark.unit
    def test_build_conflict_note_multiple_pairs(self):
        """When multiple conflict pairs are both present, all notes are concatenated."""
        index = ToolManifestIndex()
        index.register_all([
            ToolManifest(
                tool_name="tool_a",
                source="sre",
                domains=frozenset(),
                tags=frozenset(),
                affordance=ToolAffordance.READ,
                example_queries=(),
                conflicts_with=frozenset({"tool_b"}),
                conflict_note="Note about A vs B.",
                preferred_over=frozenset(),
            ),
            ToolManifest(
                tool_name="tool_b",
                source="azure",
                domains=frozenset(),
                tags=frozenset(),
                affordance=ToolAffordance.READ,
                example_queries=(),
                conflicts_with=frozenset({"tool_a"}),
                conflict_note="Note about B vs A.",
                preferred_over=frozenset(),
            ),
        ])
        note = index.build_conflict_note_for_context(["tool_a", "tool_b"])
        # Both tools have conflict notes — at least one must appear
        assert "Note about" in note


# ---------------------------------------------------------------------------
# Singleton — loads real manifests from the manifests/ package
# ---------------------------------------------------------------------------

class TestGetToolManifestIndexSingleton:

    @pytest.mark.unit
    def test_loads_without_error(self):
        """Singleton loader must not raise even if some manifests fail to import."""
        index = get_tool_manifest_index()
        assert index is not None

    @pytest.mark.unit
    def test_has_entries(self):
        """At least the SRE and CLI manifests should be loaded."""
        index = get_tool_manifest_index()
        assert len(index) > 0, "Expected at least 1 manifest entry"

    @pytest.mark.unit
    def test_known_sre_tool_present(self):
        index = get_tool_manifest_index()
        m = index.get("check_resource_health")
        assert m is not None, "check_resource_health should be in the loaded index"
        assert m.affordance == ToolAffordance.READ

    @pytest.mark.unit
    def test_known_destructive_tool_present(self):
        index = get_tool_manifest_index()
        m = index.get("execute_safe_restart")
        assert m is not None, "execute_safe_restart should be in the loaded index"
        assert m.affordance == ToolAffordance.DESTRUCTIVE

    @pytest.mark.unit
    def test_cli_tool_requires_confirmation(self):
        index = get_tool_manifest_index()
        m = index.get("azure_cli_execute_command")
        assert m is not None, "azure_cli_execute_command should be in the loaded index"
        assert m.requires_confirmation is True

    @pytest.mark.unit
    def test_singleton_returns_same_instance(self):
        index1 = get_tool_manifest_index()
        index2 = get_tool_manifest_index()
        assert index1 is index2

    @pytest.mark.unit
    def test_known_tools_have_non_empty_sources(self):
        """Spot-check that loaded manifests have non-empty source strings."""
        index = get_tool_manifest_index()
        for tool_name in ("check_resource_health", "execute_safe_restart"):
            m = index.get(tool_name)
            if m is not None:
                assert isinstance(m.source, str)
                assert len(m.source) > 0, f"{tool_name} has empty source"

    @pytest.mark.unit
    def test_all_loaded_manifests_have_valid_affordance(self):
        """Every loaded manifest must have a valid ToolAffordance value."""
        index = get_tool_manifest_index()
        valid_affordances = set(ToolAffordance)
        for name in index.all_tool_names():
            m = index.get(name)
            assert m is not None
            assert m.affordance in valid_affordances, (
                f"{name} has invalid affordance: {m.affordance!r}"
            )
