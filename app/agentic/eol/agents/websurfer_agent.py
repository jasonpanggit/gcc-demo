import asyncio
import logging
import time
import re
from typing import Dict, Any, Optional

from .base_eol_agent import BaseEOLAgent

logger = logging.getLogger(__name__)

# Check for AutoGen dependencies availability
AUTOGEN_AVAILABLE = False
try:
    # Import only if libraries are available
    from autogen_ext.agents.web_surfer import MultimodalWebSurfer
    AUTOGEN_AVAILABLE = True
    logger.info("✅ AutoGen dependencies loaded successfully for WebSurfer agent")
except ImportError as import_error:
    logger.warning(f"⚠️ AutoGen dependencies not available: {import_error}")
    logger.warning("⚠️ WebSurfer functionality will use fallback methods")

# Define placeholder classes for type hints when imports fail
if AUTOGEN_AVAILABLE:
    from autogen_core import CancellationToken
    try:
        from autogen_agentchat.messages import TextMessage, MultiModalMessage
    except ImportError:
        # Fallback if MultiModalMessage is not available
        from autogen_agentchat.messages import TextMessage
        MultiModalMessage = TextMessage
else:
    # Placeholder classes for when AutoGen is not available
    class CancellationToken:
        pass
    
    class TextMessage:
        def __init__(self, content: str, source: str):
            self.content = content
            self.source = source
    
    class MultiModalMessage:
        def __init__(self, content: str, source: str):
            self.content = content
            self.source = source


