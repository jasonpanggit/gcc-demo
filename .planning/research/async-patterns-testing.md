# Python Async Patterns and Testing Strategies for Orchestrators

**Research Document**
**Date:** 2026-02-27
**Focus:** Fire-and-forget patterns, task lifecycle, pytest-asyncio, mocking, and fixtures

---

## Table of Contents

1. [Fire-and-Forget Task Patterns](#1-fire-and-forget-task-patterns)
2. [Task Lifecycle Management](#2-task-lifecycle-management)
3. [Async Testing with pytest-asyncio](#3-async-testing-with-pytest-asyncio)
4. [Mocking Async Functions and Azure SDK Clients](#4-mocking-async-functions-and-azure-sdk-clients)
5. [Test Fixture Design for Complex Async Systems](#5-test-fixture-design-for-complex-async-systems)
6. [Production Patterns from Codebase](#6-production-patterns-from-codebase)
7. [Recommendations](#7-recommendations)

---

## 1. Fire-and-Forget Task Patterns

### 1.1 Basic `asyncio.create_task`

**Purpose:** Schedule a coroutine to run concurrently without blocking the caller.

```python
import asyncio

async def background_operation():
    await asyncio.sleep(5)
    print("Background task completed")

async def main():
    # Schedule task - returns immediately
    task = asyncio.create_task(background_operation())
    print("Task scheduled, continuing...")
    # Do other work...
```

**Key Points:**
- `create_task()` requires a running event loop (raises `RuntimeError` if none)
- Returns a `Task` object immediately
- Task begins execution "soon" (scheduled on next event loop iteration)
- Optional parameters:
  - `name`: Descriptive name for debugging (Python 3.8+)
  - `context`: contextvars.Context to run the coro in (Python 3.11+)
  - `eager_start`: Run synchronously if completes without blocking (Python 3.14+)

### 1.2 The Garbage Collection Problem

**Critical Warning:** The event loop holds only **weak references** to tasks. An unreferenced task may be garbage-collected mid-execution.

```python
# ❌ DANGEROUS - Task may be garbage collected
async def bad_example():
    asyncio.create_task(background_work())  # No reference kept!
    # Task might get GC'd before completing

# ✅ CORRECT - Keep strong reference
async def good_example():
    task = asyncio.create_task(background_work())
    await task  # Or store in a collection
```

### 1.3 Background Task Set Pattern

**Recommended pattern for fire-and-forget tasks:**

```python
import asyncio
from typing import Set

# Module-level or class-level task set
background_tasks: Set[asyncio.Task] = set()

def spawn_background(coro):
    """Schedule a background task and track it."""
    task = asyncio.create_task(coro)
    background_tasks.add(task)

    # Remove from set when done (prevents memory leak)
    task.add_done_callback(background_tasks.discard)

    return task

# Usage
async def main():
    spawn_background(some_async_operation())
    spawn_background(another_async_operation())
    # Tasks run in background, automatically cleaned up
```

**Pattern Benefits:**
- Prevents garbage collection
- Automatic cleanup via `add_done_callback`
- No memory leak (tasks removed when complete)
- Can track/cancel all background tasks if needed

### 1.4 FastAPI Background Tasks

For FastAPI applications, use `BackgroundTasks`:

```python
from fastapi import BackgroundTasks, FastAPI

app = FastAPI()

async def write_log(message: str):
    with open("log.txt", "a") as f:
        f.write(message)

@app.post("/send-notification/")
async def send_notification(background_tasks: BackgroundTasks):
    # Task runs after response is sent
    background_tasks.add_task(write_log, "Notification sent")
    return {"message": "Notification sent in the background"}
```

**FastAPI Pattern:**
- Tasks run after response is returned to client
- Integrated with request lifecycle
- No manual task tracking needed
- Best for post-response operations (logging, notifications, cleanup)

### 1.5 Production Example from Codebase

From `app/agentic/eol/agents/mcp_orchestrator.py`:

```python
# Build semantic index in a fire-and-forget background task so it never
# blocks the calling request (embedding 140+ tools can take seconds).
if self._tool_embedder and self._tool_definitions:
    asyncio.create_task(self._build_embedding_index_bg())

async def _build_embedding_index_bg(self) -> None:
    """Background task: build ToolEmbedder semantic index without blocking callers."""
    try:
        if self._tool_embedder and self._tool_definitions:
            await self._tool_embedder.build_index(self._tool_definitions)
            logger.info("✅ Background embedding index built")
    except Exception as exc:
        logger.warning(f"⚠️ Background embedding index build failed: {exc}")
```

**Analysis:**
- ⚠️ No reference kept - relies on task completing before GC
- ✅ Has exception handling
- ✅ Non-critical operation (can fail gracefully)
- **Recommendation:** Consider storing in a task set if reliability is critical

---

## 2. Task Lifecycle Management

### 2.1 Task States and Methods

**Task Methods:**
- `done()` → bool: True if task completed (success or exception)
- `result()` → Any: Returns result or re-raises exception (blocks if not done)
- `exception()` → Optional[Exception]: Returns exception or None
- `cancel(msg=None)` → bool: Request cancellation, returns True if successful
- `cancelled()` → bool: True if task was cancelled
- `cancelling()` → int: Number of pending cancellation requests
- `uncancel()` → int: Decrement cancellation count

### 2.2 Cancellation Patterns

**Basic Cancellation:**

```python
task = asyncio.create_task(long_running_task())
await asyncio.sleep(1)

# Request cancellation
task.cancel()

try:
    await task
except asyncio.CancelledError:
    print("Task was cancelled")
```

**Cancellation with Cleanup:**

```python
async def worker():
    try:
        await long_running_operation()
    except asyncio.CancelledError:
        # Cleanup before propagating
        await cleanup_resources()
        raise  # MUST re-raise
    finally:
        # Always runs
        release_connections()
```

**Critical Rules:**
1. **Always re-raise `CancelledError`** (or call `uncancel()` if intentionally suppressing)
2. `CancelledError` inherits from `BaseException`, not `Exception`
3. Use `try/finally` for guaranteed cleanup
4. Swallowing `CancelledError` breaks structured concurrency

### 2.3 Timeouts

**Modern Approach (Python 3.11+):**

```python
async def main():
    try:
        async with asyncio.timeout(10):
            await long_running_task()
    except TimeoutError:
        print("Task timed out")
```

**Legacy Approach:**

```python
try:
    result = await asyncio.wait_for(some_task(), timeout=5.0)
except asyncio.TimeoutError:
    print("Task timed out")
```

**Timeout Without Cancellation (using shield):**

```python
task = asyncio.create_task(critical_task())
try:
    result = await asyncio.wait_for(asyncio.shield(task), timeout=5.0)
except TimeoutError:
    # Caller timed out, but task keeps running
    print("Timeout, but task continues")
```

### 2.4 Structured Concurrency with TaskGroup

**Modern pattern (Python 3.11+):**

```python
async def main():
    async with asyncio.TaskGroup() as tg:
        task1 = tg.create_task(fetch_data_1())
        task2 = tg.create_task(fetch_data_2())
        task3 = tg.create_task(fetch_data_3())

    # All tasks complete before exiting context
    # If any task raises, others are cancelled
    # Exceptions aggregated into ExceptionGroup

    print(task1.result(), task2.result(), task3.result())
```

**Benefits over `gather()`:**
- Automatic cancellation of remaining tasks on first error
- Exception aggregation (ExceptionGroup)
- Structured lifetime (RAII-style)
- Safer than manual task management

**When to Use:**
- ✅ Related tasks with shared lifetime
- ✅ Want automatic cancellation on error
- ✅ Python 3.11+
- ❌ Long-lived background tasks
- ❌ Need fine-grained error control

### 2.5 Graceful Shutdown Pattern

```python
import asyncio
import signal
from typing import Set

background_tasks: Set[asyncio.Task] = set()

async def graceful_shutdown():
    """Cancel all background tasks gracefully."""
    print(f"Shutting down {len(background_tasks)} tasks...")

    for task in background_tasks:
        task.cancel()

    # Wait for all cancellations to complete
    await asyncio.gather(*background_tasks, return_exceptions=True)
    print("All tasks cancelled")

async def main():
    # Set up signal handlers
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(
            sig,
            lambda: asyncio.create_task(graceful_shutdown())
        )

    # Run application
    await run_app()
```

---

## 3. Async Testing with pytest-asyncio

### 3.1 Installation and Configuration

```bash
pip install pytest-asyncio
```

**pytest.ini or pyproject.toml:**

```ini
[pytest]
asyncio_mode = auto
```

Or mark tests individually:

```python
@pytest.mark.asyncio
async def test_my_async_function():
    result = await my_async_function()
    assert result == expected
```

### 3.2 Basic Async Test Patterns

**Simple async test:**

```python
import pytest

@pytest.mark.asyncio
async def test_async_operation():
    result = await fetch_data()
    assert result is not None
```

**Testing exceptions:**

```python
@pytest.mark.asyncio
async def test_async_exception():
    with pytest.raises(ValueError):
        await function_that_raises()
```

**Testing timeouts:**

```python
@pytest.mark.asyncio
async def test_with_timeout():
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(slow_function(), timeout=1.0)
```

### 3.3 Event Loop Management

**pytest-asyncio automatically manages event loops:**

```python
# No manual loop creation needed
@pytest.mark.asyncio
async def test_example():
    # Event loop already running
    await some_async_function()
```

**Custom event loop fixture (if needed):**

```python
import pytest
import asyncio

@pytest.fixture
def event_loop():
    """Create a new event loop for each test."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()
```

### 3.4 FastAPI Testing with TestClient

**Synchronous TestClient (blocks on async operations):**

```python
from fastapi.testclient import TestClient
from main import app

def test_endpoint():
    with TestClient(app) as client:
        response = client.get("/api/endpoint")
        assert response.status_code == 200
```

**Async TestClient (for true async testing):**

```python
import pytest
from httpx import AsyncClient
from main import app

@pytest.mark.asyncio
async def test_async_endpoint():
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/api/endpoint")
        assert response.status_code == 200
```

### 3.5 Testing Lifespan Events

**Pattern from FastAPI docs:**

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.testclient import TestClient

items = {}

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    items["foo"] = {"name": "Fighters"}
    yield
    # Shutdown
    items.clear()

app = FastAPI(lifespan=lifespan)

def test_lifespan():
    assert items == {}  # Before context

    with TestClient(app) as client:
        # Lifespan startup ran
        assert items == {"foo": {"name": "Fighters"}}
        response = client.get("/items/foo")
        assert response.status_code == 200

    # Lifespan cleanup ran
    assert items == {}
```

### 3.6 Codebase Pattern: Unit Tests with Markers

From `test_sre_gateway.py`:

```python
@pytest.fixture
def gateway() -> SREGateway:
    """Gateway with LLM fallback disabled for pure keyword tests."""
    gw = SREGateway()
    gw._llm_fallback_enabled = False
    return gw

@pytest.mark.unit
@pytest.mark.parametrize("expected_domain, query", DOMAIN_QUERIES)
def test_canonical_query_routes_to_correct_domain(self, expected_domain, query, gateway):
    """Each canonical query must classify to the expected domain."""
    domain, score = gateway.classify_sync(query)
    assert domain == expected_domain
```

**Key Patterns:**
- `@pytest.mark.unit` for tests without external dependencies
- `@pytest.mark.asyncio` for async tests
- `@pytest.mark.remote` for integration tests
- Parametrize for data-driven tests

---

## 4. Mocking Async Functions and Azure SDK Clients

### 4.1 AsyncMock Basics

**From unittest.mock (Python 3.8+):**

```python
from unittest.mock import AsyncMock, MagicMock, patch

@pytest.mark.asyncio
async def test_with_async_mock():
    mock_client = AsyncMock()
    mock_client.get_data.return_value = {"status": "ok"}

    result = await mock_client.get_data()
    assert result["status"] == "ok"

    # Verify call
    mock_client.get_data.assert_called_once()
```

### 4.2 Mocking Azure SDK Clients

**Pattern 1: Mock at client level:**

```python
@pytest.mark.asyncio
async def test_azure_operation():
    mock_cosmos_client = MagicMock()
    mock_container = AsyncMock()
    mock_container.read_item.return_value = {"id": "123", "data": "test"}

    mock_cosmos_client.get_database_client.return_value.get_container_client.return_value = mock_container

    with patch('app.utils.cosmos_cache.CosmosClient', return_value=mock_cosmos_client):
        result = await fetch_from_cosmos("123")
        assert result["data"] == "test"
```

**Pattern 2: Mock specific methods:**

```python
@pytest.mark.asyncio
async def test_with_method_patch():
    with patch('app.utils.azure_client.get_resource_client') as mock_get_client:
        mock_client = AsyncMock()
        mock_client.get.return_value = {"status": "healthy"}
        mock_get_client.return_value = mock_client

        result = await check_resource_health()
        assert result["status"] == "healthy"
```

### 4.3 Mocking Async Context Managers

```python
from unittest.mock import AsyncMock, MagicMock
import pytest

@pytest.mark.asyncio
async def test_async_context_manager():
    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.query.return_value = [{"id": 1}]

    async with mock_client as client:
        result = await client.query()
        assert len(result) == 1
```

### 4.4 Mocking Multiple Azure Service Calls

```python
@pytest.mark.asyncio
async def test_multi_service_orchestration():
    # Mock Azure OpenAI
    mock_openai = AsyncMock()
    mock_openai.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content="AI response"))]
    )

    # Mock Cosmos DB
    mock_cosmos = AsyncMock()
    mock_cosmos.read_item.return_value = {"cached": "data"}

    # Mock Resource Graph
    mock_graph = AsyncMock()
    mock_graph.resources.return_value = [{"type": "Microsoft.Compute/virtualMachines"}]

    with patch.multiple(
        'app.agents.orchestrator',
        get_openai_client=MagicMock(return_value=mock_openai),
        get_cosmos_client=MagicMock(return_value=mock_cosmos),
        get_graph_client=MagicMock(return_value=mock_graph),
    ):
        result = await orchestrator.handle_request("query")
        assert "AI response" in result
```

### 4.5 Codebase Pattern: Mocking Agent Dependencies

From `test_security_compliance_agent.py`:

```python
@pytest.mark.asyncio
async def test_network_audit_action_with_mock():
    """Test network compliance audit action with mocked Azure CLI responses."""
    agent = SecurityComplianceAgent()

    # Mock dependencies
    agent.registry = MagicMock()
    agent.context_store = AsyncMock()
    agent.context_store.create_workflow_context = AsyncMock()

    # Mock tool proxy agent
    agent.tool_proxy_agent = AsyncMock()

    # Mock Azure CLI response
    vnet_response = {
        "status": "success",
        "stdout": json.dumps([{
            "name": "test-vnet",
            "subnets": [{"name": "subnet1", "networkSecurityGroup": None}]
        }])
    }

    async def mock_handle_request(request):
        command = request.get("parameters", {}).get("command", "")
        if "vnet list" in command:
            return vnet_response
        # ... more conditions

    agent.tool_proxy_agent.handle_request = mock_handle_request

    result = await agent._audit_network_compliance({})
    assert result["violations_found"] > 0
```

### 4.6 Advanced Pattern: Side Effects

```python
@pytest.mark.asyncio
async def test_with_side_effects():
    mock_client = AsyncMock()

    # First call returns one thing, second another
    mock_client.fetch.side_effect = [
        {"status": "pending"},
        {"status": "complete"},
    ]

    result1 = await mock_client.fetch()
    result2 = await mock_client.fetch()

    assert result1["status"] == "pending"
    assert result2["status"] == "complete"
```

### 4.7 Mocking Exceptions

```python
@pytest.mark.asyncio
async def test_error_handling():
    mock_client = AsyncMock()
    mock_client.get_resource.side_effect = Exception("Resource not found")

    with pytest.raises(Exception, match="Resource not found"):
        await mock_client.get_resource()
```

---

## 5. Test Fixture Design for Complex Async Systems

### 5.1 Basic Fixture Patterns

**Simple fixture:**

```python
@pytest.fixture
def gateway() -> SREGateway:
    """Gateway with default configuration."""
    return SREGateway()
```

**Fixture with setup/teardown:**

```python
@pytest.fixture
async def database():
    """Database fixture with cleanup."""
    db = await create_test_database()
    yield db
    await db.cleanup()
```

### 5.2 Fixture Scopes

```python
# Function scope (default) - new instance per test
@pytest.fixture
def per_test_client():
    return create_client()

# Module scope - shared across all tests in module
@pytest.fixture(scope="module")
def shared_client():
    client = create_expensive_client()
    yield client
    client.close()

# Session scope - shared across entire test session
@pytest.fixture(scope="session")
def global_config():
    return load_config()
```

### 5.3 Async Fixtures

```python
@pytest.fixture
async def async_client():
    """Async fixture for httpx client."""
    async with httpx.AsyncClient() as client:
        yield client

@pytest.mark.asyncio
async def test_with_async_fixture(async_client):
    response = await async_client.get("https://api.example.com")
    assert response.status_code == 200
```

### 5.4 Fixture Composition

```python
@pytest.fixture
def mock_cosmos():
    """Mock Cosmos DB client."""
    mock = AsyncMock()
    mock.read_item.return_value = {"id": "123"}
    return mock

@pytest.fixture
def mock_openai():
    """Mock Azure OpenAI client."""
    mock = AsyncMock()
    mock.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content="response"))]
    )
    return mock

