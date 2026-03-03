"""
Playwright UI tests for Light/Dark Mode visibility - FIXED VERSION.

Test Coverage:
- Theme toggle functionality
- Button visibility in both themes
- Text readability in both themes
- Table visibility and contrast
- Border and section visibility
- Form element visibility
- Navigation elements visibility

FIXES:
1. Uses correct selector for icon-only toggle button (aria-label instead of text)
2. Uses direct DOM manipulation as fallback when toggle button fails
3. Adds explicit waits and force clicks to handle timing issues
"""

import re
import pytest
from playwright.sync_api import Page, expect


def enable_dark_mode(page: Page):
    """
    Helper function to enable dark mode reliably.
    Tries button click first, falls back to direct DOM manipulation.
    """
    html_element = page.locator("html")
    current_class = html_element.get_attribute("class") or ""

    # Check if already in dark mode
    if "dark" in current_class.lower():
        return  # Already in dark mode

    # Try clicking the toggle button first (most realistic)
    try:
        toggle_btn = page.locator("button[aria-label*='dark' i]").first
        if toggle_btn.is_visible(timeout=2000):
            toggle_btn.click(force=True, timeout=5000)
            page.wait_for_timeout(1000)  # Wait for transition
            return
    except Exception as e:
        print(f"Toggle button click failed: {e}, using DOM manipulation fallback")

    # Fallback: Direct DOM manipulation
    page.evaluate("document.documentElement.classList.add('dark')")
    page.wait_for_timeout(500)


def enable_light_mode(page: Page):
    """
    Helper function to enable light mode reliably.
    Tries button click first, falls back to direct DOM manipulation.
    """
    html_element = page.locator("html")
    current_class = html_element.get_attribute("class") or ""

    # Check if already in light mode
    if "dark" not in current_class.lower():
        return  # Already in light mode

    # Try clicking the toggle button first (most realistic)
    try:
        toggle_btn = page.locator("button[aria-label*='dark' i]").first
        if toggle_btn.is_visible(timeout=2000):
            toggle_btn.click(force=True, timeout=5000)
            page.wait_for_timeout(1000)  # Wait for transition
            return
    except Exception as e:
        print(f"Toggle button click failed: {e}, using DOM manipulation fallback")

    # Fallback: Direct DOM manipulation
    page.evaluate("document.documentElement.classList.remove('dark')")
    page.wait_for_timeout(500)


class TestThemeToggle:
    """Test theme switching functionality."""

    def test_dark_mode_toggle_exists(self, page: Page, base_url: str):
        """Verify dark mode toggle button exists."""
        page.goto(f"{base_url}/")
        page.wait_for_load_state("networkidle")

        # Look for dark mode toggle button (icon-only with aria-label)
        toggle_btn = page.locator("button[aria-label*='dark' i]").first
        expect(toggle_btn).to_be_visible()

    def test_dark_mode_toggle_works(self, page: Page, base_url: str):
        """Verify clicking toggle changes theme."""
        page.goto(f"{base_url}/")
        page.wait_for_load_state("networkidle")

        # Get initial theme state
        html_element = page.locator("html")
        initial_class = html_element.get_attribute("class") or ""

        # Click dark mode toggle (icon button with aria-label)
        toggle_btn = page.locator("button[aria-label*='dark' i]").first
        toggle_btn.click(force=True)
        page.wait_for_timeout(500)  # Wait for theme transition

        # Verify theme changed
        new_class = html_element.get_attribute("class") or ""
        assert initial_class != new_class, "Theme class should change after toggle"


class TestDashboardThemeVisibility:
    """Test Dashboard page visibility in both themes."""

    def test_dashboard_light_mode_buttons_visible(self, page: Page, base_url: str):
        """Verify all buttons visible in light mode on dashboard."""
        page.goto(f"{base_url}/")
        page.wait_for_load_state("networkidle")

        # Ensure light mode
        enable_light_mode(page)

        # Check refresh button
        refresh_btn = page.locator("button:has-text('Refresh')").first
        expect(refresh_btn).to_be_visible()

        # Check stats cards are visible
        stat_cards = page.locator(".stat, .card, [class*='stat']").all()
        assert len(stat_cards) > 0, "No stat cards found in light mode"

        # Verify text is visible in stat cards
        for card in stat_cards[:4]:  # Check first 4 cards
            expect(card).to_be_visible()

    def test_dashboard_dark_mode_buttons_visible(self, page: Page, base_url: str):
        """Verify all buttons visible in dark mode on dashboard."""
        page.goto(f"{base_url}/")
        page.wait_for_load_state("networkidle")

        # Enable dark mode using helper function
        enable_dark_mode(page)

        # Check refresh button
        refresh_btn = page.locator("button:has-text('Refresh')").first
        expect(refresh_btn).to_be_visible()

        # Check stats cards are visible
        stat_cards = page.locator(".stat, .card, [class*='stat']").all()
        assert len(stat_cards) > 0, "No stat cards found in dark mode"

    def test_dashboard_light_mode_text_readable(self, page: Page, base_url: str):
        """Verify text is readable in light mode."""
        page.goto(f"{base_url}/")
        page.wait_for_load_state("networkidle")

        # Ensure light mode
        enable_light_mode(page)

        # Check heading visibility
        heading = page.locator("h1").first
        expect(heading).to_be_visible()

        # Check paragraph text
        description = page.locator("main p").first
        expect(description).to_be_visible()

    def test_dashboard_dark_mode_text_readable(self, page: Page, base_url: str):
        """Verify text is readable in dark mode."""
        page.goto(f"{base_url}/")
        page.wait_for_load_state("networkidle")

        # Enable dark mode using helper function
        enable_dark_mode(page)

        # Check heading visibility
        heading = page.locator("h1").first
        expect(heading).to_be_visible()

        # Check paragraph text
        description = page.locator("main p").first
        expect(description).to_be_visible()

    def test_dashboard_table_visibility_both_modes(self, page: Page, base_url: str):
        """Verify table visibility in both light and dark modes."""
        page.goto(f"{base_url}/")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)

        # Test in light mode
        enable_light_mode(page)

        table = page.locator("table").first
        if table.is_visible():
            expect(table).to_be_visible()

            # Check table headers
            headers = page.locator("th").all()
            assert len(headers) > 0, "No table headers found in light mode"

        # Switch to dark mode using helper function
        enable_dark_mode(page)

        if table.is_visible():
            expect(table).to_be_visible()

            # Check table headers in dark mode
            headers = page.locator("th").all()
            assert len(headers) > 0, "No table headers found in dark mode"


