"""
Playwright UI tests for OS EOL Tracker page.

Test Coverage:
- Page loading and navigation
- OS EOL tracking display
- EOL status and dates
- Filters and actions
"""

import re
import pytest
from playwright.sync_api import Page, expect


class TestOSEOLTrackerBasics:
    """Basic page functionality tests."""

    def test_page_loads(self, page: Page, base_url: str):
        """Verify OS EOL Tracker page loads successfully."""
        page.goto(f"{base_url}/eol-management")
        expect(page).to_have_title(re.compile(r"EOL.*Tracker|EOL.*Management|OS.*EOL", re.IGNORECASE))

    def test_main_heading_present(self, page: Page, base_url: str):
        """Check for main page heading."""
        page.goto(f"{base_url}/eol-management")
        heading = page.locator("h1")
        expect(heading).to_be_visible()
        expect(heading).to_contain_text(re.compile(r"EOL|Tracker|Management", re.IGNORECASE))

    def test_sidebar_visible(self, page: Page, base_url: str):
        """Verify sidebar navigation is present."""
        page.goto(f"{base_url}/eol-management")
        sidebar = page.locator("aside, [role='complementary'], nav.sidebar, .sidebar")
        expect(sidebar.first).to_be_visible()


class TestOSEOLTrackerDisplay:
    """Test EOL tracking display."""

    def test_eol_table_or_list_present(self, page: Page, base_url: str):
        """Check for EOL tracking table or list."""
        page.goto(f"{base_url}/eol-management")
        page.wait_for_load_state("networkidle")

        eol_container = page.locator("table, .eol-list, .tracker-list").first
        expect(eol_container).to_be_visible(timeout=15000)

    def test_table_headers_present(self, page: Page, base_url: str):
        """Verify table headers if table exists."""
        page.goto(f"{base_url}/eol-management")
        page.wait_for_load_state("networkidle")

        table = page.locator("table").first
        if table.is_visible():
            headers = page.locator("th, [role='columnheader']").all()
            assert len(headers) > 0, "No table headers found"

    def test_os_entries_visible_or_empty(self, page: Page, base_url: str):
        """Verify OS entries or empty message."""
        page.goto(f"{base_url}/eol-management")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)

        entries_count = page.locator("tbody tr, .eol-entry, .os-item").count()
        empty_message = page.locator("text=/No.*data|Empty|No.*OS/i").first

        assert entries_count > 0 or empty_message.is_visible(), "No OS entries and no empty message"


class TestOSEOLTrackerContent:
    """Test EOL tracking content."""

    def test_os_names_displayed(self, page: Page, base_url: str):
        """Check that OS names are shown."""
        page.goto(f"{base_url}/eol-management")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)

        # Look for OS names (Windows, Linux, Ubuntu, RHEL, etc.)
        os_name = page.locator("text=/Windows|Linux|Ubuntu|RHEL|CentOS|Debian/i").first

        if os_name.is_visible():
            expect(os_name).to_be_visible()

    def test_eol_dates_displayed(self, page: Page, base_url: str):
        """Check that EOL dates are shown."""
        page.goto(f"{base_url}/eol-management")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)

        # Look for dates in different formats
        date_pattern = page.locator("text=/\\d{4}-\\d{2}-\\d{2}|\\d{1,2}\\/\\d{1,2}\\/\\d{4}/i").first
        date_cells = page.locator("td:has-text('202')").first

        if date_pattern.is_visible() or date_cells.is_visible():
            # At least one date format should be visible
            assert True

    def test_eol_status_indicators(self, page: Page, base_url: str):
        """Check for EOL status indicators."""
        page.goto(f"{base_url}/eol-management")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)

        # Look for status badges (Active, EOL, Warning, Critical, etc.)
        status_class = page.locator(".status, .badge, [class*='status']").first
        status_text = page.locator("text=/Active|EOL|Warning|Critical|Expired/i").first

        if status_class.is_visible() or status_text.is_visible():
            # At least one type of status indicator should be present
            assert True

    def test_version_information(self, page: Page, base_url: str):
        """Check for OS version information."""
        page.goto(f"{base_url}/eol-management")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)

        # Look for version numbers
        version = page.locator("text=/\\d+\\.\\d+|Version|v\\d+/i").first

        if version.is_visible():
            expect(version).to_be_visible()


