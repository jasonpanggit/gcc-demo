"""
Unit tests for MCP Orchestrator enhancements.
Tests circuit breaker, caching, retry logic, and timeout configuration.
"""
import pytest
import asyncio
import sys
import os
from datetime import datetime, timedelta

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import only the classes we need to test
from agents.mcp_orchestrator import CircuitBreaker, ToolResultCache


class TestCircuitBreaker:
    """Test circuit breaker functionality."""
    
    def test_circuit_starts_closed(self):
        """Circuit should start in closed state."""
        cb = CircuitBreaker(failure_threshold=3)
        assert cb.can_execute("test_tool")
        assert cb.states.get("test_tool", "closed") == "closed"
    
    def test_circuit_opens_after_threshold_failures(self):
        """Circuit should open after reaching failure threshold."""
        cb = CircuitBreaker(failure_threshold=3)
        
        # Record failures
        for _ in range(3):
            cb.record_failure("test_tool")
        
        # Circuit should be open
        assert not cb.can_execute("test_tool")
        assert cb.states["test_tool"] == "open"
    
    def test_circuit_transitions_to_half_open_after_timeout(self):
        """Circuit should transition to half-open after timeout."""
        cb = CircuitBreaker(failure_threshold=2, timeout=0.1)
        
        # Open the circuit
        cb.record_failure("test_tool")
        cb.record_failure("test_tool")
        assert cb.states["test_tool"] == "open"
        
        # Wait for timeout
        import time
        time.sleep(0.2)
        
        # Should transition to half-open
        assert cb.can_execute("test_tool")
        assert cb.states["test_tool"] == "half_open"
    
    def test_circuit_closes_after_success_threshold(self):
        """Circuit should close after reaching success threshold in half-open state."""
        cb = CircuitBreaker(failure_threshold=2, success_threshold=2)
        
        # Open the circuit
        cb.record_failure("test_tool")
        cb.record_failure("test_tool")
        cb.states["test_tool"] = "half_open"  # Manually transition for testing
        
        # Record successes
        cb.record_success("test_tool")
        cb.record_success("test_tool")
        
        # Circuit should be closed
        assert cb.can_execute("test_tool")
        assert cb.states["test_tool"] == "closed"
    
    def test_get_status_returns_all_states(self):
        """get_status should return comprehensive circuit state."""
        cb = CircuitBreaker()
        
        cb.record_failure("tool1")
        cb.record_failure("tool2")
        
        status = cb.get_status()
        
        assert "circuit_states" in status
        assert "failure_counts" in status
        assert "success_counts" in status
        assert status["failure_counts"]["tool1"] == 1
        assert status["failure_counts"]["tool2"] == 1


class TestToolResultCache:
    """Test tool result caching functionality."""
    
    def test_cache_stores_and_retrieves_results(self):
        """Cache should store and retrieve results correctly."""
        cache = ToolResultCache(ttl_seconds=60)
        tool_name = "test_tool"
        args = {"arg1": "value1", "arg2": 123}
        result = {"success": True, "data": "test_data"}
        
        # Store result
        cache.set(tool_name, args, result)
        
        # Retrieve result
        cached = cache.get(tool_name, args)
        
        assert cached is not None
        assert cached["success"] is True
        assert cached["data"] == "test_data"
    
    def test_cache_returns_none_for_missing_entry(self):
        """Cache should return None for non-existent entries."""
        cache = ToolResultCache()
        
        result = cache.get("nonexistent_tool", {"arg": "value"})
        
        assert result is None
    
    def test_cache_expires_after_ttl(self):
        """Cache should expire entries after TTL."""
        cache = ToolResultCache(ttl_seconds=0.1)
        tool_name = "test_tool"
        args = {"arg1": "value1"}
        result = {"success": True, "data": "test"}
        
        # Store result
        cache.set(tool_name, args, result)
        
        # Wait for expiration
        import time
        time.sleep(0.2)
        
        # Should be expired
        cached = cache.get(tool_name, args)
        assert cached is None
    
    def test_cache_evicts_oldest_when_full(self):
        """Cache should evict oldest entries when full."""
        cache = ToolResultCache(max_size=2)
        
        # Add three entries
        cache.set("tool1", {"a": 1}, {"data": "1"})
        cache.set("tool2", {"a": 2}, {"data": "2"})
        cache.set("tool3", {"a": 3}, {"data": "3"})
        
        # First entry should be evicted
        assert cache.get("tool1", {"a": 1}) is None
        assert cache.get("tool2", {"a": 2}) is not None
        assert cache.get("tool3", {"a": 3}) is not None
    
    def test_cache_invalidation_by_tool_name(self):
        """Cache should invalidate entries for specific tool."""
        cache = ToolResultCache()
        
        cache.set("tool1", {"a": 1}, {"data": "1"})
        cache.set("tool1", {"a": 2}, {"data": "2"})
        cache.set("tool2", {"a": 1}, {"data": "3"})
        
        # Invalidate tool1
        cache.invalidate("tool1")
        
        # tool1 entries should be gone
        assert cache.get("tool1", {"a": 1}) is None
        assert cache.get("tool1", {"a": 2}) is None
        # tool2 should still exist
        assert cache.get("tool2", {"a": 1}) is not None
    
    def test_cache_invalidation_all(self):
        """Cache should invalidate all entries."""
        cache = ToolResultCache()
        
        cache.set("tool1", {"a": 1}, {"data": "1"})
        cache.set("tool2", {"a": 1}, {"data": "2"})
        
        # Invalidate all
        cache.invalidate()
        
        # All entries should be gone
        assert cache.get("tool1", {"a": 1}) is None
        assert cache.get("tool2", {"a": 1}) is None
        assert len(cache.cache) == 0
    
    def test_get_stats_returns_cache_info(self):
        """get_stats should return cache statistics."""
        cache = ToolResultCache(ttl_seconds=300, max_size=1000)
        
        cache.set("tool1", {"a": 1}, {"data": "1"})
        cache.set("tool2", {"a": 1}, {"data": "2"})
        
        stats = cache.get_stats()
        
        assert stats["size"] == 2
        assert stats["max_size"] == 1000
        assert stats["ttl_seconds"] == 300
        assert "oldest_entry_age" in stats


