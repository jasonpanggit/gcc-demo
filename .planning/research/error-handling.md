# Error Handling in Async Python Orchestrators - Research & Best Practices

**Research Date:** 2026-02-27
**Focus:** Multi-agent orchestration, async error handling, circuit breaker patterns, graceful degradation

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [asyncio.gather() and return_exceptions](#asynciogather-and-return_exceptions)
3. [Circuit Breaker Patterns](#circuit-breaker-patterns)
4. [Error Aggregation Strategies](#error-aggregation-strategies)
5. [Graceful Degradation Patterns](#graceful-degradation-patterns)
6. [Retry Patterns and Libraries](#retry-patterns-and-libraries)
7. [FastAPI Error Handling](#fastapi-error-handling)
8. [Current Codebase Patterns](#current-codebase-patterns)
9. [Recommendations](#recommendations)
10. [Code Examples](#code-examples)

---

## Executive Summary

### Key Findings

1. **`asyncio.gather(return_exceptions=True)` is essential** for multi-agent orchestrators to prevent cascade failures
2. **Circuit breaker patterns** should be applied selectively to external dependencies, not between internal agents
3. **Error aggregation** requires structured logging, monitoring, and partial success handling
4. **Graceful degradation** demands fallback paths, timeout management, and result prioritization
5. **Retry logic** should be exponential with jitter and context-aware (transient vs permanent errors)

### Current State Analysis

The gcc-demo codebase demonstrates **good foundational patterns**:
- Custom retry decorators with exponential backoff + jitter (`utils/retry.py`)
- Standardized error handlers for API and agent layers (`utils/error_handlers.py`)
- Extensive use of `return_exceptions=True` in orchestrators (16 files)
- No circuit breaker library dependency (tenacity not installed)

**Gap Areas:**
- Inconsistent error aggregation across orchestrators
- Limited circuit breaker patterns for external Azure API calls
- Some orchestrators use `return_exceptions=False` (azure_ai_sre_agent.py)
- No centralized error rate monitoring/alerting

---

## asyncio.gather() and return_exceptions

### Core Behavior

```python
# Signature
asyncio.gather(*aws, return_exceptions=False)
```

**Default behavior (`return_exceptions=False`):**
- First exception raised is **immediately propagated** to caller
- Other awaitables in the sequence **continue to run** (not cancelled automatically)
- Use when you want fast-fail but background tasks to complete

**With `return_exceptions=True`:**
- Exceptions are **treated as successful results** and included in the result list
- The list may contain a mix of results and exception objects
- Use when you need to inspect and handle each outcome individually

**Cancellation semantics:**
- If `gather()` itself is cancelled, all submitted awaitables are cancelled
- If an individual Task/Future is cancelled, it raises `CancelledError` (propagated unless `return_exceptions=True`)
- Cancelling `gather()` **after** it has already propagated an exception will **not cancel children**

### Best Practices

#### 1. Multi-Agent Orchestration: Use `return_exceptions=True`

**Why:** Prevents one agent failure from breaking the entire orchestration. Allows best-effort result aggregation.

```python
# GOOD: Multi-agent pattern
async def orchestrate_agents(query: str) -> Dict[str, Any]:
    tasks = [
        agent_a.process(query),
        agent_b.process(query),
        agent_c.process(query),
    ]

    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Aggregate partial results
    successful = []
    failed = []

    for idx, result in enumerate(results):
        if isinstance(result, Exception):
            logger.warning(f"Agent {idx} failed: {result}")
            failed.append({"agent": idx, "error": str(result)})
        else:
            successful.append(result)

    return {
        "success": len(successful) > 0,
        "results": successful,
        "errors": failed,
        "partial": len(failed) > 0,
    }
```

#### 2. Critical Dependencies: Use Default + Manual Cancellation

**Why:** When all tasks must succeed or none should continue, explicitly cancel remaining tasks on first failure.

```python
# GOOD: Fail-fast with cleanup
async def execute_critical_workflow(steps: List[Step]) -> WorkflowResult:
    tasks = [asyncio.create_task(execute_step(s)) for s in steps]

    try:
        results = await asyncio.gather(*tasks)  # return_exceptions=False
        return WorkflowResult(success=True, results=results)
    except Exception as exc:
        logger.error(f"Critical workflow failed: {exc}")

        # Cancel all unfinished tasks
        for task in tasks:
            if not task.done():
                task.cancel()

        # Wait for cancellation to complete
        await asyncio.gather(*tasks, return_exceptions=True)

        return WorkflowResult(success=False, error=str(exc))
```

#### 3. Structured Concurrency: Prefer TaskGroup (Python 3.11+)

**Why:** Provides stronger safety guarantees. Automatically cancels remaining tasks when one fails.

```python
# BEST: Modern structured concurrency
import asyncio

async def structured_execution(operations: List[Callable]) -> List[Any]:
    """
    TaskGroup cancels remaining tasks on first failure and waits for all
    children to finish/cancel. Exceptions are grouped and re-raised.
    """
    results = []

    try:
        async with asyncio.TaskGroup() as tg:
            tasks = [tg.create_task(op()) for op in operations]

        # All succeeded - extract results
        results = [task.result() for task in tasks]

    except* Exception as exc_group:
        # Handle ExceptionGroup from TaskGroup
        logger.error(f"Structured execution failed: {exc_group}")
        raise

    return results
```

### When to Use Each Pattern

| Pattern | Use Case | Cancellation Behavior | Error Propagation |
|---------|----------|----------------------|-------------------|
| `return_exceptions=False` | Critical workflows where all must succeed | Manual (tasks continue) | First exception propagates |
| `return_exceptions=True` | **Multi-agent/best-effort** | Manual (tasks continue) | All exceptions returned in list |
| `TaskGroup` (3.11+) | Structured workflows with strict cleanup | **Automatic** | ExceptionGroup after all cancelled |

### Common Pitfalls

❌ **Don't assume other tasks are cancelled on exception:**
```python
# WRONG: Other tasks will keep running!
try:
    await asyncio.gather(long_task(), failing_task())
except Exception:
    # long_task() is still running here!
    pass
```

❌ **Don't forget to check exception types with `return_exceptions=True`:**
```python
# WRONG: Will try to process exception as result
results = await asyncio.gather(*tasks, return_exceptions=True)
for result in results:
    process_data(result)  # May fail if result is an Exception!
```

✅ **Always inspect results when using `return_exceptions=True`:**
```python
# CORRECT: Check each result
results = await asyncio.gather(*tasks, return_exceptions=True)
for idx, result in enumerate(results):
    if isinstance(result, Exception):
        logger.error(f"Task {idx} failed: {result}")
    else:
        process_data(result)
```

❌ **Don't rely on cancelling gather() to stop children after exception:**
```python
# WRONG: gather_task.cancel() won't cancel children that already started
gather_task = asyncio.create_task(asyncio.gather(*tasks))
try:
    await gather_task
except Exception:
    gather_task.cancel()  # Too late - children keep running!
```

### Performance Considerations

- **Memory:** `gather()` holds references to all awaitables until complete
- **Ordering:** Results are always returned in input order, regardless of completion order
- **Fire-and-forget:** Save strong references to background tasks (event loop keeps only weak refs)
- **Timeout:** Combine with `asyncio.wait_for()` for timeout on entire gather operation

---

## Circuit Breaker Patterns

### When to Use Circuit Breakers

Circuit breakers are **selective protective mechanisms** for external dependencies:

✅ **Use circuit breakers for:**
- External API calls (Azure SDKs, third-party APIs)
- Database connections that can become unresponsive
- Network services with known reliability issues
- Resource-intensive operations that can cascade failures

❌ **Don't use circuit breakers for:**
- Internal agent-to-agent communication
- In-memory operations
- Fast-fail operations with timeouts
- One-off operations without retry

### Why Not tenacity for Circuit Breakers?

**Key finding:** The tenacity library (Python's most popular retry library) **does not provide a built-in circuit breaker primitive**.

**What tenacity provides:**
- Retry logic with exponential backoff
- Flexible stop conditions (attempts, time, custom)
- Wait strategies (fixed, exponential, random jitter)
- Retry conditions based on exceptions or results
- Async support via `@retry` decorator or `AsyncRetrying` loop

**What tenacity does NOT provide:**
- Circuit breaker state machine (CLOSED → OPEN → HALF_OPEN)
- Failure threshold tracking across calls
- Automatic circuit opening/closing
- Health check mechanisms

### Circuit Breaker Implementation Options

#### Option 1: pybreaker (Dedicated Library)

```bash
pip install pybreaker
```

```python
from pybreaker import CircuitBreaker, CircuitBreakerError
import asyncio

# Create circuit breaker
azure_api_breaker = CircuitBreaker(
    fail_max=5,           # Open after 5 failures
    timeout_duration=60,  # Stay open for 60 seconds
    name="azure_api"
)

@azure_api_breaker
async def call_azure_api(resource_id: str) -> Dict[str, Any]:
    """Call Azure API with circuit breaker protection."""
    async with aiohttp.ClientSession() as session:
        async with session.get(f"https://management.azure.com/{resource_id}") as resp:
            resp.raise_for_status()
            return await resp.json()

# Usage
try:
    result = await call_azure_api(resource_id)
except CircuitBreakerError:
    logger.warning("Azure API circuit breaker OPEN - using cached data")
    result = await get_cached_data(resource_id)
```

**Pros:**
- Purpose-built for circuit breaker pattern
- Simple decorator API
- Built-in state management
- Works with async code

**Cons:**
- Another dependency to maintain
- Less flexible than custom implementation
- No built-in retry integration

#### Option 2: Custom Circuit Breaker with tenacity Retry

```python
import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Callable, Optional
from tenacity import AsyncRetrying, stop_after_attempt, wait_exponential, RetryError

class CircuitState(Enum):
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Blocking calls
    HALF_OPEN = "half_open"  # Testing recovery

@dataclass
class CircuitBreakerConfig:
    failure_threshold: int = 5
    timeout_seconds: float = 60.0
    half_open_attempts: int = 1

class AsyncCircuitBreaker:
    """
    Custom circuit breaker with integrated retry logic.

    States:
    - CLOSED: Normal operation, retry on failures
    - OPEN: Fast-fail without calling dependency
    - HALF_OPEN: Allow limited calls to test recovery
    """

    def __init__(self, name: str, config: CircuitBreakerConfig):
        self.name = name
        self.config = config
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time: Optional[datetime] = None
        self.half_open_attempts = 0

    def should_allow_request(self) -> bool:
        """Check if request should be allowed based on circuit state."""
        if self.state == CircuitState.CLOSED:
            return True

        if self.state == CircuitState.OPEN:
            # Check if timeout has elapsed
            if self.last_failure_time:
                elapsed = (datetime.utcnow() - self.last_failure_time).total_seconds()
                if elapsed >= self.config.timeout_seconds:
                    self.state = CircuitState.HALF_OPEN
                    self.half_open_attempts = 0
                    return True
            return False

        if self.state == CircuitState.HALF_OPEN:
            # Allow limited attempts in half-open state
            if self.half_open_attempts < self.config.half_open_attempts:
                self.half_open_attempts += 1
                return True
            return False

        return False

    def record_success(self):
        """Record successful call and close circuit if half-open."""
        if self.state == CircuitState.HALF_OPEN:
            self.state = CircuitState.CLOSED
            self.failure_count = 0

    def record_failure(self):
        """Record failed call and potentially open circuit."""
        self.failure_count += 1
        self.last_failure_time = datetime.utcnow()

        if self.failure_count >= self.config.failure_threshold:
            self.state = CircuitState.OPEN

    async def call(self, func: Callable, *args, **kwargs):
        """
        Execute function with circuit breaker protection and retry logic.

        Raises:
            CircuitBreakerOpenError: When circuit is open
            RetryError: When all retry attempts exhausted
        """
        if not self.should_allow_request():
            raise CircuitBreakerOpenError(
                f"Circuit breaker '{self.name}' is OPEN - request blocked"
            )

        try:
            # Use tenacity for retry logic
            async for attempt in AsyncRetrying(
                stop=stop_after_attempt(3),
                wait=wait_exponential(multiplier=1, min=4, max=10),
            ):
                with attempt:
                    result = await func(*args, **kwargs)
                    self.record_success()
                    return result

        except RetryError as e:
            self.record_failure()
            raise

class CircuitBreakerOpenError(Exception):
    """Raised when circuit breaker is open and blocking requests."""
    pass

# Usage example
azure_compute_breaker = AsyncCircuitBreaker(
    name="azure_compute_api",
    config=CircuitBreakerConfig(
        failure_threshold=5,
        timeout_seconds=60.0,
    )
)

async def get_vm_status(vm_id: str) -> str:
    """Get VM status with circuit breaker and retry protection."""
    try:
        return await azure_compute_breaker.call(
            _fetch_vm_status,
            vm_id
        )
    except CircuitBreakerOpenError:
        logger.warning(f"Azure Compute API circuit breaker OPEN")
        return "unknown"  # Graceful degradation
    except RetryError:
        logger.error(f"Failed to get VM status after retries")
        return "error"

async def _fetch_vm_status(vm_id: str) -> str:
    """Internal function that calls Azure API."""
    # Actual Azure SDK call here
    async with compute_client.virtual_machines.instance_view(
        resource_group, vm_id
    ) as vm:
        return vm.statuses[0].code
```

#### Option 3: Azure SDK Built-in Retry Policies

**Best practice:** Use Azure SDK's built-in retry policies for Azure API calls.

```python
from azure.core.pipeline.policies import RetryPolicy
from azure.mgmt.compute import ComputeManagementClient
from azure.identity.aio import DefaultAzureCredential

# Configure custom retry policy
custom_retry = RetryPolicy(
    retry_total=5,
    retry_connect=3,
    retry_read=3,
    retry_status=3,
    retry_backoff_factor=0.8,
    retry_backoff_max=60,
)

credential = DefaultAzureCredential()
compute_client = ComputeManagementClient(
    credential=credential,
    subscription_id=subscription_id,
    retry_policy=custom_retry,
)

# SDK automatically retries on transient failures
# Wrap in circuit breaker for additional protection
```

### Recommended Pattern: Layered Protection

Combine Azure SDK retry + custom circuit breaker + timeout:

```python
from azure.core.exceptions import AzureError
import asyncio

async def call_azure_with_protection(
    operation: Callable,
    circuit_breaker: AsyncCircuitBreaker,
    timeout_seconds: float = 30.0,
    fallback_value: Any = None,
) -> Any:
    """
    Call Azure operation with layered protection:
    1. Circuit breaker check (fast-fail if open)
    2. Timeout protection
    3. Azure SDK retry (built-in)
    4. Circuit breaker tracking
    5. Fallback on failure
    """

    # Layer 1: Circuit breaker
    if not circuit_breaker.should_allow_request():
        logger.warning(f"Circuit breaker {circuit_breaker.name} is OPEN")
        return fallback_value

    try:
        # Layer 2: Timeout
        result = await asyncio.wait_for(
            circuit_breaker.call(operation),  # Layer 3: Retry + breaker tracking
            timeout=timeout_seconds
        )
        return result

    except asyncio.TimeoutError:
        logger.error(f"Azure operation timed out after {timeout_seconds}s")
        circuit_breaker.record_failure()
        return fallback_value

    except (AzureError, Exception) as e:
        logger.error(f"Azure operation failed: {e}")
        circuit_breaker.record_failure()
        return fallback_value
```

---

## Error Aggregation Strategies

### Multi-Agent Error Aggregation

In multi-agent systems, error aggregation serves multiple purposes:
1. **Observability:** Track which agents failed and why
2. **Partial Success:** Return best-effort results when some agents succeed
3. **Debugging:** Provide detailed error context for troubleshooting
4. **User Feedback:** Communicate partial failures without overwhelming users

### Pattern 1: Structured Error Collection

```python
from dataclasses import dataclass
from typing import List, Dict, Any, Optional
from enum import Enum

class ErrorSeverity(Enum):
    CRITICAL = "critical"  # Blocks entire operation
    HIGH = "high"          # Blocks partial functionality
    MEDIUM = "medium"      # Degraded experience
    LOW = "low"            # Minor issue, user may not notice

@dataclass
class AgentError:
    agent_name: str
    error_type: str
    message: str
    severity: ErrorSeverity
    timestamp: str
    context: Optional[Dict[str, Any]] = None
    retry_attempted: bool = False

@dataclass
class AggregatedResult:
    success: bool
    partial_success: bool
    results: List[Any]
    errors: List[AgentError]
    metadata: Dict[str, Any]

    @property
    def has_critical_errors(self) -> bool:
        return any(e.severity == ErrorSeverity.CRITICAL for e in self.errors)

    @property
    def error_summary(self) -> str:
        if not self.errors:
            return "No errors"

        by_severity = {}
        for error in self.errors:
            by_severity.setdefault(error.severity, []).append(error)

        parts = []
        for severity in ErrorSeverity:
            count = len(by_severity.get(severity, []))
            if count > 0:
                parts.append(f"{severity.value}: {count}")

        return ", ".join(parts)

async def orchestrate_with_error_aggregation(
    agents: List[Agent],
    query: str
) -> AggregatedResult:
    """
    Execute agents in parallel and aggregate errors with severity classification.
    """
    tasks = [agent.process(query) for agent in agents]
    results_or_exceptions = await asyncio.gather(*tasks, return_exceptions=True)

    successful_results = []
    errors = []

    for idx, outcome in enumerate(results_or_exceptions):
        agent = agents[idx]

        if isinstance(outcome, Exception):
            # Classify error severity
            severity = classify_error_severity(outcome, agent)

            error = AgentError(
                agent_name=agent.name,
                error_type=type(outcome).__name__,
                message=str(outcome),
                severity=severity,
                timestamp=datetime.utcnow().isoformat(),
                context={
                    "query": query,
                    "agent_type": agent.agent_type,
                }
            )
            errors.append(error)

            logger.error(
                f"Agent {agent.name} failed with {severity.value} severity",
                extra={
                    "agent_name": agent.name,
                    "error_type": type(outcome).__name__,
                    "severity": severity.value,
                }
            )
        else:
            successful_results.append(outcome)

    # Determine overall success
    has_critical = any(e.severity == ErrorSeverity.CRITICAL for e in errors)
    success = not has_critical and len(successful_results) > 0
    partial = len(successful_results) > 0 and len(errors) > 0

    return AggregatedResult(
        success=success,
        partial_success=partial,
        results=successful_results,
        errors=errors,
        metadata={
            "total_agents": len(agents),
            "successful": len(successful_results),
            "failed": len(errors),
            "query": query,
        }
    )

def classify_error_severity(error: Exception, agent: Agent) -> ErrorSeverity:
    """Classify error severity based on exception type and agent criticality."""

    # Network/timeout errors are usually transient
    if isinstance(error, (asyncio.TimeoutError, ConnectionError)):
        return ErrorSeverity.MEDIUM

    # Azure SDK errors
    if "AzureError" in type(error).__name__:
        if "NotFound" in type(error).__name__:
            return ErrorSeverity.LOW
        if "Unauthorized" in type(error).__name__:
            return ErrorSeverity.CRITICAL
        return ErrorSeverity.HIGH

    # Agent-specific criticality
    if agent.is_critical:
        return ErrorSeverity.CRITICAL

    return ErrorSeverity.MEDIUM
```

### Pattern 2: Error Rate Monitoring

```python
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Dict

class ErrorRateMonitor:
    """
    Monitor error rates across agents/operations to detect patterns.
    Useful for alerting and circuit breaker decisions.
    """

    def __init__(self, window_minutes: int = 5):
        self.window = timedelta(minutes=window_minutes)
        self.errors: Dict[str, List[datetime]] = defaultdict(list)
        self.successes: Dict[str, List[datetime]] = defaultdict(list)

    def record_error(self, operation: str):
        """Record error for operation."""
        now = datetime.utcnow()
        self.errors[operation].append(now)
        self._cleanup_old_records(operation)

    def record_success(self, operation: str):
        """Record success for operation."""
        now = datetime.utcnow()
        self.successes[operation].append(now)
        self._cleanup_old_records(operation)

    def _cleanup_old_records(self, operation: str):
        """Remove records outside the time window."""
        cutoff = datetime.utcnow() - self.window
        self.errors[operation] = [
            t for t in self.errors[operation] if t > cutoff
        ]
        self.successes[operation] = [
            t for t in self.successes[operation] if t > cutoff
        ]

    def get_error_rate(self, operation: str) -> float:
        """Get error rate (0.0 to 1.0) for operation in current window."""
        self._cleanup_old_records(operation)

        error_count = len(self.errors[operation])
        success_count = len(self.successes[operation])
        total = error_count + success_count

        if total == 0:
            return 0.0

        return error_count / total

    def is_unhealthy(self, operation: str, threshold: float = 0.5) -> bool:
        """Check if operation error rate exceeds threshold."""
        return self.get_error_rate(operation) > threshold

    def get_stats(self) -> Dict[str, Dict[str, Any]]:
        """Get error rate stats for all operations."""
        stats = {}
        all_ops = set(self.errors.keys()) | set(self.successes.keys())

        for op in all_ops:
            self._cleanup_old_records(op)
            error_count = len(self.errors[op])
            success_count = len(self.successes[op])
            total = error_count + success_count

            stats[op] = {
                "error_count": error_count,
                "success_count": success_count,
                "total": total,
                "error_rate": error_count / total if total > 0 else 0.0,
                "window_minutes": self.window.total_seconds() / 60,
            }

        return stats

# Usage in orchestrator
error_monitor = ErrorRateMonitor(window_minutes=5)

async def execute_agent_with_monitoring(
    agent: Agent,
    query: str
) -> Any:
    """Execute agent and track error rates."""
    operation = f"agent_{agent.name}"

    try:
        result = await agent.process(query)
        error_monitor.record_success(operation)
        return result

    except Exception as e:
        error_monitor.record_error(operation)

        # Check if agent is unhealthy
        if error_monitor.is_unhealthy(operation, threshold=0.7):
            logger.critical(
                f"Agent {agent.name} error rate > 70% - consider disabling",
                extra=error_monitor.get_stats()[operation]
            )

        raise
```

### Pattern 3: Partial Success with Confidence Scoring

```python
@dataclass
class AgentResult:
    agent_name: str
    data: Any
    confidence: float  # 0.0 to 1.0
    source: str
    timestamp: str

async def aggregate_with_confidence(
    agents: List[Agent],
    query: str,
    min_confidence: float = 0.5,
) -> Dict[str, Any]:
    """
    Aggregate results from multiple agents, filtering by confidence
    and selecting best result.
    """
    tasks = [agent.process(query) for agent in agents]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    valid_results = []
    errors = []

    for idx, outcome in enumerate(results):
        agent = agents[idx]

        if isinstance(outcome, Exception):
            errors.append({
                "agent": agent.name,
                "error": str(outcome),
                "type": type(outcome).__name__,
            })
            continue

        # Extract confidence from result
        confidence = outcome.get("confidence", 0.0)

        if confidence >= min_confidence:
            valid_results.append(AgentResult(
                agent_name=agent.name,
                data=outcome.get("data"),
                confidence=confidence,
                source=outcome.get("source", agent.name),
                timestamp=datetime.utcnow().isoformat(),
            ))

    if not valid_results:
        return {
            "success": False,
            "message": f"No results met minimum confidence {min_confidence}",
            "errors": errors,
        }

    # Sort by confidence and return best result
    best_result = max(valid_results, key=lambda r: r.confidence)

    return {
        "success": True,
        "result": best_result.data,
        "confidence": best_result.confidence,
        "source": best_result.source,
        "alternatives": len(valid_results) - 1,
        "errors": errors,  # Include errors for observability
        "metadata": {
            "total_agents": len(agents),
            "successful_agents": len(valid_results),
            "failed_agents": len(errors),
            "best_agent": best_result.agent_name,
        }
    }
```

---

## Graceful Degradation Patterns

Graceful degradation ensures systems remain functional when components fail. Key strategies:

1. **Fallback chains:** Primary → Secondary → Cached → Default
2. **Feature toggling:** Disable non-critical features when dependencies fail
3. **Timeouts:** Prevent slow operations from blocking system
4. **Result prioritization:** Return partial/stale data instead of nothing

### Pattern 1: Fallback Chain

```python
from typing import Optional, Callable, Any, List

async def execute_with_fallbacks(
    primary: Callable,
    fallbacks: List[Callable],
    timeout_seconds: float = 10.0,
    cache_result: bool = True,
) -> Optional[Any]:
    """
    Execute operation with fallback chain.

    Tries primary, then each fallback in order until one succeeds.
    Caches successful results for future fallbacks.
    """
    operations = [primary] + fallbacks
    last_error = None

    for idx, operation in enumerate(operations):
        operation_name = operation.__name__
        is_fallback = idx > 0

        try:
            logger.info(
                f"Executing {'fallback' if is_fallback else 'primary'}: {operation_name}"
            )

            result = await asyncio.wait_for(
                operation(),
                timeout=timeout_seconds
            )

            if is_fallback:
                logger.warning(
                    f"Primary failed, used fallback: {operation_name}"
                )

            # Cache successful result
            if cache_result and result is not None:
                await cache_manager.set(
                    f"fallback_cache_{primary.__name__}",
                    result,
                    ttl=300,  # 5 minutes
                )

            return result

        except asyncio.TimeoutError:
            logger.warning(
                f"{operation_name} timed out after {timeout_seconds}s"
            )
            last_error = f"Timeout after {timeout_seconds}s"

        except Exception as e:
            logger.error(f"{operation_name} failed: {e}")
            last_error = str(e)

    # All operations failed
    logger.error(
        f"All operations failed, last error: {last_error}",
        extra={"operation_count": len(operations)}
    )
    return None

# Example usage
async def get_vm_status_with_fallbacks(vm_id: str) -> str:
    """Get VM status with multiple fallback strategies."""

    async def from_azure_api():
        return await azure_client.virtual_machines.instance_view(
            resource_group, vm_id
        )

    async def from_inventory_cache():
        cached = await inventory_cache.get(vm_id)
        if cached and "status" in cached:
            return cached["status"]
        raise ValueError("No cached status")

    async def from_resource_graph():
        query = f"Resources | where id == '{vm_id}' | project powerState"
        result = await resource_graph_client.query(query)
        return result.data[0]["powerState"]

    async def default_unknown():
        return "unknown"

    status = await execute_with_fallbacks(
        primary=from_azure_api,
        fallbacks=[
            from_inventory_cache,
            from_resource_graph,
            default_unknown,
        ],
        timeout_seconds=5.0,
    )

    return status
```

### Pattern 2: Feature Toggle Manager

```python
from enum import Enum
from typing import Dict, Set

class FeatureFlag(Enum):
    AZURE_MONITORING = "azure_monitoring"
    COST_ANALYSIS = "cost_analysis"
    ADVANCED_ANALYTICS = "advanced_analytics"
    THIRD_PARTY_INTEGRATIONS = "third_party_integrations"

class FeatureToggleManager:
    """
    Manage feature toggles for graceful degradation.

    Automatically disables non-critical features when dependencies fail.
    """

    def __init__(self):
        self._enabled: Dict[FeatureFlag, bool] = {
            flag: True for flag in FeatureFlag
        }
        self._critical: Set[FeatureFlag] = set()

    def mark_critical(self, feature: FeatureFlag):
        """Mark feature as critical (never auto-disable)."""
        self._critical.add(feature)

    def is_enabled(self, feature: FeatureFlag) -> bool:
        """Check if feature is currently enabled."""
        return self._enabled.get(feature, False)

    def disable(self, feature: FeatureFlag, reason: str):
        """Disable feature (unless critical)."""
        if feature in self._critical:
            logger.warning(
                f"Cannot disable critical feature {feature.value}: {reason}"
            )
            return

        if self._enabled[feature]:
            logger.warning(
                f"Disabling feature {feature.value}: {reason}"
            )
            self._enabled[feature] = False

    def enable(self, feature: FeatureFlag):
        """Re-enable feature."""
        if not self._enabled[feature]:
            logger.info(f"Re-enabling feature {feature.value}")
            self._enabled[feature] = True

    def get_status(self) -> Dict[str, Any]:
        """Get status of all features."""
        return {
            flag.value: {
                "enabled": self._enabled[flag],
                "critical": flag in self._critical,
            }
            for flag in FeatureFlag
        }

# Usage in orchestrator
feature_manager = FeatureToggleManager()
feature_manager.mark_critical(FeatureFlag.AZURE_MONITORING)

async def execute_with_feature_toggle(
    feature: FeatureFlag,
    operation: Callable,
    fallback_result: Any = None,
) -> Any:
    """Execute operation if feature is enabled, otherwise return fallback."""

    if not feature_manager.is_enabled(feature):
        logger.info(f"Feature {feature.value} disabled, using fallback")
        return fallback_result

    try:
        result = await operation()
        return result

    except Exception as e:
        logger.error(f"Feature {feature.value} failed: {e}")

        # Auto-disable feature on repeated failures
        error_rate = error_monitor.get_error_rate(feature.value)
        if error_rate > 0.8:
            feature_manager.disable(
                feature,
                reason=f"Error rate {error_rate:.1%} exceeds threshold"
            )

        return fallback_result

# Example
async def get_cost_analysis(resource_group: str) -> Dict[str, Any]:
    """Get cost analysis with graceful degradation."""

    async def fetch_cost_data():
        return await azure_cost_client.query(resource_group)

    return await execute_with_feature_toggle(
        feature=FeatureFlag.COST_ANALYSIS,
        operation=fetch_cost_data,
        fallback_result={
            "message": "Cost analysis temporarily unavailable",
            "estimated": True,
        }
    )
```

### Pattern 3: Timeout Cascade Prevention

```python
async def execute_with_timeout_budget(
    operations: List[Tuple[str, Callable]],
    total_budget_seconds: float,
    min_timeout_per_op: float = 1.0,
) -> Dict[str, Any]:
    """
    Execute operations with timeout budget management.

    Prevents slow operations from consuming entire budget and blocking
    subsequent operations. Each operation gets fair share of remaining time.
    """
    results = {}
    errors = {}
    start_time = asyncio.get_event_loop().time()

    for idx, (name, operation) in enumerate(operations):
        # Calculate remaining budget
        elapsed = asyncio.get_event_loop().time() - start_time
        remaining_budget = total_budget_seconds - elapsed

        if remaining_budget <= 0:
            logger.warning(
                f"Timeout budget exhausted, skipping remaining {len(operations) - idx} operations"
            )
            break

        # Allocate timeout: fair share of remaining budget
        remaining_ops = len(operations) - idx
        allocated_timeout = max(
            remaining_budget / remaining_ops,
            min_timeout_per_op
        )

        try:
            result = await asyncio.wait_for(
                operation(),
                timeout=allocated_timeout
            )
            results[name] = result

        except asyncio.TimeoutError:
            logger.warning(
                f"{name} timed out after {allocated_timeout:.2f}s"
            )
            errors[name] = f"Timeout after {allocated_timeout:.2f}s"

        except Exception as e:
            logger.error(f"{name} failed: {e}")
            errors[name] = str(e)

    total_elapsed = asyncio.get_event_loop().time() - start_time

    return {
        "success": len(results) > 0,
        "results": results,
        "errors": errors,
        "metadata": {
            "total_budget_seconds": total_budget_seconds,
            "elapsed_seconds": total_elapsed,
            "completed": len(results),
            "failed": len(errors),
            "skipped": len(operations) - len(results) - len(errors),
        }
    }

# Example usage
async def comprehensive_sre_check(resource_group: str) -> Dict[str, Any]:
    """Run comprehensive SRE checks with timeout budget."""

    operations = [
        ("health_check", lambda: check_resource_health(resource_group)),
        ("performance", lambda: analyze_performance(resource_group)),
        ("cost_analysis", lambda: get_cost_breakdown(resource_group)),
        ("security_scan", lambda: run_security_scan(resource_group)),
        ("compliance_check", lambda: check_compliance(resource_group)),
    ]

    return await execute_with_timeout_budget(
        operations,
        total_budget_seconds=30.0,  # 30s total budget
        min_timeout_per_op=2.0,     # At least 2s per operation
    )
```

---

## Retry Patterns and Libraries

### Comparison: tenacity vs Custom Retry

| Feature | tenacity | Custom (`utils/retry.py`) | Winner |
|---------|----------|--------------------------|---------|
| **Zero dependencies** | ❌ | ✅ | Custom |
| **Async support** | ✅ | ✅ | Tie |
| **Exponential backoff** | ✅ | ✅ | Tie |
| **Jitter** | ✅ | ✅ | Tie |
| **Retry on result** | ✅ | ❌ | tenacity |
| **Custom stop conditions** | ✅ | ❌ | tenacity |
| **Statistics/hooks** | ✅ | ❌ | tenacity |
| **Simplicity** | Complex API | Simple decorator | Custom |
| **Maintenance** | External | In-house | Custom |

### Current Implementation Analysis

The existing `utils/retry.py` provides:
- ✅ Exponential backoff with jitter
- ✅ Configurable retry attempts and delays
- ✅ Async and sync decorators
- ✅ Zero external dependencies
- ✅ Simple, maintainable code

**Gaps:**
- ❌ No retry based on return value
- ❌ No statistics/observability hooks
- ❌ No dynamic stop conditions
- ❌ No way to force retry (no `TryAgain` exception)

### Recommendation: Enhance Custom Implementation

Instead of adding tenacity dependency, enhance existing `utils/retry.py`:

```python
# Enhanced version of utils/retry.py

import asyncio
import functools
import logging
import random
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Optional, Tuple, Type, Any, Dict

logger = logging.getLogger(__name__)

ExceptionTypes = Tuple[Type[BaseException], ...]

@dataclass
class RetryStats:
    """Statistics for retry operations."""
    total_attempts: int = 0
    successful_attempts: int = 0
    failed_attempts: int = 0
    total_delay_seconds: float = 0.0
    last_attempt_time: Optional[datetime] = None

class TryAgain(Exception):
    """Exception to explicitly force a retry."""
    pass

def retry_async(
    retries: int = 5,
    initial_delay: float = 1.0,
    max_delay: float = 30.0,
    backoff_factor: float = 2.0,
    exceptions: Optional[ExceptionTypes] = None,
    jitter: float = 0.1,
    on_retry: Optional[Callable[[int, Exception], None]] = None,
    retry_on_result: Optional[Callable[[Any], bool]] = None,
    reraise: bool = True,
    stats: Optional[RetryStats] = None,
):
    """
    Enhanced async retry decorator with hooks and result-based retry.

    Args:
        retries: Total attempts (including first)
        initial_delay: Starting delay in seconds
        max_delay: Maximum delay in seconds
        backoff_factor: Multiplier for delay on each retry
        exceptions: Tuple of exception classes to catch and retry
        jitter: Fraction of delay to add as random jitter (0.0-1.0)
        on_retry: Callback function called before each retry: f(attempt_num, exception)
        retry_on_result: Function to check result and force retry: f(result) -> bool
        reraise: If True, reraise last exception; if False, return None
        stats: Optional RetryStats object to track statistics

    Raises:
        Last exception if all retries exhausted and reraise=True

    Returns:
        Function result or None if retries exhausted and reraise=False
    """
    if exceptions is None:
        exceptions = (Exception,)

    # Always include TryAgain in retry exceptions
    if TryAgain not in exceptions:
        exceptions = exceptions + (TryAgain,)

    def decorator(func: Callable):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            delay = initial_delay
            last_exc = None

            for attempt in range(1, retries + 1):
                if stats:
                    stats.total_attempts += 1
                    stats.last_attempt_time = datetime.utcnow()

                try:
                    result = await func(*args, **kwargs)

                    # Check if result should trigger retry
                    if retry_on_result and retry_on_result(result):
                        if attempt == retries:
                            logger.warning(
                                f"{func.__name__}: Result check failed on final attempt"
                            )
                            return result

                        logger.debug(
                            f"{func.__name__}: Result check failed, retrying (attempt {attempt}/{retries})"
                        )
                        raise TryAgain("Result condition not met")

                    if stats:
                        stats.successful_attempts += 1

                    return result

                except exceptions as exc:
                    last_exc = exc

                    if stats:
                        stats.failed_attempts += 1

                    if attempt == retries:
                        # Exhausted retries
                        logger.error(
                            f"{func.__name__}: All {retries} attempts failed",
                            exc_info=not isinstance(exc, TryAgain)
                        )
                        if reraise:
                            raise
                        return None

                    # Calculate sleep time with jitter
                    jitter_amount = random.uniform(0, jitter * delay)
                    sleep_for = min(delay + jitter_amount, max_delay)

                    # Call retry hook
                    if on_retry:
                        try:
                            on_retry(attempt, exc)
                        except Exception as hook_err:
                            logger.error(f"on_retry hook failed: {hook_err}")

                    logger.warning(
                        f"{func.__name__}: Attempt {attempt}/{retries} failed, "
                        f"retrying in {sleep_for:.2f}s: {exc}"
                    )

                    if stats:
                        stats.total_delay_seconds += sleep_for

                    await asyncio.sleep(sleep_for)
                    delay = min(delay * backoff_factor, max_delay)

            # Should not reach here
            if last_exc and reraise:
                raise last_exc
            return None

        # Attach stats to function for inspection
        if stats:
            wrapper.retry_stats = stats

        return wrapper

    return decorator

# Example usage with enhanced features
retry_stats = RetryStats()

def log_retry_attempt(attempt: int, exception: Exception):
    """Hook called before each retry."""
    logger.warning(f"Retry attempt {attempt} after error: {exception}")

@retry_async(
    retries=5,
    initial_delay=1.0,
    max_delay=30.0,
    on_retry=log_retry_attempt,
    retry_on_result=lambda r: r is None or r.get("status") != "ready",
    stats=retry_stats,
)
async def fetch_with_result_check(resource_id: str) -> Dict[str, Any]:
    """Fetch resource and retry if not ready."""
    result = await azure_client.get_resource(resource_id)
    return result

# Check stats later
print(f"Total attempts: {retry_stats.total_attempts}")
print(f"Success rate: {retry_stats.successful_attempts / retry_stats.total_attempts:.1%}")
```

---

## FastAPI Error Handling

### Global Exception Handlers

FastAPI provides powerful exception handling for standardized error responses:

```python
from fastapi import FastAPI, Request, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from utils.response_models import StandardResponse

app = FastAPI()

# Handle all HTTP exceptions (including Starlette framework errors)
@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """Handle HTTP exceptions with structured logging."""
    logger.warning(
        f"HTTP {exc.status_code} error on {request.url.path}: {exc.detail}",
        extra={
            "status_code": exc.status_code,
            "path": request.url.path,
            "method": request.method,
        }
    )

    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "message": exc.detail,
            "error": {
                "type": "HTTPException",
                "status_code": exc.status_code,
            }
        }
    )

# Handle validation errors
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle request validation errors."""
    # Log full details server-side
    logger.error(
        f"Validation error on {request.url.path}",
        extra={
            "errors": exc.errors(),
            "body": exc.body,
            "path": request.url.path,
        }
    )

    # Return sanitized response to client
    return JSONResponse(
        status_code=422,
        content={
            "success": False,
            "message": "Request validation failed",
            "error": {
                "type": "ValidationError",
                "details": exc.errors(),
            }
        }
    )

# Handle all unhandled exceptions
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Catch-all handler for unexpected errors."""
    logger.critical(
        f"Unhandled exception on {request.url.path}",
        exc_info=True,
        extra={
            "path": request.url.path,
            "method": request.method,
            "error_type": type(exc).__name__,
        }
    )

    # Never expose internal error details to clients
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "message": "Internal server error",
            "error": {
                "type": "InternalError",
                "request_id": str(uuid.uuid4()),  # For support tracking
            }
        }
    )
```

### Async Dependency Error Handling

```python
from fastapi import Depends, HTTPException

async def get_current_user(token: str) -> User:
    """Dependency that may fail."""
    try:
        user = await auth_service.verify_token(token)
        if not user:
            raise HTTPException(status_code=401, detail="Invalid token")
        return user
    except Exception as e:
        logger.error(f"Auth service error: {e}")
        raise HTTPException(
            status_code=503,
            detail="Authentication service unavailable"
        )

@app.get("/api/protected")
async def protected_route(user: User = Depends(get_current_user)):
    """Route with dependency error handling."""
    # user is guaranteed to be valid here
    return {"message": f"Hello {user.name}"}
```

---

## Current Codebase Patterns

### Analysis of Existing Implementation

#### ✅ Strengths

1. **Custom Retry Implementation** (`utils/retry.py`)
   - Zero dependencies
   - Exponential backoff + jitter
   - Async and sync support
   - Clean, maintainable code

2. **Standardized Error Handlers** (`utils/error_handlers.py`)
   - API and agent-level decorators
   - StandardResponse integration
   - Structured logging with context

3. **Widespread `return_exceptions=True`** Usage
   - 16 files use this pattern
   - Good for multi-agent orchestration
   - Prevents cascade failures

4. **Consistent Logging**
   - Structured extra fields
   - Error type classification
   - Context preservation

#### ⚠️ Areas for Improvement

1. **Inconsistent Error Aggregation**
   - Some orchestrators just log errors, others collect them
   - No standardized error severity classification
   - Limited partial success handling

2. **No Circuit Breaker Patterns**
   - Azure API calls lack protection against cascading failures
   - No failure threshold tracking
   - No automatic degradation

3. **Mixed `return_exceptions` Usage**
   - `azure_ai_sre_agent.py` line 1431: `return_exceptions=False`
   - May cause unexpected behavior in some flows

4. **Limited Timeout Management**
   - Some operations lack timeouts
   - No timeout budget management
   - Potential for hanging operations

5. **No Centralized Error Rate Monitoring**
   - Errors logged but not aggregated
   - No alerting on error rate spikes
   - Hard to detect patterns

### Examples from Codebase

#### Good Pattern: EOL Orchestrator Error Handling

```python
# From eol_orchestrator.py line 802
gathered = await asyncio.gather(*tasks, return_exceptions=True)
for outcome in gathered:
    if isinstance(outcome, Exception) or not outcome:
        continue
    local_outcomes.append(outcome)
    result = outcome.get("result")
    confidence = outcome.get("confidence", 0.0)
    # ... process successful results
```

**Why it's good:**
- Uses `return_exceptions=True` ✅
- Checks for exceptions before processing ✅
- Continues with partial results ✅
- Extracts confidence for prioritization ✅

#### Needs Improvement: Azure AI SRE Agent

```python
# From azure_ai_sre_agent.py line 1431
return_exceptions=False,
```

**Issue:** In multi-tool execution context, this can cause first failure to propagate immediately, preventing other tools from completing.

**Suggested fix:**
```python
return_exceptions=True,  # Allow all tools to complete
```

Then handle exceptions in result processing loop.

#### Good Pattern: Executor with Error Collection

```python
# From executor.py line 188-206
parallel_results = await asyncio.gather(
    *[
        self._execute_step(s, completed, skip_destructive=skip_destructive)
        for s in parallel_steps
    ],
    return_exceptions=True,
)
for step, res in zip(parallel_steps, parallel_results):
    if isinstance(res, Exception):
        sr = StepResult(
            step_id=step.step_id,
            tool_name=step.tool_name,
            success=False,
            error=str(res),
        )
    else:
        sr = res
    result.step_results.append(sr)
    completed[step.step_id] = sr
```

**Why it's good:**
- Collects all results and exceptions ✅
- Creates structured error results ✅
- Continues workflow with partial success ✅
- Tracks completion status ✅

---

## Recommendations

### Priority 1: Standardize Error Aggregation (High Impact)

**Action:** Create `utils/error_aggregation.py` with reusable patterns:

```python
# utils/error_aggregation.py
from dataclasses import dataclass
from enum import Enum
from typing import List, Any, Optional

class ErrorSeverity(Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"

@dataclass
class AgentError:
    agent_name: str
    error_type: str
    message: str
    severity: ErrorSeverity
    timestamp: str

@dataclass
class AggregatedResult:
    success: bool
    partial_success: bool
    results: List[Any]
    errors: List[AgentError]

    @property
    def has_critical_errors(self) -> bool:
        return any(e.severity == ErrorSeverity.CRITICAL for e in self.errors)

# Standard aggregation function
async def aggregate_agent_results(
    agents: List[Any],
    operation: str,
) -> AggregatedResult:
    """Standard pattern for agent result aggregation."""
    # Implementation from examples above
```

**Impact:** Consistent error handling across all orchestrators, better observability.

### Priority 2: Add Circuit Breaker for Azure APIs (Medium Impact)

**Action:** Implement custom circuit breaker in `utils/circuit_breaker.py`:

```python
# utils/circuit_breaker.py
class AsyncCircuitBreaker:
    """Circuit breaker for Azure API protection."""
    # Implementation from examples above

# Create breakers for Azure SDK clients
azure_compute_breaker = AsyncCircuitBreaker(
    name="azure_compute",
    config=CircuitBreakerConfig(failure_threshold=5, timeout_seconds=60)
)

azure_monitor_breaker = AsyncCircuitBreaker(
    name="azure_monitor",
    config=CircuitBreakerConfig(failure_threshold=3, timeout_seconds=30)
)
```

**Impact:** Protects against Azure API failures cascading, improves resilience.

### Priority 3: Enhance Retry Implementation (Low Impact)

**Action:** Add optional features to `utils/retry.py`:

- [ ] `on_retry` callback hook
- [ ] `retry_on_result` for value-based retry
- [ ] `RetryStats` for observability
- [ ] `TryAgain` exception for explicit retry

**Impact:** More flexible retry logic without adding dependencies.

### Priority 4: Fix Inconsistent return_exceptions (High Priority)

**Action:** Audit all `asyncio.gather()` calls and standardize:

- Multi-agent orchestration → `return_exceptions=True`
- Critical workflows → `return_exceptions=False` with explicit cancellation
- Document reasoning in code comments

**Files to review:**
- ✅ `agents/eol_orchestrator.py` - Already good
- ✅ `utils/executor.py` - Already good
- ⚠️ `agents/azure_ai_sre_agent.py` - Change to `return_exceptions=True`
- ⚠️ Other orchestrators - Audit and standardize

### Priority 5: Add Error Rate Monitoring (Medium Priority)

**Action:** Implement `utils/error_rate_monitor.py`:

```python
# utils/error_rate_monitor.py
class ErrorRateMonitor:
    """Track error rates across operations."""
    # Implementation from examples above

# Global instance
error_monitor = ErrorRateMonitor(window_minutes=5)
```

Integrate with existing decorators in `utils/error_handlers.py`:

```python
@handle_agent_errors("Agent execution")
async def execute_agent(agent, query):
    operation = f"agent_{agent.name}"
    try:
        result = await agent.process(query)
        error_monitor.record_success(operation)
        return result
    except Exception as e:
        error_monitor.record_error(operation)
        if error_monitor.is_unhealthy(operation):
            logger.critical(f"Agent {agent.name} error rate critical")
        raise
```

---

## Code Examples

### Complete Orchestrator Pattern

```python
# Example: Resilient multi-agent orchestrator with all patterns

from typing import List, Dict, Any
from utils.retry import retry_async
from utils.circuit_breaker import AsyncCircuitBreaker, CircuitBreakerConfig
from utils.error_aggregation import aggregate_agent_results, ErrorSeverity, AgentError
from utils.logger import get_logger

logger = get_logger(__name__)

# Circuit breaker for external dependencies
azure_breaker = AsyncCircuitBreaker(
    name="azure_api",
    config=CircuitBreakerConfig(failure_threshold=5, timeout_seconds=60)
)

class ResilientOrchestrator:
    """
    Orchestrator with complete error handling patterns:
    - Parallel agent execution with return_exceptions=True
    - Circuit breaker for external dependencies
    - Retry with exponential backoff
    - Error aggregation with severity
    - Graceful degradation with fallbacks
    - Timeout management
    """

    def __init__(self, agents: List[Agent]):
        self.agents = agents
        self.timeout_per_agent = 10.0
        self.total_timeout = 30.0

    async def execute(self, query: str) -> Dict[str, Any]:
        """Execute all agents with full error handling."""

        # Step 1: Execute agents in parallel with timeouts
        tasks = []
        for agent in self.agents:
            task = asyncio.create_task(
                self._execute_agent_with_protection(agent, query)
            )
            tasks.append(task)

        # Step 2: Gather with return_exceptions for partial success
        results = await asyncio.wait_for(
            asyncio.gather(*tasks, return_exceptions=True),
            timeout=self.total_timeout
        )

        # Step 3: Aggregate results and errors
        aggregated = await self._aggregate_results(results)

        # Step 4: Apply fallbacks if needed
        if aggregated.has_critical_errors:
            fallback = await self._get_fallback_result(query)
            return fallback

        return {
            "success": aggregated.success,
            "partial": aggregated.partial_success,
            "results": aggregated.results,
            "errors": [
                {
                    "agent": e.agent_name,
                    "type": e.error_type,
                    "severity": e.severity.value,
                    "message": e.message,
                }
                for e in aggregated.errors
            ],
            "metadata": {
                "total_agents": len(self.agents),
                "successful": len(aggregated.results),
                "failed": len(aggregated.errors),
            }
        }

    @retry_async(retries=3, initial_delay=1.0, max_delay=10.0)
    async def _execute_agent_with_protection(
        self,
        agent: Agent,
        query: str
    ) -> Dict[str, Any]:
        """Execute single agent with timeout, retry, and circuit breaker."""

        # Apply circuit breaker if agent uses external APIs
        if agent.uses_external_api:
            if not azure_breaker.should_allow_request():
                raise Exception("Circuit breaker OPEN")

        try:
            # Execute with timeout
            result = await asyncio.wait_for(
                agent.process(query),
                timeout=self.timeout_per_agent
            )

            if agent.uses_external_api:
                azure_breaker.record_success()

            return {
                "agent_name": agent.name,
                "result": result,
                "confidence": result.get("confidence", 0.5),
            }

        except asyncio.TimeoutError:
            logger.warning(
                f"Agent {agent.name} timed out after {self.timeout_per_agent}s"
            )
            if agent.uses_external_api:
                azure_breaker.record_failure()
            raise

        except Exception as e:
            logger.error(f"Agent {agent.name} failed: {e}")
            if agent.uses_external_api:
                azure_breaker.record_failure()
            raise

    async def _aggregate_results(
        self,
        results: List[Any]
    ) -> AggregatedResult:
        """Aggregate results and classify errors."""

        successful = []
        errors = []

        for idx, result in enumerate(results):
            agent = self.agents[idx]

            if isinstance(result, Exception):
                severity = self._classify_error_severity(result, agent)

                error = AgentError(
                    agent_name=agent.name,
                    error_type=type(result).__name__,
                    message=str(result),
                    severity=severity,
                    timestamp=datetime.utcnow().isoformat(),
                )
                errors.append(error)
            else:
                successful.append(result)

        return AggregatedResult(
            success=len(successful) > 0 and len(errors) == 0,
            partial_success=len(successful) > 0 and len(errors) > 0,
            results=successful,
            errors=errors,
        )

    def _classify_error_severity(
        self,
        error: Exception,
        agent: Agent
    ) -> ErrorSeverity:
        """Classify error severity based on type and agent criticality."""

        if agent.is_critical:
            return ErrorSeverity.CRITICAL

        if isinstance(error, asyncio.TimeoutError):
            return ErrorSeverity.MEDIUM

        if "azure" in type(error).__module__.lower():
            return ErrorSeverity.HIGH

        return ErrorSeverity.LOW

    async def _get_fallback_result(self, query: str) -> Dict[str, Any]:
        """Get fallback result when critical errors occur."""

        # Try cache first
        cached = await self.cache.get(f"query:{query}")
        if cached:
            logger.info("Using cached result as fallback")
            return {
                "success": True,
                "result": cached,
                "fallback": True,
                "source": "cache",
            }

        # Return minimal safe response
        return {
            "success": False,
            "message": "Service temporarily unavailable",
            "fallback": True,
        }
```

---

## Summary

### Key Takeaways

1. **`asyncio.gather(return_exceptions=True)` is essential** for multi-agent systems
2. **Circuit breakers protect external dependencies**, not internal agents
3. **Error aggregation requires structure** - use dataclasses and severity classification
4. **Graceful degradation needs fallback chains** and timeout management
5. **Custom retry implementation is sufficient** - don't add tenacity unless needed
6. **Current codebase has good foundations** - focus on standardization and consistency

### Implementation Priorities

1. ✅ **Standardize error aggregation** across orchestrators
2. ✅ **Add circuit breakers** for Azure API calls
3. ✅ **Fix inconsistent `return_exceptions`** usage
4. ✅ **Enhance retry implementation** with hooks and stats
5. ✅ **Add error rate monitoring** for observability

### Best Practices Checklist

- [ ] Use `return_exceptions=True` for multi-agent orchestration
- [ ] Apply circuit breakers to external API calls
- [ ] Classify error severity (CRITICAL, HIGH, MEDIUM, LOW)
- [ ] Implement fallback chains for graceful degradation
- [ ] Add timeouts to all async operations
- [ ] Log structured error context with extra fields
- [ ] Return partial success when possible
- [ ] Monitor error rates for health checks
- [ ] Use retry with exponential backoff + jitter
- [ ] Document error handling strategy in code comments

---

**Research compiled by:** Claude Code
**Date:** 2026-02-27
**Version:** 1.0

**References:**
- Python asyncio documentation (docs.python.org)
- tenacity documentation (tenacity.readthedocs.io)
- FastAPI error handling guide (fastapi.tiangolo.com)
- Current codebase: gcc-demo/app/agentic/eol/
