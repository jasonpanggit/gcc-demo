"""
MCP Orchestrator Agent - Agentic Azure MCP Server Orchestration

An advanced agentic AI system that autonomously leverages Azure MCP Server tools 
to accomplish complex cloud management tasks.

Key Capabilities:
- 🤖 Autonomous reasoning using ReAct pattern (Reasoning + Acting)
- 🔄 Multi-step workflow execution with self-correction
- 🧠 Strategic planning and task decomposition
- 🔧 Intelligent tool selection and orchestration
- 👁️ Observation and reflection on results
- 🎯 Adaptive strategy adjustment based on outcomes
- ✨ Comprehensive Azure resource management

The agent operates through continuous reasoning loops:
1. REASONING: Analyzes the task and plans approach
2. ACTION: Executes tools based on reasoning
3. OBSERVATION: Processes tool results and reflects
4. ADAPTATION: Adjusts strategy if needed and continues

This creates truly autonomous behavior where the agent can:
- Break down complex requests into manageable steps
- Learn from tool failures and retry with corrections
- Chain multiple tools to build comprehensive answers
- Provide detailed reasoning traces for transparency
"""
import os
import asyncio
import json
import uuid
import traceback
import re
import copy
from typing import Dict, List, Any, Optional, Tuple
PLACEHOLDER_PATTERN = re.compile(r"<([a-z0-9][a-z0-9_\-]*)>", re.IGNORECASE)

from datetime import datetime

# Initialize logger
try:
    from utils import get_logger
    from utils.cache_stats_manager import cache_stats_manager
    logger = get_logger(__name__)
except Exception:
    import logging
    logger = logging.getLogger(__name__)
    class DummyCacheStatsManager:
        def record_agent_request(self, *args, **kwargs): pass
    cache_stats_manager = DummyCacheStatsManager()

# Azure OpenAI imports
try:
    from openai import AsyncAzureOpenAI
    from azure.identity import DefaultAzureCredential, get_bearer_token_provider
    AZURE_OPENAI_AVAILABLE = True
except ImportError as e:
    logger.error(f"Azure OpenAI imports failed: {e}")
    AZURE_OPENAI_AVAILABLE = False

# Azure MCP Client (stdio - direct process communication)
try:
    from utils.azure_mcp_client import get_azure_mcp_client
except ImportError as e:
    logger.error(f"Azure MCP client import failed: {e}")

try:
    from utils.azure_cli_executor_client import get_cli_executor_client
except ImportError as e:
    logger.error(f"Azure CLI executor client import failed: {e}")
    get_cli_executor_client = None

try:
    from .tool_metadata import get_tool_metadata_manager
except ImportError:
    try:
        from tool_metadata import get_tool_metadata_manager  # type: ignore
    except Exception:
        get_tool_metadata_manager = None  # type: ignore


