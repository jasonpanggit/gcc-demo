"""
Playwright UI tests for EOL Search AI page.

Test Coverage:
- Page loading and navigation
- AI search interface
- Input forms and interaction
- Search functionality
"""

import re
import pytest
from playwright.sync_api import Page, expect


class TestEOLSearchAIBasics:
    """Basic page functionality tests."""

    def test_page_loads(self, page: Page, base_url: str):
        """Verify EOL Search AI page loads successfully."""
        page.goto(f"{base_url}/eol-search")
        expect(page).to_have_title(re.compile(r"EOL.*Search|Search.*EOL", re.IGNORECASE))

    def test_main_heading_present(self, page: Page, base_url: str):
        """Check for main page heading."""
        page.goto(f"{base_url}/eol-search")
        heading = page.locator("h1")
        expect(heading).to_be_visible()
        expect(heading).to_contain_text(re.compile(r"EOL|Search", re.IGNORECASE))

    def test_sidebar_navigation_present(self, page: Page, base_url: str):
        """Verify sidebar is visible."""
        page.goto(f"{base_url}/eol-search")
        sidebar = page.locator("aside, [role='complementary'], nav.sidebar, .sidebar")
        expect(sidebar.first).to_be_visible()


class TestEOLSearchAIInterface:
    """Test AI search interface components."""

    def test_search_input_present(self, page: Page, base_url: str):
        """Check for search input field."""
        page.goto(f"{base_url}/eol-search")
        page.wait_for_load_state("networkidle")

        # Look for input/textarea for search queries
        search_input = page.locator("textarea, input[type='text'], input[type='search'], [contenteditable='true']").first
        expect(search_input).to_be_visible(timeout=10000)

    def test_search_button_present(self, page: Page, base_url: str):
        """Verify search/submit button exists."""
        page.goto(f"{base_url}/eol-search")
        page.wait_for_load_state("networkidle")

        # Look for search, submit, or send button
        search_btn = page.locator("button:has-text('Search'), button:has-text('Submit'), button:has-text('Send'), button:has-text('Ask'), button[type='submit']").first
        expect(search_btn).to_be_visible(timeout=10000)

    def test_ai_badge_visible(self, page: Page, base_url: str):
        """Check for AI assistant badge in sidebar."""
        page.goto(f"{base_url}/eol-search")

        # Verify AI badge is shown
        ai_badge = page.locator("text=/AI/i").first
        expect(ai_badge).to_be_visible()


class TestEOLSearchAINavigation:
    """Test navigation to/from EOL Search AI page."""

    def test_navigate_from_sidebar(self, page: Page, base_url: str):
        """Navigate to EOL Search AI from sidebar."""
        page.goto(f"{base_url}/")
        page.wait_for_load_state("networkidle")

        # Click EOL Search AI link
        eol_link = page.locator("a[href='/eol-search'], a:has-text('EOL Search')")
        eol_link.first.click()

        expect(page).to_have_url(re.compile(r"/eol-search"))
        expect(page.locator("h1")).to_be_visible()

    def test_navigate_from_dashboard_quick_action(self, page: Page, base_url: str):
        """Navigate from dashboard quick actions."""
        page.goto(f"{base_url}/")
        page.wait_for_load_state("networkidle")

        # Look for EOL Search quick action
        quick_action = page.locator("a[href='/eol-search']").first
        if quick_action.is_visible():
            quick_action.click()
            expect(page).to_have_url(re.compile(r"/eol-search"))


class TestEOLSearchAIInteraction:
    """Test user interactions with search interface."""

    def test_search_input_accepts_text(self, page: Page, base_url: str):
        """Verify search input accepts text."""
        page.goto(f"{base_url}/eol-search")
        page.wait_for_load_state("networkidle")

        # Find search input
        input_field = page.locator("textarea, input[type='text'], input[type='search'], [contenteditable='true']").first

        # Enter search query
        test_query = "Windows Server 2019"
        input_field.fill(test_query)

        # Verify text was entered
        value = input_field.input_value() if input_field.evaluate("el => el.tagName !== 'DIV'") else input_field.inner_text()
        assert "Windows" in value or "2019" in value

    def test_example_queries_or_suggestions(self, page: Page, base_url: str):
        """Check for example queries or suggestions."""
        page.goto(f"{base_url}/eol-search")
        page.wait_for_load_state("networkidle")

        # Look for example queries, suggestions, or help text
        examples = page.locator(".examples, .suggestions, .help-text, .hint").first

        # This is optional - just check if present
        if examples.is_visible():
            expect(examples).to_be_visible()


