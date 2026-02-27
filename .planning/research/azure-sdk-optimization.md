# Azure SDK for Python: Performance and Reliability Best Practices

**Research Date:** 2026-02-27
**Target SDK Version:** Azure SDK for Python (azure-core based libraries)
**Python Version:** 3.9+

---

## Executive Summary

This document provides comprehensive guidance on optimizing Azure SDK for Python applications for production deployment. Key areas covered include connection pooling, credential management, client lifecycle patterns, async operations, and common pitfalls to avoid.

**Key Takeaways:**
- Reuse client instances and credentials across requests (singleton pattern)
- Use DefaultAzureCredential with proper caching for authentication
- Leverage async SDK variants with proper transport configuration
- Configure retry policies, timeouts, and connection pooling for your workload
- Avoid common pitfalls like recreating clients per request

---

## 1. Connection Pooling and HTTP Client Configuration

### 1.1 Understanding Azure SDK Transport Layer

Azure SDK for Python uses a **pipeline architecture** with the transport as the last node. The transport manages HTTP connections and connection pooling.

**Default Transports:**
- **Synchronous:** `RequestsTransport` (uses Python `requests` library)
- **Asynchronous:** `AioHttpTransport` (uses `aiohttp` library)

### 1.2 Connection Pooling Implementation

#### Sync Client with Connection Pooling

The Azure SDK sync transport uses `requests.Session` under the hood, which provides connection pooling by default. To optimize:

```python
import requests
from azure.core.pipeline.transport import RequestsTransport
from azure.mgmt.compute import ComputeManagementClient
from azure.identity import DefaultAzureCredential

# Create a session with custom pool configuration
session = requests.Session()
adapter = requests.adapters.HTTPAdapter(
    pool_connections=10,  # Number of connection pools
    pool_maxsize=20,      # Max connections per pool
    pool_block=False      # Don't block when pool is full
)
session.mount('https://', adapter)

# Create transport with custom session
transport = RequestsTransport(session=session)

# Create client with custom transport
credential = DefaultAzureCredential()
compute_client = ComputeManagementClient(
    credential=credential,
    subscription_id="your-subscription-id",
    transport=transport
)
```

**Best Practices:**
- Set `pool_connections` to the number of unique hosts you'll connect to (typically 5-10)
- Set `pool_maxsize` based on expected concurrency (20-50 for most apps)
- Use `pool_block=False` to fail fast rather than waiting for connections
- Reuse the session across all Azure SDK clients in your application

#### Async Client with Connection Pooling

For async clients, configure the `aiohttp` connector:

```python
import aiohttp
from azure.core.pipeline.transport import AioHttpTransport
from azure.mgmt.compute.aio import ComputeManagementClient
from azure.identity.aio import DefaultAzureCredential

# Create connector with connection pooling
connector = aiohttp.TCPConnector(
    limit=100,           # Total connection limit
    limit_per_host=30,   # Per-host connection limit
    ttl_dns_cache=300    # DNS cache TTL in seconds
)

# Create transport with custom connector
transport = AioHttpTransport(connector=connector)

# Create async client
credential = DefaultAzureCredential()
compute_client = ComputeManagementClient(
    credential=credential,
    subscription_id="your-subscription-id",
    transport=transport
)
```

**Best Practices:**
- Set `limit` to maximum concurrent connections (50-200 depending on load)
- Set `limit_per_host` to prevent overwhelming single endpoints (20-50)
- Enable DNS caching with `ttl_dns_cache` to reduce DNS lookups
- Always close the connector when done: `await connector.close()`

### 1.3 Transport Configuration Options

Key configuration parameters for both sync and async transports:

```python
transport_config = {
    'connection_timeout': 30,        # Connection timeout in seconds (default: 300)
    'read_timeout': 60,              # Read timeout in seconds (default: 300)
    'connection_verify': True,       # SSL verification (default: True)
    'connection_cert': None,         # Client certificate path
    'connection_data_block_size': 4096  # Data block size in bytes
}

# Apply when creating transport
transport = RequestsTransport(**transport_config)
```

**Recommendations:**
- Lower default timeouts (300s is too high for most operations)
- Use 30s connection timeout, 60-120s read timeout as starting points
- Keep SSL verification enabled unless testing locally
- Increase `connection_data_block_size` for large file operations (16384 or 65536)

---

## 2. Credential Management and Caching

### 2.1 DefaultAzureCredential Overview

`DefaultAzureCredential` is the recommended credential type. It attempts multiple authentication methods in order:

**Credential Chain (as of v1.14.0+):**
1. **EnvironmentCredential** - Service principal from environment variables
2. **WorkloadIdentityCredential** - Azure Kubernetes Service workload identity
3. **ManagedIdentityCredential** - Azure managed identity
4. **AzureCliCredential** - Azure CLI credentials
5. **AzurePowerShellCredential** - Azure PowerShell credentials
6. **AzureDeveloperCliCredential** - Azure Developer CLI credentials
7. **InteractiveBrowserCredential** - Interactive browser login (disabled by default)

