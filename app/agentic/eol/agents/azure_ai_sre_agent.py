"""
Azure AI SRE Agent - Integration with Azure AI Agent Service for SRE Operations

This module provides a wrapper around the SRE MCP server tools using Azure AI Agent Service.
It enables managed agent lifecycle, persistent conversation state, and integration with
Azure AI Foundry portal.

Key Features:
- Managed agent lifecycle (start, stop, restart)
- Persistent conversation history in Azure AI Project
- Integration with Azure AI Foundry portal
- Tool registration via Azure AI Agents SDK
- Multi-agent coordination capabilities
"""

import asyncio
import logging
import os
from typing import Dict, Any, Optional, List
from datetime import datetime

# Set up logger
try:
    from app.agentic.eol.utils.logger import get_logger
    logger = get_logger(__name__)
except Exception:
    import logging
    logger = logging.getLogger(__name__)

# Azure AI Agent Service dependencies
try:
    from azure.identity import DefaultAzureCredential
    from azure.ai.projects import AIProjectClient
    from azure.ai.agents import AgentsClient
    from azure.ai.agents.models import Agent, AgentThread, MessageRole, ThreadMessage
    AZURE_AI_AGENTS_AVAILABLE = True
    logger.info("✅ Azure AI Agent Service dependencies available")
except ImportError as e:
    logger.warning(f"⚠️ Azure AI Agent Service dependencies not available: {e}")
    logger.warning("💡 Install: pip install azure-ai-projects azure-ai-agents azure-identity")
    AZURE_AI_AGENTS_AVAILABLE = False
    # Placeholder classes
    class AIProjectClient:
        pass
    class AgentsClient:
        pass
    class Agent:
        pass


