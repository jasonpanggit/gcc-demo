"""Domain classifier for query-based routing.

Classifies user queries into operational domain labels to drive
routing decisions in the unified routing pipeline.

Design:
- Fast keyword-based classification (no LLM call, no embeddings)
- Returns primary domain, up to 2 secondary domains, and confidence
- General domain is the fallback when no keywords match

Usage:
    classifier = DomainClassifier()
    result = await classifier.classify("check VM health status")
    print(result.primary_domain)   # DomainLabel.COMPUTE
    print(result.confidence)        # 0.6
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional

try:
    from app.agentic.eol.utils.logger import get_logger
except ModuleNotFoundError:
    from utils.logger import get_logger  # type: ignore[import-not-found]

logger = get_logger(__name__)


class DomainLabel(str, Enum):
    """Supported domain labels for query classification."""
    SRE = "sre"
    MONITORING = "monitoring"
    NETWORK = "network"
    INVENTORY = "inventory"
    PATCH = "patch"
    COMPUTE = "compute"
    STORAGE = "storage"
    COST = "cost"
    SECURITY = "security"
    GENERAL = "general"


@dataclass
class DomainClassification:
    """Result of domain classification.

    Attributes:
        primary_domain: The most likely domain for this query.
        secondary_domains: Additional relevant domains (up to 2).
        confidence: Score 0.0–1.0 reflecting classification certainty.
        reasoning: Optional human-readable explanation.
    """
    primary_domain: DomainLabel
    secondary_domains: List[DomainLabel]
    confidence: float
    reasoning: Optional[str] = None


class DomainClassifier:
    """Classify user queries into domain labels for routing.

    Uses substring / keyword matching for speed — zero external calls.
    Normalises the query to lowercase before scoring so patterns are
    case-insensitive without requiring regex flags.

    Scoring:
    - +1 per keyword found in the query
    - Confidence = min(top_score / 5.0, 1.0) so 5+ matches → 1.0
    - No match → GENERAL with 0.5 confidence
    - Secondary domains: any domain with score >= 50% of top score

    Thread safety: instance is read-only after __init__, safe to share.
    """

    def __init__(self) -> None:
        self.keyword_patterns = self._build_keyword_patterns()

    # ----------------------------------------------------------------
    # Public API
    # ----------------------------------------------------------------

    async def classify(self, query: str) -> DomainClassification:
        """Classify a query into domain labels.

        Args:
            query: User's natural language query.

        Returns:
            DomainClassification with primary domain, secondaries, and confidence.
        """
        if not query or not query.strip():
            return DomainClassification(
                primary_domain=DomainLabel.GENERAL,
                secondary_domains=[],
                confidence=0.5,
                reasoning="Empty query — defaulting to GENERAL",
            )

        query_lower = query.lower()

        # Score each domain
        scores: Dict[DomainLabel, int] = {}
        for domain, keywords in self.keyword_patterns.items():
            score = sum(1 for kw in keywords if kw in query_lower)
            if score > 0:
                scores[domain] = score

        if not scores:
            logger.debug("DomainClassifier: no keyword match for query=%r → GENERAL", query[:80])
            return DomainClassification(
                primary_domain=DomainLabel.GENERAL,
                secondary_domains=[],
                confidence=0.5,
                reasoning="No domain keywords matched — defaulting to GENERAL",
            )

        # Sort descending by score
        sorted_domains = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        primary, top_score = sorted_domains[0]

        # Secondary: any other domain with score >= 50% of top score
        secondary = [
            d for d, s in sorted_domains[1:]
            if s >= top_score * 0.5
        ][:2]  # Cap at 2

        confidence = min(top_score / 5.0, 1.0)
        reasoning = (
            f"Matched {top_score} keyword(s) for {primary.value}"
            + (f"; secondary: {[d.value for d in secondary]}" if secondary else "")
        )

        logger.debug(
            "DomainClassifier: query=%r → primary=%s (score=%d, conf=%.2f)",
            query[:80],
            primary.value,
            top_score,
            confidence,
        )

        return DomainClassification(
            primary_domain=primary,
            secondary_domains=secondary,
            confidence=confidence,
            reasoning=reasoning,
        )

    # ----------------------------------------------------------------
    # Keyword patterns
    # ----------------------------------------------------------------

    def _build_keyword_patterns(self) -> Dict[DomainLabel, List[str]]:
        """Build keyword lists per domain for fast substring matching.

        Longer/more-specific phrases are listed before single words to
        allow the scorer to pick up multi-word hits before shorter ones.
        """
        return {
            DomainLabel.SRE: [
                "incident",
                "outage",
                "downtime",
                "site reliability",
                "sre",
                "health check",
                "availability",
                "on-call",
                "triage",
                "rca",
                "root cause",
            ],
            DomainLabel.MONITORING: [
                "alert",
                "metric",
                "monitor",
                "threshold",
                "logs",
                "log analysis",
                "dashboard",
                "observability",
                "telemetry",
                "alarm",
                "notification",
            ],
            DomainLabel.NETWORK: [
                "network",
                "nsg",
                "vnet",
                "subnet",
                "firewall",
                "connectivity",
                "routing",
                "peering",
                "vpn",
                "load balancer",
                "dns",
                "bandwidth",
                "latency",
            ],
            DomainLabel.INVENTORY: [
                "inventory",
                "resource",
                "list",
                "discover",
                "catalog",
                "enumerate",
                "asset",
                "count resources",
            ],
            DomainLabel.PATCH: [
                "patch",
                "update",
                "vulnerability",
                "compliance",
                "cve",
                "hotfix",
                "security update",
                "patch management",
                "pending updates",
            ],
            DomainLabel.COMPUTE: [
                "vm",
                "virtual machine",
                "compute",
                "scale",
                "restart",
                "cpu",
                "memory",
                "instance",
                "container",
                "kubernetes",
                "aks",
                "vmss",
            ],
            DomainLabel.STORAGE: [
                "storage",
                "blob",
                "disk",
                "file share",
                "backup",
                "snapshot",
                "container registry",
                "data lake",
            ],
            DomainLabel.COST: [
                "cost",
                "billing",
                "expense",
                "budget",
                "spend",
                "invoice",
                "pricing",
                "reservation",
                "saving",
            ],
            DomainLabel.SECURITY: [
                "security",
                "audit",
                "policy",
                "rbac",
                "access control",
                "permission",
                "defender",
                "threat",
                "identity",
                "zero trust",
                "encryption",
            ],
        }


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_classifier_instance: Optional[DomainClassifier] = None


def get_domain_classifier() -> DomainClassifier:
    """Return the module-level DomainClassifier singleton."""
    global _classifier_instance
    if _classifier_instance is None:
        _classifier_instance = DomainClassifier()
    return _classifier_instance