**Continuation Policy (v1.14.0+):**
- Developer credentials continue on failure (try all)
- Service credentials stop with exception if token retrieval attempted but failed
- This ensures predictable behavior in production while being flexible in development

### 2.2 Credential Caching Best Practices

#### Pattern 1: Singleton Credential Instance

**✅ BEST PRACTICE:**
```python
# Create credential ONCE at application startup
from azure.identity import DefaultAzureCredential

class AzureClientManager:
    _credential = None
    _clients = {}

    @classmethod
    def get_credential(cls):
        """Get or create singleton credential instance."""
        if cls._credential is None:
            cls._credential = DefaultAzureCredential()
        return cls._credential

    @classmethod
    def get_compute_client(cls, subscription_id):
        """Get or create compute client with cached credential."""
        if 'compute' not in cls._clients:
            from azure.mgmt.compute import ComputeManagementClient
            cls._clients['compute'] = ComputeManagementClient(
                credential=cls.get_credential(),
                subscription_id=subscription_id
            )
        return cls._clients['compute']

# Usage
compute_client = AzureClientManager.get_compute_client("sub-id")
```

#### Pattern 2: Application Startup Initialization

**✅ BEST PRACTICE:**
```python
# In your FastAPI/Flask app startup
from contextlib import asynccontextmanager
from fastapi import FastAPI
from azure.identity.aio import DefaultAzureCredential

class AppState:
    credential = None
    compute_client = None
    network_client = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Create credential and clients once
    AppState.credential = DefaultAzureCredential()
    AppState.compute_client = ComputeManagementClient(
        credential=AppState.credential,
        subscription_id=os.getenv("AZURE_SUBSCRIPTION_ID")
    )

    yield

    # Shutdown: Clean up resources
    await AppState.credential.close()

app = FastAPI(lifespan=lifespan)

# Use in routes
@app.get("/vms")
async def list_vms():
    vms = AppState.compute_client.virtual_machines.list_all()
    return {"vms": [vm.name async for vm in vms]}
```

#### Pattern 3: Token Caching with Persistence

For applications requiring persistent token caching across restarts:

```python
from azure.identity import TokenCachePersistenceOptions
from azure.identity import DefaultAzureCredential

# Enable persistent token cache
cache_options = TokenCachePersistenceOptions(
    allow_unencrypted_storage=False,  # Use encrypted storage
    name="my_token_cache"             # Cache file name
)

credential = DefaultAzureCredential(
    cache_persistence_options=cache_options
)
```

**Persistent Cache Benefits:**
- Reduces authentication requests to Azure AD
- Improves startup time
- Maintains tokens across application restarts

**Security Considerations:**
- Never set `allow_unencrypted_storage=True` in production
- Ensure cache files have proper permissions (600 on Linux/macOS)
- Consider using keyring/keychain for sensitive environments

### 2.3 Credential-Specific Optimizations

#### ClientSecretCredential

For service principal authentication with explicit credentials:

```python
from azure.identity import ClientSecretCredential

# Create once and reuse
credential = ClientSecretCredential(
    tenant_id=os.getenv("AZURE_TENANT_ID"),
    client_id=os.getenv("AZURE_CLIENT_ID"),
    client_secret=os.getenv("AZURE_CLIENT_SECRET"),

    # Optional: Cache configuration
    cache_persistence_options=cache_options
)
```

**Performance Tips:**
- Reuse credential instance across all clients
- Token is cached internally by default (in-memory)
- Add persistent cache for long-running services

#### ManagedIdentityCredential

For Azure-hosted applications (VMs, App Service, AKS):

```python
from azure.identity import ManagedIdentityCredential

# System-assigned managed identity
credential = ManagedIdentityCredential()

# User-assigned managed identity (specify client ID)
credential = ManagedIdentityCredential(
    client_id="your-managed-identity-client-id"
)
```

**Benefits:**
- No secrets to manage
- Automatic token refresh
- Zero credential rotation overhead
- Best choice for Azure-hosted workloads

### 2.4 Anti-Patterns to Avoid

**❌ BAD: Creating credential per request**
```python
# DON'T DO THIS
def get_vms():
    credential = DefaultAzureCredential()  # Created every time!
    client = ComputeManagementClient(credential, subscription_id)
    return client.virtual_machines.list_all()
```

**❌ BAD: Not closing credentials in async code**
```python
# DON'T DO THIS
async def get_vms():
    credential = DefaultAzureCredential()
    client = ComputeManagementClient(credential, subscription_id)
    vms = await client.virtual_machines.list_all()
    # Credential never closed, leaks resources!
    return vms
```

**✅ GOOD: Use context manager**
```python
async def get_vms():
    async with DefaultAzureCredential() as credential:
        client = ComputeManagementClient(credential, subscription_id)
        vms = await client.virtual_machines.list_all()
    return vms  # Credential properly closed
```

---

## 3. Client Lifecycle Management

### 3.1 Singleton Pattern for Client Instances

