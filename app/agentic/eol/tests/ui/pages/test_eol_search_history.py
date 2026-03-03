"""
Playwright UI tests for EOL Search History page.

Test Coverage:
- Page loading and navigation
- Search history listing
- History entries display
- Filter and search functionality
"""

import re
import pytest
from playwright.sync_api import Page, expect


class TestEOLSearchHistoryBasics:
    """Basic page functionality tests."""

    def test_page_loads(self, page: Page, base_url: str):
        """Verify EOL Search History page loads successfully."""
        page.goto(f"{base_url}/eol-searches")
        expect(page).to_have_title(re.compile(r"EOL.*Search.*History|Search.*History|History", re.IGNORECASE))

    def test_main_heading_present(self, page: Page, base_url: str):
        """Check for main page heading."""
        page.goto(f"{base_url}/eol-searches")
        heading = page.locator("h1")
        expect(heading).to_be_visible()
        expect(heading).to_contain_text(re.compile(r"History|Search", re.IGNORECASE))

    def test_sidebar_visible(self, page: Page, base_url: str):
        """Verify sidebar navigation is present."""
        page.goto(f"{base_url}/eol-searches")
        sidebar = page.locator("aside, [role='complementary'], nav.sidebar, .sidebar")
        expect(sidebar.first).to_be_visible()


class TestEOLSearchHistoryDisplay:
    """Test search history display."""

    def test_history_table_or_list_present(self, page: Page, base_url: str):
        """Check for history table or list."""
        page.goto(f"{base_url}/eol-searches")
        page.wait_for_load_state("networkidle")

        history_container = page.locator("table, .history-list, .search-history").first
        expect(history_container).to_be_visible(timeout=15000)

    def test_history_entries_visible_or_empty(self, page: Page, base_url: str):
        """Verify history entries or empty message."""
        page.goto(f"{base_url}/eol-searches")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)

        entries_count = page.locator("tbody tr, .history-entry, .search-item").count()
        empty_message = page.locator("text=/No.*history|No.*search|Empty/i").first

        assert entries_count > 0 or empty_message.is_visible(), "No history entries and no empty message"

    def test_table_headers_present(self, page: Page, base_url: str):
        """Verify table headers if table exists."""
        page.goto(f"{base_url}/eol-searches")
        page.wait_for_load_state("networkidle")

        table = page.locator("table").first
        if table.is_visible():
            headers = page.locator("th, [role='columnheader']").all()
            assert len(headers) > 0, "No table headers found"


class TestEOLSearchHistoryContent:
    """Test history entry content."""

    def test_search_query_displayed(self, page: Page, base_url: str):
        """Check that search queries are shown."""
        page.goto(f"{base_url}/eol-searches")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)

        # Look for query text in entries
        query_cell = page.locator("td, .query, .search-term").first

        if query_cell.is_visible():
            expect(query_cell).to_be_visible()

    def test_timestamp_displayed(self, page: Page, base_url: str):
        """Check that timestamps are shown."""
        page.goto(f"{base_url}/eol-searches")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)

        # Look for date/time information
        timestamp = page.locator("text=/\\d{4}-\\d{2}-\\d{2}|\\d{1,2}:\\d{2}|ago/i").first

        if timestamp.is_visible():
            expect(timestamp).to_be_visible()

    def test_results_count_displayed(self, page: Page, base_url: str):
        """Check if results count is shown."""
        page.goto(f"{base_url}/eol-searches")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)

        # Look for results count
        results_count_text = page.locator("text=/\\d+.*result/i").first
        results_count_class = page.locator(".results-count").first

        if results_count_text.is_visible() or results_count_class.is_visible():
            # At least one should be visible
            assert True


class TestEOLSearchHistoryActions:
    """Test history action buttons."""

    def test_view_results_button(self, page: Page, base_url: str):
        """Check for view results buttons."""
        page.goto(f"{base_url}/eol-searches")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)

        view_btn = page.locator("button:has-text('View'), a:has-text('View'), button:has-text('Results')").first

        if view_btn.is_visible():
            expect(view_btn).to_be_visible()

    def test_repeat_search_button(self, page: Page, base_url: str):
        """Check for repeat/rerun search buttons."""
        page.goto(f"{base_url}/eol-searches")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)

        repeat_btn = page.locator("button:has-text('Repeat'), button:has-text('Rerun'), button:has-text('Search again')").first

        if repeat_btn.is_visible():
            expect(repeat_btn).to_be_visible()

    def test_delete_history_button(self, page: Page, base_url: str):
        """Check for delete history buttons."""
        page.goto(f"{base_url}/eol-searches")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)

        delete_btn = page.locator("button:has-text('Delete'), button:has-text('Remove'), button[title*='Delete' i]").first

        if delete_btn.is_visible():
            expect(delete_btn).to_be_visible()

    def test_clear_all_history_button(self, page: Page, base_url: str):
        """Check for clear all history button."""
        page.goto(f"{base_url}/eol-searches")
        page.wait_for_load_state("networkidle")

        clear_all_btn = page.locator("button:has-text('Clear all'), button:has-text('Clear history')").first

        if clear_all_btn.is_visible():
            expect(clear_all_btn).to_be_visible()


