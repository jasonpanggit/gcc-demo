# Manifest Authoring Guide

How to write high-quality MCP tool manifests that enable accurate tool selection.

---

## Table of Contents

1. [Why Manifest Quality Matters](#why-manifest-quality-matters)
2. [Manifest Structure](#manifest-structure)
3. [Field-by-Field Guidance](#field-by-field-guidance)
4. [Template for Excellent Manifests](#template-for-excellent-manifests)
5. [Good vs Bad Examples](#good-vs-bad-examples)
6. [Documenting Tool Conflicts](#documenting-tool-conflicts)
7. [Quality Checklist](#quality-checklist)
8. [Running the Linter](#running-the-linter)

---

## Why Manifest Quality Matters

Tool manifests are the primary metadata source for the MCP tool selection pipeline.
When a user asks "list my container apps", the pipeline uses manifest metadata
(tags, example queries, conflict notes) to rank and select the right tool.

**Poor manifests cause:**
- Wrong tool selection (e.g. `speech` chosen for "check health")
- Ambiguous selections where the LLM picks between similarly-described tools
- Missing tools that should appear in selection but don't have relevant tags

**Good manifests cause:**
- Deterministic, correct tool selection on first try
- Clear disambiguation when confusable tools are both available
- Fast retrieval via semantic tags matching user intent

---

## Manifest Structure

Every tool manifest is a `ToolManifest` frozen dataclass:

```python
@dataclass(frozen=True)
class ToolManifest:
    tool_name: str                          # Unique identifier
    source: str                             # MCP server origin
    domains: FrozenSet[str]                 # Domain classification
    tags: FrozenSet[str]                    # Semantic retrieval tags
    affordance: ToolAffordance              # READ | WRITE | DESTRUCTIVE | DEPLOY
    example_queries: Tuple[str, ...]        # Natural language triggers
    conflicts_with: FrozenSet[str]          # Confusable tool names
    conflict_note: str                      # Disambiguation guidance
    preferred_over: FrozenSet[str]          # Priority over other tools
    requires_confirmation: bool = False     # Gate for mutating tools
    deprecated: bool = False                # Sunset flag
    output_schema: Dict = field(default_factory=dict)
```

---

## Field-by-Field Guidance

### `tool_name`

**Purpose:** Unique identifier matching the MCP tool registration name.

**Rules:**
- Must match exactly what the MCP server exposes
- Use `snake_case` (lowercase, underscores)
- Should be descriptive of the action: `verb_noun` pattern preferred

```python
# Good
tool_name="container_app_list"
tool_name="check_resource_health"

# Bad
tool_name="ContainerAppList"   # No PascalCase
tool_name="list"               # Too generic
```

### `source`

**Purpose:** Identifies which MCP server provides this tool.

**Valid values:**
`"azure"` | `"sre"` | `"network"` | `"compute"` | `"storage"` | `"monitor"` |
`"inventory"` | `"os_eol"` | `"azure_cli"` | `"azure_mcp"` | `"patch"`

### `domains`

**Purpose:** Classifies what area of operations this tool belongs to.

**Rules:**
- At least 1 domain required
- Tools that span areas can have 2-3 domains
- Use established domain vocabulary

**Domain vocabulary:**
- `azure_management` - General Azure resource operations
- `sre_health` - Health checks and diagnostics
- `sre_incident` - Incident response and triage
- `sre_performance` - Performance metrics and anomalies
- `sre_cost_security` - Cost and security analysis
- `sre_rca` - Root cause analysis
- `sre_remediation` - Automated fixes
- `network` - Network operations
- `observability` - Monitoring and alerting
- `deployment` - Deploy and release operations
- `arc_inventory` - Arc server inventory
- `documentation` - Documentation lookup

### `tags`

**Purpose:** Semantic keywords for retrieval scoring. These are the primary signal
for finding relevant tools when a user asks a question.

**Rules:**
- Minimum 2 tags, target 3-5
- Use domain-specific vocabulary users would actually say
- Include synonyms and abbreviations
- Don't repeat the tool name as a tag

```python
# Excellent: diverse, user-facing terms
tags=frozenset({"health", "container", "containerapp", "running", "status"})

# Good: covers key concepts
tags=frozenset({"health", "container", "containerapp"})

# Poor: too few, too generic
tags=frozenset({"health"})
```

### `affordance`

**Purpose:** Mutability classification that determines confirmation gates.

| Affordance | Meaning | Confirmation |
|------------|---------|-------------|
| `READ` | Safe, read-only query | None needed |
| `WRITE` | Mutating but reversible | Present plan |
| `DESTRUCTIVE` | Irreversible, high impact | Explicit confirm + gate |
| `DEPLOY` | Deployment lifecycle | Pre-flight + validation |

**Rule:** `DESTRUCTIVE` and `DEPLOY` tools **must** set `requires_confirmation=True`.

### `example_queries`

**Purpose:** Natural language phrases a user would say to trigger this tool.
The primary signal for semantic matching during tool retrieval.

**Rules:**
- Minimum 2 queries, target 4
- Each query should be 3+ words
- Use diverse phrasing (don't repeat the same structure)
- Write what a real user would actually ask, not technical descriptions
- Include different verb forms and question styles

```python
# Excellent: diverse phrasing, user-natural, 4 examples
example_queries=(
    "list all container apps in my subscription",
    "show my container apps",
    "what container apps are running",
    "which container apps do I have deployed",
)

# Good: adequate coverage
example_queries=(
    "list container apps",
    "show my container apps",
    "what container apps are running",
)

# Poor: too few, too short, repetitive
example_queries=(
    "list containers",
    "show containers",
)
```

### `conflicts_with`

**Purpose:** Names of tools that the LLM commonly confuses with this one.

**Rules:**
- Only list tools that have actually been misselected (real confusions)
- Both sides of a conflict should reference each other
- Empty is OK if no confusion has been observed

```python
# check_resource_health conflicts with resourcehealth
conflicts_with=frozenset({"resourcehealth"})

# resourcehealth conflicts with check_resource_health
conflicts_with=frozenset({"check_resource_health"})
```

### `conflict_note`

**Purpose:** Disambiguation text injected into the LLM context when conflicting
tools are both present. This is the most impactful field for reducing misselections.

**Rules:**
- **Required** when `conflicts_with` is non-empty
- Start with what THIS tool does (positive framing)
- Then clarify what it does NOT do
- Mention the specific alternative tool by name

```python
# Excellent: clear, specific, names alternatives
conflict_note=(
    "check_resource_health (SRE) provides deep diagnostics with remediation planning. "
    "resourcehealth (Azure MCP) provides basic platform availability only. "
    "Prefer check_resource_health for actionable SRE insights."
)

# Bad: vague, doesn't help LLM decide
conflict_note="This tool is different from resourcehealth."
```

### `preferred_over`

**Purpose:** Declares that this tool should be ranked higher than named tools
when both are candidates for the same query.

```python
# container_app_list is preferred over azure_cli_execute_command for listing
preferred_over=frozenset({"azure_cli_execute_command"})
```

---

## Template for Excellent Manifests

Copy this template when adding a new tool:

```python
ToolManifest(
    tool_name="<snake_case_name>",
    source="<server_label>",
    domains=frozenset({"<primary_domain>"}),
    tags=frozenset({"<tag1>", "<tag2>", "<tag3>", "<tag4>"}),
    affordance=ToolAffordance.READ,  # or WRITE, DESTRUCTIVE, DEPLOY
    example_queries=(
        "<natural query phrasing 1>",
        "<different phrasing 2>",
        "<question-form phrasing 3>",
        "<action-form phrasing 4>",
    ),
    conflicts_with=frozenset({"<confusable_tool_1>"}),
    conflict_note=(
        "<this_tool> is the preferred tool for <specific use case>. "
        "Do NOT use <confusable_tool_1> for <this use case> — "
        "use it for <its actual use case> instead."
    ),
    preferred_over=frozenset({"<lower_priority_tool>"}),
    requires_confirmation=False,  # True for DESTRUCTIVE/DEPLOY
),
```

---

## Good vs Bad Examples

### Example 1: Health Check Tool

**Excellent manifest:**

```python
ToolManifest(
    tool_name="check_container_app_health",
    source="sre",
    domains=frozenset({"sre_health"}),
    tags=frozenset({"health", "container", "containerapp", "running", "status"}),
    affordance=ToolAffordance.READ,
    example_queries=(
        "check health of my container app prod-api",
        "is my container app running",
        "container app health status",
        "what is the health of my container apps",
    ),
    conflicts_with=frozenset({"resourcehealth"}),
    conflict_note=(
        "check_container_app_health provides Container App-specific health data "
        "(replicas, ingress, provisioning). "
        "resourcehealth only provides generic Azure platform availability."
    ),
    preferred_over=frozenset({"resourcehealth"}),
)
```

**Poor manifest (would fail linter):**

```python
ToolManifest(
    tool_name="check_container_app_health",
    source="sre",
    domains=frozenset({"sre_health"}),
    tags=frozenset({"health"}),              # Only 1 tag
    affordance=ToolAffordance.READ,
    example_queries=(                        # Only 1 query, too short
        "health check",
    ),
    conflicts_with=frozenset({"resourcehealth"}),
    conflict_note="",                        # Missing! conflicts_with is set
    preferred_over=frozenset(),
)
```

### Example 2: Destructive Operation

**Excellent manifest:**

```python
ToolManifest(
    tool_name="execute_safe_restart",
    source="sre",
    domains=frozenset({"sre_remediation"}),
    tags=frozenset({"remediation", "restart", "reboot", "recovery"}),
    affordance=ToolAffordance.DESTRUCTIVE,
    example_queries=(
        "restart my container app",
        "reboot the failing VM",
        "safe restart for the API service",
        "restart production container app",
    ),
    conflicts_with=frozenset({"scale_resource"}),
    conflict_note=(
        "execute_safe_restart performs a graceful restart with pre/post health checks. "
        "For scaling operations (add replicas, resize), use scale_resource instead."
    ),
    preferred_over=frozenset(),
    requires_confirmation=True,  # Required for DESTRUCTIVE
)
```

---

## Documenting Tool Conflicts

Tool conflicts are the most common source of misselection. Follow this process:

### 1. Identify Conflicts

Look for tools that could be confused because they:
- Have similar names (e.g. `storage` vs `storage_account_list`)
- Operate on similar resources (e.g. `monitor` vs `get_service_monitor_resources`)
- Have overlapping functionality (e.g. `nsg_list` vs `inspect_nsg_rules`)

### 2. Document Both Sides

When tools A and B conflict, update **both** manifests:

```python
# Tool A
conflicts_with=frozenset({"tool_b"})
conflict_note="tool_a does X. Use tool_b when you need Y."

# Tool B
conflicts_with=frozenset({"tool_a"})
conflict_note="tool_b does Y. Use tool_a when you need X."
```

### 3. Set Priority Where Appropriate

If one tool should be preferred for the overlapping use case:

```python
# The preferred tool
preferred_over=frozenset({"tool_b"})

# The secondary tool (no preferred_over needed)
preferred_over=frozenset()
```

### 4. Test the Conflict Resolution

Create a golden scenario that includes both conflicting tools and verifies
the correct one is selected:

```yaml
# tests/fixtures/golden/health_check_disambiguation.yaml
expected:
  tools:
    required: ["check_resource_health"]
    forbidden: ["resourcehealth", "speech"]
```

---

## Quality Checklist

Before submitting a new or updated manifest, verify:

- [ ] `tool_name` matches MCP server registration (snake_case)
- [ ] `source` is set to the correct MCP server label
- [ ] `domains` has at least 1 domain from the vocabulary
- [ ] `tags` has at least 3 diverse, user-facing keywords
- [ ] `example_queries` has at least 3 diverse natural language queries
- [ ] Each example query is 3+ words
- [ ] No duplicate example queries
- [ ] `conflicts_with` references only tools that exist in the index
- [ ] `conflict_note` is set when `conflicts_with` is non-empty
- [ ] `conflict_note` names both tools and explains when to use each
- [ ] `requires_confirmation=True` for DESTRUCTIVE and DEPLOY tools
- [ ] Linter passes: `python scripts/manifest_linter.py`
- [ ] Quality score is 80+: `python scripts/manifest_quality_scorecard.py`

---

## Running the Linter

```bash
cd app/agentic/eol

# Quick check
python scripts/manifest_linter.py

# Strict mode (warnings = errors)
python scripts/manifest_linter.py --strict

# JSON output for tooling
python scripts/manifest_linter.py --json

# Quality scorecard
python scripts/manifest_quality_scorecard.py

# Show only top 10 tools needing work
python scripts/manifest_quality_scorecard.py --top-gaps 10

# Fail if below quality threshold
python scripts/manifest_quality_scorecard.py --min-score 80
```

### Linter Rules Reference

| Rule | Severity | What It Checks |
|------|----------|---------------|
| TOOL-001 | Critical | tool_name is non-empty and valid characters |
| TOOL-002 | Warning | tool_name should be lowercase |
| SRC-001 | Critical | source field is non-empty |
| DOM-001 | Error | domains has at least 1 entry |
| TAG-001 | Error | tags has at least 2 entries |
| EX-001 | Error | example_queries has at least 2 entries |
| EX-002 | Warning | No duplicate example queries |
| EX-003 | Warning | Example queries should be 3+ words |
| CONF-001 | Warning | conflicts_with references existing tools |
| CONF-002 | Error | conflict_note required when conflicts_with is set |
| PREF-001 | Warning | preferred_over references existing tools |
| AFF-001 | Error | DESTRUCTIVE/DEPLOY tools need confirmation |

---

**Version:** 1.0 (Created 2026-03-03)
**Audience:** Developers adding or updating MCP tool manifests
