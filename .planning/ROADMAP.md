# GCC Demo Platform: Production Readiness Roadmap

**Project:** Production Readiness Refactoring
**Timeline:** 2 weeks (10 business days)
**Start Date:** 2026-02-27
**Status:** Planning Complete

---

## Executive Summary

This roadmap details the 4-phase approach to transform the GCC Demo platform into a production-ready system. The refactoring focuses on error handling, configuration management, performance optimization, testing coverage, and observability while maintaining backward compatibility and zero breaking changes.

**Success Metrics:**
- Test coverage: 60% → ≥80%
- Orchestrator tests: 0 → ≥20
- MCP tool tests: 0 → 100% coverage
- Error boundaries: 0% → 100% orchestrators
- P95 latency: Target ≤2s for EOL queries

**Risk Level:** MEDIUM - Controlled refactoring with extensive testing and staged rollout

---

## Table of Contents

1. [Phase Overview](#phase-overview)
2. [Phase 1: Testing Foundation (Days 1-3)](#phase-1-testing-foundation-days-1-3)
3. [Phase 2: Error Boundaries & Configuration (Days 4-7)](#phase-2-error-boundaries--configuration-days-4-7)
4. [Phase 3: Performance Optimizations (Days 8-10)](#phase-3-performance-optimizations-days-8-10)
5. [Phase 4: Code Quality & Polish (Days 11-14)](#phase-4-code-quality--polish-days-11-14)
6. [Critical Path Analysis](#critical-path-analysis)
7. [Dependencies Matrix](#dependencies-matrix)
8. [Risk Mitigation Strategy](#risk-mitigation-strategy)
9. [Integration Testing Strategy](#integration-testing-strategy)
10. [Commit Strategy](#commit-strategy)
11. [Rollback Plan](#rollback-plan)

---

## Phase Overview

| Phase | Days | Focus | Requirements | Success Criteria |
|-------|------|-------|--------------|------------------|
| **Phase 1** | 1-3 | Testing Foundation | 27 | ≥20 orchestrator tests, 100% MCP tool tests |
| **Phase 2** | 4-7 | Error Boundaries & Config | 47 | All orchestrators resilient, centralized timeouts |
| **Phase 3** | 8-10 | Performance | 28 | Async writes, connection pooling, P95 ≤2s |
| **Phase 4** | 11-14 | Code Quality | 18 | Enhanced retry, cleanup, browser pool bounds |

**Total Requirements Addressed:** 120 (out of 148 in REQUIREMENTS.md - 28 are cross-cutting)

---

## Phase 1: Testing Foundation (Days 1-3)

**Goal:** Establish comprehensive testing infrastructure to enable confident refactoring in later phases.

**Duration:** 3 days
**Risk Level:** LOW
**Dependencies:** None

### Day 1: Test Infrastructure Setup

#### Morning (4 hours)

**Task 1.1: Configure pytest for async testing** (1h)
- [ ] Install `pytest-asyncio`, `pytest-cov`
- [ ] Create/update `pytest.ini` with markers and async mode
- [ ] Configure coverage reporting (target ≥80%)
- [ ] Verify test runner works with existing tests

**Markers to configure:**
```ini
[pytest]
asyncio_mode = auto
markers =
    unit: Unit tests (no external dependencies)
    integration: Integration tests (may use mocks)
    remote: Remote tests (require live services)
    asyncio: Async tests
```

**Deliverable:** `pytest.ini` configured, coverage baseline established
**Requirements:** TECH-TST-05, TEST-FIX-01

---

**Task 1.2: Create conftest.py with base fixtures** (2h)
- [ ] Create `app/agentic/eol/tests/conftest.py`
- [ ] Add Azure SDK mock fixtures (Compute, Network, Cosmos, OpenAI)
- [ ] Add MCP server mock fixtures (Patch, Network, SRE)
- [ ] Add factory fixtures for orchestrators and agents

**Example fixture:**
```python
@pytest.fixture
def mock_cosmos_client():
    """Mock Cosmos DB client with common operations."""
    client = AsyncMock()
    client.read_item.return_value = {"id": "123", "data": "test"}
    client.upsert_item.return_value = {"status": "ok"}
    return client
```

**Deliverable:** Reusable test fixtures in `conftest.py`
**Requirements:** TEST-FIX-01 through TEST-FIX-07

---

**Task 1.3: Write orchestrator test template** (1h)
- [ ] Create test template for orchestrator unit tests
- [ ] Document test patterns (happy path, error cases, partial success)
- [ ] Create example test for one orchestrator method

**Deliverable:** Test template documented, one example test passing
**Requirements:** TST-05, TST-06, TST-07

---

#### Afternoon (4 hours)

**Task 1.4: EOL Orchestrator unit tests** (3h)
- [ ] Test happy path (all agents succeed)
- [ ] Test agent failure handling
- [ ] Test partial success scenario
- [ ] Test timeout handling
- [ ] Test circuit breaker integration
- [ ] Test error aggregation
- [ ] Test fallback mechanisms
- [ ] Test context propagation

**Target:** 8 tests for EOL orchestrator
**Deliverable:** `test_eol_orchestrator.py` with 8 passing tests
**Requirements:** TEST-UNIT-01, TST-01, TST-02

---

**Task 1.5: Coverage analysis and gaps identification** (1h)
- [ ] Run pytest with coverage report
- [ ] Identify coverage gaps in orchestrators
- [ ] Document critical paths needing tests
- [ ] Create test prioritization list for Day 2

**Deliverable:** Coverage report, gap analysis document
**Requirements:** TEST-COV-01, TEST-COV-02

---

### Day 2: Orchestrator Testing Expansion

#### Morning (4 hours)

**Task 2.1: SRE Orchestrator unit tests** (3h)
- [ ] Test happy path (successful SRE query)
- [ ] Test agent failure handling
- [ ] Test partial success scenario
- [ ] Test timeout handling
- [ ] Test circuit breaker integration
- [ ] Test error aggregation
- [ ] Test fallback mechanisms
- [ ] Test context propagation

**Target:** 8 tests for SRE orchestrator
**Deliverable:** `test_sre_orchestrator.py` with 8 passing tests
**Requirements:** TEST-UNIT-02, TST-02

---

**Task 2.2: Inventory Orchestrator unit tests** (1h)
- [ ] Test happy path (successful inventory query)
- [ ] Test agent failure handling
- [ ] Test partial success scenario
- [ ] Test timeout handling
- [ ] Test circuit breaker integration
- [ ] Test error aggregation
- [ ] Test fallback mechanisms
- [ ] Test context propagation

**Target:** 8 tests for Inventory orchestrator
**Deliverable:** `test_inventory_orchestrator.py` with 8 passing tests
**Requirements:** TEST-UNIT-03, TST-02

---

#### Afternoon (4 hours)

**Task 2.3: MCP server tool validation tests - Part 1** (4h)
- [ ] Patch MCP server: List all tools, validate schemas
- [ ] Network MCP server: List all tools, validate schemas
- [ ] Security/Compliance MCP server: List all tools, validate schemas

**Test pattern for each tool:**
- Validate input schema (required fields, types)
- Validate output schema (structure, required fields)
- Test error handling (invalid input, missing parameters)

**Deliverable:** 50% of MCP server tools validated
**Requirements:** TEST-MCP-01, TEST-MCP-02, TEST-MCP-03

---

### Day 3: MCP Testing & Utilities

#### Morning (4 hours)

**Task 3.1: MCP server tool validation tests - Part 2** (3h)
- [ ] SRE MCP server: List all tools, validate schemas
- [ ] Monitoring MCP server: List all tools, validate schemas
- [ ] Document any schema issues found

**Deliverable:** 100% of MCP server tools validated
**Requirements:** TEST-MCP-04, TEST-MCP-05, TEST-MCP-06, TST-03

---

**Task 3.2: Utility function tests** (1h)
- [ ] Test error aggregation utilities (5 tests)
- [ ] Test circuit breaker state transitions (6 tests)
- [ ] Test correlation ID middleware (4 tests)
- [ ] Test retry logic (6 tests)

**Deliverable:** 21 utility tests passing
**Requirements:** TEST-UNIT-04, TEST-UNIT-05, TEST-UNIT-06, TEST-UNIT-07

---

#### Afternoon (4 hours)

**Task 3.3: Integration test setup** (2h)
- [ ] Create integration test structure
- [ ] Test orchestrator with mocked Azure clients
- [ ] Test fire-and-forget task completion
- [ ] Test correlation ID propagation
- [ ] Test circuit breaker with Azure SDK
- [ ] Test structured logging output format

**Deliverable:** 5 integration tests passing
**Requirements:** TEST-INT-01 through TEST-INT-05

---

**Task 3.4: Phase 1 validation and documentation** (2h)
- [ ] Run full test suite with coverage
- [ ] Verify ≥70% coverage achieved
- [ ] Document test patterns and conventions
- [ ] Update ROADMAP.md with Phase 1 completion status
- [ ] Create Phase 1 summary report

**Success Criteria:**
- ✅ ≥20 orchestrator unit tests passing
- ✅ 100% MCP tool validation tests passing
- ✅ Test coverage ≥70%
- ✅ Test fixtures established in conftest.py

**Deliverable:** Phase 1 completion report, updated ROADMAP.md
**Requirements:** SUCCESS-P1-01 through SUCCESS-P1-04

---

**Commit Strategy for Phase 1:**
1. `test: configure pytest for async testing with markers` (Task 1.1)
2. `test: add base fixtures for Azure SDKs and MCP servers` (Task 1.2)
3. `test: add EOL orchestrator unit tests (8 tests)` (Task 1.4)
4. `test: add SRE orchestrator unit tests (8 tests)` (Task 2.1)
5. `test: add Inventory orchestrator unit tests (8 tests)` (Task 2.2)
6. `test: add MCP server tool validation tests (all servers)` (Task 2.3, 3.1)
7. `test: add utility function tests (error aggregation, circuit breaker)` (Task 3.2)
8. `test: add integration tests for orchestrator error handling` (Task 3.3)

**Total Commits:** 8 atomic commits

---

## Phase 2: Error Boundaries & Configuration (Days 4-7)

**Goal:** Implement robust error handling, centralized configuration, and comprehensive observability.

**Duration:** 4 days
**Risk Level:** MEDIUM (orchestrator changes require careful testing)
**Dependencies:** Phase 1 (test infrastructure required)

### Day 4: Error Handling Infrastructure

#### Morning (4 hours)

**Task 4.1: Implement error aggregation utilities** (2h)
- [ ] Create `utils/error_aggregation.py`
- [ ] Define `ErrorSeverity` enum (CRITICAL, HIGH, MEDIUM, LOW)
- [ ] Define `AgentError` dataclass
- [ ] Define `AggregatedResult` dataclass
- [ ] Implement `classify_error_severity()` function
- [ ] Add unit tests for error classification

**Code structure:**
```python
@dataclass
class AgentError:
    agent_name: str
    error_type: str
    message: str
    severity: ErrorSeverity
    timestamp: str
    context: Optional[Dict[str, Any]] = None
    retry_attempted: bool = False
```

**Deliverable:** `utils/error_aggregation.py` with tests
**Requirements:** TECH-ERR-01, TECH-ERR-02, TECH-ERR-03, ERR-02, ERR-06

---

**Task 4.2: Implement circuit breaker** (2h)
- [ ] Create `utils/circuit_breaker.py`
- [ ] Define `CircuitState` enum (CLOSED, OPEN, HALF_OPEN)
- [ ] Define `CircuitBreakerConfig` dataclass
- [ ] Implement `AsyncCircuitBreaker` class
- [ ] Add state transition logic (failure threshold, timeout)
- [ ] Add unit tests for circuit breaker

**Circuit breaker config:**
- `failure_threshold=5` (open after 5 failures)
- `timeout_seconds=60` (stay open for 60s)
- `half_open_attempts=1` (1 test call in half-open state)

**Deliverable:** `utils/circuit_breaker.py` with tests
**Requirements:** TECH-ERR-04, TECH-ERR-05, ERR-07, ERR-08

---

#### Afternoon (4 hours)

**Task 4.3: Implement error rate monitoring** (2h)
- [ ] Create `utils/error_rate_monitor.py`
- [ ] Define `ErrorRateMonitor` class
- [ ] Implement sliding window tracking (5 minutes default)
- [ ] Add `record_error()` and `record_success()` methods
- [ ] Add `get_error_rate()` and `is_unhealthy()` methods
- [ ] Add unit tests for error rate tracking

**Deliverable:** `utils/error_rate_monitor.py` with tests
**Requirements:** TECH-ERR-06, ERR-09

---

**Task 4.4: Update EOL orchestrator with error boundaries** (2h)
- [ ] Add error aggregation to agent execution
- [ ] Implement `return_exceptions=True` for all `gather()` calls
- [ ] Add error severity classification
- [ ] Implement graceful degradation (partial results)
- [ ] Add circuit breaker for Azure API calls
- [ ] Update unit tests to verify error handling
- [ ] Run integration tests

**Deliverable:** Updated `agents/eol_orchestrator.py` with error boundaries
**Requirements:** ERR-01, ERR-03, ERR-04, ERR-05, TECH-ERR-07

---

### Day 5: Orchestrator Error Boundaries Completion

#### Morning (4 hours)

**Task 5.1: Update SRE orchestrator with error boundaries** (2h)
- [ ] Add error aggregation to agent execution
- [ ] Fix `azure_ai_sre_agent.py` line 1431 to use `return_exceptions=True`
- [ ] Add error severity classification
- [ ] Implement graceful degradation
- [ ] Add circuit breaker for Azure API calls
- [ ] Update unit tests to verify error handling

**Deliverable:** Updated `agents/sre_orchestrator.py` and `agents/azure_ai_sre_agent.py`
**Requirements:** ERR-01, TECH-ERR-08

---

**Task 5.2: Update Inventory orchestrator with error boundaries** (1h)
- [ ] Add error aggregation to agent execution
- [ ] Ensure `return_exceptions=True` in all `gather()` calls
- [ ] Add error severity classification
- [ ] Implement graceful degradation
- [ ] Update unit tests to verify error handling

**Deliverable:** Updated `agents/inventory_orchestrator.py`
**Requirements:** ERR-01

---

**Task 5.3: Verify error handling across all orchestrators** (1h)
- [ ] Run all orchestrator tests
- [ ] Run integration tests with error scenarios
- [ ] Verify partial success handling
- [ ] Verify circuit breaker state transitions
- [ ] Document error handling patterns

**Deliverable:** All orchestrator tests passing, error handling validated
**Requirements:** ERR-03, ERR-04, ERR-05

---

#### Afternoon (4 hours)

**Task 5.4: Implement centralized timeout configuration** (3h)
- [ ] Create `utils/timeout_config.py`
- [ ] Define `TimeoutConfig` dataclass with clear defaults
- [ ] Document timeout rationale for each operation type
- [ ] Support environment variable overrides with `TIMEOUT_` prefix
- [ ] Implement backward compatibility for existing env vars
- [ ] Add configuration validation on startup
- [ ] Update orchestrators to use centralized timeouts

**Timeout defaults:**
- Connection timeout: 30s
- Tool execution timeout: 60s
- Total operation timeout: 300s
- AOAI timeout: 120s
- Azure API timeout: 90s

**Deliverable:** `utils/timeout_config.py` with orchestrators updated
**Requirements:** CFG-01, CFG-02, CFG-03, CFG-04, CFG-05, CFG-06

---

**Task 5.5: Create timeout migration guide** (1h)
- [ ] Document old env var → new env var mapping
- [ ] Provide migration examples
- [ ] Document validation errors and fixes
- [ ] Add troubleshooting section

**Deliverable:** `docs/TIMEOUT_MIGRATION.md`
**Requirements:** CFG-07

---

### Day 6: Observability Infrastructure

#### Morning (4 hours)

**Task 6.1: Implement correlation ID middleware** (2h)
- [ ] Create `middleware/correlation_id.py`
- [ ] Implement correlation ID generation/extraction
- [ ] Use `contextvars.ContextVar` for propagation
- [ ] Store in `request.state` for direct access
- [ ] Add correlation ID to response headers
- [ ] Add unit tests for middleware

**Deliverable:** `middleware/correlation_id.py` with tests
**Requirements:** TECH-OBS-01, TECH-OBS-02, OBS-01, OBS-02, OBS-04

---

**Task 6.2: Configure structured logging with structlog** (2h)
- [ ] Install `structlog`
- [ ] Create `utils/logging_config.py`
- [ ] Configure structlog processors:
  - `merge_contextvars`
  - `filter_by_level`
  - `add_logger_name`
  - `add_log_level`
  - `TimeStamper(fmt="iso")`
  - `JSONRenderer()` for production
- [ ] Add application metadata processor
- [ ] Add sensitive data redaction processor
- [ ] Initialize in `main.py`

**Deliverable:** `utils/logging_config.py` configured
**Requirements:** TECH-OBS-03, TECH-OBS-04, TECH-OBS-05, TECH-OBS-06, TECH-OBS-07, OBS-05, OBS-06, OBS-09

---

#### Afternoon (4 hours)

**Task 6.3: Implement request context middleware** (2h)
- [ ] Create `middleware/request_context.py`
- [ ] Clear context vars at request start
- [ ] Bind request metadata to structlog contextvars
- [ ] Log request started/completed
- [ ] Propagate context to nested operations
- [ ] Add unit tests for context propagation

**Deliverable:** `middleware/request_context.py` with tests
**Requirements:** TECH-OBS-08, OBS-03, OBS-07

---

**Task 6.4: Update all loggers to use structlog** (2h)
- [ ] Replace `logging.getLogger(__name__)` with `structlog.get_logger(__name__)`
- [ ] Update log statements to use structured format
- [ ] Add correlation IDs to all log statements (automatic via contextvars)
- [ ] Verify context propagation in logs
- [ ] Test structured log output format

**Deliverable:** All loggers using structlog, correlation IDs in logs
**Requirements:** OBS-03, OBS-06

---

### Day 7: OpenTelemetry Integration & Validation

#### Morning (4 hours)

**Task 7.1: Install and configure OpenTelemetry (optional)** (3h)
- [ ] Install OpenTelemetry packages:
  - `opentelemetry-api`
  - `opentelemetry-sdk`
  - `opentelemetry-instrumentation-fastapi`
  - `opentelemetry-exporter-otlp` (optional)
- [ ] Create `utils/tracing.py`
- [ ] Configure OTLP exporter (if backend available)
- [ ] Instrument FastAPI with `FastAPIInstrumentor`
- [ ] Link OpenTelemetry trace IDs with correlation IDs
- [ ] Add manual spans for critical operations

**Note:** This task is optional if no tracing backend is available. Can be deferred to post-production.

**Deliverable:** `utils/tracing.py` configured (if enabled)
**Requirements:** TECH-OBS-09, TECH-OBS-10, TECH-OBS-11, TECH-OBS-12, OBS-08

---

**Task 7.2: Phase 2 validation and testing** (1h)
- [ ] Run all unit tests
- [ ] Run integration tests
- [ ] Verify error boundaries in all orchestrators
- [ ] Verify correlation IDs in all logs
- [ ] Test timeout configuration changes
- [ ] Test circuit breaker behavior under load

**Deliverable:** All tests passing, Phase 2 features validated
**Requirements:** SUCCESS-P2-01 through SUCCESS-P2-05

---

#### Afternoon (4 hours)

**Task 7.3: End-to-end observability testing** (2h)
- [ ] Test request flow with correlation ID
- [ ] Verify correlation ID in response headers
- [ ] Query logs by correlation ID
- [ ] Test context propagation across async boundaries
- [ ] Test structured log format in production mode
- [ ] Verify OpenTelemetry traces (if enabled)

**Deliverable:** Observability validated end-to-end
**Requirements:** NFR-OBS-01, NFR-OBS-02, NFR-OBS-03

---

**Task 7.4: Phase 2 documentation and completion** (2h)
- [ ] Document error handling patterns
- [ ] Document timeout configuration
- [ ] Document observability architecture
- [ ] Update ROADMAP.md with Phase 2 completion
- [ ] Create Phase 2 summary report

**Success Criteria:**
- ✅ All orchestrators use `return_exceptions=True`
- ✅ Error aggregation with severity classification functional
- ✅ Circuit breaker pattern implemented for Azure APIs
- ✅ Centralized timeout configuration operational
- ✅ Correlation IDs in all logs and API responses

**Deliverable:** Phase 2 completion report, updated ROADMAP.md

---

**Commit Strategy for Phase 2:**
1. `feat: add error aggregation utilities with severity classification` (Task 4.1)
2. `feat: add async circuit breaker for Azure API protection` (Task 4.2)
3. `feat: add error rate monitoring with sliding window` (Task 4.3)
4. `refactor: add error boundaries to EOL orchestrator` (Task 4.4)
5. `refactor: add error boundaries to SRE orchestrator, fix return_exceptions` (Task 5.1)
6. `refactor: add error boundaries to Inventory orchestrator` (Task 5.2)
7. `feat: add centralized timeout configuration` (Task 5.4)
8. `docs: add timeout configuration migration guide` (Task 5.5)
9. `feat: add correlation ID middleware with contextvars` (Task 6.1)
10. `feat: configure structured logging with structlog` (Task 6.2)
11. `feat: add request context middleware` (Task 6.3)
12. `refactor: migrate all loggers to structlog` (Task 6.4)
13. `feat(optional): add OpenTelemetry instrumentation` (Task 7.1)

**Total Commits:** 12-13 atomic commits

---

## Phase 3: Performance Optimizations (Days 8-10)

**Goal:** Optimize Azure SDK usage, implement async patterns, and establish caching consistency.

**Duration:** 3 days
**Risk Level:** MEDIUM (performance changes need benchmarking)
**Dependencies:** Phase 2 (error handling and observability for monitoring)

**Plans:** 5 plans

Plans:
- [x] 03-01-PLAN.md — AzureSDKManager singleton: credential/client caching, connection pooling, FastAPI lifespan wiring ✅ 2026-03-01
- [x] 03-02-PLAN.md — Migrate all 6 agents to shared AzureSDKManager credential (sync + async) ✅ 2026-03-01
- [x] 03-03-PLAN.md — Fire-and-forget task set pattern: _background_tasks, _spawn_background(), async Cosmos writes ✅ 2026-03-01
- [x] 03-04-PLAN.md — Cache TTL standardization (cache_config.py) + async timeout guards in eol_orchestrator ✅ 2026-03-01
- [x] 03-05-PLAN.md — Phase 3 validation: 14 integration tests, P95 0.2-1ms (≤2s), human approved ✅ 2026-03-01

### Day 8: Azure SDK Optimization

#### Morning (4 hours)

**Task 8.1: Implement Azure SDK singleton manager** (3h)
- [ ] Create `utils/azure_client_manager.py`
- [ ] Define `AzureSDKManager` singleton class
- [ ] Implement credential caching with `DefaultAzureCredential`
- [ ] Enable persistent token cache with `TokenCachePersistenceOptions`
- [ ] Implement client caching (Compute, Network, Storage, etc.)
- [ ] Configure connection pooling for sync clients:
  - `pool_connections=10`
  - `pool_maxsize=20`
- [ ] Configure connection pooling for async clients:
  - `limit=100`
  - `limit_per_host=30`
- [ ] Set client timeouts:
  - `connection_timeout=30s`
  - `read_timeout=120s`
- [ ] Configure retry policy:
  - `retry_total=3`
  - `retry_mode='exponential'`

**Deliverable:** `utils/azure_client_manager.py` with singleton pattern
**Requirements:** TECH-AZ-01, TECH-AZ-02, TECH-AZ-03, TECH-AZ-04, TECH-AZ-05, TECH-AZ-06, PRF-03, PRF-04, PRF-05

---

**Task 8.2: Initialize Azure clients in FastAPI lifespan** (1h)
- [ ] Update `main.py` lifespan context
- [ ] Initialize `AzureSDKManager` on startup
- [ ] Create all Azure clients once
- [ ] Implement graceful shutdown to close clients
- [ ] Add unit tests for lifespan events

**Deliverable:** Azure clients initialized at startup
**Requirements:** TECH-AZ-07, TECH-AZ-08

---

#### Afternoon (4 hours)

**Task 8.3: Update orchestrators to use Azure SDK manager** (3h)
- [ ] Replace direct Azure client creation with singleton access
- [ ] Update EOL orchestrator
- [ ] Update SRE orchestrator
- [ ] Update Inventory orchestrator
- [ ] Update all agents using Azure clients
- [ ] Verify connection pooling in action
- [ ] Test credential caching

**Deliverable:** All orchestrators using Azure SDK manager
**Requirements:** PRF-03

---

**Task 8.4: Measure Azure SDK performance improvements** (1h)
- [ ] Benchmark credential acquisition time (before/after)
- [ ] Measure connection pool efficiency
- [ ] Monitor client initialization overhead
- [ ] Document performance gains

**Deliverable:** Performance benchmark report
**Requirements:** NFR-PRF-03, NFR-PRF-04

---

### Day 9: Async Patterns & Caching

#### Morning (4 hours)

**Task 9.1: Implement fire-and-forget task set pattern** (2h)
- [ ] Add `_background_tasks: Set[asyncio.Task]` to orchestrator classes
- [ ] Implement `_spawn_background()` method with:
  - Task creation with name
  - Add to background task set
  - Automatic cleanup callback (`discard` on completion)
  - Exception logging callback
- [ ] Implement `shutdown()` method to cancel background tasks
- [ ] Update MCP orchestrator embedding index build to use pattern
- [ ] Add unit tests for task lifecycle

**Deliverable:** Fire-and-forget pattern implemented in orchestrators
**Requirements:** TECH-TST-01, TECH-TST-02, TECH-TST-03, TECH-TST-04, PRF-02

---

**Task 9.2: Implement async Cosmos DB writes** (2h)
- [ ] Identify all Cosmos DB write operations
- [ ] Update to fire-and-forget pattern for non-critical writes
- [ ] Use background task set to prevent GC
- [ ] Add exception handling for write failures
- [ ] Log write completion/failure
- [ ] Measure write latency (should be <1s)

**Deliverable:** Async Cosmos writes with fire-and-forget
**Requirements:** PRF-01, PRF-02, NFR-PRF-02

---

#### Afternoon (4 hours)

**Task 9.3: Standardize cache TTL configuration** (2h)
- [ ] Create `utils/cache_config.py`
- [ ] Define standard TTLs for different data types:
  - Ephemeral: 5 minutes
  - Short-lived: 15 minutes
  - Medium-lived: 1 hour
  - Long-lived: 24 hours
- [ ] Update all cache implementations to use standard TTLs
- [ ] Document cache strategy (L1 in-memory + L2 Cosmos)
- [ ] Implement consistent cache key naming

**Deliverable:** `utils/cache_config.py` with standardized TTLs
**Requirements:** PRF-06, PRF-07

---

**Task 9.4: Implement async timeout management** (1h)
- [ ] Audit all async operations for timeout usage
- [ ] Add `asyncio.wait_for()` to operations without timeouts
- [ ] Use centralized timeout config from Phase 2
- [ ] Test timeout behavior with slow operations

**Deliverable:** All async operations with proper timeouts
**Requirements:** PRF-08

---

**Task 9.5: Performance testing preparation** (1h)
- [ ] Set up performance test scripts
- [ ] Define load testing scenarios
- [ ] Create baseline performance metrics
- [ ] Document P95/P99 latency targets

**Deliverable:** Performance test suite ready
**Requirements:** NFR-PRF-01

---

### Day 10: Performance Validation & Optimization

#### Morning (4 hours)

**Task 10.1: End-to-end performance testing** (3h)
- [ ] Run load tests with 50+ concurrent requests
- [ ] Measure P50/P95/P99 latencies
- [ ] Verify connection pool efficiency ≥80%
- [ ] Monitor memory usage (check for leaks)
- [ ] Test fire-and-forget task handling (100+ tasks)
- [ ] Monitor Azure SDK connection reuse
- [ ] Check credential caching effectiveness

**Deliverable:** Performance test results, bottlenecks identified
**Requirements:** NFR-PRF-01, NFR-PRF-04, NFR-PRF-05, NFR-SCL-01, NFR-SCL-02

---

**Task 10.2: Performance optimization based on results** (1h)
- [ ] Address any bottlenecks found
- [ ] Tune connection pool sizes if needed
- [ ] Adjust cache TTLs if needed
- [ ] Optimize hot paths

**Deliverable:** Performance optimizations applied
**Requirements:** NFR-PRF-01

---

#### Afternoon (4 hours)

**Task 10.3: Cache strategy validation** (2h)
- [ ] Test L1 (in-memory) cache hit rate
- [ ] Test L2 (Cosmos) cache hit rate
- [ ] Verify cache invalidation logic
- [ ] Test cache consistency across requests
- [ ] Monitor cache memory usage
- [ ] Verify cache reduces Azure API calls by ≥60%

**Deliverable:** Cache strategy validated, metrics documented
**Requirements:** PRF-07, NFR-SCL-04

---

**Task 10.4: Phase 3 validation and documentation** (2h)
- [ ] Run all tests (unit, integration, performance)
- [ ] Verify P95 latency ≤2s for EOL queries
- [ ] Verify async Cosmos writes complete <1s
- [ ] Verify connection pool efficiency ≥80%
- [ ] Document performance improvements
- [ ] Update ROADMAP.md with Phase 3 completion
- [ ] Create Phase 3 summary report

**Success Criteria:**
- ✅ Async Cosmos writes implemented with fire-and-forget pattern
- ✅ Azure SDK connection pooling configured and tested
- ✅ Credential/client singleton pattern implemented
- ✅ Cache TTL standardized across all caches
- ✅ P95 latency ≤2s for EOL queries (measured)

**Deliverable:** Phase 3 completion report, performance benchmarks
**Requirements:** SUCCESS-P3-01 through SUCCESS-P3-05

---

**Commit Strategy for Phase 3:**
1. `perf: add Azure SDK singleton manager with connection pooling` (Task 8.1)
2. `refactor: initialize Azure clients in FastAPI lifespan` (Task 8.2)
3. `refactor: update orchestrators to use Azure SDK manager` (Task 8.3)
4. `perf: implement fire-and-forget task set pattern` (Task 9.1)
5. `perf: convert Cosmos DB writes to async fire-and-forget` (Task 9.2)
6. `refactor: standardize cache TTL configuration` (Task 9.3)
7. `refactor: add async timeout management to all operations` (Task 9.4)
8. `perf: optimize hot paths based on load testing` (Task 10.2)

**Total Commits:** 8 atomic commits

---

## Phase 4: Code Quality & Polish (Days 11-14)

**Goal:** Enhance retry logic, clean up code quality issues, bound resource usage, and finalize production readiness.

**Duration:** 4 days
**Risk Level:** LOW
**Dependencies:** Phases 1-3 (full test coverage required)

### Day 11: Retry Logic Enhancement

#### Morning (4 hours)

**Task 11.1: Enhance utils/retry.py** (3h)
- [ ] Add `retry_on_result` parameter for result-based retry
- [ ] Add `on_retry` callback hook for observability
- [ ] Add `RetryStats` dataclass for tracking metrics
- [ ] Add `TryAgain` exception for explicit retry forcing
- [ ] Maintain backward compatibility with existing decorators
- [ ] Update docstrings with examples
- [ ] Add unit tests for new features

**Enhanced retry decorator signature:**
```python
@retry_async(
    retries=5,
    initial_delay=1.0,
    on_retry=log_retry_attempt,
    retry_on_result=lambda r: r is None or r.get("status") != "ready",
    stats=retry_stats,
)
```

**Deliverable:** Enhanced `utils/retry.py` with backward compatibility
**Requirements:** TECH-RET-01, TECH-RET-02, TECH-RET-03, TECH-RET-04, TECH-RET-05, CQ-01, CQ-02

---

**Task 11.2: Update operations to use enhanced retry** (1h)
- [ ] Add retry stats tracking to critical operations
- [ ] Add retry callbacks for observability
- [ ] Use result-based retry where appropriate
- [ ] Document retry configuration per operation type

**Deliverable:** Critical operations using enhanced retry logic
**Requirements:** CQ-01, CQ-02

---

#### Afternoon (4 hours)

**Task 11.3: Standardize logging levels** (3h)
- [ ] Audit all log statements project-wide
- [ ] Update to standard levels:
  - INFO: Normal flow (request started/completed, operation success)
  - WARNING: Recoverable issues (retry attempted, fallback used, deprecated API)
  - ERROR: Operation failures (API error, validation error, exception)
  - CRITICAL: System instability (out of memory, data corruption)
- [ ] Remove debug statements from production code paths
- [ ] Verify no sensitive data in logs
- [ ] Test log output with different log levels

**Deliverable:** Standardized logging levels project-wide
**Requirements:** CQ-04

---

**Task 11.4: Documentation update** (1h)
- [ ] Update README with new features
- [ ] Document error handling patterns
- [ ] Document retry configuration
- [ ] Document performance tuning
- [ ] Update API documentation

**Deliverable:** Updated documentation
**Requirements:** NFR-MNT-04

---

### Day 12: Code Cleanup & Resource Management

#### Morning (4 hours)

**Task 12.1: Remove unused imports** (2h)
- [ ] Use `autoflake` or manual review to find unused imports
- [ ] Remove unused imports from targeted files (from concern #14)
- [ ] Run tests to verify no breakage
- [ ] Run linter to verify code style

**Target files (from CONCERNS.md #14):**
- List specific files identified in concern #14

**Deliverable:** Unused imports removed, tests passing
**Requirements:** CQ-03

---

**Task 12.2: Implement bounded Playwright browser pool** (2h)
- [ ] Locate Playwright browser pool implementation
- [ ] Add max browser limit (default: 5 concurrent browsers)
- [ ] Implement pool manager with semaphore
- [ ] Add graceful cleanup on shutdown
- [ ] Release browsers after use
- [ ] Add unit tests for pool behavior
- [ ] Test resource limits under load

**Browser pool pattern:**
```python
class BrowserPool:
    def __init__(self, max_browsers: int = 5):
        self._semaphore = asyncio.Semaphore(max_browsers)
        self._browsers: Set[Browser] = set()

    async def acquire(self) -> Browser:
        async with self._semaphore:
            browser = await self._create_browser()
            self._browsers.add(browser)
            return browser

    async def shutdown(self):
        for browser in self._browsers:
            await browser.close()
```

**Deliverable:** Bounded Playwright browser pool
**Requirements:** CQ-05, CQ-06

---

#### Afternoon (4 hours)

**Task 12.3: Implement graceful shutdown for orchestrators** (2h)
- [ ] Add shutdown method to EOL orchestrator
- [ ] Add shutdown method to SRE orchestrator
- [ ] Add shutdown method to Inventory orchestrator
- [ ] Cancel all background tasks on shutdown
- [ ] Wait for task cancellation to complete
- [ ] Register shutdown handlers in FastAPI lifespan
- [ ] Test shutdown behavior

**Deliverable:** Graceful shutdown in all orchestrators
**Requirements:** CQ-07

---

**Task 12.4: Document agent hierarchy and debugging** (2h)
- [ ] Create architecture diagram showing 5-layer stack
- [ ] Document responsibility boundaries per layer
- [ ] Create debugging guide for tracing requests
- [ ] Document context propagation at each layer
- [ ] Identify simplification opportunities for future

**Deliverable:** Architecture documentation and debugging guide
**Requirements:** ARC-01, ARC-02, ARC-03, ARC-04

---

### Day 13: Integration Testing & Validation

#### Morning (4 hours)

**Task 13.1: Comprehensive integration testing** (3h)
- [ ] Test end-to-end EOL query flow
- [ ] Test end-to-end SRE query flow
- [ ] Test end-to-end Inventory query flow
- [ ] Test error scenarios (agent failure, timeout, API error)
- [ ] Test partial success scenarios
- [ ] Test circuit breaker behavior
- [ ] Test correlation ID propagation
- [ ] Test retry logic with various scenarios
- [ ] Test background task cleanup
- [ ] Test graceful shutdown

**Deliverable:** Comprehensive integration test suite passing
**Requirements:** NFR-REL-01, NFR-REL-02, NFR-REL-03

---

**Task 13.2: Regression testing** (1h)
- [ ] Run all existing tests to ensure no breakage
- [ ] Test backward compatibility for API contracts
- [ ] Test existing .env configurations still work
- [ ] Verify no breaking changes introduced

**Deliverable:** All regression tests passing
**Requirements:** SUCCESS-QG-02, SUCCESS-QG-03

---

#### Afternoon (4 hours)

**Task 13.3: Performance regression testing** (2h)
- [ ] Re-run performance tests from Phase 3
- [ ] Compare with baseline metrics
- [ ] Verify no performance degradation
- [ ] Document final performance numbers

**Deliverable:** Performance benchmarks showing no degradation
**Requirements:** SUCCESS-QG-05, NFR-PRF-01

---

**Task 13.4: Production readiness checklist** (2h)
- [ ] Verify error handling in all orchestrators
- [ ] Verify monitoring and observability
- [ ] Verify performance meets targets
- [ ] Verify resource management (no leaks)
- [ ] Verify security (no sensitive data in logs)
- [ ] Verify configuration management
- [ ] Verify documentation completeness

**Deliverable:** Production readiness checklist completed
**Requirements:** SUCCESS-P4-05

---

### Day 14: Final Polish & Documentation

#### Morning (4 hours)

**Task 14.1: Create production runbooks** (3h)
- [ ] Write deployment runbook
- [ ] Write operations runbook (monitoring, alerting)
- [ ] Write troubleshooting guide
- [ ] Write performance tuning guide
- [ ] Write incident response guide
- [ ] Document common issues and resolutions

**Deliverable:** Complete runbook set
**Requirements:** NFR-MNT-04

---

**Task 14.2: Update CONCERNS.md tracking** (1h)
- [ ] Mark all addressed concerns as complete
- [ ] Update status for partially addressed concerns
- [ ] Document any deferred concerns
- [ ] Link concerns to implemented features

**Deliverable:** Updated CONCERNS.md with completion status
**Requirements:** Project tracking

---

#### Afternoon (4 hours)

**Task 14.3: Final validation and testing** (2h)
- [ ] Run full test suite (unit, integration, performance)
- [ ] Verify all success criteria met
- [ ] Check code coverage ≥80%
- [ ] Verify all requirements addressed
- [ ] Run production checklist one final time

**Deliverable:** All tests passing, all criteria met
**Requirements:** All SUCCESS-P4 criteria

---

**Task 14.4: Project completion and handoff** (2h)
- [ ] Create final summary report
- [ ] Document all changes and improvements
- [ ] Create release notes
- [ ] Update ROADMAP.md with final status
- [ ] Create handoff documentation for operations team
- [ ] Schedule team review meeting

**Success Criteria:**
- ✅ Enhanced retry logic deployed with hooks and stats
- ✅ Unused imports removed from all targeted files
- ✅ Logging levels standardized project-wide
- ✅ Playwright browser pool bounded and tested
- ✅ Production checklist completed (error handling, monitoring, performance)

**Deliverable:** Project completion report, final documentation
**Requirements:** SUCCESS-P4-01 through SUCCESS-P4-05

---

**Commit Strategy for Phase 4:**
1. `feat: enhance retry logic with hooks and stats` (Task 11.1)
2. `refactor: update operations to use enhanced retry` (Task 11.2)
3. `refactor: standardize logging levels project-wide` (Task 11.3)
4. `chore: remove unused imports from all modules` (Task 12.1)
5. `feat: add bounded Playwright browser pool` (Task 12.2)
6. `feat: add graceful shutdown to all orchestrators` (Task 12.3)
7. `docs: add architecture and debugging guides` (Task 12.4)
8. `docs: add production runbooks and troubleshooting guide` (Task 14.1)

**Total Commits:** 8 atomic commits

---

## Critical Path Analysis

### Phase Dependencies

```
Phase 1 (Testing)
    ↓
Phase 2 (Error Handling & Config) ← Depends on Phase 1 tests
    ↓
Phase 3 (Performance) ← Depends on Phase 2 error handling
    ↓
Phase 4 (Code Quality) ← Depends on Phases 1-3
```

### Critical Path Tasks (No Slack)

1. **Phase 1, Day 1, Task 1.1**: Configure pytest (blocks all testing)
2. **Phase 1, Day 1, Task 1.2**: Create conftest.py (blocks all tests)
3. **Phase 2, Day 4, Task 4.1**: Error aggregation utilities (blocks orchestrator updates)
4. **Phase 2, Day 5, Task 5.4**: Centralized timeout config (blocks performance testing)
5. **Phase 2, Day 6, Task 6.2**: Structured logging (blocks observability)
6. **Phase 3, Day 8, Task 8.1**: Azure SDK manager (blocks performance optimizations)
7. **Phase 3, Day 10, Task 10.3**: Cache validation (blocks Phase 4)
8. **Phase 4, Day 14, Task 14.3**: Final validation (blocks completion)

### Tasks with Slack (Can be deferred if needed)

- **Phase 2, Task 7.1**: OpenTelemetry integration (optional, can be post-production)
- **Phase 4, Task 12.1**: Unused imports cleanup (nice-to-have)
- **Phase 4, Task 12.4**: Architecture documentation (can be completed post-launch)

### Parallel Work Opportunities

- **Days 1-3**: Multiple orchestrator tests can be written in parallel
- **Days 2-3**: MCP server tests can be parallelized across servers
- **Day 4-5**: Orchestrator updates can happen in parallel after infrastructure is ready
- **Day 9**: Cache standardization and async write conversion can happen in parallel

---

## Dependencies Matrix

| Task | Depends On | Blocks | Can Be Parallelized With |
|------|------------|--------|--------------------------|
| **Phase 1** | | | |
| 1.1 pytest config | None | All testing | None |
| 1.2 conftest.py | 1.1 | All unit tests | None |
| 1.4 EOL tests | 1.2 | None | 2.1, 2.2 (after Day 1) |
| 2.1 SRE tests | 1.2 | None | 1.4, 2.2 |
| 2.2 Inventory tests | 1.2 | None | 1.4, 2.1 |
| 2.3 MCP tests 1 | 1.2 | None | 3.1, 3.2 |
| 3.1 MCP tests 2 | 1.2 | None | 2.3, 3.2 |
| **Phase 2** | | | |
| 4.1 Error aggregation | Phase 1 complete | 4.4, 5.1, 5.2 | 4.2, 4.3 |
| 4.2 Circuit breaker | Phase 1 complete | 4.4, 5.1 | 4.1, 4.3 |
| 4.3 Error rate monitor | Phase 1 complete | None | 4.1, 4.2 |
| 4.4 EOL orchestrator | 4.1, 4.2 | None | None (sequential) |
| 5.1 SRE orchestrator | 4.1, 4.2, 4.4 | None | 5.2 (after 4.4) |
| 5.2 Inventory orch | 4.1, 4.2, 4.4 | None | 5.1 (after 4.4) |
| 5.4 Timeout config | 4.4, 5.1, 5.2 | Phase 3 | None |
| 6.1 Correlation ID | Phase 1 complete | 6.3 | 6.2 |
| 6.2 Structured logging | Phase 1 complete | 6.4 | 6.1 |
| 6.3 Request context | 6.1, 6.2 | None | None |
| 6.4 Update loggers | 6.2, 6.3 | None | None |
| 7.1 OpenTelemetry | 6.1, 6.2 | None | None (optional) |
| **Phase 3** | | | |
| 8.1 Azure SDK manager | Phase 2 complete | 8.2, 8.3 | None |
| 8.2 Lifespan init | 8.1 | 8.3 | None |
| 8.3 Update orchs | 8.1, 8.2 | None | None |
| 9.1 Task set pattern | Phase 2 complete | 9.2 | 9.3 |
| 9.2 Async Cosmos | 9.1 | None | 9.3, 9.4 |
| 9.3 Cache TTL | Phase 2 complete | None | 9.1, 9.2, 9.4 |
| 9.4 Timeout mgmt | Phase 2 (5.4) | None | 9.2, 9.3 |
| 10.1 Performance test | 8.3, 9.2, 9.3 | 10.2 | None |
| **Phase 4** | | | |
| 11.1 Enhance retry | Phase 3 complete | 11.2 | 11.3 |
| 11.3 Logging levels | Phase 3 complete | None | 11.1, 12.1 |
| 12.1 Unused imports | Phase 3 complete | None | 11.3, 12.2 |
| 12.2 Browser pool | Phase 3 complete | None | 12.1, 12.3 |
| 12.3 Graceful shutdown | Phase 3 complete | None | 12.2 |
| 13.1 Integration tests | 11.1, 12.3 | None | None |
| 14.1 Runbooks | All phases | None | 14.2 |
| 14.3 Final validation | All tasks | None | None |

---

## Risk Mitigation Strategy

### High-Risk Areas

#### Risk 1: Orchestrator Changes Break Workflows
**Impact:** HIGH
**Probability:** MEDIUM

**Mitigation:**
1. Write comprehensive unit tests BEFORE making changes (Phase 1)
2. Test each orchestrator independently with mocked dependencies
3. Use `return_exceptions=True` carefully - verify exception handling
4. Run integration tests after each orchestrator update
5. Deploy to staging environment for full testing
6. Have rollback plan ready (see Rollback Plan section)

**Detection:**
- Unit test failures
- Integration test failures
- Performance degradation in load tests
- Error rate spikes in logs

**Response:**
- Revert specific orchestrator changes
- Fix issues in isolated branch
- Re-run full test suite before re-merge

---

#### Risk 2: Timeout Changes Break Existing Behavior
**Impact:** MEDIUM
**Probability:** LOW

**Mitigation:**
1. Maintain backward compatibility with existing env vars
2. Document all timeout changes clearly
3. Test with existing configurations
4. Provide migration guide with examples
5. Add validation to detect invalid configs
6. Use generous defaults initially, tune later

**Detection:**
- Configuration validation errors on startup
- Timeout errors in logs
- Operations failing that previously succeeded
- User reports of timeout issues

**Response:**
- Adjust timeout values based on telemetry
- Update documentation with recommended values
- Add configuration troubleshooting guide

---

#### Risk 3: Performance Regressions
**Impact:** MEDIUM
**Probability:** LOW

**Mitigation:**
1. Establish baseline performance metrics before changes
2. Run load tests after each performance optimization
3. Compare P95/P99 latencies before/after
4. Monitor connection pool usage
5. Check for memory leaks in fire-and-forget tasks
6. Test under realistic load (50+ concurrent requests)

**Detection:**
- Load test results show increased latency
- Memory usage increases over time
- Connection pool exhaustion
- Azure SDK rate limiting errors

**Response:**
- Revert performance changes
- Profile application to find bottlenecks
- Adjust pool sizes, cache TTLs, or task limits
- Add performance monitoring alerts

---

#### Risk 4: Context Propagation Issues
**Impact:** MEDIUM
**Probability:** LOW

**Mitigation:**
1. Test correlation ID propagation at every layer
2. Verify contextvars work across async boundaries
3. Test background tasks with context copy
4. Add integration tests for context propagation
5. Log correlation IDs early to verify presence

**Detection:**
- Missing correlation IDs in logs
- Context variables not accessible in nested calls
- Background tasks missing context
- Integration test failures

**Response:**
- Review contextvars usage
- Ensure context is set in middleware
- Check background task context copying
- Add debug logging to trace context flow

---

#### Risk 5: Test Coverage Expansion Delays Schedule
**Impact:** LOW
**Probability:** MEDIUM

**Mitigation:**
1. Prioritize critical path tests (orchestrators, error handling)
2. Use test templates to speed up writing
3. Parallelize test writing across team members
4. Focus on high-value tests first
5. Defer nice-to-have tests to Phase 4 or post-launch
6. Time-box test writing tasks

**Detection:**
- Test writing tasks exceeding time estimates
- Phase 1 slipping past Day 3
- Coverage targets not met

**Response:**
- Focus on must-have tests only
- Reduce test count but maintain quality
- Extend Phase 1 by 1 day if critical
- Defer less critical tests to Phase 4

---

### Risk Response Escalation

| Risk Level | Response Time | Escalation Path |
|------------|---------------|-----------------|
| **LOW** | 1 day | Self-resolve, document in daily standup |
| **MEDIUM** | 4 hours | Escalate to tech lead, adjust plan if needed |
| **HIGH** | Immediate | Stop work, escalate to tech lead and PM, create mitigation plan |
| **CRITICAL** | Immediate | Emergency meeting, consider rollback, involve stakeholders |

---

## Integration Testing Strategy

### Integration Test Phases

#### Phase 1 Integration Tests (Day 3)
**Focus:** Orchestrator behavior with mocked dependencies

**Test Scenarios:**
1. Orchestrator executes agents in parallel
2. Orchestrator handles agent failure gracefully
3. Orchestrator returns partial results
4. Orchestrator respects timeouts
5. Correlation ID propagates through orchestrator

**Environment:** Local with mocked Azure SDKs

---

#### Phase 2 Integration Tests (Day 7)
**Focus:** Error handling and observability end-to-end

**Test Scenarios:**
1. Error aggregation with severity classification
2. Circuit breaker opens after threshold failures
3. Circuit breaker half-open state transitions
4. Correlation ID in logs and response headers
5. Structured log format validation
6. Context propagation across async boundaries

**Environment:** Local with mocked Azure SDKs + structured logging

---

#### Phase 3 Integration Tests (Day 10)
**Focus:** Performance and resource management

**Test Scenarios:**
1. Azure SDK connection pooling efficiency
2. Fire-and-forget task completion and cleanup
3. Async Cosmos writes without blocking
4. Cache hit rate and consistency
5. Load test with 50+ concurrent requests
6. Memory stability (no leaks)

**Environment:** Local or staging with real Azure services (optional)

---

#### Phase 4 Integration Tests (Day 13)
**Focus:** End-to-end production scenarios

**Test Scenarios:**
1. Complete EOL query flow (request → response)
2. Complete SRE query flow with multiple agents
3. Error scenarios (timeout, API failure, circuit breaker)
4. Retry logic with transient failures
5. Graceful shutdown with pending tasks
6. Regression testing (all existing features)

**Environment:** Staging environment with real Azure services

---

### Integration Test Checkpoints

| Checkpoint | Phase | Day | Criteria |
|------------|-------|-----|----------|
| **Checkpoint 1** | Phase 1 | Day 3 | All orchestrator tests passing, fixtures working |
| **Checkpoint 2** | Phase 2 | Day 7 | Error boundaries functional, logs structured |
| **Checkpoint 3** | Phase 3 | Day 10 | Performance targets met, no regressions |
| **Checkpoint 4** | Phase 4 | Day 13 | All tests passing, production ready |

**Gating Criteria:** Cannot proceed to next phase if checkpoint fails. Must resolve issues first.

---

### Test Environments

#### Development Environment
- **Purpose:** Unit testing, local development
- **Infrastructure:** Local machine, Docker containers (optional)
- **Azure Services:** Mocked via `AsyncMock`
- **Data:** Test fixtures, synthetic data

#### Staging Environment
- **Purpose:** Integration testing, load testing, pre-production validation
- **Infrastructure:** Azure App Service or Kubernetes
- **Azure Services:** Real Azure services in test subscription
- **Data:** Anonymized production-like data

#### Production Environment
- **Purpose:** Final deployment (post-refactoring)
- **Infrastructure:** Azure production environment
- **Azure Services:** Production Azure services
- **Data:** Real production data

---

## Commit Strategy

### Commit Guidelines

1. **Atomic Commits**: One logical change per commit
2. **Descriptive Messages**: Use conventional commit format
3. **Test Coverage**: Include tests in same commit as implementation
4. **Backward Compatibility**: Never break existing functionality
5. **Documentation**: Update docs in same commit as feature

### Conventional Commit Format

```
<type>(<scope>): <subject>

<body>

<footer>
```

**Types:**
- `feat`: New feature
- `fix`: Bug fix
- `refactor`: Code refactoring (no behavior change)
- `perf`: Performance improvement
- `test`: Add/update tests
- `docs`: Documentation
- `chore`: Maintenance tasks

**Example:**
```
feat(orchestrator): add error boundaries to EOL orchestrator

- Implement return_exceptions=True for agent execution
- Add error severity classification
- Implement graceful degradation with partial results
- Add unit tests for error scenarios

Addresses: ERR-01, ERR-03, TECH-ERR-07
```

### Commit Schedule by Phase

#### Phase 1: 8 commits
1. `test: configure pytest for async testing with markers`
2. `test: add base fixtures for Azure SDKs and MCP servers`
3. `test: add EOL orchestrator unit tests (8 tests)`
4. `test: add SRE orchestrator unit tests (8 tests)`
5. `test: add Inventory orchestrator unit tests (8 tests)`
6. `test: add MCP server tool validation tests (all servers)`
7. `test: add utility function tests (error aggregation, circuit breaker)`
8. `test: add integration tests for orchestrator error handling`

#### Phase 2: 12-13 commits
1. `feat: add error aggregation utilities with severity classification`
2. `feat: add async circuit breaker for Azure API protection`
3. `feat: add error rate monitoring with sliding window`
4. `refactor: add error boundaries to EOL orchestrator`
5. `refactor: add error boundaries to SRE orchestrator, fix return_exceptions`
6. `refactor: add error boundaries to Inventory orchestrator`
7. `feat: add centralized timeout configuration`
8. `docs: add timeout configuration migration guide`
9. `feat: add correlation ID middleware with contextvars`
10. `feat: configure structured logging with structlog`
11. `feat: add request context middleware`
12. `refactor: migrate all loggers to structlog`
13. `feat(optional): add OpenTelemetry instrumentation`

#### Phase 3: 8 commits
1. `perf: add Azure SDK singleton manager with connection pooling`
2. `refactor: initialize Azure clients in FastAPI lifespan`
3. `refactor: update orchestrators to use Azure SDK manager`
4. `perf: implement fire-and-forget task set pattern`
5. `perf: convert Cosmos DB writes to async fire-and-forget`
6. `refactor: standardize cache TTL configuration`
7. `refactor: add async timeout management to all operations`
8. `perf: optimize hot paths based on load testing`

#### Phase 4: 8 commits
1. `feat: enhance retry logic with hooks and stats`
2. `refactor: update operations to use enhanced retry`
3. `refactor: standardize logging levels project-wide`
4. `chore: remove unused imports from all modules`
5. `feat: add bounded Playwright browser pool`
6. `feat: add graceful shutdown to all orchestrators`
7. `docs: add architecture and debugging guides`
8. `docs: add production runbooks and troubleshooting guide`

**Total Commits:** 36-37 atomic commits over 2 weeks

### Branching Strategy

**Main Branch:** `main`
**Feature Branch:** `feature/production-readiness-refactoring`
**Sub-branches (optional):** `feature/prod-ready-phase-N` for each phase

**Workflow:**
1. Create feature branch from `main`
2. Work on phase tasks, commit atomically
3. Run full test suite before phase completion
4. Create PR for phase review
5. Merge phase to main after approval
6. Tag release after final phase

---

## Rollback Plan

### Rollback Triggers

**Automatic Rollback:**
- Test coverage drops below 60%
- Error rate exceeds 10% in staging
- P95 latency exceeds 5s (2.5x target)
- Critical bug blocking functionality

**Manual Rollback:**
- Performance degradation >20%
- User-reported issues affecting workflow
- Security vulnerability introduced
- Stakeholder decision

### Rollback Procedures

#### Immediate Rollback (Emergency)
**When:** Critical production issue

**Steps:**
1. Revert to last known good commit
2. Deploy previous version to staging
3. Verify functionality in staging
4. Deploy to production
5. Notify stakeholders
6. Post-mortem within 24 hours

**Time to Rollback:** <30 minutes

---

#### Graceful Rollback (Non-Emergency)
**When:** Non-critical issue, performance degradation

**Steps:**
1. Identify problematic commit(s)
2. Create revert branch
3. Revert specific commits (not entire feature)
4. Run full test suite
5. Deploy to staging for validation
6. Deploy to production after approval
7. Document issue and resolution

**Time to Rollback:** 2-4 hours

---

#### Phase Rollback
**When:** Entire phase needs to be reverted

**Steps:**
1. Identify last commit before phase
2. Create new branch from that commit
3. Cherry-pick any safe commits from phase
4. Run full test suite
5. Update documentation
6. Deploy to staging
7. Validate all functionality
8. Deploy to production

**Time to Rollback:** 4-8 hours

---

### Rollback Testing

Before any rollback:
1. Run full test suite
2. Verify error handling still works
3. Check performance benchmarks
4. Validate backward compatibility
5. Test with production-like load

### Rollback Communication

**Internal:**
- Immediate Slack notification to team
- Email to stakeholders within 1 hour
- Post-mortem document within 24 hours

**External (if needed):**
- Status page update
- Customer notification (if user-facing)
- Incident report

---

## Daily Standup Format

**Time:** 9:00 AM daily
**Duration:** 15 minutes

**Format:**
1. **Yesterday:** What was completed (with task IDs)
2. **Today:** What will be worked on (with task IDs)
3. **Blockers:** Any impediments or risks
4. **Metrics:** Test coverage, commits, issues

**Example:**
```
Yesterday:
- Completed Task 1.1: pytest configuration ✅
- Completed Task 1.2: conftest.py fixtures ✅
- Started Task 1.4: EOL orchestrator tests (50% done)

Today:
- Complete Task 1.4: EOL orchestrator tests
- Start Task 1.5: Coverage analysis

Blockers:
- None

Metrics:
- Test coverage: 62% (up from 60%)
- Commits: 2
- Tests added: 12
```

---

## Progress Tracking

### Requirement Completion Tracker

Track requirement completion in REQUIREMENTS.md with checkboxes.

**Status Codes:**
- ☐ Not started
- 🔄 In progress
- ✅ Complete
- ⚠️ Blocked
- ❌ Deferred

**Example:**
```markdown
- [x] ERR-01: All orchestrators use return_exceptions=True
- [x] ERR-02: Orchestrators aggregate errors with structured collection
- [ ] ERR-03: Orchestrators implement graceful degradation
```

### Metrics Dashboard (Daily Update)

| Metric | Baseline | Current | Target | Status |
|--------|----------|---------|--------|--------|
| Test Coverage | 60% | 62% → ... | ≥80% | 🔄 |
| Orchestrator Tests | 0 | 4 → ... | ≥20 | 🔄 |
| MCP Tool Tests | 0 | 0 → ... | 100% | ☐ |
| Error Boundaries | 0% | 0% → ... | 100% | ☐ |
| P95 Latency | ? | ? → ... | ≤2s | ☐ |
| Concerns Addressed | 0 | 0 → ... | 13 | ☐ |

### Phase Completion Tracker

| Phase | Status | Progress | Completion Date |
|-------|--------|----------|-----------------|
| Phase 1: Testing | ✅ | 100% | 2026-02-27 |
| Phase 2: Error/Config | ✅ | 100% | 2026-02-27 |
| Phase 3: Performance | ✅ | 100% (5/5 plans) | 2026-03-01 |
| Phase 4: Quality | ☐ | 0% | Day 14 (target) |

---

## Success Validation

### Final Checklist (Day 14)

#### Quantitative Metrics
- [ ] Test coverage ≥80% (current: ___)
- [ ] Orchestrator tests ≥20 (current: ___)
- [ ] MCP tool tests = 100% (current: ___)
- [ ] Error boundaries = 100% orchestrators (current: ___)
- [ ] P95 latency ≤2s (current: ___)
- [ ] Connection pool efficiency ≥80% (current: ___)
- [ ] Cache reduces API calls by ≥60% (current: ___)

#### Qualitative Validation
- [ ] Single agent failure doesn't crash workflows
- [ ] Timeout configuration is clear and documented
- [ ] Correlation IDs present in all logs
- [ ] Performance consistent under load (50+ requests)
- [ ] No memory leaks in fire-and-forget tasks
- [ ] Graceful shutdown works correctly
- [ ] All existing tests still pass
- [ ] No breaking changes in API contracts
- [ ] Documentation complete and accurate

#### Production Readiness Checklist
- [ ] Error handling: All orchestrators have error boundaries
- [ ] Configuration: Timeouts centralized and documented
- [ ] Performance: Async writes, connection pooling, caching optimized
- [ ] Observability: Correlation IDs, structured logging, tracing (optional)
- [ ] Testing: ≥80% coverage, comprehensive test suite
- [ ] Code Quality: Enhanced retry, cleanup, bounded resources
- [ ] Documentation: Runbooks, troubleshooting, architecture docs
- [ ] Security: No sensitive data in logs, credentials managed properly
- [ ] Resource Management: Bounded pools, graceful shutdown
- [ ] Monitoring: Error rates, performance metrics tracked

**Sign-off:** Tech Lead, Project Manager, Operations Lead

---

## Post-Completion Activities

### Week 3: Monitoring & Tuning
- [ ] Monitor error rates in production
- [ ] Monitor performance metrics (P95, P99 latency)
- [ ] Monitor Azure SDK connection pool usage
- [ ] Monitor cache hit rates
- [ ] Monitor memory usage for leaks
- [ ] Tune timeout values based on telemetry
- [ ] Tune connection pool sizes if needed
- [ ] Adjust cache TTLs based on usage patterns

### Week 4: Retrospective & Iteration
- [ ] Conduct team retrospective
- [ ] Document lessons learned
- [ ] Identify technical debt introduced
- [ ] Update CONCERNS.md with new concerns
- [ ] Plan next iteration (deferred concerns)
- [ ] Update architecture documentation
- [ ] Create training materials for team

### Future Iterations
- [ ] Address deferred concerns (secrets management, RBAC, CI/CD)
- [ ] Consider agent hierarchy simplification (Concern #8)
- [ ] Implement rate limiting (Concern #4)
- [ ] Add Cosmos DB RU monitoring (Concern #5)
- [ ] Improve health checks (Concern #6)
- [ ] Set up monitoring alerts (Concern #26)
- [ ] Implement disaster recovery (Concern #27)

---

## Appendix: Quick Reference

### Key Commands

**Run Tests:**
```bash
cd app/agentic/eol/tests
./run_tests.sh
pytest -m unit  # Unit tests only
pytest -m "not remote"  # Exclude remote tests
pytest --cov=app --cov-report=html  # Coverage report
```

**Run Performance Tests:**
```bash
pytest -m integration  # Integration tests
pytest tests/test_performance.py  # Performance tests
```

**Check Code Quality:**
```bash
ruff check .  # Linting
autoflake --remove-all-unused-imports -r .  # Find unused imports
```

### Key Files

| File | Purpose |
|------|---------|
| `pytest.ini` | Test configuration |
| `conftest.py` | Test fixtures |
| `ROADMAP.md` | This document |
| `REQUIREMENTS.md` | Detailed requirements |
| `PROJECT.md` | Project overview |
| `CONCERNS.md` | Issue tracking |

### Contact Points

| Role | Responsibility |
|------|----------------|
| Tech Lead | Technical decisions, architecture review |
| Project Manager | Timeline, stakeholder communication |
| Operations Lead | Deployment, monitoring setup |
| QA Lead | Test strategy, validation |

---

**Document Version:** 1.0
**Last Updated:** 2026-02-27
**Status:** APPROVED - Ready for Implementation

---

## Change Log

| Date | Version | Changes | Author |
|------|---------|---------|--------|
| 2026-02-27 | 1.0 | Initial roadmap created | Claude Code |

---

**Next Steps:**
1. Review and approve roadmap with team
2. Set up project tracking (Jira, GitHub Projects, etc.)
3. Schedule daily standups
4. Begin Phase 1, Day 1, Task 1.1 ✅
