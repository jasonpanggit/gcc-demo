"""
UI tests for System Health and API functionality.
"""
import pytest
from playwright.sync_api import Page, expect


class TestSystemHealth:
    """Test suite for System Health functionality."""

    def test_health_endpoint_json_response(self, page: Page, base_url: str):
        """Test health endpoint returns valid JSON."""
        page.goto(f"{base_url}/health")
        page.wait_for_load_state("networkidle")

        # The health endpoint returns JSON
        content = page.content()

        # Verify JSON structure elements
        assert "status" in content
        assert "timestamp" in content
        assert "version" in content

    def test_health_status_ok(self, page: Page, base_url: str):
        """Test health endpoint returns ok status."""
        page.goto(f"{base_url}/health")
        page.wait_for_load_state("networkidle")

        content = page.content()
        assert '"status":"ok"' in content or '"status": "ok"' in content


class TestResponsiveness:
    """Test suite for responsive design."""

    def test_mobile_viewport(self, context, base_url: str):
        """Test application on mobile viewport."""
        # Create mobile context
        mobile_page = context.new_page()
        mobile_page.set_viewport_size({"width": 375, "height": 667})

        mobile_page.goto(base_url)
        mobile_page.wait_for_load_state("networkidle")

        # Verify page loads
        expect(mobile_page).to_have_title("Dashboard — Azure Agentic Platform")

        # Sidebar should be collapsible on mobile
        toggle_button = mobile_page.get_by_role("button", name="Toggle sidebar")
        expect(toggle_button).to_be_visible()

        mobile_page.close()

    def test_tablet_viewport(self, context, base_url: str):
        """Test application on tablet viewport."""
        tablet_page = context.new_page()
        tablet_page.set_viewport_size({"width": 768, "height": 1024})

        tablet_page.goto(base_url)
        tablet_page.wait_for_load_state("networkidle")

        # Verify page loads
        expect(tablet_page).to_have_title("Dashboard — Azure Agentic Platform")

        tablet_page.close()

    def test_desktop_viewport(self, context, base_url: str):
        """Test application on desktop viewport."""
        desktop_page = context.new_page()
        desktop_page.set_viewport_size({"width": 1920, "height": 1080})

        desktop_page.goto(base_url)
        desktop_page.wait_for_load_state("networkidle")

        # Verify page loads
        expect(desktop_page).to_have_title("Dashboard — Azure Agentic Platform")

        # Sidebar should be visible on desktop
        sidebar = desktop_page.locator("aside, nav")
        expect(sidebar.first).to_be_visible()

        desktop_page.close()


class TestAccessibility:
    """Test suite for accessibility features."""

    def test_skip_to_main_content_link(self, authenticated_page: Page):
        """Test skip to main content link is present."""
        skip_link = authenticated_page.get_by_role("link", name="Skip to main content")
        expect(skip_link).to_be_visible()

    def test_proper_heading_hierarchy(self, authenticated_page: Page):
        """Test pages have proper heading hierarchy."""
        # Should have h1
        h1 = authenticated_page.get_by_role("heading", level=1)
        expect(h1).to_have_count(1)

    def test_form_labels(self, authenticated_page: Page):
        """Test form inputs have proper labels."""
        # Navigate to a page with forms
        authenticated_page.goto(authenticated_page.url + "/eol-inventory")
        authenticated_page.wait_for_load_state("networkidle")

        # Check inputs have placeholders or labels
        inputs = authenticated_page.locator("input[type='text']")
        count = inputs.count()

        # Each input should have accessible label or placeholder
        for i in range(count):
            input_elem = inputs.nth(i)
            # Check for aria-label, placeholder, or associated label
            has_label = (
                input_elem.get_attribute("placeholder") is not None
                or input_elem.get_attribute("aria-label") is not None
            )
            assert has_label, f"Input {i} missing accessible label"

    def test_buttons_have_accessible_names(self, authenticated_page: Page):
        """Test buttons have accessible names."""
        buttons = authenticated_page.get_by_role("button")
        count = buttons.count()

        # Each button should have text or aria-label
        for i in range(min(count, 10)):  # Check first 10 buttons
            button = buttons.nth(i)
            # Button should have inner text or aria-label
            text = button.inner_text()
            aria_label = button.get_attribute("aria-label")
            assert text or aria_label, f"Button {i} missing accessible name"


class TestPerformance:
    """Test suite for performance metrics."""

    def test_page_load_time(self, page: Page, base_url: str):
        """Test page loads within acceptable time."""
        import time

        start_time = time.time()
        page.goto(base_url)
        page.wait_for_load_state("networkidle")
        load_time = time.time() - start_time

        # Page should load within 10 seconds
        assert load_time < 10, f"Page took {load_time}s to load"

    def test_no_console_errors_on_load(self, page: Page, base_url: str):
        """Test that no critical console errors occur on load."""
        errors = []

        def handle_console_message(msg):
            if msg.type == "error":
                errors.append(msg.text)

        page.on("console", handle_console_message)

        page.goto(base_url)
        page.wait_for_load_state("networkidle")

        # Filter out known non-critical errors (like favicon)
        critical_errors = [
            e for e in errors if "favicon" not in e.lower() and "mutation" not in e.lower()
        ]

        assert len(critical_errors) == 0, f"Console errors found: {critical_errors}"
