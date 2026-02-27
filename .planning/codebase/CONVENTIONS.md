# GCC Demo - Coding Conventions

> **Version:** 1.0
> **Last Updated:** 2026-02-27
> **Scope:** Infrastructure (Terraform) + Application (Python/FastAPI)

---

## Table of Contents

1. [Naming Conventions](#naming-conventions)
2. [Python Code Style](#python-code-style)
3. [Terraform Conventions](#terraform-conventions)
4. [Architecture Patterns](#architecture-patterns)
5. [Documentation Standards](#documentation-standards)
6. [Error Handling](#error-handling)
7. [Logging Patterns](#logging-patterns)

---

## Naming Conventions

### Python Modules and Files

- **Snake case** for all Python files: `eol_orchestrator.py`, `response_models.py`, `mcp_composite_client.py`
- **Test files** prefixed with `test_`: `test_sre_gateway.py`, `test_router.py`
- **MCP servers** suffixed with `_mcp_server.py`: `inventory_mcp_server.py`, `patch_mcp_server.py`
- **MCP clients** suffixed with `_mcp_client.py`: `sre_mcp_client.py`, `network_mcp_client.py`
- **Base classes** prefixed with `base_`: `base_eol_agent.py`, `base_sre_agent.py`

### Python Classes

- **PascalCase** for all classes: `StandardResponse`, `EOLOrchestratorAgent`, `SREGateway`
- **Agents** suffixed with `Agent`: `OSInventoryAgent`, `SoftwareInventoryAgent`, `MicrosoftEOLAgent`
- **Orchestrators** suffixed with `Orchestrator`: `EOLOrchestrator`, `SREOrchestrator`
- **Base classes** prefixed with `Base`: `BaseEOLAgent`, `BaseSREAgent`

### Python Functions and Variables

- **Snake case** for functions: `get_eol_data()`, `ensure_standard_format()`, `record_agent_request()`
- **Private functions** prefixed with underscore: `_determine_status()`, `_llm_classify()`, `_ensure_agents()`
- **Async functions** use `async def`: `async def get_inventory()`, `async def classify()`
- **Boolean variables** prefixed with verb: `is_available`, `enable_streaming`, `cache_hit`, `had_error`

### Configuration and Constants

- **UPPER_SNAKE_CASE** for constants: `DEFAULT_CACHE_TTL_SECONDS`, `MAX_CONCURRENT_EOL_ANALYSIS`, `HIGH_CONFIDENCE_THRESHOLD`
- **Config dataclasses** suffixed with `Config`: `AzureConfig`, `AppConfig`, `InventoryConfig`, `PatchManagementConfig`
- **Environment variables** use UPPER_SNAKE_CASE: `AZURE_OPENAI_ENDPOINT`, `LOG_ANALYTICS_WORKSPACE_ID`, `SRE_AGENT_TOOL_TIMEOUT`

### Terraform Resources

- **Pattern:** `<type>-<component>-<project>-<environment>`
- **Examples:**
  - Network interfaces: `nic-nva-${var.project_name}-${var.environment}`
  - Virtual machines: `vm-onprem-win2025-${var.project_name}-${var.environment}`
  - Public IPs: `pip-onprem-windows-2016-${var.project_name}-${var.environment}`
- **Hub resources** use `hub_` prefix in variables: `hub_vnet_address_space`, `hub_gateway_subnet_prefix`

### Terraform Variables

- **Snake case** for all variables: `project_name`, `environment`, `resource_group_name`
- **Boolean flags** prefixed with `deploy_`: `deploy_route_server`, `deploy_squid_proxy`, `deploy_onprem_vnet`
- **Optional resources** use `count = var.deploy_<component> ? 1 : 0` pattern

---

## Python Code Style

### Import Organization

```python
# Standard library imports (grouped)
import asyncio
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# Third-party imports (grouped by package)
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
from azure.identity import DefaultAzureCredential

# Local application imports (grouped by type)
from utils import get_logger, config
from utils.response_models import StandardResponse
from agents.eol_orchestrator import EOLOrchestratorAgent
```

### Async/Await Usage

- **Async-first** for all I/O operations and network calls
- Use `async def` for functions that perform I/O, call external services, or coordinate async operations
- Always `await` async function calls
- Use `asyncio.gather()` for concurrent operations
- Use `asyncio.wait_for()` for timeout protection

```python
# Good: Async for I/O
async def get_inventory() -> Dict[str, Any]:
    result = await inventory_agent.fetch_data()
    return result

# Good: Concurrent operations
results = await asyncio.gather(
    agent1.get_data(),
    agent2.get_data(),
    return_exceptions=True
)

# Good: Timeout protection
result = await asyncio.wait_for(
    func(*args, **kwargs),
    timeout=timeout_seconds
)
```

### Type Hints

- **Always use type hints** for function parameters and return types
- Use `Optional[T]` for nullable values
- Use `Dict[str, Any]` for flexible dictionaries
- Use `List[T]` for homogeneous lists
- Import types from `typing` module

```python
from typing import Dict, List, Any, Optional

async def get_eol_data(
    software_name: str,
    version: Optional[str] = None,
    **kwargs
) -> Dict[str, Any]:
    """Get EOL data with proper type hints."""
    pass
```

### Dataclasses and Models

- Use `@dataclass` for configuration objects
- Use Pydantic `BaseModel` for API request/response models
- Use `field(default_factory=...)` for mutable defaults
- Include type hints for all fields

```python
from dataclasses import dataclass, field
from typing import Dict, List

@dataclass
class InventoryConfig:
    enable_inventory: bool = field(
        default_factory=lambda: os.getenv("INVENTORY_ENABLE", "true").lower() == "true"
    )
    default_l1_ttl: int = 300
    resource_type_ttl_overrides: Dict[str, int] = field(default_factory=lambda: {
        "Microsoft.Compute/virtualMachines": 1800,
    })
```

### Docstrings

- **Use triple-quoted strings** for all module, class, and function docstrings
- Follow **Google style** for docstrings
- Include parameter types, return types, and examples where helpful

```python
def with_timeout_and_stats(
    agent_name: str,
    timeout_seconds: int = 30,
    track_cache: bool = True,
    auto_wrap_response: bool = True
):
    """
    Decorator to add timeout, error handling, and cache statistics to async endpoints.

    This decorator:
    1. Wraps the endpoint function with timeout protection
    2. Records cache statistics for performance tracking
    3. Handles common errors consistently
    4. Optionally wraps results in StandardResponse format

    Args:
        agent_name: Name of the agent/service for logging and stats
        timeout_seconds: Maximum execution time before timeout
        track_cache: Whether to record cache statistics
        auto_wrap_response: Whether to automatically wrap non-StandardResponse returns

    Usage:
        @app.get("/api/example")
        @with_timeout_and_stats(agent_name="example", timeout_seconds=30)
        async def example_endpoint():
            result = await some_async_operation()
            return result  # Will be wrapped in StandardResponse automatically

    Returns:
        Decorated async function with timeout and error handling
    """
```

---

## Terraform Conventions

### Resource Organization

- **Main resources** in `main.tf`
- **Variables** in `variables.tf`
- **Outputs** in `outputs.tf`
- **Providers** in `providers.tf` (root only)

### Comments and Documentation

```hcl
# ============================================================================
# SECTION HEADER (uppercase, 76 chars wide)
# ============================================================================
# Brief description of what this section does

# Network Interface for NVA
resource "azurerm_network_interface" "nic_nva" {
  count = var.deploy_route_server && var.deploy_linux_nva ? 1 : 0
  name  = "nic-nva-${var.project_name}-${var.environment}"
  # ...
}
```

### Conditional Resources

```hcl
# Use count for optional resources
resource "azurerm_public_ip" "pip_example" {
  count = var.deploy_component ? 1 : 0
  # ...
}

# Use dynamic blocks for conditional sub-resources
dynamic "ip_configuration" {
  for_each = var.enable_feature ? [1] : []
  content {
    # ...
  }
}
```

### Variable Definitions

```hcl
variable "project_name" {
  description = "The name of the project"
  type        = string
}

variable "hub_gateway_subnet_prefix" {
  description = "Address prefix for the gateway subnet"
  type        = string
  default     = null
}

variable "deploy_squid_proxy" {
  description = "Whether to deploy Squid proxy VM"
  type        = bool
  default     = false
}
```

---

## Architecture Patterns

### API Response Format

**All API endpoints MUST return `StandardResponse` format:**

```python
from utils.response_models import StandardResponse

# Success response
return StandardResponse.success_response(
    data=[{"id": 1, "name": "test"}],
    cached=True,
    metadata={"source": "cosmos_db"}
)

# Error response
return StandardResponse.error_response(
    error="Database connection failed",
    metadata={"retry_count": 3}
)
```

### Endpoint Decorators

**Use standardized decorators for all API endpoints:**

```python
from utils.endpoint_decorators import (
    standard_endpoint,
    readonly_endpoint,
    write_endpoint
)

# Standard endpoint (most common)
@router.get("/api/example", response_model=StandardResponse)
@standard_endpoint(agent_name="example", timeout_seconds=30)
async def example_endpoint():
    return result

# Read-only endpoint (shorter timeout, no cache tracking)
@router.get("/api/status", response_model=StandardResponse)
@readonly_endpoint(agent_name="status", timeout_seconds=5)
async def status_endpoint():
    return result

# Write endpoint (longer timeout, no cache tracking)
@router.post("/api/update", response_model=StandardResponse)
@write_endpoint(agent_name="update", timeout_seconds=60)
async def update_endpoint():
    return result
```

### Caching Strategy

**Two-tier caching (L1 in-memory + L2 persistence):**

```python
# L1: In-memory cache
from utils.eol_cache import eol_cache

# Check L1 first
cached = eol_cache.get(cache_key)
if cached:
    return cached

# L2: Cosmos DB (when enabled)
from utils.cosmos_cache import base_cosmos

if base_cosmos.is_available():
    cached = await base_cosmos.get_response(cache_key)
    if cached:
        eol_cache.set(cache_key, cached)  # Backfill L1
        return cached

# Source execution if not cached
result = await fetch_from_source()
eol_cache.set(cache_key, result)
if base_cosmos.is_available():
    await base_cosmos.store_response(cache_key, result)
```

### MCP Architecture

**Local MCP servers expose tools via FastMCP:**

```python
from mcp.server.fastmcp import FastMCP

mcp = FastMCP(name="inventory")

@mcp.tool()
async def get_software_inventory(
    workspace_id: str
) -> Dict[str, Any]:
    """Get software inventory from Log Analytics."""
    # Tool implementation
    return {"success": True, "data": [...]}
```

**Clients consume MCP tools:**

```python
from utils.inventory_mcp_client import inventory_mcp_client

result = await inventory_mcp_client.call_tool(
    "get_software_inventory",
    {"workspace_id": workspace_id}
)
```

### Agent Base Classes

**All EOL agents extend `BaseEOLAgent`:**

```python
from agents.base_eol_agent import BaseEOLAgent

class MicrosoftEOLAgent(BaseEOLAgent):
    def __init__(self):
        super().__init__(agent_name="microsoft")

    async def get_eol_data(
        self,
        software_name: str,
        version: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        # Implementation
        return self.create_success_response(
            software_name=software_name,
            version=version,
            eol_date="2025-10-14",
            confidence=0.95
        )
```

---

## Documentation Standards

### CLAUDE.md Files

**Every major directory has a CLAUDE.md file:**

- **Purpose:** Domain-specific navigation and patterns
- **Location:** `app/agentic/eol/CLAUDE.md`, `app/agentic/eol/agents/CLAUDE.md`, etc.
- **Format:** Markdown with consistent structure

**Standard sections:**
1. Quick Reference
2. Current Structure (with counts)
3. Core Patterns
4. Common Commands/Testing
5. Version footer

### README Files

- Technical documentation for implementation details
- Located alongside CLAUDE.md files
- Focus on HOW to implement, not navigation

### Inline Comments

```python
# Good: Explains WHY, not WHAT
# Detect if running in Azure App Service
is_azure_app_service = os.environ.get('WEBSITE_SITE_NAME') is not None

# Bad: Restates code
# Set the variable
is_azure_app_service = os.environ.get('WEBSITE_SITE_NAME') is not None
```

### Docstring Examples

Include usage examples in docstrings for complex functions:

```python
def ensure_standard_format(response: Any) -> Dict[str, Any]:
    """Ensure any response is in standard format.

    Example:
        # Handle various formats
        result = ensure_standard_format(legacy_response)
        # Always returns {"success": bool, "data": [...], ...}
    """
```

---

## Error Handling

### Decorator-Based Error Handling

```python
from utils.error_handlers import handle_api_errors, handle_agent_errors

# API endpoint error handling
@handle_api_errors("Software inventory fetch")
async def get_software_inventory():
    return await inventory_agent.get_software_inventory()

# Agent method error handling
@handle_agent_errors("Microsoft EOL Agent")
async def get_eol_data(self, software_name: str):
    # Agent logic
    pass
```

### Try-Except Patterns

```python
# Preserve HTTPException for FastAPI
try:
    result = await operation()
except HTTPException:
    raise  # Re-raise without wrapping
except Exception as e:
    logger.error(f"Operation failed: {e}", exc_info=True)
    return StandardResponse.error_response(error=str(e))
```

### Retry Logic

```python
from utils.error_handlers import retry_on_failure

@retry_on_failure(max_retries=3, delay_seconds=1.0, backoff_multiplier=2.0)
async def fetch_external_api():
    # API call that might fail
    pass
```

---

## Logging Patterns

### Logger Initialization

```python
from utils import get_logger
from utils import config

# Module-level logger
logger = get_logger(__name__, config.app.log_level)
```

### Log Levels and Emoji Conventions

```python
# INFO: Normal operations (green in development)
logger.info("✅ Cache hit for key: %s", cache_key)

# WARNING: Non-critical issues (yellow)
logger.warning("⚠️ Service check failed: %s", message)

# ERROR: Critical failures (red)
logger.error("❌ Agent failed: %s", str(e), exc_info=True)

# DEBUG: Detailed diagnostics (cyan)
logger.debug("🔍 Request params: %s", params)
```

### Structured Logging

```python
# Include context in extra field
logger.error(
    f"❌ {context} error: {e}",
    exc_info=True,
    extra={
        "context": context,
        "error_type": type(e).__name__,
        "function": func.__name__
    }
)
```

### Azure-Specific Logging

```python
# Auto-detect Azure environments
is_azure_app_service = os.environ.get('WEBSITE_SITE_NAME') is not None
is_container_app = os.environ.get('CONTAINER_APP_NAME') is not None

# Use stderr for Azure environments (better log capture)
if is_azure_app_service or is_container_app:
    stream = sys.stderr
    # Use plain formatter (no colors)
else:
    stream = sys.stdout
    # Use colored formatter
```

### Quiet Noisy Dependencies

```python
# Reduce noise from chatty libraries
logging.getLogger("openai").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
```

---

## File Organization

### Python Application Structure

```
app/agentic/eol/
├── agents/              # 41 agent modules
├── api/                 # 20 router modules
├── mcp_servers/         # 9 local MCP server implementations
├── utils/               # 71 utility modules
├── tests/               # Test suite with run_tests.sh
├── templates/           # Jinja2 HTML templates
├── static/              # JavaScript/CSS assets
├── deploy/              # Container deployment scripts
├── main.py              # FastAPI entrypoint
├── requirements.txt     # Python dependencies
├── .env.example         # Environment variable template
├── pytest.ini           # Test configuration
└── CLAUDE.md            # Domain navigation
```

### Terraform Structure

```
gcc-demo/
├── modules/             # 11 Terraform modules
│   ├── networking/
│   ├── compute/
│   ├── storage/
│   └── ...
├── demos/               # 7 demo scenarios
├── main.tf              # Root module
├── variables.tf         # Root variables
├── outputs.tf           # Root outputs
├── providers.tf         # Provider configuration
└── run-demo.sh          # Demo execution script
```

---

## Version Control

### Git Commit Messages

**Use conventional commit format:**

```
feat: add network agent for SRE operations
fix: resolve cache invalidation bug in inventory
docs: update CLAUDE.md with new agent count
refactor: simplify error handling in orchestrator
test: add unit tests for SRE gateway classification
```

### Co-Authored Commits

**When working with AI assistance:**

```bash
git commit -m "$(cat <<'EOF'
feat: add patch management orchestrator

Implement patch assessment and installation workflows for Azure VMs.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Configuration Management

### Environment Variables

- **Required variables** documented in `.env.example`
- **Config dataclasses** centralized in `utils/config.py`
- **Environment-based defaults** using `field(default_factory=lambda: os.getenv(...))`
- **Validation** via `config.validate_config()`

### Feature Flags

```python
# Boolean feature flags with env var fallback
enable_inventory: bool = field(
    default_factory=lambda: os.getenv("INVENTORY_ENABLE", "true").lower() == "true"
)

# Use in code
if config.inventory.enable_inventory:
    await run_inventory_scan()
```

---

## Code Quality Standards

### Simplicity First

- Make every change as simple as possible
- Impact minimal code
- Avoid over-engineering for simple fixes

### No Laziness

- Find root causes, not symptoms
- No temporary fixes
- Maintain senior developer standards

### Minimal Impact

- Changes should only touch necessary code
- Avoid introducing bugs through unrelated changes
- Keep scope focused

---

**Document Version:** 1.0
**Last Updated:** 2026-02-27
**Maintainer:** Development Team
