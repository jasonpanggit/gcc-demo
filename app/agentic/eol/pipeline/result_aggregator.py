"""Cross-source result aggregation and discrepancy detection.

Compares EOL dates from multiple SourceResults, applies agreement/disagreement
confidence multipliers (VAL-02), and builds the sources provenance array (VAL-03)
and discrepancies list (VAL-01) for API responses.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

from .source_adapter import SourceResult

logger = logging.getLogger(__name__)

# --- Constants ---
AGREEMENT_THRESHOLD_DAYS: int = 30
AGREEMENT_BOOST: float = 1.2
DISAGREEMENT_PENALTY: float = 0.8


@dataclass
class DiscrepancyEntry:
    """Record of disagreement between two sources on eol_date."""
    source_a: str
    source_b: str
    eol_date_a: str
    eol_date_b: str
    gap_days: int


@dataclass
class SourceEntry:
    """Per-source entry for the API response sources array."""
    agent: str
    confidence: float
    eol_date: Optional[str]
    support_end_date: Optional[str]
    release_date: Optional[str]
    source_url: Optional[str]
    tier: int
    discrepancy_flag: bool
    software_name: str = ""
    version: Optional[str] = None

    def to_dict(self) -> Dict:
        return {
            "agent": self.agent,
            "confidence": self.confidence,
            "eol_date": self.eol_date,
            "support_end_date": self.support_end_date,
            "release_date": self.release_date,
            "source_url": self.source_url,
            "tier": self.tier,
            "discrepancy_flag": self.discrepancy_flag,
            "software_name": self.software_name,
            "version": self.version,
        }


@dataclass
class AggregatedResult:
    """Output of ResultAggregator.aggregate()."""
    primary: Optional[SourceResult]
    confidence: float
    sources: List[SourceEntry] = field(default_factory=list)
    discrepancies: List[DiscrepancyEntry] = field(default_factory=list)

    def sources_as_dicts(self) -> List[Dict]:
        return [s.to_dict() for s in self.sources]

    def discrepancies_as_dicts(self) -> List[Dict]:
        return [
            {
                "source_a": d.source_a,
                "source_b": d.source_b,
                "eol_date_a": d.eol_date_a,
                "eol_date_b": d.eol_date_b,
                "gap_days": d.gap_days,
            }
            for d in self.discrepancies
        ]


class ResultAggregator:
    """Compares multi-source EOL results and applies confidence adjustments.

    Rules:
    - Higher-tier source (lowest tier number) always wins as primary (D-09).
    - Agreement (eol_date gap <= 30 days): x1.2 boost to all confidences (D-11).
    - Disagreement (eol_date gap > 30 days): x0.8 penalty, symmetric (D-10).
    - Only eol_date compared; support_end_date ignored for multiplier (D-12).
    - Single source: multiplier = 1.0 (neutral).
    - Sources without eol_date: excluded from agreement check.
    - Confidence clamped to [0.0, 1.0] after adjustments.
    """

    def aggregate(self, results: List[SourceResult]) -> AggregatedResult:
        """Aggregate multiple source results into a single response.

        Args:
            results: Scored SourceResults from TieredFetchPipeline.fetch_all().

        Returns:
            AggregatedResult with primary result, adjusted confidence,
            sources array, and discrepancies list.
        """
        if not results:
            return AggregatedResult(primary=None, confidence=0.0)

        # 1. Select primary: lowest tier number wins; ties broken by highest confidence
        sorted_results = sorted(results, key=lambda r: (r.tier, -r.confidence))
        primary = sorted_results[0]

        # 2. Compute agreement/disagreement
        results_with_eol = [r for r in results if r.eol_date]
        multiplier = 1.0
        discrepancies: List[DiscrepancyEntry] = []
        involved_in_discrepancy: set = set()

        if len(results_with_eol) >= 2:
            # Pairwise comparison
            has_agreement = False
            has_disagreement = False

            for i in range(len(results_with_eol)):
                for j in range(i + 1, len(results_with_eol)):
                    a = results_with_eol[i]
                    b = results_with_eol[j]
                    gap = self._eol_date_gap_days(a.eol_date, b.eol_date)

                    if gap is None:
                        continue  # unparseable date, skip

                    if gap > AGREEMENT_THRESHOLD_DAYS:
                        has_disagreement = True
                        involved_in_discrepancy.add(id(a))
                        involved_in_discrepancy.add(id(b))
                        discrepancies.append(DiscrepancyEntry(
                            source_a=a.source or a.agent_used or "unknown",
                            source_b=b.source or b.agent_used or "unknown",
                            eol_date_a=a.eol_date,
                            eol_date_b=b.eol_date,
                            gap_days=gap,
                        ))
                        logger.warning(
                            '[aggregator] disagreement: %s (eol=%s) vs %s (eol=%s) gap=%d days',
                            a.source, a.eol_date, b.source, b.eol_date, gap,
                        )
                    else:
                        has_agreement = True
                        logger.info(
                            '[aggregator] agreement: %s (eol=%s) vs %s (eol=%s) gap=%d days',
                            a.source, a.eol_date, b.source, b.eol_date, gap,
                        )

            # Determine multiplier: disagreement takes precedence over agreement
            if has_disagreement:
                multiplier = DISAGREEMENT_PENALTY
            elif has_agreement:
                multiplier = AGREEMENT_BOOST

        # 3. Apply multiplier to all result confidences and build sources array
        sources: List[SourceEntry] = []
        for r in results:
            adjusted_conf = round(min(r.confidence * multiplier, 1.0), 3)
            r.confidence = adjusted_conf  # mutate in place for primary reference
            sources.append(SourceEntry(
                agent=r.source or r.agent_used or "unknown",
                confidence=adjusted_conf,
                eol_date=r.eol_date,
                support_end_date=r.support_end_date,
                release_date=r.release_date,
                source_url=r.source_url,
                tier=r.tier,
                discrepancy_flag=id(r) in involved_in_discrepancy,
                software_name=r.software_name,
                version=r.version,
            ))

        # 4. Top-level confidence is primary's adjusted confidence
        top_confidence = primary.confidence

        return AggregatedResult(
            primary=primary,
            confidence=top_confidence,
            sources=sources,
            discrepancies=discrepancies,
        )

    @staticmethod
    def _eol_date_gap_days(date_a: str, date_b: str) -> Optional[int]:
        """Calculate absolute gap in days between two EOL date strings.

        Handles ISO format dates (YYYY-MM-DD). Returns None if either
        date is unparseable.
        """
        for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S%z"):
            try:
                da = datetime.strptime(date_a[:10], "%Y-%m-%d")
                db = datetime.strptime(date_b[:10], "%Y-%m-%d")
                return abs((da - db).days)
            except (ValueError, TypeError):
                continue
        return None
