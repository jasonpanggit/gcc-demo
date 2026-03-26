"""EOL Orchestrator Agent — thin coordinator for tiered EOL data retrieval.

Delegates dispatch to TieredFetchPipeline, aggregation to ResultAggregator,
and bulk operations to dedicated helpers in utils/.
All five public method signatures are preserved for API compatibility.
"""
import asyncio
import uuid
import time
from typing import Dict, List, Any, Optional, Set
from datetime import datetime, timezone

from .endoflife_agent import EndOfLifeAgent
from .microsoft_agent import MicrosoftEOLAgent
from .redhat_agent import RedHatEOLAgent
from .ubuntu_agent import UbuntuEOLAgent
from .inventory_agent import InventoryAgent
from .os_inventory_agent import OSInventoryAgent
from .software_inventory_agent import SoftwareInventoryAgent
from .azure_ai_agent import AzureAIAgentEOLAgent
from .oracle_agent import OracleEOLAgent
from .vmware_agent import VMwareEOLAgent
from .apache_agent import ApacheEOLAgent
from .nodejs_agent import NodeJSEOLAgent
from .postgresql_agent import PostgreSQLEOLAgent
from .php_agent import PHPEOLAgent
from .python_agent import PythonEOLAgent
from .playwright_agent import PlaywrightEOLAgent
from .eolstatus_agent import EOLStatusAgent

try:
    from utils.normalization import NormalizedQuery
except ImportError:
    from ..utils.normalization import NormalizedQuery  # type: ignore[no-redef]

from utils.eol_inventory import eol_inventory
from utils.orchestrator_comms import format_communication_message, determine_message_type
from utils.eol_response_tracker import track_eol_agent_response
from utils.os_inventory_eol_helper import enrich_os_inventory_with_eol

try:
    from utils.config import config as _app_config
except ImportError:
    _app_config = None  # type: ignore[assignment]

# Import from pipeline package - works both in dev and Docker
import sys
from pathlib import Path

# Ensure parent directory is in path for relative imports
_parent_dir = Path(__file__).resolve().parent.parent
if str(_parent_dir) not in sys.path:
    sys.path.insert(0, str(_parent_dir))

from pipeline import (
    create_default_registry, TieredFetchPipeline,
    ResultAggregator, AdapterRegistry, FallbackAdapter,
)

try:
    from utils import get_logger
    logger = get_logger(__name__)
except ImportError:
    import logging
    logger = logging.getLogger(__name__)

DEFAULT_CACHE_TTL_SECONDS = 3600
MAX_COMMS_LOG_SIZE = 100
MAX_EOL_RESPONSES_TRACKED = 50
RECENT_COMMS_DISPLAY_LIMIT = 20


