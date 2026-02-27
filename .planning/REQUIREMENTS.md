# Requirements: GCC Demo Platform Production Readiness Refactoring

**Defined:** 2026-02-27
**Core Value:** Transform GCC Demo platform into a production-ready system with robust error handling, optimized performance, comprehensive testing, and enterprise-grade observability

**Timeline:** 2 weeks (4 phases)
**Scope:** 13 concerns from CONCERNS.md (#3, #7-#9, #11-#12, #14-#15, #19-#23)

---

## 1. Functional Requirements

### Error Handling & Resilience (Concern #3)

- [ ] **ERR-01**: All orchestrators (EOL, SRE, Inventory) use `asyncio.gather(return_exceptions=True)` for agent execution
- [ ] **ERR-02**: Orchestrators aggregate errors with structured error collection (AgentError dataclass with severity classification)
- [ ] **ERR-03**: Orchestrators implement graceful degradation - return partial results when some agents fail
- [ ] **ERR-04**: Critical errors (CRITICAL severity) trigger fallback mechanisms
- [ ] **ERR-05**: Non-critical failures (MEDIUM/LOW severity) allow workflow to continue
- [ ] **ERR-06**: All error aggregation includes metadata: agent name, error type, severity, timestamp, context
- [ ] **ERR-07**: Azure SDK calls protected by circuit breaker pattern for cascading failure prevention
- [ ] **ERR-08**: Circuit breakers track failure rates and auto-disable unhealthy operations (5 failures → OPEN state)
- [ ] **ERR-09**: Orchestrators log structured errors with correlation IDs for traceability

### Configuration Management (Concern #7)

- [ ] **CFG-01**: Centralized timeout configuration via `TimeoutConfig` dataclass
- [ ] **CFG-02**: Timeout defaults documented with rationale: connection (30s), tool execution (60s), total operation (300s)
- [ ] **CFG-03**: Per-operation-type timeout configuration (AOAI, Azure API, database, MCP tools)
- [ ] **CFG-04**: Backward compatibility maintained for existing environment variables
- [ ] **CFG-05**: Configuration validation on startup with clear error messages
- [ ] **CFG-06**: Timeout configuration accessible via environment variables with `TIMEOUT_` prefix
- [ ] **CFG-07**: Migration guide documents transition from scattered env vars to centralized config

### Testing Coverage (Concerns #22, #23)

- [ ] **TST-01**: Orchestrator unit tests achieve ≥80% code coverage
- [ ] **TST-02**: Each orchestrator (EOL, SRE, Inventory) has ≥5 unit tests covering happy path, error cases, partial success
- [ ] **TST-03**: MCP server tools have 100% validation tests
- [ ] **TST-04**: Integration tests verify error boundary behavior with mocked dependencies
- [ ] **TST-05**: pytest fixtures provide reusable mocks for Azure clients, MCP servers, and agents
- [ ] **TST-06**: Test organization uses markers: `@pytest.mark.unit`, `@pytest.mark.asyncio`, `@pytest.mark.integration`
- [ ] **TST-07**: Async tests use `AsyncMock` for all async operations
- [ ] **TST-08**: Tests verify context propagation (correlation IDs, user context)

### Observability & Tracing (Concern #11)

- [ ] **OBS-01**: Correlation IDs generated/extracted in FastAPI middleware for every request
- [ ] **OBS-02**: Correlation IDs propagated via `contextvars` across async boundaries
- [ ] **OBS-03**: All log statements include correlation ID automatically
- [ ] **OBS-04**: Correlation IDs included in API response headers (`X-Correlation-ID`)
- [ ] **OBS-05**: Structured logging configured with `structlog` producing JSON output
- [ ] **OBS-06**: Logs include standard fields: timestamp, level, logger, message, correlation_id, service, environment, version
- [ ] **OBS-07**: Request context (method, path, client_ip) automatically bound to logs
- [ ] **OBS-08**: OpenTelemetry traces link to correlation IDs for end-to-end tracing
- [ ] **OBS-09**: Sensitive data (passwords, tokens, secrets) redacted from logs

### Performance Optimization (Concerns #19, #20, #9)

- [ ] **PRF-01**: Cosmos DB writes executed asynchronously using fire-and-forget pattern
- [ ] **PRF-02**: Background task set pattern prevents garbage collection of fire-and-forget tasks
- [ ] **PRF-03**: Azure SDK clients reused via singleton pattern (credential and client caching)
- [ ] **PRF-04**: Connection pooling configured for Azure SDK clients (pool_maxsize=20 for sync, limit=100 for async)
- [ ] **PRF-05**: DefaultAzureCredential created once at startup with persistent token caching
- [ ] **PRF-06**: Cache TTL configuration standardized across all cache implementations
- [ ] **PRF-07**: L1 in-memory cache + L2 Cosmos cache strategy consistently implemented
- [ ] **PRF-08**: Async operations use proper timeout management with `asyncio.wait_for()`

### Code Quality (Concerns #12, #14, #15, #21)

- [ ] **CQ-01**: Retry logic standardized using enhanced `utils/retry.py` with exponential backoff + jitter
- [ ] **CQ-02**: Retry logic includes hooks for observability (`on_retry` callback, `RetryStats`)
- [ ] **CQ-03**: Unused imports removed from targeted files (concern #14 list)
- [ ] **CQ-04**: Logging levels standardized (INFO for normal flow, WARNING for recoverable issues, ERROR for failures)
- [ ] **CQ-05**: Playwright browser pool bounded to prevent resource exhaustion (max 5 concurrent browsers)
- [ ] **CQ-06**: Browser pool implements graceful cleanup on shutdown
- [ ] **CQ-07**: All orchestrators implement graceful shutdown for background tasks

### Architecture Simplification (Concern #8)

- [ ] **ARC-01**: Agent hierarchy documented with clear responsibility boundaries
- [ ] **ARC-02**: Debugging guides created for tracing requests through 5-layer stack
- [ ] **ARC-03**: Context propagation verified at each layer (Orchestrator → Domain Agent → Sub-Agent → MCP Client → MCP Server)
- [ ] **ARC-04**: Consider architectural simplification opportunities for future iterations (documented in recommendations)

---

## 2. Non-Functional Requirements

### Reliability

- [ ] **NFR-REL-01**: Single agent failure does not crash entire workflow (99.9% resilience target)
- [ ] **NFR-REL-02**: Orchestrators continue with partial results when non-critical agents fail
- [ ] **NFR-REL-03**: Circuit breakers prevent cascading failures to Azure services
- [ ] **NFR-REL-04**: Retry logic handles transient failures automatically (3-5 retries with exponential backoff)
- [ ] **NFR-REL-05**: Error rate monitoring alerts when operation error rate exceeds 70%

### Performance

- [ ] **NFR-PRF-01**: P95 latency for EOL queries ≤ 2 seconds (measured end-to-end)
- [ ] **NFR-PRF-02**: Async Cosmos writes complete within 1 second (non-blocking)
- [ ] **NFR-PRF-03**: Azure SDK client initialization overhead < 100ms after first request
- [ ] **NFR-PRF-04**: Connection pool efficiency ≥ 80% (reuse vs. create new connections)
- [ ] **NFR-PRF-05**: Memory footprint stable under load (no memory leaks in fire-and-forget tasks)

### Maintainability

- [ ] **NFR-MNT-01**: Timeout configuration changes require only environment variable updates (no code changes)
- [ ] **NFR-MNT-02**: Error handling patterns consistent across all orchestrators
- [ ] **NFR-MNT-03**: Test fixtures reusable across test files (conftest.py)
- [ ] **NFR-MNT-04**: Logging standards documented with examples
- [ ] **NFR-MNT-05**: Code quality metrics tracked (test coverage, error rates, retry success rates)

### Observability

- [ ] **NFR-OBS-01**: 100% of API requests traceable via correlation ID
- [ ] **NFR-OBS-02**: Logs queryable by correlation_id, user_id, tenant_id, trace_id
- [ ] **NFR-OBS-03**: Error rates visible per agent/operation in logs
- [ ] **NFR-OBS-04**: Distributed traces link requests across services
- [ ] **NFR-OBS-05**: Log retention: 90 days in centralized logging system

### Scalability

- [ ] **NFR-SCL-01**: Connection pooling supports 50+ concurrent requests without degradation
- [ ] **NFR-SCL-02**: Fire-and-forget task tracking handles 100+ background tasks
- [ ] **NFR-SCL-03**: Circuit breaker pattern scales to 10+ Azure service dependencies
- [ ] **NFR-SCL-04**: Cache strategy reduces Azure API calls by 60% for repeated queries

### Security

- [ ] **NFR-SEC-01**: No sensitive data (passwords, tokens, secrets) logged
- [ ] **NFR-SEC-02**: Correlation IDs do not leak PII or business logic details
- [ ] **NFR-SEC-03**: Log redaction processor removes sensitive fields before output
- [ ] **NFR-SEC-04**: Azure credentials managed via managed identity (no secrets in code)

---

## 3. Technical Requirements

### Error Handling Patterns (Research: error-handling.md)

- [ ] **TECH-ERR-01**: Implement `utils/error_aggregation.py` with `ErrorSeverity` enum (CRITICAL, HIGH, MEDIUM, LOW)
- [ ] **TECH-ERR-02**: Create `AgentError` dataclass with fields: agent_name, error_type, message, severity, timestamp, context
- [ ] **TECH-ERR-03**: Create `AggregatedResult` dataclass with fields: success, partial_success, results, errors, metadata
- [ ] **TECH-ERR-04**: Implement `utils/circuit_breaker.py` with `AsyncCircuitBreaker` class
- [ ] **TECH-ERR-05**: Circuit breaker config: `failure_threshold=5`, `timeout_seconds=60`, `half_open_attempts=1`
- [ ] **TECH-ERR-06**: Implement `utils/error_rate_monitor.py` with sliding window (5 minutes default)
- [ ] **TECH-ERR-07**: Standardize `return_exceptions=True` in all multi-agent orchestrators
- [ ] **TECH-ERR-08**: Fix `azure_ai_sre_agent.py` line 1431 to use `return_exceptions=True`

### Azure SDK Optimization (Research: azure-sdk-optimization.md)

- [ ] **TECH-AZ-01**: Implement `AzureSDKManager` singleton class in `utils/azure_client_manager.py`
- [ ] **TECH-AZ-02**: Configure connection pooling: sync (pool_connections=10, pool_maxsize=20), async (limit=100, limit_per_host=30)
- [ ] **TECH-AZ-03**: Set client timeouts: connection_timeout=30s, read_timeout=120s
- [ ] **TECH-AZ-04**: Configure retry policy: retry_total=3, retry_mode='exponential'
- [ ] **TECH-AZ-05**: Implement credential caching with `TokenCachePersistenceOptions`
- [ ] **TECH-AZ-06**: Use `DefaultAzureCredential` with persistent cache enabled
- [ ] **TECH-AZ-07**: Initialize Azure clients in FastAPI lifespan context
- [ ] **TECH-AZ-08**: Implement graceful cleanup in FastAPI shutdown handler

### Async Patterns & Testing (Research: async-patterns-testing.md)

- [ ] **TECH-TST-01**: Implement fire-and-forget task set pattern in orchestrators
- [ ] **TECH-TST-02**: Add `_background_tasks: Set[asyncio.Task]` to orchestrator classes
- [ ] **TECH-TST-03**: Implement `_spawn_background()` method with automatic cleanup callbacks
- [ ] **TECH-TST-04**: Implement graceful shutdown method to cancel background tasks
- [ ] **TECH-TST-05**: Configure `pytest.ini` with `asyncio_mode = auto`
- [ ] **TECH-TST-06**: Create `conftest.py` with reusable fixtures for Azure clients, MCP servers, agents
- [ ] **TECH-TST-07**: Use `AsyncMock` for all async operations in tests
- [ ] **TECH-TST-08**: Implement factory fixtures for creating agents with custom config
- [ ] **TECH-TST-09**: Add test markers: `@pytest.mark.unit`, `@pytest.mark.integration`, `@pytest.mark.remote`

### Observability & Tracing (Research: observability-tracing.md)

- [ ] **TECH-OBS-01**: Implement `middleware/correlation_id.py` with FastAPI HTTP middleware
- [ ] **TECH-OBS-02**: Create module-level `correlation_id_var: ContextVar[str]`
- [ ] **TECH-OBS-03**: Configure `structlog` with JSON renderer for production
- [ ] **TECH-OBS-04**: Add processors: `merge_contextvars`, `filter_by_level`, `add_logger_name`, `TimeStamper(fmt="iso")`
- [ ] **TECH-OBS-05**: Implement `utils/logging_config.py` with `configure_logging()` function
- [ ] **TECH-OBS-06**: Add application metadata processor (service, environment, version, host)
- [ ] **TECH-OBS-07**: Implement sensitive data redaction processor
- [ ] **TECH-OBS-08**: Create `middleware/request_context.py` to bind request metadata to logs
- [ ] **TECH-OBS-09**: Install OpenTelemetry: `opentelemetry-api`, `opentelemetry-sdk`, `opentelemetry-instrumentation-fastapi`
- [ ] **TECH-OBS-10**: Configure OTLP exporter for trace export (optional, if tracing backend available)
- [ ] **TECH-OBS-11**: Instrument FastAPI with `FastAPIInstrumentor`
- [ ] **TECH-OBS-12**: Link OpenTelemetry trace IDs with correlation IDs in logs

### Retry Enhancement

- [ ] **TECH-RET-01**: Enhance `utils/retry.py` with `retry_on_result` parameter
- [ ] **TECH-RET-02**: Add `on_retry` callback hook for observability
- [ ] **TECH-RET-03**: Add `RetryStats` dataclass for tracking retry metrics
- [ ] **TECH-RET-04**: Add `TryAgain` exception for explicit retry forcing
- [ ] **TECH-RET-05**: Maintain backward compatibility with existing retry decorators

---

## 4. Testing Requirements

### Unit Testing

- [ ] **TEST-UNIT-01**: EOL Orchestrator: 8 unit tests (happy path, agent failure, partial success, timeout, circuit breaker, error aggregation, fallback, context propagation)
- [ ] **TEST-UNIT-02**: SRE Orchestrator: 8 unit tests (same coverage as EOL)
- [ ] **TEST-UNIT-03**: Inventory Orchestrator: 8 unit tests (same coverage)
- [ ] **TEST-UNIT-04**: Error aggregation utilities: 5 tests (severity classification, error collection, partial results, critical error handling, metadata validation)
- [ ] **TEST-UNIT-05**: Circuit breaker: 6 tests (state transitions, failure tracking, timeout, half-open, success reset, concurrent requests)
- [ ] **TEST-UNIT-06**: Correlation ID middleware: 4 tests (generation, extraction, propagation, response header)
- [ ] **TEST-UNIT-07**: Retry logic: 6 tests (exponential backoff, jitter, max retries, success after retry, hooks, result-based retry)

### Integration Testing

- [ ] **TEST-INT-01**: Orchestrator with mocked Azure clients: error handling end-to-end
- [ ] **TEST-INT-02**: Fire-and-forget tasks with task set tracking: completion and cleanup
- [ ] **TEST-INT-03**: Correlation ID propagation through full request lifecycle
- [ ] **TEST-INT-04**: Circuit breaker integration with Azure SDK clients
- [ ] **TEST-INT-05**: Structured logging with context variables: verify log output format

### MCP Server Testing

- [ ] **TEST-MCP-01**: Patch MCP server: 100% tool validation tests
- [ ] **TEST-MCP-02**: Network MCP server: 100% tool validation tests
- [ ] **TEST-MCP-03**: Security/compliance MCP server: 100% tool validation tests
- [ ] **TEST-MCP-04**: SRE MCP server: 100% tool validation tests
- [ ] **TEST-MCP-05**: Monitoring MCP server: 100% tool validation tests
- [ ] **TEST-MCP-06**: Each tool test validates: input schema, output format, error handling

### Test Coverage Targets

- [ ] **TEST-COV-01**: Overall test coverage: ≥80% (up from ~60%)
- [ ] **TEST-COV-02**: Orchestrator coverage: ≥85%
- [ ] **TEST-COV-03**: Error handling utilities coverage: ≥90%
- [ ] **TEST-COV-04**: Middleware coverage: ≥90%
- [ ] **TEST-COV-05**: Azure SDK wrapper coverage: ≥80%

### Test Fixtures

- [ ] **TEST-FIX-01**: `conftest.py` with mock Azure Compute client
- [ ] **TEST-FIX-02**: `conftest.py` with mock Azure Network client
- [ ] **TEST-FIX-03**: `conftest.py` with mock Cosmos DB client
- [ ] **TEST-FIX-04**: `conftest.py` with mock Azure OpenAI client
- [ ] **TEST-FIX-05**: `conftest.py` with mock MCP servers (patch, network, SRE)
- [ ] **TEST-FIX-06**: Factory fixture for creating orchestrators with custom config
- [ ] **TEST-FIX-07**: Factory fixture for creating agents with mocked dependencies

---

## 5. Success Criteria

### Must-Have (Phase Completion Criteria)

#### Phase 1: Testing Foundation
- [ ] **SUCCESS-P1-01**: ≥20 new orchestrator unit tests passing
- [ ] **SUCCESS-P1-02**: 100% MCP tool validation tests passing
- [ ] **SUCCESS-P1-03**: Test coverage increased to ≥70%
- [ ] **SUCCESS-P1-04**: Test fixtures established in `conftest.py`

#### Phase 2: Error Boundaries & Config
- [ ] **SUCCESS-P2-01**: All orchestrators use `return_exceptions=True`
- [ ] **SUCCESS-P2-02**: Error aggregation with severity classification functional
- [ ] **SUCCESS-P2-03**: Circuit breaker pattern implemented for Azure APIs
- [ ] **SUCCESS-P2-04**: Centralized timeout configuration operational
- [ ] **SUCCESS-P2-05**: Correlation IDs in all logs and API responses

#### Phase 3: Performance Optimizations
- [ ] **SUCCESS-P3-01**: Async Cosmos writes implemented with fire-and-forget pattern
- [ ] **SUCCESS-P3-02**: Azure SDK connection pooling configured and tested
- [ ] **SUCCESS-P3-03**: Credential/client singleton pattern implemented
- [ ] **SUCCESS-P3-04**: Cache TTL standardized across all caches
- [ ] **SUCCESS-P3-05**: P95 latency ≤ 2s for EOL queries (measured)

#### Phase 4: Code Quality & Polish
- [ ] **SUCCESS-P4-01**: Enhanced retry logic deployed with hooks and stats
- [ ] **SUCCESS-P4-02**: Unused imports removed from all targeted files
- [ ] **SUCCESS-P4-03**: Logging levels standardized project-wide
- [ ] **SUCCESS-P4-04**: Playwright browser pool bounded and tested
- [ ] **SUCCESS-P4-05**: Production checklist completed (error handling, monitoring, performance)

### Should-Have (Quality Gates)

- [ ] **SUCCESS-QG-01**: Zero critical bugs introduced by refactoring (regression testing)
- [ ] **SUCCESS-QG-02**: Backward compatibility maintained for existing API contracts
- [ ] **SUCCESS-QG-03**: All existing tests still passing after changes
- [ ] **SUCCESS-QG-04**: Documentation updated (README, runbooks, architecture docs)
- [ ] **SUCCESS-QG-05**: Performance benchmarks show no degradation vs. baseline

### Nice-to-Have (Stretch Goals)

- [ ] **SUCCESS-NG-01**: OpenTelemetry distributed tracing fully operational
- [ ] **SUCCESS-NG-02**: Load testing performed with ≥100 concurrent requests
- [ ] **SUCCESS-NG-03**: Error rate dashboard created in Azure Monitor
- [ ] **SUCCESS-NG-04**: Architecture simplification recommendations documented
- [ ] **SUCCESS-NG-05**: Team training completed on new patterns (error handling, observability)

### Measurable Outcomes

| Metric | Baseline | Target | Measurement Method |
|--------|----------|--------|-------------------|
| **Test Coverage** | ~60% | ≥80% | pytest-cov report |
| **Orchestrator Tests** | 0 | ≥20 | Test count in test files |
| **MCP Tool Tests** | 0 | 100% (all tools) | Test coverage per tool |
| **Error Boundaries** | 0% orchestrators | 100% orchestrators | Code review checklist |
| **P95 Latency** | Unknown | ≤2s | Application Insights metrics |
| **Connection Reuse Rate** | Unknown | ≥80% | Azure SDK metrics |
| **Concerns Addressed** | 0 | 13 | CONCERNS.md tracking |

---

## 6. Dependencies

### Technical Dependencies

#### Required Libraries (New)
- [ ] `structlog` - Structured logging with contextvars support
- [ ] `opentelemetry-api` - OpenTelemetry API (optional)
- [ ] `opentelemetry-sdk` - OpenTelemetry SDK (optional)
- [ ] `opentelemetry-instrumentation-fastapi` - FastAPI instrumentation (optional)
- [ ] `opentelemetry-exporter-otlp` - OTLP exporter (optional)
- [ ] `pytest-cov` - Code coverage reporting (dev dependency)

#### Existing Dependencies (Version Verification)
- [ ] `pytest-asyncio` ≥0.21.0 - Async test support
- [ ] `fastapi` ≥0.100.0 - Web framework with lifespan support
- [ ] `azure-identity` ≥1.14.0 - Credential management
- [ ] `azure-core` ≥1.28.0 - Azure SDK base
- [ ] `aiohttp` ≥3.8.0 - Async HTTP for Azure SDK

### Infrastructure Dependencies

- [ ] **DEP-INF-01**: Azure subscription with existing resources (VMs, networks, Cosmos DB)
- [ ] **DEP-INF-02**: Cosmos DB instance for cache persistence
- [ ] **DEP-INF-03**: Azure OpenAI service endpoint for LLM operations
- [ ] **DEP-INF-04**: Azure Log Analytics workspace (optional, for centralized logging)
- [ ] **DEP-INF-05**: Application Insights instance (optional, for OpenTelemetry export)

### Codebase Dependencies

- [ ] **DEP-CODE-01**: 169 Python files in `app/agentic/eol/`
- [ ] **DEP-CODE-02**: 41 agent modules (orchestrators + domain agents + sub-agents)
- [ ] **DEP-CODE-03**: 20 API router modules
- [ ] **DEP-CODE-04**: 71 utility modules
- [ ] **DEP-CODE-05**: 9 local MCP servers
- [ ] **DEP-CODE-06**: Existing retry logic in `utils/retry.py`
- [ ] **DEP-CODE-07**: Existing error handlers in `utils/error_handlers.py`
- [ ] **DEP-CODE-08**: Existing configuration in `utils/config.py`

### External Dependencies

- [ ] **DEP-EXT-01**: None - this is an internal refactoring project
- [ ] **DEP-EXT-02**: No external API changes required
- [ ] **DEP-EXT-03**: No infrastructure provisioning required

### Constraints

- [ ] **DEP-CON-01**: Must maintain backward compatibility with existing `.env` configurations
- [ ] **DEP-CON-02**: Must not break existing API contracts (public endpoints)
- [ ] **DEP-CON-03**: Must not introduce new Azure resource requirements
- [ ] **DEP-CON-04**: Must complete within 2-week timeline (10 business days)
- [ ] **DEP-CON-05**: Must prioritize critical/high concerns over stretch goals

---

## 7. Phase Breakdown Preview

### Phase 1: Testing Foundation (Days 1-3)

**Goal:** Establish testing infrastructure and baseline coverage

**Key Deliverables:**
- Orchestrator unit tests (≥20 tests)
- MCP server tool validation tests (100% tools)
- Test fixtures in `conftest.py`
- pytest configuration with markers

**Requirements Covered:**
- TST-01 through TST-08
- TEST-UNIT-01 through TEST-UNIT-07
- TEST-MCP-01 through TEST-MCP-06
- TEST-FIX-01 through TEST-FIX-07

### Phase 2: Error Boundaries & Configuration (Days 4-7)

**Goal:** Implement robust error handling and centralized configuration

**Key Deliverables:**
- Error aggregation utilities (`utils/error_aggregation.py`)
- Circuit breaker implementation (`utils/circuit_breaker.py`)
- Centralized timeout configuration (`TimeoutConfig`)
- Correlation ID middleware
- Structured logging setup

**Requirements Covered:**
- ERR-01 through ERR-09
- CFG-01 through CFG-07
- OBS-01 through OBS-09
- TECH-ERR-01 through TECH-ERR-08
- TECH-OBS-01 through TECH-OBS-12

### Phase 3: Performance Optimizations (Days 8-10)

**Goal:** Optimize Azure SDK usage and async operations

**Key Deliverables:**
- Azure SDK singleton manager
- Connection pooling configuration
- Async Cosmos writes with fire-and-forget
- Credential caching
- Cache TTL standardization

**Requirements Covered:**
- PRF-01 through PRF-08
- TECH-AZ-01 through TECH-AZ-08
- TECH-TST-01 through TECH-TST-04
- NFR-PRF-01 through NFR-PRF-05

### Phase 4: Code Quality & Polish (Days 11-14)

**Goal:** Clean up code quality issues and finalize documentation

**Key Deliverables:**
- Enhanced retry logic with hooks
- Unused imports cleanup
- Logging level standardization
- Playwright browser pool bounding
- Production runbooks and documentation

**Requirements Covered:**
- CQ-01 through CQ-07
- TECH-RET-01 through TECH-RET-05
- ARC-01 through ARC-04
- NFR-MNT-01 through NFR-MNT-05

---

## Out of Scope

Explicitly excluded from this 2-week refactoring project:

| Concern | Reason | Future Consideration |
|---------|--------|---------------------|
| **Secrets Management (#1)** | Requires Key Vault provisioning and migration plan (infrastructure change) | Separate security initiative |
| **Terraform State Security (#2)** | Infrastructure change requiring backend reconfiguration | DevOps project |
| **Rate Limiting (#4)** | Requires capacity planning, testing, and monitoring setup | Post-production deployment |
| **Cosmos DB RU Monitoring (#5)** | Observability project requiring metrics pipeline | Post-production monitoring setup |
| **Health Check Improvements (#6)** | Not critical for production readiness, can iterate post-launch | Future enhancement |
| **Agent Hierarchy Simplification (#8)** | Major architectural refactoring beyond 2-week scope | Architecture review in Q2 2026 |
| **RBAC Authentication (#18)** | Security initiative requiring AD integration and testing | Separate security project |
| **CI/CD Pipeline (#25)** | DevOps project requiring build/deploy automation | Separate DevOps initiative |
| **Monitoring Alerts (#26)** | Requires production deployment and baseline metrics | Post-production setup |
| **Disaster Recovery (#27)** | Operational project requiring backup/restore procedures | Separate operational project |

**Rationale for Exclusions:**
- These concerns require infrastructure changes, external dependencies, or extended timelines
- Focus on production readiness core: error handling, performance, testing, observability
- Deferred concerns tracked in CONCERNS.md for future sprints

---

## Traceability Matrix

### Phase 1: Testing Foundation (Days 1-3)

| Requirement ID | Category | Description | Status |
|---------------|----------|-------------|--------|
| TST-01 | Testing | Orchestrator unit tests ≥80% coverage | Pending |
| TST-02 | Testing | Each orchestrator has ≥5 unit tests | Pending |
| TST-03 | Testing | MCP server tools have 100% validation | Pending |
| TST-04 | Testing | Integration tests verify error boundaries | Pending |
| TST-05 | Testing | pytest fixtures for reusable mocks | Pending |
| TST-06 | Testing | Test organization with markers | Pending |
| TST-07 | Testing | AsyncMock for all async operations | Pending |
| TST-08 | Testing | Tests verify context propagation | Pending |
| TEST-UNIT-01 | Testing | EOL Orchestrator: 8 unit tests | Pending |
| TEST-UNIT-02 | Testing | SRE Orchestrator: 8 unit tests | Pending |
| TEST-UNIT-03 | Testing | Inventory Orchestrator: 8 unit tests | Pending |
| TEST-UNIT-04 | Testing | Error aggregation utilities: 5 tests | Pending |
| TEST-UNIT-05 | Testing | Circuit breaker: 6 tests | Pending |
| TEST-UNIT-06 | Testing | Correlation ID middleware: 4 tests | Pending |
| TEST-UNIT-07 | Testing | Retry logic: 6 tests | Pending |
| TEST-MCP-01 | Testing | Patch MCP server: 100% validation | Pending |
| TEST-MCP-02 | Testing | Network MCP server: 100% validation | Pending |
| TEST-MCP-03 | Testing | Security MCP server: 100% validation | Pending |
| TEST-MCP-04 | Testing | SRE MCP server: 100% validation | Pending |
| TEST-MCP-05 | Testing | Monitoring MCP server: 100% validation | Pending |
| TEST-FIX-01 | Testing | conftest.py: Azure Compute mock | Pending |
| TEST-FIX-02 | Testing | conftest.py: Azure Network mock | Pending |
| TEST-FIX-03 | Testing | conftest.py: Cosmos DB mock | Pending |
| TEST-FIX-04 | Testing | conftest.py: Azure OpenAI mock | Pending |
| TEST-FIX-05 | Testing | conftest.py: MCP server mocks | Pending |
| TEST-FIX-06 | Testing | Factory fixture: orchestrators | Pending |
| TEST-FIX-07 | Testing | Factory fixture: agents | Pending |

### Phase 2: Error Boundaries & Configuration (Days 4-7)

| Requirement ID | Category | Description | Status |
|---------------|----------|-------------|--------|
| ERR-01 | Error Handling | return_exceptions=True in orchestrators | Pending |
| ERR-02 | Error Handling | Structured error collection | Pending |
| ERR-03 | Error Handling | Graceful degradation with partial results | Pending |
| ERR-04 | Error Handling | Critical error fallback mechanisms | Pending |
| ERR-05 | Error Handling | Non-critical failure continuation | Pending |
| ERR-06 | Error Handling | Error metadata collection | Pending |
| ERR-07 | Error Handling | Circuit breaker for Azure SDK calls | Pending |
| ERR-08 | Error Handling | Circuit breaker auto-disable unhealthy ops | Pending |
| ERR-09 | Error Handling | Structured error logging with correlation IDs | Pending |
| CFG-01 | Configuration | Centralized TimeoutConfig dataclass | Pending |
| CFG-02 | Configuration | Timeout defaults documented | Pending |
| CFG-03 | Configuration | Per-operation-type timeout config | Pending |
| CFG-04 | Configuration | Backward compatibility for env vars | Pending |
| CFG-05 | Configuration | Configuration validation on startup | Pending |
| CFG-06 | Configuration | TIMEOUT_ prefix env vars | Pending |
| CFG-07 | Configuration | Migration guide documentation | Pending |
| OBS-01 | Observability | Correlation IDs in middleware | Pending |
| OBS-02 | Observability | Correlation ID contextvars propagation | Pending |
| OBS-03 | Observability | Correlation IDs in all logs | Pending |
| OBS-04 | Observability | Correlation IDs in response headers | Pending |
| OBS-05 | Observability | structlog with JSON output | Pending |
| OBS-06 | Observability | Standard log fields | Pending |
| OBS-07 | Observability | Request context in logs | Pending |
| OBS-08 | Observability | OpenTelemetry trace linking | Pending |
| OBS-09 | Observability | Sensitive data redaction | Pending |
| TECH-ERR-01 | Technical | error_aggregation.py implementation | Pending |
| TECH-ERR-02 | Technical | AgentError dataclass | Pending |
| TECH-ERR-03 | Technical | AggregatedResult dataclass | Pending |
| TECH-ERR-04 | Technical | circuit_breaker.py implementation | Pending |
| TECH-ERR-05 | Technical | Circuit breaker configuration | Pending |
| TECH-ERR-06 | Technical | error_rate_monitor.py implementation | Pending |
| TECH-ERR-07 | Technical | Standardize return_exceptions=True | Pending |
| TECH-ERR-08 | Technical | Fix azure_ai_sre_agent.py line 1431 | Pending |
| TECH-OBS-01 | Technical | correlation_id.py middleware | Pending |
| TECH-OBS-02 | Technical | correlation_id_var ContextVar | Pending |
| TECH-OBS-03 | Technical | structlog configuration | Pending |
| TECH-OBS-04 | Technical | structlog processors | Pending |
| TECH-OBS-05 | Technical | logging_config.py implementation | Pending |
| TECH-OBS-06 | Technical | Application metadata processor | Pending |
| TECH-OBS-07 | Technical | Sensitive data redaction processor | Pending |
| TECH-OBS-08 | Technical | request_context.py middleware | Pending |
| TECH-OBS-09 | Technical | OpenTelemetry installation | Pending |
| TECH-OBS-10 | Technical | OTLP exporter configuration | Pending |
| TECH-OBS-11 | Technical | FastAPI instrumentation | Pending |
| TECH-OBS-12 | Technical | Trace ID linking | Pending |

### Phase 3: Performance Optimizations (Days 8-10)

| Requirement ID | Category | Description | Status |
|---------------|----------|-------------|--------|
| PRF-01 | Performance | Async Cosmos writes (fire-and-forget) | Pending |
| PRF-02 | Performance | Background task set pattern | Pending |
| PRF-03 | Performance | Azure SDK client singleton | Pending |
| PRF-04 | Performance | Connection pooling configuration | Pending |
| PRF-05 | Performance | DefaultAzureCredential singleton | Pending |
| PRF-06 | Performance | Cache TTL standardization | Pending |
| PRF-07 | Performance | L1/L2 cache strategy implementation | Pending |
| PRF-08 | Performance | Async timeout management | Pending |
| TECH-AZ-01 | Technical | AzureSDKManager singleton class | Pending |
| TECH-AZ-02 | Technical | Connection pooling configuration | Pending |
| TECH-AZ-03 | Technical | Client timeout configuration | Pending |
| TECH-AZ-04 | Technical | Retry policy configuration | Pending |
| TECH-AZ-05 | Technical | Credential caching implementation | Pending |
| TECH-AZ-06 | Technical | DefaultAzureCredential setup | Pending |
| TECH-AZ-07 | Technical | FastAPI lifespan initialization | Pending |
| TECH-AZ-08 | Technical | FastAPI shutdown cleanup | Pending |
| TECH-TST-01 | Technical | Fire-and-forget task set pattern | Pending |
| TECH-TST-02 | Technical | _background_tasks set in orchestrators | Pending |
| TECH-TST-03 | Technical | _spawn_background() method | Pending |
| TECH-TST-04 | Technical | Graceful shutdown implementation | Pending |
| NFR-PRF-01 | Non-Functional | P95 latency ≤ 2s | Pending |
| NFR-PRF-02 | Non-Functional | Async writes complete < 1s | Pending |
| NFR-PRF-03 | Non-Functional | Client init overhead < 100ms | Pending |
| NFR-PRF-04 | Non-Functional | Connection pool efficiency ≥ 80% | Pending |
| NFR-PRF-05 | Non-Functional | Memory stability under load | Pending |

### Phase 4: Code Quality & Polish (Days 11-14)

| Requirement ID | Category | Description | Status |
|---------------|----------|-------------|--------|
| CQ-01 | Code Quality | Standardized retry logic | Pending |
| CQ-02 | Code Quality | Retry hooks for observability | Pending |
| CQ-03 | Code Quality | Remove unused imports | Pending |
| CQ-04 | Code Quality | Standardize logging levels | Pending |
| CQ-05 | Code Quality | Bounded Playwright browser pool | Pending |
| CQ-06 | Code Quality | Browser pool graceful cleanup | Pending |
| CQ-07 | Code Quality | Orchestrator graceful shutdown | Pending |
| ARC-01 | Architecture | Agent hierarchy documentation | Pending |
| ARC-02 | Architecture | Debugging guides | Pending |
| ARC-03 | Architecture | Context propagation verification | Pending |
| ARC-04 | Architecture | Simplification recommendations | Pending |
| TECH-RET-01 | Technical | retry_on_result parameter | Pending |
| TECH-RET-02 | Technical | on_retry callback hook | Pending |
| TECH-RET-03 | Technical | RetryStats dataclass | Pending |
| TECH-RET-04 | Technical | TryAgain exception | Pending |
| TECH-RET-05 | Technical | Retry backward compatibility | Pending |
| NFR-MNT-01 | Non-Functional | Timeout config via env vars only | Pending |
| NFR-MNT-02 | Non-Functional | Consistent error handling patterns | Pending |
| NFR-MNT-03 | Non-Functional | Reusable test fixtures | Pending |
| NFR-MNT-04 | Non-Functional | Logging standards documentation | Pending |
| NFR-MNT-05 | Non-Functional | Code quality metrics tracking | Pending |

### Coverage Summary

- **Total v1 Requirements:** 148
  - Functional: 48
  - Non-Functional: 20
  - Technical: 51
  - Testing: 29
- **Mapped to Phases:** 148 (100%)
- **Unmapped:** 0 ✓

**Phase Distribution:**
- Phase 1 (Testing): 27 requirements
- Phase 2 (Error/Config): 47 requirements
- Phase 3 (Performance): 28 requirements
- Phase 4 (Quality): 18 requirements
- Cross-cutting (All phases): 28 requirements

---

## Research Sources

This requirements document synthesized findings from the following research documents:

1. **error-handling.md** - Error handling patterns, `asyncio.gather()`, circuit breakers, error aggregation, graceful degradation
2. **azure-sdk-optimization.md** - Connection pooling, credential management, client lifecycle, async patterns, performance optimization
3. **async-patterns-testing.md** - Fire-and-forget tasks, task lifecycle, pytest-asyncio, mocking, fixture design
4. **observability-tracing.md** - Correlation IDs, structured logging, OpenTelemetry integration, context propagation

---

*Requirements defined: 2026-02-27*
*Last updated: 2026-02-27 after research synthesis*
*Next update: After Phase 1 completion (Day 3)*
