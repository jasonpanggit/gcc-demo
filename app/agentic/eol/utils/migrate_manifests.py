"""Migration utility for ToolManifest Phase 3 schema fields.

Validates that all manifests loaded from ``utils/manifests/*.py`` are compatible
with the Phase 3 schema additions.  Existing manifests without Phase 3 fields
continue to work unchanged (all new fields have safe defaults), but this script
verifies field presence and reports adoption statistics.

Usage:
    # From app/agentic/eol directory:
    python utils/migrate_manifests.py

    # Verbose output with per-tool details:
    python utils/migrate_manifests.py --verbose

    # Fail with non-zero exit if any Phase 3 field is missing (CI mode):
    python utils/migrate_manifests.py --strict

    # From repository root:
    python app/agentic/eol/utils/migrate_manifests.py

Phase 3 fields added to ToolManifest (all optional with safe defaults):
    primary_phrasings:  Tuple[str, ...]   default=()    — positive routing examples
    avoid_phrasings:    Tuple[str, ...]   default=()    — negative routing examples
    confidence_boost:   float             default=1.0   — retrieval score multiplier
    requires_sequence:  Optional[Tuple]   default=None  — prerequisite tool chain
    preferred_over_list: Tuple[str, ...]  default=()    — extended preference list

Migration status:
    Existing manifests are already backward compatible — no file changes needed.
    This script audits readiness and can be used as a CI gate or developer tool.
"""
from __future__ import annotations

import argparse
import sys
from typing import Dict, List, NamedTuple, Optional, Tuple

# Support running from both repo root and app/agentic/eol
try:
    from utils.tool_manifest_index import ToolManifest, get_tool_manifest_index  # type: ignore[import-not-found]
except ImportError:
    from app.agentic.eol.utils.tool_manifest_index import ToolManifest, get_tool_manifest_index  # type: ignore[import-not-found]

# ---------------------------------------------------------------------------
# Phase 3 field registry
# ---------------------------------------------------------------------------

PHASE3_FIELDS: List[Tuple[str, object, str]] = [
    # (field_name, neutral_value, description)
    ("primary_phrasings",  (),   "Positive routing examples (tuple of NL phrases)"),
    ("avoid_phrasings",    (),   "Negative routing examples (tuple of NL phrases)"),
    ("confidence_boost",   1.0,  "Retrieval score multiplier (float 1.0–2.0)"),
    ("requires_sequence",  None, "Prerequisite tool chain (None or tuple of names)"),
    ("preferred_over_list", (),  "Extended preference list (tuple of tool names)"),
]


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

class FieldStatus(NamedTuple):
    field_name: str
    present: bool
    has_value: bool   # True if non-default (meaningful content)
    current_value: object


class ToolMigrationStatus(NamedTuple):
    tool_name: str
    source: str
    fields: List[FieldStatus]

    @property
    def all_fields_present(self) -> bool:
        return all(f.present for f in self.fields)

    @property
    def populated_fields(self) -> int:
        return sum(1 for f in self.fields if f.has_value)


# ---------------------------------------------------------------------------
# Core migration audit logic
# ---------------------------------------------------------------------------

def _has_value(field_name: str, value: object, neutral: object) -> bool:
    """Return True if *value* differs from the neutral (default) value."""
    return value != neutral


def audit_manifest(manifest: ToolManifest) -> ToolMigrationStatus:
    """Inspect a single ToolManifest for Phase 3 field presence and content."""
    field_statuses: List[FieldStatus] = []
    for field_name, neutral, _desc in PHASE3_FIELDS:
        present = hasattr(manifest, field_name)
        if present:
            value = getattr(manifest, field_name)
            has_val = _has_value(field_name, value, neutral)
        else:
            value = None
            has_val = False
        field_statuses.append(FieldStatus(
            field_name=field_name,
            present=present,
            has_value=has_val,
            current_value=value,
        ))
    return ToolMigrationStatus(
        tool_name=manifest.tool_name,
        source=manifest.source,
        fields=field_statuses,
    )


def run_migration_audit(verbose: bool = False) -> Tuple[List[ToolMigrationStatus], Dict[str, int]]:
    """Audit all loaded manifests for Phase 3 field compatibility.

    Returns:
        (list of per-tool migration status, dict of field adoption counts)
    """
    index = get_tool_manifest_index()
    statuses: List[ToolMigrationStatus] = []

    for name in sorted(index.all_tool_names()):
        m = index.get(name)
        if m is not None:
            statuses.append(audit_manifest(m))

    # Adoption counts per field
    adoption: Dict[str, int] = {fname: 0 for fname, _, _ in PHASE3_FIELDS}
    for status in statuses:
        for fs in status.fields:
            if fs.has_value:
                adoption[fs.field_name] += 1

    return statuses, adoption