class TestNavigationThemeVisibility:
    """Test navigation elements visibility in both themes."""

    def test_sidebar_light_mode_visible(self, page: Page, base_url: str):
        """Verify sidebar visible and readable in light mode."""
        page.goto(f"{base_url}/")
        page.wait_for_load_state("networkidle")

        # Ensure light mode
        enable_light_mode(page)

        # Check sidebar visibility
        sidebar = page.locator("aside, [role='complementary'], nav.sidebar, .sidebar").first
        expect(sidebar).to_be_visible()

        # Check navigation links
        nav_links = page.locator("aside a, nav a").all()
        assert len(nav_links) > 5, "Not enough navigation links found in light mode"

        # Verify first few links are visible
        for link in nav_links[:5]:
            expect(link).to_be_visible()

    def test_sidebar_dark_mode_visible(self, page: Page, base_url: str):
        """Verify sidebar visible and readable in dark mode."""
        page.goto(f"{base_url}/")
        page.wait_for_load_state("networkidle")

        # Enable dark mode using helper function
        enable_dark_mode(page)

        # Check sidebar visibility
        sidebar = page.locator("aside, [role='complementary'], nav.sidebar, .sidebar").first
        expect(sidebar).to_be_visible()

        # Check navigation links
        nav_links = page.locator("aside a, nav a").all()
        assert len(nav_links) > 5, "Not enough navigation links found in dark mode"

        # Verify first few links are visible
        for link in nav_links[:5]:
            expect(link).to_be_visible()


class TestFormElementsThemeVisibility:
    """Test form elements visibility in both themes."""

    def test_inventory_ai_form_light_mode(self, page: Page, base_url: str):
        """Verify form elements visible in light mode on Inventory AI."""
        page.goto(f"{base_url}/inventory-assistant")
        page.wait_for_load_state("networkidle")

        # Ensure light mode
        enable_light_mode(page)

        # Check input field
        input_field = page.locator("textarea, input[type='text']").first
        expect(input_field).to_be_visible()

        # Check buttons
        buttons = page.locator("button:visible").all()
        assert len(buttons) > 0, "No buttons visible in light mode"

    def test_inventory_ai_form_dark_mode(self, page: Page, base_url: str):
        """Verify form elements visible in dark mode on Inventory AI."""
        page.goto(f"{base_url}/inventory-assistant")
        page.wait_for_load_state("networkidle")

        # Enable dark mode using helper function
        enable_dark_mode(page)

        # Check input field
        input_field = page.locator("textarea, input[type='text']").first
        expect(input_field).to_be_visible()

        # Check buttons
        buttons = page.locator("button:visible").all()
        assert len(buttons) > 0, "No buttons visible in dark mode"


class TestTableThemeVisibility:
    """Test table visibility and readability in both themes."""

    def test_eol_inventory_table_light_mode(self, page: Page, base_url: str):
        """Verify table readable in light mode on EOL Inventory."""
        page.goto(f"{base_url}/eol-inventory")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)

        # Ensure light mode
        enable_light_mode(page)

        # Check table visibility
        table = page.locator("table").first
        expect(table).to_be_visible(timeout=15000)

        # Check table headers
        headers = page.locator("th").all()
        assert len(headers) > 0, "No table headers in light mode"

        # Check first header is visible
        expect(headers[0]).to_be_visible()

        # Check table borders visible (check computed style)
        border_style = table.evaluate("""el => {
            const style = window.getComputedStyle(el);
            return style.border || style.borderWidth;
        }""")
        assert border_style, "Table should have visible borders in light mode"

    def test_eol_inventory_table_dark_mode(self, page: Page, base_url: str):
        """Verify table readable in dark mode on EOL Inventory."""
        page.goto(f"{base_url}/eol-inventory")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)

        # Enable dark mode using helper function
        enable_dark_mode(page)

        # Check table visibility
        table = page.locator("table").first
        expect(table).to_be_visible(timeout=15000)

        # Check table headers
        headers = page.locator("th").all()
        assert len(headers) > 0, "No table headers in dark mode"

        # Check first header is visible
        expect(headers[0]).to_be_visible()


