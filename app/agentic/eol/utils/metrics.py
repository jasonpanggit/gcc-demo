"""
Lightweight metrics collection for monitoring application health.

This module provides simple counters and histograms without external
dependencies. For production, consider integrating with Prometheus
or Azure Application Insights.

Usage:
from utils.metrics import metrics_collector

metrics_collector.increment("api_requests", labels={"endpoint": "/api/eol", "status": "200"})
metrics_collector.record_duration("openai_call_duration", duration_ms)
"""
import time
from typing import Dict, List, Optional
from collections import defaultdict
from dataclasses import dataclass, field
from threading import Lock


@dataclass
class Counter:
    """Simple counter metric."""

    value: int = 0
    labels: Dict[str, str] = field(default_factory=dict)


@dataclass
class Histogram:
    """Simple histogram for recording durations."""

    samples: List[float] = field(default_factory=list)
    sum: float = 0.0
    count: int = 0
    labels: Dict[str, str] = field(default_factory=dict)

    def record(self, value: float):
        """Record a sample."""
        self.samples.append(value)
        self.sum += value
        self.count += 1
        # Keep only the last 1000 samples to prevent unbounded growth
        if len(self.samples) > 1000:
            self.samples = self.samples[-1000:]

    def percentile(self, p: float) -> float:
        """Calculate percentile (p should be 0-100)."""
        if not self.samples:
            return 0.0
        sorted_samples = sorted(self.samples)
        index = int((p / 100.0) * len(sorted_samples))
        return sorted_samples[min(index, len(sorted_samples) - 1)]

    def average(self) -> float:
        """Calculate average."""
        return self.sum / self.count if self.count > 0 else 0.0


class MetricsCollector:
    """
    Thread-safe metrics collector for counters and histograms.
    """

    def __init__(self):
        self._counters: Dict[str, Counter] = defaultdict(Counter)
        self._histograms: Dict[str, Histogram] = defaultdict(Histogram)
        self._lock = Lock()

    def increment(
        self, metric_name: str, value: int = 1, labels: Optional[Dict[str, str]] = None
    ):
        """Increment a counter."""
        key = self._make_key(metric_name, labels)
        with self._lock:
            self._counters[key].value += value
            if labels:
                self._counters[key].labels = labels

    def record_duration(
        self, metric_name: str, duration_ms: float, labels: Optional[Dict[str, str]] = None
    ):
        """Record a duration in milliseconds."""
        key = self._make_key(metric_name, labels)
        with self._lock:
            self._histograms[key].record(duration_ms)
            if labels:
                self._histograms[key].labels = labels

    def get_counter(self, metric_name: str, labels: Optional[Dict[str, str]] = None) -> int:
        """Get current counter value."""
        key = self._make_key(metric_name, labels)
        with self._lock:
            return self._counters[key].value

    def get_histogram_stats(
        self, metric_name: str, labels: Optional[Dict[str, str]] = None
    ) -> Dict[str, float]:
        """Get histogram statistics."""
        key = self._make_key(metric_name, labels)
        with self._lock:
            hist = self._histograms[key]
            return {
                "count": hist.count,
                "sum": hist.sum,
                "avg": hist.average(),
                "p50": hist.percentile(50),
                "p95": hist.percentile(95),
                "p99": hist.percentile(99),
            }

    def get_all_metrics(self) -> Dict[str, any]:
        """Get all metrics as a dictionary."""
        with self._lock:
            counters = {k: c.value for k, c in self._counters.items()}
            histograms = {}
            for k, h in self._histograms.items():
                histograms[k] = {
                    "count": h.count,
                    "sum": h.sum,
                    "avg": h.average(),
                    "p50": h.percentile(50),
                    "p95": h.percentile(95),
                    "p99": h.percentile(99),
                }
            return {"counters": counters, "histograms": histograms}

    def reset(self):
        """Reset all metrics."""
        with self._lock:
            self._counters.clear()
            self._histograms.clear()

    @staticmethod
    def _make_key(metric_name: str, labels: Optional[Dict[str, str]] = None) -> str:
        """Create a unique key from metric name and labels."""
        if not labels:
            return metric_name
        label_str = ",".join(f"{k}={v}" for k, v in sorted(labels.items()))
        return f"{metric_name}{{{label_str}}}"


# Global singleton instance
metrics_collector = MetricsCollector()