@pytest.fixture
def orchestrator(mock_cosmos, mock_openai):
    """Orchestrator with all dependencies mocked."""
    return Orchestrator(
        cosmos_client=mock_cosmos,
        openai_client=mock_openai
    )

@pytest.mark.asyncio
async def test_orchestrator(orchestrator):
    result = await orchestrator.handle_request("test query")
    assert result is not None
```

### 5.5 Parametrized Fixtures

```python
@pytest.fixture(params=[
    {"llm_enabled": True, "cache_enabled": True},
    {"llm_enabled": False, "cache_enabled": True},
    {"llm_enabled": True, "cache_enabled": False},
])
def gateway_configs(request):
    """Test multiple gateway configurations."""
    return SREGateway(**request.param)

def test_all_configs(gateway_configs):
    """Test runs 3 times with different configs."""
    result = gateway_configs.classify_sync("test query")
    assert result is not None
```

### 5.6 Codebase Pattern: Multiple Configuration Fixtures

From `test_sre_gateway.py`:

```python
@pytest.fixture
def gateway() -> SREGateway:
    """Gateway with LLM fallback disabled for pure keyword tests."""
    gw = SREGateway()
    gw._llm_fallback_enabled = False
    return gw

@pytest.fixture
def gateway_with_llm() -> SREGateway:
    """Gateway with LLM fallback enabled for fallback tests."""
    gw = SREGateway()
    gw._llm_fallback_enabled = True
    return gw

