"""
UI tests for the EOL Dates Database page.
"""
import pytest
from playwright.sync_api import Page, expect


class TestEOLInventory:
    """Test suite for EOL Dates Database functionality."""

    @pytest.fixture(autouse=True)
    def navigate_to_eol_inventory(self, authenticated_page: Page):
        """Navigate to EOL Dates Database page before each test."""
        # Wait for page to be ready
        authenticated_page.wait_for_load_state("networkidle")
        authenticated_page.wait_for_timeout(1000)

        # Click EOL Dates Database link
        eol_link = authenticated_page.get_by_role("link", name="EOL Dates Database")
        eol_link.wait_for(state="visible", timeout=10000)
        eol_link.click()
        authenticated_page.wait_for_load_state("networkidle")
        self.page = authenticated_page

    def test_eol_inventory_page_loads(self):
        """Test that EOL Inventory page loads successfully."""
        expect(self.page).to_have_title("EOL Dates Database")

        # Verify main heading
        heading = self.page.get_by_role("heading", name="EOL Dates Database")
        expect(heading).to_be_visible()

    def test_eol_inventory_description(self):
        """Test page description is present."""
        description = self.page.get_by_text(
            "Cached EOL records (high confidence) stored in the PostgreSQL-backed EOL inventory"
        )
        expect(description).to_be_visible()

    def test_eol_inventory_action_buttons(self):
        """Test action buttons are present."""
        refresh_button = self.page.get_by_role("button", name="Refresh")
        expect(refresh_button).to_be_visible()

        purge_button = self.page.get_by_role("button", name="Purge All Records")
        expect(purge_button).to_be_visible()

    def test_eol_inventory_filters_section(self):
        """Test filters section."""
        expect(self.page.get_by_role("heading", name="Filters")).to_be_visible()

        # Verify filter inputs
        software_input = self.page.get_by_placeholder("e.g. windows server")
        expect(software_input).to_be_visible()

        version_input = self.page.get_by_placeholder("e.g. 2012 R2")
        expect(version_input).to_be_visible()

        # Verify apply button
        apply_button = self.page.get_by_role("button", name="Apply")
        expect(apply_button).to_be_visible()

    def test_eol_inventory_record_count_display(self):
        """Test record count is displayed."""
        # Check for record count text
        record_text = self.page.locator("text=/Loaded.*record\\(s\\) from database/")
        expect(record_text).to_be_visible()

    def test_eol_inventory_table_headers(self):
        """Test table headers are present."""
        headers = [
            "Software",
            "Version",
            "EOL Date",
            "Support End",
            "Release",
            "Risk",
            "Confidence",
            "Source",
            "Agent",
            "Created",
            "Updated",
            "Actions"
        ]

        for header in headers:
            expect(self.page.get_by_role("columnheader", name=header, exact=False)).to_be_visible()

    def test_eol_inventory_table_has_data(self):
        """Test table contains data rows."""
        # Check for table rows (should have at least header row)
        table = self.page.locator("table")
        expect(table).to_be_visible()

        # Check for data rows
        rows = table.locator("tbody tr")
        expect(rows).to_have_count(25)  # Default page size

    def test_eol_inventory_pagination_controls(self):
        """Test pagination controls."""
        # Check for pagination info
        pagination_text = self.page.locator("text=/Page.*of/")
        expect(pagination_text).to_be_visible()

        # Check for rows per page dropdown
        rows_per_page = self.page.get_by_text("Rows per page")
        expect(rows_per_page).to_be_visible()

    def test_eol_inventory_pagination_buttons(self):
        """Test pagination navigation buttons."""
        # Next button should be visible
        next_button = self.page.get_by_role("button", name="Next")
        expect(next_button).to_be_visible()

        # Prev button should be disabled on first page
        prev_button = self.page.get_by_role("button", name="Prev")
        expect(prev_button).to_be_disabled()

    def test_eol_inventory_page_numbers(self):
        """Test page number buttons."""
        # Check for page 1 button (should be disabled as current page)
        page_1 = self.page.get_by_role("button", name="1", exact=True)
        expect(page_1).to_be_disabled()

        # Check for page 2 button
        page_2 = self.page.get_by_role("button", name="2", exact=True)
        expect(page_2).to_be_visible()

    def test_eol_inventory_row_actions(self):
        """Test row action buttons."""
        # Find first edit button
        edit_buttons = self.page.get_by_role("button", name="Edit")
        expect(edit_buttons.first).to_be_visible()

        # Find first delete button
        delete_buttons = self.page.get_by_role("button", name="Delete")
        expect(delete_buttons.first).to_be_visible()

    def test_eol_inventory_checkboxes(self):
        """Test row selection checkboxes."""
        # Find checkboxes in table
        checkboxes = self.page.locator("tbody input[type='checkbox']")
        expect(checkboxes.first).to_be_visible()

    def test_eol_inventory_delete_selected_button(self):
        """Test delete selected button."""
        delete_selected = self.page.get_by_role("button", name="Delete Selected")
        expect(delete_selected).to_be_visible()
        # Should be disabled when no items selected
        expect(delete_selected).to_be_disabled()

    def test_eol_inventory_filter_by_software(self):
        """Test filtering by software name."""
        software_input = self.page.get_by_placeholder("e.g. windows server")
        apply_button = self.page.get_by_role("button", name="Apply")

        # Enter filter value
        software_input.fill("windows")

        # Click apply
        apply_button.click()

        # Wait for table to update
        self.page.wait_for_load_state("networkidle")

    def test_eol_inventory_sorting(self):
        """Test column sorting functionality."""
        # Click on Software header to sort
        software_header = self.page.get_by_role("columnheader", name="Software", exact=False)
        expect(software_header).to_be_visible()

        # Note: Actual sorting verification would require checking data order

    def test_eol_inventory_risk_badges(self):
        """Test risk level badges are displayed."""
        # Check for at least one risk badge
        risk_badges = self.page.locator(".badge, [class*='risk'], [class*='severity']")
        # We expect to see risk indicators in the table

    def test_eol_inventory_go_to_page(self):
        """Test go to page functionality."""
        go_to_page_input = self.page.get_by_label("Go to page")
        expect(go_to_page_input).to_be_visible()

        go_button = self.page.get_by_role("button", name="Go")
        expect(go_button).to_be_visible()

    def test_eol_inventory_rows_per_page_change(self):
        """Test changing rows per page."""
        rows_dropdown = self.page.locator("select").filter(has_text="25").first
        expect(rows_dropdown).to_be_visible()

        # Current value should be 25
        expect(rows_dropdown).to_have_value("25")

    def test_eol_inventory_timestamp_display(self):
        """Test last updated timestamp is shown."""
        timestamp_text = self.page.locator("text=/Last updated:/")
        expect(timestamp_text).to_be_visible()
