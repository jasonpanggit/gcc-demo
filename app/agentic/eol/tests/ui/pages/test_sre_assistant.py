"""
UI tests for the SRE Assistant page.
"""
import pytest
from playwright.sync_api import Page, expect


class TestSREAssistant:
    """Test suite for SRE Assistant functionality."""

    @pytest.fixture(autouse=True)
    def navigate_to_sre(self, authenticated_page: Page):
        """Navigate to SRE Assistant page before each test."""
        # Wait for page to be ready
        authenticated_page.wait_for_load_state("networkidle")
        authenticated_page.wait_for_timeout(1000)

        # Click SRE Assistant link
        sre_link = authenticated_page.get_by_role("link", name="SRE Assistant", exact=False).first
        sre_link.wait_for(state="visible", timeout=10000)
        sre_link.click()
        authenticated_page.wait_for_load_state("networkidle")
        self.page = authenticated_page

    def test_sre_page_loads(self):
        """Test that SRE Assistant page loads successfully."""
        expect(self.page).to_have_title("SRE Assistant - Azure Agentic Platform")

        # Verify main heading
        heading = self.page.get_by_role("heading", name="SRE Assistant")
        expect(heading).to_be_visible()

    def test_sre_description(self):
        """Test page description is present."""
        description = self.page.get_by_text(
            "Intelligent Site Reliability Engineering for your Azure resources"
        )
        expect(description).to_be_visible()

    def test_sre_agent_status_section(self):
        """Test agent status section."""
        expect(self.page.get_by_role("heading", name="Agent Status")).to_be_visible()

        # Verify refresh button
        refresh_button = self.page.get_by_role("button", name="Refresh")
        expect(refresh_button).to_be_visible()

    def test_sre_agent_health_status(self):
        """Test agent health status display."""
        # Check for health status heading
        health_heading = self.page.get_by_role("heading", name="HEALTHY")
        expect(health_heading).to_be_visible()

        # Verify agent statistics
        expect(self.page.get_by_text("Total Agents:")).to_be_visible()
        expect(self.page.get_by_text("Healthy Agents:")).to_be_visible()
        expect(self.page.get_by_text("Total Tools:")).to_be_visible()

    def test_sre_quick_prompts_categories(self):
        """Test quick prompts categories are present."""
        expect(self.page.get_by_text("Try asking…")).to_be_visible()

        # Verify categories
        expect(self.page.get_by_text("Health & Availability")).to_be_visible()
        expect(self.page.get_by_text("Incident Triage")).to_be_visible()
        expect(self.page.get_by_text("Network Diagnostics")).to_be_visible()
        expect(self.page.get_by_text("Security & Compliance")).to_be_visible()
        expect(self.page.get_by_text("Inventory & Cost")).to_be_visible()

    def test_sre_health_availability_prompts(self):
        """Test Health & Availability quick prompts."""
        # Check for specific prompts
        expect(
            self.page.get_by_role("button", name="What is the health of my container apps?")
        ).to_be_visible()
        expect(
            self.page.get_by_role("button", name="Are there any unhealthy resources?")
        ).to_be_visible()
        expect(
            self.page.get_by_role("button", name="Recent alerts last 24h")
        ).to_be_visible()

    def test_sre_incident_triage_prompts(self):
        """Test Incident Triage quick prompts."""
        expect(
            self.page.get_by_role("button", name="Why 503 errors on my container app?")
        ).to_be_visible()
        expect(
            self.page.get_by_role("button", name="Latency spike — what changed?")
        ).to_be_visible()

    def test_sre_network_diagnostics_prompts(self):
        """Test Network Diagnostics quick prompts."""
        expect(
            self.page.get_by_role("button", name="Test connectivity to database")
        ).to_be_visible()
        expect(
            self.page.get_by_role("button", name="DNS resolution check")
        ).to_be_visible()
        expect(
            self.page.get_by_role("button", name="Dependency map")
        ).to_be_visible()

    def test_sre_security_compliance_prompts(self):
        """Test Security & Compliance quick prompts."""
        expect(
            self.page.get_by_role("button", name="Defender secure score")
        ).to_be_visible()
        expect(
            self.page.get_by_role("button", name="High-severity recommendations")
        ).to_be_visible()
        expect(
            self.page.get_by_role("button", name="CIS compliance status")
        ).to_be_visible()

    def test_sre_conversation_section(self):
        """Test conversation section."""
        expect(self.page.get_by_role("heading", name="Conversation")).to_be_visible()

        # Verify clear chat button
        clear_button = self.page.get_by_role("button", name="Clear Chat")
        expect(clear_button).to_be_visible()

    def test_sre_input_field(self):
        """Test message input field."""
        input_field = self.page.get_by_placeholder(
            "Describe the issue or ask a question..."
        )
        expect(input_field).to_be_visible()
        expect(input_field).to_be_enabled()

    def test_sre_send_button(self):
        """Test send button."""
        send_button = self.page.get_by_role("button", name="Send")
        expect(send_button).to_be_visible()

    def test_sre_agent_communication_section(self):
        """Test agent communication section."""
        expect(
            self.page.get_by_role("heading", name="Agent Communication & Reasoning")
        ).to_be_visible()

        # Verify control buttons - use more specific selectors
        expect(self.page.locator("#toggle-comms-btn")).to_be_visible()
        expect(self.page.locator("#clear-comms-btn")).to_be_visible()
        expect(self.page.locator("#toggle-stats-btn")).to_be_visible()

    def test_sre_capabilities_section(self):
        """Test SRE Capabilities section."""
        expect(
            self.page.get_by_role("heading", name="SRE Capabilities")
        ).to_be_visible()

        expand_button = self.page.get_by_role("button", name="Expand")
        expect(expand_button).to_be_visible()

    def test_sre_quick_prompt_click(self):
        """Test clicking a quick prompt button."""
        # Click a quick prompt button
        prompt_button = self.page.get_by_role(
            "button", name="What is the health of my container apps?"
        )
        expect(prompt_button).to_be_enabled()

        # Note: We don't actually click as it would trigger an API call
        # This test just verifies the button is clickable

    def test_sre_message_input(self):
        """Test typing in message input field."""
        input_field = self.page.get_by_placeholder(
            "Describe the issue or ask a question..."
        )

        # Type a test message
        test_message = "Check system health"
        input_field.fill(test_message)

        # Verify value
        expect(input_field).to_have_value(test_message)
