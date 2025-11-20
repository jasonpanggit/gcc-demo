"""
Playwright Agent for EOL Data Extraction from Bing Search
Uses Playwright directly for reliable browser automation and EOL date extraction.
"""

import asyncio
import logging
import time
import re
import os
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime

from .base_eol_agent import BaseEOLAgent

logger = logging.getLogger(__name__)

# Check for Playwright availability
PLAYWRIGHT_AVAILABLE = False
try:
    from playwright.async_api import async_playwright, Browser, Page
    PLAYWRIGHT_AVAILABLE = True
    logger.info("✅ Playwright dependencies loaded successfully")
except ImportError as import_error:
    logger.warning(f"⚠️ Playwright dependencies not available: {import_error}")
    logger.warning("⚠️ Playwright functionality will be disabled")


class PlaywrightEOLAgent(BaseEOLAgent):
    """Playwright-powered fallback for web EOL lookups."""

    def __init__(self):
        super().__init__("playwright_eol_agent")
        # Browser lifecycle: Browser stays open across searches, only pages are closed
        # This provides better performance for multiple consecutive searches
        self._playwright = None
        self._browser = None
        self._browser_context = None
        self._initialization_error = None
        self._health_checked = False
        self._use_firefox = True
        self._stealth_mode = True
        
        # Container-friendly browser arguments for Chromium
        self.browser_args = [
            '--no-sandbox',
            '--disable-setuid-sandbox',
            '--disable-dev-shm-usage',
        ]
        
        if self._stealth_mode:
            # Advanced stealth arguments to bypass Cloudflare detection
            self.browser_args.extend([
                '--disable-blink-features=AutomationControlled',
                '--exclude-switches=enable-automation',
                '--disable-infobars',
                '--window-size=1920,1080',
                '--start-maximized',
                '--disable-web-security',
                '--disable-features=IsolateOrigins,site-per-process',
                '--disable-site-isolation-trials',
                '--disable-features=BlockInsecurePrivateNetworkRequests',
            ])
        
        # Firefox arguments
        self.firefox_args = []
        if self._stealth_mode:
            self.firefox_args.extend(['-width=1920', '-height=1080'])
        
        # Firefox preferences for stealth
        self.firefox_prefs = {
            'dom.webdriver.enabled': False,
            'useAutomationExtension': False,
            'general.platform.override': 'MacIntel'
        } if self._stealth_mode else {}
        
        # Selectors to try (in order of reliability based on testing)
        self.selectors_to_try = [
            '.b_ans',
            '.answer_container',
            '[data-snippet]',
            '#b_context',
            'body',
        ]
        
        browser_type = 'Firefox' if self._use_firefox else 'Chromium'
        logger.info(f"🎭 Playwright agent initialized: {browser_type} | Stealth: {self._stealth_mode}")

    async def _ensure_browser(self) -> bool:
        """Ensure browser is launched and ready with advanced stealth"""
        if not PLAYWRIGHT_AVAILABLE:
            self._initialization_error = "playwright_unavailable"
            return False
        
        # Check if browser is still connected
        if self._browser:
            try:
                if self._browser.is_connected():
                    return True
                else:
                    logger.warning("⚠️ Browser disconnected, will relaunch")
                    self._browser = None
            except Exception as e:
                logger.warning(f"⚠️ Browser check failed: {e}, will relaunch")
                self._browser = None
        
        try:
            if not self._playwright:
                self._playwright = await async_playwright().start()
                logger.info("🎭 Playwright instance started")
            
            browser_engine = self._playwright.firefox if self._use_firefox else self._playwright.chromium
            
            if self._use_firefox:
                # Firefox launch (better headless support)
                self._browser = await browser_engine.launch(
                    headless=True,
                    args=self.firefox_args,
                    firefox_user_prefs=self.firefox_prefs
                )
                logger.info("✅ Firefox browser launched (headless with stealth)")
            else:
                # Chromium launch with new headless mode
                launch_args = self.browser_args.copy()
                launch_args.append('--headless=new')
                
                self._browser = await browser_engine.launch(
                    args=launch_args,
                    chromium_sandbox=False
                )
                logger.info("✅ Chromium browser launched (new headless mode)")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to launch browser: {e}")
            self._initialization_error = f"browser_launch_failed: {str(e)}"
            return False

    async def _close_browser(self):
        """Close browser and cleanup resources"""
        try:
            if self._browser:
                await self._browser.close()
                self._browser = None
                logger.debug("🔒 Browser closed")
            
            if self._playwright:
                await self._playwright.stop()
                self._playwright = None
                logger.debug("🔒 Playwright stopped")
                
        except Exception as e:
            logger.warning(f"⚠️ Error closing browser: {e}")

    def _extract_eol_dates_from_text(self, text: str, software_name: str) -> Dict[str, Any]:
        """
        Extract EOL dates using proven patterns from debug testing.
        Returns confidence-scored results.
        """
        result = {
            "eol_date": None,
            "confidence": "low",
            "all_dates": [],
            "context": None
        }
        
        # Enhanced patterns (in priority order)
        # Tuple format: (pattern, confidence_level)
        patterns = [
            # Very high confidence: dates near EOL keywords
            (r'(?:end of life|EOL|support ends?|standard support|extended support|legacy support)(?:\s+(?:is|on|until|date))?\s*(?:on\s+)?[:\s]*(\d{1,2}\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4})', 'very_high'),
            (r'(?:end of life|EOL|support ends?|standard support|extended support)(?:\s+(?:is|on|until|date))?\s*(?:on\s+)?[:\s]*((?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4})', 'very_high'),
            
            # High confidence: well-formed dates
            (r'\b(\d{1,2}\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4})\b', 'high'),
            (r'\b((?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4})\b', 'high'),
            
            # Medium confidence: numeric formats
            (r'\b(\d{1,2}/\d{1,2}/\d{4})\b', 'medium'),
            (r'\b(\d{4}-\d{2}-\d{2})\b', 'medium'),
        ]
        
        date_map = {}
        for pattern, conf in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for match in matches:
                date_str = match if isinstance(match, str) else (match[0] if match else None)
                if date_str and date_str not in date_map:
                    date_map[date_str] = conf
        
        # Sort by confidence
        conf_order = {'very_high': 4, 'high': 3, 'medium': 2, 'low': 1}
        sorted_dates = sorted(date_map.items(), key=lambda x: conf_order[x[1]], reverse=True)
        
        if sorted_dates:
            result["eol_date"] = sorted_dates[0][0]
            result["confidence"] = sorted_dates[0][1]
            result["all_dates"] = [d[0] for d in sorted_dates]
            
            # Extract context around the date for verification
            date_pos = text.lower().find(result["eol_date"].lower())
            if date_pos != -1:
                start = max(0, date_pos - 100)
                end = min(len(text), date_pos + 100)
                result["context"] = text[start:end].replace('\n', ' ')
        
        return result

    async def _search_bing_for_eol(self, software_name: str, version: str = None) -> Dict[str, Any]:
        """
        Perform Bing search and extract EOL information.
        Returns extracted content with confidence scoring.
        
        Note: Browser stays open across searches for better performance.
        Only the page is created and closed per search.
        """
        if not await self._ensure_browser():
            return {
                "success": False,
                "error": self._initialization_error,
                "content": None
            }
        
        page = None
        context = None
        
        try:
            # Create context with realistic browser properties
            context = await self._browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                locale='en-US',
                timezone_id='America/Los_Angeles',
                extra_http_headers={
                    'Accept-Language': 'en-US,en;q=0.9',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
                    'Accept-Encoding': 'gzip, deflate, br',
                    'DNT': '1',
                    'Connection': 'keep-alive',
                    'Upgrade-Insecure-Requests': '1',
                    'Sec-Fetch-Dest': 'document',
                    'Sec-Fetch-Mode': 'navigate',
                    'Sec-Fetch-Site': 'none',
                    'Sec-Fetch-User': '?1',
                    'Cache-Control': 'max-age=0'
                }
            )
            
            # Create new page
            page = await context.new_page()
            
            # Anti-detection script injection
            if self._stealth_mode:
                await page.add_init_script("""
                    Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                    Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
                    Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
                    window.chrome = {runtime: {}};
                    Object.defineProperty(navigator, 'hardwareConcurrency', {get: () => 8});
                    Object.defineProperty(navigator, 'deviceMemory', {get: () => 8});
                """)
            
            logger.debug("📄 New page created with stealth configuration")
            
            # Build search query
            query = f"{software_name} {version or ''} end of life date".strip()
            query_encoded = query.replace(" ", "%20")
            url = f"https://www.bing.com/search?q={query_encoded}&form=DEEPSH"
            
            logger.info(f"🔍 Searching Bing: {query}")
            
            # Navigate to Bing search with realistic behavior
            try:
                await page.goto(url, timeout=30000, wait_until='domcontentloaded')
            except Exception as e:
                logger.warning(f"⚠️ Navigation timeout or error: {str(e)[:100]}")
                # Continue anyway - page might be partially loaded
            
            # Wait for initial load
            await asyncio.sleep(3)
            
            # Check for Cloudflare challenge and wait if needed
            page_text = await page.inner_text('body')
            if 'One last step' in page_text or 'Just a moment' in page_text:
                logger.info("⏳ Cloudflare challenge detected, waiting for completion...")
                # Wait up to 15 seconds for Cloudflare to complete
                for i in range(15):
                    await asyncio.sleep(1)
                    page_text = await page.inner_text('body')
                    if 'One last step' not in page_text and 'Just a moment' not in page_text:
                        logger.info(f"✅ Challenge completed after {i+1} seconds")
                        break
                    if i == 14:
                        logger.warning("⚠️ Challenge still present after 15 seconds")
                await asyncio.sleep(5)
            else:
                await asyncio.sleep(5)
            
            # Final check for blocking
            page_text = await page.inner_text('body')
            if len(page_text) < 200 and ('One last step' in page_text or 'Please solve the challenge' in page_text):
                logger.warning("🛑 Cloudflare challenge page detected (blocked)")
                return {
                    "success": False,
                    "error": "cloudflare_blocked",
                    "content": None
                }
               
            # Try multiple selectors to extract content
            # First try to extract from iframes (Bing often loads content in iframes)
            extracted_html = None
            extracted_text = None
            selector_used = None
            
            # Get all frames (including iframes)
            frames = page.frames
            logger.info(f"📊 Found {len(frames)} frame(s) on page")
            
            # Method 1: Try to find content in frames (including iframes)
            for frame_idx, frame in enumerate(frames):
                frame_url = frame.url
                logger.info(f"Checking frame {frame_idx}: {frame_url[:80]}...")
                
                for selector in self.selectors_to_try:
                    try:
                        element = await frame.query_selector(selector)
                        if element:
                            html = await element.inner_html()
                            text = await element.inner_text()
                            
                            if text and len(text) > 100:
                                logger.info(f"✅ Extracted content from frame {frame_idx} using selector: {selector}")
                                extracted_html = html
                                extracted_text = text
                                selector_used = f"frame_{frame_idx}_{selector}"
                                break
                    except Exception as e:
                        logger.info(f"    Selector {selector} failed on frame {frame_idx}: {e}")
                        continue
                
                if extracted_html:
                    break
            
            # Method 2: If no iframe content found, try main page with locators
            if not extracted_html:
                logger.info("  No content in iframes, trying main page...")
                for selector in self.selectors_to_try:
                    try:
                        loc = page.locator(selector)
                        count = await loc.count()
                        
                        if count and count > 0:
                            if selector == 'body':
                                # For body, limit the content size
                                extracted_html = await page.content()
                                extracted_text = await page.inner_text('body')
                            else:
                                extracted_html = await loc.first.inner_html()
                                extracted_text = await loc.first.inner_text()
                            
                            if extracted_text and len(extracted_text) > 100:
                                selector_used = selector
                                logger.info(f"✅ Extracted content from main page using selector: {selector}")
                                break
                                
                    except Exception as e:
                        logger.info(f"Selector {selector} failed: {e}")
                        continue
            
            if not extracted_text:
                logger.warning("⚠️ No content extracted from any frame or selector")
                return {
                    "success": False,
                    "error": "no_content_extracted",
                    "content": None
                }
            
            # Clean up the extracted text (remove extra whitespace)
            text_content = re.sub(r'\s+', ' ', extracted_text).strip()
            
            logger.info(f"📝 Extracted text content: {len(text_content)} chars")
            
            return {
                "success": True,
                "content": text_content,
                "html": extracted_html[:5000] if extracted_html else "",  # Keep first 5KB for debugging
                "selector": selector_used,
                "url": url
            }
            
        except Exception as e:
            logger.error(f"❌ Bing search failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "content": None
            }
            
        finally:
            # Always close the page and context (but keep browser open for reuse)
            if page:
                try:
                    await page.close()
                    logger.debug("📄 Page closed")
                except Exception as e:
                    logger.warning(f"⚠️ Error closing page: {e}")
            
            if context:
                try:
                    await context.close()
                    logger.debug("📄 Context closed (browser kept alive for reuse)")
                except Exception as e:
                    logger.warning(f"⚠️ Error closing context: {e}")

    async def get_eol_data(self, software_name: str, version: str = None, technology_context: str = None) -> Dict[str, Any]:
        """
        Get EOL data by searching Bing and extracting dates with confidence scoring.
        
        Args:
            software_name: Name of the software
            version: Optional version number
            technology_context: Optional context (not used in this agent)
        
        Returns:
            Standardized EOL data response with confidence scores
        """
        start_time = time.time()
        
        try:
            logger.info(f"🎭 Playwright EOL Agent starting search for: {software_name} {version or ''}")
            
            # Perform Bing search
            search_result = await self._search_bing_for_eol(software_name, version)
            
            if not search_result.get("success"):
                error_msg = search_result.get("error", "unknown_error")
                logger.warning(f"⚠️ Search failed: {error_msg}")
                return self.create_failure_response(
                    software_name=software_name,
                    version=version,
                    error_message=f"Bing search failed: {error_msg}",
                    error_code="search_failed"
                )
            
            # Extract EOL dates from content
            text_content = search_result["content"]
            eol_extraction = self._extract_eol_dates_from_text(text_content, software_name)
            
            if eol_extraction["eol_date"]:
                # Success - found EOL date
                response_time = time.time() - start_time
                
                logger.info(f"✅ Found EOL date: {eol_extraction['eol_date']} (confidence: {eol_extraction['confidence']})")
                if len(eol_extraction.get("all_dates", [])) > 1:
                    logger.info(f"📅 Other dates found: {', '.join(eol_extraction['all_dates'][1:3])}")
                
                # Map confidence to numeric value
                confidence_map = {
                    'very_high': 0.95,
                    'high': 0.85,
                    'medium': 0.70,
                    'low': 0.50
                }
                confidence_score = confidence_map.get(eol_extraction['confidence'], 0.70)
                
                return self.create_success_response(
                    software_name=software_name,
                    version=version,
                    eol_date=eol_extraction["eol_date"],
                    confidence=confidence_score,
                    source_url=search_result.get("url"),
                    additional_data={
                        "confidence_level": eol_extraction["confidence"],
                        "all_dates_found": eol_extraction["all_dates"][:5],  # Top 5 dates
                        "extraction_context": eol_extraction.get("context", ""),
                        "selector_used": search_result.get("selector"),
                        "response_time": round(response_time, 2),
                        "extraction_method": "playwright_bing_search"
                    }
                )
            else:
                # No EOL date found
                logger.warning(f"⚠️ No EOL date found for {software_name} {version or ''}")
                
                # Provide a sample of the content for debugging
                sample = text_content[:300] if text_content else ""
                
                return self.create_failure_response(
                    software_name=software_name,
                    version=version,
                    error_message="No EOL date found in search results",
                    error_code="no_eol_date_found"
                )
            
        except Exception as e:
            logger.error(f"❌ Playwright agent failed: {e}", exc_info=True)
            return self.create_failure_response(
                software_name=software_name,
                version=version,
                error_message=f"Agent exception: {str(e)}",
                error_code="agent_exception"
            )
        
        finally:
            # Browser is kept alive for reuse across multiple searches
            # Page cleanup is handled in _search_bing_for_eol() finally block
            # Explicit cleanup() call required to close browser when done
            pass

    async def health_check(self) -> bool:
        """
        Check if the agent is healthy and can perform searches.
        """
        if not PLAYWRIGHT_AVAILABLE:
            logger.warning("⚠️ Playwright not available")
            return False
        
        try:
            # Try to launch browser
            if await self._ensure_browser():
                logger.info("✅ Playwright health check passed")
                self._health_checked = True
                return True
            else:
                logger.warning("⚠️ Playwright health check failed: browser launch failed")
                return False
                
        except Exception as e:
            logger.error(f"❌ Playwright health check failed: {e}")
            return False

    async def cleanup(self):
        """
        Cleanup resources (close browser, etc.)
        """
        logger.info("🧹 Cleaning up Playwright agent resources...")
        await self._close_browser()
        logger.info("✅ Playwright agent cleanup complete")

    def __del__(self):
        """Destructor to ensure cleanup"""
        if self._browser or self._playwright:
            logger.warning("⚠️ Playwright resources not cleaned up properly - forcing cleanup")
            # Note: Can't use asyncio.run() in __del__, resources will leak
            # Proper cleanup should be done via explicit cleanup() call
