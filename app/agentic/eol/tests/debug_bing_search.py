#!/usr/bin/env python3
"""
Mock test script for searching EOL dates of different OS and versions using Bing Copilot
Tests iframe extraction and EOL date parsing from Bing's response

NOW SUPPORTS HEADLESS MODE with advanced stealth techniques!
- Uses Chrome's new headless mode (harder to detect)
- Implements comprehensive anti-detection measures
- Automatically waits for Cloudflare challenges to complete
- Spoofs browser properties to appear as real Chrome

Usage:
    # Using the shell wrapper (runs headless by default):
    ./run_debug_bing.sh
    
    # Or directly with .venv (headless):
    source ../../../../.venv/bin/activate
    python3 debug_bing_search.py
    
    # Run with visible browser window:
    python3 debug_bing_search.py --headed

Features:
    - Advanced anti-detection: Hides automation signals
    - New headless mode: Uses Chrome 109+ headless=new flag
    - Auto-challenge handler: Waits for Cloudflare to complete
    - Realistic headers: Mimics genuine browser requests
"""

import asyncio
import sys
import re
import argparse
from datetime import datetime

# Check if playwright is available
try:
    from playwright.async_api import async_playwright
except ImportError:
    print("❌ Error: Playwright is not installed")
    print("\nPlease install it in your .venv:")
    print("  source ../../../../.venv/bin/activate")
    print("  pip install playwright")
    print("  playwright install chromium")
    sys.exit(1)


# Test cases: different OS and versions
TEST_CASES = [
    {"os": "Windows Server", "version": "2016", "query": "Windows Server 2016 end of life date"},
    {"os": "Windows Server", "version": "2019", "query": "Windows Server 2019 end of life date"},
    {"os": "Windows", "version": "10", "query": "Windows 10 end of life date"},
    {"os": "Ubuntu", "version": "20.04", "query": "Ubuntu 20.04 LTS end of life date"},
    {"os": "Red Hat Enterprise Linux", "version": "8", "query": "RHEL 8 end of life date"},
]


async def extract_eol_from_text(text: str, os_name: str) -> dict:
    """Extract EOL date from text using pattern matching"""
    result = {
        "eol_date": None,
        "confidence": "low",
        "raw_matches": [],
        "all_dates_found": []
    }
    
    # Extended date patterns to capture more formats
    date_patterns = [
        # Pattern 1: "31 May 2025" or "May 31 2025" (with or without comma)
        (r'\b(\d{1,2}\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4})\b', 'high'),
        (r'\b((?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4})\b', 'high'),
        
        # Pattern 2: Dates near EOL keywords
        (r'(?:end of life|EOL|support ends?|standard support|extended support|legacy support)(?:\s+(?:is|on|date|until|:))?\s*(?:on\s+)?[:\s]*([A-Za-z]+\s+\d{1,2},?\s+\d{4})', 'very_high'),
        (r'(?:end of life|EOL|support ends?|standard support|extended support|legacy support)(?:\s+(?:is|on|date|until|:))?\s*(?:on\s+)?[:\s]*(\d{1,2}\s+[A-Za-z]+\s+\d{4})', 'very_high'),
        
        # Pattern 3: Numeric formats
        (r'\b(\d{1,2}/\d{1,2}/\d{4})\b', 'medium'),
        (r'\b(\d{4}-\d{2}-\d{2})\b', 'medium'),
        
        # Pattern 4: Year only mentions
        (r'(?:until|through|end of)\s+(\d{4})', 'low'),
    ]
    
    # First pass: collect all date matches with their confidence
    date_confidence_map = {}
    
    for pattern, confidence_level in date_patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        for match in matches:
            # Handle tuple results from regex groups
            date_str = match if isinstance(match, str) else match[0] if match else None
            if date_str and date_str not in date_confidence_map:
                date_confidence_map[date_str] = confidence_level
                result["all_dates_found"].append({
                    "date": date_str,
                    "confidence": confidence_level
                })
    
    # Sort by confidence priority
    confidence_priority = {'very_high': 4, 'high': 3, 'medium': 2, 'low': 1}
    sorted_dates = sorted(
        result["all_dates_found"],
        key=lambda x: confidence_priority.get(x['confidence'], 0),
        reverse=True
    )
    
    if sorted_dates:
        best_match = sorted_dates[0]
        result["eol_date"] = best_match["date"]
        result["confidence"] = best_match["confidence"]
        result["raw_matches"] = [d["date"] for d in sorted_dates]
        
        # Boost confidence if OS name is nearby the date
        os_name_lower = os_name.lower()
        # Check if OS name appears within 200 characters of the date
        date_pos = text.lower().find(result["eol_date"].lower())
        if date_pos != -1:
            context = text[max(0, date_pos-200):min(len(text), date_pos+200)].lower()
            if os_name_lower in context or any(word in context for word in os_name_lower.split()):
                if result["confidence"] == "high":
                    result["confidence"] = "very_high"
                elif result["confidence"] == "medium":
                    result["confidence"] = "high"
    
    return result


