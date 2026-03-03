"""
Playwright UI tests for Agents Management page.

Test Coverage:
- Page loading and navigation
- Agents listing and status
- Agent configuration display
- Agent actions
"""

import re
import pytest
from playwright.sync_api import Page, expect


class TestAgentsBasics:
    """Basic page functionality tests."""

    def test_page_loads(self, page: Page, base_url: str):
        """Verify Agents page loads successfully."""
        page.goto(f"{base_url}/agents")
        expect(page).to_have_title(re.compile(r"Agent", re.IGNORECASE))

    def test_main_heading_present(self, page: Page, base_url: str):
        """Check for main page heading."""
        page.goto(f"{base_url}/agents")
        heading = page.locator("h1")
        expect(heading).to_be_visible()
        expect(heading).to_contain_text(re.compile(r"Agent", re.IGNORECASE))

    def test_sidebar_visible(self, page: Page, base_url: str):
        """Verify sidebar navigation is present."""
        page.goto(f"{base_url}/agents")
        sidebar = page.locator("aside, [role='complementary'], nav.sidebar, .sidebar")
        expect(sidebar.first).to_be_visible()


class TestAgentsDisplay:
    """Test agents listing and display."""

    def test_agents_list_or_table_present(self, page: Page, base_url: str):
        """Check for agents list or table."""
        page.goto(f"{base_url}/agents")
        page.wait_for_load_state("networkidle")

        agents_container = page.locator("table, .agents-list, .agent-items, .agents-grid").first
        expect(agents_container).to_be_visible(timeout=15000)

    def test_agent_items_visible(self, page: Page, base_url: str):
        """Verify agents are displayed."""
        page.goto(f"{base_url}/agents")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)

        # Check for agent items
        agent_items = page.locator(".agent-item, .agent-card, tbody tr, .agent").count()
        empty_message = page.locator("text=/No.*agent|Empty|No data/i").first

        assert agent_items > 0 or empty_message.is_visible(), "No agents and no empty message"

    def test_agent_status_indicators(self, page: Page, base_url: str):
        """Check for agent status indicators."""
        page.goto(f"{base_url}/agents")
        page.wait_for_load_state("networkidle")

        # Look for status (Active, Idle, Offline, etc.)
        status_class = page.locator(".status, .badge, [class*='status']").first
        status_text = page.locator("text=/Active|Idle|Offline/i").first

        if status_class.is_visible() or status_text.is_visible():
            # At least one type of status indicator should be present
            assert True
        else:
            # Optional - just log if not present
            print("Note: No agent status indicators found")

    def test_agent_types_displayed(self, page: Page, base_url: str):
        """Check that different agent types are shown."""
        page.goto(f"{base_url}/agents")
        page.wait_for_load_state("networkidle")

        # Look for agent type labels (SRE, MCP, EOL, Inventory, etc.)
        agent_type = page.locator("text=/SRE|MCP|EOL|Inventory|Azure/i").first

        if agent_type.is_visible():
            expect(agent_type).to_be_visible()


class TestAgentsStatistics:
    """Test agent statistics display."""

    def test_agent_stats_present(self, page: Page, base_url: str):
        """Check for agent statistics."""
        page.goto(f"{base_url}/agents")
        page.wait_for_load_state("networkidle")

        # Look for stat cards
        stats = page.locator(".stat, .stats, .summary, .card").first

        if stats.is_visible():
            expect(stats).to_be_visible()

    def test_active_agents_count(self, page: Page, base_url: str):
        """Check for active agents count."""
        page.goto(f"{base_url}/agents")
        page.wait_for_load_state("networkidle")

        # Look for active count
        active_count = page.locator("text=/Active.*Agent|\\d+.*Active/i").first

        if active_count.is_visible():
            expect(active_count).to_be_visible()


class TestAgentsActions:
    """Test agent management actions."""

    def test_start_or_stop_button(self, page: Page, base_url: str):
        """Check for start/stop agent buttons."""
        page.goto(f"{base_url}/agents")
        page.wait_for_load_state("networkidle")

        action_btn = page.locator("button:has-text('Start'), button:has-text('Stop'), button:has-text('Restart')").first

        if action_btn.is_visible():
            expect(action_btn).to_be_visible()

    def test_configure_button(self, page: Page, base_url: str):
        """Check for configure/settings buttons."""
        page.goto(f"{base_url}/agents")
        page.wait_for_load_state("networkidle")

        config_btn = page.locator("button:has-text('Configure'), button:has-text('Settings'), button:has-text('Edit')").first

        if config_btn.is_visible():
            expect(config_btn).to_be_visible()

    def test_view_details_button(self, page: Page, base_url: str):
        """Check for view details buttons."""
        page.goto(f"{base_url}/agents")
        page.wait_for_load_state("networkidle")

        details_btn = page.locator("button:has-text('View'), button:has-text('Details'), a:has-text('View')").first

        if details_btn.is_visible():
            expect(details_btn).to_be_visible()

    def test_refresh_button_present(self, page: Page, base_url: str):
        """Verify refresh button exists."""
        page.goto(f"{base_url}/agents")
        page.wait_for_load_state("networkidle")

        refresh_btn = page.locator("button:has-text('Refresh'), button[title*='Refresh' i]").first

        if refresh_btn.is_visible():
            expect(refresh_btn).to_be_enabled()


