"""Multiplicative confidence scoring for EOL results.

Replaces the additive heuristic in eol_orchestrator._calculate_confidence
with a formula that respects data source reliability:

    score = tier_base x completeness x freshness

- tier_base: fixed score per source tier (API > JSON-LD > scraper > search)
- completeness: weighted presence of key fields (eol_date, support_end_date, etc.)
- freshness: linear decay for stale data (window depends on tier)

Agreement multiplier is Phase 3 scope (VAL-01, VAL-02).
"""

from typing import Any, Dict, Optional

try:
    from utils import get_logger
    logger = get_logger(__name__)
except ImportError:
    import logging
    logger = logging.getLogger(__name__)


class ConfidenceScorer:
    """Multiplicative confidence scoring engine.

    Tier base scores encode source reliability:
        Tier 1 (endoflife.date API): 0.90
        Tier 2 (eolstatus.com JSON-LD): 0.75
        Tier 3 (vendor HTML scrapers): 0.55
        Tier 4 (Playwright/web search): 0.35
    """

    TIER_BASE: Dict[int, float] = {1: 0.90, 2: 0.75, 3: 0.55, 4: 0.35}

    COMPLETENESS_WEIGHTS: Dict[str, float] = {
        "eol_date": 0.60,
        "support_end_date": 0.20,
        "release_date": 0.10,
        "source_url": 0.10,
    }
    COMPLETENESS_FLOOR: float = 0.3

    # Freshness windows (seconds)
    TIER_HIGH_WINDOW_SECONDS: float = 7 * 24 * 3600  # 7 days for Tier 1-2
    TIER_LOW_WINDOW_SECONDS: float = 24 * 3600        # 24 hours for Tier 3-4
    FRESHNESS_MIN: float = 0.5  # floor: score halved at most

    def score(
        self,
        data: Dict[str, Any],
        tier: int,
        data_age_seconds: Optional[float] = None,
    ) -> float:
        """Calculate multiplicative confidence score.

        Args:
            data: Result data dict containing eol_date, support_end_date, etc.
            tier: Source tier (1-4).
            data_age_seconds: Age of the data in seconds since retrieval.
                None means fresh (factor = 1.0).

        Returns:
            Confidence score in [0.0, 1.0], rounded to 3 decimal places.
        """
        tier_base = self.TIER_BASE.get(tier, 0.35)
        completeness = self._completeness(data)
        freshness = self._freshness(tier, data_age_seconds)
        raw = tier_base * completeness * freshness
        return round(min(raw, 1.0), 3)

    def _completeness(self, data: Dict[str, Any]) -> float:
        """Calculate completeness factor from field presence.

        Each field contributes its weight when present and truthy.
        Floor of 0.3 prevents total zeroing.
        """
        if not data or not isinstance(data, dict):
            return self.COMPLETENESS_FLOOR

        total = 0.0
        for field_name, weight in self.COMPLETENESS_WEIGHTS.items():
            if data.get(field_name):
                total += weight

        return max(self.COMPLETENESS_FLOOR, total)

    def _freshness(self, tier: int, age_seconds: Optional[float]) -> float:
        """Calculate freshness decay factor.

        Data within the window gets factor 1.0.
        After the window, factor decays linearly to FRESHNESS_MIN.
        Decay formula: factor = max(FRESHNESS_MIN, 1.0 - (age - window) / window)
        """
        if age_seconds is None or age_seconds <= 0:
            return 1.0

        window = (
            self.TIER_HIGH_WINDOW_SECONDS
            if tier <= 2
            else self.TIER_LOW_WINDOW_SECONDS
        )

        if age_seconds <= window:
            return 1.0

        overage = age_seconds - window
        decay = 1.0 - (overage / window)
        return max(self.FRESHNESS_MIN, decay)


class ConfidenceNormalizer:
    """Normalize agent-reported confidence values to [0.0, 1.0] float scale.

    Handles:
    - Integer percentages (e.g., 95 -> 0.95)
    - Float percentages > 1.0 (e.g., 80.0 -> 0.80)
    - Valid floats in [0.0, 1.0] (pass through)
    - Non-numeric values (returns None)
    """

    @staticmethod
    def normalize(value: Any) -> Optional[float]:
        """Convert a confidence value to a [0.0, 1.0] float.

        Args:
            value: Agent-reported confidence. May be int, float, str, or None.

        Returns:
            Normalized float in [0.0, 1.0], or None if value is not numeric.
        """
        if value is None:
            return None

        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return None

        # Treat values > 1.0 as percentages (e.g., 95 -> 0.95)
        if numeric > 1.0:
            numeric = numeric / 100.0

        # Clamp to [0.0, 1.0]
        return round(max(0.0, min(1.0, numeric)), 3)


# Module-level singleton for convenience
confidence_scorer = ConfidenceScorer()
confidence_normalizer = ConfidenceNormalizer()