Azure SDK clients are **thread-safe** and should be created once and reused.

**✅ BEST PRACTICE: Application-Level Singleton**

```python
from typing import Dict, Optional
from azure.identity import DefaultAzureCredential
from azure.mgmt.compute import ComputeManagementClient
from azure.mgmt.network import NetworkManagementClient
from azure.mgmt.storage import StorageManagementClient

class AzureSDKManager:
    """Centralized Azure SDK client manager with singleton pattern."""

    def __init__(self, subscription_id: str):
        self.subscription_id = subscription_id
        self._credential: Optional[DefaultAzureCredential] = None
        self._clients: Dict[str, any] = {}

    @property
    def credential(self) -> DefaultAzureCredential:
        """Lazy-load credential (created once)."""
        if self._credential is None:
            self._credential = DefaultAzureCredential()
        return self._credential

    @property
    def compute(self) -> ComputeManagementClient:
        """Get cached compute management client."""
        if 'compute' not in self._clients:
            self._clients['compute'] = ComputeManagementClient(
                credential=self.credential,
                subscription_id=self.subscription_id
            )
        return self._clients['compute']

    @property
    def network(self) -> NetworkManagementClient:
        """Get cached network management client."""
        if 'network' not in self._clients:
            self._clients['network'] = NetworkManagementClient(
                credential=self.credential,
                subscription_id=self.subscription_id
            )
        return self._clients['network']

    @property
    def storage(self) -> StorageManagementClient:
        """Get cached storage management client."""
        if 'storage' not in self._clients:
            self._clients['storage'] = StorageManagementClient(
                credential=self.credential,
                subscription_id=self.subscription_id
            )
        return self._clients['storage']

    def close(self):
        """Close credential and clean up resources."""
        if self._credential:
            self._credential.close()
        self._clients.clear()

# Global instance
_azure_manager: Optional[AzureSDKManager] = None

def get_azure_manager() -> AzureSDKManager:
    """Get global Azure SDK manager instance."""
    global _azure_manager
    if _azure_manager is None:
        _azure_manager = AzureSDKManager(
            subscription_id=os.getenv("AZURE_SUBSCRIPTION_ID")
        )
    return _azure_manager
```

### 3.2 Async Client Lifecycle

For async applications, use proper context management:

```python
from contextlib import asynccontextmanager
from azure.identity.aio import DefaultAzureCredential
from azure.mgmt.compute.aio import ComputeManagementClient

class AsyncAzureManager:
    """Async-safe Azure SDK manager."""

    def __init__(self, subscription_id: str):
        self.subscription_id = subscription_id
        self._credential: Optional[DefaultAzureCredential] = None
        self._compute_client: Optional[ComputeManagementClient] = None

    async def __aenter__(self):
        """Initialize clients on context entry."""
        self._credential = DefaultAzureCredential()
        self._compute_client = ComputeManagementClient(
            credential=self._credential,
            subscription_id=self.subscription_id
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Clean up clients on context exit."""
        if self._compute_client:
            await self._compute_client.close()
        if self._credential:
            await self._credential.close()

    @property
    def compute(self) -> ComputeManagementClient:
        """Get compute client (must be used within async context)."""
        if self._compute_client is None:
            raise RuntimeError("Manager not initialized. Use async with.")
        return self._compute_client

# Usage
async def main():
    async with AsyncAzureManager(subscription_id) as azure:
        vms = await azure.compute.virtual_machines.list_all()
        async for vm in vms:
            print(vm.name)
```

### 3.3 Client Configuration Best Practices

When creating clients, configure them for your workload:

```python
from azure.mgmt.compute import ComputeManagementClient
from azure.identity import DefaultAzureCredential

credential = DefaultAzureCredential()

compute_client = ComputeManagementClient(
    credential=credential,
    subscription_id=subscription_id,

    # Logging
    logging_enable=True,  # Enable for debugging

    # Retry configuration
    retry_total=3,        # Lower for faster failures
    retry_mode='exponential',

    # Timeout configuration
    connection_timeout=30,  # 30s to establish connection
    read_timeout=120,       # 2min to complete operation

    # Proxy configuration (if needed)
    proxies={
        'http': 'http://proxy.example.com:8080',
        'https': 'http://proxy.example.com:8080',
    }
)
```

### 3.4 Per-Request Configuration

Override client defaults for specific operations:

```python
# Client-level defaults
compute_client = ComputeManagementClient(
    credential=credential,
    subscription_id=subscription_id,
    connection_timeout=30
)

# Override for specific operation
vm = compute_client.virtual_machines.get(
    resource_group_name="my-rg",
    vm_name="my-vm",

    # Override defaults for this call
    connection_timeout=10,  # Faster timeout for this operation
    retry_total=1,          # Only retry once
)
```

---

## 4. Async Patterns with Azure SDK

### 4.1 When to Use Async

**Use async when:**
- Your application handles multiple concurrent requests (web servers)
- You need to call multiple Azure operations in parallel
- You're building high-throughput data processing pipelines
- Your application uses async frameworks (FastAPI, aiohttp, etc.)