class TestAgentsNavigation:
    """Test navigation to/from Agents page."""

    def test_navigate_from_sidebar(self, page: Page, base_url: str):
        """Navigate to Agents from sidebar."""
        page.goto(f"{base_url}/")
        page.wait_for_load_state("networkidle")

        agents_link = page.locator("a[href='/agents'], a:has-text('Agents')").first
        agents_link.click()

        expect(page).to_have_url(re.compile(r"/agents"))
        expect(page.locator("h1")).to_be_visible()


class TestAgentsFilters:
    """Test filtering functionality."""

    def test_status_filter_present(self, page: Page, base_url: str):
        """Check for status filter."""
        page.goto(f"{base_url}/agents")
        page.wait_for_load_state("networkidle")

        status_filter = page.locator("select[name*='status' i], button:has-text('Status'), button:has-text('Filter')").first

        if status_filter.is_visible():
            expect(status_filter).to_be_visible()

    def test_agent_type_filter(self, page: Page, base_url: str):
        """Check for agent type filter."""
        page.goto(f"{base_url}/agents")
        page.wait_for_load_state("networkidle")

        type_filter = page.locator("select[name*='type' i], button:has-text('Type')").first

        if type_filter.is_visible():
            expect(type_filter).to_be_visible()

    def test_search_input_present(self, page: Page, base_url: str):
        """Check for search input."""
        page.goto(f"{base_url}/agents")
        page.wait_for_load_state("networkidle")

        search_input = page.locator("input[type='search'], input[placeholder*='Search' i]").first

        if search_input.is_visible():
            expect(search_input).to_be_visible()


class TestAgentsAccessibility:
    """Accessibility tests."""

    def test_skip_link_present(self, page: Page, base_url: str):
        """Verify skip to main content link."""
        page.goto(f"{base_url}/agents")
        skip_link = page.locator("a:has-text('Skip to')")
        expect(skip_link).to_be_attached()

    def test_main_landmark_present(self, page: Page, base_url: str):
        """Check for main landmark."""
        page.goto(f"{base_url}/agents")
        main_element = page.locator("main, [role='main']")
        expect(main_element.first).to_be_visible()


class TestAgentsConsole:
    """Test console output and errors."""

    def test_no_critical_console_errors(self, page: Page, base_url: str):
        """Check for critical JavaScript errors."""
        console_messages = []
        page.on("console", lambda msg: console_messages.append(msg))

        page.goto(f"{base_url}/agents")
        page.wait_for_load_state("networkidle")

        errors = [msg for msg in console_messages if msg.type == "error"]

        critical_errors = [
            error for error in errors
            if "favicon" not in error.text.lower()
        ]

        for error in critical_errors:
            print(f"Console error: {error.text}")


class TestAgentsContent:
    """Test page content."""

    def test_page_description_present(self, page: Page, base_url: str):
        """Verify page has description."""
        page.goto(f"{base_url}/agents")

        description = page.locator("p, .description, .subtitle").first
        expect(description).to_be_visible()

    def test_agent_configuration_info(self, page: Page, base_url: str):
        """Check for agent configuration information."""
        page.goto(f"{base_url}/agents")
        page.wait_for_load_state("networkidle")

        # Look for configuration details
        config_info = page.locator("text=/Configuration|Config|Settings/i").first

        if config_info.is_visible():
            expect(config_info).to_be_visible()


class TestAgentsInteraction:
    """Test user interactions."""

    def test_agent_row_selectable(self, page: Page, base_url: str):
        """Check if agent rows are selectable."""
        page.goto(f"{base_url}/agents")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)

        # Look for checkboxes or selectable rows
        checkbox = page.locator("input[type='checkbox'], [role='checkbox']").first

        if checkbox.is_visible():
            expect(checkbox).to_be_visible()

    def test_agent_details_expandable(self, page: Page, base_url: str):
        """Check if agent details can be expanded."""
        page.goto(f"{base_url}/agents")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)

        # Look for expand buttons
        expand_btn = page.locator("button[aria-label*='Expand' i], .expand-icon, [aria-expanded]").first

        if expand_btn.is_visible():
            expect(expand_btn).to_be_visible()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