class WebsurferEOLAgent(BaseEOLAgent):
    """EOL Agent that uses WebSurfer for real-time web search"""

    def __init__(self, model_client):
        super().__init__("websurfer_eol")
        self.web_surfer = None
        self._initialization_error = None
        self._health_checked = False
        self._initialize_websurfer(model_client)

    def _initialize_websurfer(self, model_client):
        """Initialize WebSurfer only if AutoGen dependencies are available"""
        if not AUTOGEN_AVAILABLE:
            self._initialization_error = "autogen_unavailable"
            logger.warning("⚠️ AutoGen dependencies not available - WebSurfer will not be initialized")
            return
            
        try:
            from autogen_ext.agents.web_surfer import MultimodalWebSurfer
            import os
            
            # Configure browser options for Azure App Services container environment
            # Set environment variables for Playwright browser configuration
            import os
            
            # Check if running in container environment
            if os.getenv('CONTAINER_MODE') or os.getenv('WEBSITE_SITE_NAME'):
                logger.info("🐳 Container environment detected - configuring Playwright for Azure App Services")
                
                # Set Playwright browser arguments via environment variable
                # This is the recommended approach for autogen-ext WebSurfer
                browser_args = [
                    # Core security and sandbox arguments
                    "--no-sandbox",
                    "--disable-setuid-sandbox", 
                    "--disable-dev-shm-usage",
                    
                    # Performance optimizations for containers
                    "--disable-accelerated-2d-canvas",
                    "--disable-gpu",
                    "--disable-gpu-sandbox",
                    "--disable-software-rasterizer",
                    "--disable-background-timer-throttling",
                    "--disable-backgrounding-occluded-windows",
                    "--disable-renderer-backgrounding",
                    "--disable-features=TranslateUI",
                    "--disable-features=VizDisplayCompositor",
                    "--disable-ipc-flooding-protection",
                    
                    # Memory and process management
                    "--memory-pressure-off",
                    "--max_old_space_size=4096",
                    "--no-zygote",
                    "--single-process",
                    
                    # Azure App Service specific optimizations
                    "--no-first-run",
                    "--no-default-browser-check",
                    "--disable-default-apps",
                    "--disable-extensions",
                    "--disable-component-extensions-with-background-pages",
                    "--disable-background-networking",
                    "--disable-sync",
                    "--disable-translate",
                    "--hide-scrollbars",
                    "--mute-audio",
                    
                    # Network and security settings
                    "--disable-web-security",
                    "--disable-features=VizDisplayCompositor",
                    "--ignore-certificate-errors",
                    "--ignore-ssl-errors",
                    "--ignore-certificate-errors-spki-list",
                    
                    # Window and display settings for headless mode
                    "--window-size=1920,1080",
                    "--virtual-time-budget=5000",
                    
                    # Disable screenshot and visual operations that can cause issues in containers
                    "--disable-canvas-aa",
                    "--disable-2d-canvas-clip-aa", 
                    "--disable-gl-drawing-for-tests",
                    "--disable-gl-extensions",
                    "--disable-skia-runtime-opts",
                    "--disable-system-font-check",
                    "--disable-vulkan-fallback-to-gl-for-testing",
                    
                    # Additional stability for Azure App Service
                    "--force-color-profile=srgb",
                    "--disable-lcd-text",
                    "--disable-logging",
                    "--disable-breakpad"
                ]
                
                # Set environment variables that Playwright/WebSurfer will use
                os.environ['PLAYWRIGHT_CHROMIUM_ARGS'] = ' '.join(browser_args)
                os.environ['PLAYWRIGHT_BROWSER_HEADLESS'] = 'true'
                
                # Additional Playwright environment variables for container compatibility
                os.environ['PLAYWRIGHT_LAUNCH_OPTIONS'] = '{"headless": true, "args": ["' + '", "'.join(browser_args) + '"]}'
                
                # Disable screenshot and multimodal features to prevent container issues
                os.environ['PLAYWRIGHT_DISABLE_SCREENSHOTS'] = 'true'
                os.environ['PLAYWRIGHT_SKIP_BROWSER_VALIDATION'] = 'true'
                os.environ['PLAYWRIGHT_BROWSERS_PATH'] = '/ms-playwright'
                
                # Disable problematic page evaluation operations that cause CancelledError
                os.environ['AUTOGEN_DISABLE_MULTIMODAL'] = 'true'
                os.environ['AUTOGEN_DISABLE_FOCUS_TRACKING'] = 'true'
                os.environ['PLAYWRIGHT_DISABLE_FOCUS_RECT'] = 'true'
                
                # Additional WebSurfer-specific environment variables to disable screenshots
                os.environ['WEBSURFER_DISABLE_SCREENSHOTS'] = 'true'
                os.environ['MULTIMODAL_WEBSURFER_DISABLE_SCREENSHOTS'] = 'true'
                os.environ['AUTOGEN_WEBSURFER_DISABLE_VISION'] = 'true'
                
                # Additional focus and interaction disabling for container stability
                os.environ['AUTOGEN_WEBSURFER_DISABLE_FOCUS'] = 'true'
                os.environ['PLAYWRIGHT_DISABLE_PAGE_EVALUATION'] = 'true'
                os.environ['WEBSURFER_SIMPLE_MODE'] = 'true'
                
                logger.info(f"🔧 Configured {len(browser_args)} browser args for container environment")
                logger.info(f"🔧 Set PLAYWRIGHT_CHROMIUM_ARGS environment variable")
                logger.info("🔧 Disabled screenshot operations for container compatibility")
            
            # Create WebSurfer instance for cloud-friendly deployment
            # Note: Browser configuration is handled via environment variables set above
            self.web_surfer = MultimodalWebSurfer(
                name="websurfer_eol_agent", 
                model_client=model_client
            )

            logger.info("🌐 WebSurfer instance created successfully - will test browser on first use")
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize WebSurfer: {e}")
            self._initialization_error = f"init_failed: {str(e)}"
            self.web_surfer = None

    async def get_eol_data(self, software_name: str, version: str = None, technology_context: str = None) -> Dict[str, Any]:
        """Get EOL data using WebSurfer - returns unsuccessful result if WebSurfer fails to allow other agents to try"""
        start_time = time.time()
        
        try:
            logger.info(f"🔍 WebSurfer EOL Agent starting search for: {software_name} {version or ''}")
            
            # Check WebSurfer health before attempting search
            if self.web_surfer:
                is_healthy = await self.check_websurfer_health()
                if is_healthy:
                    logger.info("✅ WebSurfer health check passed - proceeding with search")
                    
                    # Perform WebSurfer search
                    search_result = await self.perform_websurfer_search(software_name, version, technology_context)
                    
                    if search_result.get("success", False):
                        logger.info(f"✅ WebSurfer search successful for {software_name} {version or ''}")
                        return search_result
                    else:
                        logger.warning("⚠️ WebSurfer search unsuccessful - returning failure to allow other agents to try")
                        return {
                            "success": False,
                            "agent": self.agent_name,
                            "error": "websurfer_search_failed",
                            "details": "WebSurfer was unable to retrieve EOL data"
                        }
                else:
                    logger.info("⚠️ WebSurfer health check failed - returning failure to allow other agents to try")
                    return {
                        "success": False,
                        "agent": self.agent_name,
                        "error": "websurfer_health_check_failed",
                        "details": f"WebSurfer health check failed: {self._initialization_error}"
                    }
            else:
                # WebSurfer not available - return failure to allow other agents to try
                if self._initialization_error:
                    logger.info(f"💡 WebSurfer unavailable due to: {self._initialization_error}")
                    error_details = f"WebSurfer initialization failed: {self._initialization_error}"
                else:
                    logger.info("💡 WebSurfer not available - this is normal in cloud deployment environments without browser dependencies")
                    error_details = "WebSurfer not available in this environment"
                
                logger.info("🔄 Returning failure to allow other search agents (e.g., Azure AI) to attempt the search")
                return {
                    "success": False,
                    "agent": self.agent_name,
                    "error": "websurfer_unavailable",
                    "details": error_details
                }
            
        except Exception as e:
            logger.error(f"❌ WebSurfer EOL search failed: {e}")
            return {
                "success": False,
                "agent": self.agent_name,
                "error": "websurfer_exception",
                "details": f"WebSurfer search failed with exception: {str(e)}"
            }

    async def _safe_fallback(self, software_name: str, version: str, technology_context: str, primary_error: str = None) -> Dict[str, Any]:
        """
        DEPRECATED: Safely attempt fallback to static knowledge base with error handling
        
        This method is no longer used by default. The WebSurfer agent now returns failure
        to allow other agents (like Azure AI search) to attempt the search before falling back to static data.
        """
        try:
            logger.info("🔄 Attempting fallback to static knowledge base")
            fallback_result = self.get_fallback_eol_info(software_name, version, technology_context)
            
            if fallback_result.get("success", False):
                logger.info("✅ Fallback to static knowledge base successful")
                return fallback_result
            else:
                logger.warning("⚠️ Fallback to static knowledge base returned unsuccessful result")
                
        except Exception as fallback_error:
            logger.error(f"❌ Even fallback to static knowledge base failed: {fallback_error}")
        
        # Return comprehensive error response if all else fails
        error_message = "WebSurfer search failed and fallback unavailable"
        if primary_error:
            error_message = f"WebSurfer search failed ({primary_error}) and fallback unavailable"
            
        return self.create_failure_response(
            software_name=software_name,
            version=version,
            error_message=error_message,
            error_code="all_methods_failed"
        )

    async def check_websurfer_health(self) -> bool:
        """Check if WebSurfer is healthy and can perform searches"""
        # Quick return for known failure states
        if self._initialization_error:
            logger.info(f"🔍 WebSurfer health check: Known initialization error - {self._initialization_error}")
            return False
            
        if not self.web_surfer or not AUTOGEN_AVAILABLE:
            logger.info("🔍 WebSurfer health check: WebSurfer not available")
            return False
        
        # Skip health check in environments where WebSurfer is known to have issues
        import os
        if os.getenv('SKIP_WEBSURFER_HEALTH_CHECK', '').lower() in ['true', '1', 'yes']:
            logger.info("🔍 WebSurfer health check: Skipped due to SKIP_WEBSURFER_HEALTH_CHECK environment variable")
            self._initialization_error = "health_check_skipped"
            return False
        
        # Auto-skip in Azure App Service environments where WebSurfer commonly fails
        # Note: Re-enabled to allow WebSurfer to attempt running in Azure App Service
        # The focus tracking operations may fail, but we'll try with improved environment variables
        if os.getenv('WEBSITE_SITE_NAME') or os.getenv('WEBSITE_INSTANCE_ID'):
            logger.info("🔍 WebSurfer health check: Auto-skipping in Azure App Service environment due to focus tracking issues")
            self._initialization_error = "azure_app_service_environment"
            return False
        
        # Return cached health status if already checked successfully
        if self._health_checked:
            logger.info("✅ WebSurfer health check: Previously verified healthy")
            return True
        
        try:
            # Perform one-time browser health test with container-optimized approach
            logger.info("🔍 WebSurfer health check: Performing first-time browser test")
            
            health_check_start = time.time()
            
            # Use a very simple test message with minimal AI processing required
            test_messages = [TextMessage(
                content="Visit example.com and respond with just 'OK'", 
                source="user"
            )]
            
            # Use shorter timeout for container environments to avoid resource constraints
            timeout_seconds = 30 if self._is_container_environment() else 20
            
            response = await asyncio.wait_for(
                self.web_surfer.on_messages(test_messages, CancellationToken()), 
                timeout=timeout_seconds
            )
            
            if response and response.chat_message:
                content = response.chat_message.content
                logger.info(f"🔍 WebSurfer health check: Browser test returned {len(content)} characters")
                
                # Check for common error patterns that indicate browser issues
                if self._is_error_response(content):
                    logger.error("🔍 WebSurfer health check: Browser test failed with error response")
                    logger.error(f"🔍 Error content: {content[:500]}...")
                    self._initialization_error = "browser_test_failed"
                    return False
                
                # Additional check for container-specific issues
                if self._has_container_browser_issues(content):
                    logger.error("🔍 WebSurfer health check: Container-specific browser issues detected")
                    self._initialization_error = "container_browser_issues"
                    return False
            
            health_check_time = time.time() - health_check_start
            logger.info(f"✅ WebSurfer health check: Browser test passed ({health_check_time:.1f}s)")
            
            # Cache successful health check
            self._health_checked = True
            return True
            
        except asyncio.CancelledError:
            logger.error("🔍 WebSurfer health check: Browser operation was cancelled (likely screenshot issue in container)")
            self._initialization_error = "browser_cancelled_operation"
            return False
        except asyncio.TimeoutError:
            timeout_msg = f"Browser test timed out after {timeout_seconds}s"
            if self._is_container_environment():
                timeout_msg += " - This is common in container environments, falling back to static knowledge base"
            logger.error(f"🔍 WebSurfer health check: {timeout_msg}")
            self._initialization_error = "browser_timeout"
            return False
        except RuntimeError as runtime_error:
            # Handle asyncio event loop issues
            if "event loop" in str(runtime_error).lower():
                logger.error(f"🔍 WebSurfer health check: AsyncIO event loop error - {runtime_error}")
                self._initialization_error = "asyncio_event_loop_error"
            else:
                logger.error(f"🔍 WebSurfer health check: Runtime error - {runtime_error}")
                self._initialization_error = f"runtime_error: {str(runtime_error)}"
            return False
        except Exception as health_check_error:
            logger.error(f"❌ WebSurfer health check failed: {health_check_error}")
            # Check if it's a web surfing error (browser/playwright issue)
            if self._is_browser_related_error(str(health_check_error)):
                self._initialization_error = "browser_test_failed"
            else:
                self._initialization_error = f"health_check_failed: {str(health_check_error)}"
            return False

    async def perform_websurfer_search(self, software_name: str, version: str = None, technology_context: str = "") -> Dict[str, Any]:
        """Perform WebSurfer search for EOL information"""
        if not AUTOGEN_AVAILABLE:
            logger.warning("⚠️ AutoGen dependencies not available - cannot perform WebSurfer search")
            return self.create_failure_response(
                software_name=software_name,
                version=version,
                error_message="AutoGen dependencies not available for WebSurfer",
                error_code="autogen_unavailable"
            )
            
        try:
            # Construct search query based on technology context
            search_query = self._build_search_query(software_name, version, technology_context)
            
            # Perform the actual WebSurfer search
            search_results = await self._execute_websurfer_search(search_query, software_name, version)
            
            if not search_results:
                logger.info("� Primary search failed - falling back to static knowledge base")
                return self.get_fallback_eol_info(software_name, version, technology_context)
            
            # Parse EOL information from search results
            eol_data = self.parse_websurfer_results(search_results, software_name, version)
            
            # Check if parsing was successful or if we need alternative searches
            if eol_data.get("confidence", 0) < 0.7:
                logger.info(f"🔍 Initial search confidence low ({eol_data.get('confidence', 0):.2f}) - attempting alternative searches")
                enhanced_eol_data = await self._try_alternative_searches(software_name, version, eol_data)
                if enhanced_eol_data.get("confidence", 0) > eol_data.get("confidence", 0):
                    eol_data = enhanced_eol_data
            
            # Construct successful response
            return {
                "success": True,
                "data": {
                    "software_name": software_name,
                    "version": version or "Unknown",
                    "eol_date": eol_data.get("eol_date", "Unknown"),
                    "support_end_date": eol_data.get("support_end_date", "Unknown"),
                    "status": eol_data.get("status", "Unknown"),
                    "risk_level": eol_data.get("risk_level", "Unknown"),
                    "confidence": eol_data.get("confidence", 0.5),
                    "source_url": eol_data.get("source_url", ""),
                    "raw_results": search_results
                }
            }
            
        except Exception as e:
            logger.error(f"❌ WebSurfer search failed with exception: {e}")
            logger.info("🔄 Falling back to static EOL knowledge base")
            return self.get_fallback_eol_info(software_name, version, technology_context)

    async def _execute_websurfer_search(self, search_query: str, software_name: str, version: str = None) -> Optional[str]:
        """Execute a single WebSurfer search and return results or None on failure"""
        try:
            # Create task for WebSurfer
            task_message = self._build_task_message(software_name, version, search_query)
            messages = [TextMessage(content=task_message, source="user")]
            
            logger.info(f"🔍 Attempting WebSurfer search for: {search_query}")

            try:
                loop = asyncio.get_running_loop()
                # We're in an async context, need to run in executor
                import concurrent.futures
                import threading
                
                def run_in_new_loop():
                    # Create a new event loop for this thread
                    new_loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(new_loop)

                    try:
                        response = new_loop.run_until_complete(self.web_surfer.on_messages(messages, CancellationToken()))
                        logger.info(f"🔍 WebSurfer raw response: {response}")

                        # Extract information from WebSurfer response
                        search_results = response.chat_message.content if response and response.chat_message else "No results found"
                        
                        # Check if WebSurfer returned an error instead of actual search results
                        if self._is_error_response(search_results):
                            logger.error(f"❌ WebSurfer returned error content instead of search results")
                            logger.error(f"❌ Error content: {search_results[:500]}...")
                            return None
                        
                        logger.info(f"✅ WebSurfer search completed successfully")
                        logger.info(f"🔍 [DEBUG] WebSurfer returned {len(search_results)} characters of content")
                        logger.info(f"🔍 [DEBUG] First 500 chars of WebSurfer results: {search_results[:500]}...")
                
                        return search_results
                    except asyncio.CancelledError:
                        logger.error("🔍 WebSurfer operation was cancelled (common in container environments with focus/screenshot operations)")
                        return None
                    except Exception as loop_error:
                        logger.error(f"🔍 WebSurfer loop error: {loop_error}")
                        return None
                    finally:
                        new_loop.close()

                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(run_in_new_loop)
                    return future.result(timeout=30)
                    
            except RuntimeError as runtime_error:
                # No running event loop, we can use asyncio.run directly
                logger.info(f"🔍 No running event loop detected, using asyncio.run: {runtime_error}")
                return None
            except Exception as inner_error:
                # Handle any other errors in the asyncio logic
                logger.error(f"❌ AsyncIO execution error in Microsoft EOL tool: {inner_error}")
                return None
            
        except Exception as websurfer_error:
            logger.error(f"❌ WebSurfer search operation failed: {websurfer_error}")
            logger.error(f"❌ WebSurfer error type: {type(websurfer_error).__name__}")
            return None
                
    def _build_search_query(self, software_name: str, version: str = None, technology_context: str = "") -> str:
        """Build search query based on technology context"""
        if technology_context.lower() == "microsoft":
            search_query = f"Microsoft {software_name} {version or ''} end of life EOL lifecycle support dates official".strip()
        elif technology_context.lower() == "ubuntu":
            search_query = f"Ubuntu or Linux {software_name} {version or ''} end of life EOL support dates official".strip()
        elif technology_context.lower() == "python":
            search_query = f"Python {software_name} {version or ''} end of life EOL support schedule official".strip()
        elif technology_context.lower() == "nodejs":
            search_query = f"Node.js {software_name} {version or ''} end of life EOL support schedule official".strip()
        elif technology_context.lower() == "php":
            search_query = f"PHP {software_name} {version or ''} end of life EOL support dates official".strip()
        elif technology_context.lower() == "oracle":
            search_query = f"Oracle {software_name} {version or ''} end of life EOL support lifecycle official".strip()
        elif technology_context.lower() == "postgresql":
            search_query = f"PostgreSQL {software_name} {version or ''} end of life EOL support policy official".strip()
        elif technology_context.lower() == "redhat":
            search_query = f"Red Hat {software_name} {version or ''} end of life EOL support lifecycle official".strip()
        elif technology_context.lower() == "vmware":
            search_query = f"VMware {software_name} {version or ''} end of life EOL support lifecycle official".strip()
        elif technology_context.lower() == "apache":
            search_query = f"Apache {software_name} {version or ''} end of life EOL support dates official".strip()
        else:
            search_query = f"{software_name} {version or ''} end of life EOL support dates official".strip()
        
        return search_query
    
    def _build_task_message(self, software_name: str, version: str, search_query: str) -> str:
        """Build task message for WebSurfer"""
        task_message = f"""Search for official end-of-life (EOL) and support lifecycle information for {software_name}"""
        if version:
            task_message += f" version {version}"
        task_message += f""". 

FOCUS ON FINDING:
1. Exact end-of-life dates (when support completely stops)
2. End of mainstream support dates  
3. End of extended support dates
4. Official vendor documentation or announcements
5. Support lifecycle timelines

SEARCH STRATEGY:
- Look for official vendor docs, official announcements, or lifecycle pages
- Find specific dates in YYYY-MM-DD format
- Prioritize official vendor sources over third-party sites

Search query: {search_query}"""
        return task_message
    
    def _is_error_response(self, search_results: str) -> bool:
        """Check if WebSurfer response contains error indicators"""
        if not search_results:
            return False
        
        logger.info(f"🔍 WebSurfer response content: {search_results}")

        error_indicators = [
            "Web surfing error:",
            "Traceback (most recent call last):",
            "Error:",
            "_multimodal_web_surfer.py",
            "ERR_CONNECTION_CLOSED",
            "Page.goto:",
            "playwright._impl._errors.Error",
            "asyncio.exceptions.CancelledError",
            "screenshot()",
            "_page.screenshot()",
            "playwright._impl._page.py",
            "_openai_client.py",
            "openai/resources/chat/completions.py",
            "_base_client.py",
            "anyio/to_thread.py",
            "_generate_reply"
        ]
        
        return any(indicator in search_results for indicator in error_indicators)
    
    async def _try_alternative_searches(self, software_name: str, version: str, current_eol_data: Dict[str, Any]) -> Dict[str, Any]:
        """Try alternative search strategies if initial search was insufficient"""
        alternative_queries = [
            f"{software_name} {version or ''} support lifecycle vendor docs",
            f"{software_name} {version or ''} end of support extended mainstream",
            f"vendor {software_name} {version or ''} retirement schedule",
            f"{software_name} {version or ''} discontinuation announcement"
        ]
        
        for alt_query in alternative_queries:
            try:
                logger.info(f"🔍 Trying alternative search: {alt_query}")
                
                # Use the consolidated search method for consistency
                alt_search_results = await self._execute_websurfer_search(alt_query, software_name, version)
                
                if not alt_search_results:
                    logger.warning(f"⚠️ Alternative search returned no results, skipping")
                    continue
                
                logger.info(f"🔍 Alternative search returned {len(alt_search_results)} characters")
                alt_eol_data = self.parse_websurfer_results(alt_search_results, software_name, version)
                
                # If this alternative search gives better results, use it
                if alt_eol_data.get("confidence", 0) > current_eol_data.get("confidence", 0):
                    logger.info(f"🔍 Alternative search provided better results (confidence: {alt_eol_data.get('confidence', 0)})")
                    return alt_eol_data
                    
                # Brief pause between searches
                await asyncio.sleep(1)
                
            except Exception as alt_error:
                logger.warning(f"🔍 Alternative search failed: {alt_error}")
                continue
        
        return current_eol_data
    
    def parse_websurfer_results(self, search_results: str, software_name: str, version: str = None) -> Dict[str, Any]:
        """Parse EOL information from WebSurfer search results with enhanced extraction"""
        # Initialize default values
        eol_data = {
            "eol_date": "Unknown",
            "support_end_date": "Unknown",
            "status": "Unknown",
            "risk_level": "Unknown",
            "confidence": 0.5,
            "source_url": ""
        }
        
        if not search_results:
            logger.info("🔍 [DEBUG] No search results to parse")
            return eol_data
        
        logger.info(f"🔍 [DEBUG] Parsing WebSurfer results for {software_name} {version or ''}")
        
        # Extract URLs from search results
        url_matches = re.findall(r'https?://[^\s<>"]+', search_results)
        if url_matches:
            # Filter URLs to prefer official documentation sources
            preferred_domains = [
                'microsoft.com', 'docs.microsoft.com', 'learn.microsoft.com',
                'ubuntu.com', 'canonical.com',
                'redhat.com', 'access.redhat.com',
                'oracle.com', 'java.com',
                'vmware.com', 'lifecycle.vmware.com',
                'apache.org', 'archive.apache.org',
                'nodejs.org', 'php.net', 'python.org', 'postgresql.org',
                'endoflife.date'
            ]
            
            # Try to find a preferred URL first
            preferred_url = None
            for url in url_matches:
                for domain in preferred_domains:
                    if domain in url.lower():
                        preferred_url = url
                        break
                if preferred_url:
                    break
            
            # Use preferred URL or first URL found
            eol_data["source_url"] = preferred_url or url_matches[0]
        
        # Enhanced date extraction patterns
        date_patterns = [
            r'(?:end of life|eol|discontinued|retire[ds]?|support end[s]?)[^.]*?(\d{4}[-/]\d{1,2}[-/]\d{1,2})',
            r'(\d{4}[-/]\d{1,2}[-/]\d{1,2})[^.]*?(?:end of life|eol|discontinued|support end)',
            r'(?:january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{1,2},?\s+(\d{4})',
            r'(\d{1,2})[/-](\d{1,2})[/-](\d{4})',
            r'(\d{4})[-/](\d{1,2})[-/](\d{1,2})'
        ]
        
        for pattern in date_patterns:
            matches = re.findall(pattern, search_results, re.IGNORECASE)
            if matches:
                if isinstance(matches[0], tuple):
                    # Handle tuple matches (month/day/year patterns)
                    if len(matches[0]) == 3:
                        eol_data["eol_date"] = f"{matches[0][2]}-{matches[0][0].zfill(2)}-{matches[0][1].zfill(2)}"
                    else:
                        eol_data["eol_date"] = matches[0][0]
                else:
                    eol_data["eol_date"] = matches[0]
                eol_data["confidence"] = 0.8
                break
        
        # Status determination
        if eol_data["eol_date"] != "Unknown":
            try:
                from datetime import datetime
                eol_date = datetime.strptime(eol_data["eol_date"], "%Y-%m-%d")
                current_date = datetime.now()
                
                if eol_date < current_date:
                    eol_data["status"] = "End of Life"
                    eol_data["risk_level"] = "Critical"
                elif (eol_date - current_date).days < 365:
                    eol_data["status"] = "Approaching EOL"
                    eol_data["risk_level"] = "High"
                else:
                    eol_data["status"] = "Supported"
                    eol_data["risk_level"] = "Low"
                    
                eol_data["support_end_date"] = eol_data["eol_date"]
                eol_data["confidence"] = min(0.9, eol_data["confidence"] + 0.1)
                
            except ValueError:
                logger.warning(f"Could not parse EOL date: {eol_data['eol_date']}")
        
        return eol_data

    def get_fallback_eol_info(self, software_name: str, version: str = None, technology_context: str = None) -> Dict[str, Any]:
        """Provide fallback EOL information when WebSurfer is not available"""
        
        # Comprehensive EOL knowledge base for common software
        eol_knowledge = {
            "windows server 2025": {
                "eol_date": "2034-11-14",
                "support_end_date": "2029-11-13", 
                "status": "Supported",
                "risk_level": "Low",
                "source_url": "https://learn.microsoft.com/en-us/lifecycle/products/windows-server-2025"
            },
            "windows server 2022": {
                "eol_date": "2031-10-14",
                "support_end_date": "2026-10-13", 
                "status": "Supported",
                "risk_level": "Low",
                "source_url": "https://docs.microsoft.com/en-us/lifecycle/products/windows-server-2022"
            },
            "windows server 2019": {
                "eol_date": "2029-01-09",
                "support_end_date": "2024-01-09", 
                "status": "Extended Support",
                "risk_level": "Medium",
                "source_url": "https://docs.microsoft.com/en-us/lifecycle/products/windows-server-2019"
            },
            "windows server 2016": {
                "eol_date": "2027-01-12",
                "support_end_date": "2027-01-12", 
                "status": "Supported",
                "risk_level": "Medium",
                "source_url": "https://docs.microsoft.com/en-us/lifecycle/products/windows-server-2016"
            },
            "windows server 2012 r2": {
                "eol_date": "2023-10-10",
                "support_end_date": "2018-10-09",
                "status": "Unsupported",
                "risk_level": "Critical",
                "source_url": "https://docs.microsoft.com/en-us/lifecycle/products/windows-server-2012-r2"
            },
            "windows server 2012": {
                "eol_date": "2023-10-10",
                "support_end_date": "2023-10-10",
                "status": "End of Life",
                "risk_level": "Critical",
                "source_url": "https://docs.microsoft.com/en-us/lifecycle/products/windows-server-2012"
            },
            "windows server 2008 r2": {
                "eol_date": "2020-01-14",
                "support_end_date": "2013-01-14",
                "status": "Unsupported",
                "risk_level": "Critical",
                "source_url": "https://docs.microsoft.com/en-us/lifecycle/products/windows-server-2008-r2"
            },
            "windows server 2008": {
                "eol_date": "2020-01-14",
                "support_end_date": "2013-01-14",
                "status": "Unsupported",
                "risk_level": "Critical",
                "source_url": "https://docs.microsoft.com/en-us/lifecycle/products/windows-server-2008"
            },
            "windows 10": {
                "eol_date": "2025-10-14",
                "support_end_date": "2025-10-14",
                "status": "Approaching EOL",
                "risk_level": "High",
                "source_url": "https://docs.microsoft.com/en-us/lifecycle/products/windows-10-enterprise-and-education"
            },
            "ubuntu 18.04": {
                "eol_date": "2028-04-01",
                "support_end_date": "2028-04-01",
                "status": "LTS Supported",
                "risk_level": "Low",
                "source_url": "https://ubuntu.com/about/release-cycle"
            },
            "ubuntu 20.04": {
                "eol_date": "2030-04-01",
                "support_end_date": "2030-04-01",
                "status": "LTS Supported",
                "risk_level": "Low",
                "source_url": "https://ubuntu.com/about/release-cycle"
            },
            "ubuntu 22.04": {
                "eol_date": "2032-04-01",
                "support_end_date": "2032-04-01",
                "status": "LTS Supported",
                "risk_level": "Low",
                "source_url": "https://ubuntu.com/about/release-cycle"
            },
            "python 3.8": {
                "eol_date": "2024-10-14",
                "support_end_date": "2024-10-14",
                "status": "End of Life",
                "risk_level": "Critical",
                "source_url": "https://devguide.python.org/versions/"
            },
            "python 3.9": {
                "eol_date": "2025-10-05",
                "support_end_date": "2025-10-05",
                "status": "Approaching EOL",
                "risk_level": "High",
                "source_url": "https://devguide.python.org/versions/"
            },
            "python 3.10": {
                "eol_date": "2026-10-04",
                "support_end_date": "2026-10-04",
                "status": "Supported",
                "risk_level": "Low",
                "source_url": "https://devguide.python.org/versions/"
            },
            "python 3.11": {
                "eol_date": "2027-10-24",
                "support_end_date": "2027-10-24",
                "status": "Supported",
                "risk_level": "Low",
                "source_url": "https://devguide.python.org/versions/"
            }
        }
        
        # Try to match software name with improved matching logic
        lookup_key = f"{software_name.lower()} {version or ''}".strip()
        
        # First try exact match
        if lookup_key in eol_knowledge:
            info = eol_knowledge[lookup_key]
            logger.info(f"✅ Found exact static EOL data for {software_name} {version or ''}")
            return {
                "success": True,
                "data": {
                    "software_name": software_name,
                    "version": version or "Unknown",
                    "eol_date": info["eol_date"],
                    "support_end_date": info["support_end_date"],
                    "status": info["status"],
                    "risk_level": info["risk_level"],
                    "confidence": 0.9,
                    "source_url": info["source_url"],
                    "raw_results": f"Fallback information for {software_name} (WebSurfer unavailable)"
                }
            }
        
        # Then try partial matches, prioritizing longer matches
        best_match = None
        best_score = 0
        
        for known_software, info in eol_knowledge.items():
            # Check if the known software key is contained in the lookup key
            if known_software in lookup_key:
                # Score based on how much of the lookup key is matched
                score = len(known_software) / len(lookup_key)
                if score > best_score:
                    best_score = score
                    best_match = (known_software, info)
            # Also check reverse - if lookup key is contained in known software
            elif lookup_key in known_software:
                score = len(lookup_key) / len(known_software)
                if score > best_score:
                    best_score = score
                    best_match = (known_software, info)
        
        if best_match:
            known_software, info = best_match
            logger.info(f"✅ Found partial static EOL data for {software_name} (matched: {known_software})")
            return {
                "success": True,
                "data": {
                    "software_name": software_name,
                    "version": version or "Unknown",
                    "eol_date": info["eol_date"],
                    "support_end_date": info["support_end_date"],
                    "status": info["status"],
                    "risk_level": info["risk_level"],
                    "confidence": 0.8,
                    "source_url": info["source_url"],
                    "raw_results": f"Fallback information for {software_name} (WebSurfer unavailable)"
                }
            }
        
        # Generic fallback if no specific knowledge available
        fallback_result = {
            "success": True,
            "data": {
                "software_name": software_name,
                "version": version or "Unknown",
                "eol_date": "Please check vendor documentation",
                "support_end_date": "Please check vendor documentation",
                "status": "Unknown - WebSurfer Required",
                "risk_level": "Unknown",
                "confidence": 0.3,
                "source_url": "",
                "raw_results": f"WebSurfer not available for real-time search. Please check official vendor documentation for {software_name} EOL information."
            }
        }
        
        # Debug logging for fallback source URL
        logger.info(f"🔗 [CITATION DEBUG] WebSurfer fallback source URL: '{fallback_result['data']['source_url']}'")
        logger.warning(f"⚠️ [CITATION] Using generic fallback with empty source URL for: {software_name} {version or ''}")
        
        return fallback_result

    def _is_container_environment(self) -> bool:
        """Check if running in a container environment"""
        import os
        return bool(os.getenv('CONTAINER_MODE') or os.getenv('WEBSITE_SITE_NAME') or os.getenv('KUBERNETES_SERVICE_HOST'))

    def _has_container_browser_issues(self, content: str) -> bool:
        """Check for container-specific browser issues"""
        container_issues = [
            "No sandbox helpers in place",
            "Unable to launch browser",
            "DevToolsActivePort file doesn't exist",
            "Chrome failed to start",
            "Browser process crashed",
            "Failed to launch the browser process"
        ]
        return any(issue in content for issue in container_issues)

    def _is_browser_related_error(self, error_str: str) -> bool:
        """Check if error is related to browser/Playwright issues"""
        browser_error_indicators = [
            "web surfing error",
            "playwright",
            "browser",
            "chromium", 
            "devtools",
            "screenshot",
            "page.goto",
            "connection closed",
            "timeout waiting for",
            "browser process"
        ]
        error_lower = error_str.lower()
        return any(indicator in error_lower for indicator in browser_error_indicators)