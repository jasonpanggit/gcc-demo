"""EOL Repository -- EOL Records, Agent Responses, and Extraction Rules.

Covers all EOL-domain queries from Phase 6 TARGET-SQL-INVENTORY-DOMAIN.md
(queries 12a, 13a, 14a, 15a-15b, 16a). Absorbs read paths previously served
by Cosmos-backed ``eol_inventory.py`` and ``os_extraction_rules.py``.

Also provides the write path for the ``eol_agent_responses`` table (Phase 7).
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional
from uuid import UUID

import asyncpg

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Sort whitelist -- BH-009 fix (server-side ORDER BY)
# Maps user-facing column names to actual DB column names.
# ---------------------------------------------------------------------------
ALLOWED_SORT_COLUMNS: Dict[str, str] = {
    "software_name": "software_name",
    "software_key": "software_key",
    "version": "version",
    "version_key": "version_key",
    "status": "status",
    "risk_level": "risk_level",
    "eol_date": "eol_date",
    "support_end_date": "support_end_date",
    "release_date": "release_date",
    "confidence": "confidence",
    "source": "source",
    "agent_used": "agent_used",
    "is_eol": "is_eol",
    "item_type": "item_type",
    "created_at": "created_at",
    "updated_at": "updated_at",
}

# ---------------------------------------------------------------------------
# SQL constants -- asyncpg $1/$2 parameterised syntax throughout
# ---------------------------------------------------------------------------

# From: TARGET-SQL-INVENTORY-DOMAIN.md Query 12a
QUERY_EOL_BY_KEY = """
SELECT id, software_key, software_name, version_key, version,
       eol_date, support_end_date, release_date, status, risk_level,
       confidence, source, source_url, agent_used,
       normalized_software_name, normalized_version,
       is_eol, item_type, created_at, updated_at
FROM eol_records
WHERE software_key = $1;
"""

# From: TARGET-SQL-INVENTORY-DOMAIN.md Query 13a (BH-009 fix)
# NOTE: ORDER BY column is dynamically set via ALLOWED_SORT_COLUMNS whitelist.
# The {sort_clause} is NOT user input -- it is validated against ALLOWED_SORT_COLUMNS.
QUERY_EOL_LIST_TEMPLATE = """
SELECT id, software_key, software_name, version_key, version,
       eol_date, support_end_date, release_date, status, risk_level,
       confidence, source, source_url, agent_used,
       raw_software_name, raw_version,
       normalized_software_name, normalized_version,
       derivation_strategy, derivation_rule_name,
       is_eol, item_type, created_at, updated_at
FROM eol_records
WHERE (item_type = 'os' OR item_type IS NULL)
  AND ($1::text IS NULL OR normalized_software_name ILIKE '%%' || $1 || '%%'
       OR software_name ILIKE '%%' || $1 || '%%')
ORDER BY {sort_clause}
LIMIT $2 OFFSET $3;
"""

QUERY_EOL_COUNT = """
SELECT COUNT(*) AS total
FROM eol_records
WHERE (item_type = 'os' OR item_type IS NULL)
  AND ($1::text IS NULL OR normalized_software_name ILIKE '%%' || $1 || '%%'
       OR software_name ILIKE '%%' || $1 || '%%');
"""

# From: TARGET-SQL-INVENTORY-DOMAIN.md Query 14a
QUERY_VM_EOL_MANAGEMENT = """
SELECT DISTINCT ON (v.resource_id)
       v.resource_id, v.vm_name, v.os_name, v.os_type, v.vm_type,
       v.resource_group, v.location,
       e.is_eol, e.eol_date, e.status AS eol_status, e.risk_level,
       e.version_key AS os_version
FROM vms v
LEFT JOIN eol_records e ON LOWER(v.os_name) = LOWER(e.software_key)
WHERE ($1::uuid IS NULL OR v.subscription_id = $1)
ORDER BY v.resource_id, e.eol_date ASC NULLS LAST
LIMIT $2 OFFSET $3;
"""

# From: TARGET-SQL-INVENTORY-DOMAIN.md Query 15a
QUERY_RECENT_RESPONSES = """
SELECT response_id, session_id, user_query, agent_response,
       sources, timestamp, response_time_ms