# Tests choose appropriate fixture
class TestKeywordClassification:
    def test_keyword_only(self, gateway):
        # Uses gateway without LLM
        pass

class TestLLMFallback:
    @pytest.mark.asyncio
    async def test_llm_classification(self, gateway_with_llm):
        # Uses gateway with LLM
        pass
```

### 5.7 Factory Fixtures

```python
@pytest.fixture
def create_agent():
    """Factory fixture for creating agents with custom config."""
    agents = []

    def _create_agent(agent_type: str, **kwargs):
        agent = Agent(agent_type=agent_type, **kwargs)
        agents.append(agent)
        return agent

    yield _create_agent

    # Cleanup all created agents
    for agent in agents:
        agent.cleanup()

def test_multiple_agents(create_agent):
    agent1 = create_agent("sre", timeout=30)
    agent2 = create_agent("eol", timeout=60)
    # Both cleaned up automatically
```

### 5.8 Shared State Fixtures

```python
@pytest.fixture(scope="module")
def shared_cache():
    """Module-level cache shared across tests."""
    cache = {}
    return cache

def test_write_cache(shared_cache):
    shared_cache["key"] = "value"

def test_read_cache(shared_cache):
    # Can read value from previous test
    assert shared_cache.get("key") == "value"
```

### 5.9 Monkeypatch Fixture

```python
def test_with_monkeypatch(monkeypatch):
    """pytest built-in fixture for patching."""

    # Patch environment variable
    monkeypatch.setenv("API_KEY", "test-key")

    # Patch attribute
    monkeypatch.setattr(
        "app.config.TIMEOUT",
        5.0
    )

    # Patch function
    monkeypatch.setattr(
        "app.utils.get_client",
        lambda: MockClient()
    )

    # Test with patched values
    result = function_using_env_and_config()
    assert result is not None
