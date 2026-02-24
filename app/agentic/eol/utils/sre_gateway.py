"""SRE Gateway — fast intent classifier that routes to the correct SRE specialist.

Two-stage classification:
  1. Fast path: keyword substring matching (zero LLM cost, <1ms)
  2. Slow path: single gpt-4o-mini call only when ambiguous (~200 tokens)

The gateway returns an SREDomain enum value consumed by SREOrchestratorAgent
to select the correct specialist agent and its narrow tool subset.

Usage:
    gateway = SREGateway()
    domain = await gateway.classify("my container app is down")
    # → SREDomain.HEALTH
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List, Optional, Tuple

try:
    from app.agentic.eol.utils.sre_tool_registry import SREDomain
    from app.agentic.eol.utils.logger import get_logger
except ModuleNotFoundError:
    from utils.sre_tool_registry import SREDomain  # type: ignore[import-not-found]
    from utils.logger import get_logger  # type: ignore[import-not-found]

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Keyword patterns per SRE sub-domain (fast path)
# These are intentionally more specific than QueryPatterns.SRE_PATTERNS which
# only distinguishes SRE vs non-SRE. Here we distinguish sub-domains.
# ---------------------------------------------------------------------------

_DOMAIN_KEYWORDS: Dict[SREDomain, List[str]] = {
    SREDomain.HEALTH: [
        "health", "up", "down", "unavailable", "unhealthy", "degraded",
        "check health", "resource health", "container app health", "aks health",
        "app service health", "apim health", "is running", "status",
        "availability", "diagnose", "diagnostic", "ping", "reachable",
        "service down", "not responding", "503", "502", "504",
    ],
    SREDomain.INCIDENT: [
        "incident", "triage", "alert", "alarm", "outage", "error log",
        "log search", "log error", "search logs", "correlate", "alert correlation",
        "activity log", "incident summary", "incident report", "app insights trace",
        "request telemetry", "failed request", "audit trail", "event",
        "spike", "failure", "exception", "5xx", "4xx", "timeout",
    ],
    SREDomain.PERFORMANCE: [
        "performance", "slow", "latency", "p95", "p99", "response time",
        "throughput", "cpu", "memory", "bottleneck", "metric", "metrics",
        "utilization", "load", "request rate", "error rate", "anomaly",
        "baseline", "slo burn", "burn rate", "dependency map",
        "resource exhaustion", "capacity", "predict capacity",
    ],
    SREDomain.COST_SECURITY: [
        "cost", "spend", "spending", "budget", "billing", "price",
        "orphaned", "unused", "idle resource", "right-siz", "reserved",
        "cost optim", "cost anomal", "cost spike", "savings",
        "security score", "secure score", "security posture",
        "compliance status", "compliance check", "check compliance",
        "compliance report", "compliance",
        "cis", "nist", "pci", "azure policy", "defender", "vulnerability",
        "security recommend", "security finding",
    ],
    SREDomain.RCA: [
        "root cause", "rca", "why did", "cause of",
        "generate postmortem", "generate a postmortem", "postmortem", "post-mortem",
        "mttr", "calculate mttr", "dora", "mean time to",
        "trace dependency", "dependency chain",
        "log pattern", "analyze log", "predict capacity", "capacity issue",
        "what caused", "investigate the",
    ],
    SREDomain.REMEDIATION: [
        "restart", "redeploy", "scale", "fix it", "fix this", "resolve",
        "remediat", "remediation plan", "plan remediation", "execute",
        "clear cache", "flush cache", "rollback", "notify team",
        "teams notification", "alert team", "on-call", "page",
        "send alert", "send notification",
    ],
}

# Scoring weights: how much each keyword hit counts
_EXACT_PHRASE_WEIGHT = 3   # exact multi-word phrase match
_SINGLE_WORD_WEIGHT = 1    # single-word/prefix match


class SREGateway:
    """Cheap SRE intent classifier — keyword fast path + LLM fallback.

    The gateway itself has ZERO tools. Its only job is to classify the
    user's intent into one of the 6 SRE domains so the orchestrator
    can load only the relevant specialist and its narrow tool subset.
    """

    # Score threshold below which we consider classification ambiguous
    # and fall back to the LLM. Tune via SRE_GATEWAY_THRESHOLD env var.
    _AMBIGUITY_THRESHOLD: int = int(os.getenv("SRE_GATEWAY_THRESHOLD", "2"))

    def __init__(self) -> None:
        self._llm_fallback_enabled: bool = (
            os.getenv("SRE_GATEWAY_LLM_FALLBACK", "true").lower() == "true"
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def classify(self, query: str) -> SREDomain:
        """Classify user query into an SREDomain.

        Fast path: O(n) keyword scan, returns immediately when confident.
        Slow path: single gpt-4o-mini call (~200 tokens) when ambiguous.

        Returns SREDomain.GENERAL on complete failure (never raises).
        """
        domain, score = self._keyword_classify(query)

        if score >= self._AMBIGUITY_THRESHOLD:
            logger.debug(
                "🎯 SREGateway [fast]: query=%r → domain=%s (score=%d)",
                query[:80],
                domain.value,
                score,
            )
            return domain

        # Low confidence — try LLM fallback
        if self._llm_fallback_enabled:
            llm_domain = await self._llm_classify(query)
            if llm_domain is not None:
                logger.info(
                    "🎯 SREGateway [llm]: query=%r → domain=%s (keyword score=%d was ambiguous)",
                    query[:80],
                    llm_domain.value,
                    score,
                )
                return llm_domain

        # Return best keyword guess or GENERAL fallback
        result = domain if score > 0 else SREDomain.GENERAL
        logger.info(
            "🎯 SREGateway [fallback]: query=%r → domain=%s (score=%d)",
            query[:80],
            result.value,
            score,
        )
        return result

    def classify_sync(self, query: str) -> Tuple[SREDomain, int]:
        """Synchronous keyword-only classification. Returns (domain, score).

        Useful for unit tests and when async context is unavailable.
        """
        return self._keyword_classify(query)

    # ------------------------------------------------------------------
    # Fast path — keyword scoring
    # ------------------------------------------------------------------

    def _keyword_classify(self, query: str) -> Tuple[SREDomain, int]:
        """Score the query against each domain's keyword list.

        Returns (best_domain, best_score). When multiple domains tie,
        prefers in order: incident → health → performance → rca →
        cost_security → remediation → general.
        """
        q = query.lower()
        scores: Dict[SREDomain, int] = {d: 0 for d in SREDomain if d != SREDomain.GENERAL}

        for domain, keywords in _DOMAIN_KEYWORDS.items():
            if domain == SREDomain.GENERAL:
                continue
            for kw in keywords:
                if " " in kw:
                    # Multi-word: exact phrase match scores higher
                    if kw in q:
                        scores[domain] += _EXACT_PHRASE_WEIGHT
                else:
                    if kw in q:
                        scores[domain] += _SINGLE_WORD_WEIGHT

        if not scores or max(scores.values()) == 0:
            return SREDomain.GENERAL, 0

        best_domain = max(scores, key=lambda d: scores[d])
        best_score = scores[best_domain]
        return best_domain, best_score

    # ------------------------------------------------------------------
    # Slow path — LLM fallback (gpt-4o-mini, ~200 tokens)
    # ------------------------------------------------------------------

    _LLM_SYSTEM_PROMPT = (
        "You are an SRE intent classifier. Given a user query, respond with exactly ONE of "
        "these JSON values and nothing else:\n"
        '{"domain": "health"} — resource availability, diagnostics, service status\n'
        '{"domain": "incident"} — alerts, outages, log search, incident triage\n'
        '{"domain": "performance"} — metrics, latency, CPU/memory, bottlenecks\n'
        '{"domain": "cost_security"} — cost, billing, security score, compliance\n'
        '{"domain": "rca"} — root cause analysis, postmortems, dependency tracing\n'
        '{"domain": "remediation"} — restart, scale, fix, remediation plans\n'
        'When in doubt, use {"domain": "health"}.'
    )

    async def _llm_classify(self, query: str) -> Optional[SREDomain]:
        """Call gpt-4o-mini with a minimal prompt to classify the domain.

        Returns None if the LLM call fails or returns an unrecognised value.
        """
        try:
            from openai import AsyncAzureOpenAI  # type: ignore[import-not-found]

            endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
            api_key = os.getenv("AZURE_OPENAI_API_KEY")
            api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2024-08-01-preview")
            # Prefer mini model for cheap classification; fall back to default
            deployment = os.getenv(
                "AZURE_OPENAI_MINI_DEPLOYMENT",
                os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT_NAME", "gpt-4o-mini"),
            )

            if not endpoint or not api_key:
                logger.debug("SREGateway LLM fallback skipped — missing AZURE_OPENAI config")
                return None

            client = AsyncAzureOpenAI(
                api_key=api_key,
                azure_endpoint=endpoint,
                api_version=api_version,
            )
            try:
                resp = await client.chat.completions.create(
                    model=deployment,
                    messages=[
                        {"role": "system", "content": self._LLM_SYSTEM_PROMPT},
                        {"role": "user", "content": query},
                    ],
                    temperature=0.0,
                    max_tokens=20,
                )
                raw = resp.choices[0].message.content or ""
                data = json.loads(raw.strip())
                return SREDomain(data["domain"])
            finally:
                await client.close()

        except Exception as exc:
            logger.warning("SREGateway LLM fallback failed: %s", exc)
            return None
