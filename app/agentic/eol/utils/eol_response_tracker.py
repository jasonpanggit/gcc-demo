"""EOL agent response tracking helpers extracted from EOLOrchestratorAgent.

Tracks EOL query results in-memory and optionally persists them to a database
repository (if `eol_repo` is injected).
"""
import json
import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

MAX_EOL_RESPONSES_TRACKED = 50  # Maximum EOL responses to track in memory


async def track_eol_agent_response(
    *,
    responses_list: List[Dict[str, Any]],
    session_id: str,
    eol_repo: Any,
    agent_name: str,
    software_name: str,
    software_version: Optional[str],
    eol_result: Dict[str, Any],
    response_time: float,
    query_type: str,
) -> None:
    """Track and optionally persist an EOL agent response."""
    try:
        data_field = eol_result.get("data", {}) if isinstance(eol_result, dict) else {}
        if not isinstance(data_field, dict):
            data_field = {}

        response_entry = {
            "timestamp": datetime.now().isoformat(),
            "agent_name": agent_name,
            "software_name": software_name,
            "software_version": software_version or "Not specified",
            "query_type": query_type,
            "response_time": response_time,
            "success": eol_result.get("success", False),
            "eol_data": data_field,
            "error": eol_result.get("error", {}),
            "confidence": data_field.get("confidence", 0),
            "source_url": data_field.get("source_url", ""),
            "agent_used": data_field.get("agent_used", agent_name),
            "session_id": session_id,
            "orchestrator_type": "eol_orchestrator",
            "cache_source": eol_result.get("cache_source"),
            "cached": bool(eol_result.get("cached")),
            "cache_created_at": eol_result.get("cache_created_at"),
            "cache_expires_at": eol_result.get("expires_at"),
            "search_internet_only": eol_result.get("search_internet_only", False),
            "search_mode": eol_result.get("search_mode"),
        }

        responses_list.append(response_entry)
        if len(responses_list) > MAX_EOL_RESPONSES_TRACKED:
            del responses_list[: len(responses_list) - MAX_EOL_RESPONSES_TRACKED]

        logger.info(
            "📊 [EOL Orchestrator] Tracked EOL response: %s -> %s (%s) - Success: %s - Total tracked: %d",
            agent_name, software_name, software_version, response_entry["success"], len(responses_list),
        )

        await persist_agent_response(eol_repo=eol_repo, response_entry=response_entry)

    except Exception as exc:
        logger.error("❌ Error tracking EOL agent response: %s", exc)


async def persist_agent_response(
    *,
    eol_repo: Any,
    response_entry: Dict[str, Any],
) -> None:
    """Persist an EOL agent response to database if eol_repo is available."""
    try:
        if eol_repo is None:
            logger.debug("🔍 [EOL Orchestrator] eol_repo not injected - skipping persistence")
            return

        response_id = str(uuid.uuid4())
        user_query = f"{response_entry['software_name']} {response_entry['software_version']}"
        agent_response_json = json.dumps(response_entry)

        sources = {
            "agent_used": response_entry.get("agent_used"),
            "source_url": response_entry.get("source_url"),
            "cache_source": response_entry.get("cache_source"),
            "orchestrator_type": response_entry.get("orchestrator_type"),
        }
        response_time_ms = int(response_entry.get("response_time", 0) * 1000)

        await eol_repo.save_agent_response(
            response_id=response_id,
            session_id=response_entry["session_id"],
            user_query=user_query,
            agent_response=agent_response_json,
            sources=sources,
            response_time_ms=response_time_ms,
        )

        logger.debug(
            "💾 [EOL Orchestrator] Persisted agent response: %s", response_entry["software_name"]
        )

    except Exception as exc:
        logger.warning("⚠️ Failed to persist agent response to database: %s", exc)