class EOLOrchestratorAgent:
    """Thin coordinator that routes EOL queries through the tiered pipeline."""

    def __init__(
        self,
        *,
        agents: Optional[Dict[str, Any]] = None,
        vendor_routing: Optional[Dict[str, List[str]]] = None,
        use_mock_data: Optional[bool] = None,
        close_provided_agents: bool = False,
    ) -> None:
        self.session_id = str(uuid.uuid4())
        self.start_time = datetime.now(timezone.utc)
        self._comms_log: List[Dict[str, Any]] = []
        self.agent_name = "eol_orchestrator"
        self.eol_agent_responses: List[Dict[str, Any]] = []
        self._close_lock = asyncio.Lock()
        self._closed = False
        self._owns_agents = close_provided_agents or agents is None
        self._background_tasks: Set[asyncio.Task] = set()
        self.agents = dict(agents) if agents is not None else self._create_default_agents(use_mock_data=use_mock_data)
        self.eol_cache: Dict[str, Any] = {}
        self.cache_ttl = DEFAULT_CACHE_TTL_SECONDS

        _threshold = 0.80
        try:
            if _app_config is not None:
                _threshold = _app_config.eol.pipeline_confidence_threshold
        except (AttributeError, Exception):
            pass

        self._pipeline_registry = create_default_registry(self.agents, vendor_routing=vendor_routing)
        self._pipeline = TieredFetchPipeline(self._pipeline_registry, confidence_threshold=_threshold)
        self._aggregator = ResultAggregator()
        logger.info("🚀 EOL Orchestrator initialized with %d agents", len(self.agents))

    def _create_default_agents(self, *, use_mock_data: Optional[bool]) -> Dict[str, Any]:
        import os
        resolved = use_mock_data if use_mock_data is not None else (os.getenv("USE_MOCK_DATA", "false").lower() == "true")
        if resolved:
            try:
                from tests.mock_agents import MockOSInventoryAgent, MockSoftwareInventoryAgent  # type: ignore
                sa: Any = MockSoftwareInventoryAgent()
                oa: Any = MockOSInventoryAgent()
                logger.info("🧪 EOL Orchestrator: MOCK MODE")
            except ImportError as exc:
                logger.warning("Mock agents unavailable (%s). Using real agents.", exc)
                sa, oa = SoftwareInventoryAgent(), OSInventoryAgent()
        else:
            sa, oa = SoftwareInventoryAgent(), OSInventoryAgent()
        return {
            "inventory": InventoryAgent(), "os_inventory": oa, "software_inventory": sa,
            "endoflife": EndOfLifeAgent(), "microsoft": MicrosoftEOLAgent(), "redhat": RedHatEOLAgent(),
            "ubuntu": UbuntuEOLAgent(), "oracle": OracleEOLAgent(), "vmware": VMwareEOLAgent(),
            "apache": ApacheEOLAgent(), "nodejs": NodeJSEOLAgent(), "postgresql": PostgreSQLEOLAgent(),
            "php": PHPEOLAgent(), "python": PythonEOLAgent(), "eolstatus": EOLStatusAgent(),
            "azure_ai": AzureAIAgentEOLAgent(), "playwright": PlaywrightEOLAgent(),
        }

    def _iter_unique_agents(self):
        seen: Set[int] = set()
        for agent in self.agents.values():
            if id(agent) not in seen:
                seen.add(id(agent))
                yield agent

    async def _maybe_aclose_agent(self, agent: Any) -> None:
        try:
            fn = getattr(agent, "aclose", None) or getattr(agent, "close", None)
            if callable(fn):
                result = fn()
                if asyncio.iscoroutine(result):
                    await result
        except Exception as exc:
            logger.debug("Ignored error closing %s: %s", type(agent).__name__, exc)

    def _spawn_background(self, coro, *, name: Optional[str] = None) -> asyncio.Task:
        task = asyncio.create_task(coro, name=name)
        self._background_tasks.add(task)
        def _on_done(t: asyncio.Task) -> None:
            self._background_tasks.discard(t)
            if not t.cancelled() and t.exception() is not None:
                logger.debug("Background task %r raised: %s", t.get_name(), t.exception())
        task.add_done_callback(_on_done)
        return task

    async def shutdown(self) -> None:
        tasks = list(self._background_tasks)
        for t in tasks:
            t.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._background_tasks.clear()

    async def aclose(self) -> None:
        await self.shutdown()
        async with self._close_lock:
            if self._closed:
                return
            self._closed = True
        if self._owns_agents:
            await asyncio.gather(*[self._maybe_aclose_agent(a) for a in self._iter_unique_agents()], return_exceptions=True)
        logger.info("🧹 EOL orchestrator resources released")

    async def __aenter__(self) -> "EOLOrchestratorAgent":
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self.aclose()

    @property
    def vendor_routing(self) -> Dict[str, List[str]]:
        """Expose vendor routing map from the VendorScraperAdapter.

        This allows the API endpoint to access the vendor routing configuration
        that determines which keywords map to which vendor agents.

        Returns:
            Dict mapping vendor name to list of keywords (software names).
            Returns empty dict if VendorScraperAdapter is not registered.
        """
        try:
            # Find the VendorScraperAdapter in the registry
            for adapter in self._pipeline_registry.all_adapters():
                if adapter.name == "vendor_scraper" and adapter.tier == 3:
                    # VendorScraperAdapter stores routing in _vendor_routing
                    return getattr(adapter, "_vendor_routing", {})
            return {}
        except Exception as exc:
            logger.warning("Failed to retrieve vendor_routing from pipeline: %s", exc)
            return {}

    async def log_communication(self, agent_name: str, action: str, data: Dict[str, Any], result: Optional[Dict[str, Any]] = None) -> None:
        try:
            self._comms_log.append({"id": str(uuid.uuid4()), "sessionId": self.session_id, "timestamp": datetime.now(timezone.utc).isoformat(), "agentName": agent_name, "action": action, "input": data, "output": result})
            if len(self._comms_log) > MAX_COMMS_LOG_SIZE:
                self._comms_log = self._comms_log[-MAX_COMMS_LOG_SIZE:]
        except Exception as exc:
            logger.error("Error logging communication: %s", exc)

    def get_recent_communications(self) -> List[Dict[str, Any]]:
        try:
            if not isinstance(self._comms_log, list):
                self._comms_log = []
            comms = []
            for comm in reversed(self._comms_log[-RECENT_COMMS_DISPLAY_LIMIT:]):
                if not isinstance(comm, dict):
                    continue
                comms.append({"timestamp": comm.get("timestamp", ""), "agent_name": comm.get("agentName", "unknown"), "action": comm.get("action", "unknown"), "status": "completed", "input": comm.get("input", {}), "output": comm.get("output", {}), "message": format_communication_message(comm), "type": determine_message_type(comm), "session_id": comm.get("sessionId", self.session_id)})
            if not comms:
                comms.append({"timestamp": self.start_time.isoformat(), "agent_name": "eol_orchestrator", "action": "session_start", "status": "completed", "input": {}, "output": {"session_id": self.session_id}, "message": "🚀 EOL Orchestrator session started", "type": "info"})
            return comms
        except Exception as exc:
            logger.error("Error getting recent communications: %s", exc)
            return []

    async def get_communication_history(self) -> List[Dict[str, Any]]:
        return list(reversed(self._comms_log))

    def clear_communications(self) -> Dict[str, Any]:
        try:
            prev, cache_before = len(self._comms_log), len(self.eol_cache)
            self._comms_log.clear()
            self.eol_cache.clear()
            old_sid = self.session_id
            self.session_id = str(uuid.uuid4())
            self.start_time = datetime.now(timezone.utc)
            return {"success": True, "message": f"Cleared {prev} communications", "details": {"communications_cleared": prev, "cache_items_cleared": cache_before, "new_session_id": self.session_id}}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    async def _track_eol_agent_response(self, *, agent_name: str, software_name: str, software_version: Optional[str], eol_result: Dict[str, Any], response_time: float, query_type: str) -> None:
        await track_eol_agent_response(responses_list=self.eol_agent_responses, session_id=self.session_id, eol_repo=getattr(self, "eol_repo", None), agent_name=agent_name, software_name=software_name, software_version=software_version, eol_result=eol_result, response_time=response_time, query_type=query_type)

    def get_eol_agent_responses(self) -> List[Dict[str, Any]]:
        return self.eol_agent_responses.copy()

    def clear_eol_agent_responses(self) -> None:
        self.eol_agent_responses.clear()

    async def get_cache_status(self) -> Dict[str, Any]:
        try:
            now = datetime.now(timezone.utc)
            total = len(self.eol_cache)
            return {"success": True, "data": {"eol_cache": {"total_items": total, "cache_ttl_seconds": self.cache_ttl}, "agents": {n: {"status": "available", "type": type(a).__name__} for n, a in self.agents.items()}, "session": {"session_id": self.session_id, "uptime_seconds": (now - self.start_time).total_seconds()}}}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    async def get_os_inventory_with_eol(self, days: int = 90) -> Dict[str, Any]:
        try:
            os_result = await self.agents["os_inventory"].get_os_inventory(days=days)
            if not os_result.get("success") or not os_result.get("data"):
                return {"success": False, "error": "Failed to retrieve OS inventory", "data": []}
            return await enrich_os_inventory_with_eol(os_result["data"], self.eol_cache, self.cache_ttl, self.session_id, self.get_autonomous_eol_data)
        except Exception as exc:
            logger.error("❌ OS inventory EOL analysis failed: %s", exc)
            return {"success": False, "error": str(exc), "data": []}

    async def get_autonomous_eol_data(
        self,
        software_name,
        version=None,
        item_type="software",
        search_internet_only=False,
        search_include_internet=False,
        search_ignore_cache=False,
        search_agent_only=False,
        fast_mode=True,
    ):
        """Autonomous EOL data retrieval via tiered pipeline.

        Args:
            fast_mode: When True (default), use early-terminating fetch()
                that stops at the first tier returning a high-confidence result.
                When False, use fetch_all() to run all tiers for cross-source
                validation. The default is True because endoflife.date covers
                487 products and Playwright fallback adds 12-15s latency for
                products already covered by Tier 1.
        """
        try:
            t0 = time.time()
            software_name = (software_name or "").strip()
            version = (version.strip() or None) if version else None

            if not software_name:
                return {"success": False, "error": "software_name is required", "agent_used": "orchestrator", "communications": self.get_recent_communications(), "elapsed_seconds": time.time() - t0}

            await self.log_communication("eol_orchestrator", "get_autonomous_eol_data", {"software_name": software_name, "version": version, "item_type": item_type, "search_internet_only": search_internet_only, "search_include_internet": search_include_internet, "search_ignore_cache": search_ignore_cache, "search_agent_only": search_agent_only})

            _nq = NormalizedQuery.from_os(software_name, version) if item_type == "os" else NormalizedQuery.from_software(software_name, version)
            normalized_name, normalized_version = _nq.as_tuple()

            if not (search_ignore_cache or search_internet_only):
                _dbt = getattr(getattr(_app_config, "timeouts", None), "db_query_timeout", 10.0)
                try:
                    cached_eol = await asyncio.wait_for(eol_inventory.get(normalized_name, normalized_version), timeout=_dbt)
                except asyncio.TimeoutError:
                    logger.warning("EOL cache timeout for %s %s", normalized_name, normalized_version)
                    cached_eol = None
                if cached_eol:
                    cd = cached_eol.get("data") or {}
                    if float(cd.get("confidence") or cached_eol.get("confidence") or 0) > 0 and (cd.get("eol_date") or cached_eol.get("eol_date")):
                        cached_eol.update({"agent_used": cached_eol.get("agent_used") or "cached", "cache_hit": True, "cache_source": "eol_cache", "elapsed_seconds": time.time() - t0, "communications": self.get_recent_communications(), "sources": [], "discrepancies": []})
                        await self._track_eol_agent_response(agent_name=cached_eol.get("agent_used", "eol_inventory"), software_name=software_name, software_version=version, eol_result=cached_eol, response_time=time.time() - t0, query_type="eol_cache")
                        return cached_eol

            pipeline = self._pipeline
            if search_internet_only:
                reg = AdapterRegistry()
                if "playwright" in self.agents:
                    reg.register(FallbackAdapter(self.agents["playwright"]))
                pipeline = TieredFetchPipeline(reg)
            elif search_agent_only:
                pipeline = TieredFetchPipeline(create_default_registry({k: v for k, v in self.agents.items() if k != "playwright"}))

            if fast_mode:
                # Early-terminating fetch: stops at first high-confidence tier
                best_result = await pipeline.fetch(_nq)
                results = [best_result] if best_result is not None else []
            else:
                # Full cross-source validation: runs all tiers
                results = await pipeline.fetch_all(_nq)
            aggregated = self._aggregator.aggregate(results)

            if aggregated.primary is not None:
                p = aggregated.primary
                bc = aggregated.confidence
                dp: Dict[str, Any] = p.raw_data.get("data", {}) if p.raw_data else {}
                if not isinstance(dp, dict):
                    dp = {}
                sm = "internet_only" if search_internet_only else ("agents_only" if search_agent_only else "agents_plus_internet")
                best = {"success": True, "data": dp, "confidence": bc, "agent_used": p.source or p.agent_used or "unknown", "source": p.source or "unknown", "source_url": p.source_url, "search_mode": sm, "sources": aggregated.sources_as_dicts(), "discrepancies": aggregated.discrepancies_as_dicts(), "communications": self.get_recent_communications(), "elapsed_seconds": time.time() - t0}
                for k, v in [("software_name", p.software_name), ("version", p.version), ("eol_date", p.eol_date), ("support_end_date", p.support_end_date), ("release_date", p.release_date), ("source_url", p.source_url), ("confidence", bc), ("agent_used", best["agent_used"]), ("source", p.source), ("search_mode", sm)]:
                    dp.setdefault(k, v)
                await self._track_eol_agent_response(agent_name=best["agent_used"], software_name=software_name, software_version=version, eol_result=best, response_time=time.time() - t0, query_type="autonomous_search")
                _thr = 0.80
                try:
                    if _app_config is not None:
                        _thr = _app_config.eol.pipeline_confidence_threshold
                except (AttributeError, Exception):
                    pass
                if bc >= _thr and not search_ignore_cache:
                    best.setdefault("cache_source", "eol_cache")
                    best.setdefault("cached", False)
                    _nn, _nv, _res, _sn, _sv, _it = normalized_name, normalized_version, best, software_name, version, item_type
                    async def _do_upsert(_nn=_nn, _nv=_nv, _res=_res, _sn=_sn, _sv=_sv, _it=_it):
                        try:
                            await eol_inventory.upsert(_nn, _nv, _res, raw_software_name=_sn, raw_version=_sv, item_type=_it)
                        except Exception as exc:
                            logger.debug("EOL upsert skipped: %s", exc)
                    self._spawn_background(_do_upsert(), name=f"db_upsert_{normalized_name}")
                logger.info("EOL data found for %s (confidence: %.2f, agent: %s)", software_name, bc, best["agent_used"])
                return best

            err = "No EOL data found via internet search" if search_internet_only else "No EOL data found from pipeline"
            fail = {"success": False, "error": err, "agent_used": "playwright" if search_internet_only else "orchestrator", "sources": [], "discrepancies": [], "communications": self.get_recent_communications(), "elapsed_seconds": time.time() - t0}
            await self._track_eol_agent_response(agent_name="orchestrator", software_name=software_name, software_version=version, eol_result=fail, response_time=time.time() - t0, query_type="autonomous_search")
            return fail

        except Exception as exc:
            logger.error("Error in autonomous EOL data retrieval: %s", exc)
            return {"success": False, "error": str(exc), "agent_used": "orchestrator", "sources": [], "discrepancies": [], "communications": self.get_recent_communications(), "elapsed_seconds": time.time() - t0}

    async def get_eol_data(self, software_name, version=None):
        return await self.get_autonomous_eol_data(software_name, version)

    async def get_software_inventory(self, days=90, include_eol=True, use_cache=True):
        return await self.agents["software_inventory"].get_software_inventory(days=days, use_cache=use_cache)

    async def search_software_eol(self, software_name: str, software_version: str = None, search_hints: str = None, search_include_internet: bool = False, search_ignore_cache: bool = False, search_agent_only: bool = False):
        return await self.get_autonomous_eol_data(software_name=software_name, version=software_version, item_type="os", search_internet_only=False, search_include_internet=search_include_internet, search_ignore_cache=search_ignore_cache, search_agent_only=search_agent_only)

    async def search_software_eol_internet(self, software_name: str, software_version: str = None, search_hints: str = None, search_ignore_cache: bool = False):
        return await self.get_autonomous_eol_data(software_name=software_name, version=software_version, item_type="os", search_internet_only=True, search_ignore_cache=search_ignore_cache)

    async def health_check(self) -> Dict[str, Any]:
        try:
            status: Dict[str, Any] = {"orchestrator": {"status": "healthy", "session_id": self.session_id, "uptime_seconds": (datetime.utcnow() - self.start_time).total_seconds(), "cache_size": len(self.eol_cache), "agents_count": len(self.agents)}, "agents": {}}
            for name, agent in list(self.agents.items())[:5]:
                try:
                    status["agents"][name] = await asyncio.wait_for(agent.health_check(), timeout=2.0) if hasattr(agent, "health_check") else {"status": "available"}
                except Exception:
                    status["agents"][name] = {"status": "timeout"}
            return {"success": True, "data": status}
        except Exception as exc:
            return {"success": False, "error": str(exc)}


# Backward compatibility alias
OrchestratorAgent = EOLOrchestratorAgent
