"""
UI tests for the Analytics/Visualizations page.
"""
import pytest
from playwright.sync_api import Page, expect


class TestAnalytics:
    """Test suite for Analytics page functionality."""

    @pytest.fixture(autouse=True)
    def navigate_to_analytics(self, authenticated_page: Page):
        """Navigate to Analytics page before each test."""
        # Wait for page to be fully loaded
        authenticated_page.wait_for_load_state("networkidle")
        authenticated_page.wait_for_timeout(1000)  # Give time for any animations

        # Click Analytics link
        analytics_link = authenticated_page.get_by_role("link", name="Analytics", exact=True)
        analytics_link.wait_for(state="visible", timeout=10000)
        analytics_link.click()
        authenticated_page.wait_for_load_state("networkidle")
        self.page = authenticated_page

    def test_analytics_page_loads(self):
        """Test that Analytics page loads successfully."""
        expect(self.page).to_have_title("Data Visualizations Demo - Azure Agentic Platform")

        # Verify main heading
        heading = self.page.get_by_role("heading", name="Data Visualizations")
        expect(heading).to_be_visible()

    def test_analytics_description(self):
        """Test page description is present."""
        description = self.page.get_by_text(
            "Enhanced charts and graphs for the EOL Agentic Platform"
        )
        expect(description).to_be_visible()

    def test_analytics_sparklines_section(self):
        """Test Sparklines section."""
        expect(self.page.get_by_role("heading", name="Sparklines")).to_be_visible()

        # Verify sparkline types
        expect(self.page.get_by_text("Line Chart")).to_be_visible()
        expect(self.page.get_by_text("Area Chart")).to_be_visible()
        expect(self.page.get_by_text("Bar Chart")).to_be_visible()
        expect(self.page.get_by_text("Trend Indicator")).to_be_visible()

    def test_analytics_eol_heatmap_section(self):
        """Test EOL Risk Heatmap section."""
        expect(self.page.get_by_role("heading", name="EOL Risk Heatmap")).to_be_visible()

        # Verify legend
        expect(self.page.get_by_text("Critical (< 30 days)")).to_be_visible()
        expect(self.page.get_by_text("High (30-90 days)")).to_be_visible()
        expect(self.page.get_by_text("Medium (90-180 days)")).to_be_visible()
        expect(self.page.get_by_text("Low (180-365 days)")).to_be_visible()
        expect(self.page.get_by_text("Safe (> 365 days)")).to_be_visible()

    def test_analytics_eol_heatmap_data(self):
        """Test EOL heatmap displays sample data."""
        # Check for sample OS entries
        expect(self.page.get_by_text("Windows Server 2012 R2")).to_be_visible()
        expect(self.page.get_by_text("Ubuntu 18.04 LTS")).to_be_visible()
        expect(self.page.get_by_text("RHEL 7")).to_be_visible()

    def test_analytics_agent_metrics_section(self):
        """Test Agent Metrics Dashboard section."""
        expect(
            self.page.get_by_role("heading", name="Agent Metrics Dashboard")
        ).to_be_visible()

    def test_analytics_agent_metrics_cards(self):
        """Test agent metrics stat cards."""
        expect(self.page.get_by_text("Total Requests")).to_be_visible()
        expect(self.page.get_by_text("Success Rate")).to_be_visible()
        expect(self.page.get_by_text("Avg Response")).to_be_visible()
        expect(self.page.get_by_text("Active Agents")).to_be_visible()

    def test_analytics_agent_metrics_charts(self):
        """Test agent metrics charts are present."""
        expect(
            self.page.get_by_role("heading", name="Response Time Trends")
        ).to_be_visible()
        expect(
            self.page.get_by_role("heading", name="Success vs Failures")
        ).to_be_visible()
        expect(
            self.page.get_by_role("heading", name="Agent Activity Distribution")
        ).to_be_visible()
        expect(
            self.page.get_by_role("heading", name="Token Usage Over Time")
        ).to_be_visible()

    def test_analytics_token_usage_section(self):
        """Test Token Usage Analytics section."""
        expect(
            self.page.get_by_role("heading", name="Token Usage Analytics").first
        ).to_be_visible()

    def test_analytics_token_usage_time_filters(self):
        """Test token usage time period filters."""
        expect(self.page.get_by_role("button", name="1 Hour")).to_be_visible()
        expect(self.page.get_by_role("button", name="24 Hours")).to_be_visible()
        expect(self.page.get_by_role("button", name="7 Days")).to_be_visible()
        expect(self.page.get_by_role("button", name="30 Days")).to_be_visible()

    def test_analytics_token_usage_metrics(self):
        """Test token usage metric cards."""
        expect(self.page.get_by_text("Total Tokens")).to_be_visible()
        expect(self.page.get_by_text("Input Tokens")).to_be_visible()
        expect(self.page.get_by_text("Output Tokens")).to_be_visible()
        expect(self.page.get_by_text("Estimated Cost")).to_be_visible()

    def test_analytics_token_usage_charts(self):
        """Test token usage charts."""
        # Find all Token Usage Over Time headings
        token_usage_headings = self.page.get_by_role(
            "heading", name="Token Usage Over Time"
        )
        expect(token_usage_headings.first).to_be_visible()

        expect(
            self.page.get_by_role("heading", name="Token Distribution")
        ).to_be_visible()
        expect(
            self.page.get_by_role("heading", name="Token Usage by Agent")
        ).to_be_visible()

    def test_analytics_cost_breakdown_table(self):
        """Test cost breakdown table."""
        expect(
            self.page.get_by_role("heading", name="Detailed Cost Breakdown")
        ).to_be_visible()

        # Verify table headers
        expect(self.page.get_by_role("columnheader", name="Agent")).to_be_visible()
        expect(self.page.get_by_role("columnheader", name="Input Tokens")).to_be_visible()
        expect(self.page.get_by_role("columnheader", name="Output Tokens")).to_be_visible()
        expect(self.page.get_by_role("columnheader", name="Total Tokens")).to_be_visible()
        expect(self.page.get_by_role("columnheader", name="Estimated Cost")).to_be_visible()

    def test_analytics_cost_breakdown_data(self):
        """Test cost breakdown table contains data."""
        # Check for agent entries
        expect(self.page.get_by_text("MCP Orchestrator")).to_be_visible()
        expect(self.page.get_by_text("SRE Orchestrator")).to_be_visible()
        expect(self.page.get_by_text("EOL Analyzer")).to_be_visible()
        expect(self.page.get_by_text("Inventory Agent")).to_be_visible()

    def test_analytics_chartjs_section(self):
        """Test Chart.js Theme section."""
        expect(self.page.get_by_role("heading", name="Chart.js Theme")).to_be_visible()

        # Verify chart examples
        expect(self.page.get_by_role("heading", name="Line Chart Example")).to_be_visible()
        expect(self.page.get_by_role("heading", name="Bar Chart Example")).to_be_visible()
        expect(self.page.get_by_role("heading", name="Doughnut Chart Example")).to_be_visible()
        expect(
            self.page.get_by_role("heading", name="Stacked Area Chart Example")
        ).to_be_visible()

    def test_analytics_time_period_button_click(self):
        """Test clicking time period buttons."""
        one_hour_button = self.page.get_by_role("button", name="1 Hour")
        expect(one_hour_button).to_be_enabled()

        # Click and verify no errors
        one_hour_button.click()
        self.page.wait_for_timeout(300)

    def test_analytics_canvas_elements(self):
        """Test that canvas elements for charts exist."""
        # Charts are rendered on canvas elements
        canvases = self.page.locator("canvas")
        # We expect multiple canvas elements for the various charts
        expect(canvases.first).to_be_visible()
