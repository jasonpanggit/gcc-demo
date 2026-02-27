"""
Retry Logic Tests

Tests for retry.py utility functions with exponential backoff and jitter.
Created: 2026-02-27 (Phase 1, Task 3.2)
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock
from pathlib import Path
import sys

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.retry import retry_async, retry_sync


@pytest.mark.unit
@pytest.mark.asyncio
class TestRetryAsync:
    """Tests for retry_async decorator."""

    async def test_retry_async_success_first_try(self):
        """Test that successful call on first attempt returns immediately."""
        mock_func = AsyncMock(return_value="success")
        decorated = retry_async(retries=3)(mock_func)

        result = await decorated("arg1", kwarg="value")

        assert result == "success"
        assert mock_func.call_count == 1
        mock_func.assert_called_once_with("arg1", kwarg="value")

    async def test_retry_async_success_after_failures(self):
        """Test that function retries and succeeds on second attempt."""
        mock_func = AsyncMock(side_effect=[
            Exception("First failure"),
            "success"
        ])
        decorated = retry_async(retries=3, initial_delay=0.01)(mock_func)

        result = await decorated()

        assert result == "success"
        assert mock_func.call_count == 2

    async def test_retry_async_exhausted_retries(self):
        """Test that function raises exception after exhausting retries."""
        mock_func = AsyncMock(side_effect=ValueError("Always fails"))
        decorated = retry_async(retries=3, initial_delay=0.01)(mock_func)

        with pytest.raises(ValueError, match="Always fails"):
            await decorated()

        assert mock_func.call_count == 3

    async def test_retry_async_exponential_backoff(self):
        """Test that retry delays increase exponentially."""
        mock_func = AsyncMock(side_effect=[
            Exception("Fail 1"),
            Exception("Fail 2"),
            "success"
        ])
        decorated = retry_async(
            retries=3,
            initial_delay=0.01,
            backoff_factor=2.0,
            jitter=0.0  # Disable jitter for predictable timing
        )(mock_func)

        start_time = asyncio.get_event_loop().time()
        result = await decorated()
        elapsed = asyncio.get_event_loop().time() - start_time

        assert result == "success"
        # Should wait ~0.01s then ~0.02s (total ~0.03s minimum)
        assert elapsed >= 0.03

    async def test_retry_async_specific_exceptions(self):
        """Test that retry only catches specified exceptions."""
        mock_func = AsyncMock(side_effect=TypeError("Not retryable"))
        decorated = retry_async(
            retries=3,
            initial_delay=0.01,
            exceptions=(ValueError,)  # Only retry ValueError
        )(mock_func)

        with pytest.raises(TypeError, match="Not retryable"):
            await decorated()

        # Should fail immediately, not retry
        assert mock_func.call_count == 1

    async def test_retry_async_max_delay_cap(self):
        """Test that delay is capped at max_delay."""
        mock_func = AsyncMock(side_effect=[
            Exception("Fail 1"),
            Exception("Fail 2"),
            "success"
        ])
        decorated = retry_async(
            retries=3,
            initial_delay=0.01,
            max_delay=0.015,  # Cap delay
            backoff_factor=10.0,  # Would exceed max without cap
            jitter=0.0
        )(mock_func)

        start_time = asyncio.get_event_loop().time()
        result = await decorated()
        elapsed = asyncio.get_event_loop().time() - start_time

        assert result == "success"
        # Should wait ~0.01s then capped at ~0.015s (total ~0.025s)
        assert elapsed < 0.05  # Much less than uncapped would be


@pytest.mark.unit
class TestRetrySync:
    """Tests for retry_sync decorator."""

    def test_retry_sync_success_first_try(self):
        """Test that successful call on first attempt returns immediately."""
        mock_func = MagicMock(return_value="success")
        decorated = retry_sync(retries=3)(mock_func)

        result = decorated("arg1", kwarg="value")

        assert result == "success"
        assert mock_func.call_count == 1
        mock_func.assert_called_once_with("arg1", kwarg="value")

    def test_retry_sync_success_after_failures(self):
        """Test that function retries and succeeds on second attempt."""
        mock_func = MagicMock(side_effect=[
            Exception("First failure"),
            "success"
        ])
        decorated = retry_sync(retries=3, initial_delay=0.01)(mock_func)

        result = decorated()

        assert result == "success"
        assert mock_func.call_count == 2

    def test_retry_sync_exhausted_retries(self):
        """Test that function raises exception after exhausting retries."""
        mock_func = MagicMock(side_effect=ValueError("Always fails"))
        decorated = retry_sync(retries=3, initial_delay=0.01)(mock_func)

        with pytest.raises(ValueError, match="Always fails"):
            decorated()

        assert mock_func.call_count == 3

    def test_retry_sync_specific_exceptions(self):
        """Test that retry only catches specified exceptions."""
        mock_func = MagicMock(side_effect=TypeError("Not retryable"))
        decorated = retry_sync(
            retries=3,
            initial_delay=0.01,
            exceptions=(ValueError,)  # Only retry ValueError
        )(mock_func)

        with pytest.raises(TypeError, match="Not retryable"):
            decorated()

        # Should fail immediately, not retry
        assert mock_func.call_count == 1
