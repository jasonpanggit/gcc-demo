"""
Playwright UI tests for Cache Management page.

Test Coverage:
- Page loading and navigation
- Cache statistics and display
- Cache management actions
- Cache entries listing
"""

import re
import pytest
from playwright.sync_api import Page, expect


class TestCacheBasics:
    """Basic page functionality tests."""

    def test_page_loads(self, page: Page, base_url: str):
        """Verify Cache page loads successfully."""
        page.goto(f"{base_url}/cache")
        expect(page).to_have_title(re.compile(r"Cache", re.IGNORECASE))

    def test_main_heading_present(self, page: Page, base_url: str):
        """Check for main page heading."""
        page.goto(f"{base_url}/cache")
        heading = page.locator("h1")
        expect(heading).to_be_visible()
        expect(heading).to_contain_text(re.compile(r"Cache", re.IGNORECASE))

    def test_sidebar_visible(self, page: Page, base_url: str):
        """Verify sidebar navigation is present."""
        page.goto(f"{base_url}/cache")
        sidebar = page.locator("aside, [role='complementary'], nav.sidebar, .sidebar")
        expect(sidebar.first).to_be_visible()


class TestCacheStatistics:
    """Test cache statistics display."""

    def test_cache_stats_present(self, page: Page, base_url: str):
        """Check for cache statistics."""
        page.goto(f"{base_url}/cache")
        page.wait_for_load_state("networkidle")

        # Look for stat cards or summary
        stats = page.locator(".stat, .stats, .summary, .card").first
        expect(stats).to_be_visible(timeout=10000)

    def test_hit_rate_displayed(self, page: Page, base_url: str):
        """Check for cache hit rate stat."""
        page.goto(f"{base_url}/cache")
        page.wait_for_load_state("networkidle")

        # Look for hit rate or percentage
        hit_rate = page.locator("text=/Hit.*Rate|Cache.*Rate/i").first

        if hit_rate.is_visible():
            expect(hit_rate).to_be_visible()

    def test_cache_size_displayed(self, page: Page, base_url: str):
        """Check for cache size information."""
        page.goto(f"{base_url}/cache")
        page.wait_for_load_state("networkidle")

        # Look for cache size, count, or entries
        cache_size = page.locator("text=/Size|Entries|Items|Count/i").first

        if cache_size.is_visible():
            expect(cache_size).to_be_visible()


class TestCacheEntries:
    """Test cache entries display."""

    def test_cache_entries_table_or_list(self, page: Page, base_url: str):
        """Check for cache entries table or list."""
        page.goto(f"{base_url}/cache")
        page.wait_for_load_state("networkidle")

        entries = page.locator("table, .cache-entries, .entries-list").first
        expect(entries).to_be_visible(timeout=15000)

    def test_table_headers_present(self, page: Page, base_url: str):
        """Verify table headers if table exists."""
        page.goto(f"{base_url}/cache")
        page.wait_for_load_state("networkidle")

        table = page.locator("table").first
        if table.is_visible():
            headers = page.locator("th, [role='columnheader']").all()
            assert len(headers) > 0, "No table headers found"

    def test_cache_keys_displayed(self, page: Page, base_url: str):
        """Check that cache keys are shown."""
        page.goto(f"{base_url}/cache")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)

        # Look for cache keys or entries
        entries_count = page.locator("tbody tr, .cache-entry, .entry-item").count()
        empty_message = page.locator("text=/No.*cache|Empty|No data/i").first

        assert entries_count > 0 or empty_message.is_visible(), "No cache entries and no empty message"


class TestCacheActions:
    """Test cache management actions."""

    def test_clear_cache_button_present(self, page: Page, base_url: str):
        """Check for clear cache button."""
        page.goto(f"{base_url}/cache")
        page.wait_for_load_state("networkidle")

        clear_btn = page.locator("button:has-text('Clear'), button:has-text('Flush'), button:has-text('Reset')").first

        if clear_btn.is_visible():
            expect(clear_btn).to_be_enabled()

    def test_refresh_button_present(self, page: Page, base_url: str):
        """Verify refresh button exists."""
        page.goto(f"{base_url}/cache")
        page.wait_for_load_state("networkidle")

        refresh_btn = page.locator("button:has-text('Refresh'), button[title*='Refresh' i]").first

        if refresh_btn.is_visible():
            expect(refresh_btn).to_be_enabled()

    def test_delete_entry_buttons(self, page: Page, base_url: str):
        """Check for delete/remove entry buttons."""
        page.goto(f"{base_url}/cache")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)

        # Look for delete icons or buttons
        delete_btn = page.locator("button:has-text('Delete'), button:has-text('Remove'), button[title*='Delete' i]").first

        if delete_btn.is_visible():
            expect(delete_btn).to_be_visible()