class AzureAISREAgent:
    """
    Azure AI SRE Agent wrapper for managed SRE operations

    This class provides integration between the SRE MCP server tools and Azure AI Agent Service,
    enabling managed agent lifecycle, persistent conversations, and Azure AI Foundry integration.
    """

    def __init__(
        self,
        project_endpoint: Optional[str] = None,
        agent_name: str = "sre-agent",
        instructions: Optional[str] = None
    ):
        """
        Initialize Azure AI SRE Agent

        Args:
            project_endpoint: Azure AI Project endpoint (optional, uses env var if not provided)
            agent_name: Name for the agent instance
            instructions: System instructions for the agent (optional)
        """
        self.agent_name = agent_name

        # Azure AI Project configuration
        self.project_endpoint = project_endpoint or os.getenv("AZURE_AI_PROJECT_ENDPOINT", "")
        self.subscription_id = os.getenv("SUBSCRIPTION_ID", "")
        self.resource_group = os.getenv("RESOURCE_GROUP_NAME", "")

        # Default SRE agent instructions
        self.instructions = instructions or """
You are an Azure SRE (Site Reliability Engineering) agent specializing in:
- Resource health monitoring and diagnostics
- Incident response and troubleshooting
- Performance analysis and optimization
- Safe automated remediation with approval workflows
- Azure Monitor integration and alerting

Use the available SRE tools to diagnose and resolve Azure infrastructure issues.
Always confirm before executing any remediation actions (restart, scale, clear_cache).
Provide clear explanations and recommendations for all operations.
"""

        # Initialize Azure credential
        self.credential = None
        self.ai_client = None
        self.agents_client = None
        self.agent = None
        self.thread = None

        if AZURE_AI_AGENTS_AVAILABLE:
            try:
                self.credential = DefaultAzureCredential()

                # Initialize Azure AI Project Client
                if self.project_endpoint:
                    self.ai_client = AIProjectClient(
                        endpoint=self.project_endpoint,
                        credential=self.credential
                    )

                    # Initialize Agents Client
                    self.agents_client = self.ai_client.agents

                    logger.info(f"✅ Azure AI SRE Agent '{agent_name}' initialized")
                else:
                    logger.warning("⚠️ AZURE_AI_PROJECT_ENDPOINT not configured")

            except Exception as e:
                logger.error(f"❌ Failed to initialize Azure AI SRE Agent: {e}")
                self.credential = None
                self.ai_client = None
                self.agents_client = None

    def is_available(self) -> bool:
        """Check if Azure AI Agent Service is properly configured"""
        if not AZURE_AI_AGENTS_AVAILABLE:
            logger.info("💡 Azure AI Agent Service dependencies not installed")
            return False

        is_configured = bool(
            self.agents_client and
            self.credential and
            self.project_endpoint
        )

        if not is_configured:
            logger.info("💡 Azure AI Agent Service not fully configured")
            logger.info("   Required: AZURE_AI_PROJECT_ENDPOINT, Azure credentials")

        return is_configured

    async def create_agent(
        self,
        model: str = "gpt-4o",
        tools: Optional[List[Dict[str, Any]]] = None
    ) -> Optional[Agent]:
        """
        Create a new Azure AI Agent instance

        Args:
            model: Model deployment name (default: gpt-4o)
            tools: List of tool definitions (optional, uses SRE tools if not provided)

        Returns:
            Agent instance or None if creation fails
        """
        if not self.is_available():
            logger.error("❌ Azure AI Agent Service not available")
            return None

        try:
            # Create agent with SRE tools
            self.agent = self.agents_client.create_agent(
                model=model,
                name=self.agent_name,
                instructions=self.instructions,
                tools=tools or self._get_sre_tools()
            )

            logger.info(f"✅ Created Azure AI Agent: {self.agent.id}")
            return self.agent

        except Exception as e:
            logger.error(f"❌ Failed to create Azure AI Agent: {e}")
            return None

    async def create_thread(self) -> Optional[AgentThread]:
        """
        Create a new conversation thread

        Returns:
            AgentThread instance or None if creation fails
        """
        if not self.is_available():
            logger.error("❌ Azure AI Agent Service not available")
            return None

        try:
            self.thread = self.agents_client.create_thread()
            logger.info(f"✅ Created conversation thread: {self.thread.id}")
            return self.thread

        except Exception as e:
            logger.error(f"❌ Failed to create thread: {e}")
            return None

    async def send_message(
        self,
        message: str,
        thread_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Send a message to the agent and get response

        Args:
            message: User message content
            thread_id: Thread ID (optional, uses current thread if not provided)

        Returns:
            Response dictionary with agent's reply
        """
        if not self.is_available():
            logger.error("❌ Azure AI Agent Service not available")
            return {"error": "Azure AI Agent Service not available"}

        if not self.agent:
            logger.error("❌ Agent not created. Call create_agent() first")
            return {"error": "Agent not created"}

        try:
            # Use provided thread_id or current thread
            target_thread = thread_id or (self.thread.id if self.thread else None)

            if not target_thread:
                # Create new thread if none exists
                await self.create_thread()
                target_thread = self.thread.id

            # Create message in thread
            message_obj = self.agents_client.create_message(
                thread_id=target_thread,
                role=MessageRole.USER,
                content=message
            )

            # Run the agent
            run = self.agents_client.create_run(
                thread_id=target_thread,
                assistant_id=self.agent.id
            )

            # Wait for completion
            while run.status in ["queued", "in_progress"]:
                await asyncio.sleep(1)
                run = self.agents_client.get_run(
                    thread_id=target_thread,
                    run_id=run.id
                )

            # Get messages
            messages = self.agents_client.list_messages(thread_id=target_thread)

            # Extract assistant's response
            assistant_messages = [
                msg for msg in messages.data
                if msg.role == MessageRole.ASSISTANT and msg.created_at > message_obj.created_at
            ]

            if assistant_messages:
                response_content = assistant_messages[0].content[0].text.value
                return {
                    "response": response_content,
                    "thread_id": target_thread,
                    "run_id": run.id,
                    "status": run.status
                }
            else:
                return {
                    "error": "No response from agent",
                    "run_status": run.status
                }

        except Exception as e:
            logger.error(f"❌ Failed to send message: {e}")
            return {"error": str(e)}

    async def delete_agent(self, agent_id: Optional[str] = None):
        """
        Delete the agent instance

        Args:
            agent_id: Agent ID to delete (optional, uses current agent if not provided)
        """
        if not self.is_available():
            return

        try:
            target_agent_id = agent_id or (self.agent.id if self.agent else None)
            if target_agent_id:
                self.agents_client.delete_agent(agent_id=target_agent_id)
                logger.info(f"✅ Deleted agent: {target_agent_id}")
                self.agent = None
        except Exception as e:
            logger.error(f"❌ Failed to delete agent: {e}")

    def _get_sre_tools(self) -> List[Dict[str, Any]]:
        """
        Get SRE tool definitions for Azure AI Agent Service.

        Dynamically imports tool definitions from the SRE MCP server when available,
        falling back to a comprehensive static definition list.

        Returns:
            List of tool definitions compatible with Azure AI Agents SDK
        """
        # Try dynamic import from SRE MCP server
        try:
            dynamic_tools = self._get_dynamic_sre_tools()
            if dynamic_tools:
                logger.info(f"✅ Loaded {len(dynamic_tools)} SRE tools dynamically from MCP server")
                return dynamic_tools
        except Exception as e:
            logger.debug(f"Dynamic tool import failed, using static definitions: {e}")

        # Fallback: comprehensive static definitions
        return self._get_static_sre_tools()

    def _get_dynamic_sre_tools(self) -> Optional[List[Dict[str, Any]]]:
        """
        Attempt to dynamically load tool definitions from the SRE MCP server.

        Returns:
            List of tool definitions or None if unavailable
        """
        try:
            from utils.sre_mcp_client import SREMCPClient
            import asyncio

            client = SREMCPClient()
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Can't run sync in an async context — return None for fallback
                logger.debug("Event loop already running, using static SRE tools")
                return None

            initialized = loop.run_until_complete(client.initialize())
            if initialized:
                tools = client.get_available_tools()
                loop.run_until_complete(client.cleanup())
                return tools
            return None
        except Exception as e:
            logger.debug(f"Failed to load dynamic SRE tools: {e}")
            return None

    def _get_static_sre_tools(self) -> List[Dict[str, Any]]:
        """
        Get comprehensive static SRE tool definitions as fallback.

        Returns:
            List of tool definitions compatible with Azure AI Agents SDK
        """
        return [
            # === Resource Health & Diagnostics ===
            {
                "type": "function",
                "function": {
                    "name": "check_resource_health",
                    "description": "Check the health status of an Azure resource using Resource Health API",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "resource_id": {"type": "string", "description": "Full Azure resource ID"}
                        },
                        "required": ["resource_id"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "check_container_app_health",
                    "description": "Check Container App health via Log Analytics",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "workspace_id": {"type": "string", "description": "Log Analytics workspace ID"},
                            "resource_id": {"type": "string", "description": "Full Container App resource ID"}
                        },
                        "required": ["workspace_id", "resource_id"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_diagnostic_logs",
                    "description": "Retrieve diagnostic logs from Log Analytics",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "workspace_id": {"type": "string", "description": "Log Analytics workspace ID"},
                            "query": {"type": "string", "description": "KQL query"}
                        },
                        "required": ["workspace_id", "query"]
                    }
                }
            },
            # === Incident Response ===
            {
                "type": "function",
                "function": {
                    "name": "triage_incident",
                    "description": "Automated incident triage with health checks and severity assessment",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "resource_id": {"type": "string", "description": "Azure resource ID to investigate"},
                            "description": {"type": "string", "description": "Incident description"}
                        },
                        "required": ["resource_id"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "search_logs_by_error",
                    "description": "Search logs for specific error patterns",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "workspace_id": {"type": "string", "description": "Log Analytics workspace ID"},
                            "error_pattern": {"type": "string", "description": "Error pattern to search for"}
                        },
                        "required": ["workspace_id", "error_pattern"]
                    }
                }
            },
            # === Performance ===
            {
                "type": "function",
                "function": {
                    "name": "get_performance_metrics",
                    "description": "Query Azure Monitor metrics (CPU, memory, network) with auto-calculated time ranges",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "resource_id": {"type": "string", "description": "Azure resource ID"},
                            "metric_names": {"type": "string", "description": "Comma-separated metric names"}
                        },
                        "required": ["resource_id"]
                    }
                }
            },
            # === Remediation ===
            {
                "type": "function",
                "function": {
                    "name": "plan_remediation",
                    "description": "Generate step-by-step remediation plan with approval workflow",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "resource_id": {"type": "string", "description": "Azure resource ID"},
                            "issue_type": {"type": "string", "description": "Type of issue to remediate"}
                        },
                        "required": ["resource_id", "issue_type"]
                    }
                }
            },
            # === Cost Optimization ===
            {
                "type": "function",
                "function": {
                    "name": "get_cost_analysis",
                    "description": "Query Azure Cost Management for spending breakdown by resource group, service, or tag",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "scope": {"type": "string", "description": "Cost analysis scope (subscription or resource group)"},
                            "time_range": {"type": "string", "description": "Time range (e.g., 'last_7_days', 'last_30_days')"}
                        },
                        "required": ["scope"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "identify_orphaned_resources",
                    "description": "Find unused Azure resources (unattached disks, idle public IPs, empty NSGs)",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "subscription_id": {"type": "string", "description": "Azure subscription ID"}
                        },
                        "required": []
                    }
                }
            },
            # === SLO Management ===
            {
                "type": "function",
                "function": {
                    "name": "define_slo",
                    "description": "Define a service level objective (availability, latency, or error rate target)",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "service_name": {"type": "string", "description": "Name of the service"},
                            "sli_type": {"type": "string", "description": "SLI type: availability, latency, or error_rate"},
                            "target_percentage": {"type": "number", "description": "Target percentage (e.g., 99.9)"},
                            "window_days": {"type": "integer", "description": "SLO measurement window in days"}
                        },
                        "required": ["service_name", "sli_type", "target_percentage"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "calculate_error_budget",
                    "description": "Calculate remaining error budget based on SLI measurements vs SLO targets",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "service_name": {"type": "string", "description": "Name of the service"},
                            "slo_id": {"type": "string", "description": "SLO definition ID"}
                        },
                        "required": ["service_name"]
                    }
                }
            },
            # === Security & Compliance ===
            {
                "type": "function",
                "function": {
                    "name": "get_security_score",
                    "description": "Get Microsoft Defender for Cloud secure score with control-level breakdown",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "subscription_id": {"type": "string", "description": "Azure subscription ID"}
                        },
                        "required": []
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "check_compliance_status",
                    "description": "Check Azure Policy compliance for regulatory frameworks (CIS, NIST, PCI-DSS)",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "scope": {"type": "string", "description": "Compliance scope (subscription or resource group)"},
                            "policy_definition_name": {"type": "string", "description": "Policy initiative name"}
                        },
                        "required": ["scope"]
                    }
                }
            },
            # === Application Insights ===
            {
                "type": "function",
                "function": {
                    "name": "query_app_insights_traces",
                    "description": "Query Application Insights for distributed traces by operation ID",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "workspace_id": {"type": "string", "description": "Log Analytics workspace ID"},
                            "operation_id": {"type": "string", "description": "Operation/correlation ID to trace"}
                        },
                        "required": ["workspace_id", "operation_id"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_request_telemetry",
                    "description": "Get request performance telemetry (response times, failure rates, P95/P99 latencies)",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "workspace_id": {"type": "string", "description": "Log Analytics workspace ID"},
                            "app_name": {"type": "string", "description": "Application name"}
                        },
                        "required": ["workspace_id", "app_name"]
                    }
                }
            },
        ]


# Factory function for easy agent creation
async def create_sre_agent(
    agent_name: str = "sre-agent",
    model: str = "gpt-4o",
    auto_create: bool = True
) -> Optional[AzureAISREAgent]:
    """
    Factory function to create and initialize an Azure AI SRE Agent

    Args:
        agent_name: Name for the agent
        model: Model deployment name
        auto_create: Automatically create agent and thread

    Returns:
        Initialized AzureAISREAgent instance or None
    """
    agent = AzureAISREAgent(agent_name=agent_name)

    if not agent.is_available():
        logger.warning("⚠️ Azure AI Agent Service not available")
        return None

    if auto_create:
        await agent.create_agent(model=model)
        await agent.create_thread()

    return agent
