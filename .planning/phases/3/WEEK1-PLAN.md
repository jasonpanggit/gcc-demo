# Phase 3 - Week 1 Plan: Core Agent Testing

**Duration:** Week 1 (5 days)
**Goal:** Test 10 core agents with 80+ tests
**Target Coverage:** +5-7%

---

## Day 1-2: Vendor EOL Agents (30 tests)

### Target Agents
1. **microsoft_agent.py** (10 tests)
   - Test scraping logic
   - Test cache integration
   - Test error handling
   - Test URL mapping
   - Test response parsing

2. **redhat_agent.py** (10 tests)
   - Similar pattern to Microsoft
   - Test RedHat-specific URLs
   - Test response format

3. **ubuntu_agent.py** (10 tests)
   - Similar pattern to Microsoft
   - Test Ubuntu-specific parsing
   - Test version detection

### Test Structure
```python
@pytest.mark.unit
@pytest.mark.asyncio
class TestMicrosoftAgent:
    """Test MicrosoftEOLAgent functionality."""

    async def test_agent_initialization(self):
        """Test agent initializes correctly."""

    async def test_query_execution(self):
        """Test successful query execution."""

    async def test_error_handling(self):
        """Test error handling with error aggregation."""

    async def test_cache_integration(self):
        """Test cache hit/miss scenarios."""

    async def test_timeout_handling(self):
        """Test timeout configuration."""
```

---

## Day 3-4: Domain Sub-Agents (30 tests)

### Target Agents
4. **sre_sub_agent.py** (10 tests)
   - Test SRE-specific queries
   - Test tool routing
   - Test ReAct loop
   - Test system prompt

5. **patch_sub_agent.py** (10 tests)
   - Test patch assessment
   - Test patch installation
   - Test compliance checking

6. **monitor_agent.py** (10 tests)
   - Test monitoring queries
   - Test alert generation
   - Test metric aggregation

---

## Day 5: Base Classes & Inventory (20 tests)

### Target Agents
7. **base_eol_agent.py** (6 tests)
   - Test base class methods
   - Test common functionality

8. **domain_sub_agent.py** (6 tests)
   - Test base domain patterns
   - Test tool delegation

9. **inventory_agent.py** (8 tests)
   - Test inventory queries
   - Test resource discovery
   - Test cache integration

---

## Test Fixtures Needed

### Create in conftest.py
```python
@pytest.fixture
def mock_microsoft_agent():
    """Mock Microsoft agent for testing."""

@pytest.fixture
def mock_http_response():
    """Mock HTTP response for scraping tests."""

@pytest.fixture
def mock_eol_cache():
    """Mock EOL cache for testing."""

@pytest.fixture
def error_aggregator():
    """Error aggregator for agent error handling."""
```

---

## Mocking Strategy

### External Dependencies to Mock
1. **HTTP Requests** - Mock requests library
2. **Cosmos DB** - Mock cache operations
3. **Azure SDK** - Mock Azure client calls
4. **MCP Tools** - Mock MCP tool responses

### Use Phase 2 Utilities
- Error aggregator for error tracking
- Circuit breaker for failure scenarios
- Correlation ID for tracing
- Timeout config for timeout tests

---

## Success Criteria

| Metric | Target | Day 1-2 | Day 3-4 | Day 5 |
|--------|--------|---------|---------|-------|
| Tests created | 80 | 30 | 30 | 20 |
| Agents covered | 9 | 3 | 3 | 3 |
| Coverage gain | +5-7% | +2% | +2% | +1-3% |

---

## Execution Plan

### Day 1: Setup + Microsoft Agent
- Create agent test fixtures
- Write MicrosoftAgent tests
- Run and validate (10 passing)

### Day 2: RedHat + Ubuntu Agents
- Write RedHat tests
- Write Ubuntu tests
- Run and validate (20 passing total)

### Day 3: SRE + Patch Sub-Agents
- Write SRE sub-agent tests
- Write Patch sub-agent tests
- Run and validate (40 passing total)

### Day 4: Monitor Agent
- Write Monitor agent tests
- Run and validate (50 passing total)

### Day 5: Base Classes + Inventory
- Write base class tests
- Write inventory agent tests
- Week 1 validation (70-80 passing)

---

## Deliverables

### Code
- `test_microsoft_agent.py` (10 tests)
- `test_redhat_agent.py` (10 tests)
- `test_ubuntu_agent.py` (10 tests)
- `test_sre_sub_agent.py` (10 tests)
- `test_patch_sub_agent.py` (10 tests)
- `test_monitor_agent.py` (10 tests)
- `test_base_eol_agent.py` (6 tests)
- `test_domain_sub_agent.py` (6 tests)
- `test_inventory_agent.py` (8 tests)

### Documentation
- Week 1 progress report
- Coverage delta analysis

---

**Status:** Ready to start
**Next:** Create agent test fixtures and begin Day 1
