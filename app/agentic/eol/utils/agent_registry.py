"""Agent registry for dynamic agent and tool discovery.

Manages agent lifecycle, tool registration, and health monitoring.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Set

try:
    from app.agentic.eol.agents.base_sre_agent import BaseSREAgent
    from app.agentic.eol.utils.logger import get_logger
except ModuleNotFoundError:
    from agents.base_sre_agent import BaseSREAgent
    from utils.logger import get_logger


logger = get_logger(__name__)


class AgentRegistry:
    """Registry for managing agents and their capabilities.

    Provides:
    - Agent registration and discovery
    - Tool catalog management
    - Agent health monitoring
    - Dynamic tool loading from MCP servers
    """

    def __init__(self):
        """Initialize agent registry."""
        self._agents: Dict[str, BaseSREAgent] = {}
        self._agent_metadata: Dict[str, Dict[str, Any]] = {}
        self._tools: Dict[str, Dict[str, Any]] = {}
        self._tool_to_agent_map: Dict[str, str] = {}
        self._agent_health: Dict[str, Dict[str, Any]] = {}

        logger.info("Agent registry initialized")

    async def register_agent(
        self,
        agent: BaseSREAgent,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Register an agent.

        Args:
            agent: Agent instance to register
            metadata: Optional agent metadata

        Returns:
            True if registration successful
        """
        agent_id = agent.agent_id

        if agent_id in self._agents:
            logger.warning(f"Agent {agent_id} already registered, updating")

        # Register agent
        self._agents[agent_id] = agent

        # Store metadata
        self._agent_metadata[agent_id] = {
            "agent_type": agent.agent_type,
            "registered_at": datetime.utcnow().isoformat(),
            "status": "registered",
            **(metadata or {})
        }

        # Initialize health tracking
        self._agent_health[agent_id] = {
            "healthy": True,
            "last_check": datetime.utcnow().isoformat(),
            "consecutive_failures": 0
        }

        logger.info(
            f"✓ Registered agent: {agent_id} (type: {agent.agent_type})"
        )

        return True

    async def unregister_agent(self, agent_id: str) -> bool:
        """Unregister an agent.

        Args:
            agent_id: Agent ID to unregister

        Returns:
            True if unregistration successful
        """
        if agent_id not in self._agents:
            logger.warning(f"Agent {agent_id} not found in registry")
            return False

        # Clean up agent
        agent = self._agents[agent_id]
        await agent.cleanup()

        # Remove from registry
        del self._agents[agent_id]
        del self._agent_metadata[agent_id]
        del self._agent_health[agent_id]

        # Remove tool mappings
        tools_to_remove = [
            tool_name for tool_name, aid in self._tool_to_agent_map.items()
            if aid == agent_id
        ]
        for tool_name in tools_to_remove:
            del self._tools[tool_name]
            del self._tool_to_agent_map[tool_name]

        logger.info(f"✓ Unregistered agent: {agent_id}")

        return True

    def get_agent(self, agent_id: str) -> Optional[BaseSREAgent]:
        """Get agent by ID.

        Args:
            agent_id: Agent ID

        Returns:
            Agent instance or None if not found
        """
        return self._agents.get(agent_id)

    def get_agent_by_type(self, agent_type: str) -> Optional[BaseSREAgent]:
        """Get first agent of specified type.

        Args:
            agent_type: Agent type (e.g., "incident", "monitoring")

        Returns:
            Agent instance or None if not found
        """
        for agent in self._agents.values():
            if agent.agent_type == agent_type:
                return agent
        return None

    def list_agents(
        self,
        agent_type: Optional[str] = None,
        healthy_only: bool = False
    ) -> List[Dict[str, Any]]:
        """List registered agents.

        Args:
            agent_type: Filter by agent type (optional)
            healthy_only: Only return healthy agents

        Returns:
            List of agent information dictionaries
        """
        agents = []

        for agent_id, agent in self._agents.items():
            # Apply filters
            if agent_type and agent.agent_type != agent_type:
                continue

            if healthy_only and not self._agent_health[agent_id]["healthy"]:
                continue

            agents.append({
                "agent_id": agent_id,
                "agent_type": agent.agent_type,
                "initialized": agent.is_initialized(),
                "health": self._agent_health[agent_id],
                "metadata": self._agent_metadata[agent_id],
                "metrics": agent.get_metrics()
            })

        return agents

    async def register_tool(
        self,
        tool_name: str,
        agent_id: str,
        tool_definition: Dict[str, Any]
    ) -> bool:
        """Register a tool with an agent.

        Args:
            tool_name: Tool name
            agent_id: Agent ID that provides this tool
            tool_definition: Tool definition (MCP tool format)

        Returns:
            True if registration successful
        """
        if agent_id not in self._agents:
            logger.error(f"Cannot register tool {tool_name}: agent {agent_id} not found")
            return False

        self._tools[tool_name] = {
            "name": tool_name,
            "agent_id": agent_id,
            "agent_type": self._agents[agent_id].agent_type,
            "definition": tool_definition,
            "registered_at": datetime.utcnow().isoformat()
        }

        self._tool_to_agent_map[tool_name] = agent_id

        logger.debug(f"✓ Registered tool: {tool_name} → agent {agent_id}")

        return True

    async def register_tools_bulk(
        self,
        agent_id: str,
        tools: List[Dict[str, Any]]
    ) -> int:
        """Register multiple tools for an agent.

        Args:
            agent_id: Agent ID
            tools: List of tool definitions

        Returns:
            Number of tools registered
        """
        registered_count = 0

        for tool_def in tools:
            tool_name = tool_def.get("function", {}).get("name")
            if not tool_name:
                logger.warning(f"Skipping tool with no name: {tool_def}")
                continue

            if await self.register_tool(tool_name, agent_id, tool_def):
                registered_count += 1

        logger.info(
            f"✓ Registered {registered_count}/{len(tools)} tools for agent {agent_id}"
        )

        return registered_count

    def get_tool(self, tool_name: str) -> Optional[Dict[str, Any]]:
        """Get tool information.

        Args:
            tool_name: Tool name

        Returns:
            Tool information or None if not found
        """
        return self._tools.get(tool_name)

    def get_agent_for_tool(self, tool_name: str) -> Optional[str]:
        """Get agent ID that provides a tool.

        Args:
            tool_name: Tool name

        Returns:
            Agent ID or None if tool not found
        """
        return self._tool_to_agent_map.get(tool_name)

    def list_tools(
        self,
        agent_id: Optional[str] = None,
        agent_type: Optional[str] = None,
        category: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """List registered tools.

        Args:
            agent_id: Filter by agent ID (optional)
            agent_type: Filter by agent type (optional)
            category: Filter by category (optional)

        Returns:
            List of tool information dictionaries
        """
        tools = []

        for tool_name, tool_info in self._tools.items():
            # Apply filters
            if agent_id and tool_info["agent_id"] != agent_id:
                continue

            if agent_type and tool_info["agent_type"] != agent_type:
                continue

            if category:
                tool_category = tool_info["definition"].get("category", "")
                if tool_category != category:
                    continue

            tools.append(tool_info)

        return tools

    def get_tool_categories(self) -> List[str]:
        """Get all unique tool categories.

        Returns:
            List of category names
        """
        categories: Set[str] = set()

        for tool_info in self._tools.values():
            category = tool_info["definition"].get("category")
            if category:
                categories.add(category)

        return sorted(list(categories))

    async def check_agent_health(self, agent_id: str) -> Dict[str, Any]:
        """Check agent health status.

        Args:
            agent_id: Agent ID

        Returns:
            Health status dictionary
        """
        if agent_id not in self._agents:
            return {
                "healthy": False,
                "error": "Agent not found"
            }

        agent = self._agents[agent_id]

        # Check if initialized
        if not agent.is_initialized():
            self._agent_health[agent_id]["healthy"] = False
            self._agent_health[agent_id]["error"] = "Agent not initialized"
            return self._agent_health[agent_id]

        # Get agent metrics
        metrics = agent.get_metrics()

        # Determine health based on success rate
        success_rate = metrics.get("success_rate", 0.0)
        healthy = success_rate >= 0.8 or metrics["requests_handled"] == 0

        self._agent_health[agent_id]["healthy"] = healthy
        self._agent_health[agent_id]["last_check"] = datetime.utcnow().isoformat()
        self._agent_health[agent_id]["success_rate"] = success_rate

        if not healthy:
            self._agent_health[agent_id]["consecutive_failures"] += 1
        else:
            self._agent_health[agent_id]["consecutive_failures"] = 0

        return self._agent_health[agent_id]

    async def health_check_all(self) -> Dict[str, Dict[str, Any]]:
        """Check health of all registered agents.

        Returns:
            Dictionary mapping agent IDs to health status
        """
        health_results = {}

        for agent_id in self._agents.keys():
            health_results[agent_id] = await self.check_agent_health(agent_id)

        return health_results

    def get_registry_stats(self) -> Dict[str, Any]:
        """Get registry statistics.

        Returns:
            Registry statistics dictionary
        """
        healthy_agents = sum(
            1 for health in self._agent_health.values()
            if health["healthy"]
        )

        agent_types = {}
        for agent in self._agents.values():
            agent_types[agent.agent_type] = agent_types.get(agent.agent_type, 0) + 1

        return {
            "total_agents": len(self._agents),
            "healthy_agents": healthy_agents,
            "unhealthy_agents": len(self._agents) - healthy_agents,
            "total_tools": len(self._tools),
            "agent_types": agent_types,
            "tool_categories": len(self.get_tool_categories())
        }


# Global registry instance
_agent_registry: Optional[AgentRegistry] = None


def get_agent_registry() -> AgentRegistry:
    """Get or create the global agent registry.

    Returns:
        Global AgentRegistry instance
    """
    global _agent_registry

    if _agent_registry is None:
        _agent_registry = AgentRegistry()

    return _agent_registry