**Avoid async when:**
- Building simple scripts or CLI tools
- Operations are sequential and not I/O bound
- Team lacks async Python experience

### 4.2 Installing Async Transport

Async Azure SDK clients require an async transport library:

```bash
# Install async identity and SDK packages
pip install azure-identity[aio]
pip install azure-mgmt-compute[aio]
pip install aiohttp  # Required async transport
```

### 4.3 Async Client Patterns

#### Pattern 1: Parallel Operations

```python
import asyncio
from azure.identity.aio import DefaultAzureCredential
from azure.mgmt.compute.aio import ComputeManagementClient
from azure.mgmt.network.aio import NetworkManagementClient

async def get_infrastructure_inventory(subscription_id: str):
    """Fetch VMs and networks in parallel."""
    async with DefaultAzureCredential() as credential:
        # Create clients
        compute = ComputeManagementClient(credential, subscription_id)
        network = NetworkManagementClient(credential, subscription_id)

        # Execute in parallel
        vms_task = compute.virtual_machines.list_all()
        vnets_task = network.virtual_networks.list_all()

        # Gather results
        vms = [vm async for vm in vms_task]
        vnets = [vnet async for vnet in vnets_task]

        # Clean up
        await compute.close()
        await network.close()

        return {"vms": vms, "vnets": vnets}

# Run
result = asyncio.run(get_infrastructure_inventory("sub-id"))
```

#### Pattern 2: Batch Processing

```python
async def process_vm_batch(vm_names: list[str], subscription_id: str):
    """Process multiple VMs concurrently."""
    async with DefaultAzureCredential() as credential:
        compute = ComputeManagementClient(credential, subscription_id)

        # Create tasks for all VMs
        tasks = [
            compute.virtual_machines.get("my-rg", vm_name)
            for vm_name in vm_names
        ]

        # Execute with concurrency limit
        results = await asyncio.gather(*tasks, return_exceptions=True)

        await compute.close()

        # Process results
        successful = [r for r in results if not isinstance(r, Exception)]
        failed = [r for r in results if isinstance(r, Exception)]

        return {"successful": successful, "failed": failed}
```

#### Pattern 3: Async Context Manager for Long-Running Operations

```python
async def start_vm_and_wait(rg_name: str, vm_name: str):
    """Start VM and wait for completion asynchronously."""
    async with DefaultAzureCredential() as credential:
        compute = ComputeManagementClient(credential, subscription_id)

        # Start operation (returns poller)
        poller = await compute.virtual_machines.begin_start(rg_name, vm_name)

        # Wait for completion (non-blocking)
        result = await poller.result()

        await compute.close()
        return result
```

### 4.4 Async Best Practices

**✅ DO:**
- Always close async credentials and clients
- Use `async with` for automatic cleanup
- Limit concurrency with `asyncio.Semaphore` for large batches
- Handle exceptions per-task with `return_exceptions=True`

**❌ DON'T:**
- Mix sync and async clients (pick one)
- Create new credentials in tight loops
- Forget to await async operations
- Use `asyncio.run()` multiple times in same process

### 4.5 Concurrency Control

For large-scale operations, control concurrency:

```python
import asyncio
from azure.identity.aio import DefaultAzureCredential
from azure.mgmt.compute.aio import ComputeManagementClient

async def get_vm_details_with_limit(vm_names: list[str], max_concurrent: int = 10):
    """Fetch VM details with concurrency limit."""
    semaphore = asyncio.Semaphore(max_concurrent)

    async def get_vm_with_semaphore(compute_client, rg_name, vm_name):
        async with semaphore:  # Limit concurrent operations
            return await compute_client.virtual_machines.get(rg_name, vm_name)

    async with DefaultAzureCredential() as credential:
        compute = ComputeManagementClient(credential, subscription_id)

        tasks = [
            get_vm_with_semaphore(compute, "my-rg", vm_name)
            for vm_name in vm_names
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        await compute.close()
        return results
```

---

## 5. Azure Management SDK Best Practices

### 5.1 Common Management SDK Patterns

#### Compute Management

```python
from azure.mgmt.compute import ComputeManagementClient
from azure.identity import DefaultAzureCredential

# Initialize once
credential = DefaultAzureCredential()
compute_client = ComputeManagementClient(credential, subscription_id)

# List all VMs (paginated)
vms = compute_client.virtual_machines.list_all()
for vm in vms:
    print(f"VM: {vm.name}, State: {vm.provisioning_state}")

# Get specific VM
vm = compute_client.virtual_machines.get(
    resource_group_name="my-rg",
    vm_name="my-vm",
    expand="instanceView"  # Include runtime status
)

# Start VM (long-running operation)
poller = compute_client.virtual_machines.begin_start("my-rg", "my-vm")
result = poller.result()  # Wait for completion

# Create VM (complex operation)
vm_parameters = {
    "location": "eastus",
    "hardware_profile": {"vm_size": "Standard_D2s_v3"},
    "storage_profile": {
        "image_reference": {
            "publisher": "Canonical",
            "offer": "UbuntuServer",
            "sku": "18.04-LTS",
            "version": "latest"
        }
    },
    "os_profile": {
        "computer_name": "myvm",
        "admin_username": "azureuser",
        "admin_password": "P@ssw0rd123!"
    },
    "network_profile": {
        "network_interfaces": [{"id": nic_id}]
    }
}

poller = compute_client.virtual_machines.begin_create_or_update(
    resource_group_name="my-rg",
    vm_name="my-new-vm",
    parameters=vm_parameters
)
vm = poller.result()  # Wait for VM creation
```

