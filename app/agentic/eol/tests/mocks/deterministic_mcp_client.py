"""Deterministic MCP Client for local testing.

Provides a drop-in replacement for real MCP clients (SREMCPClient,
NetworkMCPClient, etc.) that returns pre-defined responses from JSON
fixture files. This enables tool selection testing without deploying
to Azure.

Design principles:
- Same interface as real MCP clients (call_tool, list_tools, initialize, cleanup)
- Fixture-driven: responses loaded from JSON files
- Key normalization: correlation_id, timestamp fields ignored during matching
- Pattern matching: supports partial param matching with wildcards
- Clear error messages when fixtures are missing

Fixture file format:
{
    "server_label": "sre",
    "tools": [
        {"name": "tool_name", "description": "...", "parameters": {...}}
    ],
    "responses": {
        "tool_name": [
            {
                "match": {"param1": "value1"},
                "response": {"status": "ok", "data": {...}}
            },
            {
                "match": "*",
                "response": {"status": "ok", "data": "default"}
            }
        ]
    }
}
"""
from __future__ import annotations

import json
import logging
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)

# Keys that are ignored during parameter matching (dynamic/non-deterministic)
DEFAULT_NORMALIZED_KEYS: Set[str] = frozenset({
    "correlation_id",
    "timestamp",
    "request_id",
    "trace_id",
    "session_id",
})


@dataclass
class FixtureResponse:
    """A single fixture response entry with match criteria.

    Attributes:
        match: Parameter matching criteria. Can be:
            - "*" for catch-all default
            - dict of key-value pairs to match against call arguments
            - None treated as catch-all
        response: The deterministic response to return
        call_count: Number of times this fixture has been matched
    """
    match: Any  # str("*"), dict, or None
    response: Any
    call_count: int = 0

    def matches(self, arguments: Dict[str, Any], normalized_keys: Set[str]) -> bool:
        """Check if this fixture matches the given arguments.

        Args:
            arguments: The tool call arguments to match against
            normalized_keys: Set of key names to ignore during matching

        Returns:
            True if this fixture matches the given arguments
        """
        # Wildcard/default match
        if self.match is None or self.match == "*":
            return True

        if not isinstance(self.match, dict):
            return False

        # Normalize arguments by removing dynamic keys
        normalized_args = {
            k: v for k, v in arguments.items()
            if k not in normalized_keys
        }
        normalized_match = {
            k: v for k, v in self.match.items()
            if k not in normalized_keys
        }

        # Check all match criteria exist in arguments
        for key, expected_value in normalized_match.items():
            if key not in normalized_args:
                return False

            actual_value = normalized_args[key]

            # String wildcard pattern matching
            if isinstance(expected_value, str) and expected_value == "*":
                continue  # Any value matches

            # Exact match (with type coercion for numeric strings)
            if actual_value != expected_value:
                # Try string comparison as fallback
                if str(actual_value) != str(expected_value):
                    return False

        return True


