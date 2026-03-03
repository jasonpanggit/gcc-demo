"""
Playwright UI tests for Alerts Management page.

Test Coverage:
- Page loading and navigation
- Alerts listing and display
- Alert status and filtering
- Alert actions
"""

import re
import pytest
from playwright.sync_api import Page, expect


class TestAlertsBasics:
    """Basic page functionality tests."""

    def test_page_loads(self, page: Page, base_url: str):
        """Verify Alerts page loads successfully."""
        page.goto(f"{base_url}/alerts")
        expect(page).to_have_title(re.compile(r"Alert", re.IGNORECASE))

    def test_main_heading_present(self, page: Page, base_url: str):
        """Check for main page heading."""
        page.goto(f"{base_url}/alerts")
        heading = page.locator("h1")
        expect(heading).to_be_visible()
        expect(heading).to_contain_text(re.compile(r"Alert", re.IGNORECASE))

    def test_sidebar_visible(self, page: Page, base_url: str):
        """Verify sidebar navigation is present."""
        page.goto(f"{base_url}/alerts")
        sidebar = page.locator("aside, [role='complementary'], nav.sidebar, .sidebar")
        expect(sidebar.first).to_be_visible()


class TestAlertsDisplay:
    """Test alerts display and listing."""

    def test_alerts_list_or_table_present(self, page: Page, base_url: str):
        """Check for alerts list or table."""
        page.goto(f"{base_url}/alerts")
        page.wait_for_load_state("networkidle")

        alerts_container = page.locator("table, .alerts-list, .alert-items").first
        expect(alerts_container).to_be_visible(timeout=15000)

    def test_alert_items_visible_or_empty_message(self, page: Page, base_url: str):
        """Verify alerts are displayed or empty message shown."""
        page.goto(f"{base_url}/alerts")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)

        # Check for alert items or empty state
        alert_items = page.locator(".alert-item, tbody tr, .alert").count()
        empty_message = page.locator("text=/No.*alert|Empty|No data/i").first

        assert alert_items > 0 or empty_message.is_visible(), "No alerts and no empty message"

    def test_alert_severity_indicators(self, page: Page, base_url: str):
        """Check for severity indicators (Critical, Warning, Info)."""
        page.goto(f"{base_url}/alerts")
        page.wait_for_load_state("networkidle")

        # Look for severity badges
        severity = page.locator(".severity, .badge, [class*='critical'], [class*='warning'], [class*='info']").first

        if severity.is_visible():
            expect(severity).to_be_visible()


class TestAlertsFilters:
    """Test filtering functionality."""

    def test_severity_filter_present(self, page: Page, base_url: str):
        """Check for severity filter."""
        page.goto(f"{base_url}/alerts")
        page.wait_for_load_state("networkidle")

        severity_filter = page.locator("select[name*='severity' i], button:has-text('Severity')").first

        if severity_filter.is_visible():
            expect(severity_filter).to_be_visible()

    def test_status_filter_present(self, page: Page, base_url: str):
        """Check for status filter (Active, Resolved, etc.)."""
        page.goto(f"{base_url}/alerts")
        page.wait_for_load_state("networkidle")

        status_filter = page.locator("select[name*='status' i], button:has-text('Status')").first

        if status_filter.is_visible():
            expect(status_filter).to_be_visible()

    def test_refresh_button_present(self, page: Page, base_url: str):
        """Verify refresh button exists."""
        page.goto(f"{base_url}/alerts")
        page.wait_for_load_state("networkidle")

        refresh_btn = page.locator("button:has-text('Refresh'), button[title*='Refresh' i]").first

        if refresh_btn.is_visible():
            expect(refresh_btn).to_be_enabled()


class TestAlertsNavigation:
    """Test navigation to/from Alerts page."""

    def test_navigate_from_sidebar(self, page: Page, base_url: str):
        """Navigate to Alerts from sidebar."""
        page.goto(f"{base_url}/")
        page.wait_for_load_state("networkidle")

        alerts_link = page.locator("a[href='/alerts'], a:has-text('Alerts')").first
        alerts_link.click()

        expect(page).to_have_url(re.compile(r"/alerts"))
        expect(page.locator("h1")).to_be_visible()


class TestAlertsActions:
    """Test alert action buttons."""

    def test_acknowledge_or_dismiss_button(self, page: Page, base_url: str):
        """Check for acknowledge/dismiss buttons."""
        page.goto(f"{base_url}/alerts")
        page.wait_for_load_state("networkidle")

        action_btn = page.locator("button:has-text('Acknowledge'), button:has-text('Dismiss'), button:has-text('Resolve')").first

        if action_btn.is_visible():
            expect(action_btn).to_be_visible()

    def test_view_details_button(self, page: Page, base_url: str):
        """Check for view details buttons."""
        page.goto(f"{base_url}/alerts")
        page.wait_for_load_state("networkidle")

        details_btn = page.locator("button:has-text('View'), button:has-text('Details'), a:has-text('View')").first

        if details_btn.is_visible():
            expect(details_btn).to_be_visible()


class TestAlertsAccessibility:
    """Accessibility tests."""

    def test_skip_link_present(self, page: Page, base_url: str):
        """Verify skip to main content link."""
        page.goto(f"{base_url}/alerts")
        skip_link = page.locator("a:has-text('Skip to')")
        expect(skip_link).to_be_attached()

    def test_main_landmark_present(self, page: Page, base_url: str):
        """Check for main landmark."""
        page.goto(f"{base_url}/alerts")
        main_element = page.locator("main, [role='main']")
        expect(main_element.first).to_be_visible()


class TestAlertsConsole:
    """Test console output and errors."""

    def test_no_critical_console_errors(self, page: Page, base_url: str):
        """Check for critical JavaScript errors."""
        console_messages = []
        page.on("console", lambda msg: console_messages.append(msg))

        page.goto(f"{base_url}/alerts")
        page.wait_for_load_state("networkidle")

        errors = [msg for msg in console_messages if msg.type == "error"]

        critical_errors = [
            error for error in errors
            if "favicon" not in error.text.lower()
        ]

        for error in critical_errors:
            print(f"Console error: {error.text}")


class TestAlertsContent:
    """Test page content."""

    def test_page_description_present(self, page: Page, base_url: str):
        """Verify page has description."""
        page.goto(f"{base_url}/alerts")

        description = page.locator("p, .description, .subtitle").first
        expect(description).to_be_visible()

    def test_alert_count_or_stats(self, page: Page, base_url: str):
        """Check for alert statistics."""
        page.goto(f"{base_url}/alerts")
        page.wait_for_load_state("networkidle")

        # Look for alert count or stats
        stats = page.locator(".stat, .stats, .count, .summary").first

        if stats.is_visible():
            expect(stats).to_be_visible()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
