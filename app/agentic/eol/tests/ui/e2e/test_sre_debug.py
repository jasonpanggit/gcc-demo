"""
Debug test to investigate SRE Assistant interaction issues.
"""
import pytest
from playwright.sync_api import Page, expect


class TestSREDebug:
    """Debug suite to understand what's happening."""

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

    def test_debug_prompt_click_and_wait(self):
        """Debug test to see what happens when clicking a prompt."""
        # Click prompt
        health_prompt = self.page.get_by_role(
            "button", name="What is the health of my container apps?"
        )
        print("\n[DEBUG] Clicking health prompt...")
        health_prompt.click()

        # Wait a bit
        self.page.wait_for_timeout(2000)

        # Check what's in the chat history
        chat_history = self.page.locator("#chat-history")
        print(f"[DEBUG] Chat history HTML:\n{chat_history.inner_html()[:500]}")

        # Look for any messages
        all_messages = self.page.locator(".chat-message")
        message_count = all_messages.count()
        print(f"[DEBUG] Total messages: {message_count}")

        for i in range(message_count):
            msg = all_messages.nth(i)
            classes = msg.get_attribute("class")
            text = msg.inner_text()[:100]
            print(f"[DEBUG] Message {i}: class={classes}, text={text}")

        # Check for errors in console
        self.page.wait_for_timeout(3000)

        # Take a screenshot for debugging
        self.page.screenshot(path="/tmp/sre_debug.png")
        print("[DEBUG] Screenshot saved to /tmp/sre_debug.png")

        # Wait longer to see if agent responds
        print("[DEBUG] Waiting 30s for agent response...")
        try:
            self.page.wait_for_selector(
                ".chat-message.agent",
                timeout=30000,
                state="visible"
            )
            print("[DEBUG] Agent responded!")
            agent_msg = self.page.locator(".chat-message.agent").first
            print(f"[DEBUG] Agent response: {agent_msg.inner_text()[:200]}")
        except Exception as e:
            print(f"[DEBUG] No agent response: {e}")

            # Check if there are error messages
            error_msgs = self.page.locator(".chat-message.error")
            if error_msgs.count() > 0:
                print(f"[DEBUG] Error message: {error_msgs.first.inner_text()}")

            # Check if input is disabled (might indicate processing)
            input_field = self.page.locator("#chat-input")
            is_disabled = input_field.is_disabled()
            print(f"[DEBUG] Input field disabled: {is_disabled}")

            # Check page HTML for any error indicators
            page_text = self.page.content()
            if "error" in page_text.lower() or "exception" in page_text.lower():
                print("[DEBUG] Found error/exception text in page")

        # Always pass so we can see the debug output
        assert True
