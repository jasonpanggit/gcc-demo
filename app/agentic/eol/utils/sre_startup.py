"""
SRE Orchestrator Startup Initialization

This module initializes the SRE orchestrator, registers all agents and tools
when the application starts.
"""
import asyncio
from utils.logger import get_logger
from utils.agent_registry import get_agent_registry
from utils.sre_mcp_client import get_sre_mcp_client
from agents.base_sre_agent import BaseSREAgent

logger = get_logger(__name__)


class SREToolProxyAgent(BaseSREAgent):
    """Proxy agent for SRE MCP tools."""

    def __init__(self):
        super().__init__(
            agent_type="sre-tool-proxy",
            agent_id="sre-mcp-server",
            max_retries=2,
            timeout=120
        )
        self.sre_client = None

    async def _initialize_impl(self) -> None:
        try:
            self.sre_client = await get_sre_mcp_client()
            logger.info("✓ SRE MCP client initialized")
        except Exception as exc:
            logger.error(f"Failed to initialize SRE MCP client: {exc}")
            raise

    async def _cleanup_impl(self) -> None:
        if self.sre_client:
            await self.sre_client.cleanup()

    async def execute(self, request: dict, context: dict = None) -> dict:
        if not self.sre_client or not self.sre_client.is_initialized():
            raise RuntimeError("SRE MCP client not initialized")

        tool_name = request.get("tool")
        parameters = request.get("parameters", {})

        if not tool_name:
            return {"success": False, "error": "Tool name required"}

        result = await self.sre_client.call_tool(tool_name, parameters)
        return result


async def initialize_sre_orchestrator():
    """
    Initialize SRE Orchestrator system:
    1. Create and register tool proxy agent
    2. Register all SRE MCP tools
    3. Register all specialist agents

    Returns:
        bool: True if initialization successful
    """
    try:
        logger.info("=" * 60)
        logger.info("🚀 Initializing SRE Orchestrator System")
        logger.info("=" * 60)

        # Get agent registry
        registry = get_agent_registry()

        # Step 1: Create and initialize tool proxy agent
        logger.info("Creating SRE Tool Proxy Agent...")
        proxy_agent = SREToolProxyAgent()

        try:
            initialized = await proxy_agent.initialize()
            if not initialized:
                logger.error("❌ Failed to initialize proxy agent")
                return False

            logger.info("✓ Proxy agent initialized")
        except Exception as exc:
            logger.error(f"❌ Failed to initialize proxy agent: {exc}")
            # Continue without SRE tools - orchestrator will still work for queries
            return False

        # Step 2: Register proxy agent
        await registry.register_agent(
            proxy_agent,
            metadata={"description": "Proxy agent for SRE MCP server tools"}
        )
        logger.info("✓ Proxy agent registered")

        # Step 3: Register all SRE tools
        try:
            tools = proxy_agent.sre_client.get_available_tools()
            registered_count = await registry.register_tools_bulk(
                agent_id=proxy_agent.agent_id,
                tools=tools
            )
            logger.info(f"✓ Registered {registered_count}/{len(tools)} SRE tools")
        except Exception as exc:
            logger.error(f"❌ Failed to register tools: {exc}")
            return False

        # Step 4: Import and register specialist agents (lazy loading to avoid import issues)
        specialist_agents = []

        try:
            from agents.incident_response_agent import IncidentResponseAgent
            specialist_agents.append(("Incident Response", IncidentResponseAgent))
        except ImportError as e:
            logger.warning(f"⚠️ Could not import IncidentResponseAgent: {e}")

        try:
            from agents.performance_analysis_agent import PerformanceAnalysisAgent
            specialist_agents.append(("Performance Analysis", PerformanceAnalysisAgent))
        except ImportError as e:
            logger.warning(f"⚠️ Could not import PerformanceAnalysisAgent: {e}")

        try:
            from agents.cost_optimization_agent import CostOptimizationAgent
            specialist_agents.append(("Cost Optimization", CostOptimizationAgent))
        except ImportError as e:
            logger.warning(f"⚠️ Could not import CostOptimizationAgent: {e}")

        try:
            from agents.security_compliance_agent import SecurityComplianceAgent
            specialist_agents.append(("Security Compliance", SecurityComplianceAgent))
        except ImportError as e:
            logger.warning(f"⚠️ Could not import SecurityComplianceAgent: {e}")

        try:
            from agents.health_monitoring_agent import HealthMonitoringAgent
            specialist_agents.append(("Health Monitoring", HealthMonitoringAgent))
        except ImportError as e:
            logger.warning(f"⚠️ Could not import HealthMonitoringAgent: {e}")

        try:
            from agents.configuration_management_agent import ConfigurationManagementAgent
            specialist_agents.append(("Configuration Management", ConfigurationManagementAgent))
        except ImportError as e:
            logger.warning(f"⚠️ Could not import ConfigurationManagementAgent: {e}")

        try:
            from agents.slo_management_agent import SLOManagementAgent
            specialist_agents.append(("SLO Management", SLOManagementAgent))
        except ImportError as e:
            logger.warning(f"⚠️ Could not import SLOManagementAgent: {e}")

        try:
            from agents.remediation_agent import RemediationAgent
            specialist_agents.append(("Remediation", RemediationAgent))
        except ImportError as e:
            logger.warning(f"⚠️ Could not import RemediationAgent: {e}")

        # Register each specialist agent
        registered_agents = 0
        for name, AgentClass in specialist_agents:
            try:
                agent = AgentClass()
                await agent.initialize()
                await registry.register_agent(
                    agent,
                    metadata={"description": f"{name} specialist agent"}
                )
                logger.info(f"✓ Registered {name} Agent")
                registered_agents += 1
            except Exception as exc:
                logger.warning(f"⚠️ Could not register {name} Agent: {exc}")

        # Step 5: Summary
        stats = registry.get_registry_stats()
        logger.info("=" * 60)
        logger.info("✅ SRE Orchestrator Initialization Complete")
        logger.info(f"   Total Agents: {stats['total_agents']}")
        logger.info(f"   Total Tools: {stats['total_tools']}")
        logger.info(f"   Tool Categories: {stats['tool_categories']}")
        logger.info("=" * 60)

        return True

    except Exception as exc:
        logger.error(f"❌ SRE Orchestrator initialization failed: {exc}", exc_info=True)
        return False


# Global initialization flag
_sre_initialized = False


async def ensure_sre_initialized():
    """
    Ensure SRE orchestrator is initialized (idempotent).
    Can be called multiple times safely.
    """
    global _sre_initialized

    if _sre_initialized:
        return True

    success = await initialize_sre_orchestrator()
    if success:
        _sre_initialized = True

    return success
