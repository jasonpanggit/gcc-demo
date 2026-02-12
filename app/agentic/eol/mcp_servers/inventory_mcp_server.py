"""MCP server exposing Log Analytics inventory retrieval tools."""
from __future__ import annotations

import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Annotated, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve()
for depth in range(4, -1, -1):
    candidate = PROJECT_ROOT.parents[depth] if depth < len(PROJECT_ROOT.parents) else None
    if candidate and (candidate / "app").is_dir():
        if str(candidate) not in sys.path:
            sys.path.insert(0, str(candidate))
        break

EOL_ROOT = PROJECT_ROOT.parent.parent
if (EOL_ROOT / "agents").is_dir() and str(EOL_ROOT) not in sys.path:
    sys.path.insert(0, str(EOL_ROOT))

from mcp.server.fastmcp import Context, FastMCP
from mcp.types import TextContent

try:
    from agents.os_inventory_agent import OSInventoryAgent
    from agents.software_inventory_agent import SoftwareInventoryAgent
except ModuleNotFoundError:
    from app.agentic.eol.agents.os_inventory_agent import OSInventoryAgent
    from app.agentic.eol.agents.software_inventory_agent import SoftwareInventoryAgent

logger = logging.getLogger(__name__)

_server = FastMCP(name="law-inventory")
_os_agent: Optional[OSInventoryAgent] = None
_software_agent: Optional[SoftwareInventoryAgent] = None
_agent_lock = asyncio.Lock()


async def _ensure_agents() -> None:
    global _os_agent, _software_agent
    if _os_agent is not None and _software_agent is not None:
        return
    async with _agent_lock:
        if _os_agent is None:
            logger.info("Starting OS inventory agent for MCP server")
            _os_agent = OSInventoryAgent()
        if _software_agent is None:
            logger.info("Starting software inventory agent for MCP server")
            _software_agent = SoftwareInventoryAgent()


def _text_payload(payload: Dict[str, object]) -> List[TextContent]:
    return [TextContent(type="text", text=json.dumps(payload, ensure_ascii=False, indent=2))]


def _normalise_tabular_result(
    *,
    agent_result: Dict[str, object],
    requested: Dict[str, object],
    data_field: str,
) -> Dict[str, object]:
    """Flatten nested agent responses so the UI renders a single data table."""

    if not isinstance(agent_result, dict):
        return {
            "success": False,
            "requested": requested,
            "data": [],
            "error": "Inventory agent returned an unexpected payload format.",
        }

    raw_rows = agent_result.get(data_field)
    if isinstance(raw_rows, list):
        rows: object = raw_rows
    elif raw_rows is None:
        rows = []
    else:
        rows = [raw_rows]

    metadata = {
        key: value
        for key, value in agent_result.items()
        if key not in {data_field, "success", "error"}
    }

    payload: Dict[str, object] = {
        "success": bool(agent_result.get("success", True)),
        "requested": requested,
        "data": rows,
    }

    if agent_result.get("error"):
        payload["error"] = agent_result["error"]

    if metadata:
        payload["metadata"] = metadata

    return payload


@_server.tool(
    name="law_get_os_inventory",
    description=(
        "Get raw OS inventory records from Log Analytics — one row per computer. "
        "Returns: computer name, OS name, OS version, environment, IP address, last seen date. "
        "Use this to get the full machine-level list. "
        "For aggregated views, use law_get_os_summary or law_get_os_environment_breakdown instead."
    ),
)
async def law_get_os_inventory(
    context: Context,  # noqa: ARG001 - unused but required by FastMCP
    days: Annotated[int, "Lookback window in days."] = 90,
    limit: Annotated[int, "Maximum number of rows to return (default 2000)."] = 2000,
    use_cache: Annotated[bool, "Use cached inventory when available (default true)."] = True,
) -> List[TextContent]:
    await _ensure_agents()
    assert _os_agent is not None  # Satisfy type checkers

    try:
        result = await _os_agent.get_os_inventory(days=days, limit=limit, use_cache=use_cache)
    except Exception as exc:  # pylint: disable=broad-except
        logger.exception("OS inventory retrieval failed")
        return _text_payload({"success": False, "error": str(exc), "requested": {"days": days, "limit": limit}})

    payload = _normalise_tabular_result(
        agent_result=result,
        requested={"days": days, "limit": limit, "use_cache": use_cache},
        data_field="data",
    )
    return _text_payload(payload)