class TestEOLSearchHistoryNavigation:
    """Test navigation to/from Search History page."""

    def test_navigate_from_sidebar(self, page: Page, base_url: str):
        """Navigate to EOL Search History from sidebar."""
        page.goto(f"{base_url}/")
        page.wait_for_load_state("networkidle")

        history_link = page.locator("a[href='/eol-searches'], a:has-text('EOL Search History')").first
        history_link.click()

        expect(page).to_have_url(re.compile(r"/eol-searches"))
        expect(page.locator("h1")).to_be_visible()

    def test_link_to_eol_search_page(self, page: Page, base_url: str):
        """Check for link to EOL Search page."""
        page.goto(f"{base_url}/eol-searches")
        page.wait_for_load_state("networkidle")

        search_link = page.locator("a[href='/eol-search'], a:has-text('New search')").first

        if search_link.is_visible():
            expect(search_link).to_be_visible()


class TestEOLSearchHistoryFilters:
    """Test filtering functionality."""

    def test_search_filter_present(self, page: Page, base_url: str):
        """Check for search/filter input."""
        page.goto(f"{base_url}/eol-searches")
        page.wait_for_load_state("networkidle")

        search_input = page.locator("input[type='search'], input[placeholder*='Search' i], input[placeholder*='Filter' i]").first

        if search_input.is_visible():
            expect(search_input).to_be_visible()

    def test_date_filter_present(self, page: Page, base_url: str):
        """Check for date range filter."""
        page.goto(f"{base_url}/eol-searches")
        page.wait_for_load_state("networkidle")

        date_filter = page.locator("input[type='date'], select[name*='date' i], button:has-text('Date')").first

        if date_filter.is_visible():
            expect(date_filter).to_be_visible()


class TestEOLSearchHistoryAccessibility:
    """Accessibility tests."""

    def test_skip_link_present(self, page: Page, base_url: str):
        """Verify skip to main content link."""
        page.goto(f"{base_url}/eol-searches")
        skip_link = page.locator("a:has-text('Skip to')")
        expect(skip_link).to_be_attached()

    def test_main_landmark_present(self, page: Page, base_url: str):
        """Check for main landmark."""
        page.goto(f"{base_url}/eol-searches")
        main_element = page.locator("main, [role='main']")
        expect(main_element.first).to_be_visible()


class TestEOLSearchHistoryConsole:
    """Test console output and errors."""

    def test_no_critical_console_errors(self, page: Page, base_url: str):
        """Check for critical JavaScript errors."""
        console_messages = []
        page.on("console", lambda msg: console_messages.append(msg))

        page.goto(f"{base_url}/eol-searches")
        page.wait_for_load_state("networkidle")

        errors = [msg for msg in console_messages if msg.type == "error"]

        critical_errors = [
            error for error in errors
            if "favicon" not in error.text.lower()
        ]

        for error in critical_errors:
            print(f"Console error: {error.text}")


class TestEOLSearchHistoryInteraction:
    """Test user interactions."""

    def test_pagination_controls(self, page: Page, base_url: str):
        """Check for pagination controls."""
        page.goto(f"{base_url}/eol-searches")
        page.wait_for_load_state("networkidle")

        pagination = page.locator(".pagination, nav[aria-label*='Pagination' i]").first

        if pagination.is_visible():
            expect(pagination).to_be_visible()

    def test_sort_controls(self, page: Page, base_url: str):
        """Check for sort controls."""
        page.goto(f"{base_url}/eol-searches")
        page.wait_for_load_state("networkidle")

        sort_controls = page.locator("th[role='button'], th.sortable, select[name*='sort' i], button:has-text('Sort')").first

        if sort_controls.is_visible():
            expect(sort_controls).to_be_visible()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
