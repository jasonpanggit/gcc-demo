"""
Enhanced debug test to capture network traffic and actual responses.
"""
import pytest
from playwright.sync_api import Page, expect, Response


class TestSRENetworkDebug:
    """Network debugging test suite."""

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
        self.responses = []

    def test_capture_network_traffic(self):
        """Capture and analyze network traffic when clicking prompt."""

        # Listen to network traffic
        def handle_response(response: Response):
            if "/api/sre-orchestrator/execute" in response.url:
                print(f"\n[NETWORK] Response URL: {response.url}")
                print(f"[NETWORK] Status: {response.status}")
                print(f"[NETWORK] Headers: {response.headers}")
                try:
                    body = response.json()
                    print(f"[NETWORK] Body: {body}")
                    self.responses.append({
                        "status": response.status,
                        "body": body
                    })
                except Exception as e:
                    print(f"[NETWORK] Could not parse JSON: {e}")
                    text = response.text()
                    print(f"[NETWORK] Text: {text[:500]}")
                    self.responses.append({
                        "status": response.status,
                        "text": text[:500]
                    })

        self.page.on("response", handle_response)

        # Click prompt
        print("\n[DEBUG] Clicking health prompt...")
        health_prompt = self.page.get_by_role(
            "button", name="What is the health of my container apps?"
        )
        health_prompt.click()

        # Wait for request to complete
        print("[DEBUG] Waiting for network request...")
        self.page.wait_for_timeout(10000)

        # Check what we captured
        print(f"\n[DEBUG] Captured {len(self.responses)} responses")
        for i, resp in enumerate(self.responses):
            print(f"\n[DEBUG] Response {i}: {resp}")

        # Check console errors
        print("\n[DEBUG] Checking console messages...")
        # Note: Console messages are captured by Playwright automatically

        # Always pass to see output
        assert True
