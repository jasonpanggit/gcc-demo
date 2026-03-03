"""
UI tests for the Dashboard page.
"""
import pytest
from playwright.sync_api import Page, expect


class TestDashboard:
    """Test suite for Dashboard functionality."""

    def test_dashboard_loads(self, authenticated_page: Page):
        """Test that the dashboard page loads successfully."""
        # Verify page title
        expect(authenticated_page).to_have_title("Dashboard — Azure Agentic Platform")

        # Verify main heading
        heading = authenticated_page.get_by_role("heading", name="Dashboard", level=1)
        expect(heading).to_be_visible()

        # Verify welcome message
        welcome = authenticated_page.get_by_text("Welcome to Azure Agentic Platform")
        expect(welcome).to_be_visible()

    def test_dashboard_sidebar_navigation(self, authenticated_page: Page):
        """Test sidebar navigation elements are present."""
        # Verify sidebar sections (use .first to handle duplicates)
        expect(authenticated_page.get_by_text("Main", exact=True).first).to_be_visible()
        expect(authenticated_page.get_by_text("AI Assistants", exact=True).first).to_be_visible()
        expect(authenticated_page.get_by_text("Resources", exact=True).first).to_be_visible()
        expect(authenticated_page.get_by_text("Management", exact=True).first).to_be_visible()

    def test_dashboard_stats_cards(self, authenticated_page: Page):
        """Test that stats cards are displayed on dashboard."""
        # Check for stat cards (use first to avoid multiple matches)
        expect(authenticated_page.get_by_text("Active Agents", exact=True).first).to_be_visible()
        expect(authenticated_page.get_by_text("Cached Items", exact=True).first).to_be_visible()
        expect(authenticated_page.get_by_text("AI Sessions", exact=True).first).to_be_visible()
        expect(authenticated_page.get_by_text("Database Items", exact=True).first).to_be_visible()

    def test_dashboard_quick_actions(self, authenticated_page: Page):
        """Test quick action buttons are present."""
        # Verify Quick Actions section
        expect(authenticated_page.get_by_role("heading", name="Quick Actions")).to_be_visible()

        # Verify quick action links
        expect(authenticated_page.get_by_role("link", name="Azure MCP AI Assistant")).to_be_visible()
        expect(authenticated_page.get_by_role("link", name="EOL Search Find Lifecycles")).to_be_visible()
        expect(authenticated_page.get_by_role("link", name="Analytics View Reports")).to_be_visible()

    def test_dashboard_recent_activity_table(self, authenticated_page: Page):
        """Test recent activity table is present."""
        expect(authenticated_page.get_by_role("heading", name="Recent Activity")).to_be_visible()

        # Table may be loading or empty, so check for table structure or loading indicator
        table_or_loading = authenticated_page.locator("table, .loading, [class*='loading']").first
        expect(table_or_loading).to_be_visible()

    def test_dashboard_system_health(self, authenticated_page: Page):
        """Test system health section is displayed."""
        expect(authenticated_page.get_by_role("heading", name="System Health")).to_be_visible()

    def test_dashboard_refresh_button(self, authenticated_page: Page):
        """Test refresh button functionality."""
        refresh_button = authenticated_page.get_by_role("button", name="Refresh")
        expect(refresh_button).to_be_visible()
        expect(refresh_button).to_be_enabled()

        # Click refresh and verify no errors
        refresh_button.click()
        authenticated_page.wait_for_load_state("networkidle")

    def test_dashboard_dark_mode_toggle(self, authenticated_page: Page):
        """Test dark mode toggle button."""
        dark_mode_toggle = authenticated_page.get_by_role("button", name="Toggle dark mode")
        expect(dark_mode_toggle).to_be_visible()
        expect(dark_mode_toggle).to_be_enabled()

    def test_dashboard_user_menu(self, authenticated_page: Page):
        """Test user menu is accessible."""
        user_menu = authenticated_page.get_by_role("button", name="User menu")
        expect(user_menu).to_be_visible()
        expect(user_menu).to_be_enabled()

    def test_dashboard_notifications(self, authenticated_page: Page):
        """Test notifications button is present."""
        notifications = authenticated_page.get_by_role("button", name="Notifications")
        expect(notifications).to_be_visible()

    def test_dashboard_sidebar_toggle(self, authenticated_page: Page):
        """Test sidebar toggle button."""
        toggle_button = authenticated_page.get_by_role("button", name="Toggle sidebar")
        expect(toggle_button).to_be_visible()
        expect(toggle_button).to_be_enabled()