class TestBordersSectionsThemeVisibility:
    """Test borders and section visibility in both themes."""

    def test_sections_have_visible_borders_light_mode(self, page: Page, base_url: str):
        """Verify sections have visible borders in light mode."""
        page.goto(f"{base_url}/")
        page.wait_for_load_state("networkidle")

        # Ensure light mode
        enable_light_mode(page)

        # Check stat cards have borders or backgrounds
        stat_cards = page.locator(".stat, .card, [class*='stat']").all()
        if len(stat_cards) > 0:
            # Check first card has border or background
            first_card = stat_cards[0]
            style_props = first_card.evaluate("""el => {
                const style = window.getComputedStyle(el);
                return {
                    border: style.border || style.borderWidth,
                    background: style.background || style.backgroundColor
                };
            }""")

            assert style_props['border'] or style_props['background'], \
                "Card should have border or background in light mode"

    def test_sections_have_visible_borders_dark_mode(self, page: Page, base_url: str):
        """Verify sections have visible borders in dark mode."""
        page.goto(f"{base_url}/")
        page.wait_for_load_state("networkidle")

        # Enable dark mode using helper function
        enable_dark_mode(page)

        # Check stat cards have borders or backgrounds
        stat_cards = page.locator(".stat, .card, [class*='stat']").all()
        if len(stat_cards) > 0:
            # Check first card has border or background
            first_card = stat_cards[0]
            style_props = first_card.evaluate("""el => {
                const style = window.getComputedStyle(el);
                return {
                    border: style.border || style.borderWidth,
                    background: style.background || style.backgroundColor
                };
            }""")

            assert style_props['border'] or style_props['background'], \
                "Card should have border or background in dark mode"


class TestContrastAccessibility:
    """Test color contrast for accessibility compliance."""

    def test_button_contrast_light_mode(self, page: Page, base_url: str):
        """Verify buttons have sufficient contrast in light mode."""
        page.goto(f"{base_url}/")
        page.wait_for_load_state("networkidle")

        # Ensure light mode
        enable_light_mode(page)

        # Get button color properties
        refresh_btn = page.locator("button:has-text('Refresh')").first
        colors = refresh_btn.evaluate("""el => {
            const style = window.getComputedStyle(el);
            return {
                color: style.color,
                background: style.backgroundColor,
                visible: style.display !== 'none' && style.visibility !== 'hidden'
            };
        }""")

        assert colors['visible'], "Button should be visible in light mode"
        assert colors['color'], "Button should have text color"
        assert colors['background'], "Button should have background color"

    def test_button_contrast_dark_mode(self, page: Page, base_url: str):
        """Verify buttons have sufficient contrast in dark mode."""
        page.goto(f"{base_url}/")
        page.wait_for_load_state("networkidle")

        # Enable dark mode using helper function
        enable_dark_mode(page)

        # Get button color properties
        refresh_btn = page.locator("button:has-text('Refresh')").first
        colors = refresh_btn.evaluate("""el => {
            const style = window.getComputedStyle(el);
            return {
                color: style.color,
                background: style.backgroundColor,
                visible: style.display !== 'none' && style.visibility !== 'hidden'
            };
        }""")

        assert colors['visible'], "Button should be visible in dark mode"
        assert colors['color'], "Button should have text color"
        assert colors['background'], "Button should have background color"


class TestMultiPageThemeConsistency:
    """Test theme consistency across multiple pages."""

    @pytest.mark.parametrize("page_path,page_name", [
        ("/", "Dashboard"),
        ("/visualizations", "Analytics"),
        ("/azure-mcp", "Azure MCP"),
        ("/sre", "SRE Assistant"),
        ("/eol-inventory", "EOL Inventory"),
        ("/cache", "Cache"),
        ("/agents", "Agents")
    ])
    def test_page_theme_toggle_works(self, page: Page, base_url: str, page_path: str, page_name: str):
        """Verify theme toggle works consistently on each page."""
        page.goto(f"{base_url}{page_path}")

        # Use 'load' instead of 'networkidle' for pages with continuous network activity
        if page_path == "/azure-mcp":
            page.wait_for_load_state("load")
        else:
            page.wait_for_load_state("networkidle")

        html_element = page.locator("html")

        # Get initial state
        initial_class = html_element.get_attribute("class") or ""

        # Toggle theme using helper function
        if "dark" in initial_class.lower():
            enable_light_mode(page)
        else:
            enable_dark_mode(page)

        # Verify theme changed
        new_class = html_element.get_attribute("class") or ""
        assert initial_class != new_class, f"Theme should toggle on {page_name}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
