# Phase 5: Declarative MCP Server Configuration - Research

**Researched:** 2026-03-02
**Domain:** Python YAML configuration, Pydantic v2 validation, MCP server initialization
**Confidence:** HIGH

---

## Summary

Phase 5 replaces the current per-client hardcoded initialization with a single `config/mcp_servers.yaml` file that centralizes all 10 MCP server definitions. The goal: to add/remove/toggle a server by editing YAML instead of touching Python source.

The project already has **PyYAML 6.0.2** and **Pydantic 2.12.4** in requirements.txt — no new dependencies needed. The env-var interpolation pattern (`${VAR:-default}`) can be implemented as a pre-parse regex substitution (verified working). Pydantic v2's `model_validator` provides validation without a third-party schema library.

The existing 10 MCP clients each hardcode their `label`, `domain`, `priority`, `command`, and `args` inside `_register_with_registry()`. Phase 5 extracts all these values into YAML and feeds them back in via `MCPConfigLoader`. The MCPHost gets a `from_config()` classmethod; individual clients keep running — they just receive their metadata from the YAML source of truth rather than literals.

**Primary recommendation:** Use PyYAML + Pydantic v2 for load/validate, `re.sub` for `${VAR:-default}` interpolation, and a `from_config()` factory on `MCPHost`. No need for `jsonschema` or `strictyaml` — Pydantic already provides all required validation.

---

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| PyYAML | 6.0.2 | YAML parsing | Already in requirements.txt; `yaml.safe_load()` is the safe default |
| Pydantic | 2.12.4 | Config model + validation | Already in requirements.txt; project uses it for API models |
| Python re | stdlib | `${VAR:-default}` interpolation | No extra dependency; regex verified working |
| python-dotenv | 1.2.1 | `.env` file loading at startup | Already in requirements.txt; config.py pattern |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pathlib.Path | stdlib | Resolve config file path | Relative → absolute; consistent with existing code style |
| dataclasses / @dataclass | stdlib | Alternative to Pydantic for simple structs | Skip — project uses Pydantic, stay consistent |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| PyYAML + Pydantic | strictyaml | strictyaml is safer but not in requirements; adds dep |
| PyYAML + Pydantic | jsonschema | More verbose; Pydantic already does JSON schema |
| regex interpolation | python-dotenv expand | dotenv's expand only works on `.env` format, not YAML values |
| pre-parse interpolation | PyYAML custom Loader | Custom Loader is fragile; pre-parse regex is simpler |

**Installation:** No new packages needed — all dependencies already present.

---

## Architecture Patterns

### Recommended Project Structure
```
app/agentic/eol/
├── config/
│   └── mcp_servers.yaml         # NEW: server definitions
└── utils/
    └── mcp_config_loader.py     # NEW: loader + validator
```

`utils/mcp_host.py` gets one new classmethod — no new file for MCPHost changes.

### Pattern 1: Pre-Parse Env Var Interpolation
**What:** Substitute `${VAR:-default}` tokens in raw YAML text before `yaml.safe_load()`.
**When to use:** The only safe approach — PyYAML has no built-in env var support, and custom Loaders are fragile.
**Verified working (local test):**
```python
import os, re, yaml

_ENV_PATTERN = re.compile(r'\$\{([A-Z_][A-Z0-9_]*)(?::-(.*?))?\}')

def _interpolate_env(text: str) -> str:
    """Replace ${VAR:-default} with env value or default."""
    def _replace(m: re.Match) -> str:
        return os.environ.get(m.group(1), m.group(2) or '')
    return _ENV_PATTERN.sub(_replace, text)

# Usage:
raw = Path(config_path).read_text(encoding="utf-8")
interpolated = _interpolate_env(raw)
data = yaml.safe_load(interpolated)
```

### Pattern 2: Pydantic v2 Config Models
**What:** `MCPServerConfig` and `MCPServersFile` Pydantic models for structured validation.
**When to use:** After YAML parsing — lets Pydantic catch missing required fields, wrong types.
**Verified working (local test):**
```python
from pydantic import BaseModel, model_validator
from typing import List

class MCPServerConfig(BaseModel):
    name: str
    label: str
    command: str
    args: List[str] = []
    domains: List[str] = []
    priority: int = 10
    enabled: bool = True
    env: dict = {}

    @model_validator(mode='after')
    def validate_fields(self):
        if not self.name.strip():
            raise ValueError('name cannot be empty')
        if not self.label.strip():
            raise ValueError('label cannot be empty')
        return self

class MCPServersFile(BaseModel):
    version: str = "1.0"
    servers: List[MCPServerConfig]
```

