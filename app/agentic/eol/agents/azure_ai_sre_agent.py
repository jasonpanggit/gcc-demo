"""
Azure AI SRE Agent - Integration with Azure AI Agent Service for SRE Operations

This module provides a wrapper around the SRE MCP server tools using Azure AI Agent Service.
It enables managed agent lifecycle, persistent conversation state, and integration with
Azure AI Foundry portal.

Key Features:
- Managed agent lifecycle (start, stop, restart)
- Persistent conversation history in Azure AI Project
- Integration with Azure AI Foundry portal
- Tool registration via Azure AI Agents SDK
- Multi-agent coordination capabilities

Enhanced Features (v2):
- Session/thread management with AgentContextStore integration (24h TTL)
- AIProjectClient singleton with connection pooling
- Configurable timeouts (30s per tool, 120s total)
- Streaming support for SSE token-by-token responses
- L1 in-memory response cache (5min TTL, mutation-aware)
- Parallel tool execution via asyncio.gather()
- Comprehensive metrics tracking (calls, latency, tokens, tool usage)
"""

import asyncio
import hashlib
import inspect
import json
import os
import threading
import time
from typing import Dict, Any, Optional, List, AsyncGenerator, Tuple
from dataclasses import dataclass, field
from datetime import datetime

# Set up logger
try:
    from app.agentic.eol.utils.logger import get_logger
    logger = get_logger(__name__)
except Exception:
    import logging
    logger = logging.getLogger(__name__)


def _is_sre_enabled_from_env() -> bool:
    return os.getenv("AZURE_AI_SRE_ENABLED", "true").lower() == "true"

# Azure AI Agent Service dependencies
try:
    from azure.identity import DefaultAzureCredential
    from azure.ai.projects import AIProjectClient
    from azure.ai.agents import AgentsClient
    from azure.ai.agents.models import Agent, AgentThread, MessageRole, ThreadMessage
    AZURE_AI_AGENTS_AVAILABLE = True
    if _is_sre_enabled_from_env():
        logger.info("Azure AI Agent Service dependencies available")
    else:
        logger.debug("Azure AI Agent Service dependencies available (SRE agent disabled)")
except ImportError as e:
    logger.warning("Azure AI Agent Service dependencies not available: %s", e)
    logger.warning("Install: pip install azure-ai-projects azure-ai-agents azure-identity")
    AZURE_AI_AGENTS_AVAILABLE = False

    # Placeholder classes for type hints when SDK not installed
    class AIProjectClient:  # type: ignore[no-redef]
        pass

    class AgentsClient:  # type: ignore[no-redef]
        pass

    class Agent:  # type: ignore[no-redef]
        pass

    class AgentThread:  # type: ignore[no-redef]
        pass


# ---------------------------------------------------------------------------
# Performance configuration dataclass
# ---------------------------------------------------------------------------

@dataclass
class AgentPerformanceConfig:
    """Performance tuning for Azure AI SRE Agent integration."""

    tool_call_timeout: int = 30           # seconds per tool call
    total_timeout: int = 120              # seconds for entire conversation turn
    parallel_tool_limit: int = 5          # max tools to run concurrently
    cache_ttl_seconds: int = 300          # 5 min response cache TTL
    cache_max_entries: int = 200          # max cached responses
    connection_pool_size: int = 10        # concurrent agent connections
    enable_streaming: bool = True         # SSE streaming support
    enable_response_cache: bool = True    # L1 response cache toggle
    thread_ttl_seconds: int = 86400       # 24h thread TTL in context store

    @classmethod
    def from_env(cls) -> "AgentPerformanceConfig":
        """Load configuration from environment variables with sensible defaults."""
        return cls(
            tool_call_timeout=int(os.getenv("SRE_AGENT_TOOL_TIMEOUT", "30")),
            total_timeout=int(os.getenv("SRE_AGENT_TOTAL_TIMEOUT", "120")),
            parallel_tool_limit=int(os.getenv("SRE_PARALLEL_TOOLS", "5")),
            cache_ttl_seconds=int(os.getenv("SRE_CACHE_TTL", "300")),
            cache_max_entries=int(os.getenv("SRE_CACHE_MAX_ENTRIES", "200")),
            connection_pool_size=int(os.getenv("SRE_CONNECTION_POOL_SIZE", "10")),
            enable_streaming=os.getenv("SRE_ENABLE_STREAMING", "true").lower() == "true",
            enable_response_cache=os.getenv("SRE_ENABLE_CACHE", "true").lower() == "true",
            thread_ttl_seconds=int(os.getenv("SRE_THREAD_TTL", "86400")),
        )


# ---------------------------------------------------------------------------
# L1 in-memory response cache
# ---------------------------------------------------------------------------

# Mutation tools that should never be cached
_MUTATION_TOOLS = frozenset({
    "triage_incident", "plan_remediation", "execute_safe_restart",
    "execute_restart_resource", "scale_resource", "execute_scale_resource",
    "clear_cache", "execute_clear_redis_cache", "send_teams_notification",
    "send_teams_alert", "send_sre_status_update", "define_slo",
    "generate_incident_summary", "generate_postmortem",
    "execute_automation_runbook", "create_incident_ticket",
    "execute_remediation_step", "register_custom_runbook",
})


@dataclass
class _CacheEntry:
    """Single response cache entry with TTL."""
    value: Dict[str, Any]
    created_at: float
    expires_at: float
    query_hash: str


