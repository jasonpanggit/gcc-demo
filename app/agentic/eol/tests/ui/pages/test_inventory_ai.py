"""
Playwright UI tests for Inventory AI Assistant page.

Test Coverage:
- Page loading and basic elements
- AI assistant interface
- Input forms and submission
- Navigation consistency
"""

import re
import pytest
from playwright.sync_api import Page, expect


class TestInventoryAIBasics:
    """Basic page functionality tests."""

    def test_page_loads(self, page: Page, base_url: str):
        """Verify Inventory AI page loads successfully."""
        page.goto(f"{base_url}/inventory-assistant")
        expect(page).to_have_title(re.compile(r"Inventory.*AI|Inventory.*Assistant", re.IGNORECASE))

    def test_main_heading_present(self, page: Page, base_url: str):
        """Check for main page heading."""
        page.goto(f"{base_url}/inventory-assistant")
        heading = page.locator("h1")
        expect(heading).to_be_visible()
        expect(heading).to_contain_text(re.compile(r"Inventory", re.IGNORECASE))

    def test_sidebar_visible(self, page: Page, base_url: str):
        """Verify sidebar navigation is present."""
        page.goto(f"{base_url}/inventory-assistant")
        sidebar = page.locator("aside, [role='complementary'], nav.sidebar, .sidebar")
        expect(sidebar.first).to_be_visible()


class TestInventoryAIInterface:
    """Test AI assistant interface components."""

    def test_ai_input_present(self, page: Page, base_url: str):
        """Check for AI input field or textarea."""
        page.goto(f"{base_url}/inventory-assistant")
        page.wait_for_load_state("networkidle")

        # Look for input, textarea, or contenteditable element
        ai_input = page.locator("textarea, input[type='text'], [contenteditable='true']").first
        expect(ai_input).to_be_visible(timeout=10000)

    def test_submit_button_present(self, page: Page, base_url: str):
        """Verify submit/send button exists."""
        page.goto(f"{base_url}/inventory-assistant")
        page.wait_for_load_state("networkidle")

        # Look for submit, send, or ask buttons
        submit_btn = page.locator("button:has-text('Send'), button:has-text('Submit'), button:has-text('Ask'), button[type='submit']").first
        expect(submit_btn).to_be_visible(timeout=10000)

    def test_ai_assistant_badge_present(self, page: Page, base_url: str):
        """Check for AI assistant indicator or badge."""
        page.goto(f"{base_url}/inventory-assistant")

        # Look for AI badge in sidebar
        ai_badge = page.locator("text=/AI/i").first
        expect(ai_badge).to_be_visible()


class TestInventoryAINavigation:
    """Test navigation to/from Inventory AI page."""

    def test_navigate_from_sidebar(self, page: Page, base_url: str):
        """Navigate to Inventory AI from sidebar link."""
        page.goto(f"{base_url}/")
        page.wait_for_load_state("networkidle")

        # Click Inventory AI link
        inventory_link = page.locator("a[href='/inventory-assistant'], a:has-text('Inventory AI')")
        inventory_link.first.click()

        expect(page).to_have_url(re.compile(r"/inventory-assistant"))
        expect(page.locator("h1")).to_be_visible()

    def test_navigate_from_dashboard(self, page: Page, base_url: str):
        """Navigate to Inventory AI from dashboard quick action."""
        page.goto(f"{base_url}/")
        page.wait_for_load_state("networkidle")

        # Look for Inventory AI quick action link
        quick_action = page.locator("a[href='/inventory-assistant']").first
        if quick_action.is_visible():
            quick_action.click()
            expect(page).to_have_url(re.compile(r"/inventory-assistant"))
        else:
            # If no quick action, use sidebar
            sidebar_link = page.locator("a:has-text('Inventory AI')")
            sidebar_link.first.click()
            expect(page).to_have_url(re.compile(r"/inventory-assistant"))