```

---

## 6. Production Patterns from Codebase

### 6.1 Fire-and-Forget in MCP Orchestrator

**Location:** `app/agentic/eol/agents/mcp_orchestrator.py`

```python
# Build semantic index in a fire-and-forget background task
if self._tool_embedder and self._tool_definitions:
    asyncio.create_task(self._build_embedding_index_bg())

async def _build_embedding_index_bg(self) -> None:
    """Background task: build ToolEmbedder semantic index without blocking callers."""
    try:
        if self._tool_embedder and self._tool_definitions:
            await self._tool_embedder.build_index(self._tool_definitions)
            logger.info("✅ Background embedding index built")
    except Exception as exc:
        logger.warning(f"⚠️ Background embedding index build failed: {exc}")
```

**Analysis:**
- ✅ Exception handling prevents uncaught exceptions
- ✅ Logging for observability
- ⚠️ No task reference kept (relies on fast completion)
- **Improvement:** Consider task set pattern for reliability

### 6.2 Test Markers and Organization

**Location:** `app/agentic/eol/tests/`

```python
# Marker strategy
@pytest.mark.unit          # No external dependencies
@pytest.mark.asyncio       # Async test
@pytest.mark.remote        # Requires live service
@pytest.mark.parametrize   # Data-driven testing

