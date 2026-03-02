# MCPToolRegistry - Centralized Tool Registry

## Overview

The MCPToolRegistry provides centralized management of all MCP (Model Context Protocol) tools across the application. It eliminates tool duplication, provides dynamic discovery, and enables efficient tool routing.

## Key Features

- **Centralized Registration**: Single source of truth for all MCP tools
- **Dynamic Discovery**: Automatic tool discovery via `list_tools()` protocol
- **Collision Resolution**: Priority-based handling of duplicate tool names
- **Domain Organization**: Tools organized by domain (sre, monitoring, network, etc.)
- **Notification System**: Subscribe to tool catalog changes
- **Thread-Safe**: Async-safe singleton pattern

## Architecture

```
┌─────────────────┐
│  MCPToolRegistry│  (Singleton)
│   get_tool_      │
│   _registry()    │
└────────┬─────────┘
         │
         ├──> ToolEntry (name, description, parameters, source, domain, priority)
         ├──> ServerEntry (label, client, domain, priority, enabled)
         └──> Tool Indexes (by name, domain, source)
```

## Basic Usage

### 1. Get Registry Instance

```python
from utils.tool_registry import get_tool_registry

registry = get_tool_registry()
```

### 2. Register an MCP Server

```python
# Register a server (client auto-registers during initialization)
await registry.register_server(
    label="sre",
    client=sre_mcp_client,
    domain="sre",
    priority=10,
    auto_discover=True  # Automatically discover tools
)
```

### 3. Query Tools

```python
# Get all tools
all_tools = registry.get_all_tools()

# Get tools by domain
sre_tools = registry.get_tools_by_domain("sre")

# Get tools by source
network_tools = registry.get_tools_by_source("network")

# Get specific tool
health_tool = registry.get_tool_by_name("check_resource_health")

# Get tools in OpenAI format
openai_tools = registry.get_all_tools_openai_format()
```

### 4. Invoke Tools

```python
# Invoke a tool by name
result = await registry.invoke_tool(
    "check_resource_health",
    {"resource_id": "vm-123"}
)
```

## Integration with MCP Clients

All MCP client wrappers (`*_mcp_client.py`) automatically register with the registry during initialization:

```python
class SREMCPClient:
    async def initialize(self) -> bool:
        # ... MCP server initialization ...

        # Auto-register with registry
        await self._register_with_registry()
        return True

    async def _register_with_registry(self) -> None:
        """Register this MCP client with the centralized tool registry."""
        try:
            registry = get_tool_registry()
            await registry.register_server(
                label="sre",
                client=self,
                domain="sre",
                priority=10,
                auto_discover=True
            )
        except ValueError as exc:
            if "already registered" in str(exc):
                logger.debug("Already registered")
            else:
                raise
```

## Priority-Based Collision Resolution

When multiple servers provide tools with the same name, the registry resolves collisions based on priority (lower number = higher priority):

```python
# Azure MCP has priority=5 (high priority)
await registry.register_server("azure", azure_client, priority=5)

# SRE MCP has priority=10 (standard priority)
await registry.register_server("sre", sre_client, priority=10)

# If both provide "read_resource":
# - azure gets clean name: "read_resource"
# - sre gets suffixed name: "read_resource_sre"
```

## Domain Organization

Tools are organized by domain for efficient filtering:

| Domain | Description | Example Tools |
|--------|-------------|---------------|
| `sre` | Site Reliability Engineering | check_resource_health, list_incidents |
| `monitoring` | Azure Monitor resources | get_workbook, query_metrics |
| `network` | Network auditing | audit_nsg_rules, analyze_routes |
| `compute` | VM management | list_vms, get_vm_status |
| `storage` | Storage operations | list_storage_accounts, get_blob |
| `azure` | General Azure operations | list_resources, get_subscription |
| `eol` | End-of-life tracking | os_eol_lookup, bulk_lookup |
| `inventory` | Resource inventory | os_inventory, software_inventory |
| `patch` | Patch management | list_patches, assess_patches |

## Notification System

Subscribe to registry events:

```python
def on_tools_changed(server_label: str, tool_count: int):
    print(f"Tools changed for {server_label}: {tool_count} tools")

registry.subscribe_notification("tools_changed", on_tools_changed)
```

## Registry Statistics

Get detailed statistics about the registry:

```python
stats = registry.get_stats()
# Returns:
# {
#     "total_servers": 10,
#     "total_tools": 87,
#     "tools_by_source": {"sre": 15, "network": 9, ...},
#     "tools_by_domain": {"sre": 15, "monitoring": 8, ...},
#     "servers": {
#         "sre": {"enabled": True, "domain": "sre", "tool_count": 15},
#         ...
#     }
# }
```

## Using with MCPHost

The MCPHost (formerly CompositeMCPClient) integrates with the registry:

```python
from utils.mcp_host import MCPHost

# Create host with multiple clients
host = MCPHost([
    ("sre", sre_client),
    ("network", network_client),
    ("azure", azure_client)
])

# Ensure all clients are registered
await host.ensure_registered()

# Option 1: Use host's legacy catalog (backward compatible)
tools = host.get_available_tools()

# Option 2: Use registry directly (recommended)
tools = host.get_tools_from_registry(domain="sre")
```

## Testing

The registry includes comprehensive unit tests:

