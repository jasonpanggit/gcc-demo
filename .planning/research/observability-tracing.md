# Observability & Distributed Tracing Research

**Date:** 2026-02-27
**Focus:** Correlation ID propagation, structured logging, OpenTelemetry integration for distributed systems

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Correlation ID Propagation Patterns](#correlation-id-propagation-patterns)
3. [Structured Logging Best Practices](#structured-logging-best-practices)
4. [OpenTelemetry Integration](#opentelemetry-integration)
5. [Request Context Management in Async Python](#request-context-management-in-async-python)
6. [Production Logging Standards](#production-logging-standards)
7. [Implementation Recommendations](#implementation-recommendations)
8. [Reference Architecture](#reference-architecture)

---

## Executive Summary

Modern distributed systems require comprehensive observability to trace requests across service boundaries, debug production issues, and monitor system health. This research covers:

- **Correlation IDs**: Unique identifiers that propagate through the entire request lifecycle
- **Structured Logging**: Machine-parseable logs with consistent format and rich context
- **OpenTelemetry**: Industry-standard distributed tracing and instrumentation
- **Context Propagation**: Managing request-scoped data across async boundaries in Python

**Key Findings:**
- Use FastAPI middleware + Python `contextvars` for correlation ID propagation
- Adopt `structlog` for structured logging with JSON output
- Integrate OpenTelemetry for distributed tracing and metrics
- Leverage `contextvars` for async-safe request context management
- Implement consistent log levels, formats, and metadata standards

---

## Correlation ID Propagation Patterns

### What is a Correlation ID?

A **correlation ID** (also called request ID or trace ID) is a unique identifier attached to each request that:
- Travels through all services handling the request
- Appears in all logs related to that request
- Enables end-to-end request tracing
- Simplifies debugging and root cause analysis

### FastAPI Middleware Implementation

FastAPI is ASGI-based (via Starlette) and supports multiple middleware patterns for correlation ID propagation.

#### Pattern 1: HTTP Middleware Function (Recommended)

**Best for:** Simple HTTP request/response scenarios

```python
from fastapi import FastAPI, Request
import uuid

app = FastAPI()

@app.middleware("http")
async def add_correlation_id(request: Request, call_next):
    # Extract or generate correlation ID
    correlation_id = request.headers.get("x-correlation-id") or str(uuid.uuid4())

    # Store in request state for handler access
    request.state.correlation_id = correlation_id

    # Process request
    response = await call_next(request)

    # Add to response headers
    response.headers["X-Correlation-ID"] = correlation_id

    return response
```

**Advantages:**
- Simple and readable
- Easy to test and debug
- Works for most HTTP use cases
- Direct access via `request.state.correlation_id`

#### Pattern 2: Class-Based Middleware

**Best for:** Reusable middleware with configuration options

```python
from fastapi import FastAPI, Request
from starlette.middleware.base import BaseHTTPMiddleware
import uuid

class CorrelationIDMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, header_name: str = "x-correlation-id"):
        super().__init__(app)
        self.header_name = header_name

    async def dispatch(self, request: Request, call_next):
        correlation_id = request.headers.get(self.header_name) or str(uuid.uuid4())
        request.state.correlation_id = correlation_id

        response = await call_next(request)
        response.headers[self.header_name.title().replace("-", "-")] = correlation_id

        return response

app = FastAPI()
app.add_middleware(CorrelationIDMiddleware, header_name="x-correlation-id")
```

**Advantages:**
- Configurable and reusable
- Clean separation of concerns
- Easy to test independently
- Can be packaged as a library

#### Pattern 3: ASGI Middleware (Advanced)

**Best for:** Low-level control, WebSocket support, streaming responses

```python
import typing
import uuid
from typing import Callable

class ASGICorrelationIDMiddleware:
    def __init__(self, app: Callable):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            # Pass through non-HTTP (WebSocket, etc.)
            await self.app(scope, receive, send)
            return

        # Extract correlation ID from headers
        correlation_id = None
        for name, value in scope.get("headers", []):
            if name.lower() == b"x-correlation-id":
                correlation_id = value.decode()
                break

        if not correlation_id:
            correlation_id = str(uuid.uuid4())

        # Store in scope
        scope.setdefault("state", {})["correlation_id"] = correlation_id

        # Wrap send to inject header on response
        async def send_wrapper(event):
            if event["type"] == "http.response.start":
                headers = list(event.get("headers", []))
                headers.append((b"x-correlation-id", correlation_id.encode()))
                event["headers"] = headers
            await send(event)

        await self.app(scope, receive, send_wrapper)

app = FastAPI()
app.add_middleware(ASGICorrelationIDMiddleware)
```

**Advantages:**
- Full ASGI-level control
- Works with WebSockets
- Can intercept streaming responses
- Maximum flexibility

### Integration with Context Variables

To make correlation IDs available throughout your application (including background tasks, logging, and nested function calls), combine middleware with Python's `contextvars`:

```python
from contextvars import ContextVar
from fastapi import FastAPI, Request
import uuid

# Module-level context variable
correlation_id_var: ContextVar[str] = ContextVar("correlation_id", default="")

@app.middleware("http")
async def correlation_id_middleware(request: Request, call_next):
    correlation_id = request.headers.get("x-correlation-id") or str(uuid.uuid4())

    # Set in context variable (auto-propagates in async tasks)
    correlation_id_var.set(correlation_id)

    # Also store in request state for direct access
    request.state.correlation_id = correlation_id

    response = await call_next(request)
    response.headers["X-Correlation-ID"] = correlation_id

    return response

# Usage in any function (even deeply nested)
def some_helper_function():
    current_correlation_id = correlation_id_var.get()
    logger.info("Processing", correlation_id=current_correlation_id)
```

### Best Practices

1. **Header Naming**: Use standardized headers
   - `X-Correlation-ID` or `X-Request-ID` for correlation tracking
   - `X-Session-ID` for user session tracking
   - `traceparent` for W3C Trace Context (OpenTelemetry standard)

2. **ID Generation**: Use UUID4 for uniqueness
   ```python
   import uuid
   correlation_id = str(uuid.uuid4())  # e.g., "550e8400-e29b-41d4-a716-446655440000"
   ```

3. **Propagation Strategy**:
   - Accept incoming correlation ID from client/upstream
   - Generate new ID only if missing
   - Always include in outgoing requests to downstream services
   - Always include in response headers

4. **Storage Strategy**:
   - Use `request.state` for request-scoped access
   - Use `contextvars` for deep propagation across async boundaries
   - Avoid thread-local storage (not async-safe)

5. **Middleware Order**:
   - Add correlation ID middleware early in the chain
   - Ensure it runs before logging and tracing middleware
   - Remember: middleware added first runs outermost

---

## Structured Logging Best Practices

### Why Structured Logging?

Traditional logging outputs unstructured strings:
```
2026-02-27 10:15:23 INFO User john logged in from 192.168.1.1
```

Structured logging outputs machine-parseable JSON:
```json
{
  "timestamp": "2026-02-27T10:15:23.456Z",
  "level": "info",
  "message": "User logged in",
  "user": "john",
  "source_ip": "192.168.1.1",
  "correlation_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

**Benefits:**
- Easy to parse and query
- Rich contextual metadata
- Consistent format across services
- Better integration with log aggregation tools (ELK, Splunk, DataDog)

### Structlog: Python's Leading Structured Logging Library

**Why structlog?**
- Built around immutable, composable processors
- Native async support
- Excellent performance (configurable caching)
- Flexible output formats (JSON, logfmt, console)
- Seamless integration with stdlib `logging`

#### Basic Setup

```python
import structlog

# Configure structlog
structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,  # Merge context variables
        structlog.stdlib.filter_by_level,          # Filter by log level
        structlog.stdlib.add_logger_name,          # Add logger name
        structlog.stdlib.add_log_level,            # Add log level
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer()        # Output as JSON
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

# Get a logger
logger = structlog.get_logger(__name__)

# Log with context
logger.info("user_logged_in", user_id="12345", ip_address="192.168.1.1")
```

#### Integration with FastAPI

```python
import structlog
from fastapi import FastAPI, Request
from contextvars import ContextVar

# Context variable for correlation ID
correlation_id_var: ContextVar[str] = ContextVar("correlation_id", default="")

# Configure structlog to use contextvars
structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,  # Critical: merges contextvar data
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.JSONRenderer()
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

app = FastAPI()
logger = structlog.get_logger(__name__)

@app.middleware("http")
async def logging_middleware(request: Request, call_next):
    import uuid

    correlation_id = request.headers.get("x-correlation-id") or str(uuid.uuid4())

    # Clear previous context and bind new values
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(
        correlation_id=correlation_id,
        method=request.method,
        path=request.url.path,
        client_ip=request.client.host if request.client else "unknown"
    )

    # Log request
    logger.info("request_started")

    # Process request
    response = await call_next(request)

    # Log response
    logger.info("request_completed", status_code=response.status_code)

    response.headers["X-Correlation-ID"] = correlation_id
    return response

@app.get("/users/{user_id}")
async def get_user(user_id: str):
    # Correlation ID automatically included in logs!
    logger.info("fetching_user", user_id=user_id)

    # ... business logic ...

    logger.info("user_fetched", user_id=user_id)
    return {"user_id": user_id}
```

### Four Integration Patterns with stdlib logging

#### Pattern 1: Don't Integrate (Parallel Systems)
- Keep structlog and stdlib logging separate
- Use structlog for new code
- Leave existing stdlib logging as-is
- Both output to same destination

**Use when:** Migrating legacy applications gradually

#### Pattern 2: Render in Structlog (Recommended)
- Structlog produces final formatted output
- Forward to stdlib logging for handler management
- Stdlib acts as transport layer only

```python
import logging
import structlog

# Configure stdlib logging handlers
logging.basicConfig(
    format="%(message)s",  # structlog already formatted the message
    level=logging.INFO,
    handlers=[logging.StreamHandler()]
)

# Configure structlog
structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.format_exc_info,
        structlog.processors.JSONRenderer(),  # Final rendering
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)
```

**Advantages:**
- Simple setup
- Structlog controls format
- Works with existing logging handlers

#### Pattern 3: Build Event Dict, Format via Logging
- Structlog builds event dictionary
- Pass to stdlib logging as `extra` dict
- Stdlib formatter renders final output

```python
import structlog

structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.stdlib.render_to_log_kwargs,  # Pass to stdlib
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    logger_factory=structlog.stdlib.LoggerFactory(),
)
```

**Advantages:**
- Leverage existing stdlib formatters
- Works with third-party logging tools
- Gradual migration path

#### Pattern 4: ProcessorFormatter (Most Flexible)
- Use structlog processors within stdlib's `Formatter`
- Unified formatting for both structlog and stdlib logs

```python
import logging
import structlog

# Configure structlog processors
shared_processors = [
    structlog.contextvars.merge_contextvars,
    structlog.stdlib.add_logger_name,
    structlog.stdlib.add_log_level,
    structlog.processors.TimeStamper(fmt="iso"),
]

# Stdlib handler with ProcessorFormatter
handler = logging.StreamHandler()
handler.setFormatter(
    structlog.stdlib.ProcessorFormatter(
        processor=structlog.processors.JSONRenderer(),
        foreign_pre_chain=shared_processors,
    )
)

logging.basicConfig(handlers=[handler], level=logging.INFO)

# Configure structlog
structlog.configure(
    processors=shared_processors + [
        structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)
```

**Advantages:**
- Single source of formatting logic
- Works for both structlog and stdlib logs
- Consistent output format

### Contextvars Integration with Structlog

Structlog has native support for Python's `contextvars` module, enabling automatic context propagation.

```python
import structlog
from contextvars import ContextVar

# Configure structlog to merge contextvars
structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,  # MUST be first!
        # ... other processors ...
    ]
)

# In middleware or request handler
structlog.contextvars.clear_contextvars()  # Clear previous request context
structlog.contextvars.bind_contextvars(
    correlation_id="550e8400-e29b-41d4-a716-446655440000",
    user_id="user123",
    tenant_id="tenant456"
)

# Anywhere in your code (even nested functions)
logger = structlog.get_logger()
logger.info("processing_request")  # Automatically includes correlation_id, user_id, tenant_id
```

**Key Functions:**
- `merge_contextvars()`: Processor that merges context into log events
- `clear_contextvars()`: Clear all context (call at request start)
- `bind_contextvars(**kwargs)`: Add key-value pairs to context
- `unbind_contextvars(*keys)`: Remove keys from context
- `get_contextvars()`: Get current context dict

**Context Manager Pattern:**
```python
from structlog.contextvars import bound_contextvars

# Temporarily add context
with bound_contextvars(operation="database_query", table="users"):
    logger.info("query_started")  # Includes operation and table
    # ... perform query ...
    logger.info("query_completed")  # Still includes operation and table
# Context automatically removed after block
```

### Log Levels and When to Use Them

| Level | When to Use | Examples |
|-------|-------------|----------|
| **DEBUG** | Detailed diagnostic info for developers | Variable values, function entry/exit, loop iterations |
| **INFO** | General informational messages | Request started/completed, user actions, system state changes |
| **WARNING** | Something unexpected but recoverable | Deprecated API used, retry attempted, fallback activated |
| **ERROR** | Error that prevented an operation | Database connection failed, validation error, external API error |
| **CRITICAL** | Severe error causing system instability | Out of memory, data corruption, security breach |

**Best Practices:**
- Use INFO for normal application flow
- Use WARNING for recoverable issues
- Use ERROR for failures that need attention
- Avoid DEBUG in production (performance impact)
- Never log sensitive data (passwords, tokens, PII)

### Async Logging Considerations

**Important:** Structlog supports async logging but with caveats:

```python
import structlog

# Configure async-aware logger
structlog.configure(
    wrapper_class=structlog.stdlib.AsyncBoundLogger,  # Async wrapper
    # ... other configuration ...
)

# Usage
logger = structlog.get_logger()

# All methods are now async
await logger.ainfo("async_log_message", user_id="123")
await logger.aerror("async_error", error="something went wrong")
```

**When to use async logging:**
- When logging to async I/O destinations (remote endpoints, async databases)
- When using async log processors

**When NOT to use:**
- For simple file/stdout logging (sync is faster)
- When compatibility with sync code is needed

**Hybrid approach (recommended):**
- Use sync logging for most cases
- Use async logging only for I/O-heavy log destinations

---

## OpenTelemetry Integration

### What is OpenTelemetry?

**OpenTelemetry** (OTel) is an observability framework providing:
- **Traces**: Request flow through distributed services
- **Metrics**: Quantitative measurements (latency, request rate, error rate)
- **Logs**: Detailed event records (increasingly integrated with traces)

**Key Components:**
- **API**: Interface for instrumentation
- **SDK**: Implementation of the API
- **Instrumentation**: Auto and manual code instrumentation
- **Exporters**: Send data to backends (Jaeger, Zipkin, Prometheus, DataDog)

### Why OpenTelemetry for FastAPI?

1. **Automatic Instrumentation**: Auto-trace HTTP requests with zero code changes
2. **Context Propagation**: Traces span across services automatically
3. **Rich Metadata**: Capture request details, headers, status codes
4. **Backend Agnostic**: Export to any observability platform
5. **Industry Standard**: W3C Trace Context propagation

### FastAPI Instrumentation Setup

#### Installation

```bash
pip install opentelemetry-api
pip install opentelemetry-sdk
pip install opentelemetry-instrumentation-fastapi
pip install opentelemetry-instrumentation-logging
pip install opentelemetry-exporter-otlp  # For OTLP export (recommended)
```

#### Basic Auto-Instrumentation

```python
from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

# Set up tracing
trace.set_tracer_provider(TracerProvider())
tracer_provider = trace.get_tracer_provider()

# Add exporter (console for demo, use OTLP for production)
tracer_provider.add_span_processor(
    BatchSpanProcessor(ConsoleSpanExporter())
)

# Create FastAPI app
app = FastAPI()

# Instrument FastAPI (automatically traces all requests)
FastAPIInstrumentor.instrument_app(app)

@app.get("/users/{user_id}")
async def get_user(user_id: str):
    # This request is automatically traced!
    return {"user_id": user_id}
```

#### Production Setup with OTLP Exporter

```python
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource, SERVICE_NAME
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

# Define service resource
resource = Resource(attributes={
    SERVICE_NAME: "eol-agent-service",
    "environment": "production",
    "version": "1.0.0"
})

# Set up tracer provider
tracer_provider = TracerProvider(resource=resource)

# Configure OTLP exporter (send to collector/backend)
otlp_exporter = OTLPSpanExporter(
    endpoint="http://otel-collector:4317",  # Your collector endpoint
    insecure=True  # Use TLS in production
)

tracer_provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
trace.set_tracer_provider(tracer_provider)

# Instrument FastAPI
app = FastAPI()
FastAPIInstrumentor.instrument_app(app)
```

### Manual Span Creation

For custom tracing within your application:

```python
from opentelemetry import trace

tracer = trace.get_tracer(__name__)

@app.get("/process")
async def process_data():
    # Create a custom span
    with tracer.start_as_current_span("process_data_operation") as span:
        # Add attributes to span
        span.set_attribute("user_id", "12345")
        span.set_attribute("operation", "data_processing")

        # Simulate work
        result = await some_async_operation()

        # Add event to span
        span.add_event("processing_completed", attributes={"records": 100})

        return {"result": result}

async def some_async_operation():
    # Nested span
    with tracer.start_as_current_span("database_query") as span:
        span.set_attribute("db.system", "cosmosdb")
        span.set_attribute("db.operation", "select")
        # ... perform query ...
        return "data"
```

### Context Propagation Across Services

OpenTelemetry automatically propagates trace context via HTTP headers using W3C Trace Context standard:

**Outgoing Request (Client):**
```python
import httpx
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

# Instrument httpx client
HTTPXClientInstrumentor().instrument()

async with httpx.AsyncClient() as client:
    # Trace context automatically added to headers!
    response = await client.get("http://downstream-service/api/resource")
```

**Incoming Request (Server):**
```python
# FastAPI automatically extracts trace context from headers
# and continues the trace!

@app.get("/api/resource")
async def resource():
    # This span is automatically linked to parent trace
    return {"data": "value"}
```

**Headers Propagated:**
- `traceparent`: Contains trace-id, span-id, trace-flags
- `tracestate`: Vendor-specific trace state

### Integration with Correlation IDs

You can link OpenTelemetry trace IDs with correlation IDs:

```python
from opentelemetry import trace
import structlog

logger = structlog.get_logger()

@app.middleware("http")
async def tracing_middleware(request: Request, call_next):
    # Get current span
    span = trace.get_current_span()
    span_context = span.get_span_context()

    # Extract trace and span IDs
    trace_id = format(span_context.trace_id, '032x') if span_context.is_valid else None
    span_id = format(span_context.span_id, '016x') if span_context.is_valid else None

    # Bind to logging context
    structlog.contextvars.bind_contextvars(
        trace_id=trace_id,
        span_id=span_id
    )

    response = await call_next(request)
    return response
```

### Common Exporters

| Exporter | Use Case | Installation |
|----------|----------|--------------|
| **OTLP** | Standard protocol, supports all backends | `opentelemetry-exporter-otlp` |
| **Jaeger** | Open-source tracing backend | `opentelemetry-exporter-jaeger` |
| **Zipkin** | Open-source tracing backend | `opentelemetry-exporter-zipkin` |
| **Console** | Development/debugging | Built-in |
| **Azure Monitor** | Azure Application Insights | `azure-monitor-opentelemetry-exporter` |

### Best Practices

1. **Use OTLP Exporter**: Industry standard, future-proof
2. **Batch Span Processing**: Use `BatchSpanProcessor` for performance
3. **Resource Attributes**: Always set service name and environment
4. **Sample Production Traffic**: Use sampling to reduce overhead
5. **Instrument External Calls**: Use auto-instrumentation for HTTP, DB, Redis
6. **Add Custom Spans**: For business-critical operations
7. **Set Span Attributes**: Add context (user_id, tenant_id, operation type)
8. **Handle Errors**: Record exceptions in spans

```python
with tracer.start_as_current_span("operation") as span:
    try:
        # ... operation ...
    except Exception as e:
        span.record_exception(e)
        span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
        raise
```

---

## Request Context Management in Async Python

### Why Context Management Matters

In asynchronous Python applications:
- Multiple requests are processed concurrently
- Request-specific data (user, correlation ID, session) must not leak between requests
- Context must propagate across `await` boundaries
- Traditional thread-local storage doesn't work

### Python's contextvars Module

**Key Concepts:**

1. **ContextVar**: Context-local variable (like thread-local but async-safe)
2. **Context**: Immutable snapshot of all context variables
3. **Token**: Handle for restoring previous values

#### Basic Usage

```python
from contextvars import ContextVar

# Declare context variable at module level
request_id_var: ContextVar[str] = ContextVar("request_id", default="")

# Set value (returns token for restoration)
token = request_id_var.set("req-12345")

# Get value
current_request_id = request_id_var.get()  # "req-12345"

# Reset to previous value
request_id_var.reset(token)
```

#### Context Variable Propagation

**Automatic propagation in asyncio:**

```python
import asyncio
from contextvars import ContextVar

user_id_var: ContextVar[str] = ContextVar("user_id")

async def handler():
    user_id_var.set("user-123")
    await process_request()  # Context propagates automatically

async def process_request():
    # Context available here!
    user_id = user_id_var.get()
    print(f"Processing for {user_id}")  # "Processing for user-123"

asyncio.run(handler())
```

**Isolation between tasks:**

```python
async def task_a():
    user_id_var.set("user-A")
    await asyncio.sleep(0.1)
    print(f"Task A: {user_id_var.get()}")  # Always "user-A"

async def task_b():
    user_id_var.set("user-B")
    await asyncio.sleep(0.1)
    print(f"Task B: {user_id_var.get()}")  # Always "user-B"

# Run concurrently - contexts don't interfere
await asyncio.gather(task_a(), task_b())
```

### FastAPI Request Context Pattern

**Complete implementation:**

```python
from contextvars import ContextVar
from fastapi import FastAPI, Request, Depends
from typing import Optional
import uuid

# Context variables
correlation_id_var: ContextVar[str] = ContextVar("correlation_id", default="")
user_id_var: ContextVar[Optional[str]] = ContextVar("user_id", default=None)
tenant_id_var: ContextVar[Optional[str]] = ContextVar("tenant_id", default=None)

app = FastAPI()

@app.middleware("http")
async def context_middleware(request: Request, call_next):
    # Generate/extract correlation ID
    correlation_id = request.headers.get("x-correlation-id") or str(uuid.uuid4())
    correlation_id_var.set(correlation_id)

    # Extract user context (from auth)
    user_id = request.headers.get("x-user-id")
    if user_id:
        user_id_var.set(user_id)

    # Extract tenant context (for multi-tenancy)
    tenant_id = request.headers.get("x-tenant-id")
    if tenant_id:
        tenant_id_var.set(tenant_id)

    # Process request
    response = await call_next(request)

    # Add correlation ID to response
    response.headers["X-Correlation-ID"] = correlation_id

    return response

# Helper functions to access context
def get_correlation_id() -> str:
    return correlation_id_var.get()

def get_user_id() -> Optional[str]:
    return user_id_var.get()

def get_tenant_id() -> Optional[str]:
    return tenant_id_var.get()

# Use in any handler or dependency
@app.get("/api/resource")
async def get_resource():
    correlation_id = get_correlation_id()
    user_id = get_user_id()

    logger.info(
        "fetching_resource",
        correlation_id=correlation_id,
        user_id=user_id
    )

    # Context available in nested calls!
    result = await fetch_from_database()

    return {"result": result}

async def fetch_from_database():
    # Context still available here
    user_id = get_user_id()
    # ... query database filtered by user_id ...
```

### Token-Based Context Management

**Temporarily override context:**

```python
from contextvars import ContextVar

user_id_var: ContextVar[str] = ContextVar("user_id")

async def admin_operation():
    # Save current context
    token = user_id_var.set("admin-user")

    try:
        # Perform admin operation with admin context
        await sensitive_operation()
    finally:
        # Restore previous context
        user_id_var.reset(token)

# Python 3.14+ context manager support
async def admin_operation_cm():
    with user_id_var.set("admin-user"):
        # Admin context active here
        await sensitive_operation()
    # Original context automatically restored
```

### Context Copying for Background Tasks

**Problem:** Background tasks don't automatically inherit context

**Solution:** Copy context explicitly

```python
import asyncio
from contextvars import copy_context

async def trigger_background_task():
    user_id_var.set("user-123")

    # Copy current context
    ctx = copy_context()

    # Run in background with copied context
    asyncio.create_task(ctx.run(background_work))

async def background_work():
    # Context available here!
    user_id = user_id_var.get()
    print(f"Background task for {user_id}")
```

**FastAPI BackgroundTasks pattern:**

```python
from fastapi import BackgroundTasks
from contextvars import copy_context

@app.post("/process")
async def process_data(background_tasks: BackgroundTasks):
    user_id_var.set("user-123")

    # Capture context
    ctx = copy_context()

    # Schedule with context
    background_tasks.add_task(ctx.run, process_in_background)

    return {"status": "processing"}

async def process_in_background():
    # Context available!
    user_id = user_id_var.get()
    # ... perform background processing ...
```

### Best Practices

1. **Declare ContextVars at Module Level**
   ```python
   # Good: Module-level declaration
   user_id_var: ContextVar[str] = ContextVar("user_id")

   # Bad: Inside function (memory leak risk)
   def bad_example():
       var = ContextVar("temp")  # Don't do this
   ```

2. **Use Type Hints**
   ```python
   from typing import Optional

   user_id_var: ContextVar[Optional[str]] = ContextVar("user_id", default=None)
   ```

3. **Provide Defaults**
   ```python
   # With default
   correlation_id_var: ContextVar[str] = ContextVar("correlation_id", default="")

   # Access safely
   correlation_id = correlation_id_var.get()  # Never raises
   ```

4. **Clear Context Between Requests** (for structlog)
   ```python
   @app.middleware("http")
   async def clear_context_middleware(request: Request, call_next):
       structlog.contextvars.clear_contextvars()  # Clear previous request
       # ... set new context ...
       response = await call_next(request)
       return response
   ```

5. **Use Context Managers for Temporary Changes**
   ```python
   # Good: Automatic cleanup
   with user_id_var.set("temp-user"):
       await operation()

   # Avoid: Manual reset (error-prone)
   token = user_id_var.set("temp-user")
   try:
       await operation()
   finally:
       user_id_var.reset(token)
   ```

6. **Copy Context for Threads**
   ```python
   import threading
   from contextvars import copy_context

   def sync_operation():
       ctx = copy_context()
       thread = threading.Thread(target=ctx.run, args=(worker_func,))
       thread.start()
   ```

---

## Production Logging Standards

### Log Format Standardization

**Recommended JSON Schema:**

```json
{
  "timestamp": "2026-02-27T10:15:23.456789Z",
  "level": "info",
  "logger": "eol.agents.sre_orchestrator",
  "message": "Processing patch request",
  "correlation_id": "550e8400-e29b-41d4-a716-446655440000",
  "trace_id": "0af7651916cd43dd8448eb211c80319c",
  "span_id": "b7ad6b7169203331",
  "user_id": "user-12345",
  "tenant_id": "tenant-456",
  "service": "eol-agent-service",
  "environment": "production",
  "version": "1.2.3",
  "host": "pod-abc123",
  "process_id": 42,
  "thread_name": "MainThread",
  "module": "sre_orchestrator",
  "function": "process_patch",
  "line": 145,
  "extra": {
    "patch_id": "patch-789",
    "vm_count": 5,
    "duration_ms": 1234
  }
}
```

### Required Fields

| Field | Type | Description | Source |
|-------|------|-------------|--------|
| `timestamp` | ISO 8601 | When event occurred | Automatic |
| `level` | string | Log level | Logger |
| `logger` | string | Logger name | `__name__` |
| `message` | string | Human-readable message | Log call |
| `correlation_id` | string | Request correlation ID | Middleware |
| `service` | string | Service name | Config |
| `environment` | string | Deployment environment | Config |
| `version` | string | Application version | Config |

### Recommended Fields

| Field | Type | Description |
|-------|------|-------------|
| `trace_id` | string | OpenTelemetry trace ID |
| `span_id` | string | OpenTelemetry span ID |
| `user_id` | string | Authenticated user |
| `tenant_id` | string | Multi-tenancy identifier |
| `host` | string | Hostname/pod name |
| `process_id` | int | OS process ID |
| `module` | string | Python module name |
| `function` | string | Function name |
| `line` | int | Line number |

### Complete Production Configuration

```python
import logging
import structlog
import sys
from contextvars import ContextVar

# Context variables
correlation_id_var: ContextVar[str] = ContextVar("correlation_id", default="")
user_id_var: ContextVar[str] = ContextVar("user_id", default="")
tenant_id_var: ContextVar[str] = ContextVar("tenant_id", default="")

# Application metadata
SERVICE_NAME = "eol-agent-service"
ENVIRONMENT = "production"  # from env var
VERSION = "1.2.3"  # from package metadata
HOST = "pod-abc123"  # from env var

def add_app_context(logger, method_name, event_dict):
    """Add application-level context to all logs"""
    event_dict["service"] = SERVICE_NAME
    event_dict["environment"] = ENVIRONMENT
    event_dict["version"] = VERSION
    event_dict["host"] = HOST
    return event_dict

# Configure stdlib logging
logging.basicConfig(
    format="%(message)s",
    stream=sys.stdout,
    level=logging.INFO,
)

# Configure structlog
structlog.configure(
    processors=[
        # 1. Merge context variables (correlation_id, user_id, etc.)
        structlog.contextvars.merge_contextvars,

        # 2. Filter by log level
        structlog.stdlib.filter_by_level,

        # 3. Add logger name
        structlog.stdlib.add_logger_name,

        # 4. Add log level
        structlog.stdlib.add_log_level,

        # 5. Add timestamp
        structlog.processors.TimeStamper(fmt="iso", utc=True),

        # 6. Add caller info (module, function, line)
        structlog.processors.CallsiteParameterAdder(
            parameters=[
                structlog.processors.CallsiteParameter.MODULE,
                structlog.processors.CallsiteParameter.FUNC_NAME,
                structlog.processors.CallsiteParameter.LINENO,
            ]
        ),

        # 7. Add application context
        add_app_context,

        # 8. Add stack info for errors
        structlog.processors.StackInfoRenderer(),

        # 9. Format exceptions
        structlog.processors.format_exc_info,

        # 10. Decode unicode
        structlog.processors.UnicodeDecoder(),

        # 11. Render as JSON
        structlog.processors.JSONRenderer(sort_keys=True),
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

# Get logger
logger = structlog.get_logger(__name__)

# Usage
logger.info(
    "processing_patch_request",
    patch_id="patch-789",
    vm_count=5,
    severity="critical"
)
```

### Sensitive Data Handling

**Never log:**
- Passwords
- API keys / tokens
- Credit card numbers
- Social security numbers
- Personal health information
- Session IDs (in production)

**Redaction processor:**

```python
import structlog

def redact_sensitive_data(logger, method_name, event_dict):
    """Redact sensitive fields from logs"""
    sensitive_fields = ["password", "token", "api_key", "secret", "ssn"]

    for field in sensitive_fields:
        if field in event_dict:
            event_dict[field] = "***REDACTED***"

    return event_dict

# Add to processor chain (early)
structlog.configure(
    processors=[
        redact_sensitive_data,  # Add early in chain
        # ... other processors ...
    ]
)
```

### Log Retention and Rotation

**Recommendations:**
- **Development**: 7 days, local files
- **Staging**: 30 days, centralized logging
- **Production**: 90+ days (compliance dependent), centralized logging

**File rotation (local development):**

```python
import logging
from logging.handlers import RotatingFileHandler

handler = RotatingFileHandler(
    "app.log",
    maxBytes=10 * 1024 * 1024,  # 10 MB
    backupCount=5
)

logging.basicConfig(handlers=[handler])
```

**Production: Use centralized logging**
- Azure Monitor / Application Insights
- ELK Stack (Elasticsearch, Logstash, Kibana)
- Splunk
- DataDog
- CloudWatch Logs

### Performance Considerations

1. **Use log level filtering early**
   ```python
   structlog.stdlib.filter_by_level,  # Put this early in processor chain
   ```

2. **Cache loggers**
   ```python
   cache_logger_on_first_use=True,  # Avoid reconfig overhead
   ```

3. **Avoid expensive operations in hot paths**
   ```python
   # Bad: Expensive serialization
   logger.info("data", large_object=huge_dict)

   # Good: Log summary only
   logger.info("data_processed", record_count=len(huge_dict))
   ```

4. **Use async logging for high-throughput**
   ```python
   from logging.handlers import QueueHandler, QueueListener
   import queue

   log_queue = queue.Queue()
   queue_handler = QueueHandler(log_queue)

   # Process logs in background thread
   listener = QueueListener(log_queue, *actual_handlers)
   listener.start()
   ```

---

## Implementation Recommendations

### For GCC Demo / EOL Application

Based on the current architecture (`app/agentic/eol`), here's a recommended implementation plan:

#### 1. Correlation ID Middleware

**Location:** `app/agentic/eol/middleware/correlation_id.py`

```python
from fastapi import Request
from contextvars import ContextVar
import uuid

# Module-level context variable
correlation_id_var: ContextVar[str] = ContextVar("correlation_id", default="")

async def correlation_id_middleware(request: Request, call_next):
    """Add correlation ID to every request"""
    correlation_id = request.headers.get("x-correlation-id") or str(uuid.uuid4())

    # Set in context variable (for logging and nested calls)
    correlation_id_var.set(correlation_id)

    # Store in request state (for direct access)
    request.state.correlation_id = correlation_id

    # Process request
    response = await call_next(request)

    # Add to response headers
    response.headers["X-Correlation-ID"] = correlation_id

    return response

def get_correlation_id() -> str:
    """Helper to access correlation ID anywhere"""
    return correlation_id_var.get()
```

**Register in `main.py`:**

```python
from middleware.correlation_id import correlation_id_middleware

app = FastAPI()
app.middleware("http")(correlation_id_middleware)
```

#### 2. Structured Logging Configuration

**Location:** `app/agentic/eol/utils/logging_config.py`

```python
import structlog
import logging
import sys
import os

def configure_logging():
    """Configure structured logging for the application"""

    # Application metadata
    service_name = os.getenv("SERVICE_NAME", "eol-agent-service")
    environment = os.getenv("ENVIRONMENT", "development")
    version = os.getenv("APP_VERSION", "1.0.0")

    def add_app_context(logger, method_name, event_dict):
        event_dict["service"] = service_name
        event_dict["environment"] = environment
        event_dict["version"] = version
        return event_dict

    # Configure stdlib logging
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=logging.INFO if environment == "production" else logging.DEBUG,
    )

    # Configure structlog
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.CallsiteParameterAdder(
                parameters=[
                    structlog.processors.CallsiteParameter.MODULE,
                    structlog.processors.CallsiteParameter.FUNC_NAME,
                    structlog.processors.CallsiteParameter.LINENO,
                ]
            ),
            add_app_context,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer() if environment == "production"
                else structlog.dev.ConsoleRenderer(),  # Pretty console for dev
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )
```

**Initialize in `main.py`:**

```python
from utils.logging_config import configure_logging

configure_logging()
logger = structlog.get_logger(__name__)

logger.info("application_started")
```

#### 3. Request Context Middleware

**Location:** `app/agentic/eol/middleware/request_context.py`

```python
from fastapi import Request
import structlog
from middleware.correlation_id import get_correlation_id

async def request_context_middleware(request: Request, call_next):
    """Add request context to logs"""

    # Clear previous request context
    structlog.contextvars.clear_contextvars()

    # Bind request context
    structlog.contextvars.bind_contextvars(
        correlation_id=get_correlation_id(),
        method=request.method,
        path=request.url.path,
        client_ip=request.client.host if request.client else "unknown",
        user_agent=request.headers.get("user-agent", "unknown")
    )

    # Log request start
    logger = structlog.get_logger(__name__)
    logger.info("request_started")

    # Process request
    response = await call_next(request)

    # Log request completed
    logger.info("request_completed", status_code=response.status_code)

    return response
```

#### 4. OpenTelemetry Integration (Optional but Recommended)

**Location:** `app/agentic/eol/utils/tracing.py`

```python
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource, SERVICE_NAME
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
import os

def configure_tracing(app):
    """Configure OpenTelemetry tracing"""

    if not os.getenv("ENABLE_TRACING", "false").lower() == "true":
        return  # Tracing disabled

    # Define service resource
    resource = Resource(attributes={
        SERVICE_NAME: os.getenv("SERVICE_NAME", "eol-agent-service"),
        "environment": os.getenv("ENVIRONMENT", "development"),
        "version": os.getenv("APP_VERSION", "1.0.0")
    })

    # Set up tracer provider
    tracer_provider = TracerProvider(resource=resource)

    # Configure OTLP exporter
    otlp_endpoint = os.getenv("OTLP_ENDPOINT", "http://localhost:4317")
    otlp_exporter = OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True)

    tracer_provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
    trace.set_tracer_provider(tracer_provider)

    # Instrument FastAPI
    FastAPIInstrumentor.instrument_app(app)
```

**Initialize in `main.py`:**

```python
from utils.tracing import configure_tracing

app = FastAPI()
configure_tracing(app)
```

#### 5. Middleware Registration Order

**In `main.py`:**

```python
from fastapi import FastAPI
from middleware.correlation_id import correlation_id_middleware
from middleware.request_context import request_context_middleware
from utils.logging_config import configure_logging
from utils.tracing import configure_tracing

# Configure logging first
configure_logging()

# Create app
app = FastAPI()

# Register middleware (order matters - first registered runs outermost)
app.middleware("http")(correlation_id_middleware)  # 1. Add correlation ID
app.middleware("http")(request_context_middleware)  # 2. Add request context

# Configure tracing
configure_tracing(app)

# ... rest of application setup ...
```

### Migration Strategy

**Phase 1: Foundation (Week 1)**
- [ ] Add correlation ID middleware
- [ ] Configure structlog with basic processors
- [ ] Update existing loggers to use structlog
- [ ] Test in development environment

**Phase 2: Context Enrichment (Week 2)**
- [ ] Add request context middleware
- [ ] Implement context variables for user/tenant
- [ ] Add context to all log statements
- [ ] Test context propagation

**Phase 3: Distributed Tracing (Week 3)**
- [ ] Install OpenTelemetry dependencies
- [ ] Configure OTLP exporter
- [ ] Instrument FastAPI
- [ ] Add manual spans for critical operations
- [ ] Test trace propagation

**Phase 4: Production Hardening (Week 4)**
- [ ] Add sensitive data redaction
- [ ] Configure log retention
- [ ] Set up centralized logging backend
- [ ] Performance testing and optimization
- [ ] Documentation and training

---

## Reference Architecture

### High-Level Flow

```
┌─────────────┐
│   Client    │
└──────┬──────┘
       │ X-Correlation-ID: <uuid>
       ▼
┌─────────────────────────────────────────┐
│     Correlation ID Middleware            │
│  - Extract or generate correlation ID    │
│  - Set in contextvars                   │
│  - Store in request.state               │
└──────────────┬──────────────────────────┘
               ▼
┌─────────────────────────────────────────┐
│    Request Context Middleware            │
│  - Clear previous context                │
│  - Bind request metadata to contextvars  │
│  - Log request start                    │
└──────────────┬──────────────────────────┘
               ▼
┌─────────────────────────────────────────┐
│      OpenTelemetry Instrumentation       │
│  - Create span for request               │
│  - Extract/inject trace context          │
│  - Record span attributes               │
└──────────────┬──────────────────────────┘
               ▼
┌─────────────────────────────────────────┐
│          Route Handler                   │
│  - Business logic                        │
│  - Access correlation ID via contextvar  │
│  - Logs automatically include context   │
└──────────────┬──────────────────────────┘
               ▼
┌─────────────────────────────────────────┐
│        Structured Logging                │
│  - Merge contextvars                     │
│  - Add application metadata              │
│  - Render as JSON                       │
│  - Output to stdout/file                │
└──────────────┬──────────────────────────┘
               ▼
┌─────────────────────────────────────────┐
│     Centralized Logging Backend          │
│  (Azure Monitor / ELK / Splunk)          │
└─────────────────────────────────────────┘
```

### Data Flow

```
Request → Correlation ID → Context Vars → Logs
                                ↓
                           OpenTelemetry Spans
                                ↓
                           Trace Backend
```

### Context Propagation

```
Middleware
    ├─ Set correlation_id_var
    ├─ Set user_id_var
    └─ Set tenant_id_var
         │
         ├─→ Handler Function
         │       ├─→ Helper Function 1
         │       │       └─→ Database Call
         │       │             (correlation_id available)
         │       └─→ Helper Function 2
         │               └─→ External API Call
         │                     (correlation_id in headers)
         └─→ Background Task (with context copy)
                 └─→ Async Worker
                       (correlation_id available)
```

---

## Summary & Quick Reference

### Key Technologies

| Technology | Purpose | Installation |
|-----------|---------|--------------|
| **FastAPI Middleware** | Correlation ID injection | Built-in |
| **contextvars** | Async-safe context propagation | Built-in (Python 3.7+) |
| **structlog** | Structured logging | `pip install structlog` |
| **OpenTelemetry** | Distributed tracing | `pip install opentelemetry-*` |

### Essential Patterns

**Correlation ID:**
```python
@app.middleware("http")
async def add_correlation_id(request, call_next):
    correlation_id = request.headers.get("x-correlation-id") or str(uuid.uuid4())
    correlation_id_var.set(correlation_id)
    response = await call_next(request)
    response.headers["X-Correlation-ID"] = correlation_id
    return response
```

**Structured Logging:**
```python
logger = structlog.get_logger(__name__)
logger.info("operation_completed", user_id="123", duration_ms=1234)
```

**Context Variables:**
```python
correlation_id_var: ContextVar[str] = ContextVar("correlation_id", default="")
correlation_id_var.set("req-12345")
current_id = correlation_id_var.get()
```

**OpenTelemetry:**
```python
with tracer.start_as_current_span("operation") as span:
    span.set_attribute("user_id", "123")
    # ... perform operation ...
```

### Checklist for Implementation

- [ ] Install dependencies (`structlog`, `opentelemetry-*`)
- [ ] Configure structured logging
- [ ] Add correlation ID middleware
- [ ] Add request context middleware
- [ ] Update loggers to use structlog
- [ ] Implement context variables
- [ ] Configure OpenTelemetry (optional)
- [ ] Add manual spans for key operations
- [ ] Test context propagation
- [ ] Configure log aggregation backend
- [ ] Add monitoring/alerting
- [ ] Document logging standards

---

## Additional Resources

### Documentation

- **FastAPI Middleware**: https://fastapi.tiangolo.com/advanced/middleware/
- **structlog**: https://www.structlog.org/
- **OpenTelemetry Python**: https://opentelemetry-python.readthedocs.io/
- **Python contextvars**: https://docs.python.org/3/library/contextvars.html

### Related Standards

- **W3C Trace Context**: https://www.w3.org/TR/trace-context/
- **OpenTelemetry Specification**: https://opentelemetry.io/docs/specs/otel/
- **Structured Logging**: https://www.thoughtworks.com/insights/blog/structured-logging

---

**Document Version:** 1.0
**Last Updated:** 2026-02-27
**Author:** Research conducted for GCC Demo EOL Application