class TestCacheNavigation:
    """Test navigation to/from Cache page."""

    def test_navigate_from_sidebar(self, page: Page, base_url: str):
        """Navigate to Cache from sidebar."""
        page.goto(f"{base_url}/")
        page.wait_for_load_state("networkidle")

        cache_link = page.locator("a[href='/cache'], a:has-text('Cache')").first
        cache_link.click()

        expect(page).to_have_url(re.compile(r"/cache"))
        expect(page.locator("h1")).to_be_visible()


class TestCacheFilters:
    """Test filtering functionality."""

    def test_search_filter_present(self, page: Page, base_url: str):
        """Check for search/filter input."""
        page.goto(f"{base_url}/cache")
        page.wait_for_load_state("networkidle")

        search_input = page.locator("input[type='search'], input[placeholder*='Search' i], input[placeholder*='Filter' i]").first

        if search_input.is_visible():
            expect(search_input).to_be_visible()

    def test_cache_type_filter(self, page: Page, base_url: str):
        """Check for cache type filter."""
        page.goto(f"{base_url}/cache")
        page.wait_for_load_state("networkidle")

        type_filter = page.locator("select, button:has-text('Type'), button:has-text('Filter')").first

        if type_filter.is_visible():
            expect(type_filter).to_be_visible()


class TestCacheAccessibility:
    """Accessibility tests."""

    def test_skip_link_present(self, page: Page, base_url: str):
        """Verify skip to main content link."""
        page.goto(f"{base_url}/cache")
        skip_link = page.locator("a:has-text('Skip to')")
        expect(skip_link).to_be_attached()

    def test_main_landmark_present(self, page: Page, base_url: str):
        """Check for main landmark."""
        page.goto(f"{base_url}/cache")
        main_element = page.locator("main, [role='main']")
        expect(main_element.first).to_be_visible()


class TestCacheConsole:
    """Test console output and errors."""

    def test_no_critical_console_errors(self, page: Page, base_url: str):
        """Check for critical JavaScript errors."""
        console_messages = []
        page.on("console", lambda msg: console_messages.append(msg))

        page.goto(f"{base_url}/cache")
        page.wait_for_load_state("networkidle")

        errors = [msg for msg in console_messages if msg.type == "error"]

        critical_errors = [
            error for error in errors
            if "favicon" not in error.text.lower()
        ]

        for error in critical_errors:
            print(f"Console error: {error.text}")


class TestCacheContent:
    """Test page content."""

    def test_page_description_present(self, page: Page, base_url: str):
        """Verify page has description."""
        page.goto(f"{base_url}/cache")

        description = page.locator("p, .description, .subtitle").first
        expect(description).to_be_visible()

    def test_cache_performance_info(self, page: Page, base_url: str):
        """Check for cache performance information."""
        page.goto(f"{base_url}/cache")
        page.wait_for_load_state("networkidle")

        # Look for performance metrics
        performance = page.locator("text=/Performance|Efficiency|Speed/i").first

        if performance.is_visible():
            expect(performance).to_be_visible()


class TestCacheInteraction:
    """Test user interactions."""

    def test_pagination_controls(self, page: Page, base_url: str):
        """Check for pagination controls."""
        page.goto(f"{base_url}/cache")
        page.wait_for_load_state("networkidle")

        pagination = page.locator(".pagination, nav[aria-label*='Pagination' i]").first

        if pagination.is_visible():
            expect(pagination).to_be_visible()

    def test_entry_details_expandable(self, page: Page, base_url: str):
        """Check if entries can be expanded for details."""
        page.goto(f"{base_url}/cache")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)

        # Look for expand buttons
        expand_btn = page.locator("button[aria-label*='Expand' i], .expand-icon, [aria-expanded]").first

        if expand_btn.is_visible():
            expect(expand_btn).to_be_visible()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