```bash
cd app/agentic/eol
pytest tests/test_tool_registry.py -v

# Expected: 27 tests passing
```

## Error Handling

The registry handles common error scenarios:

```python
# Duplicate registration
try:
    await registry.register_server("sre", client)
    await registry.register_server("sre", client)  # Raises ValueError
except ValueError as exc:
    if "already registered" in str(exc):
        print("Server already registered")

# Tool not found
try:
    await registry.invoke_tool("nonexistent", {})
except ValueError as exc:
    print(f"Tool not found: {exc}")

# Connection errors (transient)
result = await registry.invoke_tool("tool_name", {})
if result.get("retry_suggested"):
    # Transient error - retry is recommended
    pass
```

## Performance Considerations

- **Singleton Pattern**: Registry is created once and reused
- **In-Memory Indexes**: Fast O(1) lookups by name, domain, source
- **Lazy Registration**: Clients register during initialization, not import
- **Async-Safe**: All mutating operations protected by asyncio.Lock

## Migration Guide

### From CompositeMCPClient to Registry

**Before:**
```python
from utils.mcp_composite_client import CompositeMCPClient

clients = [("sre", sre_client), ("network", network_client)]
mcp_client = CompositeMCPClient(clients)
tools = mcp_client.get_available_tools()
result = await mcp_client.call_tool("tool_name", args)
```

**After (Phase 1 - Backward Compatible):**
```python
from utils.mcp_host import MCPHost

clients = [("sre", sre_client), ("network", network_client)]
host = MCPHost(clients)
await host.ensure_registered()  # Register with registry

# Option 1: Continue using host (backward compatible)
tools = host.get_available_tools()
result = await host.call_tool("tool_name", args)

# Option 2: Use registry directly
registry = get_tool_registry()
tools = registry.get_all_tools_openai_format()
result = await registry.invoke_tool("tool_name", args)
```

## API Reference

### MCPToolRegistry

#### Core Methods

- `register_server(label, client, domain=None, priority=100, auto_discover=True)` - Register MCP server
- `discover_tools(server_label)` - Discover tools from specific server
- `refresh_tool_catalog(server_label=None)` - Refresh tool catalog
- `get_tool_by_name(tool_name)` - Get specific tool
- `get_tools_by_domain(domain)` - Get tools for domain
- `get_tools_by_source(source_label)` - Get tools from source
- `get_tools_by_sources(source_labels)` - Get tools from multiple sources
- `get_all_tools()` - Get all registered tools
- `get_all_tools_openai_format()` - Get all tools in OpenAI format
- `get_tools_openai_format(domain=None, sources=None)` - Get filtered tools in OpenAI format
- `invoke_tool(tool_name, arguments)` - Invoke tool by name
- `subscribe_notification(event_type, handler)` - Subscribe to events
- `get_stats()` - Get registry statistics
- `clear()` - Clear registry (testing only)

### ToolEntry

Dataclass representing a registered tool:
- `name: str` - Final tool name (may include collision suffix)
- `original_name: str` - Original tool name from server
- `description: str` - Tool description
- `parameters: Dict[str, Any]` - JSON schema for parameters
- `source_label: str` - Source server label
- `domain: Optional[str]` - Primary domain
- `priority: int` - Priority level (lower = higher priority)
- `client: Any` - MCP client instance
- `registered_at: datetime` - Registration timestamp

### ServerEntry

Dataclass representing a registered MCP server:
- `label: str` - Unique server identifier
- `client: Any` - MCP client instance
- `domain: Optional[str]` - Primary domain
- `priority: int` - Priority level
- `enabled: bool` - Whether server is enabled
- `registered_at: datetime` - Registration timestamp
- `tool_count: int` - Number of registered tools

## Troubleshooting

### Issue: Tools not appearing in registry

**Solution:** Ensure clients are calling `_register_with_registry()` during initialization:

```python
async def initialize(self) -> bool:
    # ... MCP server startup ...
    await self._register_with_registry()
    return True
```

### Issue: Tool name collisions

**Solution:** Check tool priorities and adjust as needed:

```python
# Higher priority servers get clean names
await registry.register_server("azure", azure_client, priority=5)  # High
await registry.register_server("sre", sre_client, priority=10)    # Standard
```

### Issue: Registry not accessible

**Solution:** Use `get_tool_registry()` function, not direct instantiation:

```python
# ✅ Correct
from utils.tool_registry import get_tool_registry
registry = get_tool_registry()

# ❌ Incorrect
from utils.tool_registry import MCPToolRegistry
registry = MCPToolRegistry()  # Will work but may create multiple instances
```

## Future Enhancements (Phase 2+)

- Tool versioning and deprecation tracking
- Tool usage analytics and metrics
- Dynamic priority adjustment based on success rates
- Tool recommendation engine
- Cross-domain tool composition
- Tool dependency graph visualization

## References

- **Source Code**: `app/agentic/eol/utils/tool_registry.py`
- **Tests**: `app/agentic/eol/tests/test_tool_registry.py`
- **MCP Host**: `app/agentic/eol/utils/mcp_host.py`
- **MCP Specification**: https://modelcontextprotocol.io/

---

**Version**: 1.0.0
**Last Updated**: 2026-03-02
**Phase**: 1 (Foundation)