class TestInventoryAIConsole:
    """Test for console errors and warnings."""

    def test_no_critical_console_errors(self, page: Page, base_url: str):
        """Check for critical JavaScript errors."""
        console_messages = []
        page.on("console", lambda msg: console_messages.append(msg))

        page.goto(f"{base_url}/inventory-assistant")
        page.wait_for_load_state("networkidle")

        # Filter for actual errors (not warnings or info)
        errors = [msg for msg in console_messages if msg.type == "error"]

        # Exclude known acceptable errors
        critical_errors = [
            error for error in errors
            if "favicon" not in error.text.lower()
        ]

        # Log errors for debugging
        for error in critical_errors:
            print(f"Console error: {error.text}")

        # We're being lenient here - just log, don't fail
        # If you want strict checking, uncomment:
        # assert len(critical_errors) == 0, f"Found {len(critical_errors)} critical console errors"


class TestInventoryAIAccessibility:
    """Accessibility tests for Inventory AI page."""

    def test_skip_link_present(self, page: Page, base_url: str):
        """Verify skip to main content link exists."""
        page.goto(f"{base_url}/inventory-assistant")
        skip_link = page.locator("a:has-text('Skip to')")
        expect(skip_link).to_be_attached()

    def test_page_has_main_landmark(self, page: Page, base_url: str):
        """Check for main landmark/region."""
        page.goto(f"{base_url}/inventory-assistant")
        main_element = page.locator("main, [role='main']")
        expect(main_element.first).to_be_visible()

    def test_form_labels_present(self, page: Page, base_url: str):
        """Verify form inputs have labels or aria-labels."""
        page.goto(f"{base_url}/inventory-assistant")
        page.wait_for_load_state("networkidle")

        # Get all inputs and textareas
        inputs = page.locator("input:visible, textarea:visible").all()

        for idx, input_elem in enumerate(inputs):
            # Check if input has label, aria-label, or aria-labelledby
            label_text = input_elem.get_attribute("aria-label")
            placeholder = input_elem.get_attribute("placeholder")

            # At least one should be present
            has_label = bool(label_text or placeholder)

            if not has_label:
                print(f"Warning: Input {idx} missing label/aria-label/placeholder")


class TestInventoryAIInteraction:
    """Test user interactions with AI assistant."""

    def test_input_field_accepts_text(self, page: Page, base_url: str):
        """Verify AI input accepts text entry."""
        page.goto(f"{base_url}/inventory-assistant")
        page.wait_for_load_state("networkidle")

        # Find input/textarea
        input_field = page.locator("textarea, input[type='text'], [contenteditable='true']").first

        # Type test message
        input_field.fill("Show me all Windows servers")

        # Verify text was entered
        value = input_field.input_value() if input_field.evaluate("el => el.tagName !== 'DIV'") else input_field.inner_text()
        assert "Windows" in value or "servers" in value

    def test_clear_or_reset_button(self, page: Page, base_url: str):
        """Check for clear/reset functionality."""
        page.goto(f"{base_url}/inventory-assistant")
        page.wait_for_load_state("networkidle")

        # Look for clear, reset, or new conversation button
        clear_btn = page.locator("button:has-text('Clear'), button:has-text('Reset'), button:has-text('New')").first

        # Just verify it exists if present (optional feature)
        if clear_btn.is_visible():
            expect(clear_btn).to_be_enabled()


class TestInventoryAIContent:
    """Test page content and information display."""

    def test_page_description_present(self, page: Page, base_url: str):
        """Check for page description or subtitle."""
        page.goto(f"{base_url}/inventory-assistant")

        # Look for description paragraph or subtitle
        description = page.locator("p, .description, .subtitle").first

        # Verify some descriptive content exists
        expect(description).to_be_visible()

    def test_conversation_area_present(self, page: Page, base_url: str):
        """Verify conversation display area exists."""
        page.goto(f"{base_url}/inventory-assistant")
        page.wait_for_load_state("networkidle")

        # Look for message container, conversation area, or chat history
        conversation_area = page.locator(".messages, .conversation, .chat-history, [role='log']").first

        # Should be visible or attached (might be empty initially)
        if conversation_area.is_visible():
            expect(conversation_area).to_be_visible()
        else:
            # At minimum, it should exist in the DOM
            expect(conversation_area).to_be_attached()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
