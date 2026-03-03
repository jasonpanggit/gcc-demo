"""
UI tests for the Azure MCP Assistant page.
"""
import pytest
from playwright.sync_api import Page, expect


class TestAzureMCPAssistant:
    """Test suite for Azure MCP Assistant functionality."""

    @pytest.fixture(autouse=True)
    def navigate_to_azure_mcp(self, authenticated_page: Page):
        """Navigate to Azure MCP page before each test."""
        # Wait for page to be ready
        authenticated_page.wait_for_load_state("networkidle")
        authenticated_page.wait_for_timeout(1000)

        # Click Azure MCP link
        mcp_link = authenticated_page.get_by_role("link", name="Azure MCP", exact=False).first
        mcp_link.wait_for(state="visible", timeout=10000)
        mcp_link.click()
        authenticated_page.wait_for_load_state("networkidle")
        self.page = authenticated_page

    def test_azure_mcp_page_loads(self):
        """Test that Azure MCP page loads successfully."""
        expect(self.page).to_have_title("Azure MCP Server - Azure Agentic Platform")

        # Verify main heading
        heading = self.page.get_by_role("heading", name="Azure MCP Assistant")
        expect(heading).to_be_visible()

    def test_azure_mcp_description(self):
        """Test page description is present."""
        description = self.page.get_by_text(
            "Explore and manage Azure resources through the Azure Agentic Platform"
        )
        expect(description).to_be_visible()

    def test_azure_mcp_conversation_section(self):
        """Test conversation section is present."""
        expect(self.page.get_by_role("heading", name="Conversation")).to_be_visible()

        # Verify clear chat button
        clear_button = self.page.get_by_role("button", name="Clear Chat")
        expect(clear_button).to_be_visible()

    def test_azure_mcp_welcome_message(self):
        """Test welcome message is displayed."""
        welcome = self.page.get_by_text("Ask me anything about your Azure resources!")
        expect(welcome).to_be_visible()

    def test_azure_mcp_server_dropdown(self):
        """Test server selection dropdown."""
        server_dropdown = self.page.locator("select").first
        expect(server_dropdown).to_be_visible()

        # Verify dropdown has options
        expect(server_dropdown).to_have_count(1)

    def test_azure_mcp_quick_examples_section(self):
        """Test quick examples section is present."""
        quick_examples = self.page.get_by_text("Quick Examples:")
        expect(quick_examples).to_be_visible()

    def test_azure_mcp_input_field(self):
        """Test message input field is present."""
        input_field = self.page.get_by_placeholder(
            "Type your question about Azure resources..."
        )
        expect(input_field).to_be_visible()
        expect(input_field).to_be_enabled()

    def test_azure_mcp_send_button(self):
        """Test send button is present."""
        send_button = self.page.get_by_role("button", name="Send")
        expect(send_button).to_be_visible()

    def test_azure_mcp_agent_communication_section(self):
        """Test agent communication section."""
        expect(
            self.page.get_by_role("heading", name="Agent Communication & Reasoning")
        ).to_be_visible()

        # Verify control buttons
        expect(self.page.get_by_role("button", name="Show")).to_be_visible()
        expect(self.page.get_by_role("button", name="Clear")).to_be_visible()
        expect(self.page.get_by_role("button", name="Stats")).to_be_visible()

    def test_azure_mcp_servers_tools_section(self):
        """Test MCP Servers & Tools section."""
        expect(
            self.page.get_by_role("heading", name="MCP Servers & Tools")
        ).to_be_visible()

        expand_button = self.page.get_by_role("button", name="Expand").first
        expect(expand_button).to_be_visible()

    def test_azure_mcp_clear_chat_button(self):
        """Test clear chat button functionality."""
        clear_button = self.page.get_by_role("button", name="Clear Chat")
        expect(clear_button).to_be_enabled()

        # Click and verify no errors
        clear_button.click()
        self.page.wait_for_timeout(500)  # Wait for any animations

    def test_azure_mcp_message_input(self):
        """Test typing in message input field."""
        input_field = self.page.get_by_placeholder(
            "Type your question about Azure resources..."
        )

        # Type a test message
        test_message = "List my Azure resources"
        input_field.fill(test_message)

        # Verify value
        expect(input_field).to_have_value(test_message)

    def test_azure_mcp_expand_collapse_sections(self):
        """Test expand/collapse functionality."""
        expand_button = self.page.get_by_role("button", name="Expand").first
        expect(expand_button).to_be_visible()

        # Click expand
        expand_button.click()
        self.page.wait_for_timeout(300)