@_server.tool(
    name="law_get_os_summary",
    description=(
        "Get a summary of OS types and version counts from Log Analytics. "
        "Returns: OS name, version, and how many computers run each combination. "
        "Use this for a quick overview of what operating systems are deployed."
    ),
)
async def law_get_os_summary(
    context: Context,  # noqa: ARG001 - unused
    days: Annotated[int, "Lookback window in days."] = 90,
) -> List[TextContent]:
    await _ensure_agents()
    assert _os_agent is not None

    try:
        summary = await _os_agent.get_os_summary(days=days)
    except Exception as exc:  # pylint: disable=broad-except
        logger.exception("OS summary retrieval failed")
        return _text_payload({"success": False, "error": str(exc), "requested": {"days": days}})

    payload = {
        "success": True,
        "requested": {"days": days},
        "data": summary,
    }
    return _text_payload(payload)


@_server.tool(
    name="law_get_software_inventory",
    description=(
        "Get raw software inventory records from Log Analytics ConfigurationData. "
        "Returns: computer name, software name, publisher, version, install date. "
        "Use software_filter to search for specific software (e.g., 'SQL Server', 'Java'). "
        "For aggregated views, use law_get_software_publisher_summary or law_get_top_software_packages."
    ),
)
async def law_get_software_inventory(
    context: Context,  # noqa: ARG001 - unused
    days: Annotated[int, "Lookback window in days."] = 90,
    limit: Annotated[int, "Maximum number of rows to return (default 10000)."] = 10000,
    software_filter: Annotated[Optional[str], "Optional substring filter applied to the software name."] = None,
    use_cache: Annotated[bool, "Use cached inventory when available (default true)."] = True,
) -> List[TextContent]:
    await _ensure_agents()
    assert _software_agent is not None

    try:
        result = await _software_agent.get_software_inventory(
            days=days,
            software_filter=software_filter,
            limit=limit,
            use_cache=use_cache,
        )
    except Exception as exc:  # pylint: disable=broad-except
        logger.exception("Software inventory retrieval failed")
        return _text_payload(
            {
                "success": False,
                "error": str(exc),
                "requested": {
                    "days": days,
                    "limit": limit,
                    "software_filter": software_filter,
                    "use_cache": use_cache,
                },
            }
        )

    payload = _normalise_tabular_result(
        agent_result=result,
        requested={
            "days": days,
            "limit": limit,
            "software_filter": software_filter,
            "use_cache": use_cache,
        },
        data_field="data",
    )
    return _text_payload(payload)


@_server.tool(
    name="law_get_os_environment_breakdown",
    description=(
        "Break down OS inventory by environment (Production, Dev, Staging, etc.) and computer type. "
        "Returns: environment, computer type, OS name, and count. "
        "Use this when the user wants to see OS distribution across environments."
    ),
)
async def law_get_os_environment_breakdown(
    context: Context,  # noqa: ARG001 - unused
    days: Annotated[int, "Lookback window in days."] = 90,
    top: Annotated[Optional[int], "Optional cap on rows returned (default all)."] = None,
) -> List[TextContent]:
    await _ensure_agents()
    assert _os_agent is not None

    try:
        breakdown = await _os_agent.get_os_environment_breakdown(days=days, top_n=top)
    except Exception as exc:  # pragma: no cover - defensive catch
        logger.exception("OS environment breakdown retrieval failed")
        return _text_payload({
            "success": False,
            "error": str(exc),
            "requested": {"days": days, "top": top},
        })

    payload = _normalise_tabular_result(
        agent_result=breakdown,
        requested={"days": days, "top": top if top is not None else "all"},
        data_field="environment_breakdown",
    )
    return _text_payload(payload)