@dataclass
class ToolDefinition:
    """A mock tool definition matching the OpenAI function-calling schema.

    Attributes:
        name: Tool name
        description: Tool description
        parameters: JSON schema for tool parameters
    """
    name: str
    description: str
    parameters: Dict[str, Any] = field(default_factory=dict)

    def to_openai_format(self) -> Dict[str, Any]:
        """Convert to OpenAI function-calling format."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


class FixtureLoader:
    """Loads and validates fixture files for DeterministicMCPClient.

    Fixture files are JSON files that define tool definitions and their
    expected responses. The loader validates the structure and provides
    clear error messages for missing or malformed fixtures.
    """

    # Default fixtures directory (relative to tests/)
    DEFAULT_FIXTURES_DIR = Path(__file__).parent / "fixtures"

    @classmethod
    def load_file(cls, fixture_path: str | Path) -> Dict[str, Any]:
        """Load and validate a fixture file.

        Args:
            fixture_path: Path to the fixture JSON file. Can be:
                - Absolute path
                - Relative to DEFAULT_FIXTURES_DIR
                - Just a filename (looked up in DEFAULT_FIXTURES_DIR)

        Returns:
            Parsed and validated fixture data

        Raises:
            FileNotFoundError: If the fixture file doesn't exist
            ValueError: If the fixture file is invalid
        """
        path = cls._resolve_path(fixture_path)

        if not path.exists():
            available = cls._list_available_fixtures()
            raise FileNotFoundError(
                f"Fixture file not found: {path}\n"
                f"Available fixtures: {available or '(none)'}\n"
                f"Fixtures directory: {cls.DEFAULT_FIXTURES_DIR}"
            )

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"Invalid JSON in fixture file {path}: {exc}"
            ) from exc

        cls._validate_fixture_data(data, path)
        return data

    @classmethod
    def load_inline(cls, fixture_data: Dict[str, Any]) -> Dict[str, Any]:
        """Validate and return inline fixture data (dict, not file).

        Args:
            fixture_data: Fixture data as a Python dictionary

        Returns:
            Validated fixture data

        Raises:
            ValueError: If the fixture data is invalid
        """
        cls._validate_fixture_data(fixture_data, source="<inline>")
        return fixture_data

    @classmethod
    def _resolve_path(cls, fixture_path: str | Path) -> Path:
        """Resolve fixture path, checking multiple locations."""
        path = Path(fixture_path)

        # If absolute or exists as-is, use directly
        if path.is_absolute() or path.exists():
            return path

        # Try relative to default fixtures dir
        in_fixtures = cls.DEFAULT_FIXTURES_DIR / path
        if in_fixtures.exists():
            return in_fixtures

        # Try adding .json extension
        if not path.suffix:
            with_json = cls.DEFAULT_FIXTURES_DIR / f"{path}.json"
            if with_json.exists():
                return with_json

        # Return the fixtures dir path (will trigger FileNotFoundError)
        return in_fixtures

    @classmethod
    def _list_available_fixtures(cls) -> List[str]:
        """List available fixture files."""
        if not cls.DEFAULT_FIXTURES_DIR.exists():
            return []
        return sorted(
            f.name for f in cls.DEFAULT_FIXTURES_DIR.glob("*.json")
        )

    @classmethod
    def _validate_fixture_data(cls, data: Dict[str, Any], source: Any = None) -> None:
        """Validate the structure of fixture data.

        Args:
            data: The fixture data to validate
            source: Source identifier for error messages

        Raises:
            ValueError: If required fields are missing or malformed
        """
        if not isinstance(data, dict):
            raise ValueError(
                f"Fixture data must be a dict, got {type(data).__name__} "
                f"(source: {source})"
            )

        # server_label is required
        if "server_label" not in data:
            raise ValueError(
                f"Fixture missing required 'server_label' field (source: {source})"
            )

        # tools must be a list of dicts with 'name'
        tools = data.get("tools", [])
        if not isinstance(tools, list):
            raise ValueError(
                f"Fixture 'tools' must be a list, got {type(tools).__name__} "
                f"(source: {source})"
            )
        for i, tool in enumerate(tools):
            if not isinstance(tool, dict):
                raise ValueError(
                    f"Fixture tool[{i}] must be a dict (source: {source})"
                )
            if "name" not in tool:
                raise ValueError(
                    f"Fixture tool[{i}] missing 'name' field (source: {source})"
                )

        # responses must be a dict of tool_name -> list of response entries
        responses = data.get("responses", {})
        if not isinstance(responses, dict):
            raise ValueError(
                f"Fixture 'responses' must be a dict, got {type(responses).__name__} "
                f"(source: {source})"
            )
        for tool_name, entries in responses.items():
            if not isinstance(entries, list):
                raise ValueError(
                    f"Fixture responses['{tool_name}'] must be a list "
                    f"(source: {source})"
                )
            for j, entry in enumerate(entries):
                if not isinstance(entry, dict):
                    raise ValueError(
                        f"Fixture responses['{tool_name}'][{j}] must be a dict "
                        f"(source: {source})"
                    )
                if "response" not in entry:
                    raise ValueError(
                        f"Fixture responses['{tool_name}'][{j}] missing 'response' "
                        f"field (source: {source})"
                    )


class DeterministicMCPClient:
    """Drop-in replacement for real MCP clients that returns deterministic responses.

    This client loads fixture data (tool definitions + canned responses) and
    returns them when `call_tool()` is invoked, matching on tool name and
    optionally on call arguments.

    It matches the interface of real MCP clients:
    - `initialize()` -> bool
    - `call_tool(tool_name, arguments)` -> Dict[str, Any]
    - `cleanup()` -> None
    - `available_tools` property (OpenAI format list)

    Usage:
        # From fixture file
        client = DeterministicMCPClient.from_fixture_file("sre_health_check.json")

        # From inline data
        client = DeterministicMCPClient.from_fixture_data({
            "server_label": "sre",
            "tools": [{"name": "check_health", "description": "..."}],
            "responses": {
                "check_health": [
                    {"match": {"resource_id": "vm-001"}, "response": {"status": "healthy"}},
                    {"match": "*", "response": {"status": "unknown"}}
                ]
            }
        })

        # Use like a real client
        await client.initialize()
        result = await client.call_tool("check_health", {"resource_id": "vm-001"})
        assert result == {"status": "healthy"}
    """

    def __init__(
        self,
        server_label: str,
        tools: List[ToolDefinition],
        responses: Dict[str, List[FixtureResponse]],
        normalized_keys: Optional[Set[str]] = None,
    ) -> None:
        """Initialize with pre-parsed fixture data.

        Prefer using factory methods (from_fixture_file, from_fixture_data)
        instead of calling __init__ directly.
        """
        self.server_label = server_label
        self._tools = tools
        self._responses = responses
        self._normalized_keys = normalized_keys or DEFAULT_NORMALIZED_KEYS
        self._initialized = False
        self._call_log: List[Dict[str, Any]] = []

        # Build available_tools in OpenAI format (matches real MCP client interface)
        self.available_tools: List[Dict[str, Any]] = [
            t.to_openai_format() for t in self._tools
        ]

    # ─────────────────────────── Factory Methods ────────────────────────────

    @classmethod
    def from_fixture_file(
        cls,
        fixture_path: str | Path,
        normalized_keys: Optional[Set[str]] = None,
    ) -> "DeterministicMCPClient":
        """Create a client from a fixture JSON file.

        Args:
            fixture_path: Path to the fixture file
            normalized_keys: Keys to ignore during parameter matching

        Returns:
            Configured DeterministicMCPClient
        """
        data = FixtureLoader.load_file(fixture_path)
        return cls._from_validated_data(data, normalized_keys)

    @classmethod
    def from_fixture_data(
        cls,
        fixture_data: Dict[str, Any],
        normalized_keys: Optional[Set[str]] = None,
    ) -> "DeterministicMCPClient":
        """Create a client from inline fixture data (dict).

        Args:
            fixture_data: Fixture data as a Python dictionary
            normalized_keys: Keys to ignore during parameter matching

        Returns:
            Configured DeterministicMCPClient
        """
        data = FixtureLoader.load_inline(fixture_data)
        return cls._from_validated_data(data, normalized_keys)

    @classmethod
    def _from_validated_data(
        cls,
        data: Dict[str, Any],
        normalized_keys: Optional[Set[str]] = None,
    ) -> "DeterministicMCPClient":
        """Build client from already-validated fixture data."""
        server_label = data["server_label"]

        # Parse tool definitions
        tools = [
            ToolDefinition(
                name=t["name"],
                description=t.get("description", ""),
                parameters=t.get("parameters", {}),
            )
            for t in data.get("tools", [])
        ]

        # Parse response fixtures
        responses: Dict[str, List[FixtureResponse]] = {}
        for tool_name, entries in data.get("responses", {}).items():
            responses[tool_name] = [
                FixtureResponse(
                    match=entry.get("match", "*"),
                    response=entry["response"],
                )
                for entry in entries
            ]

        return cls(
            server_label=server_label,
            tools=tools,
            responses=responses,
            normalized_keys=normalized_keys,
        )

    # ────────────────────────── MCP Client Interface ────────────────────────

    async def initialize(self) -> bool:
        """Initialize the mock client. Always succeeds.

        Returns:
            True (mock initialization always succeeds)
        """
        self._initialized = True
        logger.info(
            "DeterministicMCPClient[%s] initialized with %d tools, %d response sets",
            self.server_label,
            len(self._tools),
            len(self._responses),
        )
        return True

    async def call_tool(
        self,
        tool_name: str,
        arguments: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Call a tool and return the matching fixture response.

        Matches responses in order: first match wins. The last entry
        with match="*" acts as a default/catch-all.

        Args:
            tool_name: Name of the tool to call
            arguments: Tool call arguments

        Returns:
            The matching fixture response (deep-copied to prevent mutation)

        Raises:
            RuntimeError: If client not initialized
            KeyError: If no fixture found for the tool/arguments combination
        """
        if not self._initialized:
            raise RuntimeError(
                f"DeterministicMCPClient[{self.server_label}] not initialized. "
                f"Call initialize() first."
            )

        arguments = arguments or {}

        # Log the call
        call_record = {
            "tool_name": tool_name,
            "arguments": deepcopy(arguments),
            "timestamp": datetime.utcnow().isoformat(),
        }
        self._call_log.append(call_record)

        # Look up response fixtures for this tool
        fixtures = self._responses.get(tool_name)
        if fixtures is None:
            available_tools = sorted(self._responses.keys())
            raise KeyError(
                f"No fixture responses for tool '{tool_name}' in "
                f"DeterministicMCPClient[{self.server_label}].\n"
                f"Available tools with fixtures: {available_tools}\n"
                f"Arguments: {json.dumps(arguments, default=str)}"
            )

        # Find matching fixture (first match wins)
        for fixture in fixtures:
            if fixture.matches(arguments, self._normalized_keys):
                fixture.call_count += 1
                logger.debug(
                    "DeterministicMCPClient[%s] matched fixture for '%s' "
                    "(match=%s, call_count=%d)",
                    self.server_label,
                    tool_name,
                    fixture.match,
                    fixture.call_count,
                )
                # Deep copy to prevent test mutation
                return deepcopy(fixture.response)

        # No matching fixture found
        raise KeyError(
            f"No matching fixture for tool '{tool_name}' with arguments "
            f"{json.dumps(arguments, default=str)} in "
            f"DeterministicMCPClient[{self.server_label}].\n"
            f"Available match patterns: "
            f"{[f.match for f in fixtures]}"
        )

    async def cleanup(self) -> None:
        """Clean up the mock client."""
        self._initialized = False
        logger.debug("DeterministicMCPClient[%s] cleaned up", self.server_label)

    # ────────────────────────── Introspection Helpers ───────────────────────

    @property
    def call_log(self) -> List[Dict[str, Any]]:
        """Return the full call log for assertions in tests."""
        return list(self._call_log)

    @property
    def call_count(self) -> int:
        """Total number of tool calls made."""
        return len(self._call_log)

    def get_calls_for(self, tool_name: str) -> List[Dict[str, Any]]:
        """Get all logged calls for a specific tool.

        Args:
            tool_name: The tool name to filter by

        Returns:
            List of call records for that tool
        """
        return [c for c in self._call_log if c["tool_name"] == tool_name]

    def assert_tool_called(self, tool_name: str, times: Optional[int] = None) -> None:
        """Assert that a tool was called, optionally checking call count.

        Args:
            tool_name: The tool to check
            times: If provided, assert exact call count

        Raises:
            AssertionError: If the tool wasn't called or count doesn't match
        """
        calls = self.get_calls_for(tool_name)
        if not calls:
            raise AssertionError(
                f"Tool '{tool_name}' was never called. "
                f"Tools called: {sorted(set(c['tool_name'] for c in self._call_log))}"
            )
        if times is not None and len(calls) != times:
            raise AssertionError(
                f"Tool '{tool_name}' called {len(calls)} time(s), expected {times}"
            )

    def assert_tool_not_called(self, tool_name: str) -> None:
        """Assert that a tool was never called.

        Args:
            tool_name: The tool to check

        Raises:
            AssertionError: If the tool was called
        """
        calls = self.get_calls_for(tool_name)
        if calls:
            raise AssertionError(
                f"Tool '{tool_name}' was unexpectedly called {len(calls)} time(s)"
            )

    def assert_call_sequence(self, expected_sequence: List[str]) -> None:
        """Assert that tools were called in the expected order.

        Args:
            expected_sequence: List of tool names in expected call order

        Raises:
            AssertionError: If the actual sequence doesn't match
        """
        actual_sequence = [c["tool_name"] for c in self._call_log]
        if actual_sequence != expected_sequence:
            raise AssertionError(
                f"Call sequence mismatch.\n"
                f"Expected: {expected_sequence}\n"
                f"Actual:   {actual_sequence}"
            )

    def reset(self) -> None:
        """Reset call log and fixture call counts for test isolation."""
        self._call_log.clear()
        for fixtures in self._responses.values():
            for fixture in fixtures:
                fixture.call_count = 0
        logger.debug("DeterministicMCPClient[%s] reset", self.server_label)

    def get_tool_names(self) -> List[str]:
        """Return all registered tool names."""
        return [t.name for t in self._tools]

    def __repr__(self) -> str:
        return (
            f"DeterministicMCPClient("
            f"server_label={self.server_label!r}, "
            f"tools={len(self._tools)}, "
            f"response_sets={len(self._responses)}, "
            f"calls={self.call_count})"
        )
