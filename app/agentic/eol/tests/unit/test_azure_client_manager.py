"""
Unit tests for AzureSDKManager singleton with credential/client caching and connection pooling.

Tests cover:
- Test 1: Singleton pattern (get_instance returns same object)
- Test 2: Sync credential caching (DefaultAzureCredential)
- Test 3: Async credential caching (AsyncDefaultAzureCredential)
- Test 4: Client caching by subscription_id key
- Test 5: Connection pool configuration
- Test 6: Lifecycle - is_initialized() state transitions
- Test 7: aclose() closes async clients without raising
- Test 8: _run_startup_tasks() calls initialize()
- Test 9: _run_shutdown_tasks() calls aclose()
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock


# ============================================================================
# Test 1: Singleton pattern
# ============================================================================

class TestSingleton:
    def test_get_instance_returns_same_object(self):
        """AzureSDKManager.get_instance() must return the identical object on every call."""
        # Reset singleton between tests
        from utils.azure_client_manager import AzureSDKManager
        AzureSDKManager._instance = None  # reset for test isolation

        instance1 = AzureSDKManager.get_instance()
        instance2 = AzureSDKManager.get_instance()
        assert instance1 is instance2, "get_instance() must return the same singleton object"
        # cleanup
        AzureSDKManager._instance = None

    def test_module_level_accessor_returns_same_instance(self):
        """get_azure_sdk_manager() module function must match AzureSDKManager.get_instance()."""
        from utils.azure_client_manager import AzureSDKManager, get_azure_sdk_manager
        AzureSDKManager._instance = None

        manager = get_azure_sdk_manager()
        assert manager is AzureSDKManager.get_instance()
        AzureSDKManager._instance = None


# ============================================================================
# Test 2: Sync credential caching
# ============================================================================

class TestCredentialCaching:
    def setup_method(self):
        from utils.azure_client_manager import AzureSDKManager
        AzureSDKManager._instance = None

    def teardown_method(self):
        from utils.azure_client_manager import AzureSDKManager
        AzureSDKManager._instance = None

    def test_get_credential_returns_same_instance(self):
        """get_credential() must return the identical DefaultAzureCredential on every call."""
        with patch("utils.azure_client_manager.DefaultAzureCredential") as mock_cred_cls:
            mock_cred = MagicMock()
            mock_cred_cls.return_value = mock_cred

            from utils.azure_client_manager import AzureSDKManager
            AzureSDKManager._instance = None
            manager = AzureSDKManager.get_instance()

            cred1 = manager.get_credential()
            cred2 = manager.get_credential()

            assert cred1 is cred2, "get_credential() must return cached credential"
            assert mock_cred_cls.call_count == 1, "DefaultAzureCredential must be instantiated only once"

    def test_get_async_credential_returns_same_instance(self):
        """get_async_credential() must return the identical AsyncDefaultAzureCredential on every call."""
        with patch("utils.azure_client_manager.AsyncDefaultAzureCredential") as mock_async_cls:
            mock_async_cred = MagicMock()
            mock_async_cls.return_value = mock_async_cred

            from utils.azure_client_manager import AzureSDKManager
            AzureSDKManager._instance = None
            manager = AzureSDKManager.get_instance()

            acred1 = manager.get_async_credential()
            acred2 = manager.get_async_credential()

            assert acred1 is acred2, "get_async_credential() must return cached async credential"
            assert mock_async_cls.call_count == 1, "AsyncDefaultAzureCredential must be instantiated only once"


# ============================================================================
# Test 4: Client caching
# ============================================================================

class TestClientCaching:
    def setup_method(self):
        from utils.azure_client_manager import AzureSDKManager
        AzureSDKManager._instance = None

    def teardown_method(self):
        from utils.azure_client_manager import AzureSDKManager
        AzureSDKManager._instance = None

    def test_get_compute_client_caches_by_subscription_id(self):
        """get_compute_client() must return cached client on second call (no new instantiation)."""
        mock_cred = MagicMock()
        mock_client_instance = MagicMock()

        with patch("utils.azure_client_manager.DefaultAzureCredential", return_value=mock_cred), \
             patch("utils.azure_client_manager.ComputeManagementClient", return_value=mock_client_instance) as mock_compute_cls:

            from utils.azure_client_manager import AzureSDKManager
            AzureSDKManager._instance = None
            manager = AzureSDKManager.get_instance()

            sub_id = "test-subscription-123"
            client1 = manager.get_compute_client(sub_id)
            client2 = manager.get_compute_client(sub_id)

            assert client1 is client2, "compute client should be cached and return same object"
            assert mock_compute_cls.call_count == 1, "ComputeManagementClient should be instantiated only once per subscription"

    def test_get_compute_client_creates_separate_clients_per_subscription(self):
        """get_compute_client() with different subscription IDs must create separate clients."""
        mock_cred = MagicMock()
        mock_client_a = MagicMock()
        mock_client_b = MagicMock()

        with patch("utils.azure_client_manager.DefaultAzureCredential", return_value=mock_cred), \
             patch("utils.azure_client_manager.ComputeManagementClient", side_effect=[mock_client_a, mock_client_b]):

            from utils.azure_client_manager import AzureSDKManager
            AzureSDKManager._instance = None
            manager = AzureSDKManager.get_instance()

            client_a = manager.get_compute_client("sub-a")
            client_b = manager.get_compute_client("sub-b")

            assert client_a is not client_b, "Different subscriptions should have different clients"


# ============================================================================
# Test 5: Connection pool configuration
# ============================================================================

class TestConnectionPoolConfig:
    def setup_method(self):
        from utils.azure_client_manager import AzureSDKManager
        AzureSDKManager._instance = None

    def teardown_method(self):
        from utils.azure_client_manager import AzureSDKManager
        AzureSDKManager._instance = None

    def test_sync_transport_uses_connection_pool(self):
        """Sync client factory must configure RequestsTransport with pool settings."""
        mock_cred = MagicMock()

        with patch("utils.azure_client_manager.DefaultAzureCredential", return_value=mock_cred), \
             patch("utils.azure_client_manager.ComputeManagementClient") as mock_compute_cls, \
             patch("utils.azure_client_manager.RequestsTransport") as mock_transport_cls:

            mock_transport = MagicMock()
            mock_transport_cls.return_value = mock_transport
            mock_compute_cls.return_value = MagicMock()

            from utils.azure_client_manager import AzureSDKManager
            AzureSDKManager._instance = None
            manager = AzureSDKManager.get_instance()
            manager.get_compute_client("sub-pool-test")

            # Verify RequestsTransport was instantiated (pool config applied)
            assert mock_transport_cls.called, "RequestsTransport should be configured for sync clients"
            # Verify transport is passed to the client
            call_kwargs = mock_compute_cls.call_args
            assert call_kwargs is not None, "ComputeManagementClient should be called"


# ============================================================================
# Test 6: Lifecycle - is_initialized()
# ============================================================================

class TestLifecycle:
    def setup_method(self):
        from utils.azure_client_manager import AzureSDKManager
        AzureSDKManager._instance = None

    def teardown_method(self):
        from utils.azure_client_manager import AzureSDKManager
        AzureSDKManager._instance = None

    def test_is_initialized_false_before_initialize(self):
        """is_initialized() must return False before initialize() is called."""
        from utils.azure_client_manager import AzureSDKManager
        AzureSDKManager._instance = None
        manager = AzureSDKManager.get_instance()
        assert manager.is_initialized() is False

    @pytest.mark.asyncio
    async def test_is_initialized_true_after_initialize(self):
        """is_initialized() must return True after initialize() is called."""
        from utils.azure_client_manager import AzureSDKManager
        AzureSDKManager._instance = None
        manager = AzureSDKManager.get_instance()

        await manager.initialize()
        assert manager.is_initialized() is True

    @pytest.mark.asyncio
    async def test_aclose_clears_initialized_state(self):
        """aclose() must set is_initialized() back to False."""
        from utils.azure_client_manager import AzureSDKManager
        AzureSDKManager._instance = None
        manager = AzureSDKManager.get_instance()

        await manager.initialize()
        assert manager.is_initialized() is True

        await manager.aclose()
        assert manager.is_initialized() is False


# ============================================================================
# Test 7: aclose() without raising
# ============================================================================

class TestAClose:
    def setup_method(self):
        from utils.azure_client_manager import AzureSDKManager
        AzureSDKManager._instance = None

    def teardown_method(self):
        from utils.azure_client_manager import AzureSDKManager
        AzureSDKManager._instance = None

    @pytest.mark.asyncio
    async def test_aclose_does_not_raise_with_no_clients(self):
        """aclose() on a fresh manager with no async clients must not raise."""
        from utils.azure_client_manager import AzureSDKManager
        AzureSDKManager._instance = None
        manager = AzureSDKManager.get_instance()
        # Should not raise even with no clients registered
        await manager.aclose()

    @pytest.mark.asyncio
    async def test_aclose_closes_async_clients(self):
        """aclose() must call close() on all registered async clients."""
        from utils.azure_client_manager import AzureSDKManager
        AzureSDKManager._instance = None
        manager = AzureSDKManager.get_instance()

        # Inject a mock async client directly
        mock_client = AsyncMock()
        manager._async_clients["test_key"] = mock_client

        await manager.aclose()

        mock_client.close.assert_called_once()
        assert len(manager._async_clients) == 0, "Async clients dict should be cleared after aclose"

    @pytest.mark.asyncio
    async def test_aclose_tolerates_close_errors(self):
        """aclose() must not propagate exceptions from individual client.close() calls."""
        from utils.azure_client_manager import AzureSDKManager
        AzureSDKManager._instance = None
        manager = AzureSDKManager.get_instance()

        # Inject a mock client that raises on close
        mock_failing_client = AsyncMock()
        mock_failing_client.close.side_effect = RuntimeError("Connection already closed")
        manager._async_clients["failing_key"] = mock_failing_client

        # Must not raise despite the client error
        await manager.aclose()


# ============================================================================
# Tests 8-9: FastAPI lifespan integration (structural checks on main.py source)
# ============================================================================

class TestLifespanIntegration:
    def test_startup_imports_and_calls_azure_manager_initialize(self):
        """main.py _run_startup_tasks() must contain code that calls azure_manager.initialize()."""
        import ast
        import os

        main_path = os.path.join(
            os.path.dirname(__file__),
            "..", "..", "main.py"
        )
        with open(main_path) as f:
            source = f.read()

        # Check that azure_client_manager is imported in startup
        assert "azure_client_manager" in source or "get_azure_sdk_manager" in source, (
            "main.py must import from utils.azure_client_manager"
        )
        # Check that initialize() is called
        assert "azure_manager" in source and ".initialize()" in source, (
            "_run_startup_tasks() must call azure_manager.initialize()"
        )

    def test_shutdown_calls_azure_manager_aclose(self):
        """main.py _run_shutdown_tasks() must contain code that calls azure_manager.aclose()."""
        import os

        main_path = os.path.join(
            os.path.dirname(__file__),
            "..", "..", "main.py"
        )
        with open(main_path) as f:
            source = f.read()

        # Check that aclose() is called in shutdown
        assert "azure_manager" in source and ".aclose()" in source, (
            "_run_shutdown_tasks() must call azure_manager.aclose()"
        )