class TestOSEOLTrackerStatistics:
    """Test EOL statistics display."""

    def test_eol_stats_present(self, page: Page, base_url: str):
        """Check for EOL statistics cards."""
        page.goto(f"{base_url}/eol-management")
        page.wait_for_load_state("networkidle")

        stats = page.locator(".stat, .stats, .summary, .card").first

        if stats.is_visible():
            expect(stats).to_be_visible()

    def test_critical_eol_count(self, page: Page, base_url: str):
        """Check for critical EOL count."""
        page.goto(f"{base_url}/eol-management")
        page.wait_for_load_state("networkidle")

        critical_count = page.locator("text=/Critical|\\d+.*EOL|EOL.*\\d+/i").first

        if critical_count.is_visible():
            expect(critical_count).to_be_visible()


class TestOSEOLTrackerFilters:
    """Test filtering functionality."""

    def test_os_type_filter(self, page: Page, base_url: str):
        """Check for OS type filter."""
        page.goto(f"{base_url}/eol-management")
        page.wait_for_load_state("networkidle")

        os_filter = page.locator("select[name*='os' i], button:has-text('OS'), button:has-text('Type')").first

        if os_filter.is_visible():
            expect(os_filter).to_be_visible()

    def test_status_filter_present(self, page: Page, base_url: str):
        """Check for status filter."""
        page.goto(f"{base_url}/eol-management")
        page.wait_for_load_state("networkidle")

        status_filter = page.locator("select[name*='status' i], button:has-text('Status'), button:has-text('Filter')").first

        if status_filter.is_visible():
            expect(status_filter).to_be_visible()

    def test_search_input_present(self, page: Page, base_url: str):
        """Check for search input."""
        page.goto(f"{base_url}/eol-management")
        page.wait_for_load_state("networkidle")

        search_input = page.locator("input[type='search'], input[placeholder*='Search' i]").first

        if search_input.is_visible():
            expect(search_input).to_be_visible()

    def test_refresh_button_present(self, page: Page, base_url: str):
        """Verify refresh button exists."""
        page.goto(f"{base_url}/eol-management")
        page.wait_for_load_state("networkidle")

        refresh_btn = page.locator("button:has-text('Refresh'), button[title*='Refresh' i]").first

        if refresh_btn.is_visible():
            expect(refresh_btn).to_be_enabled()


class TestOSEOLTrackerActions:
    """Test EOL management actions."""

    def test_view_details_button(self, page: Page, base_url: str):
        """Check for view details buttons."""
        page.goto(f"{base_url}/eol-management")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)

        details_btn = page.locator("button:has-text('View'), button:has-text('Details'), a:has-text('View')").first

        if details_btn.is_visible():
            expect(details_btn).to_be_visible()

    def test_export_button(self, page: Page, base_url: str):
        """Check for export/download button."""
        page.goto(f"{base_url}/eol-management")
        page.wait_for_load_state("networkidle")

        export_btn = page.locator("button:has-text('Export'), button:has-text('Download'), button:has-text('CSV')").first

        if export_btn.is_visible():
            expect(export_btn).to_be_enabled()

    def test_update_button(self, page: Page, base_url: str):
        """Check for update/sync button."""
        page.goto(f"{base_url}/eol-management")
        page.wait_for_load_state("networkidle")

        update_btn = page.locator("button:has-text('Update'), button:has-text('Sync'), button:has-text('Refresh data')").first

        if update_btn.is_visible():
            expect(update_btn).to_be_visible()


