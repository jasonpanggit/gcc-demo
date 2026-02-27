# Phase 3: Agent & API Coverage - Implementation Plan

**Duration:** TBD
**Status:** Planning
**Goal:** Increase test coverage to 40-50% by testing core agents and API routers

---

## Current State

**Phase 2 Complete:**
- ✅ 719 passing tests total
- ✅ 83 Phase 2 tests (error handling & observability)
- ✅ Coverage: ~18-20% (estimated)
- ✅ 5 new utilities with 93% coverage

**Phase 3 Entry:**
- Strong foundation of error handling utilities
- Comprehensive test patterns established
- Ready to scale testing to agents and APIs

---

## Phase 3 Priorities

### Priority 1: Core Agent Testing (Week 1-2)

**Target Agents (Top 10):**
1. `microsoft_agent.py` - Critical for EOL queries
2. `redhat_agent.py` - Major vendor
3. `ubuntu_agent.py` - Major vendor
4. `sre_sub_agent.py` - SRE operations
5. `patch_sub_agent.py` - Patch management
6. `monitor_agent.py` - Monitoring
7. `inventory_agent.py` - Resource inventory
8. `endoflife_agent.py` - EOL API integration
9. `base_eol_agent.py` - Base class for EOL agents
10. `domain_sub_agent.py` - Base class for domain agents

**Test Strategy:**
- 8-10 tests per agent
- Focus on: query execution, response parsing, error handling
- Use Phase 2 utilities (error aggregation, circuit breaker)
- Mock Azure SDK and MCP calls

**Expected:** ~80 tests, +5-7% coverage

---

### Priority 2: API Router Testing (Week 2-3)

**Target Routers (Top 8):**
1. `eol.py` - EOL endpoints
2. `azure_mcp.py` - Azure MCP integration
3. `inventory.py` - Inventory endpoints
4. `azure_ai_sre.py` - SRE endpoints
5. `health.py` - Health checks
6. `cache.py` - Cache management
7. `metrics.py` - Metrics endpoints
8. `alerts.py` - Alert management

**Test Strategy:**
- 6-8 tests per router
- Focus on: request validation, response format, error handling
- Test authentication/authorization
- Mock orchestrator calls

**Expected:** ~50 tests, +4-6% coverage

---

### Priority 3: Cache Layer Testing (Week 3)

**Target Modules:**
- `cosmos_cache.py`
- `eol_cache.py`
- `inventory_cache.py`
- `sre_cache.py`
- `resource_inventory_cache.py`

**Test Strategy:**
- 6 tests per cache module
- Focus on: hit/miss, TTL, eviction
- Mock Cosmos DB calls

**Expected:** ~30 tests, +2-3% coverage

---

### Priority 4: Integration Tests (Week 4)

**Integration Scenarios:**
- Full EOL query flow (API → Orchestrator → Agent → MCP)
- Full SRE query flow
- Full Inventory query flow
- Cache integration with orchestrators
- Error handling across full stack

**Expected:** ~20 tests, +1-2% coverage

---

## Success Criteria

| Criterion | Target |
|-----------|--------|
| Core agent tests | 80+ |
| API router tests | 50+ |
| Cache layer tests | 30+ |
| Integration tests | 20+ |
| Total Phase 3 tests | 180+ |
| Coverage increase | +12-18% |
| Total coverage | 40-50% |

---

## Test Patterns to Use

### Agent Testing Pattern
```python
@pytest.mark.unit
@pytest.mark.asyncio
class TestMicrosoftAgent:
    async def test_query_execution(self):
        agent = MicrosoftAgent()
        result = await agent.query("Windows Server 2019")
        assert result is not None

    async def test_error_handling(self):
        agent = MicrosoftAgent()
        with error_aggregation:
            result = await agent.query_with_error()
```

### API Router Testing Pattern
```python
@pytest.mark.integration
class TestEOLRouter:
    def test_eol_query_endpoint(self, client):
        response = client.post("/api/eol/query", json={"query": "test"})
        assert response.status_code == 200

    def test_invalid_request(self, client):
        response = client.post("/api/eol/query", json={})
        assert response.status_code == 400
```

### Cache Testing Pattern
```python
@pytest.mark.unit
@pytest.mark.asyncio
class TestEOLCache:
    async def test_cache_hit(self):
        cache = EOLCache()
        await cache.set("key", "value", ttl=60)
        result = await cache.get("key")
        assert result == "value"
```

---

## Execution Strategy

### Week 1: Core Agents (40 tests)
- Day 1-2: Microsoft, RedHat, Ubuntu agents (24 tests)
- Day 3-4: SRE, Patch, Monitor agents (16 tests)

### Week 2: More Agents + APIs (50 tests)
- Day 1-2: Inventory, Endoflife, Base agents (24 tests)
- Day 3-4: API routers - EOL, Azure MCP, Inventory (26 tests)

### Week 3: APIs + Cache (60 tests)
- Day 1-2: API routers - SRE, Health, Cache, Metrics (30 tests)
- Day 3-4: Cache modules (30 tests)

### Week 4: Integration (20 tests)
- Day 1-2: E2E flows (12 tests)
- Day 3-4: Validation and documentation (8 tests)

---

## Dependencies

### Test Infrastructure (Already Have)
- ✅ pytest with asyncio
- ✅ pytest-cov for coverage
- ✅ conftest.py with fixtures
- ✅ Mock patterns established

### Utilities (Already Have)
- ✅ Error aggregator
- ✅ Correlation ID
- ✅ Circuit breaker
- ✅ Error boundary
- ✅ Timeout config

### Need to Create
- Agent test fixtures
- API client fixtures
- Cache mock fixtures

---

## Risk Mitigation

### Potential Risks
1. **Agent complexity** - Some agents may be complex to mock
2. **API dependencies** - Routers depend on orchestrators
3. **Cache dependencies** - Need Cosmos DB mocking
4. **Test execution time** - Large test suite may be slow

### Mitigation Strategies
1. Start with simpler agents, build patterns
2. Mock orchestrators at boundary
3. Use in-memory cache for tests
4. Run tests in parallel where possible

---

## Deliverables

### Code
- ~180 new test files/functions
- Agent test fixtures
- API test fixtures
- Cache test fixtures

### Documentation
- Phase 3 progress reports
- Test patterns documentation
- Coverage analysis

### Metrics
- Coverage report (target 40-50%)
- Test execution time
- Success rate

---

## Next Steps

1. **Review this plan** - Confirm priorities and timeline
2. **Set up fixtures** - Create agent and API test fixtures
3. **Start Week 1** - Begin with core agent testing
4. **Daily standup** - Track progress and adjust

---

**Created:** 2026-02-27
**Status:** Ready for review
**Estimated Duration:** 4 weeks
**Expected Outcome:** 40-50% total coverage, 180+ new tests
