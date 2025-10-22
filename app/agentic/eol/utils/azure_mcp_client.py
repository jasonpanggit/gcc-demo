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
        
        Returns:
            bool: True if initialization successful, False otherwise
        """
        try:
            logger.info("🔧 Initializing Azure MCP Server client...")
            
            # MCP server configuration - uses npx to run the latest Azure MCP server
            server_params = StdioServerParameters(
                command="npx",
                args=["-y", "@azure/mcp@latest", "server", "start"],
                env=None
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
            
            return {
                "success": True,
                "tool_name": tool_name,
                "content": result.content,
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