FROM eol_agent_responses
ORDER BY timestamp DESC
LIMIT $1 OFFSET $2;
"""

# From: TARGET-SQL-INVENTORY-DOMAIN.md Query 15b
QUERY_RESPONSES_BY_SESSION = """
SELECT response_id, session_id, user_query, agent_response,
       sources, timestamp, response_time_ms
FROM eol_agent_responses
WHERE session_id = $1
ORDER BY timestamp ASC;
"""

# From: TARGET-SQL-INVENTORY-DOMAIN.md Query 16a
QUERY_EXTRACTION_RULES = """
SELECT id, rule_type, pattern, replacement, priority, description, created_at
FROM os_extraction_rules
ORDER BY priority ASC, rule_type ASC;
"""

QUERY_UPSERT_EOL_RECORD = """
INSERT INTO eol_records (software_key, software_name, version_key, status, risk_level,
                         eol_date, extended_end_date, is_eol, last_verified,
                         item_type, lifecycle_url, normalized_software_name, updated_at)
VALUES ($1, $2, $3, $4, $5, $6, $7, $8, NOW(), $9, $10, LOWER($2), NOW())
ON CONFLICT (software_key) DO UPDATE SET
    software_name = EXCLUDED.software_name,
    version_key = EXCLUDED.version_key,
    status = EXCLUDED.status,
    risk_level = EXCLUDED.risk_level,
    eol_date = EXCLUDED.eol_date,
    extended_end_date = EXCLUDED.extended_end_date,
    is_eol = EXCLUDED.is_eol,
    last_verified = NOW(),
    item_type = EXCLUDED.item_type,
    lifecycle_url = EXCLUDED.lifecycle_url,
    normalized_software_name = LOWER(EXCLUDED.software_name),
    updated_at = NOW();
"""

QUERY_SAVE_AGENT_RESPONSE = """
INSERT INTO eol_agent_responses (response_id, session_id, user_query, agent_response,
                                  sources, timestamp, response_time_ms)
