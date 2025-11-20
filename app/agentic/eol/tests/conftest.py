"""
Pytest Configuration and Fixtures for EOL App Testing
Provides shared fixtures and configuration for all test modules
"""
import pytest
import pytest_asyncio
import sys
import os
from types import SimpleNamespace
from typing import AsyncGenerator
from httpx import AsyncClient, ASGITransport

from utils import config as app_config

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Determine test mode and base URL
USE_MOCK_DATA = os.getenv('USE_MOCK_DATA', 'true').lower() == 'true'
BASE_URL = os.getenv('BASE_URL', 'http://localhost:8000' if USE_MOCK_DATA else 'https://app-eol-agentic-gcc-demo.azurewebsites.net')

# Set environment variables
os.environ['USE_MOCK_DATA'] = str(USE_MOCK_DATA).lower()
os.environ['TESTING'] = os.getenv('TESTING', 'true')


@pytest.fixture(scope="session")
def anyio_backend():
    """Use asyncio backend for all async tests"""
    return "asyncio"


@pytest.fixture(scope="session")
def base_url():
    """Provide base URL for tests"""
    return BASE_URL


@pytest_asyncio.fixture(scope="session")
async def app():
    """Create FastAPI app instance with mock data (only for local testing)"""
    if USE_MOCK_DATA:
        from main import app as fastapi_app
        yield fastapi_app
    else:
        # For remote testing, we don't need the app instance
        yield None


@pytest_asyncio.fixture(scope="function")
async def client(app, base_url) -> AsyncGenerator[AsyncClient, None]:
    """
    Create async HTTP client for testing endpoints
    Fresh client for each test function
    
    Supports both local (ASGI) and remote (HTTP) testing:
    - Local: Uses ASGITransport with FastAPI app instance
    - Remote: Uses direct HTTP client to BASE_URL
    """
    if USE_MOCK_DATA and app is not None:
        # Local testing with ASGI transport
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url=base_url) as ac:
            yield ac
    else:
        # Remote testing with HTTP client
        async with AsyncClient(base_url=base_url, timeout=30.0) as ac:
            yield ac


@pytest.fixture(scope="session")
def mock_data():
    """Provide access to mock data generator"""
    from tests.mock_data import MockDataGenerator
    return MockDataGenerator()


@pytest.fixture(scope="function")
def test_software_name():
    """Sample software name for testing"""
    return "Windows Server"


@pytest.fixture(scope="function")
def test_software_version():
    """Sample software version for testing"""
    return "2016"


@pytest.fixture(scope="function")
def test_alert_config():
    """Sample alert configuration for testing"""
    return {
        "enabled": True,
        "smtp": {
            "enabled": False,
            "server": "smtp.example.com",
            "port": 587,
            "use_tls": True,
            "from_email": "test@example.com"
        },
        "thresholds": {
            "critical_days": 0,
            "high_days": 90,
            "medium_days": 180
        }
    }


# Markers for different test categories
def pytest_configure(config):
    """Register custom pytest markers"""
    config.addinivalue_line(
        "markers", "unit: Unit tests for individual components"
    )
    config.addinivalue_line(
        "markers", "integration: Integration tests for API endpoints"
    )
    config.addinivalue_line(
        "markers", "api: API endpoint tests"
    )
    config.addinivalue_line(
        "markers", "ui: UI/HTML endpoint tests"
    )
    config.addinivalue_line(
        "markers", "slow: Tests that take longer than 1 second"
    )
    config.addinivalue_line(
        "markers", "cache: Tests related to caching functionality"
    )
    config.addinivalue_line(
        "markers", "eol: Tests for EOL analysis functionality"
    )
    config.addinivalue_line(
        "markers", "inventory: Tests for inventory endpoints"
    )
    config.addinivalue_line(
        "markers", "alerts: Tests for alert management"
    )

    # Expose application configuration to pytest skip expressions
    config.inventory_assistant = app_config.inventory_assistant
    config.cosmos = SimpleNamespace(
        enabled=bool(app_config.azure.cosmos_endpoint),
        endpoint=app_config.azure.cosmos_endpoint,
    )
