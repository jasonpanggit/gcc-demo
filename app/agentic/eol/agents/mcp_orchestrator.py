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
from typing import Dict, List, Any, Optional
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
        
        # Agent communication queue for real-time UI streaming
        import asyncio
        self.communication_queue = asyncio.Queue()
        # Buffer to store recent communications (for late-connecting SSE streams)
        self.communication_buffer = []
        self.max_buffer_size = 100
        
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
                logger.info(f"✅ Azure MCP client initialized with {len(self._available_tools)} tools")
            except Exception as e:
                logger.error(f"❌ Failed to initialize Azure MCP client: {e}")
                raise
    
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
    
    async def _execute_tool_call(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        """
        Execute an MCP tool and return the result as a string.
        The MCP client now returns JSON-serializable content.
        """
        try:
            logger.info(f"🔧 Calling MCP tool: {tool_name} with args: {arguments}")
            
            result = await self._mcp_client.call_tool(tool_name, arguments)
            
            # Result from MCP client is already serialized and JSON-safe
            if isinstance(result, dict):
                if result.get("success"):
                    content = result.get("content")
                    # Content is a list of text/image content from MCP
                    if isinstance(content, str):
                        return content
                    elif isinstance(content, list):
                        # Process list items
                        text_parts = []
                        for item in content:
                            if isinstance(item, str):
                                text_parts.append(item)
                            elif isinstance(item, dict):
                                # Handle image or other structured content
                                if item.get("type") == "image":
                                    text_parts.append(f"[Image: {item.get('mimeType', 'unknown')}]")
                                else:
                                    # Other structured content - convert to JSON
                                    text_parts.append(json.dumps(item, indent=2))
                            else:
                                # Fallback: convert to string
                                text_parts.append(str(item))
                        
                        # Join all text parts
                        return "\n".join(text_parts) if text_parts else "{}"
                    else:
                        return json.dumps(content, indent=2)
                else:
                    # Tool execution failed
                    error = result.get("error", "Unknown error")
                    return json.dumps({"error": error})
            else:
                # Fallback for unexpected result format
                return json.dumps(result, indent=2)
            
        except Exception as e:
            error_msg = f"Error calling tool {tool_name}: {str(e)}"
            logger.error(error_msg)
            logger.error(traceback.format_exc())
            return json.dumps({"error": error_msg})
    
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
            # Ensure OpenAI client is initialized
            await self._ensure_openai_client_initialized()
            
            # Clear old buffer and start fresh for this request
            self.communication_buffer.clear()
            
            # Add user message to conversation
            self._messages.append({
                "role": "user",
                "content": user_message
            })
            
            logger.info(f"🤖 Processing message (request: {request_id}): {user_message[:100]}...")
            
            # Use LLM function calling to process the message
            logger.info("🔍 Using LLM function calling with all available tools")
            response_result = await self._llm_process_message()
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
                "synthesis_forced": response_result.get("synthesis_forced", False)
            }
            
            # If max iterations reached, add helpful note to response
            if metadata["max_iterations_reached"]:
                logger.info("Adding max iterations notice to response")
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
    
    async def _llm_process_message(self) -> Dict[str, Any]:
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
        failed_tools = {}  # Track failed tool calls for self-correction
        
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
            
            if self._tool_definitions:
                call_params["tools"] = self._tool_definitions
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
                    retry_count = failed_tools.get(function_name, 0)
                    if retry_count > 0:
                        logger.info(f"� Retrying tool '{function_name}' (attempt {retry_count + 1})")
                    
                    logger.info(f"�🔧 Executing tool: {function_name}")
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
                    
                    # Track success/failure for self-correction
                    is_error = False
                    try:
                        result_data = json.loads(tool_result) if isinstance(tool_result, str) else tool_result
                        if isinstance(result_data, dict) and result_data.get("error"):
                            failed_tools[function_name] = failed_tools.get(function_name, 0) + 1
                            logger.warning(f"⚠️ Tool '{function_name}' returned error: {result_data.get('error')[:100]}")
                            is_error = True
                        else:
                            # Success - reset failure count
                            failed_tools.pop(function_name, None)
                    except:
                        pass  # Continue regardless
                    
                    # Push observation to real-time communication stream
                    await self._push_communication(
                        "observation",
                        f"Tool '{function_name}' {'failed' if is_error else 'completed successfully'}",
                        iteration=iteration,
                        tool_result=str(tool_result)[:500],  # Truncate for UI
                        is_error=is_error
                    )
                    
                    tool_results.append({
                        "tool": function_name,
                        "result_length": len(str(tool_result)),
                        "success": function_name not in failed_tools
                    })
                    
                    # Add tool result to messages
                    self._messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "name": function_name,
                        "content": tool_result
                    })
                
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
                    "iterations": iteration
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
        
        logger.info(f"✅ Forced synthesis complete after {iteration} iterations with {tool_calls_made} tool calls")
        
        return {
            "response": final_message,
            "tool_calls_made": tool_calls_made,
            "reasoning_trace": reasoning_trace,
            "iterations": iteration,
            "max_iterations_reached": True,
            "synthesis_forced": True
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
            # Ensure OpenAI client is initialized
            await self._ensure_openai_client_initialized()
            
            # Add user message to conversation
            self._messages.append({
                "role": "user",
                "content": user_message
            })
            
            # Stream from Azure OpenAI
            stream = await self._openai_client.chat.completions.create(
                model=os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o-mini"),
                messages=self._messages,
                tools=self._tool_definitions if self._tool_definitions else None,
                tool_choice="auto",
                temperature=0.7,
                max_tokens=2000,
                stream=True
            )
            
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
