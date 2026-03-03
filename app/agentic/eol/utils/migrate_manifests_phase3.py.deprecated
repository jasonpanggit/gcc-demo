"""Phase 3 manifest migration script.

Scans all manifest modules loaded by ToolManifestIndex and reports which tools
are missing Phase 3 metadata fields.  When run without ``--dry-run``, it prints
a migration report but does NOT modify any source files — manifest source files
must be edited by hand (or a separate tool) to add rich phrasing data.

The script is intentionally **idempotent**: running it multiple times produces
the same output.  It will never write to or modify manifest source files.

Why no auto-patching of source files?
--------------------------------------
Phase 3 fields (``primary_phrasings``, ``avoid_phrasings``, ``confidence_boost``,
``requires_sequence``) carry *semantic intent* that cannot be inferred
automatically.  The defaults are already applied at the schema level (empty
tuples / 1.0 / None), so no manifest will break without them.  This script
exists to report coverage gaps and validate that all manifests accept the new
fields without errors.

Usage::

    # Check coverage (read-only, always safe)
    python utils/migrate_manifests_phase3.py

    # Verbose mode (show all tools, not just gaps)
    python utils/migrate_manifests_phase3.py --verbose

    # JSON output (for CI integration)
    python utils/migrate_manifests_phase3.py --json

    # Fail with non-zero exit if coverage below threshold
    python utils/migrate_manifests_phase3.py --min-coverage 50

    # Dry-run (explicitly reads schema, prints what a migration would look like)
    python utils/migrate_manifests_phase3.py --dry-run

Exit codes::

    0 — All checks passed (or below threshold was not specified)
    1 — Coverage below --min-coverage threshold
    2 — Schema error (a manifest cannot be loaded / has invalid Phase 3 values)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Path bootstrap — support running from eol/, app/, or repo root
# ---------------------------------------------------------------------------
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_EOL_DIR = os.path.dirname(_THIS_DIR)   # app/agentic/eol
_APP_DIR = os.path.dirname(os.path.dirname(_EOL_DIR))  # repo root (above app/)

for _p in (_EOL_DIR, _APP_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# ---------------------------------------------------------------------------
# Import the manifest index (supports both run-from-repo-root and run-from-eol)
# ---------------------------------------------------------------------------
try:
    from utils.tool_manifest_index import ToolManifest, ToolManifestIndex, get_tool_manifest_index  # type: ignore[import-not-found]
except ImportError:
    from app.agentic.eol.utils.tool_manifest_index import ToolManifest, ToolManifestIndex, get_tool_manifest_index  # type: ignore[import-not-found]


# ---------------------------------------------------------------------------
# Phase 3 field defaults (mirrors the dataclass defaults exactly)
# ---------------------------------------------------------------------------

_PHASE3_DEFAULTS: Dict[str, object] = {
    "primary_phrasings": (),
    "avoid_phrasings": (),
    "confidence_boost": 1.0,
    "requires_sequence": None,
}


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class ToolMigrationStatus:
    """Phase 3 migration status for a single tool manifest."""

    tool_name: str
    source: str

    # Per-field presence flags (True = field has non-default value)
    has_primary_phrasings: bool = False
    has_avoid_phrasings: bool = False
    has_confidence_boost: bool = False
    has_requires_sequence: bool = False

    # Validation errors (should be empty if schema is correct)
    errors: List[str] = field(default_factory=list)

    @property
    def is_fully_migrated(self) -> bool:
        """True when all four Phase 3 fields carry non-default values."""
        return all([
            self.has_primary_phrasings,
            self.has_avoid_phrasings,
            self.has_confidence_boost,
            self.has_requires_sequence,
        ])

    @property
    def phase3_fields_set(self) -> int:
        """Count of Phase 3 fields that have been populated (0–4)."""
        return sum([
            self.has_primary_phrasings,
            self.has_avoid_phrasings,
            self.has_confidence_boost,
            self.has_requires_sequence,
        ])

    def missing_fields(self) -> List[str]:
        """Return names of Phase 3 fields not yet populated."""
        missing = []
        if not self.has_primary_phrasings:
            missing.append("primary_phrasings")
        if not self.has_avoid_phrasings:
            missing.append("avoid_phrasings")
        if not self.has_confidence_boost:
            missing.append("confidence_boost")
        if not self.has_requires_sequence:
            missing.append("requires_sequence")
        return missing


@dataclass
class MigrationReport:
    """Aggregated Phase 3 migration coverage report."""

    total_tools: int
    fully_migrated: int
    partial_migrated: int
    not_migrated: int
    tools_with_errors: int
    statuses: List[ToolMigrationStatus] = field(default_factory=list)

    @property
    def coverage_pct(self) -> float:
        """Percentage of tools with at least one Phase 3 field populated."""
        if self.total_tools == 0:
            return 0.0
        return round(100.0 * (self.fully_migrated + self.partial_migrated) / self.total_tools, 1)

    @property
    def full_coverage_pct(self) -> float:
        """Percentage of tools that are fully migrated (all 4 fields populated)."""
        if self.total_tools == 0:
            return 0.0
        return round(100.0 * self.fully_migrated / self.total_tools, 1)


# ---------------------------------------------------------------------------
# Core analysis
# ---------------------------------------------------------------------------

def _validate_phase3_fields(manifest: ToolManifest) -> List[str]:
    """Validate Phase 3 field values on a manifest.  Returns list of error strings."""
    errors: List[str] = []

    # primary_phrasings: tuple of strings
    if not isinstance(manifest.primary_phrasings, tuple):
        errors.append(
            f"primary_phrasings must be tuple, got {type(manifest.primary_phrasings).__name__}"
        )
    else:
        for i, p in enumerate(manifest.primary_phrasings):
            if not isinstance(p, str) or len(p.strip()) < 5:
                errors.append(f"primary_phrasings[{i}]={p!r} must be a string of ≥5 chars")

    # avoid_phrasings: tuple of strings
    if not isinstance(manifest.avoid_phrasings, tuple):
        errors.append(
            f"avoid_phrasings must be tuple, got {type(manifest.avoid_phrasings).__name__}"
        )
    else:
        for i, p in enumerate(manifest.avoid_phrasings):
            if not isinstance(p, str) or len(p.strip()) < 5:
                errors.append(f"avoid_phrasings[{i}]={p!r} must be a string of ≥5 chars")

    # confidence_boost: float in [1.0, 2.0]
    if not isinstance(manifest.confidence_boost, (int, float)):
        errors.append(
            f"confidence_boost must be float, got {type(manifest.confidence_boost).__name__}"
        )
    elif not (1.0 <= manifest.confidence_boost <= 2.0):
        errors.append(
            f"confidence_boost={manifest.confidence_boost} is out of valid range [1.0, 2.0]"
        )

    # requires_sequence: None or non-empty tuple of strings
    if manifest.requires_sequence is not None:
        if not isinstance(manifest.requires_sequence, tuple):
            errors.append(
                f"requires_sequence must be None or tuple, got {type(manifest.requires_sequence).__name__}"
            )
        elif len(manifest.requires_sequence) == 0:
            errors.append("requires_sequence is empty tuple — use None for no prerequisites")
        else:
            for i, t in enumerate(manifest.requires_sequence):
                if not isinstance(t, str) or not t.strip():
                    errors.append(f"requires_sequence[{i}]={t!r} must be a non-empty string")

    return errors


def analyze_manifest(manifest: ToolManifest) -> ToolMigrationStatus:
    """Analyse a single manifest for Phase 3 field coverage."""
    status = ToolMigrationStatus(
        tool_name=manifest.tool_name,
        source=manifest.source,
    )

    # Check presence (non-default value = populated)
    status.has_primary_phrasings = bool(manifest.primary_phrasings)
    status.has_avoid_phrasings = bool(manifest.avoid_phrasings)
    status.has_confidence_boost = manifest.confidence_boost != 1.0
    status.has_requires_sequence = manifest.requires_sequence is not None

    # Validate values
    status.errors = _validate_phase3_fields(manifest)

    return status


def build_migration_report(index: Optional[ToolManifestIndex] = None) -> MigrationReport:
    """Build a full migration report from the manifest index.

    Args:
        index: Optional pre-loaded index.  If None, loads the singleton.

    Returns:
        MigrationReport with coverage stats and per-tool statuses.
    """
    if index is None:
        index = get_tool_manifest_index()

    statuses: List[ToolMigrationStatus] = []
    for name in sorted(index.all_tool_names()):
        m = index.get(name)
        if m is not None:
            statuses.append(analyze_manifest(m))

    fully_migrated = sum(1 for s in statuses if s.is_fully_migrated)
    partial_migrated = sum(1 for s in statuses if 0 < s.phase3_fields_set < 4)
    not_migrated = sum(1 for s in statuses if s.phase3_fields_set == 0)
    tools_with_errors = sum(1 for s in statuses if s.errors)

    return MigrationReport(
        total_tools=len(statuses),
        fully_migrated=fully_migrated,
        partial_migrated=partial_migrated,
        not_migrated=not_migrated,
        tools_with_errors=tools_with_errors,
        statuses=statuses,
    )


# ---------------------------------------------------------------------------
# Report rendering
# ---------------------------------------------------------------------------

def render_text_report(report: MigrationReport, verbose: bool = False) -> str:
    """Render the migration report as human-readable text."""
    lines: List[str] = []
    lines.append("=" * 72)
    lines.append("PHASE 3 MANIFEST MIGRATION REPORT")
    lines.append("=" * 72)
    lines.append(f"Total tools:         {report.total_tools}")
    lines.append(f"Fully migrated:      {report.fully_migrated}  ({report.full_coverage_pct:.1f}%)")
    lines.append(f"Partially migrated:  {report.partial_migrated}")
    lines.append(f"Not yet migrated:    {report.not_migrated}")
    lines.append(f"Tools with errors:   {report.tools_with_errors}")
    lines.append(f"Overall coverage:    {report.coverage_pct:.1f}%  (any Phase 3 field set)")
    lines.append("")

    # Validation errors first (these should be fixed immediately)
    errors_found = [s for s in report.statuses if s.errors]
    if errors_found:
        lines.append(f"── VALIDATION ERRORS ({len(errors_found)} tools) — FIX IMMEDIATELY ──")
        for s in errors_found:
            for err in s.errors:
                lines.append(f"  [{s.source}] {s.tool_name}: {err}")
        lines.append("")

    # Field-level coverage summary
    lines.append("── Field Coverage ──")
    field_names = ["primary_phrasings", "avoid_phrasings", "confidence_boost", "requires_sequence"]
    for fname in field_names:
        count = sum(1 for s in report.statuses if getattr(s, f"has_{fname}"))
        pct = 100.0 * count / report.total_tools if report.total_tools else 0
        lines.append(f"  {fname:25s}  {count:3d} / {report.total_tools}  ({pct:.0f}%)")
    lines.append("")

    # Per-source breakdown
    by_source: Dict[str, List[ToolMigrationStatus]] = {}
    for s in report.statuses:
        by_source.setdefault(s.source, []).append(s)

    lines.append("── Migration by Source ──")
    for source in sorted(by_source):
        tools = by_source[source]
        full = sum(1 for t in tools if t.is_fully_migrated)
        partial = sum(1 for t in tools if 0 < t.phase3_fields_set < 4)
        total = len(tools)
        lines.append(f"  {source:20s}  {full:2d} full  {partial:2d} partial  {total:3d} total")
    lines.append("")

    # Tools needing migration (sorted by priority: partial first, then not-migrated)
    need_migration = [s for s in report.statuses if not s.is_fully_migrated]
    if need_migration:
        lines.append(f"── Tools Needing Phase 3 Migration ({len(need_migration)}) ──")
        # Partial first (already started, finish them)
        partial = [s for s in need_migration if s.phase3_fields_set > 0]
        not_started = [s for s in need_migration if s.phase3_fields_set == 0]

        if partial:
            lines.append("  [Partial — finish these first]")
            for s in sorted(partial, key=lambda x: -x.phase3_fields_set):
                missing = ", ".join(s.missing_fields())
                lines.append(f"    [{s.source}] {s.tool_name}: missing={missing}")

        if not_started:
            lines.append(f"  [Not started — {len(not_started)} tools]")
            for s in sorted(not_started, key=lambda x: x.source):
                lines.append(f"    [{s.source}] {s.tool_name}")
        lines.append("")
    else:
        lines.append("✅ All tools have Phase 3 metadata!")
        lines.append("")

    # Verbose: fully migrated tools
    if verbose:
        fully_done = [s for s in report.statuses if s.is_fully_migrated]
        if fully_done:
            lines.append(f"── Fully Migrated Tools ({len(fully_done)}) ──")
            for s in fully_done:
                lines.append(f"  [{s.source}] {s.tool_name}")
            lines.append("")

    lines.append("=" * 72)
    lines.append("How to migrate a tool:")
    lines.append("  1. Open the relevant utils/manifests/<source>_manifests.py file")
    lines.append("  2. Add Phase 3 fields to the ToolManifest entry:")
    lines.append("       primary_phrasings=(\"query 1\", \"query 2\", ...),")
    lines.append("       avoid_phrasings=(\"bad query 1\", ...),")
    lines.append("       confidence_boost=1.2,  # or omit for default 1.0")
    lines.append("       requires_sequence=(\"prereq_tool\",),  # or None")
    lines.append("  3. Run this script again to confirm coverage improved")
    lines.append("  4. Run tests: pytest tests/tools/test_manifest_quality.py -k phase3")
    lines.append("=" * 72)

    return "\n".join(lines)


def render_json_report(report: MigrationReport) -> str:
    """Render the migration report as JSON for CI tooling."""
    output = {
        "total_tools": report.total_tools,
        "fully_migrated": report.fully_migrated,
        "partial_migrated": report.partial_migrated,
        "not_migrated": report.not_migrated,
        "tools_with_errors": report.tools_with_errors,
        "coverage_pct": report.coverage_pct,
        "full_coverage_pct": report.full_coverage_pct,
        "field_coverage": {},
        "tools": [],
    }

    # Field coverage
    field_names = ["primary_phrasings", "avoid_phrasings", "confidence_boost", "requires_sequence"]
    for fname in field_names:
        count = sum(1 for s in report.statuses if getattr(s, f"has_{fname}"))
        output["field_coverage"][fname] = {
            "count": count,
            "total": report.total_tools,
            "pct": round(100.0 * count / report.total_tools, 1) if report.total_tools else 0.0,
        }

    # Per-tool status
    for s in report.statuses:
        output["tools"].append({
            "tool_name": s.tool_name,
            "source": s.source,
            "phase3_fields_set": s.phase3_fields_set,
            "is_fully_migrated": s.is_fully_migrated,
            "has_primary_phrasings": s.has_primary_phrasings,
            "has_avoid_phrasings": s.has_avoid_phrasings,
            "has_confidence_boost": s.has_confidence_boost,
            "has_requires_sequence": s.has_requires_sequence,
            "errors": s.errors,
            "missing_fields": s.missing_fields(),
        })

    return json.dumps(output, indent=2)


# ---------------------------------------------------------------------------
# Dry-run helper
# ---------------------------------------------------------------------------

def render_dry_run_preview(report: MigrationReport) -> str:
    """Show what a migration would look like for unset fields."""
    lines: List[str] = []
    lines.append("=" * 72)
    lines.append("DRY RUN: Phase 3 migration preview")
    lines.append("(No files will be modified — manifest files must be updated manually)")
    lines.append("=" * 72)
    lines.append("")

    not_started = [s for s in report.statuses if s.phase3_fields_set == 0]
    partial = [s for s in report.statuses if 0 < s.phase3_fields_set < 4]

    all_needing_work = partial + not_started
    if not all_needing_work:
        lines.append("✅ All manifests already have Phase 3 fields populated.")
        return "\n".join(lines)

    lines.append(f"{len(all_needing_work)} tool(s) would receive default Phase 3 values:\n")
    lines.append("NOTE: The schema already applies these defaults at instantiation time.")
    lines.append("      This preview shows what EXPLICIT values would look like in source.\n")

    for s in all_needing_work[:20]:  # Limit preview to first 20
        lines.append(f"# [{s.source}] {s.tool_name}  (missing: {', '.join(s.missing_fields())})")
        if not s.has_primary_phrasings:
            lines.append("    primary_phrasings=(),  # TODO: add 5-10 natural language phrasings")
        if not s.has_avoid_phrasings:
            lines.append("    avoid_phrasings=(),    # TODO: add queries that should NOT match this tool")
        if not s.has_confidence_boost:
            lines.append("    confidence_boost=1.0,  # TODO: set to 1.1-1.5 for preferred tools")
        if not s.has_requires_sequence:
            lines.append("    requires_sequence=None,  # TODO: set to ('prereq_tool',) if applicable")
        lines.append("")

    if len(all_needing_work) > 20:
        lines.append(f"... and {len(all_needing_work) - 20} more tools (use --verbose to see all)")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> int:
    """Run the Phase 3 migration analysis and return an exit code."""
    parser = argparse.ArgumentParser(
        description="Analyse Phase 3 metadata coverage across all tool manifests.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Include fully-migrated tools in output",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output JSON instead of human-readable text",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what default values would be added to unmigrated manifests",
    )
    parser.add_argument(
        "--min-coverage",
        type=float,
        default=None,
        metavar="PCT",
        help="Exit with code 1 if full_coverage_pct is below this threshold (0-100)",
    )

    args = parser.parse_args()

    # Load manifests
    try:
        report = build_migration_report()
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: Failed to load manifest index: {exc}", file=sys.stderr)
        return 2

    # Validate — any schema errors trigger exit code 2
    if report.tools_with_errors > 0:
        errs = [s for s in report.statuses if s.errors]
        print(f"SCHEMA ERRORS in {len(errs)} manifest(s):", file=sys.stderr)
        for s in errs:
            for err in s.errors:
                print(f"  [{s.source}] {s.tool_name}: {err}", file=sys.stderr)
        return 2

    # Render
    if args.json:
        print(render_json_report(report))
    elif args.dry_run:
        print(render_text_report(report, verbose=args.verbose))
        print()
        print(render_dry_run_preview(report))
    else:
        print(render_text_report(report, verbose=args.verbose))

    # Coverage threshold check
    if args.min_coverage is not None:
        if report.full_coverage_pct < args.min_coverage:
            print(
                f"\nCoverage {report.full_coverage_pct:.1f}% is below "
                f"--min-coverage {args.min_coverage:.1f}%",
                file=sys.stderr,
            )
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
