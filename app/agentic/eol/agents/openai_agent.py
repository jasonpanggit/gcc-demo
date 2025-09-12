"""
OpenAI Agent - Provides general chat capability and intelligent query routing
"""
import asyncio
import json
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime

from azure.identity import DefaultAzureCredential
from openai import AzureOpenAI

try:
    from ..utils import get_logger, config
except ImportError:
    import sys
    import os
    sys.path.append(os.path.dirname(os.path.dirname(__file__)))
    from utils import get_logger, config

logger = get_logger(__name__)

# Suppress Azure SDK verbose logging
azure_loggers = [
    "azure.core.pipeline.policies.http_logging_policy",
    "azure.identity",
    "azure.core",
    "openai",
    "urllib3.connectionpool"
]
for azure_logger_name in azure_loggers:
    azure_logger = logging.getLogger(azure_logger_name)
    azure_logger.setLevel(logging.WARNING)


class OpenAIAgent:
    """
    OpenAI agent that provides general chat capability and intelligent query routing.
    Can handle general questions and determine if specialized EOL agents are needed.
    """
    
    def __init__(self):
        self.agent_name = "openai"
        self.agent_type = "openai"
        self._client = None
        self._credential = None
        self.orchestrator = None  # Will be set by orchestrator
        self._initialize_client()
    
    def set_orchestrator(self, orchestrator):
        """Set the orchestrator reference for accessing other agents"""
        self.orchestrator = orchestrator
        logger.info(f"✅ OpenAI agent linked to orchestrator")
    
    def _initialize_client(self):
        """Initialize Azure OpenAI client with managed identity"""
        try:
            if not config.azure.aoai_endpoint or not config.azure.aoai_deployment:
                logger.warning("Azure OpenAI not configured - OpenAI agent will not be available")
                return
            
            # Use managed identity for authentication
            self._credential = DefaultAzureCredential(
                exclude_environment_credential=True,
                exclude_shared_token_cache_credential=True,
                exclude_visual_studio_code_credential=True,
                exclude_powershell_credential=True,
                exclude_cli_credential=True,
            )
            
            logger.info("OpenAI agent credential initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize OpenAI credential: {e}")
            self._credential = None
    
    def _get_client(self):
        """Get Azure OpenAI client with fresh token"""
        try:
            if not self._credential:
                return None
                
            # Get fresh token for Azure Cognitive Services
            token = self._credential.get_token("https://cognitiveservices.azure.com/.default")
            
            client = AzureOpenAI(
                api_version="2024-06-01",
                azure_endpoint=config.azure.aoai_endpoint,
                azure_ad_token=token.token
            )
            
            return client
            
        except Exception as e:
            logger.error(f"Failed to get OpenAI client: {e}")
            return None
    
    async def is_available(self) -> bool:
        """Check if the OpenAI agent is available"""
        return self._credential is not None and config.azure.aoai_endpoint is not None
    
    async def analyze_query_intent(self, query: str, inventory_context: str = "") -> Dict[str, Any]:
        """
        Analyze the user's query to determine intent and routing strategy.
        
        Args:
            query: User's question or request
            inventory_context: Current inventory context for grounding
            
        Returns:
            Dict containing intent analysis and routing recommendations
        """
        if not await self.is_available():
            return {
                "intent": "general",
                "confidence": 0.0,
                "requires_eol_agents": False,
                "suggested_agents": [],
                "reasoning": "OpenAI agent not available"
            }
        
        try:
            # Get fresh client
            client = self._get_client()
            if not client:
                return {
                    "intent": "general_tech",
                    "confidence": 0.0,
                    "requires_eol_agents": False,
                    "suggested_agents": [],
                    "reasoning": "OpenAI client not available"
                }
            
            system_prompt = """You are an intelligent query analyzer for a software lifecycle management system. 
            Analyze user queries to determine intent and routing strategy.

            AVAILABLE AGENT TYPES:
            - microsoft: Microsoft products (Windows, Office, SQL Server, .NET, etc.)
            - redhat: Red Hat products (RHEL, CentOS, Fedora, etc.)
            - ubuntu: Ubuntu and Canonical products
            - oracle: Oracle products (Database, Java, etc.)
            - vmware: VMware products
            - apache: Apache products (HTTP Server, Tomcat, etc.)
            - nodejs: Node.js and npm packages
            - postgresql: PostgreSQL database
            - php: PHP language and frameworks
            - python: Python language and packages
            - os: General operating system queries
            - bing: Web search for unknown software
            - endoflife: Generic EOL database

            QUERY CATEGORIES:
            1. EOL_SPECIFIC: Questions about end-of-life dates, support status, vulnerability info
            2. INVENTORY_FOCUSED: Questions about current software inventory
            3. GENERAL_TECH: General technology questions not requiring EOL data
            4. CONVERSATIONAL: Greetings, thank you, general chat

            Respond with JSON only:
            {
                "intent": "eol_specific|inventory_focused|general_tech|conversational",
                "confidence": 0.0-1.0,
                "requires_eol_agents": true|false,
                "suggested_agents": ["agent1", "agent2"],
                "software_mentioned": ["software1", "software2"],
                "reasoning": "brief explanation"
            }"""
            
            user_prompt = f"""
            USER QUERY: {query}
            
            INVENTORY CONTEXT: {inventory_context[:500] if inventory_context else "No inventory data available"}
            
            Analyze this query and provide routing recommendations."""
            
            response = await asyncio.to_thread(
                client.chat.completions.create,
                model=config.azure.aoai_deployment,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                max_tokens=300,
                temperature=0.1
            )
            
            content = response.choices[0].message.content.strip()
            
            # Try to parse JSON response
            try:
                result = json.loads(content)
                return result
            except json.JSONDecodeError:
                # Fallback if JSON parsing fails
                logger.warning(f"Failed to parse OpenAI response as JSON: {content}")
                return {
                    "intent": "general_tech",
                    "confidence": 0.5,
                    "requires_eol_agents": False,
                    "suggested_agents": [],
                    "reasoning": "Failed to parse intent analysis"
                }
                
        except Exception as e:
            logger.error(f"Error analyzing query intent: {e}")
            return {
                "intent": "general_tech",
                "confidence": 0.0,
                "requires_eol_agents": False,
                "suggested_agents": [],
                "reasoning": f"Error in intent analysis: {str(e)}"
            }
    
    async def generate_response(self, query: str, context: str = "", intent_analysis: Dict = None) -> Dict[str, Any]:
        """
        Generate a conversational response using OpenAI with function calling for specialized agents.
        
        Args:
            query: User's question
            context: Additional context (inventory, EOL data, etc.)
            intent_analysis: Previous intent analysis if available
            
        Returns:
            Dict containing the generated response and metadata
        """
        if not await self.is_available():
            return {
                "response": "I'm sorry, but the AI assistant is currently unavailable. Please try again later.",
                "response_type": "error",
                "tokens_used": 0
            }

        try:
            # Get fresh client
            client = self._get_client()
            if not client:
                return {
                    "response": "I'm sorry, but the AI assistant is currently unavailable. Please try again later.",
                    "response_type": "error",
                    "tokens_used": 0
                }

            # Define available tools
            tools = [
                {
                    "type": "function",
                    "function": {
                        "name": "search_inventory",
                        "description": "Search for specific software by name in the inventory. Use ONLY when users ask to find or search for specific software products by name, not for general inventory viewing. For example: 'find Microsoft Office', 'search for Java', 'look for Adobe products'.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "search_terms": {
                                    "type": "string",
                                    "description": "Keywords to search for in the software inventory (software names, publishers, etc.)"
                                },
                                "computer_filter": {
                                    "type": "string",
                                    "description": "Specific computer name to filter results (optional)"
                                }
                            },
                            "required": ["search_terms"]
                        }
                    }
                },
                {
                    "type": "function",
                    "function": {
                        "name": "get_inventory",
                        "description": "Get comprehensive live inventory data from Log Analytics Workspace. MUST be used when users ask to show, display, list, or see inventory data. Use for requests like 'show me the inventory', 'what software do we have', 'inventory for servers', 'what's installed on windows servers', or any request to view inventory information.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "days": {
                                    "type": "integer",
                                    "description": "Number of days to look back for inventory data (default: 90, max: 365)",
                                    "minimum": 1,
                                    "maximum": 365
                                },
                                "software_filter": {
                                    "type": "string",
                                    "description": "Optional filter to search for specific software or platforms within the full inventory. Examples: 'windows' for Windows software, 'server' for server software, 'windows server' for Windows Server specifically, 'linux' for Linux software. Use this when users specify a particular platform or software type."
                                }
                            },
                            "required": []
                        }
                    }
                },
                {
                    "type": "function",
                    "function": {
                        "name": "check_software_eol",
                        "description": "Check end-of-life (EOL) status for specific software products. Use this when users ask about EOL dates, support status, or lifecycle information for software.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "software_name": {
                                    "type": "string",
                                    "description": "Name of the software to check EOL status for"
                                },
                                "version": {
                                    "type": "string",
                                    "description": "Specific version to check (optional)"
                                }
                            },
                            "required": ["software_name"]
                        }
                    }
                },
                {
                    "type": "function",
                    "function": {
                        "name": "find_approaching_eol",
                        "description": "Find software that is approaching end-of-life within a specified timeframe. This function retrieves inventory, filters by software types, checks EOL status, and returns only software approaching EOL. Use this when users ask about software approaching end-of-life, EOL in the next year, or similar queries.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "days_ahead": {
                                    "type": "integer",
                                    "description": "Number of days from today to check for approaching EOL (default: 365 for one year)",
                                    "minimum": 30,
                                    "maximum": 1095
                                },
                                "software_types": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "description": "Types of software to check. Default: ['application', 'operating_system']"
                                }
                            },
                            "required": []
                        }
                    }
                }
            ]

            # System prompt with tool usage guidance
            system_prompt = f"""You are a professional software lifecycle and end-of-life (EOL) management consultant with access to specialized tools.

AVAILABLE TOOLS:
- search_inventory: Use when users ask about specific software, versions, or targeted searches
- get_inventory: Use when users want comprehensive inventory reports, full listings, or general inventory overview
- check_software_eol: Use when users ask about end-of-life dates, support status, or software lifecycle

CONTEXT INFORMATION:
{context[:1500] if context else "No additional context available"}

CRITICAL TOOL USAGE RULES:
1. ALWAYS use get_inventory when users ask about:
   - "show me the inventory" (any variation)
   - "what software do we have"
   - "inventory report" or "inventory list"
   - "software installed on servers"
   - "what's installed on [server type]"
   - "inventory for [server/system type]"
   - ANY request that asks to display or show inventory data

2. Use search_inventory only for specific searches:
   - "find Microsoft Office"
   - "search for Java versions"
   - "look for specific software name"

3. ALWAYS use check_software_eol for EOL queries:
   - "end of life", "EOL", "support status", "lifecycle information"

MANDATORY: If a user asks to see, show, display, or list inventory data, you MUST use the get_inventory tool.
DO NOT provide general responses about inventory without using the appropriate tool first.

EXAMPLE QUERIES REQUIRING get_inventory:
- "show me the inventory for windows servers" → use get_inventory with software_filter="windows server"
- "what software do we have" → use get_inventory
- "inventory report" → use get_inventory
- "what's installed on our servers" → use get_inventory
- "list all software" → use get_inventory
- "show inventory for linux" → use get_inventory with software_filter="linux"

EXAMPLE QUERIES REQUIRING search_inventory:
- "find Microsoft Office" → use search_inventory with search_terms="Microsoft Office"
- "search for Java versions" → use search_inventory with search_terms="Java"

EXAMPLE QUERIES REQUIRING check_software_eol:
- "when does Ubuntu 20.04 reach end-of-life" → use check_software_eol with software_name="Ubuntu", version="20.04"
- "what is the EOL date for Windows 10" → use check_software_eol with software_name="Windows", version="10"
- "is Java 8 still supported" → use check_software_eol with software_name="Java", version="8"
- "end of life status for CentOS 7" → use check_software_eol with software_name="CentOS", version="7"

EXAMPLE QUERIES REQUIRING find_approaching_eol:
- "what software is approaching end-of-life" → use find_approaching_eol
- "show me software expiring soon" → use find_approaching_eol with days_ahead=180
- "which applications are ending support" → use find_approaching_eol with software_types=["application"]
- "software near end of life" → use find_approaching_eol

RESPONSE GUIDELINES:
- Use tools proactively for inventory and EOL questions
- For general questions, respond directly without using tools
- Always be helpful and provide actionable advice
- Use clear formatting with headers and bullet points
- Keep responses focused and professional

FORMATTING:
- Use ## for main sections
- Use bullet points (•) for lists
- Highlight important information with **bold**
- Provide specific dates when available"""

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": query}
            ]

            try:
                logger.info(f"🤖 OpenAI request: model={config.azure.aoai_deployment}, tools_enabled=True, query='{query[:100]}...', query_length={len(query)}")
                
                # Log key words that should trigger tools
                inventory_keywords = ['inventory', 'show', 'list', 'software', 'installed', 'servers']
                found_keywords = [word for word in inventory_keywords if word.lower() in query.lower()]
                if found_keywords:
                    logger.info(f"🔍 Detected inventory keywords in query: {found_keywords}")
                
                # Determine tool choice based on query content with improved logic
                tool_choice = "auto"
                query_lower = query.lower()
                
                # Enhanced keyword patterns for get_inventory
                get_inventory_patterns = [
                    'show me', 'show the', 'show all', 'display', 'list',
                    'inventory', 'what software', 'what is installed',
                    'software on', 'installed on', 'what do we have'
                ]
                
                # Enhanced keyword patterns for search_inventory  
                search_inventory_patterns = [
                    'find ', 'search for', 'look for', 'locate'
                ]
                
                # Enhanced keyword patterns for check_software_eol
                eol_patterns = [
                    'end of life', 'end-of-life', 'eol', 'support status', 
                    'lifecycle', 'when does', 'reach end', 'support end',
                    'retire', 'deprecated', 'sunset', 'maintenance end'
                ]
                
                # Enhanced keyword patterns for find_approaching_eol
                approaching_eol_patterns = [
                    'approaching end', 'approaching eol', 'software approaching',
                    'expiring soon', 'ending support', 'near end of life',
                    'within a year', 'next year', 'soon to expire',
                    'what software is approaching', 'which software is ending'
                ]
                
                # Check for approaching EOL patterns first (most specific)
                if any(pattern in query_lower for pattern in approaching_eol_patterns):
                    tool_choice = {"type": "function", "function": {"name": "find_approaching_eol"}}
                    matched_patterns = [pattern for pattern in approaching_eol_patterns if pattern in query_lower]
                    logger.info(f"⏰ FORCING find_approaching_eol tool - matched patterns: {matched_patterns}")
                    logger.info(f"🔍 Query: '{query}'")
                
                # Check for EOL patterns (specific software EOL queries)
                elif any(pattern in query_lower for pattern in eol_patterns):
                    tool_choice = {"type": "function", "function": {"name": "check_software_eol"}}
                    matched_patterns = [pattern for pattern in eol_patterns if pattern in query_lower]
                    logger.info(f"🕰️ FORCING check_software_eol tool - matched patterns: {matched_patterns}")
                    logger.info(f"📅 Query: '{query}'")
                
                # Check for get_inventory patterns
                elif any(pattern in query_lower for pattern in get_inventory_patterns):
                    tool_choice = {"type": "function", "function": {"name": "get_inventory"}}
                    matched_patterns = [pattern for pattern in get_inventory_patterns if pattern in query_lower]
                    logger.info(f"🎯 FORCING get_inventory tool - matched patterns: {matched_patterns}")
                    logger.info(f"� Query: '{query}'")
                    
                    # Log what we expect the AI to do with Windows filtering
                    if 'windows' in query_lower:
                        logger.info(f"🪟 Windows detected - AI should set software_filter='windows'")
                    
                # Check for search_inventory patterns (only if get_inventory wasn't triggered)
                elif any(pattern in query_lower for pattern in search_inventory_patterns):
                    tool_choice = {"type": "function", "function": {"name": "search_inventory"}}
                    matched_patterns = [pattern for pattern in search_inventory_patterns if pattern in query_lower]
                    logger.info(f"🎯 FORCING search_inventory tool - matched patterns: {matched_patterns} in query: '{query[:50]}...'")
                
                logger.info(f"🔧 Final tool_choice decision: {tool_choice}")
                
                response = await asyncio.to_thread(
                    client.chat.completions.create,
                    model=config.azure.aoai_deployment,
                    messages=messages,
                    tools=tools,
                    tool_choice=tool_choice,
                    max_tokens=800,
                    temperature=0.3
                )

                # Handle function calls if any
                if response.choices[0].message.tool_calls:
                    logger.info(f"✅ OpenAI requested function calls: {len(response.choices[0].message.tool_calls)}")
                    for tool_call in response.choices[0].message.tool_calls:
                        logger.info(f"🔧 Tool call: {tool_call.function.name} with args: {tool_call.function.arguments}")
                    return await self._handle_function_calls(response, messages, client, tools)
                else:
                    logger.warning(f"⚠️ OpenAI did not request any function calls for query: '{query[:50]}...'")
                    if found_keywords:
                        logger.warning(f"⚠️ Query contained inventory keywords {found_keywords} but no tools were called!")
                    
                    # FALLBACK: If we forced a tool but it didn't work, manually call it
                    if tool_choice != "auto" and isinstance(tool_choice, dict):
                        function_name = tool_choice["function"]["name"]
                        logger.info(f"🚨 FALLBACK: Manually calling {function_name} since forced tool choice failed")
                        
                        if function_name == "get_inventory":
                            # Extract filter from query with smart combination logic
                            args = {"days": 90}
                            query_lower = query.lower()
                            
                            # Check for specific combinations
                            if 'windows' in query_lower and 'server' in query_lower:
                                args["software_filter"] = "windows server"
                                logger.info(f"🎯 Detected combined filter: 'windows server'")
                            elif 'windows' in query_lower:
                                args["software_filter"] = "windows"
                                logger.info(f"🎯 Detected filter: 'windows'")
                            elif 'server' in query_lower:
                                args["software_filter"] = "server"
                                logger.info(f"🎯 Detected filter: 'server'")
                            elif 'linux' in query_lower:
                                args["software_filter"] = "linux"
                                logger.info(f"🎯 Detected filter: 'linux'")
                            else:
                                logger.info(f"🎯 No specific filter detected, showing all inventory")
                            
                            result = await self._call_get_inventory(args)
                            
                            # Format the result professionally
                            raw_response = f"I retrieved the inventory data for you. {result.get('message', '')}"
                            formatted_response = await self.format_professional_response(
                                raw_content=raw_response,
                                response_type="inventory",
                                context_data=result.get("data", {})
                            )
                            
                            # Format the result as if it came from tool calling
                            return {
                                "response": formatted_response,
                                "response_type": "inventory",
                                "tokens_used": 0,
                                "function_calls": [{
                                    "function": "get_inventory",
                                    "arguments": args,
                                    "result": result
                                }]
                            }
                        
                        elif function_name == "check_software_eol":
                            # Extract software name and version from query
                            import re
                            query_lower = query.lower()
                            
                            # Try to extract software name and version
                            software_name = None
                            version = None
                            
                            # Common patterns for software + version
                            patterns = [
                                r'(ubuntu)\s+(\d+\.\d+)',
                                r'(windows)\s+(\d+)',
                                r'(centos)\s+(\d+)',
                                r'(rhel)\s+(\d+)',
                                r'(java)\s+(\d+)',
                                r'(python)\s+(\d+\.\d+)',
                                r'(node\.?js)\s+(\d+)',
                                r'(\w+)\s+(\d+\.\d+\.\d+)',
                                r'(\w+)\s+(\d+\.\d+)',
                                r'(\w+)\s+(\d+)'
                            ]
                            
                            for pattern in patterns:
                                match = re.search(pattern, query_lower)
                                if match:
                                    software_name = match.group(1)
                                    version = match.group(2)
                                    break
                            
                            # If no version found, try to extract just software name
                            if not software_name:
                                # Look for common software names
                                software_keywords = ['ubuntu', 'windows', 'centos', 'rhel', 'java', 'python', 'nodejs', 'mysql', 'postgresql']
                                for keyword in software_keywords:
                                    if keyword in query_lower:
                                        software_name = keyword
                                        break
                            
                            # Default if nothing found
                            if not software_name:
                                software_name = "Unknown Software"
                            
                            args = {"software_name": software_name}
                            if version:
                                args["version"] = version
                            
                            logger.info(f"🎯 Detected software: '{software_name}', version: '{version}'")
                            
                            result = await self._call_check_software_eol(args)
                            
                            # Format the result professionally
                            raw_response = f"I checked the end-of-life status for {software_name}. {result.get('message', '')}"
                            formatted_response = await self.format_professional_response(
                                raw_content=raw_response,
                                response_type="eol",
                                context_data=result.get("data", {})
                            )
                            
                            # Format the result as if it came from tool calling
                            return {
                                "response": formatted_response,
                                "response_type": "eol",
                                "tokens_used": 0,
                                "function_calls": [{
                                    "function": "check_software_eol",
                                    "arguments": args,
                                    "result": result
                                }]
                            }
                        
                        elif function_name == "find_approaching_eol":
                            # Use default parameters if forcing failed
                            args = {
                                "days_ahead": 365,
                                "software_types": ["application", "operating_system"]
                            }
                            
                            logger.info(f"🎯 Using default parameters for approaching EOL search")
                            
                            result = await self._call_find_approaching_eol(args)
                            
                            # Format the result professionally
                            raw_response = f"I searched for software approaching end-of-life. {result.get('message', '')}"
                            formatted_response = await self.format_professional_response(
                                raw_content=raw_response,
                                response_type="approaching_eol",
                                context_data=result.get("data", {})
                            )
                            
                            # Format the result as if it came from tool calling
                            return {
                                "response": formatted_response,
                                "response_type": "approaching_eol",
                                "tokens_used": 0,
                                "function_calls": [{
                                    "function": "find_approaching_eol",
                                    "arguments": args,
                                    "result": result
                                }]
                            }
                
            except Exception as e:
                logger.warning(f"Function calling failed, falling back to regular completion: {e}")
                # Fallback to regular completion without tools
                response = await asyncio.to_thread(
                    client.chat.completions.create,
                    model=config.azure.aoai_deployment,
                    messages=messages,
                    max_tokens=800,
                    temperature=0.3
                )
            
            # Regular response without function calls
            content = response.choices[0].message.content
            tokens_used = response.usage.total_tokens if response.usage else 0
            
            # Apply professional formatting to the response
            formatted_content = await self.format_professional_response(
                raw_content=content,
                response_type="general"
            )
            
            return {
                "response": formatted_content,
                "response_type": "success",
                "tokens_used": tokens_used,
                "timestamp": datetime.utcnow().isoformat(),
                "function_calls": None
            }
            
        except Exception as e:
            logger.error(f"Error generating OpenAI response: {e}")
            return {
                "response": f"I encountered an error while processing your request: {str(e)}",
                "response_type": "error",
                "tokens_used": 0
            }

    async def _handle_function_calls(self, response, messages, client, tools):
        """Handle function calls from OpenAI and execute corresponding agent actions"""
        function_results = []
        
        try:
            # Add assistant message with tool calls to conversation
            messages.append(response.choices[0].message)
            
            for tool_call in response.choices[0].message.tool_calls:
                function_name = tool_call.function.name
                try:
                    function_args = json.loads(tool_call.function.arguments)
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse function arguments: {e}")
                    function_args = {}
                
                logger.info(f"OpenAI calling function: {function_name} with args: {function_args}")
                
                try:
                    if function_name == "search_inventory":
                        result = await self._call_inventory_agent(function_args)
                    elif function_name == "get_inventory":
                        result = await self._call_get_inventory(function_args)
                    elif function_name == "check_software_eol":
                        result = await self._call_check_software_eol(function_args)
                    elif function_name == "find_approaching_eol":
                        result = await self._call_find_approaching_eol(function_args)
                    else:
                        result = {"error": f"Unknown function: {function_name}"}
                    
                    function_results.append({
                        "function": function_name,
                        "arguments": function_args,
                        "result": result
                    })
                    
                    # Add function result to conversation
                    messages.append({
                        "tool_call_id": tool_call.id,
                        "role": "tool",
                        "name": function_name,
                        "content": json.dumps(result)
                    })
                    
                except Exception as e:
                    logger.error(f"Function execution failed for {function_name}: {e}")
                    error_result = {"error": f"Function execution failed: {str(e)}"}
                    function_results.append({
                        "function": function_name,
                        "arguments": function_args,
                        "result": error_result
                    })
                    
                    messages.append({
                        "tool_call_id": tool_call.id,
                        "role": "tool",
                        "name": function_name,
                        "content": json.dumps(error_result)
                    })
            
            # Get final response from OpenAI with function results
            try:
                final_response = await asyncio.to_thread(
                    client.chat.completions.create,
                    model=config.azure.aoai_deployment,
                    messages=messages,
                    max_tokens=1000,
                    temperature=0.3
                )
                
                content = final_response.choices[0].message.content
                total_tokens = (response.usage.total_tokens if response.usage else 0) + \
                              (final_response.usage.total_tokens if final_response.usage else 0)
                
                # Determine response type and context for professional formatting
                response_type = "general"
                context_data = {}
                
                # Extract context from function results for better formatting
                for func_result in function_results:
                    if func_result["function"] == "get_inventory":
                        response_type = "inventory"
                        if func_result["result"].get("success") and "data" in func_result["result"]:
                            context_data = func_result["result"]["data"]
                    elif func_result["function"] == "check_software_eol":
                        response_type = "eol"
                        if func_result["result"].get("success") and "data" in func_result["result"]:
                            context_data = func_result["result"]["data"]
                    elif func_result["function"] == "find_approaching_eol":
                        response_type = "approaching_eol"
                        if func_result["result"].get("success") and "data" in func_result["result"]:
                            context_data = func_result["result"]["data"]
                
                # Apply professional formatting
                formatted_content = await self.format_professional_response(
                    raw_content=content,
                    response_type=response_type,
                    context_data=context_data
                )
                
                return {
                    "response": formatted_content,
                    "response_type": "success_with_tools",
                    "tokens_used": total_tokens,
                    "timestamp": datetime.utcnow().isoformat(),
                    "function_calls": function_results
                }
                
            except Exception as e:
                logger.error(f"Failed to get final response after function calls: {e}")
                # Return a summary based on function results
                summary = f"I executed {len(function_results)} function(s): " + \
                         ", ".join([f"{f['function']} ({'success' if f['result'].get('success') else 'failed'})" 
                                   for f in function_results])
                
                return {
                    "response": summary,
                    "response_type": "function_summary",
                    "tokens_used": response.usage.total_tokens if response.usage else 0,
                    "timestamp": datetime.utcnow().isoformat(),
                    "function_calls": function_results
                }
        
        except Exception as e:
            logger.error(f"Failed to handle function calls: {e}")
            # Return the original response as fallback
            content = response.choices[0].message.content or "Function calling failed, but I'm here to help."
            return {
                "response": content,
                "response_type": "function_error",
                "tokens_used": response.usage.total_tokens if response.usage else 0,
                "timestamp": datetime.utcnow().isoformat(),
                "function_calls": function_results
            }

    async def _call_inventory_agent(self, args):
        """Call the inventory agent with search parameters via orchestrator"""
        try:
            search_terms = args.get("search_terms", "")
            logger.info(f"🔍 _call_inventory_agent: searching for '{search_terms}'")
            
            # Use the orchestrator's inventory agent if available
            if hasattr(self, 'orchestrator') and self.orchestrator and hasattr(self.orchestrator, 'inventory_agent'):
                inventory_agent = self.orchestrator.inventory_agent
                logger.info(f"✅ Using orchestrator's inventory agent for search")
                
                # Use the search_software method
                result = await inventory_agent.search_software(search_terms)
                
                logger.info(f"📊 Search returned {len(result) if isinstance(result, list) else 0} results")
                
                return {
                    "success": True,
                    "data": result,
                    "summary": f"Found {len(result) if isinstance(result, list) else 0} software items matching '{search_terms}'"
                }
            else:
                logger.error(f"❌ Orchestrator or inventory agent not available for search")
                return {
                    "success": False,
                    "error": "Inventory agent not available through orchestrator",
                    "summary": f"Cannot search inventory - orchestrator not configured"
                }
            
        except Exception as e:
            logger.error(f"❌ Error calling inventory agent: {e}")
            return {
                "success": False,
                "error": str(e),
                "summary": f"Failed to search inventory for '{args.get('search_terms', '')}'"
            }

    async def _call_eol_agent(self, args):
        """Call the appropriate EOL agent based on software name"""
        try:
            # Import here to avoid circular imports  
            from .endoflife_agent import EndOfLifeAgent
            
            eol_agent = EndOfLifeAgent()
            software_name = args.get("software_name", "")
            version = args.get("version")
            
            # Check EOL status using the correct method name
            result = await eol_agent.get_eol_data(
                software_name=software_name,
                version=version
            )
            
            return {
                "success": True,
                "data": result,
                "summary": f"Retrieved EOL information for {software_name}" + 
                          (f" version {version}" if version else "")
            }
            
        except Exception as e:
            logger.error(f"Error calling EOL agent: {e}")
            return {
                "success": False,
                "error": str(e),
                "summary": f"Failed to get EOL information for '{args.get('software_name', '')}'"
            }

    async def _call_get_inventory(self, args):
        """Call the inventory agent to get comprehensive inventory data from LAW"""
        try:
            days = args.get("days", 90)
            software_filter = args.get("software_filter", "")
            
            logger.info(f"🔍 _call_get_inventory: days={days}, filter='{software_filter}'")
            
            # Use the orchestrator's inventory agent if available
            if hasattr(self, 'orchestrator') and self.orchestrator and hasattr(self.orchestrator, 'inventory_agent'):
                inventory_agent = self.orchestrator.inventory_agent
                logger.info(f"✅ Using orchestrator's inventory agent for LAW data")
                
                # Use software inventory agent directly since search_software was removed
                if software_filter:
                    logger.info(f"🔍 Getting inventory and filtering for: '{software_filter}'")
                    inventory_data = await inventory_agent.get_software_inventory(days=days)
                    # Apply basic filter on the results
                    if isinstance(inventory_data, dict) and inventory_data.get("data"):
                        filtered_data = [
                            item for item in inventory_data["data"] 
                            if software_filter.lower() in item.get("software_name", "").lower()
                        ]
                        inventory_data["data"] = filtered_data
                        inventory_data["count"] = len(filtered_data)
                else:
                    logger.info(f"📦 Getting full inventory for last {days} days")
                    inventory_data = await inventory_agent.get_software_inventory(days=days)
                
                # Process the inventory data
                if isinstance(inventory_data, list):
                    total_items = len(inventory_data)
                    unique_software = len(set(item.get("software_name", "Unknown") for item in inventory_data))
                    unique_computers = len(set(item.get("computer_name", "Unknown") for item in inventory_data))
                    
                    logger.info(f"📊 Retrieved {total_items} items, {unique_software} unique software, {unique_computers} computers")
                    
                    return {
                        "success": True,
                        "data": {
                            "software_list": inventory_data,
                            "total_items": total_items,
                            "unique_software": unique_software,
                            "unique_computers": unique_computers,
                            "days_looked_back": days,
                            "filter_applied": software_filter or None
                        },
                        "message": f"Successfully retrieved {total_items} software items from LAW"
                    }
                else:
                    logger.warning(f"⚠️ Unexpected inventory data format: {type(inventory_data)}")
                    return {
                        "success": False,
                        "error": "Unexpected data format from inventory agent",
                        "summary": "Failed to retrieve inventory in expected format"
                    }
            else:
                logger.error(f"❌ Orchestrator or inventory agent not available")
                return {
                    "success": False,
                    "error": "Inventory agent not available through orchestrator",
                    "summary": "Cannot access LAW inventory data - orchestrator not configured"
                }
            
        except Exception as e:
            logger.error(f"❌ Error calling inventory agent: {e}")
            return {
                "success": False,
                "error": str(e),
                "summary": f"Failed to retrieve inventory data: {str(e)}"
            }
    
    async def enhance_eol_response(self, query: str, eol_data: Dict, inventory_context: str = "") -> str:
        """
        Enhance EOL agent responses with conversational context and formatting.
        
        Args:
            query: Original user query
            eol_data: Data returned from EOL agents
            inventory_context: Current inventory context
            
        Returns:
            Enhanced, conversational response
        """
        if not await self.is_available():
            return "Enhanced response unavailable - AI assistant not configured."
        
        try:
            # Get fresh client
            client = self._get_client()
            if not client:
                return f"Here's the EOL information I found:\n\n{json.dumps(eol_data, indent=2)}"
            
            system_prompt = """You are a software lifecycle consultant. Take raw EOL data and transform it into a clear, actionable response.

INSTRUCTIONS:
1. Address the user's specific question directly
2. Present EOL information in an organized, readable format
3. Highlight critical dates and risks
4. Provide actionable recommendations
5. Reference inventory data when relevant
6. Use professional but conversational tone

FORMAT GUIDELINES:
- Use ## for sections
- Use bullet points for lists
- Use **bold** for important dates/info
- Include priority levels (Critical/High/Medium/Low)
- End with specific next steps"""

            user_prompt = f"""
USER QUESTION: {query}

EOL DATA RETRIEVED:
{json.dumps(eol_data, indent=2)}

INVENTORY CONTEXT:
{inventory_context[:500] if inventory_context else "No inventory context available"}

Please create a comprehensive, user-friendly response that addresses their question using this data."""

            response = await asyncio.to_thread(
                client.chat.completions.create,
                model=config.azure.aoai_deployment,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                max_tokens=1000,
                temperature=0.2
            )
            
            return response.choices[0].message.content
            
        except Exception as e:
            logger.error(f"Error enhancing EOL response: {e}")
            # Fallback to basic formatting
            return f"Here's the EOL information I found:\n\n{json.dumps(eol_data, indent=2)}"
    
    async def get_inventory(self, days: int = 90, software_filter: str = "") -> Dict[str, Any]:
        """
        Get live inventory data from Log Analytics Workspace (LAW) via the orchestrator's inventory agent.
        
        Args:
            days: Number of days to look back for inventory data (default: 90)
            software_filter: Optional filter to search for specific software
            
        Returns:
            Dictionary containing inventory data, summary statistics, and metadata
        """
        try:
            logger.info(f"🔍 OpenAI Agent retrieving inventory data (days={days}, filter='{software_filter}')")
            
            # Use the orchestrator's inventory agent if available
            if hasattr(self, 'orchestrator') and self.orchestrator and hasattr(self.orchestrator, 'inventory_agent'):
                inventory_agent = self.orchestrator.inventory_agent
                logger.info(f"✅ Using orchestrator's inventory agent")
            else:
                # Fallback: create new inventory agent (for standalone usage)
                logger.warning(f"⚠️ Orchestrator not available, creating new inventory agent")
                from .inventory_agent import InventoryAgent
                inventory_agent = InventoryAgent()
            
            # Get inventory data and apply filter if needed
            if software_filter:
                logger.info(f"🔍 Getting inventory and filtering for: '{software_filter}'")
                inventory_data = await inventory_agent.get_software_inventory(days=days)
                operation_type = "filtered_search"
                # Apply basic filter on the results
                if isinstance(inventory_data, dict) and inventory_data.get("data"):
                    filtered_data = [
                        item for item in inventory_data["data"] 
                        if software_filter.lower() in item.get("software_name", "").lower()
                    ]
                    inventory_data["data"] = filtered_data
                    inventory_data["count"] = len(filtered_data)
            else:
                logger.info(f"📦 Getting full inventory for last {days} days")
                inventory_data = await inventory_agent.get_software_inventory(days=days)
                operation_type = "full_inventory"
            
            # Generate summary statistics
            total_items = len(inventory_data) if isinstance(inventory_data, list) else 0
            unique_software = len(set(item.get("software_name", "Unknown") for item in inventory_data)) if total_items > 0 else 0
            unique_computers = len(set(item.get("computer_name", "Unknown") for item in inventory_data)) if total_items > 0 else 0
            
            logger.info(f"📊 Inventory retrieved: {total_items} items, {unique_software} unique software, {unique_computers} computers")
            
            # Count EOL items if available
            eol_items = 0
            if total_items > 0:
                for item in inventory_data:
                    eol_status = item.get("eol_status", "")
                    if eol_status and eol_status.lower() in ["end_of_life", "approaching_eol"]:
                        eol_items += 1
            
            # Prepare response
            result = {
                "success": True,
                "data": inventory_data,
                "summary": {
                    "operation_type": operation_type,
                    "total_items": total_items,
                    "unique_software": unique_software,
                    "unique_computers": unique_computers,
                    "eol_items": eol_items,
                    "days_queried": days,
                    "software_filter": software_filter or "None",
                    "timestamp": datetime.utcnow().isoformat()
                },
                "message": f"Successfully retrieved {total_items} inventory items" + 
                          (f" matching '{software_filter}'" if software_filter else f" from last {days} days") +
                          (f". Found {eol_items} items with EOL concerns." if eol_items > 0 else ".")
            }
            
            logger.info(f"✅ OpenAI Agent inventory retrieval successful: {total_items} items")
            return result
            
        except Exception as e:
            logger.error(f"❌ Error retrieving inventory data: {e}")
            return {
                "success": False,
                "error": str(e),
                "data": [],
                "summary": {
                    "operation_type": "error",
                    "total_items": 0,
                    "unique_software": 0,
                    "unique_computers": 0,
                    "eol_items": 0,
                    "days_queried": days,
                    "software_filter": software_filter or "None",
                    "timestamp": datetime.utcnow().isoformat()
                },
                "message": f"Failed to retrieve inventory data: {str(e)}"
            }
    
    async def get_agent_status(self) -> Dict[str, Any]:
        """Get current status of the OpenAI agent"""
        is_available = await self.is_available()
        
        return {
            "agent_name": self.agent_name,
            "agent_type": self.agent_type,
            "status": "available" if is_available else "unavailable",
            "endpoint_configured": bool(config.azure.aoai_endpoint),
            "deployment_configured": bool(config.azure.aoai_deployment),
            "last_check": datetime.utcnow().isoformat()
        }

    async def _call_check_software_eol(self, args):
        """Call the EOL agent to check software end-of-life status"""
        try:
            software_name = args.get("software_name", "")
            version = args.get("version", "")
            
            if not software_name:
                return {
                    "success": False,
                    "error": "Software name is required",
                    "summary": "No software name provided"
                }
            
            # Call the EOL agent through orchestrator
            if hasattr(self, 'orchestrator') and self.orchestrator:
                eol_result = await self.orchestrator.eol_agent.check_eol_status(software_name, version)
                return {
                    "success": True,
                    "data": eol_result,
                    "summary": f"EOL status for {software_name} {version}".strip()
                }
            else:
                # Fallback: direct call if orchestrator not available
                return {
                    "success": False,
                    "error": "EOL agent not available",
                    "summary": f"Cannot check EOL status for {software_name}"
                }
                
        except Exception as e:
            logger.error(f"Error calling check_software_eol: {e}")
            return {
                "success": False,
                "error": str(e),
                "summary": f"Failed to check EOL status for {software_name}"
            }

    async def _call_find_approaching_eol(self, args):
        """Find software that is approaching end-of-life within specified timeframe"""
        try:
            from datetime import datetime, timedelta
            import json
            
            days_ahead = args.get("days_ahead", 365)
            software_types = args.get("software_types", ["application", "operating_system"])
            
            logger.info(f"🔍 Finding software approaching EOL within {days_ahead} days")
            
            # Step 1: Get inventory data
            inventory_result = await self._call_get_inventory({"days": 90})
            
            if not inventory_result.get("success", False):
                return {
                    "success": False,
                    "error": "Failed to retrieve inventory",
                    "summary": "Could not get inventory data to check for approaching EOL"
                }
            
            inventory_data = inventory_result.get("data", {})
            software_list = inventory_data.get("software_list", [])
            
            logger.info(f"📦 Retrieved {len(software_list)} software items from inventory")
            
            # Step 2: Filter by software types
            filtered_software = []
            for software in software_list:
                software_type = software.get("type", "").lower()
                if any(sw_type in software_type for sw_type in software_types):
                    filtered_software.append(software)
            
            logger.info(f"🔍 Filtered to {len(filtered_software)} software items matching types: {software_types}")
            
            # Step 3: Check EOL status for each software
            approaching_eol = []
            today = datetime.now()
            cutoff_date = today + timedelta(days=days_ahead)
            
            for software in filtered_software[:20]:  # Limit to 20 to avoid too many API calls
                software_name = software.get("name", "").strip()
                version = software.get("version", "").strip()
                
                if not software_name:
                    continue
                
                logger.info(f"🕰️ Checking EOL for {software_name} {version}".strip())
                
                # Check EOL status
                eol_result = await self._call_check_software_eol({
                    "software_name": software_name,
                    "version": version
                })
                
                if eol_result.get("success", False):
                    eol_data = eol_result.get("data", {})
                    eol_date_str = eol_data.get("eol_date")
                    
                    if eol_date_str:
                        try:
                            # Try to parse various date formats
                            eol_date = None
                            for date_format in ["%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%Y/%m/%d"]:
                                try:
                                    eol_date = datetime.strptime(eol_date_str, date_format)
                                    break
                                except ValueError:
                                    continue
                            
                            if eol_date and eol_date <= cutoff_date:
                                days_until_eol = (eol_date - today).days
                                approaching_eol.append({
                                    "software_name": software_name,
                                    "version": version,
                                    "eol_date": eol_date_str,
                                    "days_until_eol": days_until_eol,
                                    "type": software.get("type", "unknown"),
                                    "computer_name": software.get("computer_name", "unknown")
                                })
                                logger.info(f"⚠️ Found approaching EOL: {software_name} {version} - {days_until_eol} days")
                        except Exception as e:
                            logger.warning(f"Could not parse EOL date '{eol_date_str}' for {software_name}: {e}")
            
            # Step 4: Sort by days until EOL (most urgent first)
            approaching_eol.sort(key=lambda x: x["days_until_eol"])
            
            logger.info(f"⚠️ Found {len(approaching_eol)} software items approaching EOL")
            
            return {
                "success": True,
                "data": {
                    "approaching_eol_count": len(approaching_eol),
                    "approaching_eol_software": approaching_eol,
                    "checked_software_count": len(filtered_software),
                    "days_ahead": days_ahead,
                    "software_types": software_types
                },
                "summary": f"Found {len(approaching_eol)} software items approaching end-of-life within {days_ahead} days"
            }
            
        except Exception as e:
            logger.error(f"Error in find_approaching_eol: {e}")
            return {
                "success": False,
                "error": str(e),
                "summary": f"Failed to find approaching EOL software: {str(e)}"
            }

    async def format_professional_response(self, raw_content: str, response_type: str = "general", context_data: Dict = None) -> str:
        """
        DISABLED: Professional formatting disabled to avoid 502 errors.
        Simply returns the raw content without OpenAI processing.
        
        Args:
            raw_content: The raw response content to format
            response_type: Type of response (inventory, eol, approaching_eol, general)
            context_data: Additional context data for enhanced formatting
            
        Returns:
            Raw content string (formatting disabled)
        """
        # Professional formatting disabled - return raw content
        logger.info("Professional formatting disabled, returning raw content")
        return raw_content
    
    def _basic_format_fallback(self, content: str, response_type: str) -> str:
        """
        Fallback formatting when OpenAI formatting is not available
        """
        try:
            # Basic formatting improvements
            formatted = content.strip()
            
            # Add response type header
            type_headers = {
                "inventory": "📦 **Software Inventory Report**",
                "eol": "🕰️ **End-of-Life Information**", 
                "approaching_eol": "⚠️ **Software Approaching End-of-Life**",
                "general": "ℹ️ **Information Summary**"
            }
            
            header = type_headers.get(response_type, "📋 **Technical Report**")
            
            # Simple formatting improvements
            formatted = f"{header}\n\n{formatted}"
            
            # Add basic structure
            if "\n" not in formatted:
                # Single line responses
                formatted = f"{header}\n\n• {formatted}"
            
            logger.info(f"Applied basic formatting fallback for {response_type}")
            return formatted
            
        except Exception as e:
            logger.error(f"Error in basic formatting fallback: {e}")
            return content
