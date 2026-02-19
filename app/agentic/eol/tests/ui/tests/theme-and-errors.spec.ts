import { test, expect, Page } from '@playwright/test';

/**
 * UI Test Suite - Light/Dark Mode & JavaScript Errors
 *
 * Tests:
 * 1. Light mode is default
 * 2. Dark mode toggle works
 * 3. No JavaScript console errors
 * 4. All pages render correctly in both modes
 */

const pages = [
  { name: 'Dashboard', url: '/' },
  { name: 'Azure MCP', url: '/azure-mcp' },
  { name: 'Azure AI SRE', url: '/azure-ai-sre' },
  { name: 'Inventory Assistant', url: '/inventory-assistant' },
  { name: 'EOL Search', url: '/eol-search' },
];

test.describe('Light/Dark Mode Tests', () => {

  test.beforeEach(async ({ page }) => {
    // Clear localStorage before each test
    await page.goto('/');
    await page.evaluate(() => localStorage.clear());
  });

  test('should default to light mode on first visit', async ({ page }) => {
    await page.goto('/');

    // Wait for page to load
    await page.waitForLoadState('networkidle');

    // Check HTML element has light-mode class or no dark-mode class
    const htmlElement = page.locator('html');
    const hasDarkMode = await htmlElement.evaluate(el => el.classList.contains('dark-mode'));
    const hasLightMode = await htmlElement.evaluate(el => el.classList.contains('light-mode'));

    expect(hasDarkMode).toBe(false);
    expect(hasLightMode || !hasDarkMode).toBe(true);

    // Check sidebar has light background
    const sidebar = page.locator('.sidebar');
    const bgColor = await sidebar.evaluate(el => window.getComputedStyle(el).backgroundColor);

    // Light mode should have white or very light background (rgb(255, 255, 255) or similar)
    expect(bgColor).toMatch(/rgb\(25[0-5], 25[0-5], 25[0-5]\)/);
  });

  test('should toggle to dark mode when clicking moon icon', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    // Find and click the theme toggle button
    const themeToggle = page.locator('#themeToggle');
    await expect(themeToggle).toBeVisible();

    // Icon should be moon (fa-moon) initially
    const initialIcon = themeToggle.locator('i');
    const initialIconClass = await initialIcon.getAttribute('class');
    expect(initialIconClass).toContain('fa-moon');

    // Click to toggle to dark mode
    await themeToggle.click();

    // Wait a bit for theme to apply
    await page.waitForTimeout(500);

    // Check HTML element now has dark-mode class
    const htmlElement = page.locator('html');
    const hasDarkMode = await htmlElement.evaluate(el => el.classList.contains('dark-mode'));
    expect(hasDarkMode).toBe(true);

    // Icon should now be sun (fa-sun)
    const newIconClass = await initialIcon.getAttribute('class');
    expect(newIconClass).toContain('fa-sun');

    // Check localStorage saved the preference
    const savedTheme = await page.evaluate(() => localStorage.getItem('theme'));
    expect(savedTheme).toBe('dark');
  });

  test('should persist dark mode preference across page reloads', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    // Toggle to dark mode
    await page.click('#themeToggle');
    await page.waitForTimeout(500);

    // Reload the page
    await page.reload();
    await page.waitForLoadState('networkidle');

    // Should still be in dark mode
    const htmlElement = page.locator('html');
    const hasDarkMode = await htmlElement.evaluate(el => el.classList.contains('dark-mode'));
    expect(hasDarkMode).toBe(true);
  });

  test('should toggle back to light mode', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    // Toggle to dark
    await page.click('#themeToggle');
    await page.waitForTimeout(500);

    // Toggle back to light
    await page.click('#themeToggle');
    await page.waitForTimeout(500);

    // Should be in light mode
    const htmlElement = page.locator('html');
    const hasDarkMode = await htmlElement.evaluate(el => el.classList.contains('dark-mode'));
    expect(hasDarkMode).toBe(false);

    // Icon should be moon again
    const icon = page.locator('#themeToggle i');
    const iconClass = await icon.getAttribute('class');
    expect(iconClass).toContain('fa-moon');
  });
});