# Example from test_sre_gateway.py
@pytest.mark.unit
@pytest.mark.parametrize("expected_domain, query", DOMAIN_QUERIES)
def test_canonical_query_routes_to_correct_domain(self, expected_domain, query, gateway):
    domain, score = gateway.classify_sync(query)
    assert domain == expected_domain
```

**pytest.ini configuration:**

```ini
[pytest]
markers =
    unit: Unit tests (no external dependencies)
    integration: Integration tests (may use mocks)
    remote: Remote tests (require live services)
    asyncio: Async tests
```

**Running specific tests:**

```bash
# Unit tests only
pytest -m unit

# Remote tests only
pytest -m remote

# Async unit tests
pytest -m "unit and asyncio"

# Exclude remote tests
pytest -m "not remote"
```

### 6.3 Fixture Organization

**Location:** `test_sre_gateway.py`

```python
# Minimal fixtures with clear purpose
@pytest.fixture
def gateway() -> SREGateway:
    """Gateway with LLM fallback disabled for pure keyword tests."""
    gw = SREGateway()
    gw._llm_fallback_enabled = False
    return gw

@pytest.fixture
def gateway_with_llm() -> SREGateway:
    """Gateway with LLM fallback enabled for fallback tests."""
    gw = SREGateway()
    gw._llm_fallback_enabled = True
    return gw

