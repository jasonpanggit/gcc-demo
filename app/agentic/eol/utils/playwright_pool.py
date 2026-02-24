"""
Playwright browser pool manager to reuse browser instances and limit concurrency.

This module provides a process-local pool backed by asyncio.Semaphore and
startup/shutdown helper functions for creating a shared playwright browser
instance and controlling max concurrent contexts.

Usage:
- Call setup_playwright_pool(app, max_concurrency) during FastAPI lifespan startup
- Use acquire_context() as an async context manager to get a browser context
- Call teardown_playwright_pool() during shutdown to close browser/playwright

Notes:
- This pool is process-local; for multiple instances use Redis-backed counters
  or a centralized service.
- Keep max_concurrency conservative (e.g., 2-4) to limit resource usage.
"""
import asyncio
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

try:
    from playwright.async_api import async_playwright, Browser, BrowserContext
    PLAYWRIGHT_AVAILABLE = True
except Exception as e:
    PLAYWRIGHT_AVAILABLE = False


class PlaywrightPool:
    def __init__(self):
        self._playwright = None
        self._browser: Optional[Browser] = None
        self._sem: Optional[asyncio.Semaphore] = None
        self._max_concurrency = 2
        self._initialized = False

    async def setup(self, max_concurrency: int = 2, browser_type: str = "chromium", headless: bool = True):
        if not PLAYWRIGHT_AVAILABLE:
            logger.warning("Playwright not available on this host; pool disabled")
            return

        if self._initialized:
            return

        self._max_concurrency = max_concurrency
        self._sem = asyncio.Semaphore(max_concurrency)
        self._playwright = await async_playwright().start()

        if browser_type == "firefox":
            self._browser = await self._playwright.firefox.launch(headless=headless)
        else:
            self._browser = await self._playwright.chromium.launch(headless=headless, args=[
                '--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage'
            ])

        self._initialized = True
        logger.info(f"🎭 Playwright pool initialized (type={browser_type}, concurrency={max_concurrency})")

    async def teardown(self):
        try:
            if self._browser:
                await self._browser.close()
            if self._playwright:
                await self._playwright.stop()
        except Exception as e:
            logger.debug(f"Error tearing down Playwright pool: {e}")
        finally:
            self._playwright = None
            self._browser = None
            self._sem = None
            self._initialized = False
            logger.info("🎭 Playwright pool torn down")

    async def acquire_context(self) -> BrowserContext:
        if not self._initialized or not self._browser or not self._sem:
            raise RuntimeError("Playwright pool not initialized")

        await self._sem.acquire()
        try:
            context = await self._browser.new_context()
            return context
        except Exception as e:
            # Release semaphore on failure to create context
            self._sem.release()
            raise

    async def release_context(self, context: BrowserContext):
        try:
            await context.close()
        finally:
            if self._sem:
                self._sem.release()


# Module-level singleton
playwright_pool = PlaywrightPool()
