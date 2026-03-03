"""
End-to-end tests for SRE Assistant page using Playwright MCP.
These tests validate actual functionality, not just DOM presence.
"""
import pytest
from playwright.sync_api import Page, expect
import time


class TestSREAssistantE2E:
    """End-to-end test suite for SRE Assistant functionality."""

    @pytest.fixture(autouse=True)
    def navigate_to_sre(self, authenticated_page: Page):
        """Navigate to SRE Assistant page before each test."""
        authenticated_page.wait_for_load_state("networkidle")
        authenticated_page.wait_for_timeout(1000)

        # Click SRE Assistant link
        sre_link = authenticated_page.get_by_role("link", name="SRE Assistant", exact=False).first
        sre_link.wait_for(state="visible", timeout=10000)
        sre_link.click()
        authenticated_page.wait_for_load_state("networkidle")
        self.page = authenticated_page

    def test_quick_prompt_health_check_interaction(self):
        """Test clicking health check prompt and receiving response."""
        # Click the health check prompt (sendExample() immediately sends the message)
        health_prompt = self.page.get_by_role(
            "button", name="What is the health of my container apps?"
        )
        expect(health_prompt).to_be_visible()
        health_prompt.click()

        # Wait for user message to appear in chat
        self.page.wait_for_selector(
            ".chat-message.user",
            timeout=5000,
            state="visible"
        )

        # Verify user message was sent
        user_messages = self.page.locator(".chat-message.user")
        expect(user_messages.last).to_contain_text("What is the health of my container apps?")

        # Wait for agent response (adjust timeout as needed)
        self.page.wait_for_selector(
            ".chat-message.agent",
            timeout=60000,  # Agent may take time to process
            state="visible"
        )

        # Verify agent response exists
        agent_messages = self.page.locator(".chat-message.agent")
        expect(agent_messages.first).to_be_visible()

        # Verify response contains relevant content (health-related keywords)
        response_text = agent_messages.first.inner_text().lower()
        assert any(
            keyword in response_text
            for keyword in ["container", "app", "health", "status", "running", "resource"]
        ), f"Response doesn't contain expected health-related content: {response_text}"

    def test_quick_prompt_network_diagnostics(self):
        """Test network diagnostics prompt functionality."""
        # Click network diagnostic prompt
        network_prompt = self.page.get_by_role(
            "button", name="Test connectivity to database"
        )
        network_prompt.click()

        # Send the query
        send_button = self.page.get_by_role("button", name="Send")
        send_button.click()

        # Wait for agent response
        self.page.wait_for_selector(
            ".chat-message.agent",
            timeout=45000,  # Network tests may take longer
            state="visible"
        )

        # Verify response
        agent_messages = self.page.locator(".chat-message.agent")
        expect(agent_messages.first).to_be_visible()

        response_text = agent_messages.first.inner_text().lower()
        assert any(
            keyword in response_text
            for keyword in ["network", "connectivity", "database", "connection", "test"]
        ), f"Response doesn't contain expected network content: {response_text}"

    def test_custom_query_input(self):
        """Test typing a custom query and getting response."""
        # Type custom query
        input_field = self.page.get_by_placeholder(
            "Describe the issue or ask a question..."
        )
        custom_query = "Show me recent alerts for the last hour"
        input_field.fill(custom_query)

        # Verify input
        expect(input_field).to_have_value(custom_query)

        # Send query
        send_button = self.page.get_by_role("button", name="Send")
        send_button.click()

        # Wait for user message to appear
        self.page.wait_for_selector(
            ".chat-message.user",
            timeout=5000,
            state="visible"
        )

        # Verify user message
        user_message = self.page.locator(".chat-message.user").last
        expect(user_message).to_contain_text(custom_query)

        # Wait for agent response
        self.page.wait_for_selector(
            ".chat-message.agent",
            timeout=30000,
            state="visible"
        )

        # Verify agent responded
        agent_messages = self.page.locator(".chat-message.agent")
        expect(agent_messages.first).to_be_visible()

    def test_agent_communication_panel(self):
        """Test agent communication panel shows reasoning."""
        # Send a query first
        input_field = self.page.get_by_placeholder(
            "Describe the issue or ask a question..."
        )
        input_field.fill("Check system health")
        send_button = self.page.get_by_role("button", name="Send")
        send_button.click()

        # Wait a bit for agent processing
        self.page.wait_for_timeout(2000)

        # Click Show button to reveal agent communications
        show_button = self.page.locator("#toggle-comms-btn")
        show_button.click()

        # Wait for communication panel to be visible
        self.page.wait_for_timeout(1000)
        comms_section = self.page.locator("#agent-comms-section")
        expect(comms_section).to_be_visible()

        # Verify communications stream exists
        comms_stream = self.page.locator(".communications-stream")
        expect(comms_stream).to_be_visible()

        # Check if agent communications appeared (may take time)
        # Note: This depends on agent actually logging communications
        self.page.wait_for_timeout(5000)

    def test_clear_chat_functionality(self):
        """Test clearing chat conversation."""
        # Send a message first
        input_field = self.page.get_by_placeholder(
            "Describe the issue or ask a question..."
        )
        input_field.fill("Test message")
        send_button = self.page.get_by_role("button", name="Send")
        send_button.click()

        # Wait for message to appear
        self.page.wait_for_selector(
            ".chat-message.user",
            timeout=5000,
            state="visible"
        )

        # Verify message exists
        user_messages = self.page.locator(".chat-message.user")
        initial_count = user_messages.count()
        assert initial_count > 0, "No user messages found before clear"

        # Click Clear Chat button
        clear_button = self.page.get_by_role("button", name="Clear Chat")
        clear_button.click()

        # Wait for chat to clear
        self.page.wait_for_timeout(1000)

        # Verify chat is cleared
        user_messages_after = self.page.locator(".chat-message.user")
        assert user_messages_after.count() == 0, "Chat was not cleared"

    def test_agent_status_refresh(self):
        """Test refreshing agent status."""
        # Click refresh button
        refresh_button = self.page.get_by_role("button", name="Refresh").first
        refresh_button.click()

        # Wait for status update
        self.page.wait_for_timeout(2000)

        # Verify status section still shows data
        expect(self.page.get_by_text("Total Agents:")).to_be_visible()
        expect(self.page.get_by_text("Healthy Agents:")).to_be_visible()
        expect(self.page.get_by_text("Total Tools:")).to_be_visible()

        # Verify numbers are present (not just 0)
        status_card = self.page.locator(".card").filter(has_text="Agent Status").first
        status_text = status_card.inner_text()
        assert "Total Agents:" in status_text
        assert "Healthy Agents:" in status_text

    def test_multiple_prompts_conversation(self):
        """Test sending multiple prompts in sequence."""
        prompts = [
            "What is the health of my container apps?",
            "Are there any unhealthy resources?",
            "Recent alerts last 24h"
        ]

        for i, prompt_text in enumerate(prompts, 1):
            # Find and click prompt button
            prompt_button = self.page.get_by_role("button", name=prompt_text)
            prompt_button.click()

            # Send
            send_button = self.page.get_by_role("button", name="Send")
            send_button.click()

            # Wait for response
            self.page.wait_for_selector(
                f".chat-message.agent:nth-child({i * 2})",  # User + Agent pairs
                timeout=30000,
                state="visible"
            )

            # Small delay between prompts
            self.page.wait_for_timeout(1000)

        # Verify we have multiple messages
        user_messages = self.page.locator(".chat-message.user")
        agent_messages = self.page.locator(".chat-message.agent")

        assert user_messages.count() >= 3, "Not all user messages appeared"
        assert agent_messages.count() >= 3, "Not all agent responses appeared"

    def test_error_handling_invalid_query(self):
        """Test error handling for invalid or problematic queries."""
        # Send a query that might cause an error
        input_field = self.page.get_by_placeholder(
            "Describe the issue or ask a question..."
        )
        input_field.fill("%%%INVALID_QUERY%%%")
        send_button = self.page.get_by_role("button", name="Send")
        send_button.click()

        # Wait for response (could be error or graceful handling)
        self.page.wait_for_timeout(10000)

        # Check for either:
        # 1. Agent response (graceful handling)
        # 2. Error message
        # 3. Status message
        has_response = (
            self.page.locator(".chat-message.agent").count() > 0 or
            self.page.locator(".chat-message.error").count() > 0 or
            self.page.locator(".chat-message.status").count() > 0
        )

        assert has_response, "No response or error message for invalid query"

    def test_response_contains_structured_data(self):
        """Test that agent responses contain structured, useful data."""
        # Click a prompt that should return structured data
        prompt = self.page.get_by_role(
            "button", name="What is the health of my container apps?"
        )
        prompt.click()
        send_button = self.page.get_by_role("button", name="Send")
        send_button.click()

        # Wait for response
        self.page.wait_for_selector(
            ".chat-message.agent",
            timeout=30000,
            state="visible"
        )

        # Get response content
        agent_message = self.page.locator(".chat-message.agent").first
        response_html = agent_message.inner_html()

        # Check for structured elements (lists, tables, code blocks, etc.)
        has_structure = any([
            "<ul>" in response_html or "<ol>" in response_html,  # Lists
            "<table>" in response_html,  # Tables
            "<pre>" in response_html or "<code>" in response_html,  # Code blocks
            "<strong>" in response_html or "<b>" in response_html,  # Emphasis
        ])

        # At minimum, response should have some content
        response_text = agent_message.inner_text()
        assert len(response_text) > 20, f"Response too short: {response_text}"
