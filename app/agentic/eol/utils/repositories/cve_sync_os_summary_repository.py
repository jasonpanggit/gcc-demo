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

        Returns:
            List of OS summaries with fields:
                - key, display_name, normalized_version
                - match_count (alias for cached_cve_count)
                - query_mode, synced_at
                - severity_counts (extracted from sync_metadata)
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
                        (sync_metadata->>'severity_counts')::jsonb,
                        '{}'::jsonb
                    ) AS severity_counts
                FROM cve_sync_os_summary
                ORDER BY cached_cve_count DESC, normalized_name, normalized_version
                """
            )
            return [dict(row) for row in rows]

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