class MCPOrchestratorAgent:
    """
    Agentic Orchestrator for Azure MCP Server - Autonomous Cloud Management
    
    An intelligent agent that autonomously manages Azure resources through 
    the Model Context Protocol (MCP) using advanced agentic AI patterns.
    
    Architecture:
    - Implements ReAct (Reasoning + Acting) pattern for autonomous decision-making
    - Maintains conversation context and reasoning history
    - Self-corrects on tool failures with adaptive retry strategies
    - Executes multi-step workflows through iterative reasoning loops
    - Provides transparency through detailed reasoning traces
    
    Agentic Capabilities:
    - Strategic Planning: Analyzes tasks and creates execution plans
    - Tool Orchestration: Intelligently selects and chains MCP tools
    - Self-Correction: Detects failures and adjusts approach
    - Reflection: Evaluates results and determines next steps
    - Adaptation: Modifies strategy based on observations
    
    Usage:
        orchestrator = await get_mcp_orchestrator()
        
        # Simple execution
        result = await orchestrator.process_message("List my storage accounts")
        
        # With reasoning explanation
        result = await orchestrator.explain_reasoning("Analyze my Azure costs")
        
        # Create execution plan
        plan = await orchestrator.create_plan("Optimize my infrastructure")
        
        # Analyze task complexity
        analysis = await orchestrator.analyze_task_complexity("Migrate to containers")
    
    The agent operates continuously, reasoning about each step and adapting
    its approach until it has sufficient information to provide a comprehensive
    response to the user's request.
    """
    
    def __init__(self):
        self.session_id = str(uuid.uuid4())
        self.start_time = datetime.utcnow()
        self.agent_name = "mcp_orchestrator"
        
        # Conversation history (OpenAI messages format)
        self._messages: List[Dict[str, Any]] = []
        
        # Azure OpenAI client (lazy initialization)
        self._openai_client = None
        self._client_initialized = False
        
        # Azure MCP client
        self._mcp_client = None
        self._available_tools = []
        self._tool_definitions = []
        self._tool_schema_index = {}
        self._available_tool_names = set()
        self._parameter_hint_cache = {}
        self._pending_parameter_requests: Dict[str, Dict[str, Any]] = {}
        self._paginated_results: Dict[str, Dict[str, Any]] = {}
        self._last_paginated_id: Optional[str] = None
        self._pagination_page_size = 10

        # Azure CLI executor integration (lazy initialization)
        self._cli_executor_client = None
        self._cli_executor_tools_loaded = False
        self._cli_executor_tool_names = set()
        
        # Agent communication queue for real-time UI streaming
        self.communication_queue = asyncio.Queue()
        # Buffer to store recent communications (for late-connecting SSE streams)
        self.communication_buffer = []
        self.max_buffer_size = 100

        self._tool_metadata_manager = get_tool_metadata_manager() if callable(get_tool_metadata_manager) else None
        
        logger.info(f"🚀 MCP Orchestrator initialized (session: {self.session_id})")
    
    async def _push_communication(self, comm_type: str, content: str, **kwargs):
        """Push communication event to queue for real-time UI streaming."""
        try:
            event = {
                'type': comm_type,
                'content': content,
                'timestamp': datetime.utcnow().isoformat(),
                **kwargs
            }
            # Add to queue for active listeners
            await self.communication_queue.put(event)
            
            # Also buffer for late-connecting SSE streams
            self.communication_buffer.append(event)
            if len(self.communication_buffer) > self.max_buffer_size:
                self.communication_buffer.pop(0)  # Remove oldest
                
            logger.info(f"📡 Pushed {comm_type} event to queue (qsize: {self.communication_queue.qsize()}, buffer: {len(self.communication_buffer)})")
        except Exception as e:
            logger.debug(f"Failed to push communication to queue: {e}")
    
    async def _ensure_mcp_client_initialized(self):
        """Ensure Azure MCP client is initialized"""
        if self._mcp_client is None:
            try:
                self._mcp_client = await get_azure_mcp_client()
                self._available_tools = self._mcp_client.get_available_tools()
                self._index_tool_schemas()
                logger.info(f"✅ Azure MCP client initialized with {len(self._available_tools)} tools")
            except Exception as e:
                logger.error(f"❌ Failed to initialize Azure MCP client: {e}")
                raise

        """Load and register Azure CLI executor MCP tools if available"""        
        await self._ensure_cli_executor_client_initialized()
    
    def _should_enable_cli_executor(self, user_message: Optional[str]) -> bool:
        """Determine whether the Azure CLI executor should be enabled for this turn."""
        if not user_message:
            return False
        lowered = user_message.lower()

        if "using azure cli executor tool" in lowered:
            return True

        if "execute azure cli command" in lowered:
            return True

        if re.search(r"\baz\s+[a-z0-9-]", lowered):
            return True

        return False

    async def _ensure_cli_executor_client_initialized(self) -> None:
        """Ensure the standalone Azure CLI executor MCP server is available and registered."""
        if self._cli_executor_tools_loaded:
            return

        if get_cli_executor_client is None:
            logger.warning("Azure CLI executor client is unavailable; CLI execution tools will not be registered.")
            self._cli_executor_tools_loaded = True
            return

        try:
            client = await get_cli_executor_client()
        except Exception as exc:  # pylint: disable=broad-except
            logger.error(f"Failed to initialize Azure CLI executor client: {exc}")
            return

        self._cli_executor_client = client
        cli_tools = client.get_available_tools()
        if not cli_tools:
            logger.warning("Azure CLI executor client reported no tools; skipping registration.")
            self._cli_executor_tools_loaded = True
            return

        existing_names = {
            tool.get("function", {}).get("name")
            for tool in self._available_tools
            if isinstance(tool, dict)
        }

        added = 0
        for tool in cli_tools:
            func = tool.get("function", {}) if isinstance(tool, dict) else {}
            name = func.get("name") if isinstance(func, dict) else None
            if not name:
                continue
            if name not in existing_names:
                self._available_tools.append(tool)
                existing_names.add(name)
                added += 1
            self._cli_executor_tool_names.add(name)

        if added:
            self._index_tool_schemas()
            if self._client_initialized:
                self._tool_definitions = self._create_openai_tool_definitions()
            logger.info("✅ Registered %d Azure CLI executor MCP tool(s)", added)

        self._cli_executor_tools_loaded = True

    def _select_tool_definitions_for_message(self, user_message: Optional[str]) -> List[Dict[str, Any]]:
        """Return the tool definitions that should be exposed for this specific user message."""
        if not self._tool_definitions:
            return []

        if not self._cli_executor_tool_names:
            return self._tool_definitions

        if self._should_enable_cli_executor(user_message):
            return self._tool_definitions

        filtered: List[Dict[str, Any]] = []
        for tool_def in self._tool_definitions:
            func = tool_def.get("function", {})
            name = func.get("name") if isinstance(func, dict) else None
            if name in self._cli_executor_tool_names:
                continue
            filtered.append(tool_def)

        return filtered

    async def _ensure_openai_client_initialized(self):
        """Lazy initialization of Azure OpenAI client"""
        if self._client_initialized:
            return
        
        if not AZURE_OPENAI_AVAILABLE:
            raise RuntimeError("Azure OpenAI SDK is not available")
        
        try:
            # Ensure MCP client is ready and get tool definitions
            await self._ensure_mcp_client_initialized()
            self._tool_definitions = self._create_openai_tool_definitions()
            
            # Azure OpenAI configuration
            azure_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
            deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o-mini")
            api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2024-08-01-preview")
            
            if not azure_endpoint:
                raise ValueError("AZURE_OPENAI_ENDPOINT environment variable not set")
            
            # Create Azure AD token provider for authentication
            credential = DefaultAzureCredential()
            token_provider = get_bearer_token_provider(
                credential, 
                "https://cognitiveservices.azure.com/.default"
            )
            
            # Create Azure OpenAI client
            self._openai_client = AsyncAzureOpenAI(
                azure_endpoint=azure_endpoint,
                azure_deployment=deployment,
                api_version=api_version,
                azure_ad_token_provider=token_provider
            )
            
            # Initialize system message with agentic reasoning capabilities
            self._messages = [{
                "role": "system",
                "content": """You are an advanced agentic Azure cloud expert assistant with autonomous reasoning capabilities and direct access to the Azure MCP Server toolkit.

You have access to ALL Azure MCP Server tools covering:
- Azure resource management (resource groups, subscriptions, resources)
- Storage (accounts, containers, blobs, tables)
- Compute (VMs, App Services, Functions, AKS)
- Databases (SQL, Cosmos DB, MySQL, PostgreSQL, Redis)
- Networking (Event Grid, Event Hubs, Service Bus, SignalR)
- Security (Key Vault, RBAC, Confidential Ledger)
- Monitoring (Azure Monitor, Application Insights, Log Analytics)
- AI/ML (AI Foundry, AI Search, AI Speech)
- DevOps (Deploy, CLI, Bicep, Terraform)
- And many more Azure services

🤖 AGENTIC REASONING FRAMEWORK (ReAct Pattern):

You operate using the Reasoning-Action-Observation loop:

1. REASONING (Think): Before acting, reason about:
   - What is the user asking for?
   - What information do I need?
   - What tools are most appropriate?
   - What is my step-by-step plan?
   - What could go wrong?

2. ACTION (Act): Execute your plan by:
   - Calling tools directly (no narration, just call)
   - Requesting multiple tools if needed
   - Using tool results to inform next steps

3. OBSERVATION (Reflect): After tool results:
   - Did I get the expected information?
   - Is this sufficient to answer the user?
   - Do I need to adjust my approach?
   - Should I call additional tools?

4. ADAPTATION (Self-correct):
   - If tool fails: diagnose why and retry with corrections
   - If results incomplete: identify gaps and fill them
   - If answer unclear: gather more context
   - If approach ineffective: switch strategies

MULTI-STEP AUTONOMOUS WORKFLOWS:

For complex requests, break them into logical steps:
- Step 1: Gather foundational information (e.g., list resources)
- Step 2: Deep dive into specific items (e.g., get details)
- Step 3: Analyze and correlate data
- Step 4: Synthesize comprehensive response

Example workflow for "analyze my storage accounts":
1. [Reason] Need to list storage accounts first, then analyze each
2. [Act] Call tool to list storage accounts
3. [Observe] Got 3 storage accounts
4. [Reason] Should get details for each account
5. [Act] Call tools to get details for each account
6. [Observe] Got performance, configuration, and cost data
7. [Reason] Can now provide comprehensive analysis
8. [Act] Synthesize findings into actionable insights

INTELLIGENT TOOL SELECTION:

- Prioritize tools that provide most complete information
- Chain tools when one result informs the next
- Use parallel calls for independent queries
- Fall back to alternatives if primary tool fails

EXECUTION RULES:
1. Call tools IMMEDIATELY without explaining your intent
2. Use multiple tool calls to build complete picture
3. Self-correct when tools fail or results are unexpected
4. Only provide final response when you have sufficient information
5. Be transparent about limitations if tools can't fulfill request

FORMATTING RULES:
1. DO NOT indent responses - start all text at column 0
2. NO code blocks (```), quotes, or wrapper characters
3. Present data directly and cleanly
4. Use tables for structured data
5. Keep responses left-aligned and professional

PROACTIVE INTELLIGENCE:

- Anticipate user needs (e.g., if they ask about VMs, offer related info like network, disks)
- Provide actionable insights, not just raw data
- Suggest optimizations or potential issues
- Include relevant context without being asked

Remember: You are AUTONOMOUS. Make intelligent decisions, adapt to challenges, and deliver comprehensive results through multi-step reasoning and tool orchestration."""
            }]
            
            self._client_initialized = True
            logger.info(f"✅ Azure OpenAI client initialized with {len(self._tool_definitions)} MCP tools")
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize Azure OpenAI client: {e}")
            logger.error(traceback.format_exc())
            raise
    
    def _create_openai_tool_definitions(self) -> List[Dict[str, Any]]:
        """
        Create OpenAI function definitions from ALL available MCP tools.
        Registers all tools to provide comprehensive Azure resource management capabilities.
        """
        tool_definitions = []
        
        for tool in self._available_tools:
            func_def = tool.get("function", {})
            tool_name = func_def.get("name", "")
            
            # Convert MCP tool definition to OpenAI function format
            openai_tool = {
                "type": "function",
                "function": {
                    "name": tool_name,
                    "description": func_def.get("description", ""),
                    "parameters": func_def.get("parameters", {
                        "type": "object",
                        "properties": {},
                        "required": []
                    })
                }
            }
            
            tool_definitions.append(openai_tool)
            logger.debug(f"Registered OpenAI tool: {tool_name}")
        
        logger.info(f"✅ Registered {len(tool_definitions)} MCP tools with Azure OpenAI")
        return tool_definitions

    def _index_tool_schemas(self):
        """Create quick lookup indexes for tool schemas and names."""
        self._tool_schema_index = {}
        self._available_tool_names = set()
        for tool in self._available_tools:
            func = tool.get("function", {})
            name = func.get("name")
            if not name:
                continue
            self._available_tool_names.add(name)
            params = func.get("parameters") or {}
            self._tool_schema_index[name] = params

    def _tool_exists(self, tool_name: str) -> bool:
        """Check if a tool exists in the available MCP tools."""
        return tool_name in self._available_tool_names

    def _get_tool_schema(self, tool_name: str) -> Dict[str, Any]:
        """Retrieve JSON schema for a specific tool."""
        return self._tool_schema_index.get(tool_name, {})

    def _get_operation_metadata(self, tool_name: str) -> Optional[Dict[str, Any]]:
        if not self._tool_metadata_manager:
            return None
        try:
            return self._tool_metadata_manager.get_operation_by_tool_name(tool_name)
        except Exception:
            return None

    def _get_metadata_parameters(self, tool_name: str) -> Dict[str, Dict[str, Any]]:
        operation = self._get_operation_metadata(tool_name)
        if not operation:
            return {}
        metadata_params: Dict[str, Dict[str, Any]] = {}
        for param in operation.get("parameters", []) or []:
            name = param.get("name")
            if not name:
                continue
            metadata_params[name.lower()] = param
        return metadata_params

    def _get_required_parameters(self, tool_name: str) -> List[str]:
        schema = self._get_tool_schema(tool_name)
        required = schema.get("required", [])
        return required if isinstance(required, list) else []

    def _value_contains_placeholder(self, value: Any) -> bool:
        if value is None:
            return False
        if isinstance(value, str):
            return bool(PLACEHOLDER_PATTERN.search(value))
        if isinstance(value, list):
            return any(self._value_contains_placeholder(item) for item in value)
        if isinstance(value, dict):
            return any(self._value_contains_placeholder(item) for item in value.values())
        return False

    def _extract_placeholders(self, value: Any) -> List[str]:
        if value is None:
            return []
        tokens: List[str] = []
        if isinstance(value, str):
            tokens.extend(match.lower() for match in PLACEHOLDER_PATTERN.findall(value))
        elif isinstance(value, list):
            for item in value:
                tokens.extend(self._extract_placeholders(item))
        elif isinstance(value, dict):
            for item in value.values():
                tokens.extend(self._extract_placeholders(item))
        seen = set()
        ordered: List[str] = []
        for token in tokens:
            if token not in seen:
                seen.add(token)
                ordered.append(token)
        return ordered

    def _argument_has_value(self, arguments: Dict[str, Any], parameter: str) -> bool:
        if parameter not in arguments:
            return False
        value = arguments.get(parameter)
        if value is None:
            return False
        if isinstance(value, str) and not value.strip():
            return False
        return True

    def _resolve_env_default(self, parameter: str) -> Optional[str]:
        """Resolve common parameter defaults from environment variables."""
        normalized = parameter.lower()
        env_map = {
            "subscriptionid": ["SUBSCRIPTION_ID", "AZURE_SUBSCRIPTION_ID"],
            "tenantid": ["AZURE_TENANT_ID", "TENANT_ID"],
            "resourcegroup": ["RESOURCE_GROUP_NAME", "AZURE_RESOURCE_GROUP", "DEFAULT_RESOURCE_GROUP"],
            "resourcegroupname": ["RESOURCE_GROUP_NAME", "AZURE_RESOURCE_GROUP", "DEFAULT_RESOURCE_GROUP"],
            "location": ["AZURE_LOCATION", "LOCATION", "DEFAULT_LOCATION"],
            "region": ["AZURE_REGION", "REGION", "DEFAULT_REGION"],
            "workspaceid": ["AZURE_WORKSPACE_ID", "LOG_ANALYTICS_WORKSPACE_ID"],
            "project": ["AZURE_PROJECT_NAME", "PROJECT_NAME"],
            "subscription": ["SUBSCRIPTION_ID", "AZURE_SUBSCRIPTION_ID"],
            "tenant": ["AZURE_TENANT_ID", "TENANT_ID"],
        }
        for key, env_vars in env_map.items():
            if key in normalized:
                for env_var in env_vars:
                    env_value = os.getenv(env_var)
                    if env_value:
                        return env_value
        return None

    def _get_recent_user_message(self) -> str:
        """Return the most recent user message for contextual parameter inference."""
        for message in reversed(self._messages):
            if message.get("role") == "user":
                return str(message.get("content", ""))
        return ""

    def _is_azure_best_practices_tool(self, tool_name: str) -> bool:
        if not tool_name:
            return False
        normalized = tool_name.replace("_", "-").lower()
        return "azure-best-practices" in normalized and "get-best-practices" in normalized

    def _normalize_azure_best_practices_resource(self, value: str) -> Optional[str]:
        if not value:
            return None
        compact = re.sub(r"[\s_-]+", "", value.lower())
        mapping = {
            "general": "general",
            "azurefunctions": "azurefunctions",
            "azurefunction": "azurefunctions",
            "functions": "azurefunctions",
            "function": "azurefunctions",
            "functionapp": "azurefunctions",
            "functionapps": "azurefunctions",
            "staticwebapp": "static-web-app",
            "staticwebapps": "static-web-app",
            "staticapp": "static-web-app",
            "staticapps": "static-web-app",
            "swa": "static-web-app"
        }
        return mapping.get(compact)

    def _normalize_azure_best_practices_action(self, value: str) -> Optional[str]:
        if not value:
            return None
        compact = re.sub(r"[\s_-]+", "", value.lower())
        mapping = {
            "codegeneration": "code-generation",
            "codegen": "code-generation",
            "code": "code-generation",
            "deployment": "deployment",
            "deploy": "deployment",
            "release": "deployment",
            "publish": "deployment",
            "golive": "deployment",
            "all": "all"
        }
        return mapping.get(compact)

    def _infer_azure_best_practices_parameters(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Infer required parameters for the Azure best practices tool using doc guidance."""
        if not isinstance(arguments, dict):
            return {}

        user_message = self._get_recent_user_message()
        user_lower = user_message.lower()

        wants_deployment = any(keyword in user_lower for keyword in ["deployment", "deploy", "deploying", "release", "publish", "go-live", "go live"])
        lifecycle_phrases = [
            "end-to-end",
            "full lifecycle",
            "full life cycle",
            "code and deployment",
            "both code and deployment",
            "full guidance",
            "complete guidance",
            "all stages"
        ]
        wants_full_cycle = any(phrase in user_lower for phrase in lifecycle_phrases)

        resource_candidate = None
        if self._argument_has_value(arguments, "resource"):
            candidate = str(arguments.get("resource", "")).strip()
            normalized = self._normalize_azure_best_practices_resource(candidate)
            if normalized:
                resource_candidate = normalized
            else:
                resource_candidate = "general"
        else:
            static_keywords = ["static web app", "static-web app", "static web apps", "staticwebapp", "swa"]
            function_keywords = ["azure function", "azure functions", "function app", "function apps", "function-app", "functionapp", "functionapps"]
            if any(keyword in user_lower for keyword in static_keywords):
                resource_candidate = "static-web-app"
            elif any(keyword in user_lower for keyword in function_keywords):
                resource_candidate = "azurefunctions"
            else:
                resource_candidate = "general"

        action_candidate = None
        if self._argument_has_value(arguments, "action"):
            candidate = str(arguments.get("action", "")).strip()
            normalized = self._normalize_azure_best_practices_action(candidate)
            if normalized:
                action_candidate = normalized
            else:
                action_candidate = "code-generation"
        else:
            if resource_candidate == "static-web-app" and wants_full_cycle:
                action_candidate = "all"
            elif wants_deployment:
                action_candidate = "deployment"
            else:
                action_candidate = "code-generation"

        if resource_candidate != "static-web-app" and action_candidate == "all":
            action_candidate = "deployment" if wants_deployment else "code-generation"

        if resource_candidate == "static-web-app" and action_candidate not in {"code-generation", "deployment", "all"}:
            action_candidate = "code-generation"

        metadata_params = self._get_metadata_parameters(tool_name)
        if metadata_params:
            resource_meta = metadata_params.get("resource")
            if resource_meta:
                options = resource_meta.get("options")
                if isinstance(options, list) and options and resource_candidate not in options:
                    resource_candidate = options[0]
            action_meta = metadata_params.get("action")
            if action_meta:
                options = action_meta.get("options")
                if isinstance(options, list) and options and action_candidate not in options:
                    action_candidate = options[0]

        updates: Dict[str, Any] = {}

        current_resource = str(arguments.get("resource", "")).strip() if isinstance(arguments.get("resource"), str) else arguments.get("resource")
        if resource_candidate and (not self._argument_has_value(arguments, "resource") or current_resource != resource_candidate):
            updates["resource"] = resource_candidate

        current_action = str(arguments.get("action", "")).strip() if isinstance(arguments.get("action"), str) else arguments.get("action")
        if action_candidate and (not self._argument_has_value(arguments, "action") or current_action != action_candidate):
            updates["action"] = action_candidate

        return updates

    def _infer_related_list_tools(self, tool_name: str) -> List[str]:
        """Infer related listing tools based on naming conventions."""
        if not tool_name:
            return []
        parts = tool_name.split('-')
        if len(parts) < 2:
            return []
        candidates = []
        base = '-'.join(parts[:-1])
        if parts[-1] != "list":
            candidates.append(f"{base}-list")
        # Also consider pluralized variants by adding '-list' directly if not already
        if not tool_name.endswith("-list"):
            candidates.append(f"{tool_name}-list")
        return [c for c in candidates if c != tool_name]

    def _get_parameter_helper_tools(self, tool_name: str, parameter: str) -> List[str]:
        """Determine helper tools that can provide values for a parameter."""
        param_lower = parameter.lower()
        helpers: List[str] = []

        if "subscription" in param_lower:
            helpers.extend([
                "azure_subscriptions-list",
                "azure_resources-subscriptions-list",
            ])
        if "tenant" in param_lower:
            helpers.append("azure_tenants-list")
        if "resourcegroup" in param_lower:
            helpers.append("azure_resource-groups-list")
        if "workspace" in param_lower:
            helpers.append("azure_monitoring-workspaces-list")
        if "location" in param_lower or "region" in param_lower:
            helpers.extend([
                "azure_resources-available-locations-list",
                "azure_locations-list",
            ])

        helpers.extend(self._infer_related_list_tools(tool_name))

        # Preserve order but remove duplicates
        seen = set()
        ordered_helpers = []
        for helper in helpers:
            if helper and helper not in seen:
                seen.add(helper)
                ordered_helpers.append(helper)
        return ordered_helpers

    def _build_helper_arguments(
        self,
        parameter: str,
        supplied_arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Reuse already known arguments when querying helper tools."""
        helper_args = {}
        for key, value in supplied_arguments.items():
            if key == parameter:
                continue
            if value is None:
                continue
            if isinstance(value, str) and not value.strip():
                continue
            helper_args[key] = value
        return helper_args

    def _normalize_helper_content(self, content: Any) -> List[Any]:
        """Normalize helper tool content into JSON-serializable items."""
        normalized: List[Any] = []
        if isinstance(content, list):
            source = content
        else:
            source = [content]

        for item in source:
            if isinstance(item, str):
                text = item.strip()
                if text:
                    normalized.append(text)
            elif isinstance(item, dict):
                normalized.append(item)
            else:
                try:
                    normalized.append(json.loads(item))  # type: ignore[arg-type]
                except Exception:
                    normalized.append(str(item))

        # Limit to avoid overwhelming the model
        return normalized[:10]

    async def _discover_parameter_values(
        self,
        tool_name: str,
        parameter: str,
        supplied_arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Attempt to discover candidate values for a missing parameter."""
        cache_key = f"{tool_name}:{parameter}"
        if cache_key in self._parameter_hint_cache:
            return self._parameter_hint_cache[cache_key]

        helpers = self._get_parameter_helper_tools(tool_name, parameter)
        helper_arguments = self._build_helper_arguments(parameter, supplied_arguments)

        for helper_tool in helpers:
            if not self._tool_exists(helper_tool):
                continue
            try:
                logger.info(
                    f"🔍 Discovering values for '{parameter}' using helper tool '{helper_tool}'"
                )
                helper_result = await self._mcp_client.call_tool(helper_tool, helper_arguments)
            except Exception as helper_error:
                logger.warning(
                    f"⚠️ Helper tool '{helper_tool}' failed while resolving '{parameter}': {helper_error}"
                )
                continue

            if helper_result.get("success"):
                normalized = self._normalize_helper_content(helper_result.get("content", []))
                if normalized:
                    hint = {
                        "parameter": parameter,
                        "source_tool": helper_tool,
                        "candidates": normalized
                    }
                    self._parameter_hint_cache[cache_key] = hint
                    return hint
            else:
                hint = {
                    "parameter": parameter,
                    "source_tool": helper_tool,
                    "error": helper_result.get("error")
                }
                self._parameter_hint_cache[cache_key] = hint
                return hint

        return {}

    async def _resolve_tool_arguments(
        self,
        tool_name: str,
        supplied_arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Auto-resolve or suggest required parameters before calling a tool."""
        arguments = dict(supplied_arguments)
        pending_detail = self._pending_parameter_requests.get(tool_name)
        if pending_detail:
            user_supplied = pending_detail.get("user_supplied") or {}
            if isinstance(user_supplied, dict):
                for key, value in user_supplied.items():
                    if not self._argument_has_value(arguments, key):
                        arguments[key] = value
            pending_detail.setdefault("arguments", {}).update(arguments)
        placeholder_params: Dict[str, List[str]] = {}
        for parameter, value in list(arguments.items()):
            if not self._argument_has_value(arguments, parameter):
                continue
            placeholders = self._extract_placeholders(value)
            if placeholders:
                placeholder_params[parameter] = placeholders
                arguments[parameter] = None

        if pending_detail and placeholder_params:
            existing_map = pending_detail.setdefault("placeholder_parameters", {})
            if isinstance(existing_map, dict):
                for key, tokens in placeholder_params.items():
                    existing_map.setdefault(key, tokens)

        required_params = self._get_required_parameters(tool_name)
        if not required_params:
            return {
                "status": "complete",
                "arguments": arguments,
                "missing": [],
                "auto_filled": {},
                "suggestions": {},
                "message": "",
                "placeholder_parameters": placeholder_params
            }

        auto_filled: Dict[str, Any] = {}
        suggestions: Dict[str, Any] = {}
        metadata_params = self._get_metadata_parameters(tool_name)

        # First attempt environment defaults
        for parameter in required_params:
            if self._argument_has_value(arguments, parameter):
                continue
            env_value = self._resolve_env_default(parameter)
            if env_value is not None:
                arguments[parameter] = env_value
                auto_filled[parameter] = env_value

        for parameter in required_params:
            if self._argument_has_value(arguments, parameter):
                continue
            metadata_param = metadata_params.get(parameter.lower()) if metadata_params else None
            if metadata_param:
                options = metadata_param.get("options")
                if isinstance(options, list) and len(options) == 1:
                    value = options[0]
                    arguments[parameter] = value
                    auto_filled[parameter] = value

        if self._is_azure_best_practices_tool(tool_name):
            inferred = self._infer_azure_best_practices_parameters(tool_name, arguments)
            for parameter, value in inferred.items():
                if value is None:
                    continue
                if not self._argument_has_value(arguments, parameter) or arguments.get(parameter) != value:
                    arguments[parameter] = value
                    auto_filled[parameter] = value

        missing = [p for p in required_params if not self._argument_has_value(arguments, p)]

        # Gather suggestions via helper tools
        for parameter in missing:
            discovery = await self._discover_parameter_values(tool_name, parameter, arguments)
            if discovery:
                suggestions[parameter] = discovery
            elif metadata_params:
                metadata_param = metadata_params.get(parameter.lower())
                if metadata_param:
                    options = metadata_param.get("options")
                    if isinstance(options, list) and options:
                        suggestions.setdefault(parameter, {
                            "parameter": parameter,
                            "source": "documentation",
                            "candidates": options
                        })

        remaining_missing = [p for p in required_params if not self._argument_has_value(arguments, p)]

        if pending_detail:
            pending_detail["missing_parameters"] = remaining_missing
            pending_detail["auto_filled"] = auto_filled
            pending_detail["suggestions"] = suggestions
            pending_detail["arguments"] = arguments

        if auto_filled:
            await self._push_communication(
                "context",
                f"Auto-filled parameters for {tool_name}: {', '.join(auto_filled.keys())}",
                tool=tool_name,
                auto_filled=auto_filled
            )

        if suggestions:
            await self._push_communication(
                "context",
                f"Identified candidate values for {tool_name} parameters",
                tool=tool_name,
                suggestions=suggestions
            )

        if not remaining_missing:
            if pending_detail:
                self._pending_parameter_requests.pop(tool_name, None)
            return {
                "status": "complete",
                "arguments": arguments,
                "missing": [],
                "auto_filled": auto_filled,
                "suggestions": suggestions,
                "message": "",
                "placeholder_parameters": placeholder_params
            }

        # Prepare descriptive message for missing params
        schema = self._get_tool_schema(tool_name)
        properties = schema.get("properties", {}) if isinstance(schema, dict) else {}
        missing_details = []
        for parameter in remaining_missing:
            param_info = properties.get(parameter, {}) if isinstance(properties, dict) else {}
            description = param_info.get("description") if isinstance(param_info, dict) else None
            if description:
                missing_details.append(f"{parameter}: {description}")
            else:
                missing_details.append(parameter)

        message = (
            "The following required parameters are still missing: "
            + ", ".join(missing_details)
        )

        if placeholder_params:
            placeholder_notice = ", ".join(sorted(placeholder_params.keys()))
            message = (
                "Detected placeholder values for: "
                f"{placeholder_notice}. "
                + message
            )

        return {
            "status": "incomplete",
            "arguments": arguments,
            "missing": remaining_missing,
            "auto_filled": auto_filled,
            "suggestions": suggestions,
            "message": message,
            "placeholder_parameters": placeholder_params
        }
    
    def _escape_markdown_cell(self, value: Any) -> str:
        """Escape markdown table cell content."""
        if value is None:
            return ""
        text = str(value)
        return text.replace("|", "\\|").replace("\n", " ").replace("\r", " ")

    def _format_table(self, data: Any, headers: Optional[List[str]] = None) -> str:
        """Format a list of dicts or tabular data as a Markdown table."""
        if not isinstance(data, list) or not data:
            return str(data)

        if not headers:
            if isinstance(data[0], dict):
                headers = list(data[0].keys())
            else:
                return str(data)

        escaped_headers = [self._escape_markdown_cell(header) for header in headers]
        header_line = "| " + " | ".join(escaped_headers) + " |"
        separator_line = "| " + " | ".join(["---"] * len(headers)) + " |"

        body_lines = []
        for row in data:
            if isinstance(row, dict):
                values = [row.get(h, "") for h in headers]
            elif isinstance(row, (list, tuple)):
                values = list(row)
            else:
                values = [row]
            escaped_values = [self._escape_markdown_cell(value) for value in values]
            body_lines.append("| " + " | ".join(escaped_values) + " |")

        return "\n".join([header_line, separator_line, *body_lines])

    def _prepare_paginated_content(self, content: Any) -> Optional[Dict[str, Any]]:
        page_size = self._pagination_page_size

        def build_pages_from_rows(rows: List[Dict[str, Any]], headers: Optional[List[str]] = None) -> List[Dict[str, Any]]:
            items: List[Dict[str, Any]] = []
            total_items = len(rows)
            if total_items <= page_size:
                return []
            header_values = headers or (list(rows[0].keys()) if rows and isinstance(rows[0], dict) else None)
            for start in range(0, total_items, page_size):
                subset = rows[start:start + page_size]
                table_text = self._format_table(subset, header_values)
                items.append({
                    "text": table_text,
                    "start_index": start + 1,
                    "end_index": start + len(subset)
                })
            return items

        if isinstance(content, list):
            total_items = len(content)
            if total_items <= page_size:
                return None

            if content and all(isinstance(item, dict) for item in content):
                pages = build_pages_from_rows(content)
                if not pages:
                    return None
                return {
                    "pages": pages,
                    "total_items": total_items,
                    "render_mode": "table"
                }

            stringified = [self._format_text_block(item) if isinstance(item, str) else str(item) for item in content]
            if len(stringified) <= page_size:
                return None
            pages: List[Dict[str, Any]] = []
            for start in range(0, total_items, page_size):
                subset = stringified[start:start + page_size]
                pages.append({
                    "text": "\n".join(subset).strip(),
                    "start_index": start + 1,
                    "end_index": start + len(subset)
                })
            if pages:
                return {
                    "pages": pages,
                    "total_items": total_items,
                    "render_mode": "list"
                }
            return None

        if isinstance(content, str):
            structured = self._extract_structured_from_string(content)
            if structured:
                headers, rows = structured
                if len(rows) <= page_size:
                    return None
                pages = build_pages_from_rows(rows, headers)
                if pages:
                    return {
                        "pages": pages,
                        "total_items": len(rows),
                        "render_mode": "table"
                    }
        return None

    def _register_paginated_result(
        self,
        tool_name: str,
        pages: List[Dict[str, Any]],
        total_items: int,
        render_mode: str
    ) -> str:
        page_id = str(uuid.uuid4())
        self._paginated_results[page_id] = {
            "tool": tool_name,
            "pages": pages,
            "total_items": total_items,
            "render_mode": render_mode,
            "total_pages": len(pages),
            "page_size": self._pagination_page_size,
            "current_page": 1,
            "created_at": datetime.utcnow()
        }
        self._last_paginated_id = page_id

        if len(self._paginated_results) > 5:
            ordered = sorted(
                self._paginated_results.items(),
                key=lambda item: item[1].get("created_at", datetime.utcnow())
            )
            for stale_id, _ in ordered[:-5]:
                if stale_id != page_id:
                    self._paginated_results.pop(stale_id, None)

        return page_id

    def _compose_paginated_page(
        self,
        page_id: str,
        page_number: int,
        resolution: Optional[Dict[str, Any]] = None,
        include_metadata: bool = False
    ) -> Optional[str]:
        entry = self._paginated_results.get(page_id)
        if not entry:
            return None

        total_pages = entry.get("total_pages", 0)
        if total_pages <= 0:
            return None

        if page_number < 1 or page_number > total_pages:
            return None

        page_info = entry["pages"][page_number - 1]
        start_index = page_info.get("start_index", 1)
        end_index = page_info.get("end_index", start_index)
        total_items = entry.get("total_items", 0)
        tool_name = entry.get("tool", "tool")

        header_lines = [
            f"{tool_name} results: items {start_index}-{end_index} of {total_items}",
            ""
        ]

        body_text = page_info.get("text", "")
        body = "\n".join([*header_lines, body_text.strip()]) if body_text else "\n".join(header_lines)

        nav_lines = ["Navigation:"]
        if page_number > 1:
            nav_lines.append("- Reply with 'prev' or 'previous page' to see the prior page.")
        if page_number < total_pages:
            nav_lines.append(f"- Reply with 'next' or 'page {page_number + 1}' to continue.")
        nav_lines.append(f"- To jump directly, reply with 'page <number>' or 'page {page_id} <number>'.")

        composed = "\n\n".join([body.strip(), "\n".join(nav_lines)])

        entry["current_page"] = page_number

        if include_metadata and resolution is not None:
            return self._append_metadata_notice(composed, resolution)
        return composed

    def _maybe_create_paginated_payload(
        self,
        tool_name: str,
        content: Any,
        resolution: Dict[str, Any],
        raw_result: Dict[str, Any],
        resolved_arguments: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        paginated = self._prepare_paginated_content(content)
        if not paginated:
            return None

        pages = paginated.get("pages") or []
        if not pages:
            return None

        total_items = paginated.get("total_items", len(pages))
        render_mode = paginated.get("render_mode", "table")
        page_id = self._register_paginated_result(tool_name, pages, total_items, render_mode)

        first_page_text = self._compose_paginated_page(page_id, 1, resolution, include_metadata=True)
        if not first_page_text:
            return None

        return {
            "success": True,
            "tool": tool_name,
            "text": first_page_text,
            "raw_result": raw_result,
            "content": content,
            "arguments": resolved_arguments,
            "auto_filled": resolution.get("auto_filled"),
            "suggestions": resolution.get("suggestions"),
            "pagination": {
                "page_id": page_id,
                "current_page": 1,
                "total_pages": len(pages),
                "page_size": self._pagination_page_size,
                "total_items": total_items
            }
        }

    def _handle_paginated_user_request(self, user_message: str) -> Optional[Dict[str, Any]]:
        if not self._paginated_results:
            return None

        normalized = user_message.strip()
        if not normalized:
            return None

        lower_message = normalized.lower()

        page_id = None
        page_number = None

        explicit_match = re.search(r"page\s+([a-f0-9-]{8,})\s+(\d+)", lower_message)
        if explicit_match:
            page_id = explicit_match.group(1)
            page_number = int(explicit_match.group(2))

        if page_id and page_id not in self._paginated_results:
            page_id = None
            page_number = None

        if page_id is None:
            page_id = self._last_paginated_id

        if page_id is None or page_id not in self._paginated_results:
            return None

        entry = self._paginated_results[page_id]
        current_page = entry.get("current_page", 1)
        total_pages = entry.get("total_pages", 1)

        if page_number is None:
            if lower_message in {"next", "next page", "more", "show more"}:
                page_number = current_page + 1
            elif lower_message in {"prev", "previous", "previous page", "back"}:
                page_number = current_page - 1
            else:
                simple_match = re.search(r"page\s+(\d+)", lower_message)
                if simple_match:
                    page_number = int(simple_match.group(1))

        if page_number is None:
            return None

        if page_number < 1 or page_number > total_pages:
            return {
                "handled": True,
                "text": f"Page {page_number} is out of range. There are {total_pages} pages available.",
                "metadata": {
                    "pagination": {
                        "page_id": page_id,
                        "current_page": current_page,
                        "total_pages": total_pages
                    }
                }
            }

        page_text = self._compose_paginated_page(page_id, page_number, include_metadata=False)
        if not page_text:
            return None

        return {
            "handled": True,
            "text": page_text,
            "metadata": {
                "pagination": {
                    "page_id": page_id,
                    "current_page": page_number,
                    "total_pages": total_pages,
                    "page_size": entry.get("page_size"),
                    "total_items": entry.get("total_items")
                }
            }
        }

    def _try_parse_json_list(self, text: str) -> Optional[List[Dict[str, Any]]]:
        text = text.strip()
        if not text or not text.startswith('['):
            return None
        try:
            parsed = json.loads(text)
        except Exception:
            return None
        if isinstance(parsed, list) and parsed and all(isinstance(item, dict) for item in parsed):
            return parsed
        return None

    def _parse_markdown_table(self, text: str) -> Optional[tuple]:
        if '|' not in text:
            return None
        table_match = re.search(r'(\|.+\|(?:\r?\n\|[-:\s\|]+\|)(?:\r?\n\|.+\|)+)', text)
        if not table_match:
            return None
        table_block = table_match.group(1)
        lines = [line.strip() for line in table_block.strip().splitlines() if line.strip()]
        if len(lines) < 2:
            return None
        header_line = lines[0].strip('|')
        headers = [col.strip() for col in header_line.split('|') if col.strip()]
        if not headers:
            return None
        rows: List[Dict[str, Any]] = []
        for line in lines[1:]:
            stripped = line.strip()
            if not stripped:
                continue
            separator_test = stripped.replace('|', '').replace('-', '').replace(':', '').strip()
            if not separator_test:
                continue
            cells = [col.strip() for col in stripped.strip('|').split('|')]
            if len(cells) < len(headers):
                continue
            row = {headers[idx]: cells[idx] for idx in range(len(headers))}
            rows.append(row)
        if not rows:
            return None
        return headers, rows

    def _extract_structured_from_string(self, text: str) -> Optional[tuple]:
        json_rows = self._try_parse_json_list(text)
        if json_rows is not None:
            return None, json_rows
        markdown_rows = self._parse_markdown_table(text)
        if markdown_rows:
            return markdown_rows
        return None

    def _maybe_convert_to_markdown_table(self, content: Any) -> Optional[str]:
        if isinstance(content, list):
            if content and all(isinstance(item, dict) for item in content):
                return self._format_table(content)
            text_parts = [item for item in content if isinstance(item, str)]
            if text_parts:
                structured = self._extract_structured_from_string('\n'.join(text_parts))
                if structured:
                    headers, rows = structured
                    return self._format_table(rows, headers)
            return None
        if isinstance(content, str):
            structured = self._extract_structured_from_string(content)
            if structured:
                headers, rows = structured
                return self._format_table(rows, headers)
        return None

    def _is_probable_html(self, text: str) -> bool:
        return bool(re.search(r'</?[a-zA-Z][^>]*>', text))

    def _format_text_block(self, text: str) -> str:
        if text is None:
            return ""
        return str(text).strip('\n')

    def _append_metadata_notice(self, body: str, resolution: Dict[str, Any]) -> str:
        auto_filled = resolution.get("auto_filled") or {}
        suggestions = resolution.get("suggestions") or {}

        sections: List[str] = []

        if auto_filled:
            autofill_lines = ["Auto-filled parameters:"]
            for key, value in auto_filled.items():
                autofill_lines.append(f"- {key}: {value}")
            sections.append("\n".join(autofill_lines))

        if isinstance(suggestions, dict):
            suggestion_lines: List[str] = []
            for param, detail in suggestions.items():
                if not isinstance(detail, dict):
                    continue
                candidates = detail.get("candidates") or []
                if not candidates:
                    continue
                suggestion_lines.append(f"- {param}:")
                for cand in candidates[:5]:
                    suggestion_lines.append(f"  - {cand}")
            if suggestion_lines:
                sections.append("\n".join(["Suggested parameter values:", *suggestion_lines]))

        core_body = body.strip() if isinstance(body, str) else str(body)

        if sections:
            combined = "\n\n".join([section for section in sections if section.strip()])
            if core_body:
                return f"{combined}\n\n{core_body}"
            return combined

        return core_body

    def _build_missing_parameter_response(self, tool_errors: Dict[str, Dict[str, Any]]) -> str:
        lines = [
            "I need a bit more information before I can run that command."
        ]

        for tool_name, detail in tool_errors.items():
            lines.append("")
            lines.append(f"{tool_name} still needs:")

            guidance = self._build_parameter_guidance(tool_name, detail)
            if guidance:
                lines.extend(guidance)
            else:
                lines.append("  Provide the required parameters exactly as defined for this tool.")

        lines.append("")
        lines.append("Please reply with those parameters using the same names. I will rerun the command as soon as you provide them.")

        return "\n".join(line for line in lines if line is not None).strip()

    def _build_iteration_limit_response(self, tool_errors: Dict[str, Dict[str, Any]]) -> str:
        """Create a user-facing message when the reasoning loop hits the iteration ceiling."""
        lines = [
            "I reached the maximum of 15 reasoning steps and had to stop before completing this request."
        ]

        if tool_errors:
            lines.append("")
            lines.append("Here is what prevented completion:")
            for tool_name, detail in tool_errors.items():
                message = detail.get("message") or "The tool kept responding with an error."
                lines.append(f"- {tool_name}: {message}")

                guidance = self._build_parameter_guidance(tool_name, detail)
                if guidance:
                    lines.extend(guidance)
        else:
            lines.append("")
            lines.append("The tools did not return any usable results within the iteration budget.")

        lines.append("")
        lines.append(
            "Reply with the missing parameters in the suggested format so I can rerun the command. "
            "If you are unsure about a value, ask me to look it up first."
        )

        return "\n".join(line for line in lines if line is not None).strip()

    def _apply_user_parameter_response(self, user_message: str) -> Optional[Dict[str, Any]]:
        if not self._pending_parameter_requests:
            return None

        normalized_message = user_message.strip()
        if not normalized_message:
            guidance = self._build_missing_parameter_response(self._pending_parameter_requests)
            return {
                "needs_more": True,
                "guidance": guidance,
                "tool_errors": copy.deepcopy(self._pending_parameter_requests),
                "had_updates": False
            }

        tools_still_missing: Dict[str, Dict[str, Any]] = {}
        had_updates = False

        for tool_name, detail in self._pending_parameter_requests.items():
            expected = detail.get("missing_parameters")
            if not isinstance(expected, list) or not expected:
                expected = detail.get("required_parameters") or []
            if not expected:
                continue

            schema = self._get_tool_schema(tool_name)
            properties = schema.get("properties", {}) if isinstance(schema, dict) else {}

            extracted = self._extract_user_parameter_values(normalized_message, expected, properties)
            if extracted:
                user_supplied = detail.setdefault("user_supplied", {})
                if isinstance(user_supplied, dict):
                    for key, value in extracted.items():
                        user_supplied[key] = value
                        had_updates = True
                logger.info(
                    f"Captured user-supplied parameters for {tool_name}: {', '.join(extracted.keys())}"
                )

            user_supplied = detail.get("user_supplied", {}) if isinstance(detail.get("user_supplied"), dict) else {}
            remaining = []
            for param in expected:
                if not self._argument_has_value(user_supplied, param):
                    remaining.append(param)
            detail["missing_parameters"] = remaining

            if remaining:
                tools_still_missing[tool_name] = detail

        if tools_still_missing:
            guidance = self._build_missing_parameter_response(tools_still_missing)
            return {
                "needs_more": True,
                "guidance": guidance,
                "tool_errors": copy.deepcopy(tools_still_missing),
                "had_updates": had_updates
            }

        if had_updates:
            logger.info("All required parameters captured from user response; resuming execution.")

        return {
            "needs_more": False,
            "tool_errors": copy.deepcopy(self._pending_parameter_requests),
            "had_updates": had_updates
        }

    def _extract_user_parameter_values(
        self,
        message: str,
        expected_params: List[str],
        properties: Dict[str, Any]
    ) -> Dict[str, Any]:
        values: Dict[str, Any] = {}
        if not message or not expected_params:
            return values

        json_candidate = self._try_parse_json_object_from_text(message)
        if isinstance(json_candidate, dict):
            for param in expected_params:
                if param in json_candidate:
                    schema = properties.get(param, {}) if isinstance(properties, dict) else {}
                    values[param] = self._coerce_user_value(param, schema, json_candidate[param])

        normalized = re.sub(r"\s*(?:,|;)\s*(?=[A-Za-z0-9_\-]+\s*[:=])", "\n", message)
        for raw_line in normalized.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            match = re.match(r'^([A-Za-z0-9_\-]+)\s*[:=]\s*(.+)$', line)
            if not match:
                continue
            key = match.group(1).strip()
            value_text = match.group(2).strip()
            if value_text.endswith(','):
                value_text = value_text[:-1].strip()

            for param in expected_params:
                if key.lower() == param.lower():
                    schema = properties.get(param, {}) if isinstance(properties, dict) else {}
                    values[param] = self._coerce_user_value(param, schema, value_text)

        if not values:
            lower_message = message.lower()
            compressed_message = re.sub(r'[^a-z0-9]', '', lower_message)
            for param in expected_params:
                param_lower = param.lower()
                if param_lower in lower_message:
                    schema = properties.get(param, {}) if isinstance(properties, dict) else {}
                    inferred_value = self._infer_value_from_context(param, schema, message)
                    if inferred_value is not None:
                        values[param] = inferred_value
                        continue

                compressed_param = re.sub(r'[^a-z0-9]', '', param_lower)
                if compressed_param and compressed_param in compressed_message:
                    schema = properties.get(param, {}) if isinstance(properties, dict) else {}
                    inferred_value = self._infer_value_from_context(param, schema, message)
                    if inferred_value is not None:
                        values[param] = inferred_value
                        continue

                if "resource type" in lower_message and "resource" in param_lower:
                    schema = properties.get(param, {}) if isinstance(properties, dict) else {}
                    inferred_value = self._infer_value_from_context(param, schema, message)
                    if inferred_value is not None:
                        values[param] = inferred_value

        return values

    def _coerce_user_value(self, parameter: str, schema: Dict[str, Any], raw_value: Any) -> Any:
        if isinstance(raw_value, (list, dict, int, float, bool)) or raw_value is None:
            return raw_value

        text = str(raw_value).strip()
        if not text:
            return ""

        schema_type = schema.get("type") if isinstance(schema, dict) else None

        if schema_type == "array":
            if text.startswith('[') and text.endswith(']'):
                try:
                    return json.loads(text)
                except Exception:
                    pass
            parts = [item.strip().strip('\"\'') for item in text.split(',') if item.strip()]
            if "resource" in parameter.lower():
                parts = [self._normalize_resource_type_alias(part) for part in parts]
            return parts or [text]

        if schema_type in {"integer", "number"}:
            try:
                return int(text)
            except ValueError:
                try:
                    return float(text)
                except ValueError:
                    return text

        if schema_type == "boolean":
            lowered = text.lower()
            if lowered in {"true", "yes", "1"}:
                return True
            if lowered in {"false", "no", "0"}:
                return False
            return text

        if schema_type == "object":
            parsed = self._try_parse_json_object_from_text(text)
            if isinstance(parsed, dict):
                return parsed
            return text

        if text.startswith('"') and text.endswith('"') or text.startswith("'") and text.endswith("'"):
            return text[1:-1]

        return text

    def _try_parse_json_object_from_text(self, text: str) -> Optional[Any]:
        candidate = text.strip()
        if not candidate:
            return None
        try:
            return json.loads(candidate)
        except Exception:
            return None

    def _infer_value_from_context(self, parameter: str, schema: Dict[str, Any], message: str) -> Optional[Any]:
        schema_type = schema.get("type") if isinstance(schema, dict) else None
        lower_message = message.lower()

        if schema_type == "array":
            # Basic heuristic: look for resource types enclosed in quotes
            candidates = re.findall(r'"([A-Za-z0-9\./-]+)"', message)
            if candidates:
                if "resource" in parameter.lower():
                    return [self._normalize_resource_type_alias(cand) for cand in candidates]
                return candidates

            if "resource" in parameter.lower():
                if "virtual machine" in lower_message or "virtual machines" in lower_message:
                    return ["Microsoft.Compute/virtualMachines"]
                if "network interface" in lower_message:
                    return ["Microsoft.Network/networkInterfaces"]

        if schema_type == "string" and "region" in parameter.lower():
            region_match = re.search(r'(?:in|for)\s+([A-Za-z\s-]+?)(?:\.|,|$)', lower_message)
            if region_match:
                region_value = region_match.group(1).strip()
                if region_value:
                    return region_value.title()

            trailing_match = re.search(r'([A-Za-z\s-]+)\s+region', lower_message)
            if trailing_match:
                inferred = trailing_match.group(1).strip()
                if inferred:
                    return inferred.title()

        return None

    def _normalize_resource_type_alias(self, value: str) -> str:
        alias = value.strip().lower()
        alias_map = {
            "vm": "Microsoft.Compute/virtualMachines",
            "vms": "Microsoft.Compute/virtualMachines",
            "virtual machine": "Microsoft.Compute/virtualMachines",
            "virtual machines": "Microsoft.Compute/virtualMachines",
            "network interface": "Microsoft.Network/networkInterfaces",
            "network interfaces": "Microsoft.Network/networkInterfaces",
            "nic": "Microsoft.Network/networkInterfaces",
            "nics": "Microsoft.Network/networkInterfaces",
            "storage account": "Microsoft.Storage/storageAccounts",
            "storage accounts": "Microsoft.Storage/storageAccounts",
            "cosmos db": "Microsoft.DocumentDB/databaseAccounts",
            "app service": "Microsoft.Web/serverFarms",
            "app services": "Microsoft.Web/serverFarms"
        }
        return alias_map.get(alias, value.strip())

    def _build_parameter_guidance(
        self,
        tool_name: str,
        detail: Dict[str, Any]
    ) -> List[str]:
        metadata_params = self._get_metadata_parameters(tool_name)
        missing = detail.get("missing_parameters")
        if not isinstance(missing, list):
            missing = []

        schema = self._get_tool_schema(tool_name)
        properties = schema.get("properties", {}) if isinstance(schema, dict) else {}

        raw_attempted = detail.get("arguments")
        attempted_args = raw_attempted if isinstance(raw_attempted, dict) else {}

        raw_suggestions = detail.get("suggestions")
        suggestions = raw_suggestions if isinstance(raw_suggestions, dict) else {}

        required_params = detail.get("required_parameters")
        if not isinstance(required_params, list):
            required_params = self._get_required_parameters(tool_name)

        inferred_missing: List[str] = []
        if isinstance(required_params, list) and required_params:
            for param in required_params:
                if not self._argument_has_value(attempted_args, param):
                    inferred_missing.append(param)

        if not missing and inferred_missing:
            missing = inferred_missing

        if not missing and isinstance(required_params, list):
            missing = required_params

        if not missing:
            return []

        detail["missing_parameters"] = missing

        guidance_lines = ["  Provide these parameters explicitly:"]

        for param in missing:
            param_schema = properties.get(param, {}) if isinstance(properties, dict) else {}
            param_type = param_schema.get("type") if isinstance(param_schema, dict) else None
            type_label = f" ({param_type})" if isinstance(param_type, str) else ""
            description = param_schema.get("description") if isinstance(param_schema, dict) else None
            if (not description or not description.strip()) and metadata_params:
                metadata_param = metadata_params.get(param.lower())
                if metadata_param:
                    description = metadata_param.get("description") or description

            if description:
                guidance_lines.append(f"  - {param}{type_label}: {description}")
            else:
                guidance_lines.append(f"  - {param}{type_label}")

            attempted_value = attempted_args.get(param)
            if attempted_value not in (None, "", [], {}):
                try:
                    attempted_repr = json.dumps(attempted_value)
                except TypeError:
                    attempted_repr = str(attempted_value)
                guidance_lines.append(f"    Received earlier: {attempted_repr}")

            supplied_value = None
            user_supplied = detail.get("user_supplied")
            if isinstance(user_supplied, dict):
                supplied_value = user_supplied.get(param)
            if supplied_value not in (None, "", [], {}):
                try:
                    supplied_repr = json.dumps(supplied_value)
                except TypeError:
                    supplied_repr = str(supplied_value)
                guidance_lines.append(f"    Using your value: {supplied_repr}")

            suggestion_info = suggestions.get(param) if isinstance(suggestions, dict) else None
            if isinstance(suggestion_info, dict):
                candidates = suggestion_info.get("candidates")
                if isinstance(candidates, list) and candidates:
                    sample_values = ", ".join(str(candidate) for candidate in candidates[:3])
                    guidance_lines.append(f"    e.g., {sample_values}")
                    guidance_lines.append("    Choose one of these options or provide another specific value if needed.")
            elif metadata_params:
                metadata_param = metadata_params.get(param.lower())
                options = metadata_param.get("options") if metadata_param else None
                if isinstance(options, list) and options:
                    sample_values = ", ".join(options[:3])
                    guidance_lines.append(f"    e.g., {sample_values}")
                    guidance_lines.append("    Select the option that fits your request or reply with a different valid value.")

        example_lines = self._build_example_lines(
            missing,
            properties,
            attempted_args,
            suggestions,
            metadata_params
        )
        if example_lines:
            guidance_lines.append("  Example follow-up message:")
            guidance_lines.extend(example_lines)

        return guidance_lines

    def _build_example_lines(
        self,
        parameters: List[str],
        properties: Dict[str, Any],
        attempted_args: Dict[str, Any],
        suggestions: Dict[str, Any],
        metadata_params: Optional[Dict[str, Dict[str, Any]]] = None
    ) -> List[str]:
        example_map: Dict[str, Any] = {}
        for param in parameters:
            param_schema = properties.get(param, {}) if isinstance(properties, dict) else {}
            attempted = attempted_args.get(param)
            candidate_value = None

            suggestion_info = suggestions.get(param) if isinstance(suggestions, dict) else None
            if isinstance(suggestion_info, dict):
                candidates = suggestion_info.get("candidates")
                if isinstance(candidates, list) and candidates:
                    candidate_value = candidates[0]
            elif metadata_params:
                metadata_param = metadata_params.get(param.lower())
                options = metadata_param.get("options") if metadata_param else None
                if isinstance(options, list) and options:
                    candidate_value = options[0]

            value_source = attempted
            if value_source in (None, "", [], {}) and candidate_value is not None:
                value_source = self._coerce_example_candidate(param_schema, candidate_value)

            example_map[param] = self._build_example_value(param, param_schema, value_source)

        if not example_map:
            return []

        lines: List[str] = []
        for key, value in example_map.items():
            try:
                value_repr = json.dumps(value)
            except TypeError:
                value_repr = str(value)
            lines.append(f"    {key}: {value_repr}")

        lines.append("    (include each parameter using the same name in your next message)")
        return lines

    def _coerce_example_candidate(self, schema: Dict[str, Any], candidate: Any) -> Any:
        if candidate is None:
            return None

        if not isinstance(schema, dict):
            return candidate

        schema_type = schema.get("type")

        if schema_type == "array":
            if isinstance(candidate, list):
                return candidate
            return [candidate]

        if schema_type in {"integer", "number"}:
            try:
                return int(candidate)
            except (TypeError, ValueError):
                try:
                    return float(candidate)
                except (TypeError, ValueError):
                    return candidate

        if schema_type == "boolean":
            if isinstance(candidate, bool):
                return candidate
            if isinstance(candidate, str):
                lowered = candidate.strip().lower()
                if lowered in {"true", "yes", "1"}:
                    return True
                if lowered in {"false", "no", "0"}:
                    return False

        return candidate

    def _build_example_value(
        self,
        parameter: str,
        schema: Dict[str, Any],
        attempted: Any
    ) -> Any:
        if isinstance(attempted, (list, dict)):
            if attempted:
                return attempted
        elif attempted not in (None, ""):
            return attempted

        if not isinstance(schema, dict):
            return f"<{parameter}>"

        enum_values = schema.get("enum")
        if isinstance(enum_values, list) and enum_values:
            return enum_values[0]

        examples = schema.get("examples")
        if isinstance(examples, list) and examples:
            return examples[0]

        schema_type = schema.get("type")

        if schema_type == "string":
            format_hint = schema.get("format") or parameter
            return f"<{format_hint}>"

        if schema_type in {"integer", "number"}:
            return 0

        if schema_type == "boolean":
            return True

        if schema_type == "array":
            item_schema = schema.get("items", {})
            return [self._build_example_value(parameter, item_schema, None)]

        if schema_type == "object":
            properties = schema.get("properties", {})
            example_obj: Dict[str, Any] = {}
            if isinstance(properties, dict):
                for key, sub_schema in list(properties.items())[:1]:
                    example_obj[key] = self._build_example_value(key, sub_schema, None)
            if not example_obj:
                example_obj["value"] = f"<{parameter}>"
            return example_obj

        return f"<{parameter}>"

    async def _execute_tool_call(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute an MCP tool and return a structured payload describing the outcome.

        The payload always contains a `text` field for human-readable content alongside
        machine-readable keys (success, error, missing_parameters, etc.) so the
        orchestrator can reason about next steps without losing detail.
        """
        try:
            logger.info(f"🔧 Calling MCP tool: {tool_name} with args: {arguments}")

            resolution = await self._resolve_tool_arguments(tool_name, arguments or {})
            placeholder_parameters = resolution.get("placeholder_parameters")
            if not isinstance(placeholder_parameters, dict):
                placeholder_parameters = {}
            if resolution["status"] == "incomplete":
                logger.info(
                    f"⚠️ Missing parameters for tool '{tool_name}': {resolution['missing']}"
                )
                guidance_text = self._append_metadata_notice(
                    resolution["message"],
                    resolution
                )
                return {
                    "success": False,
                    "error": "missing_parameters",
                    "tool": tool_name,
                    "message": resolution["message"],
                    "text": guidance_text,
                    "arguments": resolution["arguments"],
                    "missing_parameters": resolution["missing"],
                    "auto_filled": resolution["auto_filled"],
                    "suggestions": resolution["suggestions"],
                    "placeholder_parameters": placeholder_parameters
                }

            resolved_arguments = resolution["arguments"]

            retryable_markers = ["429", "Too Many Requests", "Request rate is large"]
            max_attempts = 3
            attempt = 1
            result = None

            while attempt <= max_attempts:
                result = await self._mcp_client.call_tool(tool_name, resolved_arguments)
                if result.get("success"):
                    break

                error_text = str(result.get("error", ""))
                should_retry = any(marker in error_text for marker in retryable_markers)

                if should_retry and attempt < max_attempts:
                    backoff_seconds = 2 * attempt
                    logger.warning(
                        f"⏱️ Rate limit hit for {tool_name} (attempt {attempt}/{max_attempts}). "
                        f"Retrying in {backoff_seconds}s..."
                    )
                    await self._push_communication(
                        "warning",
                        (
                            f"Azure API rate limited the tool '{tool_name}' (HTTP 429). "
                            f"Retrying in {backoff_seconds} seconds (attempt {attempt + 1}/{max_attempts})."
                        ),
                        tool=tool_name,
                        retry_delay_seconds=backoff_seconds,
                        attempt=attempt,
                        max_attempts=max_attempts
                    )
                    await asyncio.sleep(backoff_seconds)
                    attempt += 1
                    continue

                break

            if isinstance(result, dict):
                if result.get("success"):
                    content = result.get("content")

                    pagination_payload = self._maybe_create_paginated_payload(
                        tool_name,
                        content,
                        resolution,
                        result,
                        resolved_arguments
                    )
                    if pagination_payload:
                        pagination_payload["placeholder_parameters"] = placeholder_parameters
                        return pagination_payload

                    table_markdown = self._maybe_convert_to_markdown_table(content)
                    if table_markdown:
                        rendered = self._append_metadata_notice(table_markdown, resolution)
                        return {
                            "success": True,
                            "tool": tool_name,
                            "text": rendered,
                            "raw_result": result,
                            "content": content,
                            "arguments": resolved_arguments,
                            "auto_filled": resolution.get("auto_filled"),
                            "suggestions": resolution.get("suggestions"),
                            "placeholder_parameters": placeholder_parameters
                        }

                    if isinstance(content, list):
                        text_parts = []
                        for item in content:
                            if isinstance(item, str):
                                text_parts.append(item)
                            elif isinstance(item, dict):
                                text_parts.append(json.dumps(item, indent=2))
                            else:
                                text_parts.append(str(item))
                        joined = "\n".join(text_parts).strip()
                        if not joined:
                            joined = "{}"
                        formatted = self._format_text_block(joined)
                        rendered = self._append_metadata_notice(formatted, resolution)
                        return {
                            "success": True,
                            "tool": tool_name,
                            "text": rendered,
                            "raw_result": result,
                            "content": content,
                            "arguments": resolved_arguments,
                            "auto_filled": resolution.get("auto_filled"),
                            "suggestions": resolution.get("suggestions"),
                            "placeholder_parameters": placeholder_parameters
                        }

                    if isinstance(content, str):
                        table_markdown = self._maybe_convert_to_markdown_table(content)
                        if table_markdown:
                            rendered = self._append_metadata_notice(table_markdown, resolution)
                        elif self._is_probable_html(content):
                            rendered = self._append_metadata_notice(content, resolution)
                        else:
                            formatted = self._format_text_block(content)
                            rendered = self._append_metadata_notice(formatted, resolution)
                        return {
                            "success": True,
                            "tool": tool_name,
                            "text": rendered,
                            "raw_result": result,
                            "content": content,
                            "arguments": resolved_arguments,
                            "auto_filled": resolution.get("auto_filled"),
                            "suggestions": resolution.get("suggestions"),
                            "placeholder_parameters": placeholder_parameters
                        }

                    formatted = self._format_text_block(json.dumps(content, indent=2))
                    rendered = self._append_metadata_notice(formatted, resolution)
                    return {
                        "success": True,
                        "tool": tool_name,
                        "text": rendered,
                        "raw_result": result,
                        "content": content,
                        "arguments": resolved_arguments,
                        "auto_filled": resolution.get("auto_filled"),
                        "suggestions": resolution.get("suggestions"),
                        "placeholder_parameters": placeholder_parameters
                    }

                error = result.get("error", "Unknown error")
                rate_limited = any(marker in str(error) for marker in retryable_markers)
                if rate_limited:
                    friendly = (
                        "Azure returned HTTP 429 (Too Many Requests). "
                        "Please wait a few seconds and try again, or reduce the frequency of this request."
                    )
                    error = f"{friendly}\n\nRaw error: {error}"
                error_html = self._format_text_block(error)
                rendered = self._append_metadata_notice(error_html, resolution)
                return {
                    "success": False,
                    "tool": tool_name,
                    "error": result.get("error"),
                    "message": error,
                    "text": rendered,
                    "raw_result": result,
                    "content": result.get("content"),
                    "arguments": resolved_arguments,
                    "missing_parameters": result.get("missing_parameters"),
                    "auto_filled": resolution.get("auto_filled"),
                    "suggestions": resolution.get("suggestions"),
                    "placeholder_parameters": placeholder_parameters
                }

            fallback = self._format_text_block(json.dumps(result, indent=2))
            rendered = self._append_metadata_notice(fallback, resolution)
            return {
                "success": False,
                "tool": tool_name,
                "error": "unexpected_response",
                "message": fallback,
                "text": rendered,
                "raw_result": result,
                "arguments": resolved_arguments,
                "auto_filled": resolution.get("auto_filled"),
                "suggestions": resolution.get("suggestions"),
                "placeholder_parameters": placeholder_parameters
            }

        except Exception as e:
            error_msg = f"Error calling tool {tool_name}: {str(e)}"
            logger.error(error_msg)
            logger.error(traceback.format_exc())
            return {
                "success": False,
                "tool": tool_name,
                "error": "tool_execution_exception",
                "message": error_msg,
                "text": error_msg,
                "arguments": arguments
            }
    
    async def process_message(self, user_message: str) -> Dict[str, Any]:
        """
        Process a user message using Azure OpenAI with function calling.
        
        The LLM intelligently selects and calls the appropriate Azure MCP tools
        based on the user's request. All available MCP tools are registered
        and can be utilized.
        
        Args:
            user_message: The user's message
            
        Returns:
            Dictionary containing response, history, and metadata
        """
        start_time = datetime.utcnow()
        tool_calls_made = 0
        
        # Generate request ID for this conversation turn
        import uuid
        request_id = str(uuid.uuid4())[:8]
        
        try:
            enable_cli_executor = self._should_enable_cli_executor(user_message)

            # Ensure OpenAI client is initialized
            await self._ensure_openai_client_initialized()

            if enable_cli_executor:
                await self._ensure_cli_executor_client_initialized()

            tools_for_request = self._select_tool_definitions_for_message(user_message)
            if enable_cli_executor and not any(
                tool.get("function", {}).get("name") in self._cli_executor_tool_names
                for tool in tools_for_request
            ):
                logger.warning("Requested Azure CLI executor tool but it is not available in the current tool set.")
            
            # Clear old buffer and start fresh for this request
            self.communication_buffer.clear()
            
            # Add user message to conversation
            self._messages.append({
                "role": "user",
                "content": user_message
            })

            pagination_followup = self._handle_paginated_user_request(user_message)
            if pagination_followup and pagination_followup.get("handled"):
                response_text = pagination_followup.get("text", "")
                pagination_meta = pagination_followup.get("metadata") or {}

                self._messages.append({
                    "role": "assistant",
                    "content": response_text
                })

                await self._push_communication(
                    "synthesis",
                    "Serving paginated MCP tool results",
                    pagination=pagination_meta.get("pagination")
                )

                duration = (datetime.utcnow() - start_time).total_seconds()

                conversation_history = []
                for msg in self._messages[1:]:
                    if msg["role"] in ["user", "assistant"]:
                        conversation_history.append({
                            "role": msg["role"],
                            "content": msg.get("content", ""),
                            "timestamp": datetime.utcnow().isoformat()
                        })

                metadata = {
                    "session_id": self.session_id,
                    "duration_seconds": duration,
                    "tool_calls_made": 0,
                    "available_tools": len(self._tool_definitions),
                    "message_count": len(self._messages) - 1,
                    "agentic_mode": True,
                    "reasoning_iterations": 0,
                    "max_iterations_reached": False,
                    "synthesis_forced": False,
                    "tool_errors": {},
                    "pagination": pagination_meta.get("pagination")
                }

                return {
                    "success": True,
                    "response": response_text,
                    "conversation_history": conversation_history,
                    "metadata": metadata
                }

            pending_followup = self._apply_user_parameter_response(user_message)
            if pending_followup and pending_followup.get("needs_more"):
                guidance_text = pending_followup.get("guidance", "I still need a bit more detail to continue.")
                self._messages.append({
                    "role": "assistant",
                    "content": guidance_text
                })

                await self._push_communication(
                    "guidance",
                    guidance_text,
                    pending_parameters=True,
                    tool_errors=pending_followup.get("tool_errors")
                )

                duration = (datetime.utcnow() - start_time).total_seconds()

                conversation_history = []
                for msg in self._messages[1:]:  # Skip system message
                    if msg["role"] in ["user", "assistant"]:
                        conversation_history.append({
                            "role": msg["role"],
                            "content": msg.get("content", ""),
                            "timestamp": datetime.utcnow().isoformat()
                        })

                metadata = {
                    "session_id": self.session_id,
                    "duration_seconds": duration,
                    "tool_calls_made": 0,
                    "available_tools": len(self._tool_definitions),
                    "message_count": len(self._messages) - 1,
                    "agentic_mode": True,
                    "reasoning_iterations": 0,
                    "max_iterations_reached": False,
                    "synthesis_forced": False,
                    "tool_errors": pending_followup.get("tool_errors") or {},
                    "iteration_guidance": guidance_text,
                    "requires_user_parameters": True
                }

                return {
                    "success": True,
                    "response": guidance_text,
                    "conversation_history": conversation_history,
                    "metadata": metadata
                }
            
            logger.info(f"🤖 Processing message (request: {request_id}): {user_message[:100]}...")
            
            # Use LLM function calling to process the message
            logger.info("🔍 Using LLM function calling with all available tools")
            response_result = await self._llm_process_message(tools_for_request)
            tool_calls_made = response_result.get("tool_calls_made", 0)
            response_text = response_result.get("response", "")
            
            duration = (datetime.utcnow() - start_time).total_seconds()
            
            # Build conversation history in simple format
            conversation_history = []
            for msg in self._messages[1:]:  # Skip system message
                if msg["role"] in ["user", "assistant"]:
                    conversation_history.append({
                        "role": msg["role"],
                        "content": msg.get("content", ""),
                        "timestamp": datetime.utcnow().isoformat()
                    })
            
            # Build enhanced metadata with agentic insights
            metadata = {
                "session_id": self.session_id,
                "duration_seconds": duration,
                "tool_calls_made": tool_calls_made,
                "available_tools": len(self._tool_definitions),
                "message_count": len(self._messages) - 1,  # Exclude system message
                "agentic_mode": True,
                "reasoning_iterations": response_result.get("iterations", 0),
                "max_iterations_reached": response_result.get("max_iterations_reached", False),
                "synthesis_forced": response_result.get("synthesis_forced", False),
                "tool_errors": response_result.get("tool_errors") or {},
                "iteration_guidance": response_result.get("iteration_guidance"),
                "requires_user_parameters": response_result.get("requires_user_parameters", False),
                "pagination": response_result.get("pagination")
            }
            
            # If max iterations reached, add helpful note to response
            if metadata["max_iterations_reached"]:
                guidance_message = response_result.get("iteration_guidance")
                if guidance_message:
                    logger.info("Max iteration guidance already provided by orchestrator")
                else:
                    logger.info("Adding fallback max iterations notice to response")
                    response_text = (
                        f"{response_text}\n\n"
                        f"ℹ️ Note: This response represents a synthesis of information gathered through "
                        f"{tool_calls_made} tool calls across {metadata['reasoning_iterations']} reasoning steps. "
                        f"The iteration limit was reached. For more specific details, please ask targeted follow-up questions."
                    )
            
            # Add reasoning trace if available (for debugging/analysis)
            if "reasoning_trace" in response_result:
                metadata["reasoning_trace"] = response_result["reasoning_trace"]
                metadata["reasoning_summary"] = self._summarize_reasoning_trace(
                    response_result["reasoning_trace"]
                )
            
            return {
                "success": True,
                "response": response_text,
                "conversation_history": conversation_history,
                "metadata": metadata
            }
            
        except Exception as e:
            logger.error(f"❌ Error processing message: {e}")
            logger.error(traceback.format_exc())
            
            error_response = {
                "success": False,
                "error": str(e),
                "response": f"I apologize, but I encountered an error: {str(e)}",
                "conversation_history": [],
                "metadata": {
                    "session_id": self.session_id,
                    "error_type": type(e).__name__
                }
            }
            
            return error_response
    
    async def _llm_process_message(
        self,
        tools_for_request: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        Process message using agentic LLM with reasoning, action, and reflection loop.
        
        Implements ReAct pattern (Reasoning + Acting):
        - Reasons about the task before acting
        - Takes actions (tool calls) based on reasoning
        - Observes and reflects on results
        - Adapts strategy if needed
        - Self-corrects on failures
        
        Returns:
            Dictionary with response, tool_calls_made count, and reasoning trace
        """
        tool_calls_made = 0
        max_iterations = 15  # Increased for more complex agentic workflows
        iteration = 0
        reasoning_trace = []  # Track the agent's reasoning process
        failed_tool_counts: Dict[str, int] = {}
        tool_error_details: Dict[str, Dict[str, Any]] = {}
        latest_pagination: Optional[Dict[str, Any]] = None
        
        logger.info("🤖 Starting agentic reasoning loop...")
        
        while iteration < max_iterations:
            iteration += 1
            logger.info(f"🔄 Agentic iteration {iteration}/{max_iterations}")
            
            # Call Azure OpenAI with function calling
            # Note: tool_choice can only be set when tools are available
            call_params = {
                "model": os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o-mini"),
                "messages": self._messages,
                "temperature": 0.7,
                "max_tokens": 3000  # Increased for more detailed reasoning
            }
            
            if tools_for_request:
                call_params["tools"] = tools_for_request
                call_params["tool_choice"] = "auto"
            
            response = await self._openai_client.chat.completions.create(**call_params)
            
            assistant_message = response.choices[0].message
            
            # Capture reasoning if the model provides it (before tool calls)
            if assistant_message.content and not assistant_message.tool_calls:
                reasoning_content = assistant_message.content[:200]  # Truncate for logging
                reasoning_trace.append({
                    "iteration": iteration,
                    "type": "reasoning",
                    "content": reasoning_content
                })
                # Push to real-time communication stream
                await self._push_communication(
                    "reasoning",
                    assistant_message.content,
                    iteration=iteration,
                    strategy="ReAct"
                )
            
            # Check if the model wants to call tools (ACTION phase)
            if assistant_message.tool_calls:
                num_tools = len(assistant_message.tool_calls)
                logger.info(f"🔧 Agent decided to call {num_tools} tool(s) - [ACTION phase]")
                
                # Track which tools are being called
                tool_names = [tc.function.name for tc in assistant_message.tool_calls]
                reasoning_trace.append({
                    "iteration": iteration,
                    "type": "action",
                    "tools": tool_names,
                    "count": num_tools
                })
                
                # Push action phase to real-time communication stream
                await self._push_communication(
                    "planning",
                    f"Planning to call {num_tools} tool(s): {', '.join(tool_names)}",
                    iteration=iteration,
                    strategy="ReAct"
                )
                
                # Add assistant's tool call request to messages
                self._messages.append({
                    "role": "assistant",
                    "content": assistant_message.content,
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments
                            }
                        }
                        for tc in assistant_message.tool_calls
                    ]
                })
                
                # Execute each tool call (OBSERVATION phase)
                tool_results = []
                for tool_call in assistant_message.tool_calls:
                    function_name = tool_call.function.name
                    function_args = json.loads(tool_call.function.arguments)
                    
                    # Check if this tool has failed before (self-correction check)
                    retry_count = failed_tool_counts.get(function_name, 0)
                    if retry_count > 0:
                        logger.info(
                            f"Retrying tool '{function_name}' (attempt {retry_count + 1})"
                        )

                    logger.info(f"Executing tool: {function_name}")
                    logger.debug(f"   Args: {json.dumps(function_args, indent=2)[:200]}")
                    
                    # Push action to real-time communication stream
                    await self._push_communication(
                        "action",
                        f"Calling tool: {function_name}",
                        iteration=iteration,
                        tool_name=function_name,
                        tool_params=function_args
                    )
                    
                    # Execute the tool
                    tool_result = await self._execute_tool_call(function_name, function_args)
                    tool_calls_made += 1

                    # Normalize tool payload
                    if not isinstance(tool_result, dict):
                        tool_result_data = {
                            "success": False,
                            "tool": function_name,
                            "error": "invalid_tool_payload",
                            "message": str(tool_result),
                            "text": str(tool_result),
                            "raw_result": tool_result,
                            "arguments": function_args
                        }
                    else:
                        tool_result_data = tool_result

                    display_text = tool_result_data.get("text") or tool_result_data.get("message") or ""
                    pagination_info = tool_result_data.get("pagination")
                    if pagination_info:
                        pagination_info = {
                            **pagination_info,
                            "tool": function_name
                        }
                        latest_pagination = pagination_info

                    # Track success/failure for self-correction
                    is_error = not tool_result_data.get("success", False)
                    current_error_detail: Optional[Dict[str, Any]] = None
                    prompt_user_after_call = False

                    if is_error:
                        failed_tool_counts[function_name] = failed_tool_counts.get(function_name, 0) + 1
                        logger.warning(
                            f"⚠️ Tool '{function_name}' returned error: {str(tool_result_data.get('error') or tool_result_data.get('message'))[:100]}"
                        )

                        error_text = str(tool_result_data.get("message") or tool_result_data.get("error") or "")
                        missing_parameters = tool_result_data.get("missing_parameters")
                        if not isinstance(missing_parameters, list):
                            missing_parameters = []

                        suggestions = tool_result_data.get("suggestions")
                        if not isinstance(suggestions, dict):
                            suggestions = {}

                        auto_filled = tool_result_data.get("auto_filled")
                        if not isinstance(auto_filled, dict):
                            auto_filled = {}

                        required_parameters = self._get_required_parameters(function_name)
                        if not isinstance(required_parameters, list):
                            required_parameters = []

                        inferred_missing = []
                        if required_parameters:
                            payload_args = tool_result_data.get("arguments") or function_args
                            if not isinstance(payload_args, dict):
                                payload_args = function_args
                            inferred_missing = [
                                param for param in required_parameters
                                if not self._argument_has_value(payload_args, param)
                            ]

                        if not missing_parameters and inferred_missing:
                            missing_parameters = inferred_missing

                        lower_error_text = error_text.lower()
                        parameter_signal = any(
                            phrase in lower_error_text
                            for phrase in [
                                "missing",
                                "required parameter",
                                "must provide",
                                "not provided",
                                "not recognized",
                                "invalid value"
                            ]
                        )

                        if not missing_parameters and parameter_signal and required_parameters:
                            missing_parameters = required_parameters

                        current_error_detail = {
                            "message": error_text or "The tool kept responding with an error.",
                            "error": tool_result_data.get("error"),
                            "missing_parameters": missing_parameters,
                            "suggestions": suggestions,
                            "auto_filled": auto_filled,
                            "arguments": tool_result_data.get("arguments") or function_args,
                            "required_parameters": required_parameters,
                            "parameter_signal": parameter_signal,
                            "placeholder_parameters": tool_result_data.get("placeholder_parameters")
                        }

                        tool_error_details[function_name] = current_error_detail

                        prompt_user_after_call = bool(missing_parameters) or parameter_signal
                    else:
                        failed_tool_counts.pop(function_name, None)
                        tool_error_details.pop(function_name, None)
                        self._pending_parameter_requests.pop(function_name, None)
                        current_error_detail = None
                        prompt_user_after_call = False
                    
                    # Push observation to real-time communication stream
                    await self._push_communication(
                        "observation",
                        f"Tool '{function_name}' {'failed' if is_error else 'completed successfully'}",
                        iteration=iteration,
                        tool_result=(display_text or str(tool_result_data))[:500],
                        is_error=is_error,
                        pagination=tool_result_data.get("pagination")
                    )
                    
                    tool_results.append({
                        "tool": function_name,
                        "result_length": len(display_text or str(tool_result_data)),
                        "success": function_name not in failed_tool_counts,
                        "pagination": tool_result_data.get("pagination")
                    })
                    
                    # Add tool result to messages
                    tool_message_content = display_text
                    if not tool_message_content:
                        try:
                            tool_message_content = json.dumps(tool_result_data, default=str)
                        except Exception:
                            tool_message_content = str(tool_result_data)

                    self._messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "name": function_name,
                        "content": tool_message_content
                    })

                    if prompt_user_after_call and current_error_detail:
                        pending_detail = copy.deepcopy(current_error_detail)
                        existing_pending = self._pending_parameter_requests.get(function_name)
                        if isinstance(existing_pending, dict):
                            existing_user_values = existing_pending.get("user_supplied")
                            if isinstance(existing_user_values, dict):
                                pending_detail.setdefault("user_supplied", {}).update(existing_user_values)
                        else:
                            pending_detail.setdefault("user_supplied", {})
                        self._pending_parameter_requests[function_name] = pending_detail

                        guidance_message = self._build_missing_parameter_response(
                            {function_name: current_error_detail}
                        )

                        reasoning_trace.append({
                            "iteration": iteration,
                            "type": "parameter_request",
                            "tool": function_name,
                            "missing": current_error_detail.get("missing_parameters", []),
                            "message": current_error_detail.get("message")
                        })

                        await self._push_communication(
                            "guidance",
                            guidance_message,
                            iteration=iteration,
                            tool_name=function_name,
                            missing=current_error_detail.get("missing_parameters")
                        )

                        self._messages.append({
                            "role": "assistant",
                            "content": guidance_message
                        })

                        reasoning_trace.append({
                            "iteration": iteration,
                            "type": "observation",
                            "tool_results": tool_results,
                            "total_data_received": sum(r["result_length"] for r in tool_results)
                        })

                        return {
                            "response": guidance_message,
                            "tool_calls_made": tool_calls_made,
                            "reasoning_trace": reasoning_trace,
                            "iterations": iteration,
                            "tool_errors": {function_name: current_error_detail},
                            "iteration_guidance": guidance_message,
                            "requires_user_parameters": True,
                            "max_iterations_reached": False,
                            "synthesis_forced": False,
                            "pagination": latest_pagination
                        }
                
                # Record observation phase
                reasoning_trace.append({
                    "iteration": iteration,
                    "type": "observation",
                    "tool_results": tool_results,
                    "total_data_received": sum(r["result_length"] for r in tool_results)
                })
                
                # Continue loop for REFLECTION and potential additional actions
                logger.info("✅ Tool execution complete - [REFLECTION phase] checking if more actions needed...")
                
                # Push reflection to real-time communication stream
                await self._push_communication(
                    "reflection",
                    f"Analyzing results from {len(tool_results)} tool(s), determining next steps...",
                    iteration=iteration
                )
                
                continue
                
            else:
                # No more tool calls needed - agent has reached conclusion (SYNTHESIS phase)
                logger.info("✅ Agent completed reasoning - [SYNTHESIS phase] providing final response")
                response_text = assistant_message.content

                # Record final synthesis
                reasoning_trace.append({
                    "iteration": iteration,
                    "type": "synthesis",
                    "response_length": len(response_text) if response_text else 0
                })
                
                # Push synthesis to real-time communication stream
                await self._push_communication(
                    "synthesis",
                    "Formulating final response",
                    iteration=iteration
                )
                
                # Add final assistant response to messages
                self._messages.append({
                    "role": "assistant",
                    "content": response_text
                })
                
                # Log reasoning summary
                logger.info(f"🎯 Agentic workflow complete: {len(reasoning_trace)} reasoning steps, {tool_calls_made} tool calls")
                
                return {
                    "response": response_text,
                    "tool_calls_made": tool_calls_made,
                    "reasoning_trace": reasoning_trace,
                    "iterations": iteration,
                    "tool_errors": tool_error_details,
                    "iteration_guidance": None,
                    "requires_user_parameters": False,
                    "pagination": latest_pagination
                }
        
        # Max iterations reached - force synthesis with what we have
        logger.warning(f"⚠️ Max iterations ({max_iterations}) reached - forcing final synthesis")
        
        # Add a system message to force the LLM to synthesize what it has gathered
        self._messages.append({
            "role": "system",
            "content": ("You have reached the maximum iteration limit. You MUST now synthesize and provide a response based on all the information "
                       "you have gathered so far. Do NOT say you need more iterations. Provide the best answer you can with the data collected. "
                       "If information is incomplete, clearly state what you found and what specific follow-up questions the user can ask.")
        })
        
        # Get final synthesis from the model
        try:
            final_response = await self._openai_client.chat.completions.create(
                model=os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o-mini"),
                messages=self._messages,
                temperature=0.7,
                max_tokens=3000
            )
            
            final_message = final_response.choices[0].message.content
            
            self._messages.append({
                "role": "assistant",
                "content": final_message
            })
            
        except Exception as e:
            logger.error(f"Failed to get final synthesis: {e}")
            final_message = ("I've gathered information through multiple tool calls but reached my iteration limit. "
                           "Based on the data collected, I can provide a partial response. Please ask more specific "
                           "follow-up questions to get the remaining details you need.")
        
        reasoning_trace.append({
            "iteration": iteration,
            "type": "max_iterations_reached",
            "message": "Forced final synthesis with available data"
        })
        
        guidance_message = None
        if tool_error_details:
            guidance_message = self._build_iteration_limit_response(tool_error_details)
            if final_message:
                final_message = f"{final_message}\n\n{guidance_message}".strip()
            else:
                final_message = guidance_message

        logger.info(f"✅ Forced synthesis complete after {iteration} iterations with {tool_calls_made} tool calls")
        
        return {
            "response": final_message,
            "tool_calls_made": tool_calls_made,
            "reasoning_trace": reasoning_trace,
            "iterations": iteration,
            "max_iterations_reached": True,
            "synthesis_forced": True,
            "tool_errors": tool_error_details,
            "iteration_guidance": guidance_message,
            "requires_user_parameters": False,
            "pagination": latest_pagination
        }
    
    async def stream_message(self, user_message: str):
        """
        Stream response to user message using Azure OpenAI streaming
        
        Args:
            user_message: The user's message
            
        Yields:
            Response chunks as they become available
        """
        try:
            enable_cli_executor = self._should_enable_cli_executor(user_message)

            # Ensure OpenAI client is initialized
            await self._ensure_openai_client_initialized()

            if enable_cli_executor:
                await self._ensure_cli_executor_client_initialized()

            tools_for_request = self._select_tool_definitions_for_message(user_message)
            if enable_cli_executor and not any(
                tool.get("function", {}).get("name") in self._cli_executor_tool_names
                for tool in tools_for_request
            ):
                logger.warning("Requested Azure CLI executor tool during streaming, but it is not available in the current tool set.")
            
            # Add user message to conversation
            self._messages.append({
                "role": "user",
                "content": user_message
            })
            
            # Stream from Azure OpenAI
            stream_params = {
                "model": os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o-mini"),
                "messages": self._messages,
                "temperature": 0.7,
                "max_tokens": 2000,
                "stream": True,
            }
            if tools_for_request:
                stream_params["tools"] = tools_for_request
                stream_params["tool_choice"] = "auto"

            stream = await self._openai_client.chat.completions.create(**stream_params)
            
            full_response = ""
            async for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    content = chunk.choices[0].delta.content
                    full_response += content
                    yield {
                        "type": "message",
                        "content": content,
                        "timestamp": datetime.utcnow().isoformat()
                    }
            
            # Add full response to messages
            self._messages.append({
                "role": "assistant",
                "content": full_response
            })
            
            # Signal completion
            yield {
                "type": "complete",
                "session_id": self.session_id,
                "timestamp": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"❌ Error streaming message: {e}")
            yield {
                "type": "error",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            }
    
    async def create_plan(self, user_message: str) -> Dict[str, Any]:
        """
        Create a detailed execution plan for a complex task without executing it.
        This demonstrates the agent's planning capabilities.
        
        Args:
            user_message: The user's request
            
        Returns:
            Dictionary with execution plan
        """
        try:
            await self._ensure_openai_client_initialized()
            
            # Create a planning-specific prompt
            planning_messages = [
                {
                    "role": "system",
                    "content": """You are an expert Azure planning agent. When given a task, create a detailed step-by-step execution plan.

For each step, specify:
1. The action to take
2. The tool(s) needed
3. Required parameters
4. Expected outcome
5. Potential challenges
6. Fallback strategies

Respond in JSON format:
{
  "plan_summary": "High-level overview",
  "complexity": "simple|moderate|complex",
  "estimated_steps": number,
  "steps": [
    {
      "step": number,
      "action": "description",
      "tools": ["tool1", "tool2"],
      "parameters": {"param": "value"},
      "expected_outcome": "what we'll learn",
      "challenges": ["potential issue"],
      "fallback": "alternative approach"
    }
  ],
  "dependencies": "any prerequisites",
  "success_criteria": "how to know if successful"
}"""
                },
                {
                    "role": "user",
                    "content": f"Create an execution plan for: {user_message}"
                }
            ]
            
            response = await self._openai_client.chat.completions.create(
                model=os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o-mini"),
                messages=planning_messages,
                temperature=0.3,  # Lower temperature for more focused planning
                max_tokens=2000
            )
            
            plan_text = response.choices[0].message.content
            
            # Try to parse as JSON
            try:
                plan_data = json.loads(plan_text)
            except:
                # If not valid JSON, return as text
                plan_data = {
                    "plan_summary": "Detailed execution plan",
                    "plan_text": plan_text
                }
            
            return {
                "success": True,
                "user_request": user_message,
                "plan": plan_data,
                "session_id": self.session_id,
                "note": "This is a plan only. Use process_message() to execute."
            }
            
        except Exception as e:
            logger.error(f"❌ Error creating plan: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def list_available_tools(self) -> Dict[str, Any]:
        """Get list of available Azure MCP tools with categorization"""
        try:
            await self._ensure_mcp_client_initialized()
            
            # Categorize tools by service area
            categorized_tools = self._categorize_tools()
            
            return {
                "success": True,
                "tools": self._available_tools,
                "count": len(self._available_tools),
                "categories": categorized_tools,
                "session_id": self.session_id
            }
        except Exception as e:
            logger.error(f"❌ Error listing tools: {e}")
            return {
                "success": False,
                "error": str(e),
                "tools": [],
                "count": 0
            }
    
    def _categorize_tools(self) -> Dict[str, List[str]]:
        """
        Categorize available tools by Azure service area.
        
        Returns:
            Dictionary of categories with tool names
        """
        categories = {
            "Resource Management": [],
            "Storage": [],
            "Compute": [],
            "Databases": [],
            "Networking": [],
            "Security": [],
            "Monitoring": [],
            "AI/ML": [],
            "DevOps": [],
            "Other": []
        }
        
        for tool in self._available_tools:
            tool_name = tool.get("function", {}).get("name", "").lower()
            
            if any(keyword in tool_name for keyword in ["group", "subscription", "resource"]):
                categories["Resource Management"].append(tool_name)
            elif any(keyword in tool_name for keyword in ["storage", "blob", "table", "queue"]):
                categories["Storage"].append(tool_name)
            elif any(keyword in tool_name for keyword in ["vm", "compute", "function", "app", "aks", "container"]):
                categories["Compute"].append(tool_name)
            elif any(keyword in tool_name for keyword in ["sql", "cosmos", "mysql", "postgresql", "redis", "database"]):
                categories["Databases"].append(tool_name)
            elif any(keyword in tool_name for keyword in ["network", "vnet", "subnet", "eventgrid", "eventhub", "servicebus"]):
                categories["Networking"].append(tool_name)
            elif any(keyword in tool_name for keyword in ["keyvault", "rbac", "security", "confidential", "role"]):
                categories["Security"].append(tool_name)
            elif any(keyword in tool_name for keyword in ["monitor", "insight", "log", "metric", "alert"]):
                categories["Monitoring"].append(tool_name)
            elif any(keyword in tool_name for keyword in ["ai", "cognitive", "openai", "search", "speech", "foundry"]):
                categories["AI/ML"].append(tool_name)
            elif any(keyword in tool_name for keyword in ["deploy", "bicep", "terraform", "cli", "devops"]):
                categories["DevOps"].append(tool_name)
            else:
                categories["Other"].append(tool_name)
        
        # Remove empty categories
        return {k: v for k, v in categories.items() if v}
    
    def get_conversation_history(self) -> List[Dict[str, Any]]:
        """Get the current conversation history (excluding system message)"""
        history = []
        for msg in self._messages[1:]:  # Skip system message
            if msg["role"] in ["user", "assistant"]:
                history.append({
                    "role": msg["role"],
                    "content": msg.get("content", ""),
                    "timestamp": datetime.utcnow().isoformat()
                })
        return history
    
    async def analyze_task_complexity(self, user_message: str) -> Dict[str, Any]:
        """
        Analyze the complexity of a task and suggest optimal approach.
        
        Args:
            user_message: The user's request
            
        Returns:
            Dictionary with complexity analysis and recommendations
        """
        try:
            await self._ensure_openai_client_initialized()
            
            analysis_messages = [
                {
                    "role": "system",
                    "content": """You are an expert Azure task complexity analyzer. Analyze the given task and provide:

1. Complexity level (simple, moderate, complex, very_complex)
2. Estimated number of tool calls needed
3. Estimated execution time
4. Required Azure services
5. Potential challenges
6. Recommended approach
7. Success probability

Respond in JSON format:
{
  "complexity": "simple|moderate|complex|very_complex",
  "estimated_tool_calls": number,
  "estimated_time_seconds": number,
  "required_services": ["service1", "service2"],
  "challenges": ["challenge1"],
  "recommended_approach": "description",
  "success_probability": 0.0-1.0,
  "reasoning": "why this assessment"
}"""
                },
                {
                    "role": "user",
                    "content": f"Analyze this task: {user_message}"
                }
            ]
            
            response = await self._openai_client.chat.completions.create(
                model=os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o-mini"),
                messages=analysis_messages,
                temperature=0.3,
                max_tokens=1000
            )
            
            analysis_text = response.choices[0].message.content
            
            try:
                analysis_data = json.loads(analysis_text)
            except:
                analysis_data = {
                    "complexity": "unknown",
                    "analysis_text": analysis_text
                }
            
            return {
                "success": True,
                "task": user_message,
                "analysis": analysis_data,
                "session_id": self.session_id
            }
            
        except Exception as e:
            logger.error(f"❌ Error analyzing task: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def clear_conversation(self):
        """Clear conversation history and reset session"""
        # Keep only the system message
        if self._messages and self._messages[0]["role"] == "system":
            system_msg = self._messages[0]
            self._messages = [system_msg]
        else:
            self._messages = []
        
        self.session_id = str(uuid.uuid4())
        self._paginated_results.clear()
        self._last_paginated_id = None
        logger.info(f"🔄 Conversation cleared (new session: {self.session_id})")
    
    def _summarize_reasoning_trace(self, reasoning_trace: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Summarize the agent's reasoning process for insights.
        
        Args:
            reasoning_trace: List of reasoning steps
            
        Returns:
            Summary of reasoning process
        """
        if not reasoning_trace:
            return {
                "total_steps": 0,
                "reasoning_steps": 0,
                "action_steps": 0,
                "observation_steps": 0,
                "strategy": "direct_response"
            }
        
        summary = {
            "total_steps": len(reasoning_trace),
            "reasoning_steps": sum(1 for t in reasoning_trace if t.get("type") == "reasoning"),
            "action_steps": sum(1 for t in reasoning_trace if t.get("type") == "action"),
            "observation_steps": sum(1 for t in reasoning_trace if t.get("type") == "observation"),
            "synthesis_steps": sum(1 for t in reasoning_trace if t.get("type") == "synthesis"),
            "tools_used": []
        }
        
        # Extract unique tools used
        for trace in reasoning_trace:
            if trace.get("type") == "action" and trace.get("tools"):
                summary["tools_used"].extend(trace["tools"])
        
        summary["tools_used"] = list(set(summary["tools_used"]))
        summary["unique_tools_count"] = len(summary["tools_used"])
        
        # Determine strategy
        if summary["action_steps"] == 0:
            summary["strategy"] = "direct_response"
        elif summary["action_steps"] == 1:
            summary["strategy"] = "single_tool_query"
        elif summary["action_steps"] <= 3:
            summary["strategy"] = "multi_step_workflow"
        else:
            summary["strategy"] = "complex_autonomous_workflow"
        
        return summary
    
    async def explain_reasoning(self, user_message: str) -> Dict[str, Any]:
        """
        Process a message and provide detailed reasoning explanation.
        This is useful for understanding how the agent makes decisions.
        
        Args:
            user_message: The user's message
            
        Returns:
            Dictionary with response and detailed reasoning explanation
        """
        result = await self.process_message(user_message)
        
        if result.get("success") and "reasoning_trace" in result.get("metadata", {}):
            trace = result["metadata"]["reasoning_trace"]
            summary = result["metadata"].get("reasoning_summary", {})
            
            explanation = self._generate_reasoning_explanation(trace, summary)
            result["reasoning_explanation"] = explanation
        
        return result
    
    def _generate_reasoning_explanation(
        self, 
        trace: List[Dict[str, Any]], 
        summary: Dict[str, Any]
    ) -> str:
        """
        Generate human-readable explanation of agent's reasoning.
        
        Args:
            trace: Reasoning trace
            summary: Reasoning summary
            
        Returns:
            Human-readable explanation
        """
        strategy = summary.get("strategy", "unknown")
        tool_count = summary.get("unique_tools_count", 0)
        total_steps = summary.get("total_steps", 0)
        
        explanation_parts = [
            f"🧠 Agentic Reasoning Process:",
            f"",
            f"Strategy: {strategy.replace('_', ' ').title()}",
            f"Total reasoning steps: {total_steps}",
            f"Tools utilized: {tool_count}",
        ]
        
        if tool_count > 0:
            tools = summary.get("tools_used", [])
            explanation_parts.append(f"Tools called: {', '.join(tools)}")
        
        explanation_parts.append("")
        explanation_parts.append("Workflow:")
        
        for i, step in enumerate(trace, 1):
            step_type = step.get("type", "unknown")
            if step_type == "reasoning":
                explanation_parts.append(f"  {i}. 🤔 Reasoning phase - analyzing request")
            elif step_type == "action":
                tools = step.get("tools", [])
                explanation_parts.append(f"  {i}. 🔧 Action phase - calling {len(tools)} tool(s): {', '.join(tools)}")
            elif step_type == "observation":
                results = step.get("tool_results", [])
                success_count = sum(1 for r in results if r.get("success"))
                explanation_parts.append(f"  {i}. 👁️ Observation phase - processing {len(results)} results ({success_count} successful)")
            elif step_type == "synthesis":
                explanation_parts.append(f"  {i}. ✨ Synthesis phase - generating final response")
        
        return "\n".join(explanation_parts)


# Global orchestrator instance
_mcp_orchestrator: Optional[MCPOrchestratorAgent] = None


async def get_mcp_orchestrator() -> MCPOrchestratorAgent:
    """Get or create the global MCP orchestrator instance"""
    global _mcp_orchestrator
    
    if _mcp_orchestrator is None:
        _mcp_orchestrator = MCPOrchestratorAgent()
    
    return _mcp_orchestrator