#### Network Management

```python
from azure.mgmt.network import NetworkManagementClient

network_client = NetworkManagementClient(credential, subscription_id)

# List virtual networks
vnets = network_client.virtual_networks.list_all()

# Get network interface details
nic = network_client.network_interfaces.get(
    resource_group_name="my-rg",
    network_interface_name="my-nic"
)

# Get public IP
public_ip = network_client.public_ip_addresses.get(
    resource_group_name="my-rg",
    public_ip_address_name="my-ip"
)
print(f"Public IP: {public_ip.ip_address}")

# List network security groups
nsgs = network_client.network_security_groups.list_all()
```

#### Storage Management

```python
from azure.mgmt.storage import StorageManagementClient

storage_client = StorageManagementClient(credential, subscription_id)

# List storage accounts
accounts = storage_client.storage_accounts.list()

# Get storage account keys
keys = storage_client.storage_accounts.list_keys(
    resource_group_name="my-rg",
    account_name="mystorageaccount"
)

# Create storage account
storage_params = {
    "sku": {"name": "Standard_LRS"},
    "kind": "StorageV2",
    "location": "eastus",
    "encryption": {
        "services": {
            "blob": {"enabled": True},
            "file": {"enabled": True}
        },
        "key_source": "Microsoft.Storage"
    }
}

poller = storage_client.storage_accounts.begin_create(
    resource_group_name="my-rg",
    account_name="mynewstorage",
    parameters=storage_params
)
account = poller.result()
```

### 5.2 Long-Running Operations (LRO)

Management operations often return pollers for long-running operations:

```python
# Method names with 'begin_' prefix return LROPoller
poller = compute_client.virtual_machines.begin_create_or_update(...)

# Wait for completion (blocking)
result = poller.result()

# Check status without blocking
status = poller.status()  # "InProgress", "Succeeded", "Failed"

# Check if done
if poller.done():
    result = poller.result()

# Custom polling interval
result = poller.result(timeout=300)  # Wait max 5 minutes

# Async LRO pattern
poller = await compute_client.virtual_machines.begin_start(...)
result = await poller.result()  # Non-blocking in async context
```

### 5.3 Error Handling

```python
from azure.core.exceptions import (
    ResourceNotFoundError,
    HttpResponseError,
    ClientAuthenticationError
)

try:
    vm = compute_client.virtual_machines.get("my-rg", "my-vm")
except ResourceNotFoundError:
    print("VM not found")
except ClientAuthenticationError as e:
    print(f"Authentication failed: {e.message}")
except HttpResponseError as e:
    print(f"Azure API error: {e.status_code} - {e.message}")
    print(f"Error code: {e.error.code}")
```

### 5.4 Pagination Handling

Many list operations return paged results:

```python
# Iterate through all pages automatically
vms = compute_client.virtual_machines.list_all()
for vm in vms:
    print(vm.name)

# Manual pagination (advanced)
vms = compute_client.virtual_machines.list_all()
page_iterator = vms.by_page()

for page in page_iterator:
    for vm in page:
        print(vm.name)
    # Process batch
```

---

## 6. Performance Optimization Tips

### 6.1 Batching and Parallelization

**Parallel Resource Queries:**
```python
import concurrent.futures
from azure.identity import DefaultAzureCredential
from azure.mgmt.compute import ComputeManagementClient

def get_vm_status(compute_client, rg_name, vm_name):
    """Get VM status (called in parallel)."""
    vm = compute_client.virtual_machines.instance_view(rg_name, vm_name)
    return vm.statuses

credential = DefaultAzureCredential()
compute_client = ComputeManagementClient(credential, subscription_id)

vm_list = [("rg1", "vm1"), ("rg2", "vm2"), ("rg3", "vm3")]

# Execute in parallel threads
with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
    futures = [
        executor.submit(get_vm_status, compute_client, rg, vm)
        for rg, vm in vm_list
    ]
    results = [f.result() for f in concurrent.futures.as_completed(futures)]
```

### 6.2 Caching Strategy

Implement caching for frequently accessed, infrequently changing data:

```python
from functools import lru_cache
from datetime import datetime, timedelta

class CachedAzureClient:
    def __init__(self, subscription_id):
        self.credential = DefaultAzureCredential()
        self.compute = ComputeManagementClient(self.credential, subscription_id)
        self._cache = {}
        self._cache_ttl = timedelta(minutes=5)

    def get_vm_with_cache(self, rg_name, vm_name):
        """Get VM with 5-minute cache."""
        cache_key = f"{rg_name}/{vm_name}"

        if cache_key in self._cache:
            cached_time, cached_vm = self._cache[cache_key]
            if datetime.now() - cached_time < self._cache_ttl:
                return cached_vm

        # Cache miss or expired
        vm = self.compute.virtual_machines.get(rg_name, vm_name)
        self._cache[cache_key] = (datetime.now(), vm)
        return vm
```

### 6.3 Request Optimization

**Use Projections and Filters:**
```python
# Get only necessary fields
vm = compute_client.virtual_machines.get(
    resource_group_name="my-rg",
    vm_name="my-vm",
    expand="instanceView"  # Only get instance view, not full details
)

# Filter at API level
from azure.mgmt.compute.models import ResourceSkuRestrictionsReasonCode

# Get only specific SKUs
skus = compute_client.resource_skus.list(
    filter="location eq 'eastus'"
)
```

### 6.4 Connection Reuse

Ensure clients and sessions are reused:

```python
# ❌ BAD: Creates new client each time
def get_vm_bad(rg_name, vm_name):
    client = ComputeManagementClient(DefaultAzureCredential(), subscription_id)
    return client.virtual_machines.get(rg_name, vm_name)

# ✅ GOOD: Reuses client
class VMService:
    def __init__(self, subscription_id):
        self.client = ComputeManagementClient(
            DefaultAzureCredential(),
            subscription_id
        )

    def get_vm(self, rg_name, vm_name):
        return self.client.virtual_machines.get(rg_name, vm_name)
```

### 6.5 Retry Configuration

Optimize retry behavior for your use case:

```python
# Fast-fail for user-facing operations
compute_client = ComputeManagementClient(
    credential=credential,
    subscription_id=subscription_id,
    retry_total=2,           # Only retry twice
    retry_mode='exponential',
    connection_timeout=15,   # Fail fast on connection issues
    read_timeout=30
)

# Resilient for background jobs
compute_client = ComputeManagementClient(
    credential=credential,
    subscription_id=subscription_id,
    retry_total=5,           # More retries
    retry_mode='exponential',
    connection_timeout=30,
    read_timeout=300         # Allow longer operations
)
```

---

## 7. Common Pitfalls and How to Avoid Them

### 7.1 Pitfall: Creating Clients Per Request

**❌ Problem:**
```python
# This creates new credential and client for every request!
@app.get("/vms")
def list_vms():
    credential = DefaultAzureCredential()  # Expensive!
    client = ComputeManagementClient(credential, subscription_id)  # Expensive!
    return list(client.virtual_machines.list_all())
```

**✅ Solution:**
```python
# Create once at startup
credential = DefaultAzureCredential()
compute_client = ComputeManagementClient(credential, subscription_id)

@app.get("/vms")
def list_vms():
    return list(compute_client.virtual_machines.list_all())
```

### 7.2 Pitfall: Not Handling Rate Limits

**❌ Problem:**
```python
# Rapid-fire requests without backoff
for i in range(1000):
    vm = compute_client.virtual_machines.get("my-rg", f"vm-{i}")
```

**✅ Solution:**
```python
import time
from azure.core.exceptions import HttpResponseError

def get_vm_with_backoff(client, rg_name, vm_name, max_retries=3):
    """Get VM with custom retry logic for rate limiting."""
    for attempt in range(max_retries):
        try:
            return client.virtual_machines.get(rg_name, vm_name)
        except HttpResponseError as e:
            if e.status_code == 429:  # Too Many Requests
                retry_after = int(e.response.headers.get('Retry-After', 5))
                time.sleep(retry_after)
            else:
                raise
    raise Exception("Max retries exceeded")
```

### 7.3 Pitfall: Ignoring Async Context Cleanup

**❌ Problem:**
```python
async def get_vms():
    credential = DefaultAzureCredential()
    client = ComputeManagementClient(credential, subscription_id)
    vms = await client.virtual_machines.list_all()
    return [vm async for vm in vms]
    # Credential and client never closed!
```

**✅ Solution:**
```python
async def get_vms():
    async with DefaultAzureCredential() as credential:
        client = ComputeManagementClient(credential, subscription_id)
        vms = await client.virtual_machines.list_all()
        result = [vm async for vm in vms]
        await client.close()
    return result
```

### 7.4 Pitfall: Using Default Timeouts

**❌ Problem:**
```python
# Default timeout is 604800 seconds (7 days!) - way too long
client = ComputeManagementClient(credential, subscription_id)
```

**✅ Solution:**
```python
# Set reasonable timeouts
client = ComputeManagementClient(
    credential=credential,
    subscription_id=subscription_id,
    connection_timeout=30,  # 30 seconds to connect
    read_timeout=120        # 2 minutes to complete
)
```

### 7.5 Pitfall: Not Using Managed Identity in Azure