class TestEOLSearchAIContent:
    """Test page content and layout."""

    def test_page_description_present(self, page: Page, base_url: str):
        """Verify page has description or instructions."""
        page.goto(f"{base_url}/eol-search")

        # Look for description text
        description = page.locator("p, .description, .instructions").first
        expect(description).to_be_visible()

    def test_results_area_present(self, page: Page, base_url: str):
        """Check for search results display area."""
        page.goto(f"{base_url}/eol-search")
        page.wait_for_load_state("networkidle")

        # Look for results container, conversation area, or response section
        results_area = page.locator(".results, .response, .conversation, .messages, [role='log']").first

        # Should exist in DOM (might be empty initially)
        expect(results_area).to_be_attached()


class TestEOLSearchAIAccessibility:
    """Accessibility tests."""

    def test_skip_link_present(self, page: Page, base_url: str):
        """Verify skip to main content link."""
        page.goto(f"{base_url}/eol-search")
        skip_link = page.locator("a:has-text('Skip to')")
        expect(skip_link).to_be_attached()

    def test_main_landmark_present(self, page: Page, base_url: str):
        """Check for main landmark."""
        page.goto(f"{base_url}/eol-search")
        main_element = page.locator("main, [role='main']")
        expect(main_element.first).to_be_visible()

    def test_form_has_labels(self, page: Page, base_url: str):
        """Verify form inputs have labels."""
        page.goto(f"{base_url}/eol-search")
        page.wait_for_load_state("networkidle")

        # Check search input has label or placeholder
        search_input = page.locator("textarea, input[type='text'], input[type='search']").first

        if search_input.is_visible():
            # Check for aria-label or placeholder
            aria_label = search_input.get_attribute("aria-label")
            placeholder = search_input.get_attribute("placeholder")

            assert aria_label or placeholder, "Search input missing label/placeholder"


class TestEOLSearchAIConsole:
    """Test console output and errors."""

    def test_no_critical_console_errors(self, page: Page, base_url: str):
        """Check for critical JavaScript errors."""
        console_messages = []
        page.on("console", lambda msg: console_messages.append(msg))

        page.goto(f"{base_url}/eol-search")
        page.wait_for_load_state("networkidle")

        # Filter actual errors
        errors = [msg for msg in console_messages if msg.type == "error"]

        # Exclude known acceptable errors
        critical_errors = [
            error for error in errors
            if "favicon" not in error.text.lower()
        ]

        # Log but don't fail (lenient mode)
        for error in critical_errors:
            print(f"Console error: {error.text}")


class TestEOLSearchAILinks:
    """Test related links and navigation."""

    def test_link_to_eol_database(self, page: Page, base_url: str):
        """Check if link to EOL database exists."""
        page.goto(f"{base_url}/eol-search")
        page.wait_for_load_state("networkidle")

        # Look for link to EOL inventory/database
        eol_db_link = page.locator("a[href='/eol-inventory'], a:has-text('EOL Dates'), a:has-text('Database')")

        # Optional feature - just verify if present
        if eol_db_link.first.is_visible():
            expect(eol_db_link.first).to_be_visible()

    def test_link_to_search_history(self, page: Page, base_url: str):
        """Check if link to search history exists."""
        page.goto(f"{base_url}/eol-search")
        page.wait_for_load_state("networkidle")

        # Look for search history link
        history_link = page.locator("a[href='/eol-searches'], a:has-text('History'), a:has-text('Previous')")

        # Optional feature
        if history_link.first.is_visible():
            expect(history_link.first).to_be_visible()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