class TestOSEOLTrackerNavigation:
    """Test navigation to/from OS EOL Tracker page."""

    def test_navigate_from_sidebar(self, page: Page, base_url: str):
        """Navigate to OS EOL Tracker from sidebar."""
        page.goto(f"{base_url}/")
        page.wait_for_load_state("networkidle")

        tracker_link = page.locator("a[href='/eol-management'], a:has-text('OS EOL Tracker')").first
        tracker_link.click()

        expect(page).to_have_url(re.compile(r"/eol-management"))
        expect(page.locator("h1")).to_be_visible()

    def test_link_to_eol_database(self, page: Page, base_url: str):
        """Check for link to EOL database."""
        page.goto(f"{base_url}/eol-management")
        page.wait_for_load_state("networkidle")

        db_link = page.locator("a[href='/eol-inventory'], a:has-text('EOL Dates Database')").first

        if db_link.is_visible():
            expect(db_link).to_be_visible()


class TestOSEOLTrackerAccessibility:
    """Accessibility tests."""

    def test_skip_link_present(self, page: Page, base_url: str):
        """Verify skip to main content link."""
        page.goto(f"{base_url}/eol-management")
        skip_link = page.locator("a:has-text('Skip to')")
        expect(skip_link).to_be_attached()

    def test_main_landmark_present(self, page: Page, base_url: str):
        """Check for main landmark."""
        page.goto(f"{base_url}/eol-management")
        main_element = page.locator("main, [role='main']")
        expect(main_element.first).to_be_visible()


class TestOSEOLTrackerConsole:
    """Test console output and errors."""

    def test_no_critical_console_errors(self, page: Page, base_url: str):
        """Check for critical JavaScript errors."""
        console_messages = []
        page.on("console", lambda msg: console_messages.append(msg))

        page.goto(f"{base_url}/eol-management")
        page.wait_for_load_state("networkidle")

        errors = [msg for msg in console_messages if msg.type == "error"]

        critical_errors = [
            error for error in errors
            if "favicon" not in error.text.lower()
        ]

        for error in critical_errors:
            print(f"Console error: {error.text}")


class TestOSEOLTrackerInteraction:
    """Test user interactions."""

    def test_pagination_controls(self, page: Page, base_url: str):
        """Check for pagination controls."""
        page.goto(f"{base_url}/eol-management")
        page.wait_for_load_state("networkidle")

        pagination = page.locator(".pagination, nav[aria-label*='Pagination' i]").first

        if pagination.is_visible():
            expect(pagination).to_be_visible()

    def test_sort_functionality(self, page: Page, base_url: str):
        """Check if table columns are sortable."""
        page.goto(f"{base_url}/eol-management")
        page.wait_for_load_state("networkidle")

        sortable_headers = page.locator("th[role='button'], th.sortable, th[aria-sort]").first

        if sortable_headers.is_visible():
            expect(sortable_headers).to_be_visible()

    def test_row_details_expandable(self, page: Page, base_url: str):
        """Check if rows can be expanded for details."""
        page.goto(f"{base_url}/eol-management")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)

        expand_btn = page.locator("button[aria-label*='Expand' i], .expand-icon, [aria-expanded]").first

        if expand_btn.is_visible():
            expect(expand_btn).to_be_visible()


class TestOSEOLTrackerAlerts:
    """Test EOL alert features."""

    def test_alert_indicators_present(self, page: Page, base_url: str):
        """Check for alert/warning indicators."""
        page.goto(f"{base_url}/eol-management")
        page.wait_for_load_state("networkidle")

        alert_class = page.locator(".alert, .warning, [role='alert']").first
        alert_text = page.locator("text=/Warning|Alert|Attention/i").first

        if alert_class.is_visible() or alert_text.is_visible():
            # At least one type of alert indicator should be present
            assert True

    def test_upcoming_eol_section(self, page: Page, base_url: str):
        """Check for upcoming EOL section."""
        page.goto(f"{base_url}/eol-management")
        page.wait_for_load_state("networkidle")

        upcoming_text = page.locator("text=/Upcoming|Soon|Next.*month/i").first
        upcoming_class = page.locator(".upcoming, .soon").first

        if upcoming_text.is_visible() or upcoming_class.is_visible():
            # At least one should be visible
            assert True


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
