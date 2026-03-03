"""
Pytest configuration and fixtures for UI tests using Playwright.
"""
import os
import pytest
from playwright.sync_api import sync_playwright, Browser, BrowserContext, Page


@pytest.fixture(scope="session")
def base_url():
    """Base URL for the application."""
    return os.getenv(
        "APP_BASE_URL",
        "https://azure-agentic-platform-vnet.jollywater-179e4f4a.australiaeast.azurecontainerapps.io"
    )


@pytest.fixture(scope="session")
def browser():
    """Create a browser instance for the test session."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        yield browser
        browser.close()


@pytest.fixture(scope="function")
def context(browser: Browser):
    """Create a new browser context for each test."""
    context = browser.new_context(
        viewport={"width": 1920, "height": 1080},
        ignore_https_errors=True
    )
    yield context
    context.close()


@pytest.fixture(scope="function")
def page(context: BrowserContext):
    """Create a new page for each test."""
    page = context.new_page()
    yield page
    page.close()


@pytest.fixture(scope="function")
def authenticated_page(page: Page, base_url: str):
    """Navigate to the base URL (authentication handled by app)."""
    page.goto(base_url)
    page.wait_for_load_state("networkidle")
    return page