# Test data as module constants
DOMAIN_QUERIES = [
    (SREDomain.HEALTH, "Check health of my container apps"),
    (SREDomain.INCIDENT, "Triage the recent alerts"),
    # ...
]
```

**Benefits:**
- Clear fixture purpose in docstring
- Minimal setup (only what's needed)
- Reusable test data
- Type hints for IDE support

### 6.4 Mocking Complex Dependencies

**Location:** `test_security_compliance_agent.py`

```python
@pytest.mark.asyncio
async def test_network_audit_action_with_mock():
    agent = SecurityComplianceAgent()

    # Mock all external dependencies
    agent.registry = MagicMock()
    agent.context_store = AsyncMock()
    agent.tool_proxy_agent = AsyncMock()

    # Mock responses for different commands
    async def mock_handle_request(request):
        command = request.get("parameters", {}).get("command", "")
        if "vnet list" in command:
            return vnet_response
        elif "nsg list" in command:
            return nsg_response
        # ... more cases

    agent.tool_proxy_agent.handle_request = mock_handle_request

    result = await agent._audit_network_compliance({})
    assert result["violations_found"] > 0
```

**Pattern:**
- Mock at agent attribute level (dependency injection points)
- Use command-based routing for different mock responses
- Test business logic without external calls

### 6.5 Remote Testing Pattern

**Location:** `test_remote_sre.py`

```python
"""Remote integration tests for the SRE Orchestrator API.

Configuration (via environment variables):
    TEST_BASE_URL   Base URL of the running application
    TEST_SRE_QUERY  Optional override for test query

Markers:
    remote:  Requires a live application + Azure credentials.
    asyncio: Async tests.
"""

