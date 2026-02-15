"""Base class for all SRE agents.

Provides common functionality for agent lifecycle, tool registration,
error handling, logging, and context management.
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
import uuid
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple

try:
    from app.agentic.eol.utils.logger import get_logger
except ModuleNotFoundError:
    from utils.logger import get_logger


class AgentError(Exception):
    """Base exception for agent errors."""
    pass


class AgentInitializationError(AgentError):
    """Raised when agent initialization fails."""
    pass


class AgentExecutionError(AgentError):
    """Raised when agent execution fails."""
    pass


class BaseSREAgent(ABC):
    """Base class for all SRE agents.

    Design principles:
    - Async-first: All operations are async
    - Stateless: No persistent conversation history per invocation
    - Focused: Each agent owns a specific domain
    - Observable: Comprehensive logging and metrics
    - Resilient: Automatic retries with exponential backoff

    Usage:
        class MyAgent(BaseSREAgent):
            async def execute(self, request: Dict[str, Any]) -> Dict[str, Any]:
                # Agent-specific logic
                return {"status": "success", "result": data}
    """

    def __init__(
        self,
        agent_type: str,
        agent_id: Optional[str] = None,
        max_retries: int = 3,
        timeout: int = 300,  # 5 minutes
        log_level: str = "INFO"
    ):
        """Initialize base agent.

        Args:
            agent_type: Type of agent (e.g., "incident", "monitoring", "cost")
            agent_id: Unique agent ID (generated if not provided)
            max_retries: Maximum number of retries for failed operations
            timeout: Operation timeout in seconds
            log_level: Logging level (DEBUG, INFO, WARNING, ERROR)
        """
        self.agent_type = agent_type
        self.agent_id = agent_id or f"{agent_type}-{uuid.uuid4().hex[:8]}"
        self.max_retries = max_retries
        self.timeout = timeout

        # Initialize logger
        self.logger = get_logger(
            f"{self.__class__.__name__}",
            level=log_level
        )

        # Initialization state
        self._initialized = False
        self._init_start_time: Optional[float] = None

        # Metrics
        self.metrics = {
            "requests_handled": 0,
            "requests_succeeded": 0,
            "requests_failed": 0,
            "total_execution_time": 0.0,
            "avg_execution_time": 0.0
        }

        # SSE callback for streaming updates
        self._sse_callback: Optional[Callable[[str, Dict[str, Any]], None]] = None

        self.logger.info(
            f"Initializing {self.agent_type} agent with ID: {self.agent_id}"
        )

    async def initialize(self) -> bool:
        """Initialize the agent.

        Override this method to add agent-specific initialization logic.

        Returns:
            True if initialization successful, False otherwise
        """
        if self._initialized:
            self.logger.warning(f"Agent {self.agent_id} already initialized")
            return True

        self._init_start_time = time.time()

        try:
            # Call agent-specific initialization
            await self._initialize_impl()

            self._initialized = True
            init_duration = time.time() - self._init_start_time

            self.logger.info(
                f"✓ Agent {self.agent_id} initialized successfully "
                f"in {init_duration:.2f}s"
            )
            return True

        except Exception as exc:
            init_duration = time.time() - self._init_start_time if self._init_start_time else 0
            self.logger.error(
                f"✗ Agent {self.agent_id} initialization failed "
                f"after {init_duration:.2f}s: {exc}",
                exc_info=True
            )
            return False

    async def _initialize_impl(self) -> None:
        """Agent-specific initialization logic.

        Override this method to implement custom initialization.
        """
        # Default: no-op
        pass

    async def cleanup(self) -> None:
        """Clean up agent resources.

        Override this method to add agent-specific cleanup logic.
        """
        if not self._initialized:
            return

        try:
            await self._cleanup_impl()

            self._initialized = False
            self.logger.info(f"✓ Agent {self.agent_id} cleaned up successfully")

        except Exception as exc:
            self.logger.error(
                f"✗ Agent {self.agent_id} cleanup failed: {exc}",
                exc_info=True
            )

    async def _cleanup_impl(self) -> None:
        """Agent-specific cleanup logic.

        Override this method to implement custom cleanup.
        """
        # Default: no-op
        pass

    def is_initialized(self) -> bool:
        """Check if agent is initialized."""
        return self._initialized

    def set_sse_callback(
        self,
        callback: Callable[[str, Dict[str, Any]], None]
    ) -> None:
        """Set SSE callback for streaming updates.

        Args:
            callback: Function to call with event type and data
        """
        self._sse_callback = callback

    async def _stream_event(
        self,
        event_type: str,
        data: Dict[str, Any]
    ) -> None:
        """Stream an SSE event to the callback.

        Args:
            event_type: Type of event (e.g., "progress", "result", "error")
            data: Event data
        """
        if self._sse_callback:
            try:
                event_data = {
                    "agent_id": self.agent_id,
                    "agent_type": self.agent_type,
                    "timestamp": datetime.utcnow().isoformat(),
                    **data
                }
                self._sse_callback(event_type, event_data)
            except Exception as exc:
                self.logger.error(f"Failed to stream event: {exc}")

    async def handle_request(
        self,
        request: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Handle an agent request with error handling and metrics.

        Args:
            request: Request data
            context: Optional workflow context

        Returns:
            Response dictionary with status and result
        """
        if not self._initialized:
            raise AgentInitializationError(
                f"Agent {self.agent_id} not initialized"
            )

        request_id = request.get("request_id", uuid.uuid4().hex[:8])
        start_time = time.time()

        self.logger.info(
            f"Handling request {request_id} for agent {self.agent_id}"
        )

        # Stream progress event
        await self._stream_event("progress", {
            "request_id": request_id,
            "status": "started",
            "message": f"{self.agent_type} agent processing request"
        })

        try:
            # Execute with timeout
            result = await asyncio.wait_for(
                self._execute_with_retry(request, context),
                timeout=self.timeout
            )

            # Update metrics
            execution_time = time.time() - start_time
            self.metrics["requests_handled"] += 1
            self.metrics["requests_succeeded"] += 1
            self.metrics["total_execution_time"] += execution_time
            self.metrics["avg_execution_time"] = (
                self.metrics["total_execution_time"] /
                self.metrics["requests_handled"]
            )

            self.logger.info(
                f"✓ Request {request_id} completed in {execution_time:.2f}s"
            )

            # Stream completion event
            await self._stream_event("result", {
                "request_id": request_id,
                "status": "completed",
                "execution_time": execution_time,
                "result": result
            })

            return {
                "status": "success",
                "agent_id": self.agent_id,
                "agent_type": self.agent_type,
                "request_id": request_id,
                "execution_time": execution_time,
                "result": result
            }

        except asyncio.TimeoutError:
            execution_time = time.time() - start_time
            self.metrics["requests_handled"] += 1
            self.metrics["requests_failed"] += 1

            error_msg = f"Request {request_id} timed out after {self.timeout}s"
            self.logger.error(error_msg)

            # Stream error event
            await self._stream_event("error", {
                "request_id": request_id,
                "status": "timeout",
                "message": error_msg,
                "execution_time": execution_time
            })

            return {
                "status": "error",
                "agent_id": self.agent_id,
                "agent_type": self.agent_type,
                "request_id": request_id,
                "execution_time": execution_time,
                "error": error_msg,
                "error_type": "timeout"
            }

        except Exception as exc:
            execution_time = time.time() - start_time
            self.metrics["requests_handled"] += 1
            self.metrics["requests_failed"] += 1

            error_msg = f"Request {request_id} failed: {str(exc)}"
            self.logger.error(error_msg, exc_info=True)

            # Stream error event
            await self._stream_event("error", {
                "request_id": request_id,
                "status": "failed",
                "message": error_msg,
                "execution_time": execution_time
            })

            return {
                "status": "error",
                "agent_id": self.agent_id,
                "agent_type": self.agent_type,
                "request_id": request_id,
                "execution_time": execution_time,
                "error": str(exc),
                "error_type": exc.__class__.__name__
            }

    async def _execute_with_retry(
        self,
        request: Dict[str, Any],
        context: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Execute request with automatic retry on failure.

        Args:
            request: Request data
            context: Optional workflow context

        Returns:
            Execution result
        """
        last_error: Optional[Exception] = None

        for attempt in range(1, self.max_retries + 1):
            try:
                return await self.execute(request, context)

            except Exception as exc:
                last_error = exc

                if attempt < self.max_retries:
                    backoff = 2 ** (attempt - 1)  # Exponential backoff
                    self.logger.warning(
                        f"Attempt {attempt}/{self.max_retries} failed: {exc}. "
                        f"Retrying in {backoff}s..."
                    )
                    await asyncio.sleep(backoff)
                else:
                    self.logger.error(
                        f"All {self.max_retries} attempts failed. Last error: {exc}"
                    )

        # All retries exhausted
        raise AgentExecutionError(
            f"Failed after {self.max_retries} attempts: {last_error}"
        )

    @abstractmethod
    async def execute(
        self,
        request: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Execute agent-specific logic.

        This method must be implemented by all subclasses.

        Args:
            request: Request data with agent-specific parameters
            context: Optional workflow context from orchestrator

        Returns:
            Result dictionary with agent-specific data
        """
        pass

    def get_metrics(self) -> Dict[str, Any]:
        """Get agent metrics.

        Returns:
            Dictionary of agent metrics
        """
        return {
            **self.metrics,
            "agent_id": self.agent_id,
            "agent_type": self.agent_type,
            "initialized": self._initialized,
            "success_rate": (
                self.metrics["requests_succeeded"] / self.metrics["requests_handled"]
                if self.metrics["requests_handled"] > 0 else 0.0
            )
        }

    def get_status(self) -> Dict[str, Any]:
        """Get agent status.

        Returns:
            Agent status dictionary
        """
        return {
            "agent_id": self.agent_id,
            "agent_type": self.agent_type,
            "initialized": self._initialized,
            "healthy": self._initialized and self.metrics["requests_failed"] < 10,
            "metrics": self.get_metrics()
        }

    def __repr__(self) -> str:
        """String representation of agent."""
        return (
            f"<{self.__class__.__name__} "
            f"id={self.agent_id} "
            f"type={self.agent_type} "
            f"initialized={self._initialized}>"
        )