VALUES ($1, $2, $3, $4, $5::jsonb, NOW(), $6);
"""

# ---------------------------------------------------------------------------
# Allowed sort directions
# ---------------------------------------------------------------------------
_ALLOWED_DIRECTIONS = {"ASC", "DESC"}


class EOLRepository:
    """Repository covering all EOL-domain queries (Phase 6 queries 12a-16a)."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    # -- Query 12a: PK lookup --------------------------------------------------

    async def get_by_key(self, software_key: str) -> Optional[Dict[str, Any]]:
        """Return a single EOL record by its primary key, or ``None``."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(QUERY_EOL_BY_KEY, software_key)
        if row is None:
            return None
        return dict(row)

    # -- Query 13a: paginated list with server-side sort (BH-009 fix) ----------

    async def list_records(
        self,
        search: Optional[str] = None,
        sort_column: str = "updated_at",
        sort_direction: str = "DESC",
        limit: int = 25,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """Return EOL records with optional search and server-side sorting.

        * ``sort_column`` is validated against :data:`ALLOWED_SORT_COLUMNS`;
          defaults to ``"updated_at"`` if the value is not in the whitelist.
        * ``sort_direction`` must be ``"ASC"`` or ``"DESC"``; defaults to
          ``"DESC"`` if invalid.
        """
        # Validate sort_column against whitelist
        if sort_column not in ALLOWED_SORT_COLUMNS:
            sort_column = "updated_at"
        db_column = ALLOWED_SORT_COLUMNS[sort_column]

        # Validate sort_direction
        direction = sort_direction.upper()
        if direction not in _ALLOWED_DIRECTIONS:
            direction = "DESC"

        sort_clause = f"{db_column} {direction} NULLS LAST"
        query = QUERY_EOL_LIST_TEMPLATE.format(sort_clause=sort_clause)

        async with self._pool.acquire() as conn:
            rows = await conn.fetch(query, search, limit, offset)
        return [dict(r) for r in rows]

    async def count_records(self, search: Optional[str] = None) -> int:
        """Return total count of EOL records matching optional search filter."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(QUERY_EOL_COUNT, search)
        return int(row["total"]) if row else 0

    # -- Query 14a: VMs with EOL status ----------------------------------------

    async def get_vm_eol_management(
        self,
        subscription_id: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """Return VMs joined with their EOL status."""
        sub_id: Optional[UUID] = None
        if subscription_id is not None:
            try:
                sub_id = UUID(subscription_id)
            except ValueError:
                logger.warning(
                    "Invalid subscription_id %r; treating as NULL filter",
                    subscription_id,
                )

        async with self._pool.acquire() as conn:
            rows = await conn.fetch(QUERY_VM_EOL_MANAGEMENT, sub_id, limit, offset)
        return [dict(r) for r in rows]

    # -- Query 15a: recent agent responses -------------------------------------

    async def list_recent_responses(
        self,
        limit: int = 10,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """Return the most recent EOL agent responses.

        Parses the agent_response JSON field to return structured data
        that matches the frontend's expected format.
        """
        import json
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(QUERY_RECENT_RESPONSES, limit, offset)

        results = []
        for row in rows:
            try:
                # Try to parse agent_response as JSON
                agent_response_str = row['agent_response']
                if agent_response_str:
                    parsed = json.loads(agent_response_str)
                    # If it's already a dict with the expected fields, use it
                    if isinstance(parsed, dict) and 'software_name' in parsed:
                        results.append(parsed)
                    else:
                        # Fallback: convert row to dict
                        results.append(dict(row))
                else:
                    results.append(dict(row))
            except (json.JSONDecodeError, KeyError, TypeError):
                # If parsing fails, return the row as-is
                results.append(dict(row))

        return results

    # -- Query 15b: session-scoped responses -----------------------------------

    async def get_responses_by_session(self, session_id: str) -> List[Dict[str, Any]]:
        """Return all agent responses for a given session, ordered ASC."""
        try:
            sid = UUID(session_id)
        except ValueError:
            logger.warning("Invalid session_id %r; returning empty", session_id)
            return []

        async with self._pool.acquire() as conn:
            rows = await conn.fetch(QUERY_RESPONSES_BY_SESSION, sid)
        return [dict(r) for r in rows]

    # -- Query 16a: extraction rules -------------------------------------------

    async def list_extraction_rules(self) -> List[Dict[str, Any]]:
        """Return all OS extraction rules ordered by priority."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(QUERY_EXTRACTION_RULES)
        return [dict(r) for r in rows]

    # -- UPSERT EOL record -----------------------------------------------------

    async def upsert_eol_record(
        self,
        software_key: str,
        software_name: str,
        version_key: Optional[str] = None,
        status: Optional[str] = None,
        risk_level: Optional[str] = None,
        eol_date: Any = None,
        extended_end_date: Any = None,
        is_eol: bool = False,
        item_type: Optional[str] = None,
        lifecycle_url: Optional[str] = None,
    ) -> None:
        """Insert or update an EOL record.  Re-raises on error."""
        async with self._pool.acquire() as conn:
            await conn.execute(
                QUERY_UPSERT_EOL_RECORD,
                software_key,
                software_name,
                version_key,
                status,
                risk_level,
                eol_date,
                extended_end_date,
                is_eol,
                item_type,
                lifecycle_url,
            )

    # -- INSERT agent response -------------------------------------------------

    async def save_agent_response(
        self,
        response_id: str,
        session_id: str,
        user_query: str,
        agent_response: str,
        sources: Optional[dict] = None,
        response_time_ms: Optional[int] = None,
    ) -> None:
        """Persist a single EOL agent response into ``eol_agent_responses``."""
        rid = UUID(response_id)
        sid = UUID(session_id)
        sources_json = json.dumps(sources) if sources is not None else "[]"

        async with self._pool.acquire() as conn:
            await conn.execute(
                QUERY_SAVE_AGENT_RESPONSE,
                rid,
                sid,
                user_query,
                agent_response,
                sources_json,
                response_time_ms,
            )
