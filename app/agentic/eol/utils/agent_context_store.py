"""Agent context store for shared state across multi-agent workflows.

Provides workflow-level and agent-level context management with
in-memory storage for session-scoped workflow state.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

try:
    from app.agentic.eol.utils.logger import get_logger
except ModuleNotFoundError:
    from utils.logger import get_logger


logger = get_logger(__name__)


class AgentContextStore:
    """Manages shared context for multi-agent workflows.

    Context hierarchy:
    - Workflow context: Shared across all agents in a workflow
    - Agent context: Specific to a single agent within a workflow
    - Step context: Specific to a workflow step

    Storage:
    - In-memory dictionary (session-scoped, no persistence needed)
    """

    def __init__(self):
        """Initialize context store."""
        self._initialized = False
        self._cache: Dict[str, Any] = {}  # In-memory store

    async def initialize(self) -> bool:
        """Initialize the context store.

        Returns:
            True if initialization successful
        """
        if self._initialized:
            return True

        self._initialized = True
        logger.info("Agent context store initialized (in-memory)")
        return True

    def _ensure_initialized(self) -> None:
        """Ensure store is initialized (sync check)."""
        if not self._initialized:
            raise RuntimeError("Context store not initialized. Call initialize() first.")

    async def create_workflow_context(
        self,
        workflow_id: str,
        initial_data: Optional[Dict[str, Any]] = None,
        ttl: int = 86400
    ) -> Dict[str, Any]:
        """Create a new workflow context.

        Args:
            workflow_id: Unique workflow identifier
            initial_data: Initial context data
            ttl: Time-to-live in seconds (default 24 hours)

        Returns:
            Created workflow context
        """
        self._ensure_initialized()

        context = {
            "id": workflow_id,
            "workflow_id": workflow_id,
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
            "ttl": ttl,
            "shared_data": initial_data or {},
            "agent_contexts": {},
            "step_results": [],
            "metadata": {
                "status": "created",
                "current_step": 0,
                "total_steps": 0
            }
        }

        # Cache in memory
        self._cache[workflow_id] = context

        return context

    async def get_workflow_context(
        self,
        workflow_id: str
    ) -> Optional[Dict[str, Any]]:
        """Get workflow context.

        Args:
            workflow_id: Workflow identifier

        Returns:
            Workflow context or None if not found
        """
        self._ensure_initialized()

        # Return from memory cache
        return self._cache.get(workflow_id)

    async def update_workflow_context(
        self,
        workflow_id: str,
        updates: Dict[str, Any]
    ) -> bool:
        """Update workflow context.

        Args:
            workflow_id: Workflow identifier
            updates: Dictionary of fields to update

        Returns:
            True if update successful
        """
        self._ensure_initialized()

        context = await self.get_workflow_context(workflow_id)

        if not context:
            logger.error(f"Workflow context {workflow_id} not found")
            return False

        # Apply updates
        for key, value in updates.items():
            if key == "shared_data":
                # Merge shared data
                context["shared_data"].update(value)
            elif key == "metadata":
                # Merge metadata
                context["metadata"].update(value)
            else:
                context[key] = value

        context["updated_at"] = datetime.utcnow().isoformat()

        # Update cache
        self._cache[workflow_id] = context

        return True

    async def set_context_value(
        self,
        workflow_id: str,
        key: str,
        value: Any
    ) -> bool:
        """Set a value in workflow shared context.

        Args:
            workflow_id: Workflow identifier
            key: Context key
            value: Value to set

        Returns:
            True if successful
        """
        return await self.update_workflow_context(
            workflow_id,
            {"shared_data": {key: value}}
        )

    async def get_context_value(
        self,
        workflow_id: str,
        key: str,
        default: Any = None
    ) -> Any:
        """Get a value from workflow shared context.

        Args:
            workflow_id: Workflow identifier
            key: Context key
            default: Default value if key not found

        Returns:
            Context value or default
        """
        context = await self.get_workflow_context(workflow_id)

        if not context:
            return default

        return context.get("shared_data", {}).get(key, default)

    async def set_agent_context(
        self,
        workflow_id: str,
        agent_id: str,
        agent_data: Dict[str, Any]
    ) -> bool:
        """Set agent-specific context within a workflow.

        Args:
            workflow_id: Workflow identifier
            agent_id: Agent identifier
            agent_data: Agent-specific data

        Returns:
            True if successful
        """
        self._ensure_initialized()

        context = await self.get_workflow_context(workflow_id)

        if not context:
            logger.error(f"Workflow context {workflow_id} not found")
            return False

        # Update agent context
        if "agent_contexts" not in context:
            context["agent_contexts"] = {}

        context["agent_contexts"][agent_id] = {
            "agent_id": agent_id,
            "updated_at": datetime.utcnow().isoformat(),
            "data": agent_data
        }

        context["updated_at"] = datetime.utcnow().isoformat()

        # Update cache
        self._cache[workflow_id] = context

        return True

    async def get_agent_context(
        self,
        workflow_id: str,
        agent_id: str
    ) -> Optional[Dict[str, Any]]:
        """Get agent-specific context.

        Args:
            workflow_id: Workflow identifier
            agent_id: Agent identifier

        Returns:
            Agent context or None if not found
        """
        context = await self.get_workflow_context(workflow_id)

        if not context:
            return None

        agent_contexts = context.get("agent_contexts", {})
        agent_context = agent_contexts.get(agent_id)

        return agent_context.get("data") if agent_context else None

    async def add_step_result(
        self,
        workflow_id: str,
        step_id: str,
        agent_id: str,
        result: Dict[str, Any]
    ) -> bool:
        """Add a workflow step result.

        Args:
            workflow_id: Workflow identifier
            step_id: Step identifier
            agent_id: Agent that executed the step
            result: Step execution result

        Returns:
            True if successful
        """
        self._ensure_initialized()

        context = await self.get_workflow_context(workflow_id)

        if not context:
            logger.error(f"Workflow context {workflow_id} not found")
            return False

        # Add step result
        step_entry = {
            "step_id": step_id,
            "agent_id": agent_id,
            "timestamp": datetime.utcnow().isoformat(),
            "result": result
        }

        if "step_results" not in context:
            context["step_results"] = []

        context["step_results"].append(step_entry)

        # Update metadata
        context["metadata"]["current_step"] = len(context["step_results"])
        context["updated_at"] = datetime.utcnow().isoformat()

        # Update cache
        self._cache[workflow_id] = context

        return True

    async def get_step_results(
        self,
        workflow_id: str,
        agent_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get workflow step results.

        Args:
            workflow_id: Workflow identifier
            agent_id: Filter by agent ID (optional)

        Returns:
            List of step results
        """
        context = await self.get_workflow_context(workflow_id)

        if not context:
            return []

        step_results = context.get("step_results", [])

        if agent_id:
            step_results = [
                step for step in step_results
                if step.get("agent_id") == agent_id
            ]

        return step_results

    async def delete_workflow_context(
        self,
        workflow_id: str
    ) -> bool:
        """Delete a workflow context.

        Args:
            workflow_id: Workflow identifier

        Returns:
            True if deletion successful
        """
        self._ensure_initialized()

        # Remove from cache
        if workflow_id in self._cache:
            del self._cache[workflow_id]

        return True

    async def cleanup_expired_contexts(self) -> int:
        """Clean up expired workflow contexts.

        Returns:
            Number of contexts deleted
        """
        self._ensure_initialized()
        logger.info(f"Found {len(self._cache)} active workflow contexts")
        return 0

    def get_stats(self) -> Dict[str, Any]:
        """Get context store statistics.

        Returns:
            Statistics dictionary
        """
        return {
            "initialized": self._initialized,
            "cached_contexts": len(self._cache),
            "storage_backend": "memory_only"
        }


# Global context store instance
_context_store: Optional[AgentContextStore] = None


async def get_context_store() -> AgentContextStore:
    """Get or create the global context store.

    Returns:
        Global AgentContextStore instance
    """
    global _context_store

    if _context_store is None:
        _context_store = AgentContextStore()
        await _context_store.initialize()

    return _context_store
