"""
Azure MCP Server Client Integration
Provides integration with Azure MCP Server for enhanced Azure resource management
"""
import asyncio
import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

logger = logging.getLogger(__name__)


class AzureMCPClient:
    """
    Client for Azure MCP Server integration.
    
    Provides access to Azure resources through the Model Context Protocol,
    enabling AI-powered interactions with Azure services.
    """
    
    def __init__(self):
        """Initialize the Azure MCP client."""
        self.session: Optional[ClientSession] = None
        self.available_tools: List[Dict[str, Any]] = []
        self._initialized = False
        self._read = None
        self._write = None
        self._stdio_context = None
        self._session_context = None
        self._tool_name_map: Dict[str, str] = {}
        self._auth_mode: Optional[str] = None

    @staticmethod
    def _resolve_auth_mode() -> str:
        use_sp_flag = os.getenv("USE_SERVICE_PRINCIPAL")
        sp_client_id = os.getenv("AZURE_SP_CLIENT_ID")
        sp_client_secret = os.getenv("AZURE_SP_CLIENT_SECRET")
        tenant_id = os.getenv("AZURE_TENANT_ID")

        if use_sp_flag is None:
            use_sp = bool(sp_client_id and sp_client_secret and tenant_id)
        else:
            use_sp = use_sp_flag.lower() == "true"

        if use_sp and sp_client_id and sp_client_secret and tenant_id:
            return "service_principal"
        return "managed_identity"
        
    async def initialize(self) -> bool:
        """
        Initialize the Azure MCP Server connection.
        Supports both Service Principal and Managed Identity authentication.
        
        Returns:
            bool: True if initialization successful, False otherwise
        """
        try:
            logger.info("🔧 Initializing Azure MCP Server client...")
            
            # Prepare environment variables for MCP server
            # The Azure MCP server will use these for authentication
            mcp_env = os.environ.copy()
            
            # Check if Service Principal authentication is configured. We allow
            # explicit opt-in via USE_SERVICE_PRINCIPAL, but also auto-detect when
            # the standard AZURE_SP_* variables are provided to avoid silent
            # fallbacks to Managed Identity.
            use_sp_flag = os.getenv("USE_SERVICE_PRINCIPAL")
            sp_client_id = os.getenv("AZURE_SP_CLIENT_ID")
            sp_client_secret = os.getenv("AZURE_SP_CLIENT_SECRET")
            tenant_id = os.getenv("AZURE_TENANT_ID")

            if use_sp_flag is None:
                use_sp = bool(sp_client_id and sp_client_secret and tenant_id)
            else:
                use_sp = use_sp_flag.lower() == "true"
            
            if use_sp and sp_client_id and sp_client_secret and tenant_id:
                self._auth_mode = "service_principal"
                logger.info("🔐 Using Service Principal authentication for Azure MCP Server")
                # Set Azure SDK environment variables for service principal auth
                mcp_env["AZURE_CLIENT_ID"] = sp_client_id
                mcp_env["AZURE_CLIENT_SECRET"] = sp_client_secret
                mcp_env["AZURE_TENANT_ID"] = tenant_id
                logger.info(f"   Client ID: {sp_client_id[:8]}...")
                logger.info(f"   Tenant ID: {tenant_id[:8]}...")
            else:
                if use_sp:
                    logger.warning(
                        "Service Principal authentication requested but credentials are incomplete; "
                        "falling back to Managed Identity"
                    )
                self._auth_mode = "managed_identity"
                logger.info("🔐 Using Managed Identity authentication for Azure MCP Server")
                # For Managed Identity, ensure CLIENT_ID is set if available
                managed_identity_client_id = os.getenv("MANAGED_IDENTITY_CLIENT_ID")
                if managed_identity_client_id:
                    mcp_env["AZURE_CLIENT_ID"] = managed_identity_client_id
                    logger.info(f"   Managed Identity Client ID: {managed_identity_client_id[:8]}...")
            
            # Ensure subscription ID and tenant ID are available
            if "SUBSCRIPTION_ID" in os.environ:
                mcp_env["AZURE_SUBSCRIPTION_ID"] = os.environ["SUBSCRIPTION_ID"]
            
            # MCP server configuration - wraps npx execution to filter non-JSON stdout
            wrapper_path = (
                Path(__file__).resolve().parent.parent
                / "mcp_servers"
                / "json_stdout_filter.js"
            )

            if wrapper_path.is_file():
                server_params = StdioServerParameters(
                    command="node",
                    args=[str(wrapper_path), "npx", "-y", "@azure/mcp@latest", "server", "start"],
                    env=mcp_env
                )
            else:
                logger.warning("JSON stdout filter wrapper not found at %s; falling back to direct npx execution", wrapper_path)
                server_params = StdioServerParameters(
                    command="npx",
                    args=["-y", "@azure/mcp@latest", "server", "start"],
                    env=mcp_env
                )
            
            # Connect to MCP server via stdio
            self._stdio_context = stdio_client(server_params)
            self._read, self._write = await self._stdio_context.__aenter__()
            
            # Create client session
            self._session_context = ClientSession(self._read, self._write)
            self.session = await self._session_context.__aenter__()
            
            # Initialize session
            await self.session.initialize()
            
            # List and cache available tools
            tools = await self.session.list_tools()
            self.available_tools = []
            self._tool_name_map.clear()
            for tool in tools.tools:
                original_name = tool.name
                safe_name = self._get_safe_tool_name(original_name)
                self._tool_name_map[safe_name] = original_name
                logger.info(
                    "🛠️ Registered Azure MCP tool: %s → %s",
                    safe_name,
                    original_name,
                )
                self.available_tools.append(
                    {
                        "type": "function",
                        "function": {
                            "name": safe_name,
                            "description": tool.description,
                            "parameters": tool.inputSchema,
                        },
                    }
                )
            
            logger.info(f"✅ Azure MCP Server initialized with {len(self.available_tools)} tools")
            for tool in tools.tools:
                safe_name = self._resolve_safe_name(tool.name)
                logger.debug(
                    "  - %s (sanitized: %s): %s",
                    tool.name,
                    safe_name,
                    tool.description,
                )
            
            self._initialized = True
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize Azure MCP Server: {e}")
            logger.debug(f"Error details: {e}", exc_info=True)
            return False
    
    async def cleanup(self):
        """Clean up resources and close connections."""
        try:
            if self._session_context:
                await self._session_context.__aexit__(None, None, None)
            if self._stdio_context:
                await self._stdio_context.__aexit__(None, None, None)
            self._tool_name_map.clear()
            self._initialized = False
            logger.info("✅ Azure MCP Server client cleaned up")
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")
    
    def is_initialized(self) -> bool:
        """Check if the client is initialized."""
        return self._initialized

    def get_auth_mode(self) -> str:
        """Return the resolved authentication mode for the MCP server."""
        return self._auth_mode or self._resolve_auth_mode()
    
    def get_available_tools(self) -> List[Dict[str, Any]]:
        """
        Get the list of available Azure MCP tools.
        
        Returns:
            List of tool definitions in OpenAI function calling format
        """
        return self.available_tools
    
    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        Call an Azure MCP Server tool.
        
        Args:
            tool_name: Name of the tool to call
            arguments: Tool arguments as a dictionary
            
        Returns:
            Tool execution result
            
        Raises:
            RuntimeError: If client is not initialized
            ValueError: If tool call fails
        """
        if not self._initialized or not self.session:
            raise RuntimeError("Azure MCP client not initialized. Call initialize() first.")
        
        resolved_name = self._tool_name_map.get(tool_name, tool_name)

        try:
            logger.info(
                "🔧 Calling Azure MCP tool: %s (resolved: %s)",
                tool_name,
                resolved_name,
            )
            try:
                serialized_args = json.dumps(arguments, ensure_ascii=False, indent=2)
            except (TypeError, ValueError):  # pragma: no cover - defensive serialization
                serialized_args = str(arguments)
            logger.info("🧾 Tool arguments: %s", serialized_args)
            
            result = await self.session.call_tool(resolved_name, arguments)
            
            logger.info(f"✅ Tool '{tool_name}' executed successfully")
            logger.debug(f"Result: {result.content}")
            
            # Extract text content from MCP response
            # result.content is a list of TextContent or other content types
            content_list = []
            if isinstance(result.content, list):
                for item in result.content:
                    # TextContent objects have a 'text' attribute
                    if hasattr(item, 'text'):
                        content_list.append(item.text)
                    # ImageContent objects have 'data' and 'mimeType'
                    elif hasattr(item, 'data'):
                        content_list.append({
                            "type": "image",
                            "data": item.data,
                            "mimeType": getattr(item, 'mimeType', 'application/octet-stream')
                        })
                    else:
                        # Fallback: try to convert to string
                        content_list.append(str(item))
            else:
                # Single content item
                if hasattr(result.content, 'text'):
                    content_list.append(result.content.text)
                else:
                    content_list.append(str(result.content))
            
            return {
                "success": True,
                "tool_name": tool_name,
                "original_tool_name": resolved_name,
                "content": content_list,
                "is_error": getattr(result, 'isError', False)
            }
            
        except Exception as e:
            logger.error(f"❌ Error calling tool '{tool_name}': {e}")
            return {
                "success": False,
                "tool_name": tool_name,
                "original_tool_name": resolved_name,
                "error": str(e),
                "is_error": True
            }

    def _resolve_safe_name(self, original_name: str) -> str:
        """Look up the sanitized tool name for a given original name without mutating state."""

        for safe_name, mapped_original in self._tool_name_map.items():
            if mapped_original == original_name:
                return safe_name
        return original_name

    def _get_safe_tool_name(self, original_name: str) -> str:
        """Return a sanitized, unique tool name acceptable to the Azure OpenAI APIs."""

        sanitized = re.sub(r"[^0-9a-zA-Z_-]", "_", original_name or "")
        sanitized = sanitized.strip("_") or "tool"
        if sanitized[0].isdigit():
            sanitized = f"tool_{sanitized}"

        base_name = sanitized
        suffix = 1
        # Ensure uniqueness but map same original name to same sanitized name
        while sanitized in self._tool_name_map and self._tool_name_map[sanitized] != original_name:
            suffix += 1
            sanitized = f"{base_name}_{suffix}"

        return sanitized
    
    async def list_resource_groups(self) -> Dict[str, Any]:
        """
        List all resource groups in the Azure subscription.
        
        Returns:
            Dictionary with resource group information
        """
        return await self.call_tool(
            self._resolve_safe_name("azure_resource-groups-list"),
            {}
        )
    
    async def list_storage_accounts(self, resource_group: Optional[str] = None) -> Dict[str, Any]:
        """
        List storage accounts in the subscription or a specific resource group.
        
        Args:
            resource_group: Optional resource group name to filter by
            
        Returns:
            Dictionary with storage account information
        """
        args = {}
        if resource_group:
            args["resourceGroupName"] = resource_group
        
        return await self.call_tool(
            self._resolve_safe_name("azure_storage-accounts-list"),
            args
        )
    
    async def get_resource_by_id(self, resource_id: str) -> Dict[str, Any]:
        """
        Get details of a specific Azure resource by its ID.
        
        Args:
            resource_id: The Azure resource ID
            
        Returns:
            Dictionary with resource information
        """
        return await self.call_tool(
            self._resolve_safe_name("azure_resources-get"),
            {"resourceId": resource_id}
        )
    
    async def query_resources(self, query: str) -> Dict[str, Any]:
        """
        Query Azure resources using Azure Resource Graph.
        
        Args:
            query: KQL query string
            
        Returns:
            Dictionary with query results
        """
        return await self.call_tool(
            self._resolve_safe_name("azure_resources-query"),
            {"query": query}
        )


# Global Azure MCP client instance
_azure_mcp_client: Optional[AzureMCPClient] = None


async def get_azure_mcp_client() -> AzureMCPClient:
    """
    Get the global Azure MCP client instance, initializing if needed.
    
    Returns:
        Initialized AzureMCPClient instance
        
    Raises:
        RuntimeError: If initialization fails
    """
    global _azure_mcp_client
    
    if _azure_mcp_client is None:
        _azure_mcp_client = AzureMCPClient()
        success = await _azure_mcp_client.initialize()
        if not success:
            raise RuntimeError("Failed to initialize Azure MCP client")
    
    return _azure_mcp_client


async def cleanup_azure_mcp_client():
    """Clean up the global Azure MCP client instance."""
    global _azure_mcp_client
    
    if _azure_mcp_client:
        await _azure_mcp_client.cleanup()
        _azure_mcp_client = None
