# Manifest Authoring Guide

How to write high-quality MCP tool manifests that enable accurate tool selection.

---

## Table of Contents

1. [Why Manifest Quality Matters](#why-manifest-quality-matters)
2. [Manifest Structure](#manifest-structure)
3. [Field-by-Field Guidance](#field-by-field-guidance)
4. [Phase 3 Fields (New)](#phase-3-fields-new)
5. [Template for Excellent Manifests](#template-for-excellent-manifests)
6. [Good vs Bad Examples](#good-vs-bad-examples)
7. [Documenting Tool Conflicts](#documenting-tool-conflicts)
8. [Quality Checklist](#quality-checklist)
9. [Running the Linter](#running-the-linter)

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
    # ── Core fields (required) ────────────────────────────────────────────
    tool_name: str                          # Unique identifier
    source: str                             # MCP server origin
    domains: FrozenSet[str]                 # Domain classification
    tags: FrozenSet[str]                    # Semantic retrieval tags
    affordance: ToolAffordance              # READ | WRITE | DESTRUCTIVE | DEPLOY
    example_queries: Tuple[str, ...]        # Natural language triggers
    conflicts_with: FrozenSet[str]          # Confusable tool names
    conflict_note: str                      # Disambiguation guidance
    preferred_over: FrozenSet[str]          # Priority over other tools (core set)
    requires_confirmation: bool = False     # Gate for mutating tools
    deprecated: bool = False                # Sunset flag
    output_schema: Dict = field(default_factory=dict)

    # ── Phase 3: Intelligent Routing fields (optional, default to safe values) ──
    primary_phrasings: Tuple[str, ...] = ()       # Positive routing examples
    avoid_phrasings: Tuple[str, ...] = ()         # Negative routing examples
    confidence_boost: float = 1.0                 # Retrieval score multiplier
    requires_sequence: Optional[Tuple[str, ...]] = None  # Prerequisite tool chain
    preferred_over_list: Tuple[str, ...] = ()     # Extended preference list (convenience)
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

**Purpose:** Core set of tool names that this tool should be ranked higher than
when both are candidates for the same query.

```python
# container_app_list is preferred over azure_cli_execute_command for listing
preferred_over=frozenset({"azure_cli_execute_command"})
```

---

## Phase 3 Fields (New)

Phase 3 adds five new optional fields to support **metadata-driven routing** —
shifting routing logic from hard-coded patterns in `router.py` into manifest
metadata where it can be maintained without code changes.

All Phase 3 fields have safe defaults so existing manifests continue to work
without modification.

### `primary_phrasings` *(Tuple[str, ...], default: ())*

**Purpose:** Positive example queries specifically used to **boost retrieval
confidence** when the user's query closely matches one of these phrases.

Differs from `example_queries`:
- `example_queries` — used for semantic embedding similarity
- `primary_phrasings` — used for direct scoring boost during retrieval

**Rules:**
- Aim for 5–10 diverse, natural-language phrasings
- Cover the most common intents users express for this tool
- Each phrase must be ≥5 characters
- Use tuples (not lists) since the dataclass is frozen

```python
primary_phrasings=(
    "list my container apps",
    "show all container apps",
    "what container apps do I have",
    "display container apps in subscription",
    "get all container apps in resource group",
),
```

**When to populate:** Add for high-traffic tools that need reliable routing.
Leave empty `()` for rarely-used or highly-specific tools.

### `avoid_phrasings` *(Tuple[str, ...], default: ())*

**Purpose:** Negative examples — queries that SHOULD NOT trigger this tool.

Used to suppress false-positive matches where superficially similar queries
actually belong to a different, more specific tool.

**Rules:**
- Include queries where users have been routed to this tool incorrectly
- Add a comment indicating the correct tool for each phrase
- Each phrase must be ≥5 characters
- Use tuples (not lists)

```python
avoid_phrasings=(
    "check health of container apps",  # → check_container_app_health
    "restart container app",           # → execute_safe_restart
    "deploy container app",            # → deploy_container_app
),
```

**When to populate:** Add when observing false-positive routing incidents or
when a tool has an obvious "nearest alternative" for common query patterns.

### `confidence_boost` *(float, default: 1.0)*

**Purpose:** A score multiplier applied to this tool's retrieval score.
Expresses tool preference without hard-coding keyword rules.

**Valid range:** 1.0–2.0

| Value | When to use |
|-------|-------------|
| `1.0` | Default — no preference (leave unset or set explicitly) |
| `1.1` | Mild preference — slightly more specialised than an alternative |
| `1.2` | Moderate preference — clearly the right tool for its domain |
| `1.3` | Strong preference — a specialised SRE/network tool vs a generic one |
| `1.5` | Very strong — critical tool that should almost always win |

```python
# container_app_list is the go-to tool for listing; boost it
confidence_boost=1.2,

# check_container_app_health is the preferred health check — boost further
confidence_boost=1.3,
```

**Anti-pattern:** Do not set `confidence_boost > 1.5`. Extreme values indicate
the routing conflict should instead be resolved via `conflicts_with` / `conflict_note`.

### `requires_sequence` *(Optional[Tuple[str, ...]], default: None)*

**Purpose:** Encodes deterministic tool chaining in metadata instead of router code.
When the router plans to include this tool, it injects the prerequisite tools
earlier in the plan if they aren't already present.

**Rules:**
- `None` = no prerequisites (default — leave unset for most tools)
- Non-empty tuple = ordered list of tool names that must run first
- Do not use an empty tuple `()` — use `None` instead
- All prerequisite tool names should exist in the manifest index

**The canonical use case** is container app health chaining:

```python
# check_container_app_health requires the list step to provide resource IDs
requires_sequence=("container_app_list",),
```

This replaces the hard-coded pattern that previously lived in `router.py`:
```python
# OLD (hard-coded, fragile):
if "container" in query and "health" in query:
    inject_tools(["container_app_list", "check_container_app_health"])

# NEW (metadata-driven, maintainable):
# Set requires_sequence=("container_app_list",) on check_container_app_health manifest
```

### `preferred_over_list` *(Tuple[str, ...], default: ())*

**Purpose:** Extended set of lower-priority tool names that this tool should
be ranked above during retrieval.

Complements the core `preferred_over` FrozenSet field.  Use `preferred_over_list`
when you need to declare additional dynamic preferences beyond the static conflict-
resolution set in `preferred_over`, or when authoring manifests that should
compose cleanly with the other Phase 3 tuple fields.

**Rules:**
- `()` (empty tuple) = no additional preference (default)
- Each entry must be a non-empty string matching an existing tool name
- The router merges `preferred_over` and `preferred_over_list` during ranking
- Use tuples (not lists) since the dataclass is frozen

```python
# container_app_list is also preferred over these generic alternatives
preferred_over_list=(
    "azure_cli_execute_command",
    "generic_resource_query",
),
```

**When to populate:** Prefer `preferred_over` (FrozenSet) for compile-time-known
static conflicts.  Use `preferred_over_list` for dynamically discovered conflicts
or when co-authoring a set of Phase 3 fields that belong together semantically.

---

## Template for Excellent Manifests

Copy this template when adding a new tool (all Phase 3 fields included):

```python
ToolManifest(
    # ── Core fields ──
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

    # ── Phase 3: Intelligent Routing (optional — add for high-traffic tools) ──
    primary_phrasings=(
        "<common natural query 1>",
        "<common natural query 2>",
        "<common natural query 3>",
        "<common natural query 4>",
        "<common natural query 5>",
    ),
    avoid_phrasings=(
        "<query that belongs to another tool>",  # → <other_tool_name>
    ),
    confidence_boost=1.0,          # 1.0 = default; 1.1–1.5 for preferred tools
    requires_sequence=None,        # or ("prerequisite_tool",) for chained tools
    preferred_over_list=(),        # additional tools to rank above (tuple)
),
```

---

## Good vs Bad Examples

### Example 1: Health Check Tool

**Excellent manifest (with Phase 3):**

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

    # Phase 3
    primary_phrasings=(
        "what is the health of my container apps",
        "check container app health",
        "is my container app healthy",
        "container app status check",
        "show container app health",
    ),
    avoid_phrasings=(
        "list my container apps",       # → container_app_list
        "restart container app",        # → execute_safe_restart
    ),
    confidence_boost=1.3,
    requires_sequence=("container_app_list",),
    preferred_over_list=(),
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

    # Phase 3
    primary_phrasings=(
        "restart my container app",
        "reboot the service",
        "safe restart for production",
        "restart the failing app",
    ),
    avoid_phrasings=(
        "scale up container app",    # → scale_resource
        "add more replicas",         # → scale_resource
    ),
    confidence_boost=1.1,
    requires_sequence=None,
    preferred_over_list=(),
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

**Core fields:**
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

**Phase 3 fields (for high-traffic tools):**
- [ ] `primary_phrasings` has 5+ phrases if this is a top-20 tool
- [ ] `avoid_phrasings` documents the nearest "wrong tool" alternatives
- [ ] `confidence_boost` is in range [1.0, 2.0]
- [ ] `requires_sequence` is set for tools with mandatory prerequisites
- [ ] `requires_sequence=None` (not empty tuple) when there are no prerequisites
- [ ] `preferred_over_list` is a tuple of strings (empty tuple `()` is fine)

**Validation:**
- [ ] Linter passes: `python scripts/manifest_linter.py`
- [ ] Quality score is 80+: `python scripts/manifest_quality_scorecard.py`
- [ ] Phase 3 tests pass: `pytest tests/tools/test_manifest_quality.py -v -k phase3`
- [ ] Migration audit passes: `python utils/migrate_manifests.py`

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

# Phase 3 field validation only
pytest tests/tools/test_manifest_quality.py -v -k phase3

# Migration audit (Phase 3 field adoption report)
python utils/migrate_manifests.py
python utils/migrate_manifests.py --verbose     # per-tool details
python utils/migrate_manifests.py --strict      # CI gate: fail if schema missing
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
| P3-001 | Advisory | primary_phrasings strings are ≥5 chars |
| P3-002 | Advisory | avoid_phrasings strings are ≥5 chars |
| P3-003 | Error | confidence_boost in range [1.0, 2.0] |
| P3-004 | Error | requires_sequence is None or non-empty tuple of strings |
| P3-005 | Advisory | requires_sequence references known tool names |
| P3-006 | Error | preferred_over_list is a tuple of non-empty strings |

---

**Version:** 3.0 (Updated 2026-03-03)
**Changes:** Added `preferred_over_list` Phase 3 field; added migration audit script docs; removed duplicate content
**Audience:** Developers adding or updating MCP tool manifests
