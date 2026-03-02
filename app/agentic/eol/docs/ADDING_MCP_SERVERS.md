# Adding a New MCP Server

**Estimated Time:** ~20 minutes
**Requires:** Python or Node.js for the MCP server implementation

---

## Overview

Adding a new MCP server to the orchestrator architecture involves 5 concrete steps. This guide uses the declarative configuration system introduced in Phase 5, making server addition fast and maintainable.

**Four steps:**
1. Create the MCP server (FastMCP pattern)
2. Create the MCP client wrapper
3. Register server in `config/mcp_servers.yaml`
4. Wire client factory in `MCPHost`
5. Verify with smoke test

---

## Prerequisites

- Python 3.11+ (for FastMCP servers)
- OR Node.js 18+ (for TypeScript/JavaScript servers)
- Familiarity with `@mcp.tool()` decorator pattern (FastMCP)
- Access to `app/agentic/eol/` directory

---

## Step 1: Create the MCP Server

**Location:** `app/agentic/eol/mcp_servers/my_new_mcp_server.py`

**Template:** Copy `mcp_servers/sre_mcp_server.py` as starting point

### Python Server (FastMCP)

```python
"""My New MCP Server - custom domain tools."""

import asyncio
from fastmcp import FastMCP
from utils.logger import get_logger
from utils.config import config

logger = get_logger(__name__, config.app.log_level)

# Create MCP server instance
mcp = FastMCP("My New MCP Server")


@mcp.tool()
async def my_custom_tool(param1: str, param2: int) -> dict:
    """
    Description of what this tool does.

    Args:
        param1: Description of first parameter
        param2: Description of second parameter

    Returns:
        dict: Result with status and data
    """
    logger.info("my_custom_tool called with param1=%s, param2=%d", param1, param2)

    try:
        # Your tool implementation here
        result = {
            "status": "success",
            "data": {
                "param1": param1,
                "param2": param2,
                "result": f"Processed {param1} with count {param2}"
            }
        }
        return result
    except Exception as e:
        logger.error("my_custom_tool failed: %s", e)
        return {"status": "error", "error": str(e)}


@mcp.tool()
async def another_tool(resource_id: str) -> dict:
    """Another tool in the same server."""
    logger.info("another_tool called with resource_id=%s", resource_id)
    return {"status": "success", "resource_id": resource_id}


if __name__ == "__main__":
    logger.info("Starting My New MCP Server")
    mcp.run()
```

**Key points:**
- Use `@mcp.tool()` decorator for each tool
- Include docstrings (visible to LLM)
- Return structured `dict` (not raw strings)
- Use `logger.info()` for milestones, `logger.error()` for failures
- Call `mcp.run()` in `if __name__ == "__main__"` block

---

## Step 2: Create the MCP Client Wrapper

**Location:** `app/agentic/eol/utils/my_new_mcp_client.py`

**Template:** Copy `utils/sre_mcp_client.py` as starting point

```python
"""MCP client wrapper for My New MCP Server."""

import asyncio
from pathlib import Path
from typing import Optional

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from utils.logger import get_logger
from utils.config import config

logger = get_logger(__name__, config.app.log_level)


async def get_my_new_mcp_client() -> Optional[ClientSession]:
    """
    Factory function to create My New MCP client.

    Returns:
        ClientSession if successful, None if disabled or error
    """
    # Check if server is enabled (respects env var from YAML)
    if not config.app.my_new_enabled:  # Add to config.py if needed
        logger.info("My New MCP server disabled via config")
        return None

    try:
        # Path to server script (relative to eol/ directory)
        server_path = Path(__file__).parent.parent / "mcp_servers" / "my_new_mcp_server.py"

        if not server_path.exists():
            logger.warning("My New MCP server script not found: %s", server_path)
            return None

        # Server parameters for stdio transport
        server_params = StdioServerParameters(
            command="python",
            args=[str(server_path)],
            env=None,
        )

        # Create client session
        stdio_transport = await stdio_client(server_params)
        client_session = ClientSession(*stdio_transport)

        # Initialize session
        await client_session.initialize()

        logger.info("My New MCP client initialized successfully")
        return client_session

    except Exception as e:
        logger.error("Failed to initialize My New MCP client: %s", e)
        return None


# Optional: Auto-registration with MCPToolRegistry
async def _register_with_registry():
    """Auto-register with MCPToolRegistry if available."""
    try:
        from utils.tool_registry import get_tool_registry

        client = await get_my_new_mcp_client()
        if client:
            registry = get_tool_registry()
            await registry.register_server(
                label="my_new",
                client=client,
                domain="my_domain",
                priority=10,
                auto_discover=True,
            )
            logger.info("My New MCP client registered with MCPToolRegistry")
    except Exception as e:
        logger.warning("Could not auto-register My New MCP client: %s", e)
```

