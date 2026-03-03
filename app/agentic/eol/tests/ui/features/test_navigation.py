"""
UI tests for Navigation functionality across the application.
"""
import re
import pytest
from playwright.sync_api import Page, expect


class TestNavigation:
    """Test suite for application navigation."""

    def test_navigation_to_dashboard(self, authenticated_page: Page):
        """Test navigation to Dashboard."""
        # Navigate away first, then back to dashboard
        authenticated_page.get_by_role("link", name="EOL Dates Database").click()
        authenticated_page.wait_for_load_state("networkidle")

        # Now navigate to dashboard
        authenticated_page.get_by_role("link", name="Dashboard", exact=True).click()
        authenticated_page.wait_for_load_state("networkidle")

        expect(authenticated_page).to_have_url(re.compile(r".*/"))
        expect(authenticated_page).to_have_title("Dashboard — Azure Agentic Platform")

    def test_navigation_to_analytics(self, authenticated_page: Page):
        """Test navigation to Analytics."""
        # Ensure we're on dashboard first
        authenticated_page.goto(authenticated_page.url.split('?')[0].rstrip('/').rsplit('/', 1)[0] + '/')
        authenticated_page.wait_for_load_state("networkidle")

        authenticated_page.get_by_role("link", name="Analytics", exact=True).click()
        authenticated_page.wait_for_load_state("networkidle")

        expect(authenticated_page).to_have_url(re.compile(r".*/visualizations"))
        expect(authenticated_page).to_have_title(
            "Data Visualizations Demo - Azure Agentic Platform"
        )

    def test_navigation_to_azure_mcp(self, authenticated_page: Page):
        """Test navigation to Azure MCP AI."""
        # Start from a known page
        if "azure-mcp" not in authenticated_page.url:
            authenticated_page.get_by_role("link", name="Azure MCP", exact=False).first.click()
            authenticated_page.wait_for_load_state("networkidle")

        expect(authenticated_page).to_have_url(re.compile(r".*/azure-mcp"))
        expect(authenticated_page).to_have_title("Azure MCP Server - Azure Agentic Platform")

    def test_navigation_to_sre_assistant(self, authenticated_page: Page):
        """Test navigation to SRE Assistant."""
        authenticated_page.get_by_role("link", name="SRE Assistant", exact=False).first.click()
        authenticated_page.wait_for_load_state("networkidle")

        expect(authenticated_page).to_have_url(re.compile(r".*/sre"))
        expect(authenticated_page).to_have_title("SRE Assistant - Azure Agentic Platform")

    def test_navigation_to_eol_inventory(self, authenticated_page: Page):
        """Test navigation to EOL Dates Database."""
        authenticated_page.get_by_role("link", name="EOL Dates Database").click()
        authenticated_page.wait_for_load_state("networkidle")

        expect(authenticated_page).to_have_url(re.compile(r".*/eol-inventory"))
        expect(authenticated_page).to_have_title("EOL Dates Database")

    def test_breadcrumb_navigation(self, authenticated_page: Page):
        """Test breadcrumb or back navigation."""
        # Navigate to a deep page
        authenticated_page.get_by_role("link", name="EOL Dates Database").click()
        authenticated_page.wait_for_load_state("networkidle")

        # Navigate back to dashboard
        authenticated_page.get_by_role("link", name="Dashboard", exact=True).click()
        authenticated_page.wait_for_load_state("networkidle")

        expect(authenticated_page).to_have_url(re.compile(r".*/"))

    def test_quick_action_navigation(self, authenticated_page: Page):
        """Test navigation via quick actions on dashboard."""
        # Test Azure MCP quick action
        azure_mcp_link = authenticated_page.get_by_role(
            "link", name="Azure MCP AI Assistant"
        )
        azure_mcp_link.click()
        authenticated_page.wait_for_load_state("networkidle")

        expect(authenticated_page).to_have_url(re.compile(r".*/azure-mcp"))

    def test_sidebar_remains_visible_after_navigation(self, authenticated_page: Page):
        """Test sidebar remains visible after navigating."""
        # Navigate to different pages
        authenticated_page.get_by_role("link", name="Analytics", exact=True).click()
        authenticated_page.wait_for_load_state("networkidle")

        # Verify sidebar is still visible
        sidebar = authenticated_page.locator("nav")
        expect(sidebar).to_be_visible()