_BASE_URL: str = os.getenv("TEST_BASE_URL", "http://localhost:8000")
_EXECUTE_URL: str = f"{_BASE_URL}/api/sre-orchestrator/execute"

@pytest.mark.remote
@pytest.mark.asyncio
async def test_live_orchestrator():
    """Test against running service."""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            _EXECUTE_URL,
            json={"query": "check health of container apps"}
        )
        assert response.status_code == 200
```

**Pattern:**
- Clear separation with `@pytest.mark.remote`
- Environment-based configuration
- Can run against local or deployed service
- Skipped in CI unless explicitly enabled

---

## 7. Recommendations

### 7.1 Fire-and-Forget Tasks

**Do:**
- ✅ Use task set pattern to prevent garbage collection
- ✅ Add `add_done_callback` for automatic cleanup
- ✅ Include exception handling in background tasks
- ✅ Log background task completion/failure
- ✅ Use descriptive task names for debugging
- ✅ Consider FastAPI `BackgroundTasks` for post-response operations

**Don't:**
- ❌ Create tasks without keeping references
- ❌ Ignore exceptions in background tasks
- ❌ Run critical operations fire-and-forget
- ❌ Forget to clean up task references (memory leak)

**Pattern Template:**

```python
from typing import Set
import asyncio

class Orchestrator:
    def __init__(self):
        self._background_tasks: Set[asyncio.Task] = set()

    def _spawn_background(self, coro, name: str = None):
        """Spawn a background task with automatic tracking."""
        task = asyncio.create_task(coro, name=name)
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

        # Log exceptions
        def _log_exception(t: asyncio.Task):
            if not t.cancelled() and t.exception():
                logger.error(f"Background task {name} failed: {t.exception()}")

        task.add_done_callback(_log_exception)
        return task

    async def shutdown(self):
        """Cancel all background tasks."""
        for task in self._background_tasks:
            task.cancel()
        await asyncio.gather(*self._background_tasks, return_exceptions=True)
```

### 7.2 Task Lifecycle

**Do:**
- ✅ Use `TaskGroup` for related tasks (Python 3.11+)
- ✅ Always re-raise `CancelledError` after cleanup
- ✅ Use `try/finally` for guaranteed cleanup
- ✅ Implement graceful shutdown for long-running services
- ✅ Use `asyncio.shield()` for critical operations that shouldn't be cancelled
- ✅ Set reasonable timeouts with `asyncio.timeout()` or `wait_for()`

**Don't:**
- ❌ Swallow `CancelledError` without calling `uncancel()`
- ❌ Use `except Exception` to catch cancellation
- ❌ Forget to clean up resources on cancellation
- ❌ Leave zombie tasks running after shutdown

### 7.3 Testing Strategy

**Do:**
- ✅ Use `@pytest.mark.asyncio` for async tests
- ✅ Configure `asyncio_mode = auto` in pytest.ini
- ✅ Mock external dependencies (Azure SDKs, APIs)
- ✅ Use `AsyncMock` for async functions/methods
- ✅ Test both success and failure paths
- ✅ Use fixtures for common test setup
- ✅ Organize tests with markers (unit, integration, remote)
- ✅ Use `TestClient` for FastAPI with lifespan events

**Don't:**
- ❌ Make external API calls in unit tests
- ❌ Use regular `Mock` for async functions
- ❌ Forget to await async mocks
- ❌ Mix sync and async test patterns
- ❌ Share mutable state across tests without cleanup

### 7.4 Mock Design

**Do:**
- ✅ Mock at service boundaries (clients, not internals)
- ✅ Use `AsyncMock` for async methods
- ✅ Set explicit `return_value` or `side_effect`
- ✅ Verify calls with `assert_called_once()`, etc.
- ✅ Mock context managers with `__aenter__`/`__aexit__`
- ✅ Use `patch.multiple()` for multiple patches
- ✅ Test both happy path and error cases

**Don't:**
- ❌ Mock too deep (internal implementation details)
- ❌ Forget to configure mock return values
- ❌ Use regular Mock for async functions
- ❌ Over-specify mock behavior (brittle tests)

**Mock Template:**

```python
@pytest.fixture
def mock_azure_client():
    """Mock Azure client with common operations."""
    client = AsyncMock()

    # Configure common operations
    client.get_resource.return_value = {"status": "healthy"}
    client.list_resources.return_value = [{"id": "1"}, {"id": "2"}]
    client.update_resource.return_value = {"updated": True}

    # Handle errors
    client.delete_resource.side_effect = Exception("Not found")

    return client

