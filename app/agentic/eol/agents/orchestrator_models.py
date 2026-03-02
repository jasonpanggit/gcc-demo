"""
Shared data models for orchestrator implementations.

This module defines common data structures used across BaseOrchestrator
and its subclasses (MCPOrchestratorAgent, SREOrchestratorAgent).
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class SSEEventType(Enum):
    """Server-Sent Event types for orchestrator streaming."""
    STATUS = "status"
    PROGRESS = "progress"
    TOOL_PROGRESS = "tool_progress"
    AGENT_RESPONSE = "agent_response"
    RESULT = "result"
    ERROR = "error"
    DONE = "done"


@dataclass
class ToolEntry:
    """Tool information for execution planning."""
    name: str
    description: str
    server: Optional[str] = None
    parameters: Dict[str, Any] = field(default_factory=dict)
    required: bool = False


@dataclass
class PlanStep:
    """Individual step in an execution plan."""
    step_number: int
    action: str  # "invoke_tool", "delegate_agent", "compose_response"
    target: str  # Tool name or agent name
    parameters: Dict[str, Any] = field(default_factory=dict)
    depends_on: List[int] = field(default_factory=list)  # Step numbers
    description: str = ""


@dataclass
class ExecutionPlan:
    """
    Execution plan created by route_query().

    Defines the strategy and steps for handling a user query.
    """
    strategy: str  # "react", "pipeline", "agent_first", "direct"
    domains: List[str]  # e.g., ["sre", "network", "patch"]
    tools: List[ToolEntry]  # Tools to be used
    steps: List[PlanStep]  # Execution steps
    context: Dict[str, Any] = field(default_factory=dict)  # Additional context
    estimated_duration_ms: float = 0.0
    requires_approval: bool = False


@dataclass
class OrchestratorResult:
    """
    Result returned by execute_plan().

    Contains execution outcome, formatted responses, and metadata.
    """
    success: bool
    content: str  # Raw content
    formatted_response: str  # HTML/formatted output
    metadata: Dict[str, Any] = field(default_factory=dict)
    tools_called: List[str] = field(default_factory=list)
    duration_ms: float = 0.0
    interaction_required: bool = False
    interaction_data: Optional[Dict[str, Any]] = None
    error: Optional['ErrorResult'] = None


@dataclass
class ErrorResult:
    """
    Structured error information.

    Used for consistent error handling across orchestrators.
    """
    error_type: str  # e.g., "ToolNotFound", "ExecutionTimeout", "ValidationError"
    message: str
    details: Dict[str, Any] = field(default_factory=dict)
    traceback: Optional[str] = None
    recoverable: bool = True
    retry_after_ms: Optional[int] = None


@dataclass
class Capability:
    """
    Agent capability descriptor for sub-agent discovery.

    Used by DomainSubAgent implementations to advertise capabilities.
    """
    name: str
    description: str
    domains: List[str]  # e.g., ["sre", "incident_response"]
    tool_requirements: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class InventoryContext:
    """
    Inventory grounding context.

    Assembled by ground_context() to provide tenant/subscription/resource context.
    """
    tenant_id: Optional[str] = None
    subscription_ids: List[str] = field(default_factory=list)
    resource_groups: List[str] = field(default_factory=list)
    resource_count: int = 0
    cached: bool = False
    cache_age_seconds: float = 0.0
    summary: str = ""