**Key points:**
- Factory function named `get_<label>_mcp_client()`
- Check enabled flag from config or env var
- Use `StdioServerParameters` for local Python servers
- Return `None` if disabled or error (graceful degradation)
- Optional: Auto-register with `MCPToolRegistry`

---

## Step 3: Register in config/mcp_servers.yaml

**Location:** `app/agentic/eol/config/mcp_servers.yaml`

**Add YAML entry** (copy-paste ready):

```yaml
  # My New MCP server
  - name: my_new_mcp
    label: my_new
    command: python
    args:
      - "mcp_servers/my_new_mcp_server.py"
    domains:
      - my_domain
    priority: 10
    enabled: ${MY_NEW_ENABLED:-true}
```

**Field reference:**

| Field | Description | Example |
|-------|-------------|---------|
| `name` | Human-readable server name | `my_new_mcp` |
| `label` | Unique identifier (used in code) | `my_new` |
| `command` | Executable command | `python` or `node` |
| `args` | Command arguments (relative path) | `["mcp_servers/my_new_mcp_server.py"]` |
| `domains` | Domain labels (DomainLabel enum) | `["my_domain"]` or `["sre", "health"]` |
| `priority` | Collision resolution (lower = higher priority) | `10` (standard), `5` (high), `15` (low) |
| `enabled` | Env var toggle with default | `${MY_NEW_ENABLED:-true}` |

**Priority guidelines:**
- `5` — High priority (Azure MCP, external packages)
- `10` — Standard priority (local Python servers)
- `15` — Low priority (fallback servers, CLI executors)

---

## Step 4: Wire Client Factory in MCPHost

**Location:** `app/agentic/eol/utils/mcp_host.py`

**Find function:** `_get_client_for_label(label: str)`

**Add one elif branch:**

```python
async def _get_client_for_label(label: str) -> Optional[ClientSession]:
    """Get MCP client for given label (lazy import pattern)."""
    if label == "azure":
        from .azure_mcp_client import get_azure_mcp_client
        return await get_azure_mcp_client()

    elif label == "sre":
        from .sre_mcp_client import get_sre_mcp_client
        return await get_sre_mcp_client()

    # ... existing branches ...

    elif label == "my_new":  # <-- ADD THIS BLOCK
        from .my_new_mcp_client import get_my_new_mcp_client
        return await get_my_new_mcp_client()

    else:
        logger.warning("Unknown MCP client label: %s", label)
        return None
```

**Key points:**
- Lazy import inside branch (avoids circular imports)
- Match `label` exactly to YAML entry
- Return `None` for unknown labels (graceful degradation)

---

## Step 5: Verify with Smoke Test

### Smoke Test 1: Config Loader

```bash
cd app/agentic/eol

# Verify YAML parses correctly
python -c "
from utils.mcp_config_loader import MCPConfigLoader

loader = MCPConfigLoader()
servers = loader.get_all_servers()

# Find your server
my_server = [s for s in servers if s.label == 'my_new']
if my_server:
    print(f'✅ Found server: {my_server[0].name}')
    print(f'   Enabled: {my_server[0].enabled}')
    print(f'   Domains: {my_server[0].domains}')
else:
    print('❌ Server not found in YAML')
"
```

### Smoke Test 2: MCPHost Initialization

```bash
cd app/agentic/eol

# Test MCPHost.from_config() with only your server enabled
MY_NEW_ENABLED=true \
  SRE_ENABLED=false AZURE_MCP_ENABLED=false \
  NETWORK_MCP_ENABLED=false COMPUTE_MCP_ENABLED=false \
  STORAGE_MCP_ENABLED=false MONITOR_MCP_ENABLED=false \
  PATCH_MCP_ENABLED=false OS_EOL_MCP_ENABLED=false \
  INVENTORY_MCP_ENABLED=false AZURE_CLI_EXECUTOR_ENABLED=false \
  python -c "
import asyncio
from utils.mcp_host import MCPHost

async def test():
    host = await MCPHost.from_config()
    tools = host.get_available_tools()
    print(f'✅ MCPHost initialized with {len(tools)} tools')
    for tool in tools:
        print(f'   - {tool.name}')

asyncio.run(test())
"
```

**Expected output:**
```
✅ MCPHost initialized with 2 tools
   - my_custom_tool
   - another_tool
```

### Smoke Test 3: Tool Registry

```bash
cd app/agentic/eol

# Verify tools registered in MCPToolRegistry
python -c "
from utils.tool_registry import get_tool_registry

registry = get_tool_registry()
stats = registry.get_stats()

print('Tool Registry Stats:')
for domain, count in stats.items():
    print(f'  {domain}: {count} tools')
"
```

### Smoke Test 4: Full Integration