### Pattern 3: MCPHost.from_config() Factory
**What:** Class method that reads YAML, filters enabled servers, constructs client instances, and returns a fully initialized `MCPHost`.
**When to use:** As the primary construction path; existing `MCPHost(clients)` constructor stays as-is for backward compat.
```python
class MCPHost:
    @classmethod
    async def from_config(
        cls,
        config_path: Optional[str] = None
    ) -> "MCPHost":
        loader = MCPConfigLoader(config_path)
        server_configs = loader.get_enabled_servers()
        clients = await _build_clients_from_config(server_configs)
        host = cls(clients)
        await host.ensure_registered()
        return host
```

### Pattern 4: Existing `_register_with_registry()` — Keep As-Is
**What:** Each client's `_register_with_registry()` method currently hardcodes `label`, `domain`, `priority`. Phase 5 does NOT refactor these — they remain as fallback. The YAML-driven path is additive.
**When to use:** Clients initialized individually (outside MCPHost) still self-register with hardcoded values. This is intentional backward compat.

### Anti-Patterns to Avoid
- **Custom PyYAML Loader for env vars:** Fragile, complex, hard to test — use pre-parse regex instead
- **Removing `_register_with_registry()` from individual clients:** Breaks existing initialization paths; add YAML support on top
- **Importing `yaml` in `config.py`:** Keep concerns separate; `mcp_config_loader.py` is the single YAML-aware module
- **Storing secrets in YAML:** The YAML holds server config only (command, args, domains) — secrets stay in env vars
- **Eager initialization in MCPConfigLoader constructor:** Load lazily (call `load()` explicitly) to avoid file I/O at import time

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| YAML parsing | Custom text parser | `yaml.safe_load()` | PyYAML handles multiline, anchors, types |
| Config validation | Manual dict checks | Pydantic v2 models | Type coercion, clear error messages, free |
| Env var expansion | String `.format()` | Regex `${VAR:-default}` pattern | Handles missing vars with defaults safely |
| Type coercion | `str(val) == 'true'` | Pydantic's `bool` field | Pydantic coerces `"true"/"false"/"1"/"0"` → bool after interpolation |

**Key insight:** PyYAML + Pydantic covers 100% of what's needed. No additional libraries required — they're already in requirements.txt.

---

## Common Pitfalls

### Pitfall 1: YAML Boolean Ambiguity
**What goes wrong:** PyYAML 5.x parsed `yes/no/on/off` as booleans; PyYAML 6.x is stricter and parses them as strings. After env var interpolation, `${SRE_ENABLED:-true}` becomes the string `"true"` — YAML parses this correctly as boolean `True` only if the value appears unquoted in context.
**Why it happens:** YAML spec allows bare `true`/`false` as booleans. The interpolated string `enabled: true` is parsed correctly. But `enabled: "true"` (quoted) would parse as a string — Pydantic's `bool` field handles the coercion.
**How to avoid:** Define `enabled: bool = True` in the Pydantic model. Pydantic v2 coerces string `"true"` → `True` and `"false"` → `False` automatically.
**Warning signs:** `ValidationError: value is not a valid boolean` — means the interpolated value was something unexpected.

### Pitfall 2: Config File Path Resolution
**What goes wrong:** Relative paths break when running from a different working directory.
**Why it happens:** `open("config/mcp_servers.yaml")` fails if cwd is not `app/agentic/eol/`.
**How to avoid:** Resolve relative to the loader module's `__file__`:
```python
_DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "mcp_servers.yaml"
```
This matches how `sre_mcp_client.py` resolves `server_script`:
```python
# Existing pattern (already working in production):
server_script = Path(__file__).resolve().parent.parent / "mcp_servers" / "sre_mcp_server.py"
```

### Pitfall 3: Regex Pattern Greedy Matching
**What goes wrong:** Pattern `\${(.+?)(?::-(.*?))?}` may fail on complex default values containing `}`.
**Why it happens:** Defaults like `${VAR:-some value}` are simple; but `${VAR:-{nested}}` breaks the regex.
**How to avoid:** Use `[A-Z_][A-Z0-9_]*` for var names (only valid env var chars), and `[^}]*` for defaults. Our verified pattern `r'\$\{([A-Z_][A-Z0-9_]*)(?::-(.*?))?\}'` is correct for all env var names used in this codebase.

