"""Unit tests for DeterministicMCPClient and FixtureLoader.

These tests validate the mock infrastructure itself, ensuring it
correctly loads fixtures, matches parameters, and provides clear
error messages.
"""
import json
import pytest
import pytest_asyncio
from pathlib import Path

from tests.mocks.deterministic_mcp_client import (
    DeterministicMCPClient,
    FixtureLoader,
    FixtureResponse,
    ToolDefinition,
    DEFAULT_NORMALIZED_KEYS,
)


# ─────────────────────────── Fixture Data ───────────────────────────────


MINIMAL_FIXTURE = {
    "server_label": "test",
    "tools": [
        {
            "name": "test_tool",
            "description": "A test tool",
            "parameters": {
                "type": "object",
                "properties": {
                    "param1": {"type": "string"}
                },
            },
        }
    ],
    "responses": {
        "test_tool": [
            {
                "match": {"param1": "hello"},
                "response": {"result": "matched_hello"},
            },
            {
                "match": {"param1": "world"},
                "response": {"result": "matched_world"},
            },
            {
                "match": "*",
                "response": {"result": "default"},
            },
        ]
    },
}

MULTI_TOOL_FIXTURE = {
    "server_label": "multi",
    "tools": [
        {"name": "tool_a", "description": "Tool A"},
        {"name": "tool_b", "description": "Tool B"},
        {"name": "tool_c", "description": "Tool C"},
    ],
    "responses": {
        "tool_a": [
            {"match": "*", "response": {"from": "tool_a"}}
        ],
        "tool_b": [
            {"match": {"key": "val"}, "response": {"from": "tool_b_matched"}},
            {"match": "*", "response": {"from": "tool_b_default"}},
        ],
    },
}


# ─────────────────────── FixtureResponse Tests ──────────────────────────


class TestFixtureResponse:
    """Test the FixtureResponse matching logic."""

    def test_wildcard_match(self):
        fr = FixtureResponse(match="*", response={"ok": True})
        assert fr.matches({"any": "thing"}, DEFAULT_NORMALIZED_KEYS)

    def test_none_match_is_wildcard(self):
        fr = FixtureResponse(match=None, response={"ok": True})
        assert fr.matches({"any": "thing"}, DEFAULT_NORMALIZED_KEYS)

    def test_exact_match(self):
        fr = FixtureResponse(
            match={"resource_id": "vm-001"},
            response={"ok": True},
        )
        assert fr.matches({"resource_id": "vm-001"}, DEFAULT_NORMALIZED_KEYS)
        assert not fr.matches({"resource_id": "vm-002"}, DEFAULT_NORMALIZED_KEYS)

    def test_partial_match_extra_args_ok(self):
        """Extra arguments beyond match criteria are allowed."""
        fr = FixtureResponse(
            match={"resource_id": "vm-001"},
            response={"ok": True},
        )
        assert fr.matches(
            {"resource_id": "vm-001", "extra": "ignored"},
            DEFAULT_NORMALIZED_KEYS,
        )

    def test_missing_match_key_fails(self):
        """Arguments must contain all match keys."""
        fr = FixtureResponse(
            match={"resource_id": "vm-001", "region": "eastus"},
            response={"ok": True},
        )
        assert not fr.matches({"resource_id": "vm-001"}, DEFAULT_NORMALIZED_KEYS)

    def test_normalized_keys_ignored(self):
        """Normalized keys (correlation_id, timestamp) are ignored during matching."""
        fr = FixtureResponse(
            match={"resource_id": "vm-001"},
            response={"ok": True},
        )
        # correlation_id in arguments is ignored
        assert fr.matches(
            {"resource_id": "vm-001", "correlation_id": "abc-123"},
            DEFAULT_NORMALIZED_KEYS,
        )
        # correlation_id in match criteria is also ignored
        fr2 = FixtureResponse(
            match={"resource_id": "vm-001", "correlation_id": "xyz"},
            response={"ok": True},
        )
        assert fr2.matches(
            {"resource_id": "vm-001"},
            DEFAULT_NORMALIZED_KEYS,
        )

    def test_wildcard_in_match_value(self):
        """A '*' value in match dict matches any value for that key."""
        fr = FixtureResponse(
            match={"resource_id": "*"},
            response={"ok": True},
        )
        assert fr.matches({"resource_id": "anything"}, DEFAULT_NORMALIZED_KEYS)

    def test_numeric_string_coercion(self):
        """Numeric values can match their string equivalents."""
        fr = FixtureResponse(
            match={"count": "5"},
            response={"ok": True},
        )
        assert fr.matches({"count": 5}, DEFAULT_NORMALIZED_KEYS)

    def test_call_count_tracking(self):
        fr = FixtureResponse(match="*", response={"ok": True})
        assert fr.call_count == 0
        fr.matches({"x": 1}, DEFAULT_NORMALIZED_KEYS)  # matches() doesn't increment
        assert fr.call_count == 0  # call_count is incremented by DeterministicMCPClient


