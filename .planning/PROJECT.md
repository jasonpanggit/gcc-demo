# GCC Demo Platform: Production Readiness Refactoring

## Project Overview

**Type:** Refactoring & Technical Debt Resolution
**Timeline:** 2 weeks (4 phases)
**Status:** Planning
**Started:** 2026-02-27

---

## Problem Statement

The GCC Demo platform has accumulated technical debt across error handling, configuration management, performance optimizations, and testing that prevents production deployment. Currently:

- **Critical Risk**: Orchestrators lack error boundaries - single agent failures crash entire workflows (#3)
- **High Complexity**: Timeout configuration scattered across 15+ env vars, making tuning difficult (#7)
- **Testing Gaps**: Orchestrators and MCP server tools have minimal test coverage (#22, #23)
- **Performance Issues**: Synchronous Cosmos DB writes, missing connection pooling, inconsistent caching (#19, #20, #9)
- **Observability Gaps**: No request correlation IDs for distributed tracing (#11)
- **Code Quality**: Inconsistent retry logic, unused imports, logging level issues (#12, #14, #15)
- **Architecture Complexity**: 5-layer agent hierarchy difficult to debug (#8)
- **Resource Management**: Playwright browser pool can exhaust resources (#21)

These issues prevent confident production deployment and make debugging difficult.

---

## Success Criteria

### Primary Goals (Must-Have)

1. **Error Resilience**: All orchestrators handle agent failures gracefully without cascading failures
2. **Configuration Clarity**: Centralized timeout configuration with clear defaults and tuning guidance
3. **Test Coverage**: ≥80% coverage for orchestrators, 100% MCP tool validation tests
4. **Production Readiness**: Pass production checklist (error handling, monitoring, performance)

### Secondary Goals (Should-Have)

5. **Performance**: Async Cosmos writes, Azure SDK connection pooling, optimized caching
6. **Observability**: Request correlation IDs in all logs and API responses
7. **Code Quality**: Consistent retry logic, clean imports, standardized logging levels
8. **Resource Management**: Bounded Playwright browser pool

### Stretch Goals (Nice-to-Have)

9. **Architecture Simplification**: Reduce agent hierarchy complexity where possible
10. **Load Testing**: Performance benchmarks and load tests

---

## Constraints & Risks

### Constraints

- **No Breaking Changes**: Public API contracts must remain stable
- **Backward Compatibility**: Existing .env configurations must still work
- **Minimal Disruption**: Changes must be incremental and testable
- **2-Week Timeline**: Focus on critical/high priority items first

### Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| **Orchestrator changes break existing workflows** | HIGH | Unit tests first, staged rollout |
| **Timeout consolidation breaks existing configs** | MEDIUM | Maintain backward compat, add migration guide |
| **Performance changes introduce new bugs** | MEDIUM | Benchmarking, load testing before prod |
| **Test coverage expansion delays other work** | LOW | Prioritize critical paths, parallel testing effort |

---

## Key Stakeholders

- **Development Team**: Implementation and testing
- **Operations**: Deployment and monitoring
- **End Users**: Reliability and performance improvements

---

## Dependencies

### Technical Dependencies

- Existing codebase: 169 Python files, 41 agents, 20 routers, 71 utilities
- Python 3.13 + FastAPI ecosystem
- Azure services: AOAI, Cosmos DB, Log Analytics
- MCP architecture: 9 local servers + external Azure MCP

### External Dependencies

- None (internal refactoring project)

---

## Approach Summary

### Phase 1: Testing Foundation (Days 1-3)
- Add unit tests for orchestrators (EOL, SRE, Inventory)
- Add MCP server tool validation tests
- Establish test fixtures and patterns

### Phase 2: Error Boundaries & Config (Days 4-7)
- Implement `return_exceptions=True` in orchestrators
- Centralize timeout configuration
- Add request correlation IDs

### Phase 3: Performance Optimizations (Days 8-10)
- Async Cosmos DB writes
- Azure SDK connection pooling
- Standardize cache TTL configuration

### Phase 4: Code Quality & Polish (Days 11-14)
- Standardize retry logic
- Clean unused imports and logging levels (targeted)
- Bounded Playwright browser pool
- Documentation and runbooks

---

## Out of Scope

The following concerns are explicitly **OUT OF SCOPE** for this 2-week sprint:

- **Secrets Management** (#1) - Requires Key Vault provisioning and migration plan
- **Terraform State Security** (#2) - Infrastructure change, separate effort
- **Rate Limiting** (#4) - Requires capacity planning and testing
- **Cosmos DB RU Monitoring** (#5) - Observability project, separate effort
- **Health Check Improvements** (#6) - Post-production deployment
- **RBAC Authentication** (#18) - Security initiative, separate project
- **CI/CD Pipeline** (#25) - DevOps project, separate effort
- **Monitoring Alerts** (#26) - Post-production deployment
- **Disaster Recovery** (#27) - Separate operational project

These will be tracked separately and addressed in future iterations.

---

## Metrics for Success

### Quantitative Metrics

- **Test Coverage**: Increase from ~60% to ≥80%
- **Orchestrator Tests**: 0 → ≥20 unit tests
- **MCP Tool Tests**: 0 → 100% tool coverage
- **Error Handling**: 0% → 100% orchestrators with error boundaries
- **Performance**: P95 latency ≤ 2s for EOL queries
- **Code Quality**: 0 → 13 concerns addressed

### Qualitative Metrics

- Orchestrator failures don't crash entire workflows
- Timeout configuration is clear and documented
- Debugging is easier with correlation IDs
- Performance is consistent under load

---

## Technical Context

### Current Architecture

```
User Request
  → FastAPI Router
    → Orchestrator (EOL/SRE/Inventory)
      → Domain Agents (Microsoft/Monitor/OS)
        → Sub-Agents (Patch/Network)
          → MCP Clients
            → MCP Servers
              → Azure SDKs
```

**Concerns:**
- 5-layer call stack (concern #8)
- No error boundaries at orchestrator level (concern #3)
- No correlation IDs across layers (concern #11)

### Testing Gaps

**Current State:**
- 16 test files, mostly unit tests
- 0 orchestrator-specific tests
- Partial MCP server coverage

**Target State:**
- ≥20 orchestrator unit tests
- 100% MCP tool validation
- Integration tests for error scenarios

### Configuration Complexity

**Current State:**
- 15+ timeout env vars: `SRE_AGENT_TOOL_TIMEOUT`, `SRE_AGENT_TOTAL_TIMEOUT`, `PATCH_OPERATION_TIMEOUT`, etc.
- Scattered across codebase
- No clear defaults or tuning guidance

**Target State:**
- Centralized `TimeoutConfig` dataclass
- Clear defaults with rationale
- Per-operation-type configuration

---

## Research Topics

Before implementation, research the following:

1. **Error Handling Patterns**
   - `asyncio.gather(return_exceptions=True)` best practices
   - Circuit breaker patterns in Python
   - Error aggregation strategies

2. **Azure SDK Best Practices**
   - Connection pooling patterns
   - Credential caching
   - SDK client lifecycle management

3. **Python Async Patterns**
   - Fire-and-forget task patterns (`asyncio.create_task`)
   - Background task management
   - Task cancellation and cleanup

4. **Testing Strategies**
   - Async test patterns with pytest-asyncio
   - Mocking Azure SDK clients
   - MCP server test fixtures

5. **Observability**
   - Correlation ID propagation patterns
   - Structured logging best practices
   - Distributed tracing integration

---

## Version History

- **v1.0** (2026-02-27): Initial project definition
  - Scope: 13 concerns from CONCERNS.md
  - Timeline: 2 weeks, 4 phases
  - Approach: Testing first, incremental refactoring
