"""Base class for orchestrator agents.

Provides common functionality for orchestrators that coordinate multiple tools,
agents, and MCP servers to handle complex user queries.

Design Principles:
- Abstract routing and execution (subclasses define strategy)
- Shared lifecycle management (initialize, cleanup, shutdown)
- Common error handling and logging patterns
- Unified tool invocation through MCPToolRegistry
- Consistent response formatting
- SSE streaming support for long-running operations
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
import uuid
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, AsyncGenerator, Callable, Dict, List, Optional, Sequence

try:
    from app.agentic.eol.agents.orchestrator_models import (
        ExecutionPlan,
        OrchestratorResult,
        ErrorResult,
        SSEEventType,
        InventoryContext,
    )
    from app.agentic.eol.utils.logger import get_logger
    from app.agentic.eol.utils.response_formatter import ResponseFormatter
    from app.agentic.eol.utils.tool_registry import get_tool_registry
    from app.agentic.eol.utils.mcp_host import MCPHost
except ModuleNotFoundError:
    from agents.orchestrator_models import (
        ExecutionPlan,
        OrchestratorResult,
        ErrorResult,
        SSEEventType,
        InventoryContext,
    )
    from utils.logger import get_logger
    from utils.response_formatter import ResponseFormatter
    from utils.tool_registry import get_tool_registry
    from utils.mcp_host import MCPHost


logger = get_logger(__name__)


class OrchestratorError(Exception):
    """Base exception for orchestrator errors."""
    pass


class OrchestratorInitializationError(OrchestratorError):
    """Raised when orchestrator initialization fails."""
    pass


class OrchestratorExecutionError(OrchestratorError):
    """Raised when orchestrator execution fails."""
    pass


class BaseOrchestrator(ABC):
    """Base class for all orchestrator agents.

    Orchestrators coordinate multiple tools, agents, and MCP servers to handle
    complex user queries. Subclasses implement specific routing strategies
    (ReAct, pipeline, agent-first, etc.) while sharing common infrastructure.

    Usage:
        class MyOrchestrator(BaseOrchestrator):
            async def route_query(self, query: str, context: Dict) -> ExecutionPlan:
                # Determine strategy and build plan
                ...

            async def execute_plan(self, plan: ExecutionPlan) -> OrchestratorResult:
                # Execute the plan and return results
                ...
    """

    def __init__(
        self,
        orchestrator_id: Optional[str] = None,
        enable_streaming: bool = True,
        max_retries: int = 3,
        timeout_seconds: float = 120.0,
    ):
        """Initialize the base orchestrator.

        Args:
            orchestrator_id: Unique identifier for this orchestrator instance
            enable_streaming: Enable SSE streaming for long-running operations
            max_retries: Maximum number of retries for failed operations
            timeout_seconds: Timeout for individual operations
        """
        self.orchestrator_id = orchestrator_id or f"orch_{uuid.uuid4().hex[:8]}"
        self.enable_streaming = enable_streaming
        self.max_retries = max_retries
        self.timeout_seconds = timeout_seconds

        # Shared utilities (lazy-initialized)
        self._tool_registry = None
        self._mcp_host = None
        self._response_formatter = None
        self._initialized = False

        # Background task tracking
        self._background_tasks: List[asyncio.Task] = []

        # Inventory grounding context (refreshed periodically)
        self._inventory_context: Optional[InventoryContext] = None
        self._last_inventory_refresh: float = 0.0
        self._inventory_ttl_seconds: float = 300.0  # 5 minutes

        logger.info(
            "BaseOrchestrator initialized: id=%s streaming=%s",
            self.orchestrator_id,
            self.enable_streaming,
        )

    # ========================================================================
    # Abstract Methods (Subclasses MUST implement)
    # ========================================================================

    @abstractmethod
    async def route_query(
        self,
        query: str,
        context: Dict[str, Any],
    ) -> ExecutionPlan:
        """Route a user query and determine execution strategy.

        Analyzes the query and context to determine:
        - Which strategy to use (ReAct, pipeline, agent-first, direct)
        - Which domains are involved (SRE, network, patch, etc.)
        - Which tools are needed
        - What steps to execute

        Args:
            query: User's natural language query
            context: Additional context (subscription_id, workflow_id, etc.)

        Returns:
            ExecutionPlan describing how to handle the query

        Raises:
            OrchestratorError: If routing fails
        """
        pass

    @abstractmethod
    async def execute_plan(
        self,
        plan: ExecutionPlan,
    ) -> OrchestratorResult:
        """Execute an execution plan and return results.

        Implements the orchestration logic specific to this orchestrator type.
        May involve:
        - Invoking tools directly
        - Delegating to sub-agents
        - Running ReAct loops
        - Executing pipeline stages

        Args:
            plan: Execution plan from route_query()

        Returns:
            OrchestratorResult with execution outcome

        Raises:
            OrchestratorExecutionError: If execution fails
        """
        pass

    # ========================================================================
    # Lifecycle Management
    # ========================================================================

    async def initialize(self) -> None:
        """Initialize orchestrator and dependencies.

        Lazy-initializes shared utilities (tool registry, formatters).
        Idempotent - safe to call multiple times.
        """
        if self._initialized:
            logger.debug("Orchestrator %s already initialized", self.orchestrator_id)
            return

        try:
            # Initialize tool registry
            self._tool_registry = get_tool_registry()
            logger.debug("Tool registry initialized")

            # Initialize MCP host (if needed by subclass)
            # Note: MCPHost is available as a class, not via getter
            self._mcp_host = None  # Subclasses can instantiate if needed
            logger.debug("MCP host placeholder set")

            # Initialize response formatter
            self._response_formatter = ResponseFormatter()
            logger.debug("Response formatter initialized")

            self._initialized = True
            logger.info("Orchestrator %s initialized successfully", self.orchestrator_id)

        except Exception as e:
            logger.error("Failed to initialize orchestrator: %s", e, exc_info=True)
            raise OrchestratorInitializationError(f"Initialization failed: {e}") from e

    async def cleanup(self) -> None:
        """Cleanup orchestrator resources.

        Cancels background tasks and releases resources.
        """
        logger.info("Cleaning up orchestrator %s", self.orchestrator_id)

        # Cancel all background tasks
        await self._cancel_background_tasks()

        # Reset state
        self._initialized = False
        self._inventory_context = None

        logger.info("Orchestrator %s cleanup complete", self.orchestrator_id)

    async def shutdown(self) -> None:
        """Graceful shutdown.

        Alias for cleanup() to match common shutdown patterns.
        """
        await self.cleanup()

    async def aclose(self) -> None:
        """Async context manager support.

        Allows using orchestrator with 'async with' pattern.
        """
        await self.cleanup()

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.cleanup()
        return False

    # ========================================================================
    # Main Entry Point
    # ========================================================================

    async def handle_request(
        self,
        query: str,
        context: Optional[Dict[str, Any]] = None,
        stream: bool = False,
    ) -> Any:
        """Main entry point for handling user requests.

        Orchestrates the full request lifecycle:
        1. Initialize if needed
        2. Ground with inventory context
        3. Route query to create plan
        4. Execute plan
        5. Format and return response

        Args:
            query: User's natural language query
            context: Optional context parameters
            stream: Whether to stream progress via SSE

        Returns:
            OrchestratorResult (if stream=False) or AsyncGenerator (if stream=True)

        Raises:
            OrchestratorError: If request handling fails
        """
        start_time = time.time()
        context = context or {}

        # Ensure initialized
        if not self._initialized:
            await self.initialize()

        # Ground with inventory context
        enriched_context = await self.ground_context(query, context)

        try:
            # Route query to create execution plan
            logger.debug("Routing query: %s", query[:100])
            plan = await self.route_query(query, enriched_context)
            logger.info(
                "Query routed: strategy=%s domains=%s steps=%d",
                plan.strategy,
                plan.domains,
                len(plan.steps),
            )

            # Execute plan
            if stream and self.enable_streaming:
                # Return streaming generator
                return self._stream_execution(plan, start_time)
            else:
                # Execute directly and return result
                result = await self.execute_plan(plan)
                result.duration_ms = (time.time() - start_time) * 1000
                return result

        except Exception as e:
            logger.error("Request handling failed: %s", e, exc_info=True)
            error_result = await self._handle_error(e, enriched_context)
            duration_ms = (time.time() - start_time) * 1000

            return OrchestratorResult(
                success=False,
                content=f"Error: {error_result.message}",
                formatted_response=self._format_error_response(error_result),
                metadata={"error": error_result.__dict__},
                duration_ms=duration_ms,
                error=error_result,
            )

    # ========================================================================
    # Tool Management
    # ========================================================================

    async def invoke_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Invoke a tool through the tool registry.

        Provides centralized tool invocation with error handling and logging.

        Args:
            tool_name: Name of the tool to invoke
            arguments: Tool arguments

        Returns:
            Tool execution result

        Raises:
            OrchestratorExecutionError: If tool invocation fails
        """
        if not self._tool_registry:
            raise OrchestratorExecutionError("Tool registry not initialized")

        try:
            logger.debug("Invoking tool: %s with args: %s", tool_name, arguments)
            result = await self._tool_registry.invoke_tool(tool_name, arguments)
            logger.debug("Tool %s completed successfully", tool_name)
            return result

        except Exception as e:
            logger.error("Tool %s failed: %s", tool_name, e, exc_info=True)
            raise OrchestratorExecutionError(f"Tool {tool_name} failed: {e}") from e

    async def _refresh_tool_catalog(self) -> None:
        """Refresh the tool catalog from all MCP servers.

        Called periodically or when tools might have changed.
        """
        if not self._tool_registry:
            return

        try:
            await self._tool_registry.refresh()
            logger.debug("Tool catalog refreshed")
        except Exception as e:
            logger.warning("Failed to refresh tool catalog: %s", e)

    # ========================================================================
    # Context & Inventory Grounding
    # ========================================================================

    async def ground_context(
        self,
        query: str,
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Ground request with inventory context.

        Enriches the context with inventory information about available resources,
        subscriptions, resource groups, etc. This helps the LLM and routing logic
        make better decisions without extra tool calls.

        Args:
            query: User query
            context: Existing context

        Returns:
            Enriched context with inventory information
        """
        enriched = context.copy()

        # Check if inventory context needs refresh
        now = time.time()
        if (
            self._inventory_context is None
            or (now - self._last_inventory_refresh) > self._inventory_ttl_seconds
        ):
            await self._refresh_inventory_context()

        # Add inventory context
        if self._inventory_context:
            enriched["inventory_context"] = self._inventory_context

        return enriched

    async def _refresh_inventory_context(self) -> None:
        """Refresh the inventory grounding context.

        Fetches summary information about resources, subscriptions, etc.
        Cached with TTL to avoid excessive calls.
        """
        try:
            # TODO: Integrate with actual inventory service
            # For now, create minimal context
            self._inventory_context = InventoryContext(
                tenant_id=os.getenv("AZURE_TENANT_ID"),
                subscription_ids=[os.getenv("SUBSCRIPTION_ID")] if os.getenv("SUBSCRIPTION_ID") else [],
                resource_groups=[],
                resource_count=0,
                cached=True,
                cache_age_seconds=0.0,
                summary="Inventory context placeholder",
            )
            self._last_inventory_refresh = time.time()
            logger.debug("Inventory context refreshed")

        except Exception as e:
            logger.warning("Failed to refresh inventory context: %s", e)

    # ========================================================================
    # Response Formatting
    # ========================================================================

    def format_response(
        self,
        results: Any,
        format: str = "formatted_html",
    ) -> str:
        """Format results using ResponseFormatter.

        Args:
            results: Raw results to format
            format: Output format ("formatted_html", "raw_json", etc.)

        Returns:
            Formatted response string
        """
        if not self._response_formatter:
            self._response_formatter = ResponseFormatter()

        try:
            if format == "formatted_html":
                return self._response_formatter.format(results)
            elif format == "raw_json":
                import json
                return json.dumps(results, indent=2, default=str)
            else:
                return str(results)

        except Exception as e:
            logger.warning("Response formatting failed: %s", e)
            return str(results)

    def _format_error_response(self, error: ErrorResult) -> str:
        """Format an error result as HTML.

        Args:
            error: Error result to format

        Returns:
            HTML-formatted error message
        """
        return f"""
        <div class="error-container">
            <h3>Error: {error.error_type}</h3>
            <p>{error.message}</p>
            {f'<details><summary>Details</summary><pre>{error.details}</pre></details>' if error.details else ''}
        </div>
        """

    # ========================================================================
    # Streaming Support
    # ========================================================================

    async def _stream_execution(
        self,
        plan: ExecutionPlan,
        start_time: float,
    ) -> AsyncGenerator[str, None]:
        """Stream execution progress via SSE events.

        Args:
            plan: Execution plan to stream
            start_time: Request start time

        Yields:
            SSE-formatted event strings
        """
        try:
            # Emit initial status
            yield self._emit_event(SSEEventType.STATUS, {
                "status": "started",
                "strategy": plan.strategy,
                "domains": plan.domains,
                "steps": len(plan.steps),
            })

            # Execute plan with progress updates
            result = await self.execute_plan(plan)
            result.duration_ms = (time.time() - start_time) * 1000

            # Emit final result
            yield self._emit_event(SSEEventType.RESULT, {
                "success": result.success,
                "content": result.formatted_response,
                "metadata": result.metadata,
                "duration_ms": result.duration_ms,
            })

            # Emit done event
            yield self._emit_event(SSEEventType.DONE, {
                "completed": True,
                "duration_ms": result.duration_ms,
            })

        except Exception as e:
            error_result = await self._handle_error(e, plan.context)
            yield self._emit_event(SSEEventType.ERROR, {
                "error_type": error_result.error_type,
                "message": error_result.message,
                "details": error_result.details,
            })

    def _emit_event(self, event_type: SSEEventType, content: Dict[str, Any]) -> str:
        """Format an SSE event.

        Args:
            event_type: Type of event
            content: Event content

        Returns:
            SSE-formatted event string
        """
        import json
        return f"event: {event_type.value}\ndata: {json.dumps(content)}\n\n"

    # ========================================================================
    # Background Task Management
    # ========================================================================

    def _spawn_background(self, name: str, coro) -> asyncio.Task:
        """Spawn and track a background task.

        Args:
            name: Task name for logging
            coro: Coroutine to run

        Returns:
            Created asyncio.Task
        """
        task = asyncio.create_task(coro, name=name)
        self._background_tasks.append(task)
        logger.debug("Spawned background task: %s", name)
        return task

    async def _cancel_background_tasks(self) -> None:
        """Cancel all background tasks."""
        if not self._background_tasks:
            return

        logger.info("Cancelling %d background tasks", len(self._background_tasks))

        for task in self._background_tasks:
            if not task.done():
                task.cancel()

        # Wait for all cancellations
        await asyncio.gather(*self._background_tasks, return_exceptions=True)

        self._background_tasks.clear()
        logger.debug("All background tasks cancelled")

    # ========================================================================
    # Error Handling
    # ========================================================================

    async def _handle_error(
        self,
        error: Exception,
        context: Dict[str, Any],
    ) -> ErrorResult:
        """Handle an error with standard logging and formatting.

        Args:
            error: Exception that occurred
            context: Request context

        Returns:
            Structured ErrorResult
        """
        error_type = type(error).__name__
        message = str(error)

        logger.error(
            "Orchestrator error: type=%s message=%s context=%s",
            error_type,
            message,
            context,
            exc_info=True,
        )

        return ErrorResult(
            error_type=error_type,
            message=message,
            details={"context": context},
            traceback=None,  # Don't expose traceback in production
            recoverable=True,
        )