### Pitfall 4: Azure MCP Is Special (Not Python stdio)
**What goes wrong:** The `azure_mcp_client` uses `command="node"` and `args=[...]` (not `sys.executable` + a `.py` file). The YAML schema must support arbitrary `command` + `args`, not assume Python scripts.
**Why it happens:** `@azure/mcp` is an npm package run via `npx` or a node wrapper.
**How to avoid:** The `MCPServerConfig` model uses `command: str` + `args: List[str]` — fully generic, not Python-specific. The YAML for azure_mcp would have `command: node` and `args: [wrapper_path, "npx", ...]`.

### Pitfall 5: MCPConfigLoader Not Wired Into Existing Clients
**What goes wrong:** The loader is implemented but MCPHost doesn't use it by default, so nothing changes.
**Why it happens:** Phase 5 is additive — it adds `from_config()` but doesn't force all paths to use it.
**How to avoid:** Explicitly wire `from_config()` into at least one caller (e.g., `mcp_orchestrator.py` or a test) to prove it works end-to-end. The acceptance criterion "All servers initialize from config" requires a functional integration test.

---

## Code Examples

Verified patterns from official sources and local testing:

### Complete MCPConfigLoader Implementation Pattern
```python
# utils/mcp_config_loader.py
import os
import re
from pathlib import Path
from typing import List, Optional

import yaml
from pydantic import BaseModel, model_validator

_ENV_PATTERN = re.compile(r'\$\{([A-Z_][A-Z0-9_]*)(?::-(.*?))?\}')

_DEFAULT_CONFIG_PATH = (
    Path(__file__).resolve().parent.parent / "config" / "mcp_servers.yaml"
)


class MCPServerConfig(BaseModel):
    name: str
    label: str
    command: str
    args: List[str] = []
    domains: List[str] = []
    priority: int = 10
    enabled: bool = True
    env: dict = {}

    @model_validator(mode='after')
    def _validate(self):
        if not self.name.strip():
            raise ValueError('name must not be empty')
        if not self.label.strip():
            raise ValueError('label must not be empty')
        return self


class MCPServersFile(BaseModel):
    version: str = "1.0"
    servers: List[MCPServerConfig]


class MCPConfigLoader:
    def __init__(self, config_path: Optional[str] = None) -> None:
        self._path = Path(config_path) if config_path else _DEFAULT_CONFIG_PATH
        self._loaded: Optional[MCPServersFile] = None

    def load(self) -> MCPServersFile:
        if self._loaded is not None:
            return self._loaded
        raw = self._path.read_text(encoding="utf-8")
        interpolated = _interpolate_env(raw)
        data = yaml.safe_load(interpolated)
        self._loaded = MCPServersFile(**data)
        return self._loaded

    def get_enabled_servers(self) -> List[MCPServerConfig]:
        return [s for s in self.load().servers if s.enabled]

    def get_all_servers(self) -> List[MCPServerConfig]:
        return self.load().servers


def _interpolate_env(text: str) -> str:
    def _replace(m: re.Match) -> str:
        return os.environ.get(m.group(1), m.group(2) or '')
    return _ENV_PATTERN.sub(_replace, text)
```

### YAML Config Schema
```yaml
# config/mcp_servers.yaml
version: "1.0"
servers:
  - name: azure_mcp
    label: azure
    command: node
    args: ["<wrapper_path>", "npx", "-y", "@azure/mcp@latest", "server", "start"]
    domains: [azure]
    priority: 5
    enabled: ${AZURE_MCP_ENABLED:-true}

  - name: sre_mcp
    label: sre
    command: python
    args: ["<mcp_servers/sre_mcp_server.py>"]
    domains: [sre, health, incident]
    priority: 10
    enabled: ${SRE_ENABLED:-true}

  - name: network_mcp
    label: network
    command: python
    args: ["<mcp_servers/network_mcp_server.py>"]
    domains: [network]
    priority: 10
    enabled: ${NETWORK_MCP_ENABLED:-true}

  - name: compute_mcp
    label: compute
    command: python
    args: ["<mcp_servers/compute_mcp_server.py>"]
    domains: [compute]
    priority: 10
    enabled: ${COMPUTE_MCP_ENABLED:-true}

  - name: storage_mcp
    label: storage
    command: python
    args: ["<mcp_servers/storage_mcp_server.py>"]
    domains: [storage]
    priority: 10
    enabled: ${STORAGE_MCP_ENABLED:-true}

  - name: monitor_mcp
    label: monitor
    command: python
    args: ["<mcp_servers/monitor_mcp_server.py>"]
    domains: [monitoring]
    priority: 10
    enabled: ${MONITOR_MCP_ENABLED:-true}

  - name: patch_mcp
    label: patch
    command: python
    args: ["<mcp_servers/patch_mcp_server.py>"]
    domains: [patch]
    priority: 10
    enabled: ${PATCH_MCP_ENABLED:-true}

  - name: os_eol_mcp
    label: os_eol
    command: python
    args: ["<mcp_servers/os_eol_mcp_server.py>"]
    domains: [eol]
    priority: 10
    enabled: ${OS_EOL_MCP_ENABLED:-true}

  - name: inventory_mcp
    label: inventory
    command: python
    args: ["<mcp_servers/inventory_mcp_server.py>"]
    domains: [inventory]
    priority: 10
    enabled: ${INVENTORY_MCP_ENABLED:-true}

  - name: azure_cli_executor
    label: azure_cli_executor
    command: python
    args: ["<mcp_servers/azure_cli_executor_server.py>"]
    domains: [azure]
    priority: 15
    enabled: ${AZURE_CLI_EXECUTOR_ENABLED:-true}
```