# ─────────────────────── ToolDefinition Tests ───────────────────────────


class TestToolDefinition:
    def test_to_openai_format(self):
        td = ToolDefinition(
            name="my_tool",
            description="Does things",
            parameters={"type": "object", "properties": {}},
        )
        fmt = td.to_openai_format()
        assert fmt["type"] == "function"
        assert fmt["function"]["name"] == "my_tool"
        assert fmt["function"]["description"] == "Does things"
        assert "parameters" in fmt["function"]


# ─────────────────────── FixtureLoader Tests ────────────────────────────


class TestFixtureLoader:
    def test_load_inline_valid(self):
        data = FixtureLoader.load_inline(MINIMAL_FIXTURE)
        assert data["server_label"] == "test"

    def test_load_inline_missing_server_label(self):
        with pytest.raises(ValueError, match="server_label"):
            FixtureLoader.load_inline({"tools": [], "responses": {}})

    def test_load_inline_not_dict(self):
        with pytest.raises(ValueError, match="must be a dict"):
            FixtureLoader.load_inline([1, 2, 3])

    def test_load_inline_tools_not_list(self):
        with pytest.raises(ValueError, match="must be a list"):
            FixtureLoader.load_inline({
                "server_label": "bad",
                "tools": "not_a_list",
            })

    def test_load_inline_tool_missing_name(self):
        with pytest.raises(ValueError, match="missing 'name'"):
            FixtureLoader.load_inline({
                "server_label": "bad",
                "tools": [{"description": "no name"}],
            })

    def test_load_inline_responses_not_dict(self):
        with pytest.raises(ValueError, match="must be a dict"):
            FixtureLoader.load_inline({
                "server_label": "bad",
                "tools": [],
                "responses": "not_a_dict",
            })

    def test_load_inline_response_missing_response_field(self):
        with pytest.raises(ValueError, match="missing 'response'"):
            FixtureLoader.load_inline({
                "server_label": "bad",
                "tools": [],
                "responses": {
                    "tool": [{"match": "*"}]  # missing 'response' key
                },
            })

    def test_load_file_not_found(self):
        with pytest.raises(FileNotFoundError, match="Fixture file not found"):
            FixtureLoader.load_file("/nonexistent/path/fixture.json")

    def test_load_file_example(self):
        """Test loading the example fixture file."""
        fixture_path = (
            Path(__file__).parent.parent / "mocks" / "fixtures" / "example_sre_health.json"
        )
        if fixture_path.exists():
            data = FixtureLoader.load_file(fixture_path)
            assert data["server_label"] == "sre"
            assert len(data["tools"]) >= 1

    def test_list_available_fixtures(self):
        """Verify fixture listing works."""
        available = FixtureLoader._list_available_fixtures()
        assert isinstance(available, list)


# ─────────────────── DeterministicMCPClient Tests ───────────────────────


