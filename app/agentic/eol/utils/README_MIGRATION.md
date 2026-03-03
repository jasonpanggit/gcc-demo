# Phase 3 Manifest Migration Tool

**Canonical script:** `migrate_manifests.py`

## Purpose

Audits all tool manifests for Phase 3 intelligent routing metadata coverage. This consolidated tool combines the best features from the original `migrate_manifests.py` and `migrate_manifests_phase3.py`.

## Phase 3 Fields

All fields have safe defaults, making existing manifests backward compatible:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `primary_phrasings` | `Tuple[str, ...]` | `()` | Positive routing examples (5-10 recommended) |
| `avoid_phrasings` | `Tuple[str, ...]` | `()` | Negative routing examples (2-5 recommended) |
| `confidence_boost` | `float` | `1.0` | Retrieval score multiplier (1.0-2.0 range) |
| `requires_sequence` | `Optional[Tuple[str, ...]]` | `None` | Prerequisite tool chain |
| `preferred_over_list` | `Tuple[str, ...]` | `()` | Extended preference list |

## Usage

### Basic Audit

```bash
# From repository root
python -m app.agentic.eol.utils.migrate_manifests

# From app/agentic/eol directory
python utils/migrate_manifests.py
```

**Output:** Human-readable report with field adoption statistics and source-level breakdown.

### Verbose Mode

```bash
python -m app.agentic.eol.utils.migrate_manifests --verbose
```

**Output:** Includes per-tool details showing each field's status.

### JSON Output (CI Integration)

```bash
python -m app.agentic.eol.utils.migrate_manifests --json
```

**Output:** Structured JSON with summary, field adoption, source adoption, and per-tool details.

**Example:**
```json
{
  "summary": {
    "total_tools": 103,
    "tools_with_all_fields": 103,
    "tools_with_any_metadata": 103,
    "full_coverage_pct": 100.0
  },
  "field_adoption": {
    "primary_phrasings": {
      "count": 103,
      "percentage": 100.0
    }
  }
}
```

### Strict Mode (CI Gate)

```bash
python -m app.agentic.eol.utils.migrate_manifests --strict
```

**Behavior:** Exits with code 1 if any manifest is missing a Phase 3 field (has default values).

**Use case:** Pre-commit hook or CI pipeline to enforce complete metadata.

### Coverage Threshold

```bash
python -m app.agentic.eol.utils.migrate_manifests --min-coverage 90
```

**Behavior:** Exits with code 1 if full coverage percentage is below threshold (0-100).

**Use case:** Gradual migration enforcement (start at 50%, increase to 90%, then 100%).

## Exit Codes

| Code | Meaning |
|------|---------|
| `0` | All checks passed |
| `1` | Coverage below threshold or strict mode violations |
| `2` | Schema error (manifest cannot be loaded) |

## Current Status (Phase 3.1 Complete)

**100% Phase 3 Metadata Adoption Achieved:**

- `primary_phrasings`: 103/103 (100%)
- `avoid_phrasings`: 103/103 (100%)
- `confidence_boost`: 103/103 (100%)
- `requires_sequence`: 5/103 (5% - only tools needing prerequisite chains)
- `preferred_over_list`: 48/103 (47% - only tools with priority relationships)

All 103 tools have complete routing metadata!

## Migration History

### Phase 3.1 (2026-03-04)
- **Task #3:** Enhanced all 103 tools with Phase 3 metadata (100% adoption)
- **Task #4:** Consolidated migration scripts into single canonical tool
- **Deprecated:** `migrate_manifests_phase3.py` (archived as `.deprecated`)

### Phase 3 (2026-03-03)
- **Task #1:** Added Phase 3 schema fields to `ToolManifest`
- **Task #2:** Enhanced top-20 tools with initial metadata
- Created original `migrate_manifests.py` and `migrate_manifests_phase3.py`

## Files Enhanced

| Manifest File | Tools | Status |
|---------------|-------|--------|
| `azure_manifests.py` | 21 | ✅ Complete |
| `sre_manifests.py` | 51 | ✅ Complete |
| `network_manifests.py` | 18 | ✅ Complete |
| `monitor_manifests.py` | 5 | ✅ Complete |
| `inventory_manifests.py` | 2 | ✅ Complete |
| `cli_manifests.py` | 2 | ✅ Complete |
| `compute_manifests.py` | 1 | ✅ Complete |
| `storage_manifests.py` | 1 | ✅ Complete |
| `os_eol_manifests.py` | 2 | ✅ Complete |

## Metadata Quality Guidelines

### primary_phrasings (5-10 recommended)
- Diverse natural language variants
- Complete phrases, not single keywords
- Include domain-specific terminology
- Cover common user intents (list, check, show, diagnose, etc.)

**Example:**
```python
primary_phrasings=(
    "list my container apps",
    "show all container apps",
    "what container apps do I have",
    "container app inventory",
)
```

### avoid_phrasings (2-5 recommended)
- Negative examples for disambiguation
- Similar queries that should route elsewhere
- Include target tool in comments

**Example:**
```python
avoid_phrasings=(
    "container app health",  # → check_container_app_health
    "restart container app",  # → execute_safe_restart
)
```

### confidence_boost (1.0-2.0 range)
- `1.0`: Default (neutral)
- `1.05-1.15`: Slightly preferred
- `1.2-1.3`: Moderately specialized
- `1.4+`: Highly specialized/unique

### requires_sequence
- Only for tools that need prerequisite data
- Example: `check_container_app_health` requires `container_app_list` first

**Example:**
```python
requires_sequence=("container_app_list",)
```

### preferred_over_list
- Tools this should win against in priority conflicts
- Use for semantic preference (health > generic resource, specific > namespace)

**Example:**
```python
preferred_over_list=("check_resource_health", "resourcehealth")
```

## Testing

Run manifest quality tests to verify Phase 3 compliance:

```bash
cd app/agentic/eol
pytest tests/tools/test_manifest_quality.py::TestManifestPhase3Schema -v
```

All 11 Phase 3 schema tests should pass.

## CI Integration Example

```yaml
# .github/workflows/manifest-quality.yml
- name: Check Phase 3 Coverage
  run: |
    python -m app.agentic.eol.utils.migrate_manifests --json > coverage.json
    python -m app.agentic.eol.utils.migrate_manifests --min-coverage 100 --strict
```

## References

- **Phase 3 Handoff:** `.claude/docs/PHASE-3-HANDOFF.md`
- **Phase 3 Code Review:** `.claude/docs/PHASE-3-CODE-REVIEW.md`
- **Phase 3 Completion Report:** `.claude/docs/PHASE-3-COMPLETION-REPORT.md`
- **Manifest Authoring Guide:** `.claude/docs/MANIFEST-AUTHORING-GUIDE.md`

---

**Version:** 2.0 (Consolidated)
**Last Updated:** 2026-03-04
**Status:** Production Ready (100% Phase 3 adoption)
