"""CVE Sync OS Summary Repository

Persists CVE sync metadata per OS identity for dashboard display.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List

import asyncpg

try:
    from utils.logging_config import get_logger
except ModuleNotFoundError:
    from app.agentic.eol.utils.logging_config import get_logger

logger = get_logger(__name__)


class CVESyncOSSummaryRepository:
    """Repository for CVE sync OS summary metadata."""

    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    async def upsert_os_entry(self, entry: Dict[str, Any]) -> None:
        """Upsert a single OS sync entry.

        Args:
            entry: OS sync entry with keys:
                - key: OS identity key
                - normalized_name: OS name
                - normalized_version: OS version
                - display_name: Human-readable name
                - query_mode: "cpe" or "keyword"
                - match_count: Number of CVEs cached
                - synced_at: ISO timestamp
                - (other metadata fields)
        """
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO cve_sync_os_summary (
                    os_key, normalized_name, normalized_version, display_name,
                    query_mode, cached_cve_count, synced_at, sync_metadata, updated_at
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, NOW())
                ON CONFLICT (os_key) DO UPDATE SET
                    normalized_name = EXCLUDED.normalized_name,
                    normalized_version = EXCLUDED.normalized_version,
                    display_name = EXCLUDED.display_name,
                    query_mode = EXCLUDED.query_mode,
                    cached_cve_count = EXCLUDED.cached_cve_count,
                    synced_at = EXCLUDED.synced_at,
                    sync_metadata = EXCLUDED.sync_metadata,
                    updated_at = NOW()
                """,
                entry.get("key"),
                entry.get("normalized_name"),
                entry.get("normalized_version"),
                entry.get("display_name"),
                entry.get("query_mode"),
                entry.get("match_count", 0),
                datetime.fromisoformat(entry.get("synced_at")) if entry.get("synced_at") else datetime.now(timezone.utc),
                json.dumps(entry),
            )

    async def upsert_batch(self, entries: List[Dict[str, Any]]) -> int:
        """Upsert multiple OS sync entries in a transaction.

        Args:
            entries: List of OS sync entries

        Returns:
            Number of entries processed
        """
        if not entries:
            return 0

        async with self.pool.acquire() as conn:
            async with conn.transaction():
                for entry in entries:
                    await conn.execute(
                        """
                        INSERT INTO cve_sync_os_summary (
                            os_key, normalized_name, normalized_version, display_name,
                            query_mode, cached_cve_count, synced_at, sync_metadata, updated_at
                        )
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, NOW())
                        ON CONFLICT (os_key) DO UPDATE SET
                            normalized_name = EXCLUDED.normalized_name,
                            normalized_version = EXCLUDED.normalized_version,
                            display_name = EXCLUDED.display_name,
                            query_mode = EXCLUDED.query_mode,
                            cached_cve_count = EXCLUDED.cached_cve_count,
                            synced_at = EXCLUDED.synced_at,
                            sync_metadata = EXCLUDED.sync_metadata,
                            updated_at = NOW()
                        """,
                        entry.get("key"),
                        entry.get("normalized_name"),
                        entry.get("normalized_version"),
                        entry.get("display_name"),
                        entry.get("query_mode"),
                        entry.get("match_count", 0),
                        datetime.fromisoformat(entry.get("synced_at")) if entry.get("synced_at") else datetime.now(timezone.utc),
                        json.dumps(entry),
                    )

        logger.info(f"Upserted {len(entries)} OS sync summary entries")
        return len(entries)

    async def get_all_summaries(self) -> List[Dict[str, Any]]:
        """Get all OS sync summaries ordered by CVE count.

        Severity counts are read from sync_metadata when available (populated
        after the fix in cve_inventory_sync.py).  For rows synced before the
        fix, the JSON field is absent and severity_counts falls back to {}.

        Returns:
            List of OS summaries with fields:
                - key, display_name, normalized_version
                - match_count (alias for cached_cve_count)
                - query_mode, synced_at
                - severity_counts (from sync_metadata, or {} for legacy rows)
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT
                    os_key AS key,
                    normalized_name,
                    normalized_version,
                    display_name,
                    cached_cve_count AS match_count,
                    query_mode,
                    synced_at,
                    updated_at,
                    COALESCE(
                        CASE
                            WHEN jsonb_typeof(sync_metadata) = 'object'
                            THEN (sync_metadata->'severity_counts')::jsonb
                            WHEN jsonb_typeof(sync_metadata) = 'string'
                            THEN ((sync_metadata#>>'{}')::jsonb->'severity_counts')::jsonb
                            ELSE NULL
                        END,
                        '{}'::jsonb
                    ) AS severity_counts
                FROM cve_sync_os_summary
                ORDER BY cached_cve_count DESC, normalized_name, normalized_version
                """
            )
            return [dict(row) for row in rows]

    @staticmethod
    def _extract_meta(raw_meta: Any) -> Dict[str, Any]:
        """Decode sync_metadata whether stored as JSONB object or double-encoded string."""
        if isinstance(raw_meta, str):
            try:
                return json.loads(raw_meta)
            except (json.JSONDecodeError, TypeError):
                return {}
        return raw_meta or {}

    @staticmethod
    def _cpe_filter_from_cpe_name(cpe_name: str) -> str:
        """Derive a prefix filter from a full CPE 2.3 string.

        E.g. ``cpe:2.3:o:microsoft:windows_server_2016:*:*:*:*:*:*:*:*``
        becomes ``cpe:2.3:o:microsoft:windows_server_2016``
        so that LIKE '%<filter>%' on cpe_uri matches all versions.
        """
        parts = cpe_name.split(":")
        # Keep component[0..6]: cpe, 2.3, type, vendor, product, version_prefix
        # Drop trailing wildcards (parts that are just "*")
        meaningful = parts[:6]
        while meaningful and meaningful[-1] in ("*", "-", ""):
            meaningful.pop()
        return ":".join(meaningful) if meaningful else cpe_name

    async def backfill_severity_counts(self) -> int:
        """Backfill severity_counts in sync_metadata for rows with missing or zero counts.

        For CPE-mode entries the counts are derived from the ``affected_products``
        JSONB column (same method used by the materialized view), so they match the
        CVEs that were actually fetched via the NVD CPE API.  Keyword-mode entries
        fall back to full-text search on ``search_vector``.

        Only rows whose severity_counts are all zero or absent are updated.

        Returns:
            Number of rows updated.
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT os_key, normalized_name, normalized_version, query_mode, sync_metadata
                FROM cve_sync_os_summary
                WHERE
                    cached_cve_count = 0
                    OR
                    -- No severity_counts at all (object or string storage)
                    CASE
                        WHEN jsonb_typeof(sync_metadata) = 'object'
                        THEN sync_metadata->'severity_counts' IS NULL
                        WHEN jsonb_typeof(sync_metadata) = 'string'
                        THEN (sync_metadata#>>'{}')::jsonb->'severity_counts' IS NULL
                        ELSE true
                    END
                    OR
                    -- severity_counts present but all zero (from bad previous backfill)
                    CASE
                        WHEN jsonb_typeof(sync_metadata) = 'object'
                        THEN (
                            COALESCE((sync_metadata->'severity_counts'->>'critical')::int, 0) = 0
                        AND COALESCE((sync_metadata->'severity_counts'->>'high')::int, 0) = 0
                        AND COALESCE((sync_metadata->'severity_counts'->>'medium')::int, 0) = 0
                        AND COALESCE((sync_metadata->'severity_counts'->>'low')::int, 0) = 0
                        )
                        WHEN jsonb_typeof(sync_metadata) = 'string'
                        THEN (
                            COALESCE(((sync_metadata#>>'{}')::jsonb->'severity_counts'->>'critical')::int, 0) = 0
                        AND COALESCE(((sync_metadata#>>'{}')::jsonb->'severity_counts'->>'high')::int, 0) = 0
                        AND COALESCE(((sync_metadata#>>'{}')::jsonb->'severity_counts'->>'medium')::int, 0) = 0
                        AND COALESCE(((sync_metadata#>>'{}')::jsonb->'severity_counts'->>'low')::int, 0) = 0
                        )
                        ELSE true
                    END
                """
            )
            if not rows:
                return 0

            updated = 0
            for row in rows:
                meta = self._extract_meta(row["sync_metadata"])
                query_mode = (row["query_mode"] or "").lower()

                # --- Determine the CPE name used during the original sync ---
                cpe_name: str | None = None
                live_queries = meta.get("live_queries") or []
                for lq in live_queries:
                    nvd_filters = lq.get("nvd_filters") or {}
                    if nvd_filters.get("cpeName"):
                        cpe_name = nvd_filters["cpeName"]
                        break

                if cpe_name:
                    # CPE mode: count via affected_products to match the NVD CPE API results
                    cpe_filter = self._cpe_filter_from_cpe_name(cpe_name)
                    counts = await conn.fetchrow(
                        """
                        SELECT
                            COUNT(*)                                                                      AS total,
                            COUNT(*) FILTER (WHERE COALESCE(cvss_v3_severity, 'UNKNOWN') = 'CRITICAL')   AS critical,
                            COUNT(*) FILTER (WHERE COALESCE(cvss_v3_severity, 'UNKNOWN') = 'HIGH')       AS high,
                            COUNT(*) FILTER (WHERE COALESCE(cvss_v3_severity, 'UNKNOWN') = 'MEDIUM')     AS medium,
                            COUNT(*) FILTER (WHERE COALESCE(cvss_v3_severity, 'UNKNOWN') = 'LOW')        AS low
                        FROM cves
                        WHERE EXISTS (
                            SELECT 1
                            FROM jsonb_array_elements(
                                CASE WHEN jsonb_typeof(affected_products) = 'array'
                                     THEN affected_products
                                     ELSE '[]'::jsonb
                                END
                            ) AS product
                            WHERE LOWER(COALESCE(product->>'cpe_uri', '')) LIKE '%' || LOWER($1) || '%'
                        )
                        """,
                        cpe_filter,
                    )
                else:
                    # Keyword mode: fall back to full-text search
                    norm_name = (row["normalized_name"] or "").lower().strip()
                    norm_ver = (row["normalized_version"] or "").strip().lower()
                    keyword = " ".join(filter(None, [norm_name, norm_ver]))
                    if not keyword:
                        continue
                    counts = await conn.fetchrow(
                        """
                        SELECT
                            COUNT(*)                                                                      AS total,
                            COUNT(*) FILTER (WHERE COALESCE(cvss_v3_severity, 'UNKNOWN') = 'CRITICAL')   AS critical,
                            COUNT(*) FILTER (WHERE COALESCE(cvss_v3_severity, 'UNKNOWN') = 'HIGH')       AS high,
                            COUNT(*) FILTER (WHERE COALESCE(cvss_v3_severity, 'UNKNOWN') = 'MEDIUM')     AS medium,
                            COUNT(*) FILTER (WHERE COALESCE(cvss_v3_severity, 'UNKNOWN') = 'LOW')        AS low
                        FROM cves
                        WHERE search_vector @@ plainto_tsquery('english', $1)
                        """,
                        keyword,
                    )
                total_count = counts["total"] or 0
                severity_counts = {
                    "critical": counts["critical"] or 0,
                    "high": counts["high"] or 0,
                    "medium": counts["medium"] or 0,
                    "low": counts["low"] or 0,
                }
                new_meta = {**meta, "severity_counts": severity_counts}
                # Use the live keyword count when it's non-zero (restores count zeroed
                # by a failed delta sync).  Fall back to the stored value if live
                # count returns nothing (avoids overwriting good data with 0).
                update_count = total_count if total_count > 0 else None
                if update_count is not None:
                    await conn.execute(
                        """
                        UPDATE cve_sync_os_summary
                        SET sync_metadata = $1::jsonb,
                            cached_cve_count = $3
                        WHERE os_key = $2
                        """,
                        json.dumps(new_meta),
                        row["os_key"],
                        update_count,
                    )
                else:
                    await conn.execute(
                        """
                        UPDATE cve_sync_os_summary
                        SET sync_metadata = $1::jsonb
                        WHERE os_key = $2
                        """,
                        json.dumps(new_meta),
                        row["os_key"],
                    )
                updated += 1
                logger.debug(
                    "Backfilled severity for %s: %s", row["os_key"], severity_counts
                )

            logger.info("Backfilled severity_counts for %d OS summary rows", updated)
            return updated

    async def delete_all(self) -> int:
        """Delete all OS sync summaries.

        Returns:
            Number of entries deleted
        """
        async with self.pool.acquire() as conn:
            result = await conn.execute("DELETE FROM cve_sync_os_summary")
            count = int(result.split()[-1]) if result and result.split() else 0
            logger.info(f"Deleted {count} OS sync summary entries")
            return count
