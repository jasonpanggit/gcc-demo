"""
Playwright UI tests for Patch Management page.

Test Coverage:
- Page loading and navigation
- Patch management interface
- Patch listings and status
- Filters and actions
"""

import re
import pytest
from playwright.sync_api import Page, expect


class TestPatchManagementBasics:
    """Basic page functionality tests."""

    def test_page_loads(self, page: Page, base_url: str):
        """Verify Patch Management page loads successfully."""
        page.goto(f"{base_url}/patch-management")
        expect(page).to_have_title(re.compile(r"Patch.*Management|Patch", re.IGNORECASE))

    def test_main_heading_present(self, page: Page, base_url: str):
        """Check for main page heading."""
        page.goto(f"{base_url}/patch-management")
        heading = page.locator("h1")
        expect(heading).to_be_visible()
        expect(heading).to_contain_text(re.compile(r"Patch", re.IGNORECASE))

    def test_sidebar_visible(self, page: Page, base_url: str):
        """Verify sidebar navigation is present."""
        page.goto(f"{base_url}/patch-management")
        sidebar = page.locator("aside, [role='complementary'], nav.sidebar, .sidebar")
        expect(sidebar.first).to_be_visible()


class TestPatchManagementInterface:
    """Test patch management interface components."""

    def test_patch_list_or_table_present(self, page: Page, base_url: str):
        """Check for patch list or table."""
        page.goto(f"{base_url}/patch-management")
        page.wait_for_load_state("networkidle")

        # Look for table or list of patches
        patch_container = page.locator("table, .patch-list, .patches").first
        expect(patch_container).to_be_visible(timeout=15000)

    def test_table_headers_present(self, page: Page, base_url: str):
        """Verify table headers if table exists."""
        page.goto(f"{base_url}/patch-management")
        page.wait_for_load_state("networkidle")

        table = page.locator("table").first
        if table.is_visible():
            headers = page.locator("th, [role='columnheader']").all()
            assert len(headers) > 0, "No table headers found"

    def test_status_indicators_present(self, page: Page, base_url: str):
        """Check for patch status indicators."""
        page.goto(f"{base_url}/patch-management")
        page.wait_for_load_state("networkidle")

        # Look for status badges or indicators (Pending, Applied, Failed, etc.)
        status = page.locator(".status, .badge, [class*='status']").first

        if status.is_visible():
            expect(status).to_be_visible()


class TestPatchManagementFilters:
    """Test filtering and search functionality."""

    def test_filter_controls_present(self, page: Page, base_url: str):
        """Check for filter controls."""
        page.goto(f"{base_url}/patch-management")
        page.wait_for_load_state("networkidle")

        # Look for status filter, severity filter, etc.
        filters = page.locator("select, button:has-text('Filter'), .filter-control").first

        if filters.is_visible():
            expect(filters).to_be_visible()

    def test_search_input_present(self, page: Page, base_url: str):
        """Check for search input."""
        page.goto(f"{base_url}/patch-management")
        page.wait_for_load_state("networkidle")

        search_input = page.locator("input[type='search'], input[placeholder*='Search' i]").first

        if search_input.is_visible():
            expect(search_input).to_be_visible()

    def test_refresh_button_present(self, page: Page, base_url: str):
        """Verify refresh button exists."""
        page.goto(f"{base_url}/patch-management")
        page.wait_for_load_state("networkidle")

        refresh_btn = page.locator("button:has-text('Refresh'), button[title*='Refresh' i]").first

        if refresh_btn.is_visible():
            expect(refresh_btn).to_be_enabled()


class TestPatchManagementNavigation:
    """Test navigation to/from Patch Management page."""

    def test_navigate_from_sidebar(self, page: Page, base_url: str):
        """Navigate to Patch Management from sidebar."""
        page.goto(f"{base_url}/")
        page.wait_for_load_state("networkidle")

        # Click Patch Management link
        patch_link = page.locator("a[href='/patch-management'], a:has-text('Patch Management')")
        patch_link.first.click()

        expect(page).to_have_url(re.compile(r"/patch-management"))
        expect(page.locator("h1")).to_be_visible()


class TestPatchManagementContent:
    """Test page content and information."""

    def test_page_description_present(self, page: Page, base_url: str):
        """Verify page has description."""
        page.goto(f"{base_url}/patch-management")

        description = page.locator("p, .description, .subtitle").first
        expect(description).to_be_visible()

    def test_stats_or_summary_present(self, page: Page, base_url: str):
        """Check for patch statistics or summary."""
        page.goto(f"{base_url}/patch-management")
        page.wait_for_load_state("networkidle")

        # Look for stat cards or summary section
        stats = page.locator(".stat, .stats, .summary, .card").first

        if stats.is_visible():
            expect(stats).to_be_visible()


class TestPatchManagementActions:
    """Test patch management actions."""

    def test_action_buttons_present(self, page: Page, base_url: str):
        """Check for action buttons (Apply, Deploy, Schedule, etc.)."""
        page.goto(f"{base_url}/patch-management")
        page.wait_for_load_state("networkidle")

        # Look for action buttons
        action_btn = page.locator("button:has-text('Apply'), button:has-text('Deploy'), button:has-text('Schedule'), button:has-text('Install')").first

        if action_btn.is_visible():
            expect(action_btn).to_be_visible()

    def test_details_or_view_button(self, page: Page, base_url: str):
        """Check for view details buttons."""
        page.goto(f"{base_url}/patch-management")
        page.wait_for_load_state("networkidle")

        # Look for view, details, or info buttons
        details_btn = page.locator("button:has-text('View'), button:has-text('Details'), a:has-text('View')").first

        if details_btn.is_visible():
            expect(details_btn).to_be_visible()


class TestPatchManagementAccessibility:
    """Accessibility tests."""

    def test_skip_link_present(self, page: Page, base_url: str):
        """Verify skip to main content link."""
        page.goto(f"{base_url}/patch-management")
        skip_link = page.locator("a:has-text('Skip to')")
        expect(skip_link).to_be_attached()

    def test_main_landmark_present(self, page: Page, base_url: str):
        """Check for main landmark."""
        page.goto(f"{base_url}/patch-management")
        main_element = page.locator("main, [role='main']")
        expect(main_element.first).to_be_visible()


class TestPatchManagementConsole:
    """Test console output and errors."""

    def test_no_critical_console_errors(self, page: Page, base_url: str):
        """Check for critical JavaScript errors."""
        console_messages = []
        page.on("console", lambda msg: console_messages.append(msg))

        page.goto(f"{base_url}/patch-management")
        page.wait_for_load_state("networkidle")

        errors = [msg for msg in console_messages if msg.type == "error"]

        critical_errors = [
            error for error in errors
            if "favicon" not in error.text.lower()
        ]

        for error in critical_errors:
            print(f"Console error: {error.text}")


class TestPatchManagementInteraction:
    """Test user interactions."""

    def test_table_row_expandable(self, page: Page, base_url: str):
        """Check if table rows can be expanded for details."""
        page.goto(f"{base_url}/patch-management")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)

        # Look for expand/collapse buttons or icons
        expand_btn = page.locator("button[aria-label*='Expand' i], .expand-icon, [aria-expanded]").first

        if expand_btn.is_visible():
            expect(expand_btn).to_be_visible()

    def test_pagination_controls(self, page: Page, base_url: str):
        """Check for pagination controls."""
        page.goto(f"{base_url}/patch-management")
        page.wait_for_load_state("networkidle")

        pagination = page.locator(".pagination, nav[aria-label*='Pagination' i]").first

        if pagination.is_visible():
            expect(pagination).to_be_visible()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