# ---------------------------------------------------------------------------
# Report helpers
# ---------------------------------------------------------------------------

def build_migration_report(
    statuses: List[ToolMigrationStatus],
    adoption: Dict[str, int],
    verbose: bool = False,
) -> str:
    """Build a human-readable migration audit report."""
    total = len(statuses)
    lines: List[str] = []

    lines.append("=" * 72)
    lines.append("PHASE 3 MANIFEST MIGRATION REPORT")
    lines.append("=" * 72)
    lines.append(f"Manifests audited: {total}")
    lines.append("")

    # Schema compatibility check
    incompatible = [s for s in statuses if not s.all_fields_present]
    if incompatible:
        lines.append(f"── Schema Compatibility: FAIL ({len(incompatible)} tools) ──")
        for s in incompatible:
            missing = [f.field_name for f in s.fields if not f.present]
            lines.append(f"  {s.tool_name} ({s.source}): missing {missing}")
        lines.append("")
    else:
        lines.append(f"── Schema Compatibility: PASS (all {total} tools) ──")
        lines.append("")

    # Phase 3 field adoption
    lines.append("── Phase 3 Field Adoption ──")
    lines.append(f"  {'Field':<24} {'Set':>6} / {'Total':>6}  {'%':>6}  Description")
    lines.append(f"  {'-'*24} {'-'*6}   {'-'*6}  {'-'*6}  {'-'*30}")
    for field_name, _neutral, desc in PHASE3_FIELDS:
        count = adoption.get(field_name, 0)
        pct = 100 * count / total if total else 0
        lines.append(f"  {field_name:<24} {count:>6} / {total:>6}  {pct:>5.0f}%  {desc}")
    lines.append("")

    # By source breakdown
    from collections import defaultdict
    by_source: Dict[str, List[ToolMigrationStatus]] = defaultdict(list)
    for s in statuses:
        by_source[s.source].append(s)

    lines.append("── Adoption by Source ──")
    for source in sorted(by_source):
        source_tools = by_source[source]
        populated_any = sum(1 for s in source_tools if s.populated_fields > 0)
        lines.append(
            f"  {source:<20}  {populated_any:>3} / {len(source_tools):>3} tools have ≥1 Phase 3 field"
        )
    lines.append("")

    # Verbose: per-tool detail for tools with Phase 3 data
    if verbose:
        populated = [s for s in statuses if s.populated_fields > 0]
        if populated:
            lines.append(f"── Tools with Phase 3 Metadata ({len(populated)}) ──")
            for s in populated:
                field_summary = ", ".join(
                    f.field_name for f in s.fields if f.has_value
                )
                lines.append(f"  {s.tool_name:<45s}  [{field_summary}]")
            lines.append("")

        not_populated = [s for s in statuses if s.populated_fields == 0]
        if not_populated:
            lines.append(f"── Tools without Phase 3 Metadata ({len(not_populated)}) — candidates for enhancement ──")
            for s in not_populated[:20]:
                lines.append(f"  {s.tool_name} ({s.source})")
            if len(not_populated) > 20:
                lines.append(f"  ... and {len(not_populated) - 20} more")
            lines.append("")

    lines.append("Migration notes:")
    lines.append("  • All Phase 3 fields have safe defaults — no manifest changes required.")
    lines.append("  • Manifests with empty Phase 3 fields are fully functional.")
    lines.append("  • Enrich Phase 3 metadata for top-traffic tools to improve routing accuracy.")
    lines.append("  • See .claude/docs/MANIFEST-AUTHORING-GUIDE.md for field guidance.")
    lines.append("=" * 72)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main(argv: Optional[List[str]] = None) -> int:
    """Run the migration audit and print the report.

    Returns 0 on success, 1 if --strict and schema incompatibilities found.
    """
    parser = argparse.ArgumentParser(
        description="Audit ToolManifest Phase 3 field compatibility for all loaded manifests.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show per-tool Phase 3 adoption details.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit with code 1 if any manifest is missing a Phase 3 field (CI gate).",
    )
    args = parser.parse_args(argv)

    statuses, adoption = run_migration_audit(verbose=args.verbose)
    report = build_migration_report(statuses, adoption, verbose=args.verbose)
    print(report)

    if args.strict:
        incompatible = [s for s in statuses if not s.all_fields_present]
        if incompatible:
            print(
                f"\n[STRICT] {len(incompatible)} manifest(s) missing Phase 3 fields. "
                "Exiting with code 1.",
                file=sys.stderr,
            )
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