**❌ Problem:**
```python
# Using secrets in Azure-hosted apps
credential = ClientSecretCredential(
    tenant_id=os.getenv("AZURE_TENANT_ID"),
    client_id=os.getenv("AZURE_CLIENT_ID"),
    client_secret=os.getenv("AZURE_CLIENT_SECRET")  # Secret management overhead
)
```

**✅ Solution:**
```python
# Use managed identity - no secrets needed!
from azure.identity import ManagedIdentityCredential

# For Azure VMs, App Service, AKS, etc.
credential = ManagedIdentityCredential()
```

### 7.6 Pitfall: Synchronous Code in Async Context

**❌ Problem:**
```python
# Mixing sync client in async function
async def get_vms():
    # This blocks the event loop!
    client = ComputeManagementClient(credential, subscription_id)
    vms = client.virtual_machines.list_all()  # Blocking call
    return list(vms)
```

**✅ Solution:**
```python
# Use async client
from azure.mgmt.compute.aio import ComputeManagementClient

async def get_vms():
    async with ComputeManagementClient(credential, subscription_id) as client:
        vms = client.virtual_machines.list_all()
        return [vm async for vm in vms]
```

### 7.7 Pitfall: Not Handling Pagination Correctly

**❌ Problem:**
```python
# Only gets first page!
vms_page = compute_client.virtual_machines.list_all()
print(f"Found {len(list(vms_page))} VMs")  # Only first page
```

**✅ Solution:**
```python
# Iterate through all pages
vms = compute_client.virtual_machines.list_all()
all_vms = list(vms)  # Automatically handles pagination
print(f"Found {len(all_vms)} VMs")
```

---

## 8. Production Deployment Checklist

### 8.1 Pre-Deployment Checklist

- [ ] **Credential Management**
  - [ ] Use DefaultAzureCredential or ManagedIdentityCredential
  - [ ] Never hardcode secrets in code
  - [ ] Enable persistent token caching for long-running services
  - [ ] Configure proper RBAC permissions for managed identities

- [ ] **Client Configuration**
  - [ ] Create clients once at startup (singleton pattern)
  - [ ] Set appropriate timeouts (connection_timeout, read_timeout)
  - [ ] Configure retry policies (retry_total, retry_mode)
  - [ ] Enable connection pooling with proper pool sizes

- [ ] **Performance**
  - [ ] Use async clients for high-throughput scenarios
  - [ ] Implement caching for frequently accessed data
  - [ ] Use parallel execution for batch operations
  - [ ] Set up proper connection pool limits

- [ ] **Monitoring**
  - [ ] Enable logging (logging_enable=True during development)
  - [ ] Configure structured logging for production
  - [ ] Set up application insights or equivalent
  - [ ] Monitor authentication failures and rate limits

- [ ] **Error Handling**
  - [ ] Handle ResourceNotFoundError appropriately
  - [ ] Implement retry logic for transient failures
  - [ ] Log exceptions with proper context
  - [ ] Set up alerting for authentication failures

- [ ] **Security**
  - [ ] Enable SSL verification (connection_verify=True)
  - [ ] Use encrypted token cache
  - [ ] Rotate managed identity/service principal regularly
  - [ ] Audit credential access

### 8.2 Configuration Template

Production-ready configuration:

```python
import os
from azure.identity import DefaultAzureCredential, TokenCachePersistenceOptions
from azure.mgmt.compute import ComputeManagementClient
from azure.mgmt.network import NetworkManagementClient
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class ProductionAzureClient:
    """Production-ready Azure SDK client manager."""

    def __init__(self):
        self.subscription_id = os.getenv("AZURE_SUBSCRIPTION_ID")

        # Configure persistent token cache
        cache_options = TokenCachePersistenceOptions(
            allow_unencrypted_storage=False
        )

        # Initialize credential (prefer managed identity in Azure)
        self._credential = DefaultAzureCredential(
            cache_persistence_options=cache_options,
            exclude_interactive_browser_credential=True,  # No interactive in production
            logging_enable=False  # Disable in production (enable for debugging)
        )

        # Client cache
        self._clients = {}

        logger.info("Azure SDK client manager initialized")

    def get_compute_client(self) -> ComputeManagementClient:
        """Get compute management client with production config."""
        if 'compute' not in self._clients:
            self._clients['compute'] = ComputeManagementClient(
                credential=self._credential,
                subscription_id=self.subscription_id,

                # Timeouts
                connection_timeout=30,
                read_timeout=120,

                # Retry config
                retry_total=3,
                retry_mode='exponential',

                # Logging (disable in production)
                logging_enable=False
            )
            logger.info("Compute client created")
        return self._clients['compute']

    def get_network_client(self) -> NetworkManagementClient:
        """Get network management client with production config."""
        if 'network' not in self._clients:
            self._clients['network'] = NetworkManagementClient(
                credential=self._credential,
                subscription_id=self.subscription_id,
                connection_timeout=30,
                read_timeout=120,
                retry_total=3,
                retry_mode='exponential',
                logging_enable=False
            )
            logger.info("Network client created")
        return self._clients['network']

    def close(self):
        """Clean up resources."""
        if self._credential:
            self._credential.close()
        self._clients.clear()
        logger.info("Azure SDK clients closed")

# Global singleton
_azure_client: ProductionAzureClient = None

def get_azure_client() -> ProductionAzureClient:
    """Get global Azure client instance."""
    global _azure_client
    if _azure_client is None:
        _azure_client = ProductionAzureClient()
    return _azure_client
```