test.describe('JavaScript Error Tests', () => {

  for (const pageInfo of pages) {
    test(`${pageInfo.name} should have no console errors in light mode`, async ({ page }) => {
      const consoleErrors: string[] = [];

      page.on('console', msg => {
        if (msg.type() === 'error') {
          consoleErrors.push(msg.text());
        }
      });

      page.on('pageerror', error => {
        consoleErrors.push(error.message);
      });

      await page.goto(pageInfo.url);
      await page.waitForLoadState('networkidle');

      // Wait a bit for any async JavaScript to execute
      await page.waitForTimeout(2000);

      // Filter out expected errors (if any)
      const unexpectedErrors = consoleErrors.filter(error => {
        // Filter out known/expected errors
        return !error.includes('Failed to fetch') && // API calls might fail in mock mode
               !error.includes('NetworkError') &&
               !error.includes('net::ERR_');
      });

      // Log errors for debugging
      if (unexpectedErrors.length > 0) {
        console.log(`Console errors on ${pageInfo.name}:`, unexpectedErrors);
      }

      expect(unexpectedErrors).toHaveLength(0);
    });

    test(`${pageInfo.name} should have no console errors in dark mode`, async ({ page }) => {
      const consoleErrors: string[] = [];

      page.on('console', msg => {
        if (msg.type() === 'error') {
          consoleErrors.push(msg.text());
        }
      });

      page.on('pageerror', error => {
        consoleErrors.push(error.message);
      });

      await page.goto(pageInfo.url);
      await page.waitForLoadState('networkidle');

      // Toggle to dark mode
      await page.click('#themeToggle');
      await page.waitForTimeout(1000);

      // Filter out expected errors
      const unexpectedErrors = consoleErrors.filter(error => {
        return !error.includes('Failed to fetch') &&
               !error.includes('NetworkError') &&
               !error.includes('net::ERR_');
      });

      if (unexpectedErrors.length > 0) {
        console.log(`Console errors on ${pageInfo.name} (dark mode):`, unexpectedErrors);
      }

      expect(unexpectedErrors).toHaveLength(0);
    });
  }
});

test.describe('Visual Rendering Tests', () => {

  test('Dashboard widgets should be visible in light mode', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    // Check stat widgets are visible
    await expect(page.locator('.stat-widget').first()).toBeVisible();

    // Check sidebar is visible
    await expect(page.locator('.sidebar')).toBeVisible();

    // Check topbar is visible
    await expect(page.locator('.topbar')).toBeVisible();
  });

  test('Dashboard widgets should be visible in dark mode', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    // Toggle to dark mode
    await page.click('#themeToggle');
    await page.waitForTimeout(500);

    // Check widgets are still visible
    await expect(page.locator('.stat-widget').first()).toBeVisible();
    await expect(page.locator('.sidebar')).toBeVisible();
    await expect(page.locator('.topbar')).toBeVisible();

    // Check dark mode styling is applied
    const htmlElement = page.locator('html');
    const hasDarkMode = await htmlElement.evaluate(el => el.classList.contains('dark-mode'));
    expect(hasDarkMode).toBe(true);
  });

  test('Chat interfaces should render correctly in both modes', async ({ page }) => {
    await page.goto('/azure-mcp');
    await page.waitForLoadState('networkidle');

    // Check chat container exists
    await expect(page.locator('.chat-container').first()).toBeVisible();

    // Toggle to dark mode
    await page.click('#themeToggle');
    await page.waitForTimeout(500);

    // Should still be visible
    await expect(page.locator('.chat-container').first()).toBeVisible();
  });

  test('Agent communication sections should be collapsible', async ({ page }) => {
    await page.goto('/azure-mcp');
    await page.waitForLoadState('networkidle');

    // Find agent comms section
    const agentCommsSection = page.locator('#agent-comms-section');

    // Should be hidden by default
    const isHidden = await agentCommsSection.evaluate(el => el.style.display === 'none');
    expect(isHidden).toBe(true);

    // Click show button
    const toggleBtn = page.locator('#toggle-comms-btn');
    await toggleBtn.click();
    await page.waitForTimeout(300);

    // Should now be visible
    const isVisible = await agentCommsSection.evaluate(el => el.style.display === 'block');
    expect(isVisible).toBe(true);

    // Button text should change
    const btnText = await toggleBtn.textContent();
    expect(btnText).toContain('Hide');
  });
});

test.describe('Sidebar Tests', () => {

  test('Sidebar should be collapsible', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    const sidebar = page.locator('.sidebar');
    const toggleBtn = page.locator('#sidebarToggle');

    // Should start expanded
    const hasCollapsed = await sidebar.evaluate(el => el.classList.contains('collapsed'));
    expect(hasCollapsed).toBe(false);

    // Click to collapse
    await toggleBtn.click();
    await page.waitForTimeout(500);

    // Should now be collapsed
    const isCollapsed = await sidebar.evaluate(el => el.classList.contains('collapsed'));
    expect(isCollapsed).toBe(true);

    // Check localStorage saved the state
    const savedState = await page.evaluate(() => localStorage.getItem('sidebarCollapsed'));
    expect(savedState).toBe('true');
  });

  test('Sidebar navigation links should work', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    // Click on Azure MCP link
    await page.click('a[href="/azure-mcp"]');
    await page.waitForLoadState('networkidle');

    // Should navigate to Azure MCP page
    expect(page.url()).toContain('/azure-mcp');

    // Active nav item should be highlighted
    const activeItem = page.locator('.nav-item.active');
    await expect(activeItem).toBeVisible();
  });
});