```bash
cd app/agentic/eol

# Start application and test via API
uvicorn main:app --reload --port 8000

# In another terminal:
curl -X POST http://localhost:8000/api/azure-mcp/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Use my_custom_tool with param1=test and param2=42",
    "conversation_id": "test-001"
  }'
```

---

## Domains Reference

**Available domain values** (from `utils/domain_classifier.py`):

| Domain | Use For |
|--------|---------|
| `sre` | Site reliability, health checks, incident response |
| `monitoring` | Metrics, alerts, observability |
| `network` | Networking, NSGs, routes, VNets |
| `inventory` | Resource discovery, cataloging |
| `patch` | Patch management, OS updates |
| `compute` | Virtual machines, scale sets |
| `storage` | Storage accounts, blobs, files |
| `cost` | Cost analysis, budgets, optimization |
| `security` | Security compliance, audits, policies |
| `general` | General Azure operations |

**Custom domains:** If your server needs a new domain not in the list above, add to `DomainLabel` enum in `utils/domain_classifier.py`.

---

## Troubleshooting

### Server Not Initializing

**Symptom:** `MCPHost.from_config()` returns 0 tools for your server

**Check:**
1. Server enabled in env? `echo $MY_NEW_ENABLED` → should be `true`
2. YAML syntax correct? Run smoke test 1
3. Client factory returns session? Add debug logging in `get_my_new_mcp_client()`
4. Server script executable? `python mcp_servers/my_new_mcp_server.py`

### Tools Not Showing in Registry

**Symptom:** Smoke test 3 doesn't show your domain

**Check:**
1. `@mcp.tool()` decorator on all tools?
2. Server script has `if __name__ == "__main__": mcp.run()`?
3. Client session initialized? `await client_session.initialize()`
4. Auto-registration called? (Optional step in client wrapper)

### Import Errors

**Symptom:** `ModuleNotFoundError` or `ImportError`

**Solutions:**
- Ensure working directory is `app/agentic/eol/`
- Check relative imports in client wrapper
- Verify `utils/` and `mcp_servers/` in Python path
- Run from correct directory: `cd app/agentic/eol && python -c "..."`

### Tool Collision Warnings

**Symptom:** `logger.warning("Tool name collision: <tool_name>")`

**Cause:** Another server already registered a tool with same name

**Solutions:**
1. Rename your tool (recommended)
2. Adjust priority (lower number wins)
3. Check `MCPToolRegistry.get_stats()` to see existing tools

---

## Advanced: Node.js/TypeScript MCP Server

For external npm-based MCP servers (like `@azure/mcp`):

### YAML Entry

```yaml
  - name: my_npm_server
    label: my_npm
    command: node
    args:
      - "npx"
      - "-y"
      - "@my-org/my-mcp@latest"
      - "server"
      - "start"
    domains:
      - my_domain
    priority: 5
    enabled: ${MY_NPM_ENABLED:-true}
```

### Client Wrapper

```python
async def get_my_npm_mcp_client() -> Optional[ClientSession]:
    """Factory for npm-based MCP server."""
    try:
        server_params = StdioServerParameters(
            command="node",
            args=["npx", "-y", "@my-org/my-mcp@latest", "server", "start"],
            env=None,
        )

        stdio_transport = await stdio_client(server_params)
        client_session = ClientSession(*stdio_transport)
        await client_session.initialize()

        return client_session
    except Exception as e:
        logger.error("Failed to initialize npm MCP client: %s", e)
        return None
```

---

## Checklist

Before marking complete, verify:

- [ ] MCP server created in `mcp_servers/my_new_mcp_server.py`
- [ ] MCP client wrapper created in `utils/my_new_mcp_client.py`
- [ ] YAML entry added to `config/mcp_servers.yaml`
- [ ] Client factory wired in `utils/mcp_host.py` → `_get_client_for_label()`
- [ ] Smoke test 1 passes (YAML parses)
- [ ] Smoke test 2 passes (MCPHost initializes)
- [ ] Smoke test 3 passes (tools in registry)
- [ ] Full integration test passes (API call works)
- [ ] Environment variable toggle works (`MY_NEW_ENABLED=false`)

**Estimated time:** 15-25 minutes for experienced developers

---

## Related Documentation

| Document | Purpose |
|----------|---------|
| [MIGRATION_GUIDE.md](../../../.planning/MIGRATION_GUIDE.md) | Complete architecture migration guide |
| [ORCHESTRATOR_GUIDE.md](../../../.claude/docs/ORCHESTRATOR_GUIDE.md) | When to use each orchestrator |
| [AGENT-HIERARCHY.md](../../../.claude/docs/AGENT-HIERARCHY.md) | 5-layer stack and debugging |
| [mcp_servers.yaml](../config/mcp_servers.yaml) | Server configuration reference |

---

**Maintained by:** Orchestrator Architecture Refactor Team
**Last Updated:** 2026-03-02
**Version:** 1.0