class AgentResponseCache:
    """
    L1 in-memory response cache for agent queries.

    Caches non-mutation query results with configurable TTL (default 5min).
    Uses MD5 hash of query + workflow context as cache key.
    Thread-safe via threading.RLock.
    """

    def __init__(self, ttl_seconds: int = 300, max_entries: int = 200) -> None:
        self._cache: Dict[str, _CacheEntry] = {}
        self._lock = threading.RLock()
        self._ttl = ttl_seconds
        self._max_entries = max_entries
        self._hits = 0
        self._misses = 0

    @staticmethod
    def _make_key(query: str, context: Optional[Dict[str, Any]] = None) -> str:
        """Generate deterministic cache key from query + context."""
        ctx_str = json.dumps(context or {}, sort_keys=True, default=str)
        raw = f"{query.strip().lower()}|{ctx_str}"
        return hashlib.md5(raw.encode()).hexdigest()

    @staticmethod
    def _is_mutation_query(query: str) -> bool:
        """Detect mutation-like queries that should bypass cache."""
        mutation_keywords = (
            "restart", "scale", "remediat", "execute", "clear cache",
            "delete", "remove", "stop", "start service", "rollback",
            "deploy", "update config",
        )
        lower_q = query.lower()
        return any(kw in lower_q for kw in mutation_keywords)

    def get(self, query: str, context: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """Retrieve cached response if available and not expired."""
        if self._is_mutation_query(query):
            return None

        key = self._make_key(query, context)
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                self._misses += 1
                return None
            if time.time() > entry.expires_at:
                del self._cache[key]
                self._misses += 1
                return None
            self._hits += 1
            logger.debug("Agent response cache HIT (key=%s, age=%.0fs)",
                         key[:12], time.time() - entry.created_at)
            return entry.value

    def set(self, query: str, context: Optional[Dict[str, Any]],
            value: Dict[str, Any]) -> None:
        """Cache a response. Skips mutation queries."""
        if self._is_mutation_query(query):
            return

        key = self._make_key(query, context)
        now = time.time()

        with self._lock:
            # Evict expired + oldest if at capacity
            if len(self._cache) >= self._max_entries:
                self._evict_expired()
                if len(self._cache) >= self._max_entries:
                    self._evict_oldest(count=max(1, self._max_entries // 10))

            self._cache[key] = _CacheEntry(
                value=value,
                created_at=now,
                expires_at=now + self._ttl,
                query_hash=key,
            )

    def invalidate_all(self) -> int:
        """Clear all cache entries. Returns count removed."""
        with self._lock:
            count = len(self._cache)
            self._cache.clear()
            self._hits = 0
            self._misses = 0
        return count

    def _evict_expired(self) -> int:
        now = time.time()
        expired = [k for k, v in self._cache.items() if now > v.expires_at]
        for k in expired:
            del self._cache[k]
        return len(expired)

    def _evict_oldest(self, count: int = 10) -> None:
        sorted_entries = sorted(self._cache.items(), key=lambda x: x[1].created_at)
        for k, _ in sorted_entries[:count]:
            del self._cache[k]

    def get_stats(self) -> Dict[str, Any]:
        """Return cache hit/miss statistics."""
        with self._lock:
            total = self._hits + self._misses
            return {
                "entries": len(self._cache),
                "max_entries": self._max_entries,
                "ttl_seconds": self._ttl,
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate_percent": round(self._hits / total * 100, 1) if total > 0 else 0.0,
            }


# ---------------------------------------------------------------------------
# Metrics tracker for agent operations
# ---------------------------------------------------------------------------

class AgentMetrics:
    """
    Comprehensive metrics for Azure AI SRE Agent operations.

    Tracks call counts, latencies, token usage, and tool invocations.
    Integrates with the global MetricsCollector from utils.metrics when available.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._counters: Dict[str, int] = {
            "agent_calls_total": 0,
            "agent_calls_success": 0,
            "agent_calls_error": 0,
            "agent_calls_timeout": 0,
            "agent_calls_cached": 0,
            "mcp_direct_calls_total": 0,
            "agent_tool_calls_total": 0,
            "agent_tool_calls_parallel": 0,
            "agent_streaming_sessions": 0,
            "thread_created": 0,
            "thread_reused": 0,
        }
        self._latencies: List[float] = []  # ms
        self._tool_latencies: Dict[str, List[float]] = {}
        self._token_usage: Dict[str, int] = {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        }
        # Try to integrate with global metrics collector
        self._global_collector = None
        try:
            from utils.metrics import metrics_collector
            self._global_collector = metrics_collector
        except Exception:
            try:
                from app.agentic.eol.utils.metrics import metrics_collector
                self._global_collector = metrics_collector
            except Exception:
                pass

    def record_call(self, success: bool, latency_ms: float,
                    source: str = "agent", cached: bool = False) -> None:
        """Record an agent or MCP direct call."""
        with self._lock:
            if source == "agent":
                self._counters["agent_calls_total"] += 1
                if cached:
                    self._counters["agent_calls_cached"] += 1
                elif success:
                    self._counters["agent_calls_success"] += 1
                else:
                    self._counters["agent_calls_error"] += 1
                self._latencies.append(latency_ms)
                # Keep bounded
                if len(self._latencies) > 1000:
                    self._latencies = self._latencies[-1000:]
            else:
                self._counters["mcp_direct_calls_total"] += 1

        # Forward to global collector
        if self._global_collector:
            labels = {"source": source, "success": str(success)}
            self._global_collector.increment("sre_agent_calls", labels=labels)
            self._global_collector.record_duration("sre_agent_latency_ms", latency_ms, labels=labels)

    def record_timeout(self) -> None:
        """Record a timeout event."""
        with self._lock:
            self._counters["agent_calls_timeout"] += 1

    def record_tool_call(self, tool_name: str, latency_ms: float,
                         parallel: bool = False) -> None:
        """Record a tool invocation."""
        with self._lock:
            self._counters["agent_tool_calls_total"] += 1
            if parallel:
                self._counters["agent_tool_calls_parallel"] += 1
            if tool_name not in self._tool_latencies:
                self._tool_latencies[tool_name] = []
            self._tool_latencies[tool_name].append(latency_ms)
            if len(self._tool_latencies[tool_name]) > 500:
                self._tool_latencies[tool_name] = self._tool_latencies[tool_name][-500:]

        if self._global_collector:
            self._global_collector.increment(
                "sre_agent_tool_calls",
                labels={"tool": tool_name, "parallel": str(parallel)},
            )
            self._global_collector.record_duration(
                "sre_agent_tool_latency_ms", latency_ms,
                labels={"tool": tool_name},
            )

    def record_token_usage(self, prompt: int = 0, completion: int = 0) -> None:
        """Track token consumption."""
        with self._lock:
            self._token_usage["prompt_tokens"] += prompt
            self._token_usage["completion_tokens"] += completion
            self._token_usage["total_tokens"] += prompt + completion

    def record_thread_event(self, created: bool) -> None:
        """Track thread creation vs. reuse."""
        with self._lock:
            if created:
                self._counters["thread_created"] += 1
            else:
                self._counters["thread_reused"] += 1

    def record_streaming_session(self) -> None:
        """Track a streaming SSE session."""
        with self._lock:
            self._counters["agent_streaming_sessions"] += 1

    def get_stats(self) -> Dict[str, Any]:
        """Return comprehensive metrics snapshot."""
        with self._lock:
            # Compute latency percentiles
            latency_stats: Dict[str, float] = {}
            if self._latencies:
                sorted_lat = sorted(self._latencies)
                n = len(sorted_lat)
                latency_stats = {
                    "count": n,
                    "avg_ms": round(sum(sorted_lat) / n, 1),
                    "p50_ms": round(sorted_lat[int(n * 0.5)], 1),
                    "p95_ms": round(sorted_lat[min(int(n * 0.95), n - 1)], 1),
                    "p99_ms": round(sorted_lat[min(int(n * 0.99), n - 1)], 1),
                }

            # Per-tool latency summaries
            tool_stats: Dict[str, Dict[str, float]] = {}
            for tool, lats in self._tool_latencies.items():
                if lats:
                    s = sorted(lats)
                    tool_stats[tool] = {
                        "count": len(s),
                        "avg_ms": round(sum(s) / len(s), 1),
                        "p95_ms": round(s[min(int(len(s) * 0.95), len(s) - 1)], 1),
                    }

            return {
                "counters": dict(self._counters),
                "latency": latency_stats,
                "tool_latencies": tool_stats,
                "token_usage": dict(self._token_usage),
            }

    def reset(self) -> None:
        """Reset all metrics."""
        with self._lock:
            for k in self._counters:
                self._counters[k] = 0
            self._latencies.clear()
            self._tool_latencies.clear()
            for k in self._token_usage:
                self._token_usage[k] = 0


# ---------------------------------------------------------------------------
# Singleton management for Azure AI agent clients
# ---------------------------------------------------------------------------

_client_lock = threading.Lock()
_ai_client_singleton: Optional["AIProjectClient"] = None
_agents_client_singleton: Optional["AgentsClient"] = None


def _get_ai_client_singleton(
    project_endpoint: str,
    credential: Any,
) -> Tuple[Any, Any]:
    """
    Get or create singleton Azure AI clients.

    Prefers `azure.ai.agents.AgentsClient` for runtime agent operations
    (threads/messages/runs). Falls back to `AIProjectClient(...).agents`
    for compatibility if direct client initialization is unavailable.

    Connection pooling is handled by the Azure SDK internally; the singleton
    avoids repeated credential negotiation and object creation overhead.
    """
    global _ai_client_singleton, _agents_client_singleton

    if _ai_client_singleton is not None and _agents_client_singleton is not None:
        return _ai_client_singleton, _agents_client_singleton

    with _client_lock:
        if _ai_client_singleton is not None and _agents_client_singleton is not None:
            return _ai_client_singleton, _agents_client_singleton

        # Primary runtime client for conversational agent interactions
        try:
            _agents_client_singleton = AgentsClient(
                endpoint=project_endpoint,
                credential=credential,
            )
            _ai_client_singleton = None
            logger.info("AgentsClient singleton created (endpoint=%s)", project_endpoint[:40])
            return _ai_client_singleton, _agents_client_singleton
        except Exception as direct_exc:
            logger.debug("AgentsClient init failed, falling back to AIProjectClient: %s", direct_exc)

        # Compatibility fallback for older SDK call paths
        _ai_client_singleton = AIProjectClient(
            endpoint=project_endpoint,
            credential=credential,
        )
        _agents_client_singleton = _ai_client_singleton.agents
        logger.info("AIProjectClient singleton created (fallback, endpoint=%s)", project_endpoint[:40])
        return _ai_client_singleton, _agents_client_singleton


# ---------------------------------------------------------------------------
# Main agent class
# ---------------------------------------------------------------------------

class AzureAISREAgent:
    """
    Azure AI SRE Agent wrapper for managed SRE operations.

    Provides integration between SRE MCP server tools and Azure AI Agent Service
    with session management, connection pooling, response caching, parallel tool
    execution, streaming, and comprehensive metrics.

    Architecture:
        User Query → AzureAISREAgent.chat() → Azure AI Agent Service
                                               ├─ Reasons about intent
                                               ├─ Selects tools
                                               └─ Returns synthesized response

        Fallback: If agent unavailable → caller falls back to direct MCP execution
    """

    def __init__(
        self,
        project_endpoint: Optional[str] = None,
        agent_name: str = "sre-agent",
        instructions: Optional[str] = None,
        perf_config: Optional[AgentPerformanceConfig] = None,
    ):
        """
        Initialize Azure AI SRE Agent.

        Args:
            project_endpoint: Azure AI Project endpoint (uses env var if not provided)
            agent_name: Name for the agent instance
            instructions: System instructions for the agent
            perf_config: Performance tuning configuration (auto-loaded from env if None)
        """
        self.agent_name = agent_name
        self.perf_config = perf_config or AgentPerformanceConfig.from_env()

        # Azure AI Project configuration
        self.project_endpoint = project_endpoint or os.getenv("AZURE_AI_PROJECT_ENDPOINT", "")
        self.subscription_id = os.getenv("SUBSCRIPTION_ID", "")
        self.resource_group = os.getenv("RESOURCE_GROUP_NAME", "")

        # Default SRE agent instructions
        self.instructions = instructions or """
You are an Azure SRE agent. Diagnose and resolve Azure infrastructure issues using the provided tools.
Always confirm before executing any remediation (restart, scale, clear_cache).
Provide concise, tool-driven answers. For operational requests prefer tool results over portal guidance.
"""

        # Slim instructions used when the caller requests a narrower context window
        self._slim_instructions = (
            "You are an Azure SRE agent. Use the provided tools to diagnose and resolve "
            "Azure infrastructure issues. Execute tools first; synthesise results into a "
            "clear, concise response. Confirm before any destructive action."
        )

        # Client state (uses singleton pattern for connection pooling)
        self.credential = None
        self.ai_client = None
        self.agents_client = None
        self.agent = None
        self.thread = None  # Legacy: kept for backward compat

        # Session management: workflow_id → thread_id mapping
        self._thread_map: Dict[str, str] = {}
        self._thread_map_lock = asyncio.Lock()

        # AgentContextStore reference (lazy-loaded)
        self._context_store = None
        self._context_store_initialized = False

        # Response cache
        self._response_cache = AgentResponseCache(
            ttl_seconds=self.perf_config.cache_ttl_seconds,
            max_entries=self.perf_config.cache_max_entries,
        )

        # Metrics
        self.metrics = AgentMetrics()

        # Initialize Azure clients
        if AZURE_AI_AGENTS_AVAILABLE:
            try:
                self.credential = DefaultAzureCredential()
                if self.project_endpoint:
                    self.ai_client, self.agents_client = _get_ai_client_singleton(
                        self.project_endpoint, self.credential,
                    )
                    logger.info("Azure AI SRE Agent '%s' initialized (pool=singleton)", agent_name)
                else:
                    logger.warning("AZURE_AI_PROJECT_ENDPOINT not configured")
            except Exception as e:
                logger.error("Failed to initialize Azure AI SRE Agent: %s", e)
                self.credential = None
                self.ai_client = None
                self.agents_client = None

    # ------------------------------------------------------------------
    # Context store integration (lazy init)
    # ------------------------------------------------------------------

    async def _get_context_store(self):
        """Lazy-load AgentContextStore singleton."""
        if self._context_store_initialized:
            return self._context_store
        try:
            try:
                from utils.agent_context_store import get_context_store
            except ImportError:
                from app.agentic.eol.utils.agent_context_store import get_context_store
            self._context_store = await get_context_store()
            self._context_store_initialized = True
            logger.debug("AgentContextStore loaded for thread management")
        except Exception as e:
            logger.debug("AgentContextStore unavailable, using in-memory thread map: %s", e)
            self._context_store = None
            self._context_store_initialized = True
        return self._context_store

    # ------------------------------------------------------------------
    # Availability check
    # ------------------------------------------------------------------

    async def is_available(self) -> bool:
        """Check if Azure AI Agent Service is properly configured and reachable."""
        if not AZURE_AI_AGENTS_AVAILABLE:
            logger.debug("Azure AI Agent Service dependencies not installed")
            return False

        is_configured = bool(
            self.agents_client
            and self.credential
            and self.project_endpoint
        )

        if not is_configured:
            logger.debug("Azure AI Agent Service not fully configured "
                         "(need AZURE_AI_PROJECT_ENDPOINT + credentials)")

        return is_configured

    # ------------------------------------------------------------------
    # Azure SDK compatibility helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_attr_path(obj: Any, attr_path: str) -> Optional[Any]:
        current = obj
        for part in attr_path.split("."):
            if current is None or not hasattr(current, part):
                return None
            current = getattr(current, part)
        return current

    @staticmethod
    def _filter_kwargs(func: Any, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        try:
            signature = inspect.signature(func)
            accepted = {
                name for name, param in signature.parameters.items()
                if param.kind in (param.POSITIONAL_OR_KEYWORD, param.KEYWORD_ONLY)
            }
            if any(param.kind == param.VAR_KEYWORD for param in signature.parameters.values()):
                return kwargs
            return {key: value for key, value in kwargs.items() if key in accepted}
        except Exception:
            return kwargs

    def _invoke_agents_method(
        self,
        candidate_paths: List[str],
        **kwargs: Any,
    ) -> Any:
        if not self.agents_client:
            raise RuntimeError("Agents client not initialized")

        last_error: Optional[Exception] = None
        for path in candidate_paths:
            method = self._resolve_attr_path(self.agents_client, path)
            if not callable(method):
                continue

            try:
                return method(**self._filter_kwargs(method, kwargs))
            except TypeError as exc:
                last_error = exc
                continue
            except Exception as exc:
                last_error = exc
                continue

        available = []
        try:
            available = [name for name in dir(self.agents_client) if not name.startswith("_")][:40]
        except Exception:
            pass
        raise RuntimeError(
            f"No compatible Azure AI Agents method found for {candidate_paths}; "
            f"available sample={available}. last_error={last_error}"
        )

    @staticmethod
    def _normalize_agent_id(agent_id: str) -> str:
        marker = "/providers/Microsoft.App/agents/"
        if marker in agent_id:
            return agent_id.split(marker, 1)[1].strip("/")
        return agent_id

    def get_agent(self, agent_id: str) -> Any:
        normalized_id = self._normalize_agent_id(agent_id)
        if not self.agents_client:
            raise RuntimeError("Agents client not initialized")

        # Runtime SDKs may require assistant IDs (e.g. asst_*) and reject names/ARM IDs.
        # For non-assistant identifiers, resolve via list first.
        if not normalized_id.startswith("asst"):
            try:
                list_result = self._invoke_agents_method(["list_agents", "list", "agents.list"])
                candidates = list(list_result) if list_result is not None else []

                # Exact name match (preferred for configured agent names)
                for candidate in candidates:
                    if getattr(candidate, "name", None) == normalized_id:
                        return candidate

                # Fallback ID match (in case caller already provided assistant ID without prefix check)
                for candidate in candidates:
                    if getattr(candidate, "id", None) == normalized_id:
                        return candidate
            except Exception as exc:
                logger.debug("Agent list-based resolution failed for %s: %s", normalized_id, exc)

        candidate_paths = ["get_agent", "agents.get", "get"]
        variants = [
            {"agent_name": normalized_id},
            {"name": normalized_id},
            {"id": normalized_id},
            {"agent_id": normalized_id},
        ]

        last_error: Optional[Exception] = None
        for path in candidate_paths:
            method = self._resolve_attr_path(self.agents_client, path)
            if not callable(method):
                continue

            for variant in variants:
                try:
                    return method(**self._filter_kwargs(method, variant))
                except Exception as exc:
                    last_error = exc

            # Some SDK surfaces accept positional identifier only
            try:
                return method(normalized_id)
            except Exception as exc:
                last_error = exc

        available = []
        try:
            available = [name for name in dir(self.agents_client) if not name.startswith("_")][:40]
        except Exception:
            pass
        raise RuntimeError(
            f"No compatible Azure AI Agents method found for {candidate_paths}; "
            f"available sample={available}. last_error={last_error}"
        )

    def create_thread_sdk(self) -> Any:
        return self._invoke_agents_method(
            ["create_thread", "threads.create", "create_agent_thread", "conversations.create_thread"]
        )

    def create_agent_sdk(self, **kwargs: Any) -> Any:
        if not self.agents_client:
            raise RuntimeError("Agents client not initialized")

        candidate_paths = ["create_agent", "agents.create", "create"]
        definition_payload = {
            key: value
            for key, value in kwargs.items()
            if value is not None and key in {
                "name",
                "model",
                "instructions",
                "tools",
                "description",
                "temperature",
                "top_p",
                "metadata",
                "response_format",
            }
        }

        last_error: Optional[Exception] = None
        for path in candidate_paths:
            method = self._resolve_attr_path(self.agents_client, path)
            if not callable(method):
                continue

            variants: List[Dict[str, Any]] = [kwargs]
            if definition_payload:
                variants.append({"definition": definition_payload})

            for variant in variants:
                try:
                    return method(**self._filter_kwargs(method, variant))
                except Exception as exc:
                    last_error = exc

            if definition_payload:
                try:
                    return method(definition_payload)
                except Exception as exc:
                    last_error = exc

        available = []
        try:
            available = [name for name in dir(self.agents_client) if not name.startswith("_")][:40]
        except Exception:
            pass
        raise RuntimeError(
            f"No compatible Azure AI Agents method found for {candidate_paths}; "
            f"available sample={available}. last_error={last_error}"
        )

    def delete_agent_sdk(self, agent_id: str) -> Any:
        normalized_id = self._normalize_agent_id(agent_id)
        if not self.agents_client:
            raise RuntimeError("Agents client not initialized")

        candidate_paths = ["delete_agent", "agents.delete", "delete"]
        variants = [
            {"agent_name": normalized_id},
            {"name": normalized_id},
            {"id": normalized_id},
            {"agent_id": normalized_id},
        ]

        last_error: Optional[Exception] = None
        for path in candidate_paths:
            method = self._resolve_attr_path(self.agents_client, path)
            if not callable(method):
                continue

            for variant in variants:
                try:
                    return method(**self._filter_kwargs(method, variant))
                except Exception as exc:
                    last_error = exc

            try:
                return method(normalized_id)
            except Exception as exc:
                last_error = exc

        raise RuntimeError(
            f"No compatible delete method found for {candidate_paths}. last_error={last_error}"
        )

    def create_message_sdk(self, **kwargs: Any) -> Any:
        return self._invoke_agents_method(
            ["create_message", "messages.create", "threads.messages.create"],
            **kwargs,
        )

    def create_run_sdk(self, **kwargs: Any) -> Any:
        return self._invoke_agents_method(
            ["create_run", "runs.create", "threads.runs.create"],
            **kwargs,
        )

    def get_run_sdk(self, **kwargs: Any) -> Any:
        return self._invoke_agents_method(
            ["get_run", "runs.get", "threads.runs.get"],
            **kwargs,
        )

    def list_messages_sdk(self, **kwargs: Any) -> Any:
        return self._invoke_agents_method(
            ["list_messages", "messages.list", "threads.messages.list"],
            **kwargs,
        )

    def submit_tool_outputs_sdk(self, **kwargs: Any) -> Any:
        return self._invoke_agents_method(
            ["submit_tool_outputs", "runs.submit_tool_outputs", "threads.runs.submit_tool_outputs"],
            **kwargs,
        )

    # ------------------------------------------------------------------
    # Thread / session management
    # ------------------------------------------------------------------

    async def get_or_create_thread(self, workflow_id: str) -> Optional[str]:
        """
        Get existing thread for a workflow or create a new one.

        Thread IDs are persisted in AgentContextStore (24h TTL) when available,
        with an in-memory fallback. This enables conversation continuity across
        multiple requests within the same workflow.

        Args:
            workflow_id: Unique workflow identifier

        Returns:
            Thread ID string, or None on failure
        """
        if not await self.is_available():
            return None

        async with self._thread_map_lock:
            # Check in-memory map first (L1)
            if workflow_id in self._thread_map:
                self.metrics.record_thread_event(created=False)
                logger.debug("Thread reuse (memory) for workflow=%s", workflow_id[:12])
                return self._thread_map[workflow_id]

            # Check AgentContextStore (L2)
            ctx_store = await self._get_context_store()
            if ctx_store:
                try:
                    stored_thread_id = await ctx_store.get_context_value(
                        workflow_id, "sre_agent_thread_id",
                    )
                    if stored_thread_id:
                        self._thread_map[workflow_id] = stored_thread_id
                        self.metrics.record_thread_event(created=False)
                        logger.debug("Thread reuse (context store) for workflow=%s", workflow_id[:12])
                        return stored_thread_id
                except Exception as e:
                    logger.debug("Context store lookup failed: %s", e)

            # Create new thread
            try:
                new_thread = self.create_thread_sdk()
                thread_id = new_thread.id
                self._thread_map[workflow_id] = thread_id

                # Persist to context store
                if ctx_store:
                    try:
                        # Ensure workflow context exists
                        existing = await ctx_store.get_workflow_context(workflow_id)
                        if not existing:
                            await ctx_store.create_workflow_context(
                                workflow_id=workflow_id,
                                initial_data={"sre_agent_thread_id": thread_id},
                                ttl=self.perf_config.thread_ttl_seconds,
                            )
                        else:
                            await ctx_store.set_context_value(
                                workflow_id, "sre_agent_thread_id", thread_id,
                            )
                    except Exception as e:
                        logger.debug("Failed to persist thread to context store: %s", e)

                self.metrics.record_thread_event(created=True)
                logger.info("Created thread %s for workflow=%s", thread_id, workflow_id[:12])
                return thread_id

            except Exception as e:
                logger.error("Failed to create thread for workflow=%s: %s", workflow_id[:12], e)
                return None

    async def delete_thread(self, workflow_id: str) -> bool:
        """
        Delete thread context for a workflow.

        Args:
            workflow_id: Workflow whose thread should be cleared

        Returns:
            True if successfully cleaned up
        """
        async with self._thread_map_lock:
            self._thread_map.pop(workflow_id, None)

        ctx_store = await self._get_context_store()
        if ctx_store:
            try:
                await ctx_store.delete_workflow_context(workflow_id)
            except Exception as e:
                logger.debug("Failed to delete workflow context: %s", e)

        return True

    # ------------------------------------------------------------------
    # Agent lifecycle
    # ------------------------------------------------------------------

    async def create_agent(
        self,
        model: str = "gpt-4o",
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> Optional[Any]:
        """
        Create a new Azure AI Agent instance.

        Args:
            model: Model deployment name (default: gpt-4o)
            tools: Tool definitions (uses SRE tools if not provided)

        Returns:
            Agent instance or None if creation fails
        """
        if not await self.is_available():
            logger.error("Azure AI Agent Service not available")
            return None

        try:
            self.agent = self.create_agent_sdk(
                model=model,
                name=self.agent_name,
                instructions=self.instructions,
                tools=tools or self._get_sre_tools(),
            )
            logger.info("Created Azure AI Agent: %s", self.agent.id)
            return self.agent
        except Exception as e:
            logger.error("Failed to create Azure AI Agent: %s", e)
            return None

    async def create_thread(self) -> Optional[Any]:
        """
        Create a new conversation thread (legacy interface).

        For session-aware usage, prefer get_or_create_thread(workflow_id).

        Returns:
            AgentThread instance or None
        """
        if not await self.is_available():
            return None

        try:
            self.thread = self.create_thread_sdk()
            logger.info("Created conversation thread: %s", self.thread.id)
            return self.thread
        except Exception as e:
            logger.error("Failed to create thread: %s", e)
            return None

    async def delete_agent(self, agent_id: Optional[str] = None) -> None:
        """Delete the agent instance."""
        if not await self.is_available():
            return

        try:
            target_id = agent_id or (self.agent.id if self.agent else None)
            if target_id:
                self.delete_agent_sdk(agent_id=target_id)
                logger.info("Deleted agent: %s", target_id)
                self.agent = None
        except Exception as e:
            logger.error("Failed to delete agent: %s", e)

    # ------------------------------------------------------------------
    # Core chat with timeout, caching, metrics
    # ------------------------------------------------------------------

    async def chat(
        self,
        thread_id: str,
        message: str,
        context: Optional[Dict[str, Any]] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_subset: Optional[List[Dict[str, Any]]] = None,
        slim_prompt: bool = False,
        timeout: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Send a message to the agent and get a response.

        Integrates response caching, configurable timeouts, and metrics tracking.

        Args:
            thread_id: Conversation thread ID
            message: User message content
            context: Optional context dict (resource info, workflow state, etc.)
            tools: Optional tool overrides for this turn
            tool_subset: Compact domain-specific tool list (takes priority over tools).
                         Passed by SREOrchestratorAgent to reduce prompt token cost.
            slim_prompt: When True, use the condensed 3-sentence system instructions
                         instead of the full instructions text.
            timeout: Override total timeout (defaults to perf_config.total_timeout)

        Returns:
            Response dict with keys:
            - content: str (agent text response)
            - thread_id: str
            - run_id: str
            - status: str
            - tool_calls: list (if agent requested tool execution)
            - token_usage: dict (prompt, completion, total)
            - latency_ms: float
            - cached: bool
        """
        effective_timeout = timeout or self.perf_config.total_timeout
        # tool_subset takes priority over tools
        effective_tools = tool_subset or tools
        start_time = time.time()

        # Check response cache (L1)
        if self.perf_config.enable_response_cache:
            cached = self._response_cache.get(message, context)
            if cached is not None:
                latency = (time.time() - start_time) * 1000
                self.metrics.record_call(success=True, latency_ms=latency,
                                         source="agent", cached=True)
                return {**cached, "cached": True, "latency_ms": round(latency, 1)}

        # Execute with timeout
        try:
            result = await asyncio.wait_for(
                self._chat_inner(thread_id, message, context, effective_tools, slim_prompt),
                timeout=effective_timeout,
            )
        except asyncio.TimeoutError:
            latency = (time.time() - start_time) * 1000
            self.metrics.record_timeout()
            self.metrics.record_call(success=False, latency_ms=latency, source="agent")
            logger.warning("Agent chat timed out after %ds for thread=%s",
                           effective_timeout, thread_id)
            return {
                "error": f"Agent response timed out after {effective_timeout}s",
                "thread_id": thread_id,
                "status": "timeout",
                "cached": False,
                "latency_ms": round(latency, 1),
            }
        except Exception as e:
            latency = (time.time() - start_time) * 1000
            self.metrics.record_call(success=False, latency_ms=latency, source="agent")
            logger.error("Agent chat error for thread=%s: %s", thread_id, e, exc_info=True)
            return {
                "error": str(e),
                "thread_id": thread_id,
                "status": "error",
                "cached": False,
                "latency_ms": round(latency, 1),
            }

        # Record metrics
        latency = (time.time() - start_time) * 1000
        result["latency_ms"] = round(latency, 1)
        result["cached"] = False
        has_error = "error" in result
        self.metrics.record_call(success=not has_error, latency_ms=latency, source="agent")

        # Track token usage from result
        token_usage = result.get("token_usage", {})
        if token_usage:
            self.metrics.record_token_usage(
                prompt=token_usage.get("prompt", 0),
                completion=token_usage.get("completion", 0),
            )

        # Cache successful non-error responses
        if not has_error and self.perf_config.enable_response_cache:
            self._response_cache.set(message, context, result)

        return result

    async def _chat_inner(
        self,
        thread_id: str,
        message: str,
        context: Optional[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]],
        slim_prompt: bool = False,
    ) -> Dict[str, Any]:
        """
        Inner chat implementation without timeout or caching wrappers.

        Returns structured response dict.
        """
        if not await self.is_available():
            return {"error": "Azure AI Agent Service not available"}

        if not self.agent:
            return {"error": "Agent not created. Call create_agent() first"}

        # Use slim instructions when requested to reduce prompt token cost
        if slim_prompt and self.agent:
            try:
                # Temporarily update agent instructions for this run (best-effort)
                effective_instructions = self._slim_instructions
            except Exception:
                effective_instructions = self.instructions
        else:
            effective_instructions = self.instructions  # noqa: F841 (kept for future use)

        # Build message content with optional context
        full_message = message
        if context:
            ctx_summary = json.dumps(context, indent=2, default=str)
            full_message = f"{message}\n\n[Context]\n{ctx_summary}"

        # Create message in thread
        message_obj = self.create_message_sdk(
            thread_id=thread_id,
            role="user",
            content=full_message,
        )

        # Start agent run
        run_kwargs: Dict[str, Any] = {
            "thread_id": thread_id,
            "agent_id": self.agent.id,
        }
        if tools:
            run_kwargs["tools"] = tools

        run = self.create_run_sdk(**run_kwargs)

        # Poll for completion with sleep backoff
        poll_interval = 0.5
        while run.status in ("queued", "in_progress", "requires_action"):
            # Handle tool call requests from the agent
            if run.status == "requires_action":
                tool_calls = self._extract_tool_calls(run)
                if tool_calls:
                    return {
                        "tool_calls": tool_calls,
                        "thread_id": thread_id,
                        "run_id": run.id,
                        "status": "requires_tool_execution",
                        "token_usage": self._extract_token_usage(run),
                    }

            await asyncio.sleep(poll_interval)
            poll_interval = min(poll_interval * 1.2, 3.0)  # Backoff capped at 3s
            run = self.get_run_sdk(thread_id=thread_id, run_id=run.id)

        # Handle terminal states
        if run.status == "failed":
            error_msg = getattr(run, "last_error", None)
            return {
                "error": f"Agent run failed: {error_msg or 'unknown error'}",
                "thread_id": thread_id,
                "run_id": run.id,
                "status": "failed",
                "token_usage": self._extract_token_usage(run),
            }

        # Extract assistant response
        messages = self.list_messages_sdk(thread_id=thread_id)
        message_items = list(messages)
        assistant_msgs = [
            msg for msg in message_items
            if self._is_assistant_message(msg) and msg.created_at > message_obj.created_at
        ]

        if assistant_msgs:
            content = assistant_msgs[0].content[0].text.value
            return {
                "content": content,
                "thread_id": thread_id,
                "run_id": run.id,
                "status": run.status,
                "token_usage": self._extract_token_usage(run),
            }

        return {
            "error": "No response from agent",
            "thread_id": thread_id,
            "run_id": run.id,
            "status": run.status,
            "token_usage": self._extract_token_usage(run),
        }

    # ------------------------------------------------------------------
    # Streaming support
    # ------------------------------------------------------------------

    async def chat_streaming(
        self,
        thread_id: str,
        message: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Stream agent response token-by-token for SSE delivery.

        Yields dicts with:
        - type: "token" | "tool_call" | "status" | "done" | "error"
        - content: str (token text or status message)
        - metadata: dict (optional additional info)

        Args:
            thread_id: Conversation thread ID
            message: User message
            context: Optional context dict
        """
        if not self.perf_config.enable_streaming:
            # Fall back to non-streaming
            result = await self.chat(thread_id, message, context)
            yield {"type": "done", "content": result.get("content", ""),
                   "metadata": result}
            return

        self.metrics.record_streaming_session()
        start_time = time.time()

        if not await self.is_available() or not self.agent:
            yield {"type": "error", "content": "Agent not available"}
            return

        try:
            # Build message
            full_message = message
            if context:
                ctx_summary = json.dumps(context, indent=2, default=str)
                full_message = f"{message}\n\n[Context]\n{ctx_summary}"

            # Create message
            self.create_message_sdk(
                thread_id=thread_id,
                role="user",
                content=full_message,
            )

            yield {"type": "status", "content": "Agent is thinking..."}

            # Create run with streaming if SDK supports it
            run = self.create_run_sdk(
                thread_id=thread_id,
                agent_id=self.agent.id,
            )

            # Poll and yield status updates
            poll_interval = 0.5
            last_status = ""
            while run.status in ("queued", "in_progress", "requires_action"):
                if run.status != last_status:
                    last_status = run.status
                    if run.status == "requires_action":
                        tool_calls = self._extract_tool_calls(run)
                        for tc in (tool_calls or []):
                            yield {"type": "tool_call",
                                   "content": f"Executing: {tc.get('name', 'unknown')}",
                                   "metadata": tc}

                await asyncio.sleep(poll_interval)
                poll_interval = min(poll_interval * 1.2, 3.0)
                run = self.get_run_sdk(thread_id=thread_id, run_id=run.id)

            # Get final response
            if run.status == "completed":
                messages = self.list_messages_sdk(thread_id=thread_id)
                message_items = list(messages)
                assistant_msgs = [
                    msg for msg in message_items
                    if self._is_assistant_message(msg)
                ]
                if assistant_msgs:
                    full_text = assistant_msgs[0].content[0].text.value
                    # Simulate token streaming by chunking the response
                    chunk_size = 20  # characters per chunk
                    for i in range(0, len(full_text), chunk_size):
                        chunk = full_text[i:i + chunk_size]
                        yield {"type": "token", "content": chunk}
                        await asyncio.sleep(0.02)  # Small delay for SSE pacing

            latency_ms = (time.time() - start_time) * 1000
            yield {
                "type": "done",
                "content": "",
                "metadata": {
                    "thread_id": thread_id,
                    "run_id": run.id,
                    "status": run.status,
                    "latency_ms": round(latency_ms, 1),
                    "token_usage": self._extract_token_usage(run),
                },
            }

        except asyncio.TimeoutError:
            self.metrics.record_timeout()
            yield {"type": "error", "content": "Agent response timed out"}
        except Exception as e:
            logger.error("Streaming error for thread=%s: %s", thread_id, e, exc_info=True)
            yield {"type": "error", "content": str(e)}

    # ------------------------------------------------------------------
    # Parallel tool execution
    # ------------------------------------------------------------------

    async def execute_tool_calls_parallel(
        self,
        tool_calls: List[Dict[str, Any]],
        executor_fn,
        workflow_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Execute multiple tool calls in parallel via asyncio.gather().

        Args:
            tool_calls: List of tool call dicts from agent (name, arguments)
            executor_fn: Async callable(tool_name, arguments) -> result dict
            workflow_id: Optional workflow ID for auditing

        Returns:
            List of result dicts in the same order as tool_calls
        """
        if not tool_calls:
            return []

        limit = self.perf_config.parallel_tool_limit
        tool_timeout = self.perf_config.tool_call_timeout
        is_parallel = len(tool_calls) > 1

        async def _execute_one(tc: Dict[str, Any]) -> Dict[str, Any]:
            tool_name = tc.get("name", "unknown")
            arguments = tc.get("arguments", {})
            start = time.time()
            try:
                result = await asyncio.wait_for(
                    executor_fn(tool_name, arguments),
                    timeout=tool_timeout,
                )
                latency = (time.time() - start) * 1000
                self.metrics.record_tool_call(tool_name, latency, parallel=is_parallel)
                return {
                    "tool_call_id": tc.get("id", ""),
                    "name": tool_name,
                    "result": result,
                    "success": True,
                    "latency_ms": round(latency, 1),
                }
            except asyncio.TimeoutError:
                latency = (time.time() - start) * 1000
                self.metrics.record_tool_call(tool_name, latency, parallel=is_parallel)
                logger.warning("Tool %s timed out after %ds", tool_name, tool_timeout)
                return {
                    "tool_call_id": tc.get("id", ""),
                    "name": tool_name,
                    "result": {"error": f"Tool timed out after {tool_timeout}s"},
                    "success": False,
                    "latency_ms": round(latency, 1),
                }
            except Exception as e:
                latency = (time.time() - start) * 1000
                self.metrics.record_tool_call(tool_name, latency, parallel=is_parallel)
                logger.error("Tool %s execution failed: %s", tool_name, e)
                return {
                    "tool_call_id": tc.get("id", ""),
                    "name": tool_name,
                    "result": {"error": str(e)},
                    "success": False,
                    "latency_ms": round(latency, 1),
                }

        # Execute in batches of parallel_tool_limit
        results: List[Dict[str, Any]] = []
        for i in range(0, len(tool_calls), limit):
            batch = tool_calls[i:i + limit]
            batch_results = await asyncio.gather(
                *[_execute_one(tc) for tc in batch],
                return_exceptions=False,
            )
            results.extend(batch_results)

        return results

    # ------------------------------------------------------------------
    # Submit tool results back to agent
    # ------------------------------------------------------------------

    async def submit_tool_results(
        self,
        thread_id: str,
        run_id: str,
        tool_results: List[Dict[str, Any]],
        timeout: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Submit tool execution results back to the agent for synthesis.

        After the agent requests tool calls and they are executed (possibly in parallel),
        this method sends the results back and gets the agent's final synthesized response.

        Args:
            thread_id: Conversation thread ID
            run_id: The run ID that requested the tool calls
            tool_results: List of tool result dicts (tool_call_id, result)
            timeout: Override total timeout

        Returns:
            Final agent response dict
        """
        effective_timeout = timeout or self.perf_config.total_timeout
        start_time = time.time()

        try:
            # Format tool outputs for the Azure AI SDK
            tool_outputs = []
            for tr in tool_results:
                output_str = json.dumps(tr.get("result", {}), default=str)
                tool_outputs.append({
                    "tool_call_id": tr.get("tool_call_id", ""),
                    "output": output_str,
                })

            # Submit tool outputs
            run = self.submit_tool_outputs_sdk(
                thread_id=thread_id,
                run_id=run_id,
                tool_outputs=tool_outputs,
            )

            # Poll for completion
            poll_interval = 0.5
            while run.status in ("queued", "in_progress"):
                await asyncio.sleep(poll_interval)
                poll_interval = min(poll_interval * 1.2, 3.0)
                run = self.get_run_sdk(thread_id=thread_id, run_id=run.id)

                elapsed = time.time() - start_time
                if elapsed > effective_timeout:
                    self.metrics.record_timeout()
                    return {
                        "error": f"Tool result synthesis timed out after {effective_timeout}s",
                        "thread_id": thread_id,
                        "run_id": run_id,
                        "status": "timeout",
                    }

            # Extract final response
            if run.status == "completed":
                messages = self.list_messages_sdk(thread_id=thread_id)
                message_items = list(messages)
                assistant_msgs = [
                    msg for msg in message_items
                    if self._is_assistant_message(msg)
                ]
                if assistant_msgs:
                    content = assistant_msgs[0].content[0].text.value
                    latency_ms = (time.time() - start_time) * 1000
                    return {
                        "content": content,
                        "thread_id": thread_id,
                        "run_id": run.id,
                        "status": run.status,
                        "token_usage": self._extract_token_usage(run),
                        "latency_ms": round(latency_ms, 1),
                    }

            return {
                "error": f"Agent run ended with status: {run.status}",
                "thread_id": thread_id,
                "run_id": run.id,
                "status": run.status,
            }

        except Exception as e:
            logger.error("Failed to submit tool results: %s", e, exc_info=True)
            return {
                "error": str(e),
                "thread_id": thread_id,
                "run_id": run_id,
                "status": "error",
            }

    # ------------------------------------------------------------------
    # Legacy send_message (backward compatibility)
    # ------------------------------------------------------------------

    async def send_message(
        self,
        message: str,
        thread_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Send a message to the agent and get response (legacy interface).

        For new code, prefer chat() with explicit thread_id.

        Args:
            message: User message content
            thread_id: Thread ID (optional, uses/creates current thread)

        Returns:
            Response dictionary with agent's reply
        """
        if not await self.is_available():
            return {"error": "Azure AI Agent Service not available"}

        if not self.agent:
            return {"error": "Agent not created. Call create_agent() first"}

        # Resolve thread
        target_thread = thread_id or (self.thread.id if self.thread else None)
        if not target_thread:
            await self.create_thread()
            target_thread = self.thread.id

        # Delegate to chat()
        result = await self.chat(
            thread_id=target_thread,
            message=message,
        )

        # Map to legacy response format
        if "error" in result:
            return result
        return {
            "response": result.get("content", ""),
            "thread_id": result.get("thread_id", target_thread),
            "run_id": result.get("run_id", ""),
            "status": result.get("status", ""),
        }

    # ------------------------------------------------------------------
    # Diagnostics
    # ------------------------------------------------------------------

    def get_diagnostics(self) -> Dict[str, Any]:
        """
        Get comprehensive agent diagnostics including cache, metrics, and config.

        Returns:
            Dict with cache_stats, metrics, config, and connection info
        """
        return {
            "agent_name": self.agent_name,
            "agent_id": self.agent.id if self.agent else None,
            "project_endpoint": self.project_endpoint[:40] + "..." if self.project_endpoint else None,
            "is_sdk_available": AZURE_AI_AGENTS_AVAILABLE,
            "is_configured": bool(self.agents_client and self.credential and self.project_endpoint),
            "active_threads": len(self._thread_map),
            "performance_config": {
                "tool_call_timeout": self.perf_config.tool_call_timeout,
                "total_timeout": self.perf_config.total_timeout,
                "parallel_tool_limit": self.perf_config.parallel_tool_limit,
                "cache_enabled": self.perf_config.enable_response_cache,
                "cache_ttl_seconds": self.perf_config.cache_ttl_seconds,
                "streaming_enabled": self.perf_config.enable_streaming,
            },
            "cache_stats": self._response_cache.get_stats(),
            "metrics": self.metrics.get_stats(),
        }

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_tool_calls(run) -> Optional[List[Dict[str, Any]]]:
        """Extract tool call requests from a run that requires action."""
        try:
            required_action = getattr(run, "required_action", None)
            if not required_action:
                return None
            submit_outputs = getattr(required_action, "submit_tool_outputs", None)
            if not submit_outputs:
                return None
            tool_calls = getattr(submit_outputs, "tool_calls", [])
            return [
                {
                    "id": tc.id,
                    "name": tc.function.name,
                    "arguments": json.loads(tc.function.arguments) if tc.function.arguments else {},
                }
                for tc in tool_calls
            ]
        except Exception as e:
            logger.debug("Failed to extract tool calls: %s", e)
            return None

    @staticmethod
    def _extract_token_usage(run) -> Dict[str, int]:
        """Extract token usage from a completed run."""
        try:
            usage = getattr(run, "usage", None)
            if usage:
                return {
                    "prompt": getattr(usage, "prompt_tokens", 0),
                    "completion": getattr(usage, "completion_tokens", 0),
                    "total": getattr(usage, "total_tokens", 0),
                }
        except Exception:
            pass
        return {"prompt": 0, "completion": 0, "total": 0}

    @staticmethod
    def _is_assistant_message(message_obj: Any) -> bool:
        """SDK-compatible assistant role check across enum/string variants."""
        role = getattr(message_obj, "role", None)
        if role is None:
            return False
        role_value = getattr(role, "value", role)
        role_text = str(role_value).strip().lower()
        return role_text in {"assistant", "agent"}

    # ------------------------------------------------------------------
    # Tool definitions
    # ------------------------------------------------------------------

    def _get_sre_tools(self) -> List[Dict[str, Any]]:
        """
        Get SRE tool definitions for Azure AI Agent Service.

        Dynamically imports tool definitions from the SRE MCP server when available,
        falling back to a comprehensive static definition list.

        Returns:
            List of tool definitions compatible with Azure AI Agents SDK
        """
        try:
            dynamic_tools = self._get_dynamic_sre_tools()
            if dynamic_tools:
                logger.info("Loaded %d SRE tools dynamically from MCP server",
                            len(dynamic_tools))
                return dynamic_tools
        except Exception as e:
            logger.debug("Dynamic tool import failed, using static definitions: %s", e)

        return self._get_static_sre_tools()

    def _get_dynamic_sre_tools(self) -> Optional[List[Dict[str, Any]]]:
        """Attempt to dynamically load tool definitions from the SRE MCP server."""
        try:
            try:
                from utils.sre_mcp_client import SREMCPClient
            except ImportError:
                from app.agentic.eol.utils.sre_mcp_client import SREMCPClient

            client = SREMCPClient()
            loop = asyncio.get_event_loop()
            if loop.is_running():
                logger.debug("Event loop already running, using static SRE tools")
                return None

            initialized = loop.run_until_complete(client.initialize())
            if initialized:
                tools = client.get_available_tools()
                loop.run_until_complete(client.cleanup())
                return tools
            return None
        except Exception as e:
            logger.debug("Failed to load dynamic SRE tools: %s", e)
            return None

    def _get_static_sre_tools(self) -> List[Dict[str, Any]]:
        """
        Get comprehensive static SRE tool definitions as fallback.

        Returns:
            List of tool definitions compatible with Azure AI Agents SDK
        """
        return [
            # === Resource Health & Diagnostics ===
            {
                "type": "function",
                "function": {
                    "name": "check_resource_health",
                    "description": "Check the health status of an Azure resource using Resource Health API",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "resource_id": {"type": "string", "description": "Full Azure resource ID"}
                        },
                        "required": ["resource_id"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "check_container_app_health",
                    "description": "Check Container App health via Log Analytics",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "workspace_id": {"type": "string", "description": "Log Analytics workspace ID"},
                            "resource_id": {"type": "string", "description": "Full Container App resource ID"}
                        },
                        "required": ["workspace_id", "resource_id"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_diagnostic_logs",
                    "description": "Retrieve diagnostic logs from Log Analytics",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "workspace_id": {"type": "string", "description": "Log Analytics workspace ID"},
                            "query": {"type": "string", "description": "KQL query"}
                        },
                        "required": ["workspace_id", "query"]
                    }
                }
            },
            # === Incident Response ===
            {
                "type": "function",
                "function": {
                    "name": "triage_incident",
                    "description": "Automated incident triage with health checks and severity assessment",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "resource_id": {"type": "string", "description": "Azure resource ID to investigate"},
                            "description": {"type": "string", "description": "Incident description"}
                        },
                        "required": ["resource_id"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "search_logs_by_error",
                    "description": "Search logs for specific error patterns",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "workspace_id": {"type": "string", "description": "Log Analytics workspace ID"},
                            "error_pattern": {"type": "string", "description": "Error pattern to search for"}
                        },
                        "required": ["workspace_id", "error_pattern"]
                    }
                }
            },
            # === Performance ===
            {
                "type": "function",
                "function": {
                    "name": "get_performance_metrics",
                    "description": "Query Azure Monitor metrics (CPU, memory, network) with auto-calculated time ranges",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "resource_id": {"type": "string", "description": "Azure resource ID"},
                            "metric_names": {"type": "string", "description": "Comma-separated metric names"}
                        },
                        "required": ["resource_id"]
                    }
                }
            },
            # === Remediation ===
            {
                "type": "function",
                "function": {
                    "name": "plan_remediation",
                    "description": "Generate step-by-step remediation plan with approval workflow",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "resource_id": {"type": "string", "description": "Azure resource ID"},
                            "issue_type": {"type": "string", "description": "Type of issue to remediate"}
                        },
                        "required": ["resource_id", "issue_type"]
                    }
                }
            },
            # === Cost Optimization ===
            {
                "type": "function",
                "function": {
                    "name": "get_cost_analysis",
                    "description": "Query Azure Cost Management for spending breakdown by resource group, service, or tag",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "scope": {"type": "string", "description": "Cost analysis scope (subscription or resource group)"},
                            "time_range": {"type": "string", "description": "Time range (e.g., 'last_7_days', 'last_30_days')"}
                        },
                        "required": ["scope"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "identify_orphaned_resources",
                    "description": "Find unused Azure resources (unattached disks, idle public IPs, empty NSGs)",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "subscription_id": {"type": "string", "description": "Azure subscription ID"}
                        },
                        "required": []
                    }
                }
            },
            # === SLO Management ===
            {
                "type": "function",
                "function": {
                    "name": "define_slo",
                    "description": "Define a service level objective (availability, latency, or error rate target)",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "service_name": {"type": "string", "description": "Name of the service"},
                            "sli_type": {"type": "string", "description": "SLI type: availability, latency, or error_rate"},
                            "target_percentage": {"type": "number", "description": "Target percentage (e.g., 99.9)"},
                            "window_days": {"type": "integer", "description": "SLO measurement window in days"}
                        },
                        "required": ["service_name", "sli_type", "target_percentage"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "calculate_error_budget",
                    "description": "Calculate remaining error budget based on SLI measurements vs SLO targets",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "service_name": {"type": "string", "description": "Name of the service"},
                            "slo_id": {"type": "string", "description": "SLO definition ID"}
                        },
                        "required": ["service_name"]
                    }
                }
            },
            # === Security & Compliance ===
            {
                "type": "function",
                "function": {
                    "name": "get_security_score",
                    "description": "Get Microsoft Defender for Cloud secure score with control-level breakdown",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "subscription_id": {"type": "string", "description": "Azure subscription ID"}
                        },
                        "required": []
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "check_compliance_status",
                    "description": "Check Azure Policy compliance for regulatory frameworks (CIS, NIST, PCI-DSS)",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "scope": {"type": "string", "description": "Compliance scope (subscription or resource group)"},
                            "policy_definition_name": {"type": "string", "description": "Policy initiative name"}
                        },
                        "required": ["scope"]
                    }
                }
            },
            # === Application Insights ===
            {
                "type": "function",
                "function": {
                    "name": "query_app_insights_traces",
                    "description": "Query Application Insights for distributed traces by operation ID",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "workspace_id": {"type": "string", "description": "Log Analytics workspace ID"},
                            "operation_id": {"type": "string", "description": "Operation/correlation ID to trace"}
                        },
                        "required": ["workspace_id", "operation_id"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_request_telemetry",
                    "description": "Get request performance telemetry (response times, failure rates, P95/P99 latencies)",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "workspace_id": {"type": "string", "description": "Log Analytics workspace ID"},
                            "app_name": {"type": "string", "description": "Application name"}
                        },
                        "required": ["workspace_id", "app_name"]
                    }
                }
            },
        ]


# ---------------------------------------------------------------------------
# Factory function (enhanced)
# ---------------------------------------------------------------------------

async def create_sre_agent(
    agent_name: str = "sre-agent",
    model: str = "gpt-4o",
    auto_create: bool = True,
    perf_config: Optional[AgentPerformanceConfig] = None,
) -> Optional[AzureAISREAgent]:
    """
    Factory function to create and initialize an Azure AI SRE Agent.

    Args:
        agent_name: Name for the agent
        model: Model deployment name
        auto_create: Automatically create agent and thread
        perf_config: Performance configuration (auto-loaded from env if None)

    Returns:
        Initialized AzureAISREAgent instance or None
    """
    agent = AzureAISREAgent(agent_name=agent_name, perf_config=perf_config)

    if not await agent.is_available():
        logger.warning("Azure AI Agent Service not available")
        return None

    if auto_create:
        await agent.create_agent(model=model)
        await agent.create_thread()

    return agent
