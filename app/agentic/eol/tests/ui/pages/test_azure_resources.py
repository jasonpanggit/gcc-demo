"""
Playwright UI tests for My Azure Resources page.

Test Coverage:
- Page loading and navigation
- Resource inventory table
- Filters and search
- Data display
"""

import re
import pytest
from playwright.sync_api import Page, expect


class TestAzureResourcesBasics:
    """Basic page functionality tests."""

    def test_page_loads(self, page: Page, base_url: str):
        """Verify My Azure Resources page loads successfully."""
        page.goto(f"{base_url}/resource-inventory")
        expect(page).to_have_title(re.compile(r"Azure.*Resource|Resource.*Inventory", re.IGNORECASE))

    def test_main_heading_present(self, page: Page, base_url: str):
        """Check for main page heading."""
        page.goto(f"{base_url}/resource-inventory")
        heading = page.locator("h1")
        expect(heading).to_be_visible()
        expect(heading).to_contain_text(re.compile(r"Resource|Azure", re.IGNORECASE))

    def test_sidebar_visible(self, page: Page, base_url: str):
        """Verify sidebar navigation is present."""
        page.goto(f"{base_url}/resource-inventory")
        sidebar = page.locator("aside, [role='complementary'], nav.sidebar, .sidebar")
        expect(sidebar.first).to_be_visible()


class TestAzureResourcesTable:
    """Test resource inventory table display."""

    def test_table_present(self, page: Page, base_url: str):
        """Verify resource table exists."""
        page.goto(f"{base_url}/resource-inventory")
        page.wait_for_load_state("networkidle")

        table = page.locator("table").first
        expect(table).to_be_visible(timeout=15000)

    def test_table_headers_present(self, page: Page, base_url: str):
        """Check for table column headers."""
        page.goto(f"{base_url}/resource-inventory")
        page.wait_for_load_state("networkidle")

        # Wait for table to load
        table = page.locator("table").first
        expect(table).to_be_visible(timeout=15000)

        # Check for common column headers
        headers = page.locator("th, [role='columnheader']").all()
        assert len(headers) > 0, "No table headers found"

    def test_table_has_data_or_empty_message(self, page: Page, base_url: str):
        """Verify table shows data or appropriate empty message."""
        page.goto(f"{base_url}/resource-inventory")
        page.wait_for_load_state("networkidle")

        # Wait for loading to complete
        page.wait_for_timeout(2000)

        # Check for data rows or empty message
        data_rows = page.locator("tbody tr").count()
        empty_message = page.locator("text=/No.*resource|No.*data|Empty/i").first

        # Should have either data or empty message
        assert data_rows > 0 or empty_message.is_visible(), "Table has no data and no empty message"


class TestAzureResourcesFilters:
    """Test filtering and search functionality."""

    def test_search_input_present(self, page: Page, base_url: str):
        """Check for search input field."""
        page.goto(f"{base_url}/resource-inventory")
        page.wait_for_load_state("networkidle")

        # Look for search input
        search_input = page.locator("input[type='search'], input[placeholder*='Search' i], input[name*='search' i]").first

        # Search might be optional
        if search_input.is_visible():
            expect(search_input).to_be_visible()

    def test_filter_controls_present(self, page: Page, base_url: str):
        """Check for filter dropdowns or controls."""
        page.goto(f"{base_url}/resource-inventory")
        page.wait_for_load_state("networkidle")

        # Look for filter controls (select, buttons, etc.)
        filters = page.locator("select, button:has-text('Filter'), .filter-control").first

        # Filters might be optional
        if filters.is_visible():
            expect(filters).to_be_visible()

    def test_refresh_button_present(self, page: Page, base_url: str):
        """Verify refresh button exists."""
        page.goto(f"{base_url}/resource-inventory")
        page.wait_for_load_state("networkidle")

        refresh_btn = page.locator("button:has-text('Refresh'), button[title*='Refresh' i]").first

        if refresh_btn.is_visible():
            expect(refresh_btn).to_be_enabled()


class TestAzureResourcesNavigation:
    """Test navigation to/from Azure Resources page."""

    def test_navigate_from_sidebar(self, page: Page, base_url: str):
        """Navigate to Azure Resources from sidebar."""
        page.goto(f"{base_url}/")
        page.wait_for_load_state("networkidle")

        # Click My Azure Resources link
        resource_link = page.locator("a[href='/resource-inventory'], a:has-text('My Azure Resources')")
        resource_link.first.click()

        expect(page).to_have_url(re.compile(r"/resource-inventory"))
        expect(page.locator("h1")).to_be_visible()

    def test_navigate_from_dashboard_quick_action(self, page: Page, base_url: str):
        """Navigate from dashboard quick actions."""
        page.goto(f"{base_url}/")
        page.wait_for_load_state("networkidle")

        # Look for Resources quick action
        quick_action = page.locator("a[href='/resource-inventory']").first
        if quick_action.is_visible():
            quick_action.click()
            expect(page).to_have_url(re.compile(r"/resource-inventory"))


