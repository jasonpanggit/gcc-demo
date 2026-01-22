"""MCP server exposing operating system EOL lookup tools."""
from __future__ import annotations

import asyncio
import json
import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any, Dict, List, Optional

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
    from agents.eol_orchestrator import EOLOrchestratorAgent
except ModuleNotFoundError:
    from app.agentic.eol.agents.eol_orchestrator import EOLOrchestratorAgent

logger = logging.getLogger(__name__)

_server = FastMCP(name="os-eol")
_orchestrator: Optional[EOLOrchestratorAgent] = None
_orchestrator_lock = asyncio.Lock()


async def _ensure_orchestrator() -> EOLOrchestratorAgent:
    global _orchestrator
    if _orchestrator is not None:
        return _orchestrator
    async with _orchestrator_lock:
        if _orchestrator is None:
            logger.info("Starting EOL orchestrator for OS MCP server")
            _orchestrator = EOLOrchestratorAgent()
    return _orchestrator


def _to_text_content(payload: Dict[str, Any]) -> List[TextContent]:
    return [TextContent(type="text", text=json.dumps(payload, ensure_ascii=False, indent=2))]


@_server.tool(
    name="os_eol_lookup",
    description="Retrieve end-of-life details for a single operating system using the EOL orchestrator.",
)
async def os_eol_lookup(
    context: Context,  # noqa: ARG001 - unused but required by FastMCP
    os_name: Annotated[str, "Operating system name such as 'Windows Server 2016'."],
    os_version: Annotated[Optional[str], "Optional operating system version string."] = None,
) -> List[TextContent]:
    orchestrator = await _ensure_orchestrator()
    result = await orchestrator.get_autonomous_eol_data(os_name, os_version, item_type="os")
    payload = {
        "success": bool(result.get("success")),
        "requested": {"os_name": os_name, "os_version": os_version},
        "result": result,
    }
    return _to_text_content(payload)


@dataclass
class BulkOSEntry:
    name: str
    version: Optional[str]
    alias: Optional[str] = None

    @classmethod
    def from_payload(cls, item: Dict[str, Any]) -> "BulkOSEntry":
        name = str(
            item.get("os_name")
            or item.get("name")
            or item.get("software")
            or item.get("label")
            or ""
        ).strip()
        version_value = item.get("os_version") or item.get("version")
        version = str(version_value).strip() if version_value is not None else None
        alias_value = item.get("alias") or item.get("id") or item.get("key")
        alias = str(alias_value).strip() if alias_value is not None else None
        return cls(name=name, version=version or None, alias=alias or None)

    def is_valid(self) -> bool:
        return bool(self.name)


@_server.tool(
    name="os_eol_bulk_lookup",
    description="Perform EOL lookup for multiple operating systems in a single call.",
)
async def os_eol_bulk_lookup(
    context: Context,  # noqa: ARG001 - unused but required by FastMCP
    items: Annotated[List[Dict[str, Any]], "List of operating system descriptors."],
    concurrency: Annotated[int, "Maximum concurrent lookups (default 5, max 10)."] = 5,
) -> List[TextContent]:
    if not items:
        return _to_text_content({"success": False, "error": "No OS entries provided.", "results": []})

    orchestrator = await _ensure_orchestrator()
    semaphore = asyncio.Semaphore(max(1, min(concurrency, 10)))

    results: List[Dict[str, Any]] = []

    async def _lookup(entry: BulkOSEntry) -> None:
        if not entry.is_valid():
            results.append(
                {
                    "success": False,
                    "requested": {"os_name": entry.name, "os_version": entry.version},
                    "error": "Missing operating system name.",
                    "alias": entry.alias,
                }
            )
            return
        async with semaphore:
            try:
                lookup = await orchestrator.get_autonomous_eol_data(entry.name, entry.version, item_type="os")
            except Exception as exc:  # pylint: disable=broad-except
                logger.exception("Bulk OS EOL lookup failed for %s %s", entry.name, entry.version or "")
                results.append(
                    {
                        "success": False,
                        "requested": {"os_name": entry.name, "os_version": entry.version},
                        "error": str(exc),
                        "alias": entry.alias,
                    }
                )
                return

            results.append(
                {
                    "success": bool(lookup.get("success")),
                    "requested": {"os_name": entry.name, "os_version": entry.version},
                    "result": lookup,
                    "alias": entry.alias,
                }
            )

    tasks = []
    for raw_item in items:
        try:
            entry = BulkOSEntry.from_payload(raw_item)
        except Exception as exc:  # pylint: disable=broad-except
            results.append(
                {
                    "success": False,
                    "requested": {"os_name": None, "os_version": None},
                    "error": f"Invalid item format: {exc}",
                }
            )
            continue
        tasks.append(asyncio.create_task(_lookup(entry)))

    if tasks:
        await asyncio.gather(*tasks)

    payload = {
        "success": any(item.get("success") for item in results),
        "results": results,
        "count": len(results),
    }
    return _to_text_content(payload)


async def _shutdown() -> None:
    global _orchestrator
    if _orchestrator is not None:
        try:
            await _orchestrator.aclose()
        except Exception:  # pylint: disable=broad-except
            logger.debug("Failed to close EOL orchestrator during shutdown", exc_info=True)
        _orchestrator = None


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    try:
        _server.run()
    finally:
        try:
            asyncio.run(_shutdown())
        except RuntimeError:
            # Event loop already running; schedule best-effort close
            loop = asyncio.get_event_loop()
            loop.create_task(_shutdown())


if __name__ == "__main__":
    main()
