# Azure MCP Server Integration

This integration adds support for the [Azure MCP Server](https://learn.microsoft.com/en-us/azure/developer/azure-mcp-server/) to the EOL Agentic Platform, enabling AI-powered interactions with Azure cloud services through the Model Context Protocol (MCP).

## Overview

The Azure MCP Server integration provides:

- **Direct Azure Resource Management**: Query and manage Azure resources programmatically
- **Azure Resource Graph Queries**: Execute KQL queries against Azure Resource Graph
- **Standardized API**: Consistent REST API endpoints for Azure operations
- **UI Interface**: Web-based management console for Azure MCP operations

## Prerequisites

### 1. Node.js
The Azure MCP Server requires Node.js (LTS version):

```bash
# macOS (using Homebrew)
brew install node

# Windows (using Chocolatey)
choco install nodejs-lts

# Or download from https://nodejs.org/
```

### 2. Python Dependencies
Install the required Python packages:

```bash
pip install mcp python-dotenv
```

This is already included in `requirements.txt`.

### 3. Azure Authentication
Authenticate with Azure using the Azure CLI:

```bash
# Install Azure CLI if needed
brew install azure-cli  # macOS
# or download from https://aka.ms/installazurecliwindows

# Sign in to Azure
az login

# Verify your subscription
az account show
```

The Azure MCP Server uses `DefaultAzureCredential`, which will automatically discover your Azure CLI credentials.

## Architecture

### Components

1. **`utils/azure_mcp_client.py`** - Core MCP client implementation
   - Manages connection to Azure MCP Server via stdio
   - Provides high-level methods for common Azure operations
   - Handles tool calling and result processing

2. **`api/azure_mcp.py`** - FastAPI router
   - REST API endpoints for Azure MCP operations
   - Status checking and tool listing
   - Resource management and querying

3. **`templates/azure-mcp.html`** - Web UI
   - Connection status display
   - Available tools listing
   - Resource group browser
   - Azure Resource Graph query interface

### Data Flow

```
User Request → FastAPI Endpoint → AzureMCPClient
                                       ↓
                              npx @azure/mcp server
                                       ↓
                              Azure Services (via Azure SDK)
```

## API Endpoints

### Status & Information

- `GET /api/azure-mcp/status` - Get connection status and tool count
- `GET /api/azure-mcp/tools` - List all available MCP tools

### Resource Management

- `GET /api/azure-mcp/resource-groups` - List all resource groups
- `GET /api/azure-mcp/storage-accounts` - List storage accounts (optional resource group filter)
- `GET /api/azure-mcp/resources/{resource_id}` - Get specific resource details
- `POST /api/azure-mcp/query` - Execute Azure Resource Graph KQL query

### Generic Tool Calling

- `POST /api/azure-mcp/call-tool` - Call any Azure MCP tool with custom arguments

## Usage Examples

### Using the Web UI

1. Navigate to `/azure-mcp` in your browser
2. Check the connection status
3. Click "List Tools" to see available operations
4. Click "Load Resource Groups" to view your Azure resource groups
5. Use the query interface to run custom KQL queries

### Using the REST API

#### Check Status

```bash
curl http://localhost:8000/api/azure-mcp/status
```

#### List Resource Groups

```bash
curl http://localhost:8000/api/azure-mcp/resource-groups
```

#### Execute Resource Graph Query

```bash
curl -X POST http://localhost:8000/api/azure-mcp/query \
  -H "Content-Type: application/json" \
  -d '{"query": "Resources | project name, type, location | limit 10"}'
```

#### Call Custom Tool

```bash
curl -X POST http://localhost:8000/api/azure-mcp/call-tool \
  -H "Content-Type: application/json" \
  -d '{
    "tool_name": "azure_storage-accounts-list",
    "arguments": {"resourceGroupName": "my-rg"}
  }'
```

### Using the Python Client

```python
from utils.azure_mcp_client import get_azure_mcp_client

# Initialize client
client = await get_azure_mcp_client()

# List resource groups
result = await client.list_resource_groups()
print(result)

# Query resources
result = await client.query_resources(
    "Resources | where type =~ 'Microsoft.Storage/storageAccounts' | limit 5"
)
print(result)

# Call any tool
result = await client.call_tool(
    "azure_resources-get",
    {"resourceId": "/subscriptions/.../resourceGroups/..."}
)
print(result)
```

## Available Azure MCP Tools

The Azure MCP Server provides numerous tools for Azure operations:

### Resource Management
- `azure_resources-list` - List all resources
- `azure_resources-get` - Get resource details
- `azure_resources-query` - Execute Resource Graph queries
- `azure_resource-groups-list` - List resource groups

### Storage
- `azure_storage-accounts-list` - List storage accounts
- `azure_storage-blobs-list` - List blob containers
- `azure_storage-tables-list` - List tables

### Compute
- `azure_vm-list` - List virtual machines
- `azure_vm-start` - Start a VM
- `azure_vm-stop` - Stop a VM

### And many more...

Use the `/api/azure-mcp/tools` endpoint or the web UI to see the complete list of available tools.

## Configuration

### Environment Variables

The integration uses standard Azure environment variables:

```bash
# Azure subscription (auto-detected from az login)
AZURE_SUBSCRIPTION_ID=<your-subscription-id>

# Optional: Specify tenant
AZURE_TENANT_ID=<your-tenant-id>
```

### Application Lifecycle

The Azure MCP client is automatically initialized during application startup:

```python
# Startup
@app.on_event("startup")
async def startup_event():
    # ... other initialization ...
    await get_azure_mcp_client()  # Initialize MCP client

# Shutdown
@app.on_event("shutdown")
async def shutdown_event():
    # ... other cleanup ...
    await cleanup_azure_mcp_client()  # Clean up resources
```

## Troubleshooting

### Connection Issues

**Problem**: "Azure MCP Server not available"

**Solutions**:
1. Ensure Node.js is installed: `node --version`
2. Verify Azure authentication: `az account show`
3. Check that npx can run: `npx --version`
4. Install MCP package: `pip install mcp`

### Authentication Issues

**Problem**: "Authentication failed" or "Access denied"

**Solutions**:
1. Re-authenticate with Azure: `az login`
2. Verify your account has proper RBAC roles
3. Check subscription access: `az account list`

### Tool Execution Errors

**Problem**: "Tool call failed"

**Solutions**:
1. Verify resource exists in Azure
2. Check RBAC permissions for the operation
3. Review tool parameters in the error message
4. Test the operation directly with Azure CLI

## Performance Considerations

- **Connection Pooling**: The MCP client maintains a single connection that's reused across requests
- **Tool Discovery**: Available tools are cached after initialization
- **Async Operations**: All Azure MCP calls are async to prevent blocking
- **Error Handling**: Failed operations return detailed error information without crashing the app

## Security

- **Authentication**: Uses Azure DefaultAzureCredential (managed identity in production, Azure CLI locally)
- **Authorization**: All operations are subject to Azure RBAC permissions
- **No Secrets**: No API keys or secrets stored in code
- **Audit Trail**: All operations are logged via Azure Activity Log

## Limitations

1. **Node.js Requirement**: Azure MCP Server requires Node.js to be installed
2. **Network Dependency**: Requires outbound internet access to Azure services
3. **Async Only**: All operations are async; no synchronous API available
4. **Tool Availability**: Available tools depend on the Azure MCP Server version

## Future Enhancements

Potential improvements for this integration:

- [ ] Add caching for frequently accessed Azure resources
- [ ] Implement batch operations for multiple resources
- [ ] Add Azure Resource Manager template deployment
- [ ] Integrate with existing EOL search for Azure VM software discovery
- [ ] Add automated compliance checking using Azure Policy
- [ ] Create dashboards for Azure resource health
- [ ] Add Azure Cost Management integration

## References

- [Azure MCP Server Documentation](https://learn.microsoft.com/en-us/azure/developer/azure-mcp-server/)
- [Model Context Protocol Specification](https://github.com/anthropics/mcp)
- [Azure Resource Graph KQL Documentation](https://learn.microsoft.com/en-us/azure/governance/resource-graph/concepts/query-language)
- [Azure RBAC Documentation](https://learn.microsoft.com/en-us/azure/role-based-access-control/overview)

## Support

For issues related to:
- **Azure MCP Server**: Check the [GitHub repository](https://github.com/microsoft/mcp/tree/main/servers/Azure.Mcp.Server)
- **This Integration**: Open an issue in this repository
- **Azure Services**: Contact Azure Support