---

## 9. Monitoring and Observability

### 9.1 Logging Configuration

```python
import logging
from azure.identity import DefaultAzureCredential
from azure.mgmt.compute import ComputeManagementClient

# Configure Azure SDK logging
azure_logger = logging.getLogger('azure')
azure_logger.setLevel(logging.WARNING)  # Only warnings and errors

# Configure credential logging separately
identity_logger = logging.getLogger('azure.identity')
identity_logger.setLevel(logging.INFO)  # Track authentication attempts

# Create client with logging
credential = DefaultAzureCredential(
    logging_enable=True  # Enable during debugging
)

compute_client = ComputeManagementClient(
    credential=credential,
    subscription_id=subscription_id,
    logging_enable=True  # Enable request/response logging
)
```

### 9.2 Metrics to Track

**Key Performance Indicators:**
- Credential acquisition time
- API request latency (p50, p95, p99)
- Error rate by error type
- Retry count per operation
- Connection pool utilization
- Token refresh frequency

**Sample Metrics Collection:**
```python
import time
from contextlib import contextmanager

@contextmanager
def track_operation(operation_name):
    """Context manager to track operation metrics."""
    start_time = time.time()
    try:
        yield
        duration = time.time() - start_time
        logger.info(f"{operation_name} succeeded in {duration:.2f}s")
        # Send to metrics system (Prometheus, Application Insights, etc.)
    except Exception as e:
        duration = time.time() - start_time
        logger.error(f"{operation_name} failed after {duration:.2f}s: {e}")
        # Send failure metric
        raise

# Usage
with track_operation("list_vms"):
    vms = list(compute_client.virtual_machines.list_all())
```

---

## 10. Summary and Quick Reference

### 10.1 Key Takeaways

1. **Create Once, Reuse Always**: Credentials and clients should be singletons
2. **Async for Scale**: Use async clients for high-throughput applications
3. **Configure Timeouts**: Default 7-day timeout is too long - set to 30-120s
4. **Connection Pooling**: Configure HTTPAdapter pool sizes for sync clients
5. **Managed Identity**: Use in Azure - no secret management needed
6. **Proper Cleanup**: Always close async credentials and clients
7. **Cache Tokens**: Enable persistent cache for production services
8. **Handle Retries**: Configure retry policies appropriate for your workload

### 10.2 Quick Reference Code Snippets

**Basic Singleton Pattern:**
```python
from azure.identity import DefaultAzureCredential
from azure.mgmt.compute import ComputeManagementClient

# Create once at startup
credential = DefaultAzureCredential()
compute_client = ComputeManagementClient(
    credential=credential,
    subscription_id=os.getenv("AZURE_SUBSCRIPTION_ID"),
    connection_timeout=30,
    read_timeout=120,
    retry_total=3
)
```

**Async Pattern:**
```python
from azure.identity.aio import DefaultAzureCredential
from azure.mgmt.compute.aio import ComputeManagementClient

async with DefaultAzureCredential() as credential:
    client = ComputeManagementClient(credential, subscription_id)
    vms = await client.virtual_machines.list_all()
    result = [vm async for vm in vms]
    await client.close()
```

**Connection Pooling:**
```python
import requests
from azure.core.pipeline.transport import RequestsTransport

session = requests.Session()
adapter = requests.adapters.HTTPAdapter(
    pool_connections=10,
    pool_maxsize=20
)
session.mount('https://', adapter)

transport = RequestsTransport(session=session)
client = ComputeManagementClient(
    credential=credential,
    subscription_id=subscription_id,
    transport=transport
)
```

---

## Sources

- [Azure SDK for Python Overview](https://learn.microsoft.com/en-us/azure/developer/python/sdk/azure-sdk-overview)
- [Azure Identity Library Documentation](https://learn.microsoft.com/en-us/python/api/overview/azure/identity-readme)
- [Azure Core Library README](https://github.com/Azure/azure-sdk-for-python/blob/main/sdk/core/azure-core/README.md)
- [Azure SDK Library Usage Patterns](https://learn.microsoft.com/en-us/azure/developer/python/sdk/azure-sdk-library-usage-patterns)
- [Azure Compute Management SDK](https://github.com/Azure/azure-sdk-for-python/tree/main/sdk/compute/azure-mgmt-compute)
- [Azure SDK Design Guidelines](https://azure.github.io/azure-sdk/python_design.html)

---

**Document Version:** 1.0
**Last Updated:** 2026-02-27
**Maintained By:** GCC Demo Platform Team
