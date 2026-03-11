"""Tests for ARG throttle retry logic in _query_arg."""
import asyncio
import pytest
from unittest.mock import MagicMock, AsyncMock, patch, call
from azure.core.exceptions import HttpResponseError


def make_throttle_error(retry_after: int = 5) -> HttpResponseError:
    """Create a fake ARG RateLimiting error with Retry-After header."""
    err = HttpResponseError(message="RateLimiting")
    err.error = MagicMock()
    err.error.code = "RateLimiting"
    err.response = MagicMock()
    err.response.headers = {"Retry-After": str(retry_after)}
    return err


@pytest.mark.asyncio
async def test_query_arg_retries_on_throttle():
    """_query_arg should retry on RateLimiting error and succeed on 2nd attempt."""
    call_count = 0

    def fake_resources(req):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise make_throttle_error(retry_after=0)
        mock_resp = MagicMock()
        mock_resp.data = [{"id": "test"}]
        mock_resp.skip_token = None
        return mock_resp

    with patch.dict("os.environ", {
        "AZURE_SP_CLIENT_ID": "test-client-id",
        "AZURE_SP_CLIENT_SECRET": "test-secret",
        "AZURE_TENANT_ID": "test-tenant",
    }):
        with patch("mcp_servers.patch_mcp_server.ResourceGraphClient") as mock_cls, \
             patch("mcp_servers.patch_mcp_server.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            mock_client = MagicMock()
            mock_client.resources.side_effect = fake_resources
            mock_cls.return_value = mock_client

            import mcp_servers.patch_mcp_server as mod
            rows = await mod._query_arg("Resources | take 1", ["sub-123"])

    assert call_count == 2
    assert mock_sleep.called
    assert rows == [{"id": "test"}]


@pytest.mark.asyncio
async def test_query_arg_raises_after_max_retries():
    """_query_arg should raise after exhausting MAX_RETRIES."""
    def always_throttle(req):
        raise make_throttle_error(retry_after=0)

    with patch.dict("os.environ", {
        "AZURE_SP_CLIENT_ID": "test-client-id",
        "AZURE_SP_CLIENT_SECRET": "test-secret",
        "AZURE_TENANT_ID": "test-tenant",
    }):
        with patch("mcp_servers.patch_mcp_server.ResourceGraphClient") as mock_cls, \
             patch("mcp_servers.patch_mcp_server.asyncio.sleep", new_callable=AsyncMock):
            mock_client = MagicMock()
            mock_client.resources.side_effect = always_throttle
            mock_cls.return_value = mock_client

            import mcp_servers.patch_mcp_server as mod
            with pytest.raises(HttpResponseError):
                await mod._query_arg("Resources | take 1", ["sub-123"])


@pytest.mark.asyncio
async def test_query_arg_uses_retry_after_header():
    """_query_arg should sleep for Retry-After seconds when throttled."""
    def fake_resources(req):
        raise make_throttle_error(retry_after=7)

    with patch.dict("os.environ", {
        "AZURE_SP_CLIENT_ID": "test-client-id",
        "AZURE_SP_CLIENT_SECRET": "test-secret",
        "AZURE_TENANT_ID": "test-tenant",
    }):
        with patch("mcp_servers.patch_mcp_server.ResourceGraphClient") as mock_cls, \
             patch("mcp_servers.patch_mcp_server.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            mock_client = MagicMock()
            mock_client.resources.side_effect = fake_resources
            mock_cls.return_value = mock_client

            import mcp_servers.patch_mcp_server as mod
            with pytest.raises(HttpResponseError):
                await mod._query_arg("Resources | take 1", ["sub-123"])

            assert mock_sleep.call_args_list[0] == call(7)
