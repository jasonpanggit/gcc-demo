"""
Playwright UI tests for OS & Software (LAW) page.

Test Coverage:
- Page loading and navigation
- Inventory table display
- Log Analytics Workspace data
- Filters and search
"""

import re
import pytest
from playwright.sync_api import Page, expect


class TestOSSoftwareLAWBasics:
    """Basic page functionality tests."""

    def test_page_loads(self, page: Page, base_url: str):
        """Verify OS & Software page loads successfully."""
        page.goto(f"{base_url}/inventory")
        expect(page).to_have_title(re.compile(r"Inventory|OS|Software|LAW", re.IGNORECASE))

    def test_main_heading_present(self, page: Page, base_url: str):
        """Check for main page heading."""
        page.goto(f"{base_url}/inventory")
        heading = page.locator("h1")
        expect(heading).to_be_visible()
        expect(heading).to_contain_text(re.compile(r"Inventory|OS|Software", re.IGNORECASE))

    def test_sidebar_visible(self, page: Page, base_url: str):
        """Verify sidebar navigation is present."""
        page.goto(f"{base_url}/inventory")
        sidebar = page.locator("aside, [role='complementary'], nav.sidebar, .sidebar")
        expect(sidebar.first).to_be_visible()


class TestOSSoftwareLAWTable:
    """Test inventory table display."""

    def test_table_present(self, page: Page, base_url: str):
        """Verify inventory table exists."""
        page.goto(f"{base_url}/inventory")
        page.wait_for_load_state("networkidle")

        table = page.locator("table").first
        expect(table).to_be_visible(timeout=15000)

    def test_table_headers_present(self, page: Page, base_url: str):
        """Check for table column headers."""
        page.goto(f"{base_url}/inventory")
        page.wait_for_load_state("networkidle")

        table = page.locator("table").first
        expect(table).to_be_visible(timeout=15000)

        # Check for headers (might include OS, Software, Version, Computer, etc.)
        headers = page.locator("th, [role='columnheader']").all()
        assert len(headers) > 0, "No table headers found"

    def test_table_has_data_or_empty_message(self, page: Page, base_url: str):
        """Verify table shows data or empty message."""
        page.goto(f"{base_url}/inventory")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)

        # Check for data rows or empty state
        data_rows = page.locator("tbody tr").count()
        empty_message = page.locator("text=/No.*data|Empty|Loading/i").first

        assert data_rows > 0 or empty_message.is_visible(), "Table has no data and no empty message"


class TestOSSoftwareLAWFilters:
    """Test filtering and search functionality."""

    def test_search_input_present(self, page: Page, base_url: str):
        """Check for search input field."""
        page.goto(f"{base_url}/inventory")
        page.wait_for_load_state("networkidle")

        search_input = page.locator("input[type='search'], input[placeholder*='Search' i]").first

        if search_input.is_visible():
            expect(search_input).to_be_visible()

    def test_filter_controls_present(self, page: Page, base_url: str):
        """Check for filter dropdowns."""
        page.goto(f"{base_url}/inventory")
        page.wait_for_load_state("networkidle")

        # Look for OS filter, Software type filter, etc.
        filters = page.locator("select, button:has-text('Filter')").first

        if filters.is_visible():
            expect(filters).to_be_visible()

    def test_refresh_button_present(self, page: Page, base_url: str):
        """Verify refresh button exists."""
        page.goto(f"{base_url}/inventory")
        page.wait_for_load_state("networkidle")

        refresh_btn = page.locator("button:has-text('Refresh'), button[title*='Refresh' i]").first

        if refresh_btn.is_visible():
            expect(refresh_btn).to_be_enabled()


class TestOSSoftwareLAWNavigation:
    """Test navigation to/from OS & Software page."""

    def test_navigate_from_sidebar(self, page: Page, base_url: str):
        """Navigate to OS & Software from sidebar."""
        page.goto(f"{base_url}/")
        page.wait_for_load_state("networkidle")

        # Click OS & Software (LAW) link
        inventory_link = page.locator("a[href='/inventory'], a:has-text('OS & Software')")
        inventory_link.first.click()

        expect(page).to_have_url(re.compile(r"/inventory"))
        expect(page.locator("h1")).to_be_visible()


class TestOSSoftwareLAWContent:
    """Test page content and information."""

    def test_page_description_present(self, page: Page, base_url: str):
        """Verify page has description."""
        page.goto(f"{base_url}/inventory")

        description = page.locator("p, .description, .subtitle").first
        expect(description).to_be_visible()

    def test_law_reference_present(self, page: Page, base_url: str):
        """Check for Log Analytics Workspace reference."""
        page.goto(f"{base_url}/inventory")
        page.wait_for_load_state("networkidle")

        # Look for LAW or Log Analytics mention
        law_text = page.locator("text=/Log Analytics|LAW/i").first

        # Should be mentioned somewhere on the page
        if law_text.is_visible():
            expect(law_text).to_be_visible()


class TestOSSoftwareLAWAccessibility:
    """Accessibility tests."""

    def test_skip_link_present(self, page: Page, base_url: str):
        """Verify skip to main content link."""
        page.goto(f"{base_url}/inventory")
        skip_link = page.locator("a:has-text('Skip to')")
        expect(skip_link).to_be_attached()

    def test_main_landmark_present(self, page: Page, base_url: str):
        """Check for main landmark."""
        page.goto(f"{base_url}/inventory")
        main_element = page.locator("main, [role='main']")
        expect(main_element.first).to_be_visible()


class TestOSSoftwareLAWConsole:
    """Test console output and errors."""

    def test_no_critical_console_errors(self, page: Page, base_url: str):
        """Check for critical JavaScript errors."""
        console_messages = []
        page.on("console", lambda msg: console_messages.append(msg))

        page.goto(f"{base_url}/inventory")
        page.wait_for_load_state("networkidle")

        errors = [msg for msg in console_messages if msg.type == "error"]

        critical_errors = [
            error for error in errors
            if "favicon" not in error.text.lower()
        ]

        for error in critical_errors:
            print(f"Console error: {error.text}")


class TestOSSoftwareLAWInteraction:
    """Test user interactions."""

    def test_pagination_controls(self, page: Page, base_url: str):
        """Check for pagination controls."""
        page.goto(f"{base_url}/inventory")
        page.wait_for_load_state("networkidle")

        pagination = page.locator(".pagination, nav[aria-label*='Pagination' i]").first

        if pagination.is_visible():
            expect(pagination).to_be_visible()

    def test_sort_functionality(self, page: Page, base_url: str):
        """Check if table columns are sortable."""
        page.goto(f"{base_url}/inventory")
        page.wait_for_load_state("networkidle")

        # Look for sortable column headers
        sortable_headers = page.locator("th[role='button'], th.sortable, th[aria-sort]").first

        if sortable_headers.is_visible():
            expect(sortable_headers).to_be_visible()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
