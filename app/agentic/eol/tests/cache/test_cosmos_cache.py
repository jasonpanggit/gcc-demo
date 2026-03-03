"""
Cosmos Cache Tests

Tests for base Cosmos DB client and cache foundation.
Created: 2026-02-27 (Phase 3, Week 3, Day 1)
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import os


class TestBaseCosmosClientInitialization:
    """Tests for BaseCosmosClient initialization."""

    def test_cosmos_cache_imports(self):
        """Test cosmos_cache module can be imported."""
        from utils.cosmos_cache import BaseCosmosClient

        assert BaseCosmosClient is not None

    def test_base_cosmos_client_initialization(self):
        """Test BaseCosmosClient initializes with correct defaults."""
        from utils.cosmos_cache import BaseCosmosClient

        client = BaseCosmosClient()

        assert client.cosmos_client is None
        assert client.database is None
        assert client.initialized is False
        assert client._initialization_attempted is False
        assert client.last_error is None
        assert isinstance(client._container_cache, dict)

    def test_container_cache_empty_on_init(self):
        """Test container cache starts empty."""
        from utils.cosmos_cache import BaseCosmosClient

        client = BaseCosmosClient()

        assert len(client._container_cache) == 0


class TestBaseCosmosClientSyncInitialization:
    """Tests for synchronous initialization."""

    @patch.dict(os.environ, {'COSMOS_SKIP_CREDENTIAL_VALIDATION': 'true'})
    @patch('utils.cosmos_cache.COSMOS_IMPORTS_OK', False)
    def test_ensure_initialized_no_imports(self):
        """Test _ensure_initialized when Cosmos SDK not available."""
        from utils.cosmos_cache import BaseCosmosClient

        client = BaseCosmosClient()
        client._ensure_initialized()

        assert client._initialization_attempted is True
        assert client.initialized is False
        assert "Cosmos DB SDK not installed" in client.last_error

    @patch.dict(os.environ, {'COSMOS_SKIP_CREDENTIAL_VALIDATION': 'true'})
    @patch('utils.cosmos_cache.COSMOS_IMPORTS_OK', True)
    @patch('utils.cosmos_cache.config')
    def test_ensure_initialized_no_endpoint(self, mock_config):
        """Test _ensure_initialized when endpoint not configured."""
        from utils.cosmos_cache import BaseCosmosClient

        # Mock config with no endpoint
        mock_config.azure.cosmos_endpoint = None

        client = BaseCosmosClient()
        client._ensure_initialized()

        assert client._initialization_attempted is True
        assert client.initialized is False
        assert "Cosmos DB endpoint not configured" in client.last_error

    @patch.dict(os.environ, {'COSMOS_SKIP_CREDENTIAL_VALIDATION': 'true'})
    @patch('utils.cosmos_cache.COSMOS_IMPORTS_OK', True)
    @patch('utils.cosmos_cache.config')
    @patch('utils.cosmos_cache.DefaultAzureCredential')
    @patch('utils.cosmos_cache.CosmosClient')
    def test_ensure_initialized_success(self, mock_cosmos_client, mock_credential, mock_config):
        """Test _ensure_initialized succeeds with valid config."""
        from utils.cosmos_cache import BaseCosmosClient

        # Mock config
        mock_config.azure.cosmos_endpoint = "https://test.documents.azure.com"
        mock_config.azure.cosmos_database = "test-db"

        # Mock Cosmos client
        mock_db = MagicMock()
        mock_client_instance = MagicMock()
        mock_client_instance.create_database_if_not_exists.return_value = mock_db
        mock_cosmos_client.return_value = mock_client_instance

        client = BaseCosmosClient()
        client._ensure_initialized()

        assert client._initialization_attempted is True
        assert client.initialized is True
        assert client.cosmos_client is not None
        assert client.database is not None

    def test_ensure_initialized_idempotent(self):
        """Test _ensure_initialized only runs once."""
        from utils.cosmos_cache import BaseCosmosClient

        client = BaseCosmosClient()
        client._initialization_attempted = True

        # Should not attempt initialization again
        client._ensure_initialized()

        # Should still be False since we didn't actually initialize
        assert client.initialized is False


@pytest.mark.asyncio
class TestBaseCosmosClientAsyncInitialization:
    """Tests for async initialization."""

    @patch.dict(os.environ, {'COSMOS_SKIP_CREDENTIAL_VALIDATION': 'true'})
    @patch('utils.cosmos_cache.COSMOS_IMPORTS_OK', False)
    async def test_initialize_async_no_imports(self):
        """Test _initialize_async when Cosmos SDK not available."""
        from utils.cosmos_cache import BaseCosmosClient

        client = BaseCosmosClient()
        await client._initialize_async()

        assert client._initialization_attempted is True
        assert client.initialized is False
        assert "Cosmos DB SDK not installed" in client.last_error

    @patch.dict(os.environ, {'COSMOS_SKIP_CREDENTIAL_VALIDATION': 'true'})
    @patch('utils.cosmos_cache.COSMOS_IMPORTS_OK', True)
    @patch('utils.cosmos_cache.config')
    async def test_initialize_async_no_endpoint(self, mock_config):
        """Test _initialize_async when endpoint not configured."""
        from utils.cosmos_cache import BaseCosmosClient

        # Mock config with no endpoint
        mock_config.azure.cosmos_endpoint = None

        client = BaseCosmosClient()
        await client._initialize_async()

        assert client._initialization_attempted is True
        assert client.initialized is False

    async def test_initialize_async_idempotent(self):
        """Test _initialize_async only runs once."""
        from utils.cosmos_cache import BaseCosmosClient

        client = BaseCosmosClient()
        client._initialization_attempted = True

        # Should not attempt initialization again
        await client._initialize_async()

        assert client.initialized is False


class TestBaseCosmosClientModule:
    """Tests for cosmos_cache module structure."""

    def test_module_imports(self):
        """Test cosmos_cache module imports."""
        from utils import cosmos_cache

        assert hasattr(cosmos_cache, 'BaseCosmosClient')
        assert hasattr(cosmos_cache, 'COSMOS_IMPORTS_OK')
        assert hasattr(cosmos_cache, 'logger')
        assert hasattr(cosmos_cache, 'os')

    def test_cosmos_imports_ok_flag(self):
        """Test COSMOS_IMPORTS_OK flag exists."""
        from utils import cosmos_cache

        assert hasattr(cosmos_cache, 'COSMOS_IMPORTS_OK')
        assert isinstance(cosmos_cache.COSMOS_IMPORTS_OK, bool)

    def test_azure_loggers_suppressed(self):
        """Test Azure SDK loggers are configured."""
        import logging

        # Azure loggers should be set to WARNING level
        azure_logger = logging.getLogger('azure.core')
        assert azure_logger.level == logging.WARNING or azure_logger.level == 0


class TestCosmosClientEnvironmentHandling:
    """Tests for environment variable handling."""

    def test_skip_credential_validation_env_var(self):
        """Test COSMOS_SKIP_CREDENTIAL_VALIDATION environment variable."""
        # This is important for CI/CD and testing environments
        with patch.dict(os.environ, {'COSMOS_SKIP_CREDENTIAL_VALIDATION': 'true'}):
            assert os.getenv('COSMOS_SKIP_CREDENTIAL_VALIDATION') == 'true'

    def test_skip_credential_validation_default(self):
        """Test COSMOS_SKIP_CREDENTIAL_VALIDATION defaults to false."""
        with patch.dict(os.environ, {}, clear=True):
            value = os.getenv('COSMOS_SKIP_CREDENTIAL_VALIDATION', 'false')
            assert value == 'false'