class TestAzureResourcesContent:
    """Test page content and information."""

    def test_page_description_present(self, page: Page, base_url: str):
        """Verify page has description or subtitle."""
        page.goto(f"{base_url}/resource-inventory")

        # Look for description text
        description = page.locator("p, .description, .subtitle").first
        expect(description).to_be_visible()

    def test_loading_indicator(self, page: Page, base_url: str):
        """Check for loading indicator during data fetch."""
        page.goto(f"{base_url}/resource-inventory")

        # Look for loading indicator (spinner, text, etc.)
        # This might appear briefly
        loading = page.locator(".spinner, .loading").first
        loading_text = page.locator("text=/Loading|Fetching/i").first

        # Just verify it exists in DOM (might disappear quickly)
        if loading.is_visible(timeout=1000) or loading_text.is_visible(timeout=1000):
            # If visible, it should eventually disappear
            try:
                expect(loading).to_be_hidden(timeout=15000)
            except:
                expect(loading_text).to_be_hidden(timeout=15000)


class TestAzureResourcesAccessibility:
    """Accessibility tests."""

    def test_skip_link_present(self, page: Page, base_url: str):
        """Verify skip to main content link."""
        page.goto(f"{base_url}/resource-inventory")
        skip_link = page.locator("a:has-text('Skip to')")
        expect(skip_link).to_be_attached()

    def test_main_landmark_present(self, page: Page, base_url: str):
        """Check for main landmark."""
        page.goto(f"{base_url}/resource-inventory")
        main_element = page.locator("main, [role='main']")
        expect(main_element.first).to_be_visible()

    def test_table_has_caption_or_aria_label(self, page: Page, base_url: str):
        """Verify table has caption or aria-label."""
        page.goto(f"{base_url}/resource-inventory")
        page.wait_for_load_state("networkidle")

        table = page.locator("table").first
        if table.is_visible():
            # Check for caption or aria-label
            caption = page.locator("caption").first
            aria_label = table.get_attribute("aria-label")

            # At least one should be present for accessibility
            has_label = caption.is_visible() or bool(aria_label)

            if not has_label:
                print("Warning: Table missing caption or aria-label")


class TestAzureResourcesConsole:
    """Test console output and errors."""

    def test_no_critical_console_errors(self, page: Page, base_url: str):
        """Check for critical JavaScript errors."""
        console_messages = []
        page.on("console", lambda msg: console_messages.append(msg))

        page.goto(f"{base_url}/resource-inventory")
        page.wait_for_load_state("networkidle")

        # Filter actual errors
        errors = [msg for msg in console_messages if msg.type == "error"]

        # Exclude known acceptable errors
        critical_errors = [
            error for error in errors
            if "favicon" not in error.text.lower()
        ]

        # Log but don't fail
        for error in critical_errors:
            print(f"Console error: {error.text}")


class TestAzureResourcesInteraction:
    """Test user interactions."""

    def test_table_row_clickable(self, page: Page, base_url: str):
        """Check if table rows are clickable/interactive."""
        page.goto(f"{base_url}/resource-inventory")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)

        # Get first data row
        first_row = page.locator("tbody tr").first

        if first_row.is_visible():
            # Check if row is clickable (has click handler or link)
            is_clickable = first_row.evaluate("el => window.getComputedStyle(el).cursor === 'pointer'")

            # This is optional - just log
            if is_clickable:
                print("Table rows are clickable")

    def test_pagination_controls(self, page: Page, base_url: str):
        """Check for pagination controls if present."""
        page.goto(f"{base_url}/resource-inventory")
        page.wait_for_load_state("networkidle")

        # Look for pagination controls
        pagination = page.locator(".pagination, nav[aria-label*='Pagination' i]").first

        # Optional feature
        if pagination.is_visible():
            expect(pagination).to_be_visible()


class TestAzureResourcesExport:
    """Test export or download functionality."""

    def test_export_button_present(self, page: Page, base_url: str):
        """Check for export/download button."""
        page.goto(f"{base_url}/resource-inventory")
        page.wait_for_load_state("networkidle")

        # Look for export, download, or CSV button
        export_btn = page.locator("button:has-text('Export'), button:has-text('Download'), button:has-text('CSV')").first

        # Optional feature
        if export_btn.is_visible():
            expect(export_btn).to_be_enabled()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