async def search_eol_for_os(browser, test_case: dict, test_index: int):
    """Search for EOL date for a specific OS/version"""
    
    print("\n" + "="*80)
    print(f"🔍 Test Case {test_index + 1}: {test_case['os']} {test_case['version']}")
    print("="*80)
    
    # Create context with realistic browser properties to avoid bot detection
    context = await browser.new_context(
        viewport={'width': 1920, 'height': 1080},
        user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        locale='en-US',
        timezone_id='America/Los_Angeles',
        extra_http_headers={
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
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
    
    page = await context.new_page()
    
    # Comprehensive anti-detection script injection
    await page.add_init_script("""
        // Override the navigator.webdriver property
        Object.defineProperty(navigator, 'webdriver', {
            get: () => undefined
        });
        
        // Override navigator.plugins to make it look real
        Object.defineProperty(navigator, 'plugins', {
            get: () => [1, 2, 3, 4, 5]
        });
        
        // Override navigator.languages
        Object.defineProperty(navigator, 'languages', {
            get: () => ['en-US', 'en']
        });
        
        // Chrome runtime
        window.chrome = {
            runtime: {}
        };
        
        // Override permissions
        const originalQuery = window.navigator.permissions.query;
        window.navigator.permissions.query = (parameters) => (
            parameters.name === 'notifications' ?
                Promise.resolve({ state: Notification.permission }) :
                originalQuery(parameters)
        );
        
        // Add missing browser properties
        Object.defineProperty(navigator, 'hardwareConcurrency', {
            get: () => 8
        });
        
        Object.defineProperty(navigator, 'deviceMemory', {
            get: () => 8
        });
        
        // Override toString to hide proxy
        const originalToString = Function.prototype.toString;
        Function.prototype.toString = function() {
            if (this === window.navigator.permissions.query) {
                return 'function query() { [native code] }';
            }
            return originalToString.call(this);
        };
    """)
    
    results = {
        "os": test_case["os"],
        "version": test_case["version"],
        "query": test_case["query"],
        "eol_info": None,
        "frames_found": 0,
        "iframe_content_found": False,
        "extraction_method": None,
        "timestamp": datetime.now().isoformat()
    }
    
    try:
        # Build Bing Copilot search URL
        query_encoded = test_case["query"].replace(" ", "%20")
        url = f"https://www.bing.com/search?q={query_encoded}&form=DEEPSH"
        
        print(f"📍 URL: {url}")
        
        # Navigate with realistic behavior - use shorter timeout for networkidle
        try:
            await page.goto(url, timeout=30000, wait_until='domcontentloaded')
        except Exception as e:
            print(f"   ⚠️ Navigation timeout or error: {str(e)[:100]}")
            # Continue anyway - page might be partially loaded
        
        # Wait for initial load
        print("⏳ Waiting for page to fully load...")
        await asyncio.sleep(3)
        
        # Check for Cloudflare challenge and wait if needed
        page_text = await page.inner_text('body')
        if 'One last step' in page_text or 'Just a moment' in page_text:
            print("⏳ Cloudflare challenge detected, waiting for it to complete...")
            # Wait up to 15 seconds for Cloudflare to complete
            for i in range(15):
                await asyncio.sleep(1)
                page_text = await page.inner_text('body')
                # Check if challenge is resolved
                if 'One last step' not in page_text and 'Just a moment' not in page_text:
                    print(f"   ✅ Challenge completed after {i+1} seconds")
                    break
                if i == 14:
                    print("   ⚠️  Challenge still present after 15 seconds")
            
            # Additional wait for content to load after challenge
            await asyncio.sleep(5)
        else:
            # Normal wait
            await asyncio.sleep(5)
        
        # Final check for blocking
        page_text = await page.inner_text('body')
        if len(page_text) < 200 and ('One last step' in page_text or 'Please solve the challenge' in page_text):
            print("🛑 DETECTED: Cloudflare challenge page (still blocked)!")
            print("   The automatic challenge solver may need more time or failed.")
            results["cloudflare_blocked"] = True
        
        # Get all frames
        frames = page.frames
        results["frames_found"] = len(frames)
        print(f"📊 Found {len(frames)} frame(s)")
        
        extracted_text = None
        
        # Method 1: Try to find answer_container in frames
        for i, frame in enumerate(frames):
            frame_url = frame.url
            print(f"\n  Frame {i}: {frame_url[:80]}...")
            
            try:
                # Look for answer_container or other answer elements
                selectors_to_try = [
                    '.answer_container',
                    '[data-snippet]',
                    '.b_ans',
                    '#b_context',
                    '.cib-serp-main'
                ]
                
                for selector in selectors_to_try:
                    try:
                        element = await frame.query_selector(selector)
                        if element:
                            html = await element.inner_html()
                            text = await element.inner_text()
                            
                            if text and len(text) > 50:
                                print(f"    ✅ Found content with selector: {selector}")
                                print(f"    📝 Text length: {len(text)} chars")
                                extracted_text = text
                                results["extraction_method"] = f"frame_{i}_{selector}"
                                results["iframe_content_found"] = True
                                
                                # Save HTML for inspection
                                filename = f'/tmp/eol_test_{test_index}_{selector.replace(".", "").replace("#", "")}.html'
                                with open(filename, 'w', encoding='utf-8') as f:
                                    f.write(html)
                                print(f"    💾 Saved to: {filename}")
                                break
                    except Exception as e:
                        continue
                
                if extracted_text:
                    break
                    
            except Exception as e:
                print(f"    ⚠️  Frame error: {str(e)[:50]}")
        
        # Method 2: If no iframe content, try main page
        if not extracted_text:
            print("\n  📄 Trying main page content...")
            try:
                main_content = await page.inner_text('body')
                if main_content:
                    extracted_text = main_content
                    results["extraction_method"] = "main_page"
                    print(f"    ✅ Extracted {len(main_content)} chars from main page")
            except Exception as e:
                print(f"    ❌ Main page extraction error: {e}")
        
        # Extract EOL information
        if extracted_text:
            print(f"\n  🔍 Analyzing extracted text for EOL date...")
            eol_info = await extract_eol_from_text(extracted_text, test_case["os"])
            results["eol_info"] = eol_info
            
            if eol_info["eol_date"]:
                print(f"    ✅ Found EOL date: {eol_info['eol_date']}")
                print(f"    📊 Confidence: {eol_info['confidence']}")
                if len(eol_info.get("all_dates_found", [])) > 1:
                    print(f"    � All dates found: {', '.join([d['date'] for d in eol_info['all_dates_found'][:5]])}")
                print(f"    �🔢 Top matches: {eol_info['raw_matches'][:3]}")
            else:
                print(f"    ⚠️  No EOL date found in text")
                # Show sample of text for debugging
                sample = extracted_text[:300].replace('\n', ' ')
                print(f"    📝 Text sample: {sample}...")
        else:
            print(f"    ❌ No content extracted")
        
        # Take screenshot
        screenshot_path = f'/tmp/eol_test_{test_index}_screenshot.png'
        await page.screenshot(path=screenshot_path, full_page=True)
        print(f"\n  📸 Screenshot saved to: {screenshot_path}")
        
    except Exception as e:
        print(f"\n  ❌ Test failed: {e}")
        results["error"] = str(e)
    
    finally:
        await context.close()
    
    return results


async def debug_search(headless: bool = True, stealth_mode: bool = True, use_firefox: bool = False):
    """Run EOL search tests for multiple OS versions
    
    Args:
        headless: If True, run in headless mode with stealth techniques
        stealth_mode: If True, use additional anti-detection techniques (recommended)
        use_firefox: If True, use Firefox instead of Chromium (better headless support)
    """
    
    print("\n" + "="*80)
    print("🧪 MOCK TEST: EOL Date Search for Multiple OS Versions")
    print("="*80)
    browser_type = 'Firefox' if use_firefox else 'Chromium'
    print(f"🎭 Browser: {browser_type} | Mode: {'Headless' if headless else 'Headed'} | Stealth: {'Enabled' if stealth_mode else 'Disabled'}")
    print(f"\nTesting {len(TEST_CASES)} different OS/version combinations\n")
    
    async with async_playwright() as p:
        browser_engine = p.firefox if use_firefox else p.chromium
        # Launch browser once for all tests
        # Note: Firefox generally has better headless support than Chromium
        
        if use_firefox:
            # Firefox launch (simpler, better headless support)
            firefox_args = []
            if stealth_mode:
                firefox_args.extend([
                    '-width=1920',
                    '-height=1080'
                ])
            
            browser = await browser_engine.launch(
                headless=headless,
                args=firefox_args,
                firefox_user_prefs={
                    'dom.webdriver.enabled': False,
                    'useAutomationExtension': False,
                    'general.platform.override': 'MacIntel'
                } if stealth_mode else {}
            )
        else:
            # Chromium launch
            launch_args = [
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage',
            ]
            
            if stealth_mode:
                # Advanced stealth arguments to bypass Cloudflare detection
                launch_args.extend([
                    '--disable-blink-features=AutomationControlled',  # Critical: Hide automation
                    '--exclude-switches=enable-automation',  # Remove automation flags
                    '--disable-infobars',  # Remove info bars
                    '--window-size=1920,1080',  # Set realistic window size
                    '--start-maximized',  # Start maximized
                    '--disable-web-security',  # Disable web security
                    '--disable-features=IsolateOrigins,site-per-process',  # Disable isolation
                    '--disable-site-isolation-trials',  # Disable site isolation
                    '--disable-features=BlockInsecurePrivateNetworkRequests',  # Allow requests
                ])
            
            # Use new headless mode (Chrome 109+) which is harder to detect
            if headless:
                launch_args.append('--headless=new')  # Use new headless mode
                browser = await browser_engine.launch(
                    args=launch_args,
                    chromium_sandbox=False
                )
            else:
                browser = await browser_engine.launch(
                    headless=False,
                    args=launch_args
                )
        
        if use_firefox:
            print("🦊 Using Firefox for better headless compatibility")
        
        if headless:
            print("🤖 Running in headless mode with advanced stealth techniques")
            print("   Using anti-detection measures to bypass Cloudflare...")
            if not use_firefox:
                print("   💡 TIP: Try --firefox flag if Cloudflare blocks occur")
        else:
            print("🌐 Browser window opened - Full stealth mode active")
        
        all_results = []
        
        try:
            # Run test for each OS/version
            for i, test_case in enumerate(TEST_CASES):
                result = await search_eol_for_os(browser, test_case, i)
                all_results.append(result)
                
                # Brief pause between tests
                if i < len(TEST_CASES) - 1:
                    print(f"\n⏸️  Waiting 3 seconds before next test...")
                    await asyncio.sleep(3)
            
            # Print summary
            print("\n" + "="*80)
            print("� TEST SUMMARY")
            print("="*80)
            
            for i, result in enumerate(all_results):
                print(f"\n{i+1}. {result['os']} {result['version']}")
                print(f"   Query: {result['query']}")
                
                if result.get('cloudflare_blocked'):
                    print(f"   🛑 BLOCKED: Cloudflare challenge detected")
                
                print(f"   Frames found: {result['frames_found']}")
                print(f"   Iframe content: {'✅ Yes' if result['iframe_content_found'] else '❌ No'}")
                print(f"   Extraction method: {result['extraction_method'] or 'None'}")
                
                if result.get('eol_info') and result['eol_info']['eol_date']:
                    print(f"   EOL Date: ✅ {result['eol_info']['eol_date']} (confidence: {result['eol_info']['confidence']})")
                else:
                    print(f"   EOL Date: ❌ Not found")
                
                if 'error' in result:
                    print(f"   Error: {result['error']}")
            
            print("\n" + "="*80)
            print("📁 Saved files in /tmp/:")
            print("   - eol_test_*_screenshot.png (screenshots)")
            print("   - eol_test_*_*.html (extracted HTML)")
            print("="*80)
            
            # Check if any were blocked
            blocked_count = sum(1 for r in all_results if r.get('cloudflare_blocked'))
            if blocked_count > 0:
                print(f"\n⚠️  WARNING: {blocked_count} test(s) blocked by Cloudflare")
                print("   SOLUTION: Run without --headless flag:")
                print("   python3 debug_bing_search.py")
                print("="*80)
            
            # Keep browser open for manual inspection
            print("\n⏸️  Browser will stay open for 20 seconds for manual inspection...")
            await asyncio.sleep(20)
            
        finally:
            await browser.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description='Test EOL date extraction from Bing searches with advanced headless stealth',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run in headless mode with Chromium (default):
  python3 debug_bing_search.py
  
  # Run in headless mode with Firefox (recommended - better Cloudflare bypass):
  python3 debug_bing_search.py --firefox
  
  # Run with visible browser window:
  python3 debug_bing_search.py --headed
  
  # Headless without stealth (not recommended):
  python3 debug_bing_search.py --no-stealth
  
Note: Firefox generally has better headless support and bypasses Cloudflare more reliably.
      Use --firefox flag if you encounter blocking issues with Chromium.
        """
    )
    parser.add_argument('--headed', action='store_true',
                        help='Run with visible browser window')
    parser.add_argument('--firefox', action='store_true',
                        help='Use Firefox instead of Chromium (better headless support)')
    parser.add_argument('--stealth', action='store_true', default=True,
                        help='Enable stealth mode with anti-detection (default: enabled)')
    parser.add_argument('--no-stealth', dest='stealth', action='store_false',
                        help='Disable stealth mode')
    
    args = parser.parse_args()
    
    headless = not args.headed  # Invert: default is headless now
    
    if not headless:
        print("🌐 Running with visible browser window")
        print("   This provides maximum compatibility with Cloudflare.\n")
    
    if args.firefox:
        print("🦊 Firefox selected - Generally better for headless mode\n")
    
    asyncio.run(debug_search(headless=headless, stealth_mode=args.stealth, use_firefox=args.firefox))
