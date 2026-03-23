"""Tests for pipeline.result_aggregator (VAL-01, VAL-02, VAL-03)."""

import sys
import os

# Ensure app root is on sys.path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from pipeline.source_adapter import SourceResult
from pipeline.result_aggregator import (
    ResultAggregator,
    AggregatedResult,
    DiscrepancyEntry,
    SourceEntry,
    AGREEMENT_BOOST,
    DISAGREEMENT_PENALTY,
    AGREEMENT_THRESHOLD_DAYS,
)


def _make_result(
    eol_date="2025-12-31",
    source="test_source",
    tier=1,
    confidence=0.85,
    support_end_date=None,
    release_date=None,
    source_url=None,
    agent_used=None,
) -> SourceResult:
    return SourceResult(
        software_name="test_software",
        version="1.0",
        eol_date=eol_date,
        support_end_date=support_end_date,
        release_date=release_date,
        source=source,
        source_url=source_url,
        confidence=confidence,
        tier=tier,
        raw_data={},
        agent_used=agent_used or source,
    )


class TestResultAggregator:
    """Tests for ResultAggregator.aggregate()."""

    def setup_method(self):
        self.aggregator = ResultAggregator()

    def test_empty_results_returns_none_primary(self):
        """No results -> primary is None, confidence 0.0."""
        result = self.aggregator.aggregate([])
        assert result.primary is None
        assert result.confidence == 0.0
        assert result.sources == []
        assert result.discrepancies == []

    def test_single_result_no_adjustment(self):
        """Single source -> multiplier 1.0, no discrepancies."""
        sr = _make_result(confidence=0.85, tier=1, source="endoflife")
        result = self.aggregator.aggregate([sr])
        assert result.primary is sr
        assert result.confidence == 0.85
        assert len(result.sources) == 1
        assert result.sources[0].confidence == 0.85
        assert result.discrepancies == []
        assert result.sources[0].discrepancy_flag is False

    def test_two_sources_agree_within_30_days(self):
        """Two sources agree (gap <= 30 days) -> x1.2 boost."""
        sr1 = _make_result(eol_date="2025-12-31", tier=1, confidence=0.85, source="endoflife")
        sr2 = _make_result(eol_date="2025-12-20", tier=2, confidence=0.70, source="eolstatus")
        result = self.aggregator.aggregate([sr1, sr2])
        assert result.primary is sr1  # tier 1 wins
        assert result.confidence == pytest.approx(min(0.85 * AGREEMENT_BOOST, 1.0), abs=0.01)
        assert len(result.sources) == 2
        assert result.discrepancies == []
        assert all(s.discrepancy_flag is False for s in result.sources)

    def test_two_sources_disagree_over_30_days(self):
        """Two sources disagree (gap > 30 days) -> x0.8 penalty + discrepancy."""
        sr1 = _make_result(eol_date="2025-12-31", tier=1, confidence=0.85, source="endoflife")
        sr2 = _make_result(eol_date="2025-06-01", tier=2, confidence=0.70, source="eolstatus")
        result = self.aggregator.aggregate([sr1, sr2])
        assert result.primary is sr1  # tier 1 wins
        assert result.confidence == pytest.approx(0.85 * DISAGREEMENT_PENALTY, abs=0.01)
        assert len(result.discrepancies) == 1
        d = result.discrepancies[0]
        assert d.gap_days > 30
        assert d.source_a in ("endoflife", "eolstatus")
        assert d.source_b in ("endoflife", "eolstatus")

    def test_three_sources_partial_agreement(self):
        """3 sources: T1 and T3 agree, T2 disagrees -> disagreement penalty wins."""
        sr1 = _make_result(eol_date="2025-12-31", tier=1, confidence=0.85, source="endoflife")
        sr2 = _make_result(eol_date="2025-06-01", tier=2, confidence=0.70, source="eolstatus")
        sr3 = _make_result(eol_date="2025-12-28", tier=3, confidence=0.50, source="vendor")
        result = self.aggregator.aggregate([sr1, sr2, sr3])
        # Disagreement takes precedence
        assert result.confidence == pytest.approx(0.85 * DISAGREEMENT_PENALTY, abs=0.01)
        assert len(result.discrepancies) >= 1

    def test_sources_without_eol_excluded_from_comparison(self):
        """Source without eol_date is excluded from agreement check."""
        sr1 = _make_result(eol_date="2025-12-31", tier=1, confidence=0.85, source="endoflife")
        sr2 = _make_result(eol_date=None, tier=2, confidence=0.60, source="eolstatus")
        result = self.aggregator.aggregate([sr1, sr2])
        # Only 1 source with eol_date -> no adjustment
        assert result.confidence == 0.85
        assert result.discrepancies == []

    def test_agreement_boost_clamped_to_1(self):
        """Agreement boost cannot push confidence above 1.0."""
        sr1 = _make_result(eol_date="2025-12-31", tier=1, confidence=0.95, source="endoflife")
        sr2 = _make_result(eol_date="2025-12-30", tier=2, confidence=0.90, source="eolstatus")
        result = self.aggregator.aggregate([sr1, sr2])
        assert result.confidence <= 1.0
        for s in result.sources:
            assert s.confidence <= 1.0

    def test_discrepancy_entry_format(self):
        """Discrepancy entry has correct fields."""
        sr1 = _make_result(eol_date="2025-12-31", tier=1, confidence=0.85, source="endoflife")
        sr2 = _make_result(eol_date="2025-01-01", tier=2, confidence=0.70, source="eolstatus")
        result = self.aggregator.aggregate([sr1, sr2])
        assert len(result.discrepancies) == 1
        d = result.discrepancies[0]
        assert hasattr(d, "source_a")
        assert hasattr(d, "source_b")
        assert hasattr(d, "eol_date_a")
        assert hasattr(d, "eol_date_b")
        assert hasattr(d, "gap_days")
        assert isinstance(d.gap_days, int)
        assert d.gap_days > 0

    def test_source_entry_format(self):
        """Each source entry has all required fields."""
        sr1 = _make_result(
            eol_date="2025-12-31", tier=1, confidence=0.85, source="endoflife",
            support_end_date="2025-06-30", release_date="2020-01-01",
            source_url="https://endoflife.date/test",
        )
        result = self.aggregator.aggregate([sr1])
        assert len(result.sources) == 1
        s = result.sources[0]
        assert s.agent == "endoflife"
        assert s.eol_date == "2025-12-31"
        assert s.support_end_date == "2025-06-30"
        assert s.release_date == "2020-01-01"
        assert s.source_url == "https://endoflife.date/test"
        assert s.tier == 1
        assert s.discrepancy_flag is False

    def test_primary_selects_lowest_tier(self):
        """Primary result is from the lowest tier, not highest confidence."""
        sr1 = _make_result(eol_date="2025-12-31", tier=2, confidence=0.95, source="eolstatus")
        sr2 = _make_result(eol_date="2025-12-31", tier=1, confidence=0.80, source="endoflife")
        result = self.aggregator.aggregate([sr1, sr2])
        assert result.primary.source == "endoflife"
        assert result.primary.tier == 1

    def test_sources_as_dicts(self):
        """sources_as_dicts() returns list of dicts."""
        sr1 = _make_result(tier=1, source="endoflife")
        result = self.aggregator.aggregate([sr1])
        dicts = result.sources_as_dicts()
        assert isinstance(dicts, list)
        assert len(dicts) == 1
        assert dicts[0]["agent"] == "endoflife"
        assert "confidence" in dicts[0]
        assert "tier" in dicts[0]
        assert "discrepancy_flag" in dicts[0]

    def test_discrepancies_as_dicts(self):
        """discrepancies_as_dicts() returns list of dicts."""
        sr1 = _make_result(eol_date="2025-12-31", tier=1, source="endoflife")
        sr2 = _make_result(eol_date="2025-01-01", tier=2, source="eolstatus")
        result = self.aggregator.aggregate([sr1, sr2])
        dicts = result.discrepancies_as_dicts()
        assert isinstance(dicts, list)
        assert len(dicts) == 1
        assert "source_a" in dicts[0]
        assert "gap_days" in dicts[0]