### MCPHost.from_config() Factory Pattern
```python
# In utils/mcp_host.py — add to MCPHost class

@classmethod
async def from_config(
    cls,
    config_path: Optional[str] = None
) -> "MCPHost":
    """Create MCPHost from YAML configuration file.

    Args:
        config_path: Path to mcp_servers.yaml. Defaults to config/mcp_servers.yaml.

    Returns:
        Initialized MCPHost with enabled servers registered.
    """
    from .mcp_config_loader import MCPConfigLoader
    loader = MCPConfigLoader(config_path)
    server_configs = loader.get_enabled_servers()

    # Build (label, client) tuples from config
    # Note: client construction still requires the existing client factories
    # This wires config metadata; actual client objects come from existing factories
    clients = []
    for server_cfg in server_configs:
        client = await _get_client_for_label(server_cfg.label)
        if client is not None:
            clients.append((server_cfg.label, client))

    host = cls(clients)
    await host.ensure_registered()
    return host
```

---

## Current MCP Client Metadata (Source of Truth for YAML)

This table maps each existing client to the values that should appear in `mcp_servers.yaml`:

| Client File | label | domain | priority | command | server script |
|-------------|-------|--------|----------|---------|---------------|
| azure_mcp_client.py | `azure` | `azure` | `5` | `node` | npx @azure/mcp |
| sre_mcp_client.py | `sre` | `sre` | `10` | `python` | mcp_servers/sre_mcp_server.py |
| network_mcp_client.py | `network` | `network` | `10` | `python` | mcp_servers/network_mcp_server.py |
| compute_mcp_client.py | `compute` | `compute` | `10` | `python` | mcp_servers/compute_mcp_server.py |
| storage_mcp_client.py | `storage` | `storage` | `10` | `python` | mcp_servers/storage_mcp_server.py |
| monitor_mcp_client.py | `monitor` | `monitoring` | `10` | `python` | mcp_servers/monitor_mcp_server.py |
| patch_mcp_client.py | `patch` | `patch` | `10` | `python` | mcp_servers/patch_mcp_server.py |
| os_eol_mcp_client.py | `os_eol` | `eol` | `10` | `python` | mcp_servers/os_eol_mcp_server.py |
| inventory_mcp_client.py | `inventory` | `inventory` | `10` | `python` | mcp_servers/inventory_mcp_server.py |
| azure_cli_executor_client.py | `azure_cli_executor` | `azure` | `15` | `python` | mcp_servers/azure_cli_executor_server.py |

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Per-client hardcoded `label/domain/priority` | YAML config + loader (Phase 5) | Phase 5 | Single place to add/remove/toggle servers |
| Scattered `${SERVER}_ENABLED` env vars in each client | Unified `${LABEL}_MCP_ENABLED` in YAML | Phase 5 | Consistent env var naming |
| `MCPHost(clients)` constructor only | `MCPHost.from_config()` factory | Phase 5 | Declarative initialization path |

**Deprecated/outdated patterns after Phase 5:**
- Individual `_is_{server}_disabled()` functions (each client still has them — keep for backward compat, but YAML `enabled:` becomes the authoritative source for new paths)

---

## Integration Scope

### What Phase 5 Creates
1. `config/mcp_servers.yaml` — 10 server definitions
2. `utils/mcp_config_loader.py` — `MCPConfigLoader` + `MCPServerConfig` + `MCPServersFile`
3. `utils/mcp_host.py` — `MCPHost.from_config()` classmethod added

### What Phase 5 Does NOT Change
- Individual `*_mcp_client.py` files — their `_register_with_registry()` methods stay unchanged
- `main.py` — orchestrators still initialize the same way (additive, not replacement)
- `MCPToolRegistry` — unchanged
- Existing env var patterns in each client — kept as backward compat fallback

