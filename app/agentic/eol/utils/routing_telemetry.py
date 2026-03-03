"""Routing telemetry for production monitoring and analysis.

Captures routing decisions with full context to enable:
- Routing accuracy measurement
- Metadata effectiveness analysis
- Query pattern identification
- User behavior tracking

Simple JSON log implementation (no external dependencies).
Can be upgraded to Application Insights or Cosmos DB later.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
from enum import Enum

try:
    from utils.logger import get_logger
    from utils.config import get_config
except ImportError:
    from app.agentic.eol.utils.logger import get_logger
    from app.agentic.eol.utils.config import get_config


logger = get_logger(__name__)
config = get_config()


class SelectionMethod(str, Enum):
    """How the routing decision was made."""
    METADATA_MATCH = "metadata_match"  # primary_phrasings match
    EMBEDDING_FALLBACK = "embedding_fallback"  # semantic search
    CLI_ESCAPE = "cli_escape"  # fallback to CLI
    LLM_PLANNER = "llm_planner"  # LLM-based planning


class ConfidenceLevel(str, Enum):
    """Routing confidence classification."""
    HIGH = "high"  # score ≥ 2.0
    MEDIUM = "medium"  # 1.5 ≤ score < 2.0
    LOW = "low"  # score < 1.5


@dataclass
class ToolCandidate:
    """A candidate tool with scoring details."""
    tool_name: str
    base_score: float
    confidence_boost: float
    final_score: float
    matched_phrasing: Optional[str] = None
    match_type: Optional[str] = None  # exact_substring, partial, semantic


@dataclass
class RoutingDecision:
    """Complete routing decision event."""
    timestamp: str
    query: str
    selected_tools: List[str]
    selection_method: str
    candidates: List[Dict]  # Top N candidates with scores
    prerequisite_injection: Dict[str, List[str]]
    confidence_level: str
    session_id: Optional[str] = None
    user_id: Optional[str] = None
    execution_success: Optional[bool] = None
    execution_time_ms: Optional[int] = None
    user_correction: Optional[str] = None  # Tool user switched to
    routing_correct: Optional[bool] = None


class RoutingTelemetry:
    """Telemetry collection for routing decisions.

    Logs routing decisions to JSON files for later analysis.
    Lightweight, no external dependencies.
    """

    def __init__(
        self,
        enabled: bool = True,
        log_dir: Optional[str] = None,
        sample_rate: float = 1.0
    ):
        """Initialize telemetry.

        Args:
            enabled: Whether telemetry is enabled
            log_dir: Directory for log files (default: ./routing_logs)
            sample_rate: Fraction of events to log (0.0-1.0)
        """
        self.enabled = enabled and config.app.env != "test"
        self.sample_rate = sample_rate
        self.log_dir = Path(log_dir or "./routing_logs")

        if self.enabled:
            self.log_dir.mkdir(exist_ok=True)
            logger.info(f"Routing telemetry enabled: {self.log_dir}")

    def log_routing_decision(
        self,
        query: str,
        selected_tools: List[str],
        candidates: List[ToolCandidate],
        selection_method: SelectionMethod,
        prerequisite_chains: Optional[Dict[str, List[str]]] = None,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None
    ) -> None:
        """Log a routing decision.

        Args:
            query: User's natural language query
            selected_tools: Tools that were selected
            candidates: All candidate tools with scores
            selection_method: How routing decision was made
            prerequisite_chains: Injected prerequisite tools
            session_id: Session identifier
            user_id: User identifier
        """
        if not self.enabled:
            return

        # Sample if configured
        if self.sample_rate < 1.0:
            import random
            if random.random() > self.sample_rate:
                return

        # Determine confidence level from top score
        confidence = self._classify_confidence(candidates)

        # Create decision event
        decision = RoutingDecision(
            timestamp=datetime.utcnow().isoformat(),
            query=query,
            selected_tools=selected_tools,
            selection_method=selection_method.value,
            candidates=[asdict(c) for c in candidates[:10]],  # Top 10 only
            prerequisite_injection=prerequisite_chains or {},
            confidence_level=confidence.value,
            session_id=session_id,
            user_id=user_id
        )

        # Write to daily log file
        self._write_log_entry(decision)

    def log_execution_result(
        self,
        query: str,
        success: bool,
        execution_time_ms: int,
        session_id: Optional[str] = None
    ) -> None:
        """Log execution result for a query.

        Args:
            query: The query that was executed
            success: Whether execution succeeded
            execution_time_ms: Execution time in milliseconds
            session_id: Session identifier
        """
        if not self.enabled:
            return

        # Note: In production, you'd want to correlate this with the routing decision
        # For now, we just log it separately
        event = {
            "timestamp": datetime.utcnow().isoformat(),
            "event_type": "execution_result",
            "query": query,
            "success": success,
            "execution_time_ms": execution_time_ms,
            "session_id": session_id
        }

        log_file = self.log_dir / f"execution_{datetime.utcnow().date()}.jsonl"
        with open(log_file, "a") as f:
            f.write(json.dumps(event) + "\n")

    def log_user_correction(
        self,
        query: str,
        original_tool: str,
        corrected_tool: str,
        session_id: Optional[str] = None
    ) -> None:
        """Log when user overrides tool selection.

        Args:
            query: The original query
            original_tool: Tool that was auto-selected
            corrected_tool: Tool user manually selected
            session_id: Session identifier
        """
        if not self.enabled:
            return

        event = {
            "timestamp": datetime.utcnow().isoformat(),
            "event_type": "user_correction",
            "query": query,
            "original_tool": original_tool,
            "corrected_tool": corrected_tool,
            "session_id": session_id
        }

        log_file = self.log_dir / f"corrections_{datetime.utcnow().date()}.jsonl"
        with open(log_file, "a") as f:
            f.write(json.dumps(event) + "\n")

        logger.info(
            f"User correction: '{query}' → {original_tool} → {corrected_tool}"
        )

    def _classify_confidence(self, candidates: List[ToolCandidate]) -> ConfidenceLevel:
        """Classify routing confidence based on top score."""
        if not candidates:
            return ConfidenceLevel.LOW

        top_score = candidates[0].final_score

        if top_score >= 2.0:
            return ConfidenceLevel.HIGH
        elif top_score >= 1.5:
            return ConfidenceLevel.MEDIUM
        else:
            return ConfidenceLevel.LOW

    def _write_log_entry(self, decision: RoutingDecision) -> None:
        """Write decision to daily log file."""
        log_file = self.log_dir / f"routing_{datetime.utcnow().date()}.jsonl"

        try:
            with open(log_file, "a") as f:
                f.write(json.dumps(asdict(decision)) + "\n")
        except Exception as e:
            logger.error(f"Failed to write telemetry: {e}")


# Singleton instance
_telemetry: Optional[RoutingTelemetry] = None


def get_routing_telemetry() -> RoutingTelemetry:
    """Get the global routing telemetry instance."""
    global _telemetry
    if _telemetry is None:
        # Read config from environment
        enabled = os.getenv("ROUTING_TELEMETRY_ENABLED", "false").lower() == "true"
        log_dir = os.getenv("ROUTING_TELEMETRY_LOG_DIR", "./routing_logs")
        sample_rate = float(os.getenv("ROUTING_TELEMETRY_SAMPLE_RATE", "1.0"))

        _telemetry = RoutingTelemetry(
            enabled=enabled,
            log_dir=log_dir,
            sample_rate=sample_rate
        )

    return _telemetry
