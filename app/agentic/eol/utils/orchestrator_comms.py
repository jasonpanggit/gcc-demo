"""Communication formatting helpers for the EOL orchestrator.

Extracted from EOLOrchestratorAgent to keep the orchestrator file lean.
These functions format communication log entries for frontend display.
"""
import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


def format_communication_message(comm: Dict[str, Any]) -> str:
    """Format a communication log entry for display."""
    try:
        if comm is None or not isinstance(comm, dict):
            return "❓ Invalid communication data"

        agent = comm.get("agentName", "unknown") if comm else "unknown"
        action = comm.get("action", "unknown") if comm else "unknown"
        input_data = comm.get("input", {}) if comm else {}
        output_data = comm.get("output", {}) if comm else {}

        if action == "get_eol_data":
            software = input_data.get("software_name", "unknown") if input_data else "unknown"
            version = input_data.get("version", "") if input_data else ""
            if output_data and not output_data.get("error"):
                return f"🔍 {agent} found EOL data for {software}" + (f" {version}" if version else "")
            else:
                return f"❌ {agent} failed to find EOL data for {software}" + (f" {version}" if version else "")
        elif action == "get_autonomous_eol_data":
            software = input_data.get("software_name", "unknown") if input_data else "unknown"
            return f"🎯 Orchestrator routing EOL query for {software}"
        elif action == "agent_selection":
            software = input_data.get("software_name", "unknown") if input_data else "unknown"
            agents = output_data.get("selected_agents", []) if output_data else []
            return f"🔀 Routing {software} to agents: {', '.join(agents)}"
        else:
            return f"📋 {agent}: {action}"
    except Exception as e:
        logger.error("Error formatting communication message: %s", str(e))
        return f"❌ Error formatting message: {str(e)}"


def determine_message_type(comm: Dict[str, Any]) -> str:
    """Determine message type for styling."""
    try:
        if comm is None or not isinstance(comm, dict):
            return "error"

        output_data = comm.get("output", {}) if comm else {}

        if output_data and output_data.get("error"):
            return "error"
        elif output_data and output_data.get("success") is False:
            return "warning"
        elif comm.get("action") in ["get_eol_data", "get_autonomous_eol_data"] and output_data:
            return "success"
        else:
            return "info"
    except Exception as e:
        logger.error("Error determining message type: %s", str(e))
        return "error"
