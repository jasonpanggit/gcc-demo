"""Phase 3 Manifest Migration and Audit Tool.

Consolidated migration utility combining the best features from both
migrate_manifests.py and migrate_manifests_phase3.py.

This script audits all tool manifests for Phase 3 metadata field coverage and
provides detailed reports on adoption statistics. It does NOT modify source files
— all metadata must be added manually to preserve semantic intent.

Phase 3 Fields:
    primary_phrasings:   Tuple[str, ...]   — Positive routing examples (5-10 recommended)
    avoid_phrasings:     Tuple[str, ...]   — Negative routing examples (2-5 recommended)
    confidence_boost:    float             — Retrieval score multiplier (1.0-2.0 range)
    requires_sequence:   Optional[Tuple]   — Prerequisite tool chain (None or tuple)
    preferred_over_list: Tuple[str, ...]   — Extended preference list

All fields have safe defaults, so existing manifests remain backward compatible.

Usage Examples:
    # Basic audit (from repo root)
    python -m app.agentic.eol.utils.migrate_manifests

    # Verbose mode (show all tools)
    python -m app.agentic.eol.utils.migrate_manifests --verbose

    # JSON output for CI integration
    python -m app.agentic.eol.utils.migrate_manifests --json

    # Strict mode (exit 1 if any field missing)
    python -m app.agentic.eol.utils.migrate_manifests --strict

    # Coverage threshold (exit 1 if below 90%)
    python -m app.agentic.eol.utils.migrate_manifests --min-coverage 90

Exit Codes:
    0 — All checks passed
    1 — Coverage below threshold or strict mode violations
    2 — Schema error (manifest cannot be loaded)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, field as dataclass_field
from typing import Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Path bootstrap — support running from eol/, app/, or repo root
# ---------------------------------------------------------------------------
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_EOL_DIR = os.path.dirname(_THIS_DIR)   # app/agentic/eol
_APP_DIR = os.path.dirname(os.path.dirname(_EOL_DIR))  # repo root

for _p in (_EOL_DIR, _APP_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# ---------------------------------------------------------------------------
# Import manifest index
# ---------------------------------------------------------------------------
try:
    from utils.tool_manifest_index import ToolManifest, get_tool_manifest_index  # type: ignore[import-not-found]
except ImportError:
    from app.agentic.eol.utils.tool_manifest_index import ToolManifest, get_tool_manifest_index  # type: ignore[import-not-found]


# ---------------------------------------------------------------------------
# Phase 3 field definitions
# ---------------------------------------------------------------------------

PHASE3_FIELDS: List[Tuple[str, object, str]] = [
    ("primary_phrasings",   (),   "Positive routing examples (tuple of NL phrases)"),
    ("avoid_phrasings",     (),   "Negative routing examples (tuple of NL phrases)"),
    ("confidence_boost",    1.0,  "Retrieval score multiplier (float 1.0–2.0)"),
    ("requires_sequence",   None, "Prerequisite tool chain (None or tuple of names)"),
    ("preferred_over_list", (),   "Extended preference list (tuple of tool names)"),
]


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class FieldStatus:
    """Status of a single Phase 3 field for a tool."""
    field_name: str
    present: bool
    has_value: bool  # True if non-default value
    current_value: object


@dataclass
class ToolMigrationStatus:
    """Phase 3 migration status for a single tool."""
    tool_name: str
    source: str
    fields: List[FieldStatus] = dataclass_field(default_factory=list)

    @property
    def all_fields_present(self) -> bool:
        """Return True if all Phase 3 fields exist (even if default values)."""
        return all(f.present for f in self.fields)

    @property
    def populated_fields(self) -> int:
        """Count of fields with non-default values."""
        return sum(1 for f in self.fields if f.has_value)

    @property
    def has_any_phase3_metadata(self) -> bool:
        """Return True if at least one Phase 3 field has a non-default value."""
        return self.populated_fields > 0


@dataclass
class MigrationReport:
    """Overall migration report statistics."""
    total_tools: int
    tools_with_all_fields: int
    tools_with_any_metadata: int
    field_adoption: Dict[str, int]
    source_adoption: Dict[str, Tuple[int, int]]  # source -> (enhanced, total)
    tool_statuses: List[ToolMigrationStatus]


# ---------------------------------------------------------------------------
# Core audit logic
# ---------------------------------------------------------------------------

def _has_value(field_name: str, value: object, neutral: object) -> bool:
    """Return True if value differs from neutral (default) value."""
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
            value = neutral
            has_val = False

        field_statuses.append(FieldStatus(
            field_name=field_name,
            present=present,
            has_value=has_val,
            current_value=value
        ))

    return ToolMigrationStatus(
        tool_name=manifest.tool_name,
        source=manifest.source,
        fields=field_statuses
    )


def audit_all_manifests() -> MigrationReport:
    """Audit all manifests in the catalog for Phase 3 field coverage."""
    try:
        index = get_tool_manifest_index()
        # Access internal manifests dictionary (no public get_all_manifests method)
        manifests = list(index._manifests.values())
    except Exception as e:
        print(f"ERROR: Failed to load manifest index: {e}", file=sys.stderr)
        sys.exit(2)

    tool_statuses: List[ToolMigrationStatus] = []
    field_adoption: Dict[str, int] = {field_name: 0 for field_name, _, _ in PHASE3_FIELDS}
    source_counts: Dict[str, List[int]] = {}  # source -> [enhanced, total]

    for manifest in manifests:
        status = audit_manifest(manifest)
        tool_statuses.append(status)

        # Track field adoption
        for field_status in status.fields:
            if field_status.has_value:
                field_adoption[field_status.field_name] += 1

        # Track source adoption
        source = status.source
        if source not in source_counts:
            source_counts[source] = [0, 0]
        source_counts[source][1] += 1  # total
        if status.has_any_phase3_metadata:
            source_counts[source][0] += 1  # enhanced

    total_tools = len(manifests)
    tools_with_all_fields = sum(1 for s in tool_statuses if s.all_fields_present)
    tools_with_any_metadata = sum(1 for s in tool_statuses if s.has_any_phase3_metadata)

    source_adoption = {
        src: (counts[0], counts[1])
        for src, counts in source_counts.items()
    }

    return MigrationReport(
        total_tools=total_tools,
        tools_with_all_fields=tools_with_all_fields,
        tools_with_any_metadata=tools_with_any_metadata,
        field_adoption=field_adoption,
        source_adoption=source_adoption,
        tool_statuses=tool_statuses
    )


# ---------------------------------------------------------------------------
# Output formatters
# ---------------------------------------------------------------------------

def print_human_readable_report(report: MigrationReport, verbose: bool = False) -> None:
    """Print human-readable migration report."""
    print("=" * 72)
    print("PHASE 3 MANIFEST MIGRATION REPORT")
    print("=" * 72)
    print(f"Manifests audited: {report.total_tools}")
    print()

    # Schema compatibility
    if report.tools_with_all_fields == report.total_tools:
        print(f"── Schema Compatibility: PASS (all {report.total_tools} tools) ──")
    else:
        missing = report.total_tools - report.tools_with_all_fields
        print(f"── Schema Compatibility: {missing} tools missing Phase 3 fields ──")
    print()

    # Field adoption statistics
    print("── Phase 3 Field Adoption ──")
    print(f"  {'Field':<24} {'Set /':<8} {'Total':<8} {'%':<6}  Description")
    print(f"  {'-'*24} {'-'*6}   {'-'*6}  {'-'*6}  {'-'*30}")

    for field_name, default, description in PHASE3_FIELDS:
        count = report.field_adoption[field_name]
        pct = (count / report.total_tools * 100) if report.total_tools > 0 else 0
        print(f"  {field_name:<24} {count:>3} / {report.total_tools:>6}  {pct:>5.0f}%  {description}")
    print()

    # Adoption by source
    print("── Adoption by Source ──")
    for source in sorted(report.source_adoption.keys()):
        enhanced, total = report.source_adoption[source]
        print(f"  {source:<20} {enhanced:>2} / {total:>3} tools have ≥1 Phase 3 field")
    print()

    # Verbose: show per-tool details
    if verbose:
        print("── Per-Tool Details ──")
        for status in sorted(report.tool_statuses, key=lambda s: s.tool_name):
            fields_set = status.populated_fields
            total_fields = len(PHASE3_FIELDS)
            print(f"  {status.tool_name:<40} [{status.source:<12}] {fields_set}/{total_fields} fields")

            for field_status in status.fields:
                marker = "✓" if field_status.has_value else "○"
                print(f"    {marker} {field_status.field_name:<20} = {field_status.current_value!r}")
        print()

    # Migration notes
    print("Migration notes:")
    print("  • All Phase 3 fields have safe defaults — no manifest changes required.")
    if report.tools_with_any_metadata < report.total_tools:
        missing = report.total_tools - report.tools_with_any_metadata
        print(f"  • {missing} tools still using default values (no metadata added yet).")
    print()


def print_json_report(report: MigrationReport) -> None:
    """Print JSON-formatted migration report for CI integration."""
    output = {
        "summary": {
            "total_tools": report.total_tools,
            "tools_with_all_fields": report.tools_with_all_fields,
            "tools_with_any_metadata": report.tools_with_any_metadata,
            "full_coverage_pct": round(report.tools_with_all_fields / report.total_tools * 100, 1)
                                 if report.total_tools > 0 else 0,
        },
        "field_adoption": {
            field_name: {
                "count": report.field_adoption[field_name],
                "percentage": round(report.field_adoption[field_name] / report.total_tools * 100, 1)
                             if report.total_tools > 0 else 0,
            }
            for field_name, _, _ in PHASE3_FIELDS
        },
        "source_adoption": {
            source: {
                "enhanced": enhanced,
                "total": total,
                "percentage": round(enhanced / total * 100, 1) if total > 0 else 0,
            }
            for source, (enhanced, total) in report.source_adoption.items()
        },
        "tools": [
            {
                "tool_name": status.tool_name,
                "source": status.source,
                "populated_fields": status.populated_fields,
                "fields": {
                    fs.field_name: {
                        "present": fs.present,
                        "has_value": fs.has_value,
                        "value": str(fs.current_value) if fs.has_value else None,
                    }
                    for fs in status.fields
                }
            }
            for status in report.tool_statuses
        ]
    }

    print(json.dumps(output, indent=2))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    """Main CLI entrypoint."""
    parser = argparse.ArgumentParser(
        description="Audit ToolManifest Phase 3 field compatibility for all loaded manifests.",
        epilog=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show per-tool Phase 3 adoption details."
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output JSON instead of human-readable text (for CI integration)."
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit with code 1 if any manifest is missing a Phase 3 field (CI gate)."
    )
    parser.add_argument(
        "--min-coverage",
        type=float,
        metavar="PCT",
        help="Exit with code 1 if full coverage percentage is below this threshold (0-100)."
    )

    args = parser.parse_args()

    # Run audit
    report = audit_all_manifests()

    # Output report
    if args.json:
        print_json_report(report)
    else:
        print_human_readable_report(report, verbose=args.verbose)

    # Check exit conditions
    exit_code = 0

    # Strict mode: fail if any field missing
    if args.strict and report.tools_with_all_fields < report.total_tools:
        missing = report.total_tools - report.tools_with_all_fields
        print(f"ERROR: Strict mode enabled — {missing} tools missing Phase 3 fields.", file=sys.stderr)
        exit_code = 1

    # Coverage threshold: fail if below minimum
    if args.min_coverage is not None:
        coverage_pct = (report.tools_with_all_fields / report.total_tools * 100) if report.total_tools > 0 else 0
        if coverage_pct < args.min_coverage:
            print(f"ERROR: Coverage {coverage_pct:.1f}% below minimum threshold {args.min_coverage:.1f}%.",
                  file=sys.stderr)
            exit_code = 1

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