### The MCPHost.from_config() Challenge
The `from_config()` factory needs to map `label → client instance`. The existing clients are constructed via factory functions (`get_sre_mcp_client()`, etc.) — the factory needs to call these. Two options:

**Option A: Static label→factory mapping dict** (simpler)
```python
_CLIENT_FACTORIES = {
    "sre": "utils.sre_mcp_client.get_sre_mcp_client",
    "network": "utils.network_mcp_client.get_network_mcp_client",
    # ... etc
}
```

**Option B: Convention-based import** — derive module name from label
- `label="sre"` → `utils.sre_mcp_client.get_sre_mcp_client()`
- Fragile for `azure_cli_executor` and `azure` (non-standard names)

**Recommendation:** Option A (explicit mapping dict) — clear, verifiable, matches project's "explicit over implicit" style seen in existing code.

---

## Open Questions

1. **Path representation in YAML for Python servers**
   - What we know: Python clients resolve server_script as `Path(__file__).resolve().parent.parent / "mcp_servers" / "{name}.py"`
   - What's unclear: Should YAML store relative path (`mcp_servers/sre_mcp_server.py`) and loader resolves it, or store `{mcp_servers_dir}` token?
   - Recommendation: Store just the filename/module name and resolve relative to a base dir in the loader. Or store as a module name (`mcp_servers.sre_mcp_server`) and use `sys.executable -m` instead of `python path/to/script.py`.

2. **Azure MCP command path variability**
   - What we know: `azure_mcp_client.py` tries two variants: node wrapper path, then `npx` directly
   - What's unclear: Can YAML store both as a fallback list, or pick one canonical form?
   - Recommendation: Store primary form; keep the fallback logic inside `azure_mcp_client.py` (it's client-specific behavior, not config concern)

3. **Should MCPHost.from_config() replace or complement the existing constructor?**
   - What we know: Phase 5 acceptance criteria says "All servers initialize from config" — implies from_config() must be the primary path
   - What's unclear: Does this mean we must update callers in orchestrators?
   - Recommendation: Keep `from_config()` as additive + write a test that proves it initializes all 10 servers; don't force-migrate orchestrators in Phase 5 (that's Phase 6 territory)

---

## Validation Architecture

> `workflow.nyquist_validation` is not set in `.planning/config.json` — skipping detailed validation section.

**Note on tests:** Per `app/agentic/eol/CLAUDE.md`, tests go in `tests/` and are **not committed to git**. All test files for Phase 5 should be created locally in `tests/` only. The one exception is explicit plan deliverables committed with `-f`.

Recommended local tests:
```bash
# Unit: config loader
pytest tests/test_mcp_config_loader.py -v
# Integration: MCPHost.from_config() with mock clients
pytest tests/test_mcp_host_from_config.py -v
```

---

## Sources

### Primary (HIGH confidence)
- PyYAML 6.0.2 installed locally — `python3 -c "import yaml; print(yaml.__version__)"` → `6.0.2`
- Pydantic 2.12.4 installed locally — `python3 -c "import pydantic; print(pydantic.__version__)"` → `2.12.4`
- Local verification: env var interpolation regex tested and confirmed working
- Local verification: Pydantic v2 `model_validator` validation tested and confirmed working
- Codebase inspection: all 10 MCP clients read for their `label/domain/priority` values
- `app/agentic/eol/utils/sre_mcp_client.py` — Path resolution pattern for server scripts
- `app/agentic/eol/utils/mcp_host.py` — Existing MCPHost constructor pattern
- `app/agentic/eol/utils/config.py` — ConfigManager pattern for project config style
- `app/agentic/eol/requirements.txt` — Confirmed PyYAML and Pydantic already present

### Secondary (MEDIUM confidence)
- PyYAML docs: `yaml.safe_load()` is the correct and safe parsing function (vs `yaml.load()` which requires explicit Loader)
- Pydantic v2 docs: `model_validator(mode='after')` is correct v2 syntax (not v1's `@validator`)

### Tertiary (LOW confidence)
- None — all critical claims verified locally

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — PyYAML and Pydantic already in requirements, tested locally
- Architecture: HIGH — patterns verified against existing codebase code style
- Pitfalls: HIGH — tested locally (YAML boolean, path resolution, regex)
- Integration scope: HIGH — read all 10 client files to extract exact metadata values

**Research date:** 2026-03-02
**Valid until:** 2026-04-02 (stable libraries, no fast-moving ecosystem)