class TestRetryLogic:
    """Test retry logic helpers."""
    
    def test_is_retryable_error_identifies_transient_errors(self):
        """_is_retryable_error should identify transient errors."""
        from agents.mcp_orchestrator import MCPOrchestratorAgent
        
        orchestrator = MCPOrchestratorAgent()
        
        # Retryable errors
        assert orchestrator._is_retryable_error("Connection timeout")
        assert orchestrator._is_retryable_error("Network error occurred")
        assert orchestrator._is_retryable_error("Service temporarily unavailable")
        assert orchestrator._is_retryable_error("HTTP 503 error")
        assert orchestrator._is_retryable_error("Rate limit exceeded (429)")
        assert orchestrator._is_retryable_error("Gateway timeout 504")
        
        # Non-retryable errors
        assert not orchestrator._is_retryable_error("Invalid credentials")
        assert not orchestrator._is_retryable_error("Resource not found")
        assert not orchestrator._is_retryable_error("Permission denied")
    
    def test_is_retryable_exception_identifies_transient_exceptions(self):
        """_is_retryable_exception should identify transient exceptions."""
        from agents.mcp_orchestrator import MCPOrchestratorAgent
        
        orchestrator = MCPOrchestratorAgent()
        
        # Retryable exceptions
        assert orchestrator._is_retryable_exception(asyncio.TimeoutError())
        assert orchestrator._is_retryable_exception(ConnectionError())
        assert orchestrator._is_retryable_exception(TimeoutError())
        
        # Non-retryable exceptions
        assert not orchestrator._is_retryable_exception(ValueError())
        assert not orchestrator._is_retryable_exception(KeyError())
        assert not orchestrator._is_retryable_exception(TypeError())


class TestToolTimeouts:
    """Test per-tool timeout configuration."""
    
    def test_get_tool_timeout_returns_configured_timeout(self):
        """_get_tool_timeout should return configured timeout for known tools."""
        from agents.mcp_orchestrator import MCPOrchestratorAgent
        
        orchestrator = MCPOrchestratorAgent()
        
        # Configured timeouts
        assert orchestrator._get_tool_timeout("azure_list_subscriptions") == 10.0
        assert orchestrator._get_tool_timeout("azure_list_vms") == 30.0
        assert orchestrator._get_tool_timeout("law_get_software_inventory") == 45.0
    
    def test_get_tool_timeout_returns_default_for_unknown_tools(self):
        """_get_tool_timeout should return default timeout for unknown tools."""
        from agents.mcp_orchestrator import MCPOrchestratorAgent
        
        orchestrator = MCPOrchestratorAgent()
        
        # Unknown tool should get default
        assert orchestrator._get_tool_timeout("unknown_tool") == orchestrator._default_tool_timeout


@pytest.mark.asyncio
class TestIntegration:
    """Integration tests for orchestrator enhancements."""
    
    async def test_orchestrator_initializes_with_enhancements(self):
        """Orchestrator should initialize with circuit breaker and cache."""
        from agents.mcp_orchestrator import MCPOrchestratorAgent
        
        orchestrator = MCPOrchestratorAgent()
        
        # Should have circuit breaker
        assert hasattr(orchestrator, "_circuit_breaker")
        assert isinstance(orchestrator._circuit_breaker, CircuitBreaker)
        
        # Should have cache
        assert hasattr(orchestrator, "_tool_cache")
        assert isinstance(orchestrator._tool_cache, ToolResultCache)
        
        # Should have tool timeouts
        assert hasattr(orchestrator, "_tool_timeouts")
        assert isinstance(orchestrator._tool_timeouts, dict)
        
        # Should have cacheable tools set
        assert hasattr(orchestrator, "_cacheable_tools")
        assert isinstance(orchestrator._cacheable_tools, set)
    
    async def test_public_api_methods_exist(self):
        """Public API methods should be accessible."""
        from agents.mcp_orchestrator import MCPOrchestratorAgent
        
        orchestrator = MCPOrchestratorAgent()
        
        # Should have public methods
        assert hasattr(orchestrator, "get_circuit_breaker_status")
        assert hasattr(orchestrator, "get_cache_stats")
        assert hasattr(orchestrator, "invalidate_tool_cache")
        
        # Test calling methods
        cb_status = orchestrator.get_circuit_breaker_status()
        assert isinstance(cb_status, dict)
        
        cache_stats = orchestrator.get_cache_stats()
        assert isinstance(cache_stats, dict)
        
        # Should not raise error
        orchestrator.invalidate_tool_cache()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