@pytest.mark.asyncio
async def test_orchestrator(mock_azure_client):
    orchestrator = Orchestrator(azure_client=mock_azure_client)
    result = await orchestrator.get_health()

    assert result["status"] == "healthy"
    mock_azure_client.get_resource.assert_called_once()
```

### 7.5 Fixture Design

**Do:**
- ✅ Use clear, descriptive fixture names
- ✅ Add docstrings explaining fixture purpose
- ✅ Use appropriate scope (function, module, session)
- ✅ Compose fixtures (fixtures can use other fixtures)
- ✅ Use factory fixtures for creating multiple instances
- ✅ Include cleanup in fixtures (yield pattern)
- ✅ Use `monkeypatch` for environment/config changes

**Don't:**
- ❌ Create god fixtures that do too much
- ❌ Hide important setup in fixtures
- ❌ Use module/session scope for mutable state
- ❌ Forget cleanup for fixtures with side effects

**Fixture Template:**

```python
@pytest.fixture
async def orchestrator_with_deps():
    """Orchestrator with all dependencies mocked."""
    mock_cosmos = AsyncMock()
    mock_openai = AsyncMock()
    mock_graph = AsyncMock()

    # Configure mocks
    mock_cosmos.read_item.return_value = {"cached": "data"}
    mock_openai.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content="AI response"))]
    )
    mock_graph.resources.return_value = [{"type": "Microsoft.Compute/VM"}]

    orchestrator = Orchestrator(
        cosmos_client=mock_cosmos,
        openai_client=mock_openai,
        graph_client=mock_graph
    )

    yield orchestrator

    # Cleanup
    await orchestrator.shutdown()

@pytest.mark.asyncio
async def test_with_orchestrator(orchestrator_with_deps):
    result = await orchestrator_with_deps.handle_request("test")
    assert result is not None
```

### 7.6 Project-Specific Recommendations

Based on the gcc-demo codebase analysis:

1. **Enhance fire-and-forget pattern in `mcp_orchestrator.py`:**
   - Add task set tracking for embedding index builds
   - Implement graceful shutdown for background tasks

2. **Standardize test organization:**
   - ✅ Already using good marker strategy (unit, remote, asyncio)
   - Consider adding integration marker for tests with mocked Azure services
   - Create conftest.py with common fixtures

3. **Expand fixture library:**
   - Create shared fixtures for common mocks (Azure clients, MCP servers)
   - Use factory fixtures for creating agents with different configs
   - Add session-scoped fixtures for expensive operations

4. **Improve mock coverage:**
   - Add comprehensive Azure SDK mocks to conftest.py
   - Create helper functions for common mock patterns
   - Document mock response formats

5. **Add orchestrator lifecycle tests:**
   - Test graceful shutdown with pending tasks
   - Test task cancellation behavior
   - Test error handling in background tasks

---

## References

- **Python asyncio documentation:** [https://docs.python.org/3/library/asyncio-task.html](https://docs.python.org/3/library/asyncio-task.html)
- **pytest-asyncio documentation:** [https://pytest-asyncio.readthedocs.io/](https://pytest-asyncio.readthedocs.io/)
- **FastAPI testing documentation:** [https://fastapi.tiangolo.com/advanced/testing-events/](https://fastapi.tiangolo.com/advanced/testing-events/)
- **unittest.mock documentation:** [https://docs.python.org/3/library/unittest.mock.html](https://docs.python.org/3/library/unittest.mock.html)

---

**Document Version:** 1.0
**Last Updated:** 2026-02-27
**Author:** Research compilation for gcc-demo project
