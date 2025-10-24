"""
Azure MCP Server Client Integration
Provides integration with Azure MCP Server for enhanced Azure resource management
"""
import asyncio
import json
import logging
import os
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
            
            # Check if Service Principal authentication is configured
            use_sp = os.getenv("USE_SERVICE_PRINCIPAL", "false").lower() == "true"
            sp_client_id = os.getenv("AZURE_SP_CLIENT_ID")
            sp_client_secret = os.getenv("AZURE_SP_CLIENT_SECRET")
            tenant_id = os.getenv("AZURE_TENANT_ID")
            
            if use_sp and sp_client_id and sp_client_secret and tenant_id:
                logger.info("🔐 Using Service Principal authentication for Azure MCP Server")
                # Set Azure SDK environment variables for service principal auth
                mcp_env["AZURE_CLIENT_ID"] = sp_client_id
                mcp_env["AZURE_CLIENT_SECRET"] = sp_client_secret
                mcp_env["AZURE_TENANT_ID"] = tenant_id
                logger.info(f"   Client ID: {sp_client_id[:8]}...")
                logger.info(f"   Tenant ID: {tenant_id[:8]}...")
            else:
                logger.info("🔐 Using Managed Identity authentication for Azure MCP Server")
                # For Managed Identity, ensure CLIENT_ID is set if available
                managed_identity_client_id = os.getenv("MANAGED_IDENTITY_CLIENT_ID")
                if managed_identity_client_id:
                    mcp_env["AZURE_CLIENT_ID"] = managed_identity_client_id
                    logger.info(f"   Managed Identity Client ID: {managed_identity_client_id[:8]}...")
            
            # Ensure subscription ID and tenant ID are available
            if "SUBSCRIPTION_ID" in os.environ:
                mcp_env["AZURE_SUBSCRIPTION_ID"] = os.environ["SUBSCRIPTION_ID"]
            
            # MCP server configuration - uses npx to run the latest Azure MCP server
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
            self.available_tools = [{
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.inputSchema
                }
            } for tool in tools.tools]
            
            logger.info(f"✅ Azure MCP Server initialized with {len(self.available_tools)} tools")
            for tool in tools.tools:
                logger.debug(f"  - {tool.name}: {tool.description}")
            
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
            self._initialized = False
            logger.info("✅ Azure MCP Server client cleaned up")
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")
    
    def is_initialized(self) -> bool:
        """Check if the client is initialized."""
        return self._initialized
    
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
        
        try:
            logger.info(f"🔧 Calling Azure MCP tool: {tool_name}")
            logger.debug(f"Arguments: {json.dumps(arguments, indent=2)}")
            
            result = await self.session.call_tool(tool_name, arguments)
            
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
                "content": content_list,
                "is_error": getattr(result, 'isError', False)
            }
            
        except Exception as e:
            logger.error(f"❌ Error calling tool '{tool_name}': {e}")
            return {
                "success": False,
                "tool_name": tool_name,
                "error": str(e),
                "is_error": True
            }
    
    async def list_resource_groups(self) -> Dict[str, Any]:
        """
        List all resource groups in the Azure subscription.
        
        Returns:
            Dictionary with resource group information
        """
        return await self.call_tool(
            "azure_resource-groups-list",
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
            "azure_storage-accounts-list",
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
            "azure_resources-get",
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
            "azure_resources-query",
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
