"""
Pytest Configuration and Fixtures for EOL App Testing

Provides shared fixtures and configuration for all test modules.
pytest.ini / pyproject.toml is expected to set ``pythonpath = app/agentic/eol``
so that application imports resolve without any sys.path manipulation here.
"""
import pytest
import pytest_asyncio
import os
from typing import AsyncGenerator
from httpx import AsyncClient, ASGITransport

from utils import config as app_config

# Determine test mode and base URL
USE_MOCK_DATA = os.getenv('USE_MOCK_DATA', 'true').lower() == 'true'
BASE_URL = os.getenv('BASE_URL', 'http://localhost:8000' if USE_MOCK_DATA else 'https://app-eol-agentic-gcc-demo.azurewebsites.net')

# Set environment variables
os.environ['USE_MOCK_DATA'] = str(USE_MOCK_DATA).lower()
os.environ['TESTING'] = os.getenv('TESTING', 'true')


@pytest.fixture(scope="session", autouse=True)
def fast_test_env():
    """
    Autouse session fixture that pins ``MOCK_AGENT_DELAY_MS=0`` for the entire
    test run so that mock-agent sleep calls complete instantly and do not inflate
    wall-clock test time.  The original value (if any) is restored after the
    session ends.
    """
    original = os.environ.get("MOCK_AGENT_DELAY_MS")
    os.environ["MOCK_AGENT_DELAY_MS"] = "0"
    yield
    if original is None:
        os.environ.pop("MOCK_AGENT_DELAY_MS", None)
    else:
        os.environ["MOCK_AGENT_DELAY_MS"] = original


@pytest.fixture(scope="session")
def anyio_backend():
    """Use asyncio backend for all async tests."""
    return "asyncio"


@pytest.fixture(scope="session")
def base_url():
    """Provide the resolved base URL (local or remote) for the current test run."""
    return BASE_URL


@pytest.fixture(scope="function")
def fresh_mock_generator():
    """
    Return a brand-new :class:`~tests.mock_data.MockDataGenerator` instance for
    each test function.

    Using this fixture instead of the session-scoped ``mock_data`` fixture
    guarantees that random state and any cached computer lists from a previous
    test cannot bleed into the current test, making individual tests fully
    isolated.
    """
    from tests.mock_data import MockDataGenerator
    return MockDataGenerator()


@pytest_asyncio.fixture(scope="session")
async def app():
    """
    Create a FastAPI application instance for in-process ASGI testing.

    When ``USE_MOCK_DATA=true`` (the default) the real ``main.app`` object is
    yielded so that :fixture:`client` can drive it via :class:`ASGITransport`
    without a live server.  For remote / integration runs the fixture yields
    ``None`` and :fixture:`client` falls back to a plain HTTP client.
    """
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
    """
    Provide a shared, session-scoped :class:`~tests.mock_data.MockDataGenerator`
    instance.

    Because this fixture is session-scoped it is constructed once and reused
    across all tests in the session.  If a test needs a completely isolated
    generator (no shared random state), use :fixture:`fresh_mock_generator`
    instead.
    """
    from tests.mock_data import MockDataGenerator
    return MockDataGenerator()


@pytest.fixture(scope="function")
def test_software_name():
    """Return a canonical software name used as a default test parameter."""
    return "Windows Server"


@pytest.fixture(scope="function")
def test_software_version():
    """Return a canonical software version string used as a default test parameter."""
    return "2016"


@pytest.fixture(scope="function")
def test_alert_config():
    """
    Return a minimal, self-consistent alert configuration dictionary.

    SMTP is intentionally disabled so that tests never accidentally send mail.
    Threshold values follow the standard critical / high / medium ladder.
    """
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
    """
    Register custom pytest markers and expose application-level feature flags.

    Markers registered here should mirror those listed in ``pytest.ini`` so that
    ``--strict-markers`` mode does not reject them when running the full suite.
    Application feature flags are attached to the
    ``config`` object so that test modules can reference them in ``pytest.mark.skipif``
    expressions without importing application code at collection time.
    """
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
    config.addinivalue_line(
        "markers", "golden: Golden scenario tests for MCP tool selection validation"
    )
    config.addinivalue_line(
        "markers", "smoke: Smoke tests against deployed application"
    )
    config.addinivalue_line(
        "markers", "performance: Performance validation tests requiring PostgreSQL"
    )

    # Expose application configuration to pytest skip expressions
    config.inventory_assistant = app_config.inventory_assistant