class TestDeterministicMCPClient:
    """Test the main DeterministicMCPClient class."""

    def _make_client(self, fixture=None):
        """Helper to create a client from fixture data."""
        return DeterministicMCPClient.from_fixture_data(fixture or MINIMAL_FIXTURE)

    @pytest.mark.asyncio
    async def test_initialize(self):
        client = self._make_client()
        assert not client._initialized
        result = await client.initialize()
        assert result is True
        assert client._initialized

    @pytest.mark.asyncio
    async def test_call_tool_exact_match(self):
        client = self._make_client()
        await client.initialize()
        result = await client.call_tool("test_tool", {"param1": "hello"})
        assert result == {"result": "matched_hello"}

    @pytest.mark.asyncio
    async def test_call_tool_second_match(self):
        client = self._make_client()
        await client.initialize()
        result = await client.call_tool("test_tool", {"param1": "world"})
        assert result == {"result": "matched_world"}

    @pytest.mark.asyncio
    async def test_call_tool_default_match(self):
        client = self._make_client()
        await client.initialize()
        result = await client.call_tool("test_tool", {"param1": "other"})
        assert result == {"result": "default"}

    @pytest.mark.asyncio
    async def test_call_tool_no_arguments(self):
        client = self._make_client()
        await client.initialize()
        result = await client.call_tool("test_tool")
        assert result == {"result": "default"}

    @pytest.mark.asyncio
    async def test_call_tool_not_initialized(self):
        client = self._make_client()
        with pytest.raises(RuntimeError, match="not initialized"):
            await client.call_tool("test_tool", {})

    @pytest.mark.asyncio
    async def test_call_tool_unknown_tool(self):
        client = self._make_client()
        await client.initialize()
        with pytest.raises(KeyError, match="No fixture responses"):
            await client.call_tool("nonexistent_tool", {})

    @pytest.mark.asyncio
    async def test_response_deep_copied(self):
        """Responses are deep-copied so mutations don't affect future calls."""
        client = self._make_client()
        await client.initialize()
        result1 = await client.call_tool("test_tool", {"param1": "hello"})
        result1["result"] = "MUTATED"
        result2 = await client.call_tool("test_tool", {"param1": "hello"})
        assert result2["result"] == "matched_hello"

    @pytest.mark.asyncio
    async def test_call_log(self):
        client = self._make_client()
        await client.initialize()
        await client.call_tool("test_tool", {"param1": "hello"})
        await client.call_tool("test_tool", {"param1": "world"})
        assert client.call_count == 2
        assert len(client.call_log) == 2
        assert client.call_log[0]["tool_name"] == "test_tool"
        assert client.call_log[0]["arguments"] == {"param1": "hello"}

    @pytest.mark.asyncio
    async def test_get_calls_for(self):
        client = self._make_client(MULTI_TOOL_FIXTURE)
        await client.initialize()
        await client.call_tool("tool_a", {})
        await client.call_tool("tool_b", {"key": "val"})
        await client.call_tool("tool_a", {})
        assert len(client.get_calls_for("tool_a")) == 2
        assert len(client.get_calls_for("tool_b")) == 1
        assert len(client.get_calls_for("tool_c")) == 0

    @pytest.mark.asyncio
    async def test_assert_tool_called(self):
        client = self._make_client(MULTI_TOOL_FIXTURE)
        await client.initialize()
        await client.call_tool("tool_a", {})
        client.assert_tool_called("tool_a")
        client.assert_tool_called("tool_a", times=1)
        with pytest.raises(AssertionError, match="never called"):
            client.assert_tool_called("tool_b")
        with pytest.raises(AssertionError, match="expected 2"):
            client.assert_tool_called("tool_a", times=2)

    @pytest.mark.asyncio
    async def test_assert_tool_not_called(self):
        client = self._make_client(MULTI_TOOL_FIXTURE)
        await client.initialize()
        await client.call_tool("tool_a", {})
        client.assert_tool_not_called("tool_b")
        with pytest.raises(AssertionError, match="unexpectedly called"):
            client.assert_tool_not_called("tool_a")

    @pytest.mark.asyncio
    async def test_assert_call_sequence(self):
        client = self._make_client(MULTI_TOOL_FIXTURE)
        await client.initialize()
        await client.call_tool("tool_a", {})
        await client.call_tool("tool_b", {})
        await client.call_tool("tool_a", {})
        client.assert_call_sequence(["tool_a", "tool_b", "tool_a"])
        with pytest.raises(AssertionError, match="sequence mismatch"):
            client.assert_call_sequence(["tool_b", "tool_a"])

    @pytest.mark.asyncio
    async def test_reset(self):
        client = self._make_client()
        await client.initialize()
        await client.call_tool("test_tool", {"param1": "hello"})
        assert client.call_count == 1
        client.reset()
        assert client.call_count == 0
        assert client.call_log == []

    @pytest.mark.asyncio
    async def test_cleanup(self):
        client = self._make_client()
        await client.initialize()
        assert client._initialized
        await client.cleanup()
        assert not client._initialized

    def test_available_tools_format(self):
        client = self._make_client()
        assert len(client.available_tools) == 1
        tool = client.available_tools[0]
        assert tool["type"] == "function"
        assert tool["function"]["name"] == "test_tool"

    def test_get_tool_names(self):
        client = self._make_client(MULTI_TOOL_FIXTURE)
        names = client.get_tool_names()
        assert names == ["tool_a", "tool_b", "tool_c"]

    def test_repr(self):
        client = self._make_client()
        repr_str = repr(client)
        assert "test" in repr_str
        assert "tools=1" in repr_str

    @pytest.mark.asyncio
    async def test_normalized_keys_in_call(self):
        """Correlation IDs in arguments don't affect matching."""
        client = self._make_client()
        await client.initialize()
        result = await client.call_tool(
            "test_tool",
            {"param1": "hello", "correlation_id": "test-123"}
        )
        assert result == {"result": "matched_hello"}

    @pytest.mark.asyncio
    async def test_from_fixture_file(self):
        """Test creating client from the example fixture file."""
        fixture_path = (
            Path(__file__).parent.parent / "mocks" / "fixtures" / "example_sre_health.json"
        )
        if fixture_path.exists():
            client = DeterministicMCPClient.from_fixture_file(fixture_path)
            await client.initialize()
            assert client.server_label == "sre"
            assert len(client.available_tools) >= 1

            # Test a specific call
            result = await client.call_tool(
                "check_resource_health",
                {"resource_id": "vm-healthy-001"},
            )
            assert result["status"] == "healthy"
            assert result["health_state"] == "Available"

    @pytest.mark.asyncio
    async def test_multi_param_matching(self):
        """Test matching on multiple parameters simultaneously."""
        fixture = {
            "server_label": "test",
            "tools": [{"name": "multi_tool", "description": ""}],
            "responses": {
                "multi_tool": [
                    {
                        "match": {"region": "eastus", "tier": "premium"},
                        "response": {"matched": "eastus_premium"},
                    },
                    {
                        "match": {"region": "eastus"},
                        "response": {"matched": "eastus_any"},
                    },
                    {
                        "match": "*",
                        "response": {"matched": "default"},
                    },
                ]
            },
        }
        client = DeterministicMCPClient.from_fixture_data(fixture)
        await client.initialize()

        # Both params match first entry
        r1 = await client.call_tool("multi_tool", {"region": "eastus", "tier": "premium"})
        assert r1["matched"] == "eastus_premium"

        # Only region matches second entry
        r2 = await client.call_tool("multi_tool", {"region": "eastus", "tier": "basic"})
        assert r2["matched"] == "eastus_any"

        # Nothing matches, falls to default
        r3 = await client.call_tool("multi_tool", {"region": "westus"})
        assert r3["matched"] == "default"

    @pytest.mark.asyncio
    async def test_no_default_no_match_raises(self):
        """Without a catch-all, unmatched params raise KeyError."""
        fixture = {
            "server_label": "test",
            "tools": [{"name": "strict_tool", "description": ""}],
            "responses": {
                "strict_tool": [
                    {
                        "match": {"id": "specific"},
                        "response": {"ok": True},
                    },
                ]
            },
        }
        client = DeterministicMCPClient.from_fixture_data(fixture)
        await client.initialize()
        result = await client.call_tool("strict_tool", {"id": "specific"})
        assert result["ok"] is True
        with pytest.raises(KeyError, match="No matching fixture"):
            await client.call_tool("strict_tool", {"id": "other"})