@_server.tool(
    name="law_get_os_vendor_summary",
    description=(
        "Summarize OS inventory by vendor (Microsoft, Red Hat, Canonical, etc.) and OS type. "
        "Returns: vendor, OS type, and count. "
        "Use this to understand the OS vendor distribution in the environment."
    ),
)
async def law_get_os_vendor_summary(
    context: Context,  # noqa: ARG001 - unused
    days: Annotated[int, "Lookback window in days."] = 90,
    top: Annotated[Optional[int], "Optional cap on rows returned (default all)."] = None,
) -> List[TextContent]:
    await _ensure_agents()
    assert _os_agent is not None

    try:
        summary = await _os_agent.get_os_vendor_summary(days=days, top_n=top)
    except Exception as exc:  # pragma: no cover
        logger.exception("OS vendor summary retrieval failed")
        return _text_payload({
            "success": False,
            "error": str(exc),
            "requested": {"days": days, "top": top},
        })

    payload = _normalise_tabular_result(
        agent_result=summary,
        requested={"days": days, "top": top if top is not None else "all"},
        data_field="vendor_summary",
    )
    return _text_payload(payload)


@_server.tool(
    name="law_get_software_publisher_summary",
    description=(
        "Summarize software inventory by publisher — shows top publishers and how many "
        "distinct software packages each has installed. "
        "Use this for a high-level view of software vendors in the environment."
    ),
)
async def law_get_software_publisher_summary(
    context: Context,  # noqa: ARG001 - unused
    days: Annotated[int, "Lookback window in days."] = 90,
    top: Annotated[Optional[int], "Maximum number of publishers to return (default 25)."] = 25,
) -> List[TextContent]:
    await _ensure_agents()
    assert _software_agent is not None

    try:
        summary = await _software_agent.get_software_publisher_summary(days=days, top_n=top)
    except Exception as exc:  # pragma: no cover
        logger.exception("Software publisher summary retrieval failed")
        return _text_payload({
            "success": False,
            "error": str(exc),
            "requested": {"days": days, "top": top},
        })

    payload = _normalise_tabular_result(
        agent_result=summary,
        requested={"days": days, "top": top if top is not None else "all"},
        data_field="publisher_summary",
    )
    return _text_payload(payload)


@_server.tool(
    name="law_get_top_software_packages",
    description=(
        "List the most commonly installed software packages across all computers. "
        "Returns: software name, version (optional), publisher, and install count. "
        "Use this to identify the most prevalent software in the environment."
    ),
)
async def law_get_top_software_packages(
    context: Context,  # noqa: ARG001 - unused
    days: Annotated[int, "Lookback window in days."] = 90,
    top: Annotated[Optional[int], "Maximum number of packages to return (default 50)."] = 50,
    include_versions: Annotated[bool, "Include version granularity when aggregating (default true)."] = True,
) -> List[TextContent]:
    await _ensure_agents()
    assert _software_agent is not None

    try:
        packages = await _software_agent.get_top_software_packages(
            days=days,
            top_n=top,
            include_versions=include_versions,
        )
    except Exception as exc:  # pragma: no cover
        logger.exception("Top software packages retrieval failed")
        return _text_payload({
            "success": False,
            "error": str(exc),
            "requested": {
                "days": days,
                "top": top,
                "include_versions": include_versions,
            },
        })

    payload = _normalise_tabular_result(
        agent_result=packages,
        requested={
            "days": days,
            "top": top if top is not None else "all",
            "include_versions": include_versions,
        },
        data_field="software_packages",
    )
    return _text_payload(payload)


async def _shutdown() -> None:
    global _os_agent, _software_agent
    tasks = []
    for agent in (_os_agent, _software_agent):
        if hasattr(agent, "aclose") and callable(agent.aclose):
            tasks.append(agent.aclose())  # type: ignore[misc]
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
    _os_agent = None
    _software_agent = None


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    try:
        _server.run()
    finally:
        try:
            asyncio.run(_shutdown())
        except RuntimeError:
            loop = asyncio.get_event_loop()
            loop.create_task(_shutdown())


if __name__ == "__main__":
    main()
