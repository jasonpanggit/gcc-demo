"""
Chat Orchestrator for Multi-Agent Conversations using Magentic-One
Enables dynamic agent-to-agent conversations with full transparency for chat.html interface
Updated for Magentic-One multi-agent system
"""
import os
import sys
import asyncio
import json
import time
import concurrent.futures
import re
import traceback
from typing import Dict, List, Any, Optional, Callable, Sequence, Tuple
from datetime import datetime
import uuid
from collections import defaultdict

# Initialize module-level logger early so top-level import diagnostics can use structured logging
try:
    from utils import get_logger
    from utils.cache_stats_manager import cache_stats_manager
    logger = get_logger(__name__)
    
    # Force Azure App Service logging configuration if detected
    if os.environ.get('WEBSITE_SITE_NAME'):
        import logging
        import sys
        # Check if Azure handler already exists to prevent duplicates
        azure_handler_exists = any(
            isinstance(handler, logging.StreamHandler) and 
            handler.stream == sys.stderr 
            for handler in logger.handlers
        )
        
        if not azure_handler_exists:
            azure_handler = logging.StreamHandler(sys.stderr)
            azure_formatter = logging.Formatter(
                '[%(asctime)s] %(levelname)s in %(module)s: %(message)s'
            )
            azure_handler.setFormatter(azure_formatter)
            azure_handler.setLevel(logging.INFO)
            logger.addHandler(azure_handler)
            logger.setLevel(logging.INFO)
            
        # ENABLE log propagation for Azure App Service to ensure logs appear
        logger.propagate = False
        
        # Suppress noisy AutoGen framework logging
        logging.getLogger('autogen_core').setLevel(logging.WARNING)
        logging.getLogger('autogen_core.events').setLevel(logging.ERROR)
        logging.getLogger('autogen_agentchat').setLevel(logging.WARNING)
        logging.getLogger('autogen_ext').setLevel(logging.WARNING)
        
except Exception:
    import logging
    logger = logging.getLogger(__name__)
    # Create dummy cache stats manager if not available
    class DummyCacheStatsManager:
        def record_agent_request(self, *args, **kwargs): 
            pass
    cache_stats_manager = DummyCacheStatsManager()
    
    # Suppress noisy AutoGen framework logging globally
    logging.getLogger('autogen_core').setLevel(logging.WARNING)
    logging.getLogger('autogen_core.events').setLevel(logging.ERROR)
    logging.getLogger('autogen_agentchat').setLevel(logging.WARNING)
    logging.getLogger('autogen_ext').setLevel(logging.WARNING)

# Magentic-One imports - Updated for new multi-agent system
try:
    # Magentic-One and AgentChat imports
    from autogen_agentchat.agents import AssistantAgent  # type: ignore
    from autogen_agentchat.teams import MagenticOneGroupChat  # type: ignore
    from autogen_agentchat.conditions import TextMentionTermination, MaxMessageTermination  # type: ignore
    from autogen_agentchat.messages import TextMessage, BaseChatMessage  # type: ignore
    from autogen_agentchat.base import Response  # type: ignore
    from autogen_agentchat.ui import Console  # type: ignore
    from autogen_core import CancellationToken  # type: ignore
    from autogen_ext.models.openai import AzureOpenAIChatCompletionClient  # type: ignore
    
    MAGENTIC_ONE_IMPORTS_OK = True
    magentic_one_version = "0.7.4"
    logger.info("✅ Magentic-One imports successful (WebSurfer functionality via WebsurferEOLAgent)")
except ImportError as e:
    logger.error(f"Magentic-One/WebSurfer import failed: {e}")
    # If imports fail, create dummy classes for graceful degradation
    class AssistantAgent:
        def __init__(self, *args, **kwargs):
            pass
        async def on_messages(self, *args, **kwargs):
            return "Magentic-One not available"
    class MagenticOneGroupChat:
        def __init__(self, *args, **kwargs):
            pass
        async def run(self, *args, **kwargs):
            return "I apologize, but the Magentic-One multi-agent system is not currently available. This may be due to missing dependencies or configuration issues. Please check with the system administrator or try using the standard EOL search functionality instead."
        async def run_stream(self, *args, **kwargs):
            # Return an async generator that yields the mock response
            async def mock_stream():
                yield "I apologize, but the Magentic-One multi-agent system is not currently available. This may be due to missing dependencies or configuration issues. Please check with the system administrator or try using the standard EOL search functionality instead."
            return mock_stream()
    class Console:
        def __init__(self, *args, **kwargs):
            pass
        async def run_stream(self, *args, **kwargs):
            # Return an async generator that yields the mock response
            async def mock_stream():
                yield "Magentic-One not available"
            return mock_stream()
    class TextMentionTermination:
        def __init__(self, *args, **kwargs):
            pass
    class MaxMessageTermination:
        def __init__(self, *args, **kwargs):
            pass
    class TextMessage:
        def __init__(self, content, source):
            self.content = content
            self.source = source
    class BaseChatMessage:
        def __init__(self, content, source):
            self.content = content
            self.source = source
    class Response:
        def __init__(self, messages=None):
            self.messages = messages or []
    class CancellationToken:
        pass
    class AzureOpenAIChatCompletionClient:
        def __init__(self, *args, **kwargs):
            pass
        
        async def create(self, messages):
            """Mock implementation for when Magentic-One is not available"""
            from types import SimpleNamespace
            
            # Create a mock response that mimics the real response structure
            # but with empty content to trigger fallback logic
            mock_message = SimpleNamespace(content="")
            mock_choice = SimpleNamespace(message=mock_message)
            mock_response = SimpleNamespace(
                choices=[mock_choice],
                content=""  # Also add direct content for backward compatibility
            )
            
            return mock_response
    MAGENTIC_ONE_IMPORTS_OK = False
    magentic_one_version = "unavailable"

# Import agent implementations
# Import traditional agent classes for direct EOL agent calls
from .base_eol_agent import BaseEOLAgent
from .endoflife_agent import EndOfLifeAgent
from .microsoft_agent import MicrosoftEOLAgent
from .ubuntu_agent import UbuntuEOLAgent
from .redhat_agent import RedHatEOLAgent
from .oracle_agent import OracleEOLAgent
from .vmware_agent import VMwareEOLAgent
from .apache_agent import ApacheEOLAgent
from .nodejs_agent import NodeJSEOLAgent
from .postgresql_agent import PostgreSQLEOLAgent
from .php_agent import PHPEOLAgent
from .python_agent import PythonEOLAgent
from .websurfer_agent import WebsurferEOLAgent
from .playwright_agent import PlaywrightEOLAgent
from .azure_ai_agent import AzureAIAgentEOLAgent  # Modern Azure AI Agent Service
# from .openai_agent import OpenAIAgent

class MagenticOneChatOrchestrator:
    """
    Magentic-One based orchestrator that enables natural multi-agent conversations
    for inventory management and EOL analysis with built-in planning and coordination
    Updated for Magentic-One multi-agent system
    """
    
    # Class constants for keyword matching optimization
    SEARCH_KEYWORDS = ["search", "look up", "find", "check", "research", "investigate"]
    INTERNET_KEYWORDS = ["on the internet", "online", "web search", "google", "search engine", "web", "internet", "azure ai search"]
    EOL_KEYWORDS = ["eol", "end of life", "support end", "lifecycle", "end-of-life"]
    WEB_SEARCH_PHRASES = ["search the web for", "google for", "web search for", "look online for", "find on internet", "azure ai search"]
    SEARCH_LOOKUP_KEYWORDS = ["search", "google", "web search", "look up online", "azure ai"]
    EOL_DATE_KEYWORDS = ["eol date", "end of life date", "support end date", "lifecycle information"]
    
    OS_INVENTORY_KEYWORDS = ["os inventory", "operating system", "what os", "list os", "discover os", "platform"]
    SOFTWARE_INVENTORY_KEYWORDS = ["software inventory", "what software", "list software", "installed software", "applications", "packages"]
    GENERAL_INVENTORY_KEYWORDS = ["inventory", "what do i have", "discover", "scan", "list all"]
    INVENTORY_EOL_KEYWORDS = ["os inventory", "software inventory"]
    
    MICROSOFT_KEYWORDS = ["windows", "microsoft", "office", "exchange", "sql server"]
    LINUX_KEYWORDS = ["ubuntu", "linux", "debian", "centos", "rhel"]
    PYTHON_KEYWORDS = ["python", "django", "flask", "pip"]
    NODEJS_KEYWORDS = ["nodejs", "node.js", "npm", "javascript", "node"]
    ORACLE_KEYWORDS = ["oracle", "java", "mysql", "virtualbox"]
    PHP_KEYWORDS = ["php", "composer", "laravel", "symfony"]
    POSTGRESQL_KEYWORDS = ["postgresql", "postgres", "postgis"]
    REDHAT_KEYWORDS = ["redhat", "rhel", "centos", "fedora"]
    VMWARE_KEYWORDS = ["vmware", "vsphere", "esxi", "vcenter"]
    APACHE_KEYWORDS = ["apache", "httpd", "tomcat", "maven"]
    
    ALL_TECH_KEYWORDS = ["windows", "ubuntu", "python", "nodejs", "oracle", "php", "postgresql", "redhat", "vmware", "apache"]
    
    def __init__(self):
        # Enhanced debug info for visibility
        logger.info(f"MagenticOneChatOrchestrator.__init__: MAGENTIC_ONE_IMPORTS_OK={MAGENTIC_ONE_IMPORTS_OK}")
        
        # Force immediate logging for Azure App Service visibility
        if os.environ.get('WEBSITE_SITE_NAME'):
            print(f"[Azure App Service] MagenticOneChatOrchestrator initialization starting...", file=sys.stderr, flush=True)
        
        try:
            self.session_id = str(uuid.uuid4())
            self.conversation_history = []
            self.agent_communications = []
            
            # EOL Response Tracking - Track all agent responses for detailed history
            self.eol_agent_responses = []
            
            self.agent_name = "magentic_one_orchestrator"
            
            # Initialize comprehensive logging structures
            self._init_orchestrator_logging()
            
            # Simple in-memory cache (session scoped) to avoid redundant expensive calls
            # Keys: (request_type, days, limit)
            self._inventory_cache: Dict[Tuple[str, int, int], Dict[str, Any]] = {}
            self._inventory_cache_timestamp: Dict[Tuple[str, int, int], float] = {}
            self._cache_ttl_seconds = 180  # 3 minutes for rapid follow-up queries
            
            # Persistent Playwright browser for performance optimization
            # self._playwright = None
            # self._browser = None
            # self._browser_context = None
            # self._browser_lock = asyncio.Lock()  # Thread-safe browser access
            
            self._log_orchestrator_event("orchestrator_init_start", {
                "session_id": self.session_id,
                "magentic_one_available": MAGENTIC_ONE_IMPORTS_OK,
                "version": magentic_one_version
            })
            
            # LEGACY: Traditional agent initialization commented out for Magentic-One only mode
            # Initialize traditional agent implementations for tool access
            # self._init_traditional_agents()
            
            # Azure OpenAI model client for Magentic-One with rate limiting protection
            if MAGENTIC_ONE_IMPORTS_OK:
                logger.info(f"✅ Magentic-One imports successful - initializing AzureOpenAI client")
                # Force Azure App Service visibility
                if os.environ.get('WEBSITE_SITE_NAME'):
                    print(f"[Azure App Service] Starting AzureOpenAI client initialization...", file=sys.stderr, flush=True)
                
                self._log_orchestrator_event("model_client_init_start", {
                    "azure_endpoint": os.getenv('AZURE_OPENAI_ENDPOINT', 'not_set'),
                    "deployment": os.getenv("AZURE_OPENAI_DEPLOYMENT", )
                })
                
                self.model_client = AzureOpenAIChatCompletionClient(
                    azure_deployment=os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o-mini"),
                    azure_endpoint=os.getenv('AZURE_OPENAI_ENDPOINT'),
                    model=os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o-mini"),
                    api_version="2024-08-01-preview",  # Updated for Magentic-One compatibility
                    temperature=0.1,
                    timeout=60,  # Reduced timeout for faster responses
                    max_retries=3,  # Reduced retries for faster failure recovery
                )
                logger.info(f"✅ AzureOpenAI client initialized successfully")
                self._log_orchestrator_event("model_client_init_success", {
                    "temperature": 0.1,
                    "timeout": 60,
                    "max_retries": 5
                })
                
                # Initialize WebSurfer agent via dedicated WebsurferEOLAgent class 
                # (WebsurferEOLAgent will handle all WebSurfer functionality including error handling)
                logger.info("🌐 WebSurfer functionality available via WebsurferEOLAgent class")
                
                # Mark Magentic-One components as initialized
                self._magentic_one_initialized = True
                
                logger.info("✅ Model client initialized successfully - web surfing enabled with fallback capabilities")
            else:
                logger.warning("⚠️ Magentic-One not available - using fallback functionality")
                self.model_client = None
                # WebSurfer functionality available via WebsurferEOLAgent (with fallback capabilities)
                self._log_orchestrator_event("model_client_init_fallback", {
                    "reason": "magentic_one_not_available"
                })
            
            # Setup Magentic-One specialized agents
            self._setup_magentic_one_agents()
            
            # Setup Magentic-One team
            self._setup_magentic_one_team()
            
            logger.info(f"✅ MagenticOneChatOrchestrator initialized with session_id: {self.session_id}")
            
            # Enhanced orchestrator initialization logging with strategic decisions
            agent_count = len([a for a in [
                getattr(self, 'os_inventory_specialist', None),
                getattr(self, 'software_inventory_specialist', None),
                getattr(self, 'microsoft_eol_specialist', None),
                getattr(self, 'ubuntu_eol_specialist', None)
            ] if a is not None])
            
            self._log_orchestrator_event("orchestrator_init_complete", {
                "session_id": self.session_id,
                "initialization_time": time.time() - self.init_start_time,
                "agents_initialized": agent_count,
                "team_ready": self.team is not None,
                "orchestrator_capabilities": {
                    "adaptive_planning": True,
                    "specialist_coordination": True,
                    "web_search_integration": True,
                    "citation_tracking": True,
                    "decision_transparency": True
                },
                "strategic_configuration": {
                    "approach": "multi_agent_specialist_coordination",
                    "quality_priority": "high_accuracy_with_citations",
                    "performance_balance": "optimized_for_comprehensive_analysis",
                    "fallback_strategy": "graceful_degradation_with_direct_tools"
                }
            })
            
            # Log orchestrator strategic planning capabilities (without agent selection analysis during init)
            self._log_orchestrator_event("orchestrator_capabilities_assessment", {
                "planning_capabilities": {
                    "task_decomposition": "advanced",
                    "agent_selection": "intelligent_routing",
                    "resource_management": "dynamic_allocation",
                    "quality_assurance": "multi_level_validation"
                },
                "decision_making_features": {
                    "decision_tree_generation": True,
                    "alternative_plan_creation": True,
                    "risk_assessment": True,
                    "performance_optimization": True
                },
                "coordination_strategies": {
                    "sequential_execution": "for_complex_workflows",
                    "parallel_execution": "for_independent_tasks",
                    "adaptive_routing": "based_on_query_analysis",
                    "fallback_mechanisms": "multiple_layers_available"
                }
            })
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize MagenticOneChatOrchestrator: {e}")
            self._log_orchestrator_event("orchestrator_init_error", {
                "error": str(e),
                "traceback": traceback.format_exc()
            })
            self.model_client = None
            raise
            
    def _ensure_magentic_one_initialized(self):
        """
        Lazy initialization of Magentic-One components only when needed
        """
        if not self._magentic_one_initialized and MAGENTIC_ONE_IMPORTS_OK:
            logger.info("🔧 Lazy loading Magentic-One components...")
            
            # Initialize Azure OpenAI client
            try:
                # Import Azure credential here to avoid import overhead during startup
                from azure.identity import DefaultAzureCredential
                
                credential = DefaultAzureCredential()
                token = credential.get_token("https://cognitiveservices.azure.com/.default")
                
                self.model_client = AzureOpenAIChatCompletionClient(
                    azure_deployment="gpt-4o-mini",
                    azure_endpoint=os.getenv('AZURE_OPENAI_ENDPOINT'),
                    model="gpt-4o-mini",
                    api_version="2024-08-01-preview",
                    temperature=0.1,
                    timeout=60,
                    max_retries=3,
                )
                
                # Setup Magentic-One team
                self._setup_magentic_one_agents()
                self._setup_magentic_one_team()
                
                self._magentic_one_initialized = True
                logger.info("✅ Magentic-One components lazy loaded successfully")
                
            except Exception as e:
                logger.error(f"❌ Failed to lazy load Magentic-One: {e}")
                self.model_client = None
                self.team = None
    
    # async def _get_playwright_browser(self):
    #     """
    #     Get or create a persistent Playwright browser instance.
    #     Thread-safe with async lock to prevent concurrent initialization.
    #     """
    #     async with self._browser_lock:
    #         if self._browser is None or not self._browser.is_connected():
    #             try:
    #                 logger.info("🌐 Initializing persistent Playwright browser...")
    #                 from playwright.async_api import async_playwright
                    
    #                 if self._playwright is None:
    #                     self._playwright = await async_playwright().start()
                    
    #                 self._browser = await self._playwright.chromium.launch(
    #                     headless=True,
    #                     args=[
    #                         '--no-sandbox',
    #                         '--disable-setuid-sandbox',
    #                         '--disable-dev-shm-usage',
    #                         '--single-process',
    #                         '--disable-gpu'
    #                     ]
    #                 )
                    
    #                 self._browser_context = await self._browser.new_context(
    #                     viewport={'width': 1280, 'height': 1024},
    #                     user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    #                 )
                    
    #                 logger.info("✅ Playwright browser initialized and ready for reuse")
    #             except Exception as e:
    #                 logger.error(f"❌ Failed to initialize Playwright browser: {e}")
    #                 raise
            
    #         return self._browser, self._browser_context
    
    # async def _close_playwright_browser(self):
    #     """Close the persistent Playwright browser instance gracefully."""
    #     async with self._browser_lock:
    #         try:
    #             if self._browser_context:
    #                 await self._browser_context.close()
    #                 self._browser_context = None
                    
    #             if self._browser:
    #                 await self._browser.close()
    #                 self._browser = None
                    
    #             if self._playwright:
    #                 await self._playwright.stop()
    #                 self._playwright = None
                    
    #             logger.info("✅ Playwright browser closed successfully")
    #         except Exception as e:
    #             logger.error(f"❌ Error closing Playwright browser: {e}")
    
    def _log_orchestrator_event(self, event_type: str, event_data: Dict[str, Any]):
        """Log orchestrator behavior events with structured data"""
        # Use helper method to create standardized log entry
        event_log = self._create_log_entry(
            "orchestrator_event",
            event_type=event_type,
            event_data=event_data
        )
        
        self.orchestrator_logs.append(event_log)
        
        # Log to standard logger with performance optimization
        # Only log critical events or if debug mode is explicitly enabled
        critical_events = {
            'chat_session_start', 'chat_session_complete', 'chat_with_confirmation_complete',
            'team_initialization_complete', 'magentic_one_team_ready', 'fallback_to_direct_response',
            'chat_session_failure', 'chat_with_confirmation_failure', 'orchestrator_init_start',
            'orchestrator_init_complete', 'model_client_init_start', 'model_client_init_success',
            'model_client_init_error', 'websurfer_init_success', 'websurfer_init_error'
        }
        
        # For Azure App Service, also log initialization events as INFO
        is_azure_app_service = os.environ.get('WEBSITE_SITE_NAME') is not None
        
        if event_type in critical_events or is_azure_app_service:
            # Show more meaningful information based on the event type and available data
            if 'classified_as' in event_data:
                # Map query classification to appropriate task types for better logging
                query_class = event_data['classified_as']
                task_type = event_data.get('task_type', 'unknown')
                
                # Provide meaningful task type based on query classification if not explicitly set
                if task_type == 'unknown' and query_class:
                    if query_class == 'direct_eol':
                        task_type = 'EOL_ONLY'
                    elif query_class == 'internet_eol':
                        task_type = 'INTERNET_EOL'
                    elif query_class in ['os_inventory', 'software_inventory']:
                        task_type = 'INVENTORY_ONLY'
                    elif 'eol_grounded' in query_class:
                        task_type = 'MIXED_INVENTORY_EOL'
                    elif query_class == 'general_eol_grounded':
                        task_type = 'MIXED_INVENTORY_EOL'
                
                identifier = f"{query_class} -> {task_type}"
            elif 'session_id' in event_data:
                identifier = event_data['session_id']
            elif 'conversation_id' in event_data:
                identifier = event_data['conversation_id']
            elif 'step' in event_data:
                identifier = event_data['step']
            elif 'initialization_time' in event_data:
                identifier = f"{event_data['initialization_time']:.3f}s"
            elif 'agents_initialized' in event_data:
                identifier = f"{event_data['agents_initialized']} agents"
            elif 'message_preview' in event_data:
                identifier = f"'{event_data['message_preview'][:50]}...'"
            elif 'timeout_seconds' in event_data:
                identifier = f"{event_data['timeout_seconds']}s timeout"
            else:
                # Only show N/A for events that truly have no meaningful data
                identifier = "N/A"
            
            logger.info(f"🎛️ [{event_type}]: {identifier}")
        elif os.getenv('DEBUG_MODE', '').lower() == 'true':
            logger.debug(f"🎛️ ORCHESTRATOR_EVENT [{event_type}]: {json.dumps(event_data, default=str)}")
        
        # Record to cache stats manager if available
        if hasattr(cache_stats_manager, 'record_orchestrator_event'):
            cache_stats_manager.record_orchestrator_event(event_type, event_data)
    
    def _log_agent_interaction(self, agent_name: str, action: str, data: Dict[str, Any]):
        """Log agent interactions and decisions with enhanced web search tracking"""
        # Use helper method to create standardized log entry
        interaction_log = self._create_log_entry(
            "agent_interaction",
            agent_name=agent_name,
            action=action,
            data=data
        )
        
        self.agent_interaction_logs.append(interaction_log)
        self.agent_usage_stats[agent_name] += 1
        
        # Enhanced logging for web search activities
        if "web_search" in action.lower() or "websurfer" in action.lower():
            web_search_log = {
                "timestamp": interaction_log["timestamp"],
                "agent": agent_name,
                "search_query": data.get("search_query", ""),
                "search_time": data.get("search_time", 0),
                "citations": self._extract_citations_from_data(data),
                "response_length": data.get("response_length", 0)
            }
            
            # Store web search specific logs
            if not hasattr(self, 'web_search_logs'):
                self.web_search_logs = []
            self.web_search_logs.append(web_search_log)
            
            # Performance optimized logging for web search
            if os.getenv('DEBUG_MODE', '').lower() == 'true':
                logger.debug(f"🔍 WEB_SEARCH [{agent_name}]: {data.get('search_query', '')} -> {data.get('response_length', 0)} chars")
        
        # Performance optimization: Only log agent interactions in debug mode
        is_azure_app_service = os.environ.get('WEBSITE_SITE_NAME') is not None
        
        if os.getenv('DEBUG_MODE', '').lower() == 'true':
            logger.debug(f"🤖 AGENT_INTERACTION [{agent_name}] {action}: {json.dumps(data, default=str)}")
        elif is_azure_app_service and action in ['initialization', 'start', 'complete', 'error', 'failure']:
            # For Azure App Service, always log critical agent actions
            logger.info(f"🤖 {agent_name}: {action}")
        else:
            # Simplified logging for non-critical actions
            logger.info(f"🤖 {agent_name}: {action}")
    
    def _extract_citations_from_data(self, data: Dict[str, Any]) -> List[Dict[str, str]]:
        """Extract citation information from agent interaction data"""
        citations = []
        
        # Look for common citation patterns in the data
        response_content = data.get("response_content", "")
        if isinstance(response_content, str):
            # Extract URLs from response content
            import re
            url_pattern = r'https?://[^\s<>"\'`|]+[^\s<>"\'`|,.]'
            urls = re.findall(url_pattern, response_content)
            
            # Filter and prioritize official sources
            official_domains = [
                'microsoft.com', 'docs.microsoft.com', 'learn.microsoft.com',
                'ubuntu.com', 'canonical.com', 'wiki.ubuntu.com',
                'redhat.com', 'access.redhat.com',
                'oracle.com', 'java.com',
                'vmware.com', 'lifecycle.vmware.com',
                'apache.org', 'archive.apache.org',
                'nodejs.org', 'php.net', 'python.org', 'postgresql.org',
                'endoflife.date'
            ]
            
            for url in urls:
                citation_type = "web_source"
                citation_title = "Web Source"
                
                # Classify the citation type based on domain
                for domain in official_domains:
                    if domain in url.lower():
                        if 'microsoft' in domain:
                            citation_type = "microsoft_official"
                            citation_title = "Microsoft Official Documentation"
                        elif 'ubuntu' in domain or 'canonical' in domain:
                            citation_type = "ubuntu_official"
                            citation_title = "Ubuntu Official Documentation"
                        elif 'redhat' in domain:
                            citation_type = "redhat_official"
                            citation_title = "Red Hat Official Documentation"
                        elif 'oracle' in domain or 'java' in domain:
                            citation_type = "oracle_official"
                            citation_title = "Oracle Official Documentation"
                        elif 'vmware' in domain:
                            citation_type = "vmware_official"
                            citation_title = "VMware Official Documentation"
                        elif 'apache' in domain:
                            citation_type = "apache_official"
                            citation_title = "Apache Foundation Documentation"
                        elif 'endoflife.date' in domain:
                            citation_type = "endoflife_database"
                            citation_title = "EndOfLife.date Database"
                        else:
                            citation_type = "official_vendor"
                            citation_title = "Official Vendor Documentation"
                        break
                
                citations.append({
                    "url": url,
                    "type": citation_type,
                    "title": citation_title,
                    "extracted_at": datetime.now().isoformat()
                })
        
        # Check for source URLs in structured data
        if data.get("eol_data", {}).get("data", {}).get("source_url"):
            source_url = data["eol_data"]["data"]["source_url"]
            # Use set for O(1) lookup instead of O(n) list comprehension
            existing_urls = {c.get("url") for c in citations if c.get("url")}
            if source_url and source_url not in existing_urls:
                citations.append({
                    "url": source_url,
                    "type": "structured_source",
                    "title": "Primary EOL Data Source",
                    "extracted_at": datetime.now().isoformat()
                })
        
        # Add search query as citation context
        if data.get("search_query"):
            citations.append({
                "search_query": data.get("search_query"),
                "search_method": "WebSurfer",
                "type": "search_context",
                "title": "Search Query Context",
                "extracted_at": datetime.now().isoformat()
            })
        
        # Log citation extraction results
        logger.info(f"🔗 [CITATION] Extracted {len(citations)} citations from agent data")
        for i, citation in enumerate(citations):
            if citation.get("url"):
                logger.info(f"🔗 [CITATION {i+1}] {citation.get('title', 'Unknown')}: {citation['url']}")
            elif citation.get("search_query"):
                logger.info(f"🔗 [CITATION {i+1}] Search Query: {citation['search_query']}")
        
        return citations
    
    def _make_url_clickable(self, text: str) -> str:
        """
        Convert URLs in text to clickable HTML links
        
        Args:
            text: Text that may contain URLs
            
        Returns:
            Text with URLs converted to clickable HTML links
        """
        import re
        
        # Pattern to match URLs
        url_pattern = r'(https?://[^\s\)]+)'
        
        def replace_url(match):
            url = match.group(1)
            # Remove trailing punctuation that shouldn't be part of the URL
            url = re.sub(r'[.,;:!?]+$', '', url)
            return f'<a href="{url}" target="_blank" rel="noopener noreferrer">{url}</a>'
        
        return re.sub(url_pattern, replace_url, text)
    
    def _log_task_planning(self, planning_stage: str, planning_data: Dict[str, Any]):
        """Log task planning and orchestration decisions with detailed reasoning"""
        # Add orchestrator decision-making context, but skip agent analysis for non-task stages
        orchestrator_context = {}
        
        try:
            # Only generate detailed orchestrator reasoning for actual task planning stages
            if planning_stage in ["task_initiation", "agent_coordination", "task_execution_complete"]:
                orchestrator_context = {
                    "decision_tree": self._generate_decision_tree(planning_stage, planning_data),
                    "agent_selection_reasoning": self._generate_agent_selection_reasoning(planning_data),
                    "strategic_approach": self._determine_strategic_approach(planning_data),
                    "expected_workflow": self._predict_workflow_steps(planning_data)
                }
            else:
                # For capability assessments and initialization stages, use minimal context
                orchestrator_context = {
                    "planning_stage_type": "system_assessment",
                    "requires_agent_analysis": False,
                    "context": "orchestrator_initialization_or_assessment"
                }
        except Exception as e:
            # Fallback to minimal context if analysis fails
            logger.warning(f"⚠️ Task planning context generation failed: {e}")
            orchestrator_context = {
                "error": str(e),
                "fallback_mode": True,
                "planning_stage": planning_stage
            }
        
        # Create standardized log entry with cached values
        planning_log = self._create_log_entry("planning", 
            planning_stage=planning_stage,
            planning_data=planning_data,
            orchestrator_reasoning=orchestrator_context
        )
        
        self.task_planning_logs.append(planning_log)
        
        # Also log as an agent communication for transparency
        self._log_agent_interaction("MagenticOneOrchestrator", f"planning_{planning_stage}", {
            "planning_stage": planning_stage,
            "orchestrator_decision": orchestrator_context,
            "task_context": planning_data
        })
        
        # Performance optimization: Reduce excessive logging
        if os.getenv('DEBUG_MODE', '').lower() == 'true':
            logger.debug(f"📋 TASK_PLANNING [{planning_stage}]: {json.dumps(planning_data, default=str)}")
            logger.debug(f"🧠 ORCHESTRATOR_REASONING: {json.dumps(orchestrator_context, default=str)}")
        else:
            # Simplified logging for performance
            logger.info(f"📋 TASK: {planning_stage}")
        
    def _generate_decision_tree(self, planning_stage: str, planning_data: Dict[str, Any]) -> Dict[str, Any]:
        """Generate decision tree showing orchestrator's reasoning process"""
        decision_tree = {
            "stage": planning_stage,
            "primary_decision": "",
            "decision_factors": [],
            "alternative_approaches": [],
            "selected_approach": "",
            "reasoning": ""
        }
        
        # Handle non-task stages gracefully
        if planning_stage not in ["task_initiation", "agent_coordination", "task_execution_complete"]:
            decision_tree.update({
                "primary_decision": f"System assessment for {planning_stage}",
                "decision_factors": ["System initialization", "Capability evaluation"],
                "selected_approach": "assessment_mode",
                "reasoning": f"Performing {planning_stage} without task-specific analysis"
            })
            return decision_tree
        
        if planning_stage == "task_initiation":
            task = planning_data.get("task", "")
            task_lower = task.lower()  # Cache the lowercase version to avoid repeated conversions
            
            # Priority check: Explicit internet search requests go directly to WebSurfer
            if (any(phrase in task_lower for phrase in self.SEARCH_KEYWORDS) and 
                any(phrase in task_lower for phrase in self.INTERNET_KEYWORDS) and 
                any(phrase in task_lower for phrase in self.EOL_KEYWORDS)) or \
               any(phrase in task_lower for phrase in self.WEB_SEARCH_PHRASES) or \
               (any(phrase in task_lower for phrase in self.SEARCH_LOOKUP_KEYWORDS) and 
                any(phrase in task_lower for phrase in self.EOL_DATE_KEYWORDS)):
                decision_tree.update({
                    "primary_decision": "Route directly to WebSurfer for internet-based EOL search",
                    "decision_factors": ["Internet search explicitly requested", "EOL information needed", "Web search optimal for real-time data"],
                    "alternative_approaches": ["Technology-specific specialist", "EndOfLife API", "Multiple specialist approach"],
                    "selected_approach": "WebSurfer comprehensive internet search",
                    "reasoning": "User explicitly requested internet search for EOL information; WebSurfer provides direct web search capabilities for real-time, comprehensive results"
                })
            # Analyze task type and route accordingly
            elif any(keyword in task_lower for keyword in self.OS_INVENTORY_KEYWORDS):
                decision_tree.update({
                    "primary_decision": "Execute OS inventory discovery",
                    "decision_factors": ["OS inventory keywords detected", "Need for system discovery", "Foundation for EOL analysis"],
                    "alternative_approaches": ["Direct EOL check without inventory", "Software inventory first", "Combined inventory approach"],
                    "selected_approach": "OS inventory specialist with optional EOL analysis",
                    "reasoning": "Task requires OS discovery as primary objective; route to OSInventoryAnalyst for platform discovery"
                })
            elif any(keyword in task_lower for keyword in self.SOFTWARE_INVENTORY_KEYWORDS):
                decision_tree.update({
                    "primary_decision": "Execute software inventory discovery",
                    "decision_factors": ["Software inventory keywords detected", "Application discovery needed", "Potential for bulk EOL analysis"],
                    "alternative_approaches": ["Direct EOL check without inventory", "OS inventory first", "Combined inventory approach"],
                    "selected_approach": "Software inventory specialist with optional EOL analysis",
                    "reasoning": "Task requires software discovery as primary objective; route to SoftwareInventoryAnalyst for application discovery"
                })
            elif any(keyword in task_lower for keyword in self.GENERAL_INVENTORY_KEYWORDS):
                decision_tree.update({
                    "primary_decision": "Execute comprehensive inventory discovery",
                    "decision_factors": ["General inventory keywords detected", "Comprehensive discovery needed", "Foundation for strategic analysis"],
                    "alternative_approaches": ["OS inventory only", "Software inventory only", "EOL analysis without inventory"],
                    "selected_approach": "Combined inventory with both OS and software specialists",
                    "reasoning": "Task requires broad asset discovery; use both OSInventoryAnalyst and SoftwareInventoryAnalyst for comprehensive coverage"
                })
            elif any(keyword in task_lower for keyword in self.INVENTORY_EOL_KEYWORDS) and any(keyword in task_lower for keyword in self.EOL_KEYWORDS):
                decision_tree.update({
                    "primary_decision": "Execute inventory-grounded EOL analysis",
                    "decision_factors": ["Combined inventory and EOL keywords detected", "Inventory-grounded analysis preferred", "Comprehensive lifecycle assessment needed"],
                    "alternative_approaches": ["Inventory only", "EOL analysis without inventory", "Sequential approach"],
                    "selected_approach": "Specialized inventory discovery followed by per-asset EOL analysis",
                    "reasoning": "Task combines inventory discovery with EOL analysis; use appropriate inventory specialist (OS or Software) then route to EOL specialists"
                })
            elif any(keyword in task_lower for keyword in self.MICROSOFT_KEYWORDS):
                decision_tree.update({
                    "primary_decision": "Route to Microsoft EOL specialist",
                    "decision_factors": ["Microsoft product keywords detected", "Specialized knowledge required"],
                    "alternative_approaches": ["Generic EOL search", "Multi-agent collaboration", "Inventory-grounded analysis"],
                    "selected_approach": "Microsoft specialist with web search",
                    "reasoning": "Task contains Microsoft-specific products requiring specialized EOL knowledge"
                })
            elif any(keyword in task_lower for keyword in self.LINUX_KEYWORDS):
                decision_tree.update({
                    "primary_decision": "Route to Linux EOL specialist",
                    "decision_factors": ["Linux distribution keywords detected", "OS-specific EOL patterns"],
                    "alternative_approaches": ["Generic EOL search", "Ubuntu-specific tools", "Inventory-grounded analysis"],
                    "selected_approach": "Linux specialist with distribution detection",
                    "reasoning": "Task involves Linux distributions with specific EOL lifecycles"
                })
            elif any(keyword in task_lower for keyword in self.PYTHON_KEYWORDS):
                decision_tree.update({
                    "primary_decision": "Route to Python EOL specialist",
                    "decision_factors": ["Python ecosystem keywords detected", "Language-specific lifecycle"],
                    "alternative_approaches": ["Generic EOL search", "Multi-language analysis", "Package-specific search"],
                    "selected_approach": "Python specialist with ecosystem knowledge",
                    "reasoning": "Task involves Python language or ecosystem requiring specialized knowledge"
                })
            elif any(keyword in task_lower for keyword in self.NODEJS_KEYWORDS):
                decision_tree.update({
                    "primary_decision": "Route to Node.js EOL specialist",
                    "decision_factors": ["Node.js ecosystem keywords detected", "JavaScript runtime lifecycle"],
                    "alternative_approaches": ["Generic EOL search", "JavaScript-only analysis", "Package manager search"],
                    "selected_approach": "Node.js specialist with LTS knowledge",
                    "reasoning": "Task involves Node.js runtime or ecosystem requiring specialized knowledge"
                })
            elif any(keyword in task_lower for keyword in self.ORACLE_KEYWORDS):
                decision_tree.update({
                    "primary_decision": "Route to Oracle EOL specialist",
                    "decision_factors": ["Oracle product keywords detected", "Enterprise software lifecycle"],
                    "alternative_approaches": ["Generic EOL search", "Java-specific analysis", "Database-only search"],
                    "selected_approach": "Oracle specialist with enterprise knowledge",
                    "reasoning": "Task involves Oracle products requiring specialized enterprise lifecycle knowledge"
                })
            elif any(keyword in task_lower for keyword in self.PHP_KEYWORDS):
                decision_tree.update({
                    "primary_decision": "Route to PHP EOL specialist",
                    "decision_factors": ["PHP ecosystem keywords detected", "Web framework lifecycle"],
                    "alternative_approaches": ["Generic EOL search", "Framework-specific analysis", "Language-only search"],
                    "selected_approach": "PHP specialist with framework knowledge",
                    "reasoning": "Task involves PHP language or web frameworks requiring specialized knowledge"
                })
            elif any(keyword in task_lower for keyword in self.POSTGRESQL_KEYWORDS):
                decision_tree.update({
                    "primary_decision": "Route to PostgreSQL EOL specialist",
                    "decision_factors": ["PostgreSQL keywords detected", "Database-specific lifecycle"],
                    "alternative_approaches": ["Generic database search", "SQL-only analysis", "Extension-specific search"],
                    "selected_approach": "PostgreSQL specialist with extension knowledge",
                    "reasoning": "Task involves PostgreSQL database requiring specialized database lifecycle knowledge"
                })
            elif any(keyword in task_lower for keyword in self.REDHAT_KEYWORDS):
                decision_tree.update({
                    "primary_decision": "Route to Red Hat EOL specialist",
                    "decision_factors": ["Red Hat ecosystem keywords detected", "Enterprise Linux lifecycle"],
                    "alternative_approaches": ["Generic Linux search", "Distribution-only analysis", "Package-specific search"],
                    "selected_approach": "Red Hat specialist with enterprise knowledge",
                    "reasoning": "Task involves Red Hat ecosystem requiring specialized enterprise Linux knowledge"
                })
            elif any(keyword in task_lower for keyword in self.VMWARE_KEYWORDS):
                decision_tree.update({
                    "primary_decision": "Route to VMware EOL specialist",
                    "decision_factors": ["VMware product keywords detected", "Virtualization platform lifecycle"],
                    "alternative_approaches": ["Generic virtualization search", "Platform-specific analysis", "Infrastructure-only search"],
                    "selected_approach": "VMware specialist with virtualization knowledge",
                    "reasoning": "Task involves VMware virtualization products requiring specialized platform knowledge"
                })
            elif any(keyword in task_lower for keyword in self.APACHE_KEYWORDS):
                decision_tree.update({
                    "primary_decision": "Route to Apache EOL specialist",
                    "decision_factors": ["Apache ecosystem keywords detected", "Web server/foundation lifecycle"],
                    "alternative_approaches": ["Generic web server search", "Foundation-only analysis", "Server-specific search", "WebSurfer general search"],
                    "selected_approach": "Apache specialist with foundation knowledge",
                    "reasoning": "Task involves Apache Foundation products requiring specialized web infrastructure knowledge"
                })
            elif any(keyword in task_lower for keyword in self.EOL_KEYWORDS) and not any(tech in task_lower for tech in self.ALL_TECH_KEYWORDS):
                decision_tree.update({
                    "primary_decision": "Route to WebSurfer EOL specialist for general inquiry",
                    "decision_factors": ["General EOL keywords detected", "No specific technology identified", "Web search capabilities optimal"],
                    "alternative_approaches": ["Try all specialists sequentially", "EndOfLife API fallback", "Technology detection first"],
                    "selected_approach": "WebSurfer comprehensive web search",
                    "reasoning": "General EOL inquiry without specific technology; WebSurfer can search across all sources for comprehensive EOL information"
                })
            else:
                # For general EOL queries or unknown technologies, consider WebSurfer as primary option
                decision_tree.update({
                    "primary_decision": "Route to WebSurfer EOL specialist or best-match specialist",
                    "decision_factors": ["No specific technology detected", "General EOL inquiry", "Web search capabilities needed"],
                    "alternative_approaches": ["Technology-specific routing", "Multi-specialist approach", "Inventory discovery first", "EndOfLife API fallback"],
                    "selected_approach": "WebSurfer EOL search with intelligent fallback",
                    "reasoning": "Task appears to be general EOL inquiry or unknown technology; WebSurfer can perform comprehensive web searches for any software/technology EOL information"
                })
        
        elif planning_stage == "agent_coordination":
            decision_tree.update({
                "primary_decision": "Coordinate specialist agents",
                "decision_factors": ["Task complexity", "Agent capabilities", "Response time requirements"],
                "alternative_approaches": ["Sequential execution", "Parallel execution", "Hybrid approach"],
                "selected_approach": "Coordinated specialist execution",
                "reasoning": "Optimize for accuracy and comprehensive coverage"
            })
        
        return decision_tree
    
    def _generate_agent_selection_reasoning(self, planning_data: Dict[str, Any]) -> Dict[str, Any]:
        """Generate reasoning for agent selection decisions"""
        task = planning_data.get("task", "")
        available_agents = planning_data.get("available_agents", [])
        
        # Handle case where no agents are available
        if not available_agents:
            _, task_type = self._classify_request(task)
            return {
                "task_analysis": {
                    "task_type": task_type,
                    "complexity_level": self._assess_task_complexity(task),
                    "technology_scope": self._identify_technology_scope(task)
                },
                "agent_capabilities": {},
                "selection_matrix": {},
                "final_selection": {
                    "primary_agent": "no_agents_available",
                    "selection_confidence": 0.0,
                    "selection_reasoning": ["No agents available for selection"],
                    "fallback_agents": []
                }
            }
        
        _, task_type = self._classify_request(task)
        selection_reasoning = {
            "task_analysis": {
                "task_type": task_type,
                "complexity_level": self._assess_task_complexity(task),
                "technology_scope": self._identify_technology_scope(task)
            },
            "agent_capabilities": {
                agent: self._describe_agent_capabilities(agent) 
                for agent in available_agents
            },
            "selection_matrix": self._create_agent_selection_matrix(task, available_agents),
            "final_selection": self._determine_optimal_agent_selection(task, available_agents)
        }
        
        return selection_reasoning
    
    def _determine_strategic_approach(self, planning_data: Dict[str, Any]) -> Dict[str, Any]:
        """Determine the strategic approach for task execution"""
        task = planning_data.get("task", "")
        _, task_type = self._classify_request(task)
        
        strategy = {
            "approach_type": "adaptive",
            "execution_strategy": "",
            "risk_mitigation": [],
            "quality_assurance": [],
            "performance_optimization": []
        }
        
        # Handle non-task scenarios (initialization, assessment)
        if not task:
            strategy.update({
                "execution_strategy": "system_assessment",
                "risk_mitigation": ["Graceful degradation", "Fallback mechanisms"],
                "quality_assurance": ["Capability validation", "Error handling"],
                "performance_optimization": ["Efficient initialization", "Resource management"]
            })
            return strategy
        
        # Handle mixed inventory + EOL analysis tasks with specialized strategy
        if task_type == "MIXED_INVENTORY_EOL":
            strategy.update({
                "execution_strategy": "mixed_inventory_eol_workflow",
                "risk_mitigation": [
                    "Inventory collection failure fallback",
                    "Per-asset EOL specialist routing",
                    "Partial results aggregation if some assets fail"
                ],
                "quality_assurance": [
                    "Inventory completeness validation",
                    "Per-asset EOL accuracy verification",
                    "Cross-reference inventory with EOL findings",
                    "Technology-specific specialist validation"
                ],
                "performance_optimization": [
                    "Efficient inventory collection with caching",
                    "Parallel EOL analysis for discovered assets",
                    "Technology-aware specialist routing",
                    "Result aggregation and deduplication"
                ]
            })
            return strategy
        
        # Determine execution strategy based on task characteristics for other types
        if "urgent" in task.lower() or "critical" in task.lower():
            strategy.update({
                "execution_strategy": "fast_path_with_validation",
                "risk_mitigation": ["Quick validation checks", "Fallback options ready"],
                "quality_assurance": ["Real-time verification", "Citation validation"],
                "performance_optimization": ["Cached results priority", "Parallel web searches"]
            })
        else:
            strategy.update({
                "execution_strategy": "comprehensive_analysis",
                "risk_mitigation": ["Multiple source verification", "Cross-validation"],
                "quality_assurance": ["Detailed citation tracking", "Source authenticity checks"],
                "performance_optimization": ["Deep web search", "Multiple specialist consultation"]
            })
        
        return strategy
    
    def _predict_workflow_steps(self, planning_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Predict the expected workflow steps"""
        task = planning_data.get("task", "")
        _, task_type = self._classify_request(task) if task else (None, "GENERAL_QUERY")
        
        # Handle non-task scenarios (initialization, assessment)
        if not task:
            return [
                {
                    "step": 1,
                    "action": "System Assessment",
                    "description": "Evaluate orchestrator capabilities and agent availability",
                    "expected_duration": "0.1s",
                    "success_criteria": "System readiness confirmed"
                },
                {
                    "step": 2,
                    "action": "Configuration Validation",
                    "description": "Verify system configuration and resource availability",
                    "expected_duration": "0.1s",
                    "success_criteria": "Configuration validated"
                }
            ]
        
        # Handle mixed inventory + EOL analysis workflows
        if task_type == "MIXED_INVENTORY_EOL":
            return [
                {
                    "step": 1,
                    "action": "Trigger OS or Software Inventory Specialist",
                    "description": "Call appropriate inventory specialist based on user request",
                    "expected_duration": "2-5s",
                    "success_criteria": "Complete inventory JSON response obtained"
                },
                {
                    "step": 2,
                    "action": "Wait for Response and Extract Items",
                    "description": "Iterate through inventory response, extract name and version for each item",
                    "expected_duration": "0.5s",
                    "success_criteria": "All inventory items parsed with name/version pairs"
                },
                {
                    "step": 3,
                    "action": "Trigger EOL Specialist",
                    "description": "Route each inventory item to appropriate technology specialist (Microsoft/Python/NodeJS/Oracle/PHP/PostgreSQL/RedHat/Ubuntu/VMware/Apache/AzureAI/WebSurfer) with name and version",
                    "expected_duration": "3-10s",
                    "success_criteria": "EOL status determined for all inventory items"
                },
                {
                    "step": 4,
                    "action": "Update Item with EOL Data",
                    "description": "Correlate EOL analysis results with inventory items and format response",
                    "expected_duration": "1-2s",
                    "success_criteria": "User-friendly format with inventory + EOL data consolidated"
                }
            ]
        
        # Default workflow for other task types
        workflow_steps = [
            {
                "step": 1,
                "action": "Task Analysis",
                "description": "Parse user request and identify key requirements",
                "expected_duration": "0.5s",
                "success_criteria": "Clear understanding of user intent"
            },
            {
                "step": 2,
                "action": "Agent Selection",
                "description": "Select optimal specialist agent(s) based on task type",
                "expected_duration": "0.2s",
                "success_criteria": "Appropriate specialist identified"
            },
            {
                "step": 3,
                "action": "Web Search Execution",
                "description": "Perform targeted web searches for EOL information",
                "expected_duration": "3-10s",
                "success_criteria": "Relevant EOL data with citations obtained"
            },
            {
                "step": 4,
                "action": "Data Verification",
                "description": "Validate EOL information and sources",
                "expected_duration": "1-2s",
                "success_criteria": "Information accuracy confirmed"
            },
            {
                "step": 5,
                "action": "Response Synthesis",
                "description": "Compile comprehensive response with citations",
                "expected_duration": "1s",
                "success_criteria": "Clear, actionable response delivered"
            }
        ]
        
        return workflow_steps
    
    def _classify_request(self, message: str) -> tuple[str, str]:
        """
        Unified request classification that returns both query type and task type.
        
        Returns:
            tuple: (query_type, task_type) where:
            - query_type: detailed classification for routing logic
            - task_type: high-level task classification for workflow selection
        """
        message_lower = message.lower()
        
        # 1. Internet search patterns - highest priority
        internet_search_patterns = [
            "search internet", "search the internet", "search online", "look up online",
            "search web", "search the web", "find online", "look up on the internet", 
            "search for", "google", "web search", "latest eol", "azure ai search"
        ]
        
        if any(pattern in message_lower for pattern in internet_search_patterns):
            return ("internet_eol", "INTERNET_EOL")
        
        # 2. Check for EOL keywords early to help with mixed vs pure classification
        has_eol_keywords = any(eol_word in message_lower for eol_word in [
            "eol", "end of life", "support", "lifecycle", "retirement", "support ends",
            "when does", "when will", "end of support"
        ])
        
        # 3. Check for inventory keywords
        has_inventory_keywords = any(inv_word in message_lower for inv_word in [
            "inventory", "list", "software", "versions", "what do i have", 
            "show me my", "what applications", "what systems", "installed"
        ])
        
        # 4. OS-related keywords
        has_os_keywords = any(os_word in message_lower for os_word in [
            "operating system", "windows", "linux", "ubuntu", "centos", "rhel",
            "os version", "kernel", "what os", "which os", "server os", "os"
        ])
        
        # 5. Software-related keywords  
        has_software_keywords = any(sw_word in message_lower for sw_word in [
            "software", "application", "program", "sql server", "office", "adobe"
        ])
        
        # 6. Mixed workflow: inventory + EOL analysis
        if has_inventory_keywords and has_eol_keywords:
            if has_os_keywords:
                return ("os_eol_grounded", "MIXED_INVENTORY_EOL")
            elif has_software_keywords:
                return ("software_eol_grounded", "MIXED_INVENTORY_EOL") 
            else:
                return ("general_eol_grounded", "MIXED_INVENTORY_EOL")
        
        # 7. Pure EOL queries (no inventory context needed)
        pure_eol_patterns = [
            "when does", "when will", "what is the eol", "what is the end of life",
            "support ends", "lifecycle information", "retirement date",
            "eol date", "end of support", "microsoft support", "ubuntu support"
        ]
        
        if any(pattern in message_lower for pattern in pure_eol_patterns) or \
           (has_eol_keywords and not has_inventory_keywords):
            return ("direct_eol", "EOL_ONLY")
        
        # 8. Pure inventory queries (no EOL context)
        pure_inventory_patterns = [
            "what software do i have", "what do i have installed", "show me my software",
            "list my software", "software in my inventory", "what applications do i have",
            "what os versions do i have", "what operating systems", "show me my os",
            "list my os", "os in my inventory", "what systems do i have"
        ]
        
        if any(pattern in message_lower for pattern in pure_inventory_patterns) and not has_eol_keywords:
            if has_os_keywords:
                return ("os_inventory", "INVENTORY_ONLY")
            else:
                return ("software_inventory", "INVENTORY_ONLY")
        
        # 9. OS-related queries
        if has_os_keywords:
            if has_eol_keywords:
                return ("os_eol_grounded", "MIXED_INVENTORY_EOL")
            else:
                return ("os_inventory", "INVENTORY_ONLY")
        
        # 10. Software-related queries  
        if has_software_keywords:
            if has_eol_keywords:
                return ("software_eol_grounded", "MIXED_INVENTORY_EOL")
            else:
                return ("software_inventory", "INVENTORY_ONLY")
        
        # 11. General inventory queries
        if has_inventory_keywords and not has_eol_keywords:
            return ("software_inventory", "INVENTORY_ONLY")
        
        # 12. General EOL queries (need inventory context)
        if has_eol_keywords:
            return ("general_eol_grounded", "MIXED_INVENTORY_EOL")
        
        # 13. Other task types
        if any(keyword in message_lower for keyword in ["update", "upgrade", "migration"]):
            return ("update_planning", "UPDATE_PLANNING")
        
        # 14. Default fallback
        return ("software_inventory", "INVENTORY_ONLY")
    
    def _classify_task_type(self, task: str) -> str:
        """Legacy compatibility method - redirects to unified classification"""
        _, task_type = self._classify_request(task)
        return task_type
    
    def _classify_request_simple(self, message: str) -> str:
        """Legacy compatibility method - redirects to unified classification"""
        query_type, _ = self._classify_request(message)
        return query_type
    
    def _assess_task_complexity(self, task: str) -> str:
        """Assess the complexity level of the task"""
        complexity_indicators = len(task.split()) + len(re.findall(r'\b(?:and|or|with|including)\b', task.lower()))
        
        if complexity_indicators > 20:
            return "HIGH"
        elif complexity_indicators > 10:
            return "MEDIUM"
        else:
            return "LOW"
    
    def _identify_technology_scope(self, task: str) -> List[str]:
        """Identify technology scope from task content"""
        technologies = []
        task_lower = task.lower()
        
        # Microsoft technologies
        if any(keyword in task_lower for keyword in ["windows", "microsoft", "office", "exchange", "sql server", "azure", "sharepoint", "teams"]):
            technologies.append("Microsoft")
         
        # Python technologies
        if any(keyword in task_lower for keyword in ["python", "django", "flask", "pip", "conda", "jupyter", "pandas", "numpy"]):
            technologies.append("Python")
        
        # Node.js technologies
        if any(keyword in task_lower for keyword in ["nodejs", "node.js", "npm", "javascript", "node", "express", "react", "vue"]):
            technologies.append("NodeJS")
        
        # Oracle technologies
        if any(keyword in task_lower for keyword in ["oracle", "java", "jdk", "jre", "mysql", "virtualbox", "solaris"]):
            technologies.append("Oracle")
        
        # PHP technologies
        if any(keyword in task_lower for keyword in ["php", "composer", "laravel", "symfony", "wordpress", "drupal"]):
            technologies.append("PHP")
        
        # PostgreSQL technologies
        if any(keyword in task_lower for keyword in ["postgresql", "postgres", "postgis", "pgadmin"]):
            technologies.append("PostgreSQL")
        
        # Red Hat technologies
        if any(keyword in task_lower for keyword in ["redhat", "red hat", "rhel", "centos", "fedora", "openshift"]):
            technologies.append("RedHat")
        
        # Ubuntu technologies
        if any(keyword in task_lower for keyword in ["ubuntu", "canonical", "snap", "snapcraft", "launchpad"]):
            technologies.append("Ubuntu")
        
        # VMware technologies
        if any(keyword in task_lower for keyword in ["vmware", "vsphere", "esxi", "vcenter", "workstation", "fusion"]):
            technologies.append("VMware")
        
        # Apache technologies
        if any(keyword in task_lower for keyword in ["apache", "httpd", "tomcat", "maven", "spark", "kafka", "cassandra"]):
            technologies.append("Apache")
        
        return technologies if technologies else ["Python"]  # Default to Python as most common
    
    def _describe_agent_capabilities(self, agent_name: str) -> Dict[str, Any]:
        """Describe the capabilities of a specific agent"""
        capabilities = {
            "OSInventoryAnalyst": {
                "specialty": "Operating system inventory analysis",
                "tools": ["OS discovery", "System information scanning", "Platform detection", "Version enumeration"],
                "strengths": ["OS identification", "Platform enumeration", "Version detection", "Multi-platform support"],
                "best_for": ["OS inventory queries", "Operating system discovery", "Platform auditing", "OS-grounded EOL analysis"]
            },
            "SoftwareInventoryAnalyst": {
                "specialty": "Software and application inventory analysis",
                "tools": ["Software scanning", "Application discovery", "Package enumeration", "Version detection"],
                "strengths": ["Application discovery", "Software enumeration", "Package analysis", "Cross-platform scanning"],
                "best_for": ["Software inventory queries", "Application discovery", "Package auditing", "Software-grounded EOL analysis"]
            },
            "MicrosoftEOLSpecialist": {
                "specialty": "Microsoft product EOL analysis",
                "tools": ["WebSurfer", "Microsoft-specific searches"],
                "strengths": ["Microsoft lifecycle knowledge", "Official documentation"],
                "best_for": ["Windows EOL", "Office EOL", "SQL Server EOL"]
            },
            "ApacheEOLSpecialist": {
                "specialty": "Apache software stack EOL analysis",
                "tools": ["Apache foundation sites", "Official documentation"],
                "strengths": ["Apache HTTP Server", "Tomcat", "Maven lifecycle knowledge"],
                "best_for": ["Apache HTTP Server EOL", "Tomcat EOL", "Apache ecosystem"]
            },
            "NodeJSEOLSpecialist": {
                "specialty": "Node.js and JavaScript runtime EOL analysis",
                "tools": ["Node.js release schedule", "npm registry"],
                "strengths": ["Node.js LTS cycles", "JavaScript ecosystem"],
                "best_for": ["Node.js EOL", "npm package lifecycle", "JavaScript runtime"]
            },
            "OracleEOLSpecialist": {
                "specialty": "Oracle products EOL analysis",
                "tools": ["Oracle support portal", "Official documentation"],
                "strengths": ["Oracle Database", "Java SE", "MySQL lifecycle knowledge"],
                "best_for": ["Oracle Database EOL", "Java SE EOL", "Oracle ecosystem"]
            },
            "PHPEOLSpecialist": {
                "specialty": "PHP language and ecosystem EOL analysis",
                "tools": ["PHP.net official site", "Release documentation"],
                "strengths": ["PHP version lifecycle", "Extension support"],
                "best_for": ["PHP EOL", "PHP extension lifecycle", "Web framework EOL"]
            },
            "PostgreSQLEOLSpecialist": {
                "specialty": "PostgreSQL database EOL analysis",
                "tools": ["PostgreSQL.org", "Release documentation"],
                "strengths": ["PostgreSQL version policy", "Extension lifecycle"],
                "best_for": ["PostgreSQL EOL", "Database lifecycle", "PostGIS EOL"]
            },
            "PythonEOLSpecialist": {
                "specialty": "Python language and ecosystem EOL analysis",
                "tools": ["Python.org", "PEP documentation", "PyPI"],
                "strengths": ["Python version lifecycle", "Package ecosystem"],
                "best_for": ["Python EOL", "Django EOL", "Python package lifecycle"]
            },
            "RedHatEOLSpecialist": {
                "specialty": "Red Hat and enterprise Linux EOL analysis",
                "tools": ["Red Hat portal", "RHEL documentation"],
                "strengths": ["RHEL lifecycle", "Enterprise support cycles"],
                "best_for": ["RHEL EOL", "CentOS EOL", "Red Hat ecosystem"]
            },
            "UbuntuEOLSpecialist": {
                "specialty": "Ubuntu and Canonical products EOL analysis",
                "tools": ["Ubuntu.com", "Launchpad", "Release documentation"],
                "strengths": ["Ubuntu LTS cycles", "Snap package lifecycle"],
                "best_for": ["Ubuntu EOL", "Snap EOL", "Canonical ecosystem"]
            },
            "VMwareEOLSpecialist": {
                "specialty": "VMware products EOL analysis",
                "tools": ["VMware support portal", "Product documentation"],
                "strengths": ["vSphere lifecycle", "Virtual infrastructure"],
                "best_for": ["vSphere EOL", "ESXi EOL", "VMware ecosystem"]
            },
            "AzureAIEOLSpecialist": {
                "specialty": "Azure AI Agent Service with grounding for comprehensive EOL analysis",
                "tools": ["Azure AI Foundry", "Azure AI Grounding", "Azure AI Services", "Real-time web search"],
                "strengths": ["Modern AI grounding", "Source citations", "Enterprise reliability", "Structured results"],
                "best_for": ["General EOL queries", "Unknown technology EOL", "Latest EOL updates", "Cross-platform EOL research", "Primary search agent"]
            },
            "WebSurferEOLSpecialist": {
                "specialty": "Comprehensive web-based EOL analysis for any technology",
                "tools": ["WebSurfer", "Autogen Multimodal Websurfer", "Multi-source web search", "Real-time web data"],
                "strengths": ["Universal technology coverage", "Latest information", "Multiple source validation", "Unknown technology discovery"],
                "best_for": ["General EOL queries", "Unknown technology EOL", "Latest EOL updates", "Cross-platform EOL research", "Fallback analysis"]
            }
        }
        
        return capabilities.get(agent_name, {"specialty": "Unknown", "tools": [], "strengths": [], "best_for": []})
    
    def _create_agent_selection_matrix(self, task: str, available_agents: List[str]) -> Dict[str, Any]:
        """Create a selection matrix for agent scoring"""
        _, task_type = self._classify_request(task)
        technology_scope = self._identify_technology_scope(task)
        
        matrix = {}
        for agent in available_agents:
            score = 0
            reasoning = []
            
            # Score based on agent specialization match
            if agent == "MicrosoftEOLSpecialist" and "Microsoft" in technology_scope:
                score += 3
                reasoning.append("Perfect match for Microsoft technologies")
            elif agent == "PythonEOLSpecialist" and "Python" in technology_scope:
                score += 3
                reasoning.append("Perfect match for Python ecosystem")
            elif agent == "NodeJSEOLSpecialist" and "NodeJS" in technology_scope:
                score += 3
                reasoning.append("Perfect match for Node.js ecosystem")
            elif agent == "OracleEOLSpecialist" and "Oracle" in technology_scope:
                score += 3
                reasoning.append("Perfect match for Oracle products")
            elif agent == "PHPEOLSpecialist" and "PHP" in technology_scope:
                score += 3
                reasoning.append("Perfect match for PHP ecosystem")
            elif agent == "PostgreSQLEOLSpecialist" and "PostgreSQL" in technology_scope:
                score += 3
                reasoning.append("Perfect match for PostgreSQL database")
            elif agent == "RedHatEOLSpecialist" and "RedHat" in technology_scope:
                score += 3
                reasoning.append("Perfect match for Red Hat ecosystem")
            elif agent == "UbuntuEOLSpecialist" and "Ubuntu" in technology_scope:
                score += 3
                reasoning.append("Perfect match for Ubuntu/Canonical products")
            elif agent == "VMwareEOLSpecialist" and "VMware" in technology_scope:
                score += 3
                reasoning.append("Perfect match for VMware virtualization")
            elif agent == "ApacheEOLSpecialist" and "Apache" in technology_scope:
                score += 3
                reasoning.append("Perfect match for Apache foundation products")
            elif agent == "AzureAIEOLSpecialist":
                # Azure AI Agent Service is the primary search agent with modern capabilities
                score += 2
                reasoning.append("Modern AI grounding with source citations")
                if any(keyword in task.lower() for keyword in ["search", "find", "latest", "unknown"]):
                    score += 2
                    reasoning.append("Excellent for modern search with AI grounding")
            elif agent == "WebSurferEOLSpecialist":
                # WebSurfer is universal - give it a base score and bonus for general queries
                score += 1
                reasoning.append("Universal EOL search capability")
                if not any(tech in technology_scope for tech in ["Microsoft", "Python", "NodeJS", "Oracle", "PHP", "PostgreSQL", "RedHat", "Ubuntu", "VMware", "Apache"]):
                    score += 2
                    reasoning.append("Best choice for unknown or general technologies")
                if any(keyword in task.lower() for keyword in ["general", "any", "unknown", "search", "find"]):
                    score += 1
                    reasoning.append("Optimal for general search queries")
            
            # Enhanced scoring based on task type
            if task_type == "EOL_ONLY" and "Specialist" in agent:
                score += 2
                reasoning.append("Specialized for EOL analysis")
            elif task_type == "INVENTORY_ONLY":
                if agent == "OSInventoryAnalyst" and any(keyword in task.lower() for keyword in ["os", "operating system", "platform"]):
                    score += 3
                    reasoning.append("Specialized for OS inventory analysis")
                elif agent == "SoftwareInventoryAnalyst" and any(keyword in task.lower() for keyword in ["software", "applications", "packages"]):
                    score += 3
                    reasoning.append("Specialized for software inventory analysis")
                elif agent in ["OSInventoryAnalyst", "SoftwareInventoryAnalyst"]:
                    score += 2
                    reasoning.append("General inventory capability")
            elif task_type == "MIXED_INVENTORY_EOL":
                if agent == "OSInventoryAnalyst" and any(keyword in task.lower() for keyword in ["os", "operating system", "platform"]):
                    score += 3
                    reasoning.append("Essential for OS inventory discovery in mixed analysis")
                elif agent == "SoftwareInventoryAnalyst" and any(keyword in task.lower() for keyword in ["software", "applications", "packages"]):
                    score += 3
                    reasoning.append("Essential for software inventory discovery in mixed analysis")
                elif agent in ["OSInventoryAnalyst", "SoftwareInventoryAnalyst"]:
                    score += 2
                    reasoning.append("Required for inventory discovery in mixed analysis")
                elif "Specialist" in agent:
                    score += 2
                    reasoning.append("Required for EOL analysis after inventory discovery")
                    # Additional bonus for technology-specific specialists in mixed tasks
                    if ((agent == "MicrosoftEOLSpecialist" and "Microsoft" in technology_scope) or
                        (agent == "PythonEOLSpecialist" and "Python" in technology_scope) or
                        (agent == "NodeJSEOLSpecialist" and "NodeJS" in technology_scope) or
                        (agent == "OracleEOLSpecialist" and "Oracle" in technology_scope) or
                        (agent == "PHPEOLSpecialist" and "PHP" in technology_scope) or
                        (agent == "PostgreSQLEOLSpecialist" and "PostgreSQL" in technology_scope) or
                        (agent == "RedHatEOLSpecialist" and "RedHat" in technology_scope) or
                        (agent == "UbuntuEOLSpecialist" and "Ubuntu" in technology_scope) or
                        (agent == "VMwareEOLSpecialist" and "VMware" in technology_scope) or
                        (agent == "ApacheEOLSpecialist" and "Apache" in technology_scope)):
                        score += 1
                        reasoning.append("Technology specialist bonus for inventory-grounded EOL analysis")
            
            matrix[agent] = {
                "score": score,
                "reasoning": reasoning,
                "recommended": score >= 2
            }
        
        return matrix
    
    def _determine_optimal_agent_selection(self, task: str, available_agents: List[str]) -> Dict[str, Any]:
        """Determine the optimal agent selection"""
        matrix = self._create_agent_selection_matrix(task, available_agents)
        
        # Handle empty agent list gracefully
        if not matrix or not available_agents:
            return {
                "primary_agent": "no_agents_available",
                "selection_confidence": 0.0,
                "selection_reasoning": ["No agents available for selection"],
                "fallback_agents": []
            }
        
        # Find highest scoring agent
        best_agent = max(matrix.keys(), key=lambda agent: matrix[agent]["score"])
        
        return {
            "primary_agent": best_agent,
            "selection_confidence": matrix[best_agent]["score"] / 5.0,  # Normalize to 0-1
            "selection_reasoning": matrix[best_agent]["reasoning"],
            "fallback_agents": [
                agent for agent, data in matrix.items() 
                if agent != best_agent and data["score"] > 0
            ]
        }
    
    def _log_performance_metric(self, metric_name: str, value: float, metadata: Dict[str, Any] = None):
        """Log performance metrics for orchestrator behavior"""
        metric_log = {
            "timestamp": datetime.now().isoformat(),
            "session_id": self.session_id,
            "metric_name": metric_name,
            "value": value,
            "metadata": metadata or {},
            "conversation_id": len(self.conversation_history)
        }
        
        self.performance_metrics[metric_name].append(metric_log)
        
        logger.info(f"📊 PERFORMANCE_METRIC [{metric_name}]: {value} {json.dumps(metadata or {}, default=str)}")
    
    def _log_error_and_recovery(self, error_type: str, error_details: Dict[str, Any], recovery_action: str = None):
        """Log errors and recovery actions"""
        error_log = {
            "timestamp": datetime.now().isoformat(),
            "session_id": self.session_id,
            "error_type": error_type,
            "error_details": error_details,
            "recovery_action": recovery_action,
            "conversation_id": len(self.conversation_history)
        }
        
        self.error_logs.append(error_log)
        
        if recovery_action:
            self.recovery_actions.append({
                "timestamp": datetime.now().isoformat(),
                "session_id": self.session_id,
                "recovery_action": recovery_action,
                "original_error": error_type
            })
        
        logger.error(f"🚨 ERROR_RECOVERY [{error_type}]: {json.dumps(error_details, default=str)} → {recovery_action}")
    
    async def execute_mixed_inventory_eol_workflow(self, user_message: str, planning_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute the mixed inventory with EOL analysis workflow from flow diagram:
        1. Trigger OS or Software inventory specialist and wait for response
        2. Wait for response, iterate through each item, extract name and version
        3. Trigger appropriate technology specialist with name/version to search for EOL date
        4. Update item with EOL date found and format into user-friendly format
        """
        workflow_start_time = time.time()
        
        result = {
            "workflow_type": "mixed_inventory_eol",
            "user_message": user_message,
            "steps_completed": [],
            "inventory_data": None,
            "parsed_items": [],
            "eol_analyses": [],
            "final_summary": {},
            "errors": []
        }
        
        self._log_orchestrator_event("inventory_eol_workflow_start", {
            "user_message": user_message,
            "workflow_start_time": workflow_start_time
        })
        
        try:
            # Step 1: Trigger OS or Software inventory specialist and wait for response
            self._log_orchestrator_event("workflow_step_1_start", {"step": "trigger_inventory_specialist"})
            
            # Determine if user wants OS inventory, software inventory, or both
            inventory_type = self._determine_inventory_type(user_message)
            inventory_response = await self._collect_inventory_data(inventory_type)
            result["inventory_data"] = inventory_response
            result["steps_completed"].append("trigger_inventory_specialist")
            
            self._log_orchestrator_event("workflow_step_1_complete", {
                "inventory_type": inventory_type,
                "response_length": len(str(inventory_response))
            })
            
            # Step 2: Wait for response, iterate through each item, extract name and version
            self._log_orchestrator_event("workflow_step_2_start", {"step": "extract_name_version"})
            
            parsed_items = self._parse_inventory_items(inventory_response, inventory_type)
            result["parsed_items"] = parsed_items
            result["steps_completed"].append("extract_name_version")
            
            self._log_orchestrator_event("workflow_step_2_complete", {
                "parsed_items_count": len(parsed_items),
                "sample_items": parsed_items[:3] if len(parsed_items) > 3 else parsed_items
            })
            
            # Step 3: Trigger appropriate technology specialist with name and version
            self._log_orchestrator_event("workflow_step_3_start", {"step": "trigger_eol_specialist"})
            
            eol_analyses = []
            for item in parsed_items:
                try:
                    # Determine the right EOL specialist type for this item
                    specialist_type = self._determine_eol_specialist_type(item)
                    name = item.get("name", "")
                    version = item.get("version", "")
                    
                    # Call the unified specialist function directly with proper parameters
                    eol_result = await self._call_eol_specialist_unified(
                        specialist_type, 
                        name, 
                        version, 
                        user_message=user_message,
                        conversation_id=planning_data.get("conversation_id"),
                        start_time=workflow_start_time,
                        cache_key=None,  # No caching for workflow items
                        timeout_seconds=planning_data.get("timeout_seconds", 60)
                    )
                    eol_analyses.append({
                        "item": item,
                        "specialist_used": f"{specialist_type.title()}EOLSpecialist",
                        "eol_result": eol_result,
                        "status": "success"
                    })
                    
                except Exception as e:
                    eol_analyses.append({
                        "item": item,
                        "specialist_used": "error",
                        "eol_result": None,
                        "status": "error",
                        "error": str(e)
                    })
                    result["errors"].append(f"EOL analysis failed for {item.get('name', 'unknown')}: {str(e)}")
            
            result["eol_analyses"] = eol_analyses
            result["steps_completed"].append("trigger_eol_specialist")
            
            self._log_orchestrator_event("workflow_step_3_complete", {
                "total_items_analyzed": len(eol_analyses),
                "successful_analyses": len([a for a in eol_analyses if a["status"] == "success"]),
                "failed_analyses": len([a for a in eol_analyses if a["status"] == "error"])
            })
            
            # Step 4: Update item with EOL date found and format into user-friendly format
            self._log_orchestrator_event("workflow_step_4_start", {"step": "update_item_with_eol_data"})
            
            final_summary = self._correlate_and_format_eol_results(eol_analyses, user_message)
            result["final_summary"] = final_summary
            result["steps_completed"].append("update_item_with_eol_data")
            
            workflow_end_time = time.time()
            total_duration = workflow_end_time - workflow_start_time
            
            self._log_orchestrator_event("inventory_eol_workflow_complete", {
                "total_duration": total_duration,
                "steps_completed": result["steps_completed"],
                "total_items": len(parsed_items),
                "successful_eol_checks": len([a for a in eol_analyses if a["status"] == "success"])
            })
            
            self._log_performance_metric("inventory_eol_workflow_duration", total_duration, {
                "items_processed": len(parsed_items),
                "eol_analyses_completed": len(eol_analyses)
            })
            
            return result
            
        except Exception as e:
            self._log_error_and_recovery("inventory_eol_workflow_failure", {
                "error": str(e),
                "user_message": user_message,
                "steps_completed": result["steps_completed"]
            }, "return_partial_results")
            
            result["errors"].append(f"Workflow failure: {str(e)}")
            return result
    
    async def _route_inventory_only_task(self, user_message: str, conversation_id: int, start_time: float, cache_key: str) -> Dict[str, Any]:
        """Route inventory-only tasks to appropriate specialist based on Software/OS inventory type"""
        logger.info(f"📦 Routing INVENTORY_ONLY task")
        
        # Determine if Software inventory only, OS inventory only, or mixed
        message_lower = user_message.lower()
        
        if any(keyword in message_lower for keyword in ["software", "applications", "packages"]) and not any(keyword in message_lower for keyword in ["os", "operating system", "platform"]):
            # Software inventory only
            logger.info(f"→ Routing to Software inventory specialist")
            return await self._call_software_inventory_specialist_direct(user_message, conversation_id, start_time, cache_key)
        elif any(keyword in message_lower for keyword in ["os", "operating system", "platform"]) and not any(keyword in message_lower for keyword in ["software", "applications", "packages"]):
            # OS inventory only
            logger.info(f"→ Routing to OS inventory specialist")
            return await self._call_os_inventory_specialist_direct(user_message, conversation_id, start_time, cache_key)
        else:
            # Mixed or general inventory - call both specialists
            logger.info(f"→ Routing to both OS and Software inventory specialists")
            return await self._call_both_inventory_specialists_direct(user_message, conversation_id, start_time, cache_key)
    
    async def _route_eol_only_task(self, user_message: str, conversation_id: int, start_time: float, cache_key: str, timeout_seconds: int) -> Dict[str, Any]:
        """Route EOL-only tasks to specific technology specialists based on technology detected"""
        logger.info(f"🔍 Routing EOL_ONLY task")
        
        # Determine technology scope for routing
        message_lower = user_message.lower()
        
        # Technology-specific routing using mapping for cleaner code
        specialist_mappings = {
            "microsoft": ["windows", "microsoft", "office", "exchange", "sql server", "azure"],
            "ubuntu": ["ubuntu"],
            "python": ["python", "django", "flask", "pip", "conda"],
            "nodejs": ["nodejs", "node.js", "npm", "javascript", "node"],
            "oracle": ["oracle", "java", "mysql", "virtualbox"],
            "php": ["php", "composer", "laravel", "symfony"],
            "postgresql": ["postgresql", "postgres", "postgis"],
            "redhat": ["redhat", "rhel", "fedora"],
            "vmware": ["vmware", "vsphere", "esxi", "vcenter"],
            "apache": ["apache", "httpd", "tomcat", "maven"]
        }
        
        # Find matching specialist based on keywords
        selected_specialist = None
        for specialist, keywords in specialist_mappings.items():
            if any(keyword in message_lower for keyword in keywords):
                selected_specialist = specialist
                break
        
        # Default to general if no specific technology detected
        if not selected_specialist:
            selected_specialist = "general"
        
        # Log routing decision and call unified function
        specialist_names = {
            "microsoft": "Microsoft", "ubuntu": "Ubuntu", "python": "Python", 
            "nodejs": "Node.js", "oracle": "Oracle", "php": "PHP", 
            "postgresql": "PostgreSQL", "redhat": "Red Hat", "vmware": "VMware", 
            "apache": "Apache", "general": "General"
        }
        
        logger.info(f"→ Routing to {specialist_names.get(selected_specialist, selected_specialist)} EOL specialist")
        software_name, version = self._extract_software_name_version(user_message)
        result = await self._call_eol_specialist_unified(selected_specialist, software_name, version, 
                                                     user_message, conversation_id, start_time, cache_key, timeout_seconds)
        
        # Convert tracking format to chat response format for direct calls
        return await self._convert_tracking_to_chat_response(result, user_message, conversation_id, start_time)
        
    def _determine_inventory_type(self, user_message: str) -> str:
        """Determine what type of inventory the user wants (os, software, or both)"""
        message_lower = user_message.lower()
        
        has_os_keywords = any(keyword in message_lower for keyword in ["os", "operating system", "os inventory"])
        has_software_keywords = any(keyword in message_lower for keyword in ["software", "applications", "software inventory"])
        
        if has_os_keywords and has_software_keywords:
            return "both"
        elif has_os_keywords:
            return "os"
        elif has_software_keywords:
            return "software"
        else:
            return "both"  # Default to both if unclear
    
    async def _route_internet_eol_task(self, user_message: str, conversation_id: int, start_time: float, cache_key: str, timeout_seconds: int) -> Dict[str, Any]:
        """Route INTERNET_EOL tasks directly to Playwright agent for reliable Bing search extraction"""
        logger.info(f"🌐 Routing INTERNET_EOL task to Playwright Agent")
        
        # Extract software name and version for targeted search
        software_name, version = self._extract_software_name_version(user_message)
        
        # Log the routing decision
        self._log_orchestrator_event("internet_eol_routing", {
            "user_message_preview": user_message[:100],
            "software_name": software_name,
            "version": version,
            "routing_strategy": "playwright_agent"
        })
        
        # Call unified EOL specialist with playwright type for consistent tracking
        result = await self._call_eol_specialist_unified(
            "playwright", 
            software_name, 
            version,
            user_message, 
            conversation_id, 
            start_time, 
            cache_key, 
            timeout_seconds
        )
        
        # Convert tracking format to chat response format for direct calls
        return await self._convert_tracking_to_chat_response(result, user_message, conversation_id, start_time)
    
    async def _call_software_inventory_specialist_direct(self, user_message: str, conversation_id: int, start_time: float, cache_key: str) -> Dict[str, Any]:
        """Direct call to software inventory specialist for inventory-only tasks"""
        try:
            # Call our Magentic-One software inventory tool for real data
            software_response = self._get_software_inventory_tool_sync()
            
            return {
                "response": software_response,
                "conversation_id": conversation_id,
                "response_time": time.time() - start_time,
                "agent_used": "SoftwareInventoryAnalyst",
                "query_type": "software_inventory_only"
            }
        except Exception as e:
            logger.error(f"❌ Error in software inventory specialist direct call: {e}")
            return {
                "response": f"Error collecting software inventory: {str(e)}",
                "conversation_id": conversation_id,
                "response_time": time.time() - start_time,
                "agent_used": "SoftwareInventoryAnalyst",
                "query_type": "software_inventory_only",
                "error": str(e)
            }
    
    async def _call_os_inventory_specialist_direct(self, user_message: str, conversation_id: int, start_time: float, cache_key: str) -> Dict[str, Any]:
        """Direct call to OS inventory specialist for inventory-only tasks"""
        try:
            # Call our Magentic-One OS inventory tool for real data
            os_response = self._get_os_inventory_tool_sync(direct=True)
            return {
                "response": os_response,
                "conversation_id": conversation_id,
                "response_time": time.time() - start_time,
                "agent_used": "OSInventoryAnalyst",
                "query_type": "os_inventory_only"
            }
        except Exception as e:
            logger.error(f"❌ Error in OS inventory specialist direct call: {e}")
            return {
                "response": f"Error collecting OS inventory: {str(e)}",
                "conversation_id": conversation_id,
                "response_time": time.time() - start_time,
                "agent_used": "OSInventoryAnalyst",
                "query_type": "os_inventory_only",
                "error": str(e)
            }
    
    async def _call_both_inventory_specialists_direct(self, user_message: str, conversation_id: int, start_time: float, cache_key: str) -> Dict[str, Any]:
        """Direct call to both inventory specialists for comprehensive inventory"""
        try:
            # Call both Magentic-One inventory tools for comprehensive data
            os_response = self._get_os_inventory_tool_sync()
            software_response = self._get_software_inventory_tool_sync()
            
            # Combine responses
            combined_response = f"""# Comprehensive Inventory Analysis

## Operating Systems
{os_response}

## Software Applications  
{software_response}

---
**Analysis Complete**: Both OS and software inventory data collected and ready for further analysis."""

            return {
                "response": combined_response,
                "conversation_id": conversation_id,
                "response_time": time.time() - start_time,
                "agent_used": "OSInventoryAnalyst + SoftwareInventoryAnalyst",
                "query_type": "inventory_comprehensive"
            }
        except Exception as e:
            logger.error(f"❌ Error in combined inventory specialist call: {e}")
            return {
                "response": f"Error collecting comprehensive inventory: {str(e)}",
                "conversation_id": conversation_id,
                "response_time": time.time() - start_time,
                "agent_used": "OSInventoryAnalyst + SoftwareInventoryAnalyst",
                "query_type": "inventory_comprehensive",
                "error": str(e)
            }
    
    def _track_eol_agent_response(self, agent_name: str, software_name: str, software_version: str, eol_result: Dict[str, Any], response_time: float, query_type: str) -> None:
        """Track EOL agent responses for comprehensive history tracking"""
        try:
            # Debug logging for troubleshooting
            logger.debug(f"🔧 Tracking call - Agent: {agent_name}, Software: {software_name}, Result type: {type(eol_result)}, Result: {eol_result}")
            
            # Handle None or invalid eol_result
            if eol_result is None:
                logger.warning(f"⚠️ EOL result was None for {agent_name} -> {software_name}, creating fallback result")
                eol_result = {
                    "success": False,
                    "error": "EOL result was None",
                    "data": {}
                }
            elif not isinstance(eol_result, dict):
                logger.warning(f"⚠️ EOL result was not a dictionary for {agent_name} -> {software_name}: {type(eol_result)}")
                eol_result = {
                    "success": False,
                    "error": f"EOL result was not a dictionary: {type(eol_result)}",
                    "data": {}
                }
            
            # Create comprehensive response tracking entry with defensive programming
            response_entry = {
                "timestamp": datetime.now().isoformat(),
                "agent_name": agent_name,
                "software_name": software_name,
                "software_version": software_version or "Not specified",
                "query_type": query_type,
                "response_time": response_time,
                "success": eol_result.get("success", False) if eol_result and isinstance(eol_result, dict) else False,
                "eol_data": eol_result.get("data", {}) if eol_result and isinstance(eol_result, dict) else {},
                "error": eol_result.get("error", {}) if eol_result and isinstance(eol_result, dict) else "EOL result was invalid",
                "confidence": eol_result.get("data", {}).get("confidence", 0) if eol_result and isinstance(eol_result, dict) and eol_result.get("data") else 0,
                "source_url": eol_result.get("data", {}).get("source_url", "") if eol_result and isinstance(eol_result, dict) and eol_result.get("data") else "",
                "agent_used": eol_result.get("data", {}).get("agent_used", agent_name) if eol_result and isinstance(eol_result, dict) and eol_result.get("data") else agent_name,
                "session_id": self.session_id
            }
            
            # Add to tracking list
            self.eol_agent_responses.append(response_entry)
            
            # Keep only the last 50 responses to prevent memory issues
            if len(self.eol_agent_responses) > 50:
                self.eol_agent_responses = self.eol_agent_responses[-50:]
                
            # Log the tracking for debugging
            logger.info(f"📊 Tracked EOL response: {agent_name} -> {software_name} ({software_version}) - Success: {response_entry['success']} - Total tracked: {len(self.eol_agent_responses)}")
            
            # CRITICAL FIX: Also log to agent_interaction_logs so communications appear in UI
            logger.info(f"🔧 [TRACKING] About to log agent interaction - Current agent_interaction_logs length: {len(self.agent_interaction_logs)}")
            
            self._log_agent_interaction(
                agent_name=agent_name,
                action=f"eol_query_{query_type}",
                data={
                    "software_name": software_name,
                    "software_version": software_version,
                    "query_type": query_type,
                    "response_time": response_time,
                    "success": response_entry['success'],
                    "eol_data": response_entry['eol_data'],
                    "error": response_entry.get('error'),
                    "confidence": response_entry.get('confidence', 0),
                    "source_url": response_entry.get('source_url', ''),
                    "timestamp": response_entry['timestamp']
                }
            )
            
            logger.info(f"✅ Logged EOL interaction to agent_interaction_logs - New length: {len(self.agent_interaction_logs)}")
            logger.info(f"🔍 [TRACKING] Last interaction logged: {self.agent_interaction_logs[-1] if self.agent_interaction_logs else 'None'}")
            
        except Exception as e:
            logger.error(f"❌ Error tracking EOL agent response: {e}")
    
    def get_eol_agent_responses(self) -> List[Dict[str, Any]]:
        """Get all tracked EOL agent responses for this session"""
        return self.eol_agent_responses.copy()
    
    def clear_eol_agent_responses(self) -> None:
        """Clear all tracked EOL agent responses"""
        self.eol_agent_responses.clear()
        logger.info("🧹 Cleared EOL agent response tracking history")
    
    def _extract_software_name_version(self, user_message: str) -> tuple[str, str]:
        """Extract software name and version from user message using improved parsing for compound names"""
        import re
        
        # Initialize default values
        software_name = "unknown"
        version = None
        
        # Convert message to lowercase for easier matching
        message_lower = user_message.lower()
        
        # First, try to extract version using patterns
        version_patterns = [
            r'version\s+([0-9]+(?:\.[0-9]+)*)',
            r'v([0-9]+(?:\.[0-9]+)*)',
            r'([0-9]+(?:\.[0-9]+)*)',
            r'release\s+([0-9]+(?:\.[0-9]+)*)',
        ]
        
        for pattern in version_patterns:
            match = re.search(pattern, message_lower)
            if match:
                version = match.group(1)
                break
        
        # Use centralized SoftwareMappings for name extraction
        from utils import SoftwareMappings
        
        # Check for compound software names first (higher priority)
        for canonical_name, patterns in SoftwareMappings.COMPOUND_PATTERNS.items():
            for pattern in patterns:
                if pattern in message_lower:
                    software_name = canonical_name
                    break
            if software_name != "unknown":
                break
        
        # If no compound name found, check simple software patterns
        if software_name == "unknown":
            for canonical_name, patterns in SoftwareMappings.SIMPLE_PATTERNS.items():
                for pattern in patterns:
                    if pattern in message_lower:
                        software_name = canonical_name
                        break
                if software_name != "unknown":
                    break
        
        # If still no specific software found, try to extract from context
        if software_name == "unknown":
            words = user_message.split()
            for word in words:
                # Skip common words
                if len(word) > 2 and word.lower() not in ['what', 'when', 'does', 'the', 'and', 'for', 'eol', 'end', 'life', 'support', 'date', 'of']:
                    software_name = word
                    break
        
        return software_name, version
    
    async def _collect_inventory_data(self, inventory_type: str) -> Dict[str, Any]:
        """Collect inventory data based on type using specialized inventory analysts"""
        inventory_data = {}
        
        try:
            if inventory_type in ["os", "both"]:
                # Call OSInventoryAnalyst for OS discovery
                if hasattr(self, "os_inventory_specialist") and self.os_inventory_specialist:
                    self._log_agent_interaction("OSInventoryAnalyst", "inventory_collection_request", {
                        "inventory_type": "os",
                        "request_time": time.time()
                    })
                    os_inventory = await self._call_os_inventory_specialist()
                    inventory_data["os_inventory"] = os_inventory
                    self._log_agent_interaction("OSInventoryAnalyst", "inventory_collection_complete", {
                        "response_length": len(str(os_inventory)),
                        "success": True
                    })
                else:
                    inventory_data["os_inventory"] = "OSInventoryAnalyst not available"
            
            if inventory_type in ["software", "both"]:
                # Call SoftwareInventoryAnalyst for software discovery
                if hasattr(self, "software_inventory_specialist") and self.software_inventory_specialist:
                    self._log_agent_interaction("SoftwareInventoryAnalyst", "inventory_collection_request", {
                        "inventory_type": "software",
                        "request_time": time.time()
                    })
                    software_inventory = await self._call_software_inventory_specialist()
                    inventory_data["software_inventory"] = software_inventory
                    self._log_agent_interaction("SoftwareInventoryAnalyst", "inventory_collection_complete", {
                        "response_length": len(str(software_inventory)),
                        "success": True
                    })
                else:
                    inventory_data["software_inventory"] = "SoftwareInventoryAnalyst not available"
                    
        except Exception as e:
            inventory_data["error"] = str(e)
            self._log_error_and_recovery("inventory_collection_failure", {
                "error": str(e),
                "inventory_type": inventory_type
            }, "return_partial_results")
            
        return inventory_data
    
    async def _call_os_inventory_specialist(self) -> str:
        """Call the OS inventory specialist to collect OS information"""
        try:
            # Use Magentic-One tool method directly for real data
            return self._get_os_inventory_tool_sync()
        except Exception as e:
            self._log_error_and_recovery("os_inventory_specialist_error", {"error": str(e)}, "return_error_message")
            return f"Error calling OS inventory specialist: {str(e)}"
    
    async def _call_software_inventory_specialist(self) -> str:
        """Call the software inventory specialist to collect software information"""
        try:
            # Use Magentic-One tool method directly for real data
            return self._get_software_inventory_tool_sync()
        except Exception as e:
            self._log_error_and_recovery("software_inventory_specialist_error", {"error": str(e)}, "return_error_message")
            return f"Error calling software inventory specialist: {str(e)}"
    
    def _parse_inventory_items(self, inventory_response: Dict[str, Any], inventory_type: str) -> List[Dict[str, Any]]:
        """Parse inventory response and extract name/version for each item"""
        parsed_items = []
        
        try:
            # Parse OS inventory
            if "os_inventory" in inventory_response and inventory_response["os_inventory"]:
                os_items = self._parse_os_inventory_items(inventory_response["os_inventory"])
                parsed_items.extend(os_items)
            
            # Parse software inventory
            if "software_inventory" in inventory_response and inventory_response["software_inventory"]:
                software_items = self._parse_software_inventory_items(inventory_response["software_inventory"])
                parsed_items.extend(software_items)
                
        except Exception as e:
            self._log_error_and_recovery("inventory_parsing_error", {"error": str(e)}, "continue_with_partial_results")
        
        return parsed_items
    
    def _parse_os_inventory_items(self, os_inventory: str) -> List[Dict[str, Any]]:
        """Parse OS inventory string and extract OS name/version items"""
        items = []
        
        try:
            # Use existing OS parsing logic if available
            # if hasattr(self, "_parse_os_from_raw_inventory"):
                # os_list = self._parse_os_from_raw_inventory(os_inventory)
                for os_item in os_inventory:
                    # Extract name and version from OS string
                    name = os_item.get("os_name")
                    version = os_item.get("os_version")
                    # name, version = self._extract_name_version_from_os(os_item)
                    items.append({
                        "type": "os",
                        "name": name,
                        "version": version,
                        "raw_string": os_item,
                        "category": "operating_system"
                    })
            # else:
            #     # Fallback parsing
            #     lines = str(os_inventory).split('\n')
            #     for line in lines:
            #         if line.strip():
            #             name, version = self._extract_name_version_from_os(line.strip())
            #             if name:
            #                 items.append({
            #                     "type": "os",
            #                     "name": name,
            #                     "version": version,
            #                     "raw_string": line.strip(),
            #                     "category": "operating_system"
            #                 })
        except Exception as e:
            self._log_error_and_recovery("os_parsing_error", {"error": str(e)}, "skip_os_items")
        
        return items
    
    def _parse_software_inventory_items(self, software_inventory: str) -> List[Dict[str, Any]]:
        """Parse software inventory string and extract software name/version items"""
        items = []
        
        try:
            # Use existing software parsing logic if available
            if hasattr(self, "_parse_software_from_raw_inventory"):
                software_list = self._parse_software_from_raw_inventory(software_inventory)
                for software_item in software_list:
                    name, version = self._extract_name_version_from_software(software_item)
                    items.append({
                        "type": "software",
                        "name": name,
                        "version": version,
                        "raw_string": software_item,
                        "category": "application"
                    })
            else:
                # Fallback parsing
                lines = str(software_inventory).split('\n')
                for line in lines:
                    if line.strip():
                        name, version = self._extract_name_version_from_software(line.strip())
                        if name:
                            items.append({
                                "type": "software",
                                "name": name,
                                "version": version,
                                "raw_string": line.strip(),
                                "category": "application"
                            })
        except Exception as e:
            self._log_error_and_recovery("software_parsing_error", {"error": str(e)}, "skip_software_items")
        
        return items
    
    def _extract_name_version_from_os(self, os_string: str) -> Tuple[str, str]:
        """Extract OS name and version from OS string"""
        import re
        # Special handling for Windows Server to preserve year in name for proper EOL mapping
        # Pattern to capture: "Windows Server 2025 Standard | 10.0 (1)" or "Windows Server 2025 Datacenter Azure Edition"
        windows_server_match = re.search(r'(Windows Server)\s+(\d{4})(?:\s+([^|]+?))?(?:\s*\|.*)?$', os_string, re.IGNORECASE)
        if windows_server_match:
            year = windows_server_match.group(2)
            edition = windows_server_match.group(3).strip() if windows_server_match.group(3) else ""
            # Include year in name for proper Microsoft agent EOL mapping
            full_name = f"Windows Server {year}"
            if edition:
                full_name += f" {edition}"
            # For Windows Server, use the version number (e.g., 10.0) as version if available in original string
            # The Microsoft agent has special logic to handle Windows Server 10.0 and map based on year in name
            version_match = re.search(r'(\d+\.\d+(?:\.\d+)?(?:\.\d+)?)', os_string)
            version = version_match.group(1) if version_match else year
            return full_name.strip(), version
        
        # Common OS patterns for other operating systems
        patterns = [
            r'(Windows)\s+(\d+)',
            r'(Ubuntu)\s+(\d+\.\d+(?:\.\d+)?)',
            r'(Debian)\s+(\d+(?:\.\d+)?)',
            r'(CentOS)\s+(\d+(?:\.\d+)?)',
            r'(Red Hat Enterprise Linux|RHEL)\s+(\d+(?:\.\d+)?)',
            r'(macOS)\s+(\d+\.\d+(?:\.\d+)?)',
            r'(\w+)\s+(\d+(?:\.\d+)*)'  # Generic pattern
        ]
        
        for pattern in patterns:
            match = re.search(pattern, os_string, re.IGNORECASE)
            if match:
                return match.group(1).strip(), match.group(2).strip()
        
        # If no version found, return the whole string as name
        return os_string.strip(), ""
    
    def _extract_name_version_from_software(self, software_string: str) -> Tuple[str, str]:
        """Extract software name and version from software string"""
        import re
        
        # Common software patterns
        patterns = [
            r'(.+?)\s+v?(\d+\.\d+\.\d+(?:\.\d+)?)',  # Name version
            r'(.+?)\s+(\d+\.\d+\.\d+)',
            r'(.+?)\s+(\d+\.\d+)',
            r'(.+?)\s+v(\d+)',
            r'(.+?)\s+(\d{4})',  # Year versions like Office 2019
            r'(.+?)\s+-\s+(.+)',  # Name - Version
        ]
        
        for pattern in patterns:
            match = re.search(pattern, software_string, re.IGNORECASE)
            if match:
                return match.group(1).strip(), match.group(2).strip()
        
        # If no version found, return the whole string as name
        return software_string.strip(), ""
    
    def _determine_eol_specialist_type(self, item: Dict[str, Any]) -> str:
        """Determine the appropriate EOL specialist type for an inventory item (simplified version)"""
        name = item.get("name", "").lower()
        
        # Microsoft products
        if any(keyword in name for keyword in ["windows", "microsoft", "office", "sql server", "exchange", "sharepoint", "azure"]):
            return "microsoft"
        
        # Linux/Ubuntu products
        elif any(keyword in name for keyword in ["ubuntu", "debian", "linux", "centos", "rhel", "red hat", "fedora", "suse"]):
            return "ubuntu"
        
        # Python products
        elif any(keyword in name for keyword in ["python", "django", "flask", "pip", "conda", "jupyter", "pandas", "numpy"]):
            return "python"
        
        # Node.js products
        elif any(keyword in name for keyword in ["nodejs", "node.js", "npm", "node", "express", "react", "vue", "angular"]):
            return "nodejs"
        
        # Oracle products
        elif any(keyword in name for keyword in ["oracle", "java", "jdk", "jre", "mysql", "virtualbox", "solaris"]):
            return "oracle"
        
        # PHP products
        elif any(keyword in name for keyword in ["php", "composer", "laravel", "symfony", "wordpress", "drupal"]):
            return "php"
        
        # PostgreSQL products
        elif any(keyword in name for keyword in ["postgresql", "postgres", "postgis", "pgadmin"]):
            return "postgresql"
        
        # Red Hat products (specific)
        elif any(keyword in name for keyword in ["redhat", "openshift", "ansible"]):
            return "redhat"
        
        # Ubuntu specific (separate from general Linux)
        elif any(keyword in name for keyword in ["snap", "snapcraft", "canonical", "launchpad"]):
            return "ubuntu"
        
        # VMware products
        elif any(keyword in name for keyword in ["vmware", "vsphere", "esxi", "vcenter", "workstation", "fusion"]):
            return "vmware"
        
        # Apache products
        elif any(keyword in name for keyword in ["apache", "httpd", "tomcat", "maven", "spark", "kafka", "cassandra"]):
            return "apache"
        
        # Default to Python specialist for unknown software
        else:
            return "python"
    
    # CONSOLIDATED EOL SPECIALIST CALLING FUNCTIONS
    async def _call_eol_specialist_unified(self, 
                                         specialist_type: str, 
                                         software_name: str, 
                                         version: str = None,
                                         user_message: str = None,
                                         conversation_id: int = None,
                                         start_time: float = None,
                                         cache_key: str = None,
                                         timeout_seconds: int = None) -> Dict[str, Any]:
        """
        Unified EOL specialist calling function that consolidates all duplicate specialist calls
        
        Implements cascading fallback mechanism:
        1. Specialist agents (microsoft, ubuntu, python, etc.) - Direct API/database queries
        2. General EOL agent - EndOfLife API for broad technology coverage  
        3. WebSurfer agent - Internet search when structured data unavailable
        4. Azure AI agent - Modern AI-powered internet search with grounding
        
        Args:
            specialist_type: Type of specialist ('microsoft', 'ubuntu', 'python', 'general', etc.)
            software_name: Name of software to analyze
            version: Version of software (optional)
            response_format: 'direct' for full response, 'tracking' for simple tracking format
            user_message: Original user message (for direct format)
            conversation_id: Conversation ID (for direct format)
            start_time: Start time for tracking
            cache_key: Cache key (for direct format)
            timeout_seconds: Timeout (for direct format)
        
        Returns:
            Dictionary with response in requested format
        """
        if start_time is None:
            start_time = time.time()
            
        try:
            # Get the appropriate agent based on specialist type
            agent_map = {
                'microsoft': self.microsoft_eol_agent,
                'ubuntu': self.ubuntu_eol_agent,
                'python': self.python_eol_agent,
                'nodejs': self.nodejs_eol_agent,
                'oracle': self.oracle_eol_agent,
                'php': self.php_eol_agent,
                'postgresql': self.postgresql_eol_agent,
                'redhat': self.redhat_eol_agent,
                'vmware': self.vmware_eol_agent,
                'apache': self.apache_eol_agent,
                'general': self.endoflife_agent,
                'azure_ai': self.azure_ai_eol_agent,
                'websurfer': self.websurfer_eol_agent,
                'playwright': self.playwright_eol_agent
            }
            
            agent = agent_map.get(specialist_type.lower())
            if not agent:
                raise ValueError(f"Unknown specialist type: {specialist_type}")
            
            # Call agent's get_eol_data method for standardized response
            eol_result = await agent.get_eol_data(software_name, version)
            
            # Handle None result from agent
            if eol_result is None:
                logger.warning(f"⚠️ {specialist_type} agent returned None for {software_name} {version or ''}")
                eol_result = {
                    "success": False,
                    "error": f"{specialist_type} agent returned None",
                    "data": {}
                }
            
            # If General EOL agent fails, implement cascading fallback to internet search agents
            if specialist_type.lower() == 'general' and not eol_result.get("success", False):
                logger.warning(f"⚠️ General EOL agent failed for {software_name} {version or ''}, trying WebSurfer fallback")
                try:
                    # Try WebSurfer first
                    websurfer_result = await self.websurfer_eol_agent.get_eol_data(software_name, version)
                    if websurfer_result is None:
                        websurfer_result = {"success": False, "error": "WebSurfer returned None", "data": {}}
                    
                    if websurfer_result.get("success", False):
                        logger.info(f"✅ WebSurfer fallback successful for {software_name} {version or ''}")
                        eol_result = websurfer_result
                        specialist_type = "websurfer"  # Update for response formatting
                    # disabled for now
                    # else:
                    #     logger.warning(f"⚠️ WebSurfer fallback failed for {software_name} {version or ''}, trying Azure AI fallback")
                    #     # Try Azure AI as final fallback
                    #     azure_ai_result = await self.azure_ai_eol_agent.get_eol_data(software_name, version)
                    #     if azure_ai_result is None:
                    #         azure_ai_result = {"success": False, "error": "Azure AI returned None", "data": {}}
                            
                    #     if azure_ai_result.get("success", False):
                    #         logger.info(f"✅ Azure AI fallback successful for {software_name} {version or ''}")
                    #         eol_result = azure_ai_result
                    #         specialist_type = "azure_ai"  # Update for response formatting
                    #     else:
                    #         logger.error(f"❌ All fallback agents failed for {software_name} {version or ''}")
                except Exception as fallback_error:
                    logger.error(f"❌ Fallback mechanism failed: {fallback_error}")
            
            # Final safety check - ensure eol_result is never None before tracking
            if eol_result is None:
                logger.error(f"❌ eol_result is None after all processing for {software_name} {version or ''}")
                eol_result = {
                    "success": False,
                    "error": "EOL result was None after all processing",
                    "data": {}
                }
            
            # Track the EOL agent response
            specialist_name = f"{specialist_type.title()}EOLSpecialist"
            query_type = f"{specialist_type.lower()}_eol_unified"
            self._track_eol_agent_response(specialist_name, software_name, version, eol_result, 
                                         time.time() - start_time, query_type)
            
            # Return standardized BaseEOLAgent format (matching Playwright response format)
            if eol_result.get("success", False):
                data = eol_result.get("data", {})
                
                # Build response in standard EOL format with markdown headers and structured fields
                response_lines = []
                
                # Determine confidence emoji based on data source
                confidence_emoji = "🎯"  # High confidence for specialist agents
                if data.get("confidence"):
                    confidence_level = data.get("confidence_level", "high")
                    confidence_emoji = {
                        "very_high": "🎯",
                        "high": "✅", 
                        "medium": "⚠️",
                        "low": "❓"
                    }.get(confidence_level, "ℹ️")
                
                # Main header
                response_lines.append(f"## {confidence_emoji} End-of-Life Information for {software_name} {version or ''}")
                response_lines.append("")
                
                # Main EOL data in structured format
                eol_date = data.get('eol_date', 'Unknown')
                response_lines.append(f"**📅 EOL Date:** {eol_date}")
                
                # Add support end date if different from EOL date
                support_end = data.get('support_end_date')
                if support_end and support_end != eol_date and support_end != 'Unknown':
                    response_lines.append(f"**📅 Support End:** {support_end}")
                
                # Add status and risk level
                status = data.get('status', 'Unknown')
                risk_level = data.get('risk_level', 'Unknown')
                response_lines.append(f"**📊 Status:** {status}")
                response_lines.append(f"**⚠️ Risk Level:** {risk_level.title()}")
                
                # Add confidence if available
                if data.get("confidence"):
                    confidence = data.get("confidence", 0.0)
                    confidence_level = data.get("confidence_level", "high")
                    response_lines.append(f"**🎯 Confidence:** {confidence_level.replace('_', ' ').title()} ({int(confidence * 100)}%)")
                
                # Add source as clickable link
                if data.get('source_url'):
                    clickable_url = self._make_url_clickable(data.get('source_url'))
                    response_lines.append("")
                    response_lines.append(f"**🔗 Source:** {clickable_url}")
                
                # Add verification note
                response_lines.append("")
                response_lines.append("*Please verify information with official vendor documentation as data may change.*")
                
                response_text = '\n'.join(response_lines)
                
                return {
                    "specialist": specialist_name,
                    "query": f"{software_name} {version or ''}".strip(),
                    "response": response_text,
                    "status": "success",
                    "eol_data": eol_result
                }
            else:
                error = eol_result.get("error", {})
                error_message = error.get('message', 'Unknown error') if isinstance(error, dict) else str(error)
                
                # Build failure response in standard format
                response_lines = []
                response_lines.append(f"## 🔍 End-of-Life Search for {software_name} {version or ''}")
                response_lines.append("")
                response_lines.append(f"⚠️ {specialist_name} could not find end-of-life information.")
                response_lines.append("")
                response_lines.append("**Possible reasons:**")
                response_lines.append("- The product may still be in active support")
                response_lines.append("- EOL information may not be publicly available yet")
                response_lines.append("- The product name or version may need to be more specific")
                response_lines.append("")
                response_lines.append(f"**Error:** {error_message}")
                response_lines.append("")
                response_lines.append("**💡 Recommendation:** Check the official vendor documentation or support pages for the most up-to-date lifecycle information.")
                
                response_text = '\n'.join(response_lines)
                
                return {
                    "specialist": specialist_name,
                    "query": f"{software_name} {version or ''}".strip(),
                    "response": response_text,
                    "status": "error"
                }
            
                
        except Exception as e:
            logger.error(f"❌ {specialist_type.title()} EOL specialist call failed: {e}")
            
            # Track the failed response
            error_result = {
                "success": False,
                "error": {
                    "message": str(e),
                    "software_name": software_name,
                    "version": version
                }
            }
            specialist_name = f"{specialist_type.title()}EOLSpecialist"
            self._track_eol_agent_response(specialist_name, software_name, version, error_result, 
                                         time.time() - start_time, f"{specialist_type.lower()}_eol_unified")
            
            # Build exception response in standard format
            response_lines = []
            response_lines.append(f"## ❌ Error Searching EOL Information")
            response_lines.append("")
            response_lines.append(f"⚠️ An error occurred while searching for end-of-life information for **{software_name} {version or ''}**.")
            response_lines.append("")
            response_lines.append(f"**Error Details:** {str(e)}")
            response_lines.append("")
            response_lines.append("**💡 Suggestion:** Please try again in a moment, or check the official vendor documentation directly.")
            
            response_text = '\n'.join(response_lines)
            
            return {
                "specialist": specialist_name,
                "query": f"{software_name} {version or ''}".strip(),
                "response": response_text,
                "status": "error"
            }
    
    async def _convert_tracking_to_chat_response(self, tracking_result: Dict[str, Any], user_message: str, conversation_id: int, start_time: float) -> Dict[str, Any]:
        """Convert tracking format response to chat response format for direct calls"""
        if not tracking_result:
            return {
                "response": "No response available",
                "conversation_id": conversation_id,
                "response_time": time.time() - start_time,
                "agent_used": "Unknown",
                "query_type": "unknown",
                "error": "Empty result",
                "agent_communications": [],
                "agents_involved": []
            }
        
        # Extract response content and metadata
        response_content = tracking_result.get("response", "No response available")
        specialist = tracking_result.get("specialist", "Unknown")
        status = tracking_result.get("status", "unknown")
        eol_data = tracking_result.get("eol_data", {})
        
        # Get agent communications from orchestrator logs - CRITICAL FIX
        agent_communications = await self.get_agent_communications()
        
        # Extract unique agents involved
        agents_involved = list(set([
            comm.get("agent", "Unknown") 
            for comm in agent_communications 
            if comm.get("agent")
        ]))
        
        logger.info(f"🔍 [CONVERT] Building chat response with {len(agent_communications)} communications from {len(agents_involved)} agents")
        
        # Build chat response format
        chat_response = {
            "response": response_content,
            "conversation_id": conversation_id,
            "response_time": time.time() - start_time,
            "agent_used": specialist,
            "query_type": f"{specialist.lower()}_eol_unified",
            "eol_data": eol_data,
            "agent_communications": agent_communications,  # CRITICAL: Include communications
            "agents_involved": agents_involved,  # CRITICAL: Include agents list
            "total_exchanges": len(agent_communications),  # Add exchange count
            "session_id": self.session_id,  # Add session ID
            "conversation_messages": []  # Add empty conversation messages for compatibility
        }
        
        # Add error field if status indicates error
        if status == "error":
            chat_response["error"] = "EOL analysis failed"
        
        return chat_response
    
    def _should_trigger_fallback(self, result: Dict[str, Any], name: str, version: str, specialist_name: str) -> bool:
        """
        Determine if we should trigger fallback specialists based on result quality.
        Returns True if the result seems unreliable or incorrect.
        """
        if not result or result.get("status") != "success":
            return True
        
        response = result.get("response", {})
        if not isinstance(response, dict):
            return True
        
        eol_data = response.get("data", {})
        if not eol_data:
            return True
        
        # Check if EOL date seems unrealistic or too old for the software
        eol_date = eol_data.get("eol")
        if eol_date:
            try:
                # Parse date and check if it's reasonable
                from datetime import datetime
                if isinstance(eol_date, str):
                    parsed_date = datetime.fromisoformat(eol_date.replace('Z', '+00:00'))
                    current_year = datetime.now().year
                    
                    # Flag if EOL date is more than 20 years ago (likely wrong for modern software)
                    if parsed_date.year < current_year - 20:
                        logger.warning(f"🚨 Suspicious EOL date {eol_date} for {name} {version} from {specialist_name}")
                        return True
                        
                    # For Windows Server specifically, check if year in name matches expectations
                    if "windows server" in name.lower():
                        year_match = re.search(r'(\d{4})', name)
                        if year_match:
                            name_year = int(year_match.group(1))
                            # Windows Server EOL should be at least 10 years after release
                            if parsed_date.year < name_year + 8:
                                logger.warning(f"🚨 Windows Server {name_year} EOL date {eol_date} seems too early")
                                return True
                                
            except Exception as e:
                logger.debug(f"Could not parse EOL date {eol_date}: {e}")
                return True
        
        # Check confidence score if available
        confidence = response.get("confidence", 1.0)
        if confidence < 0.7:
            logger.warning(f"🚨 Low confidence ({confidence}) from {specialist_name} for {name}")
            return True
        
        return False

    def _correlate_and_format_eol_results(self, eol_analyses: List[Dict[str, Any]], user_message: str) -> Dict[str, Any]:
        """Correlate all EOL analysis results and format into user-friendly format"""
        
        # Categorize results
        successful_analyses = [a for a in eol_analyses if a["status"] == "success"]
        failed_analyses = [a for a in eol_analyses if a["status"] == "error"]
        
        # Group by EOL status
        eol_soon = []
        eol_passed = []
        still_supported = []
        unknown_status = []
        
        for analysis in successful_analyses:
            eol_result = analysis.get("eol_result", {})
            item_name = analysis["item"]["name"]
            item_version = analysis["item"]["version"]
            
            # Extract EOL date information from the result
            eol_date = None
            support_end_date = None
            
            # Try to extract EOL date from different possible locations in the response
            if isinstance(eol_result, dict):
                # Check for structured response with eol_date field
                if "eol_data" in eol_result:
                    eol_date = eol_result["eol_data"].get("data").get("eol_date")
                    support_end_date = eol_result["eol_data"].get("data").get("support_end_date")
                # elif "support_end_date" in eol_result:
                #     support_end_date = eol_result["support_end_date"]
                # elif "response" in eol_result and isinstance(eol_result["response"], dict):
                     # Check nested response object
                #     response_data = eol_result["response"]
                #     eol_date = response_data.get("eol_date") or response_data.get("eol") or response_data.get("end_of_life")
                #     support_end_date = response_data.get("support_end_date") or response_data.get("support_end")
            
            # Determine the relevant date to use
            relevant_date = eol_date or support_end_date
            
            # Parse the date if available
            parsed_date = None
            if relevant_date and relevant_date != "Unknown" and relevant_date != "":
                try:
                    if isinstance(relevant_date, str):
                        # Try different date formats
                        for date_format in ["%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%SZ"]:
                            try:
                                parsed_date = datetime.strptime(relevant_date.replace('Z', ''), date_format.replace('Z', ''))
                                break
                            except ValueError:
                                continue
                        if not parsed_date:
                            # Try ISO format parsing
                            parsed_date = datetime.fromisoformat(relevant_date.replace('Z', '+00:00'))
                except Exception as e:
                    logger.debug(f"Could not parse date {relevant_date}: {e}")
            
            # Categorize based on EOL status and date
            eol_response = eol_result.get("response", "")
            current_date = datetime.now()
            
            item_with_date = {
                "name": item_name, 
                "version": item_version, 
                "analysis": analysis,
                "eol_date": relevant_date,
                "parsed_date": parsed_date
            }
            
            if parsed_date:
                # Use actual date to categorize
                days_until_eol = (parsed_date - current_date).days
                if days_until_eol < 0:
                    eol_passed.append(item_with_date)
                elif days_until_eol < 365:  # Within a year
                    eol_soon.append(item_with_date)
                else:
                    still_supported.append(item_with_date)
            else:
                # Fall back to text analysis
                if any(keyword in str(eol_response).lower() for keyword in ["end of life", "eol", "unsupported", "deprecated"]):
                    if any(keyword in str(eol_response).lower() for keyword in ["2024", "2025", "soon", "approaching"]):
                        eol_soon.append(item_with_date)
                    else:
                        eol_passed.append(item_with_date)
                elif any(keyword in str(eol_response).lower() for keyword in ["supported", "current", "lts", "active"]):
                    still_supported.append(item_with_date)
                else:
                    unknown_status.append(item_with_date)
        
        # Generate summary statistics
        total_items = len(eol_analyses)
        total_success = len(successful_analyses)
        
        # Format final response
        formatted_response = self._generate_formatted_eol_summary(
            eol_soon, eol_passed, still_supported, unknown_status, failed_analyses, total_items, total_success
        )
        
        return {
            "total_items_analyzed": total_items,
            "successful_analyses": total_success,
            "failed_analyses": len(failed_analyses),
            "eol_soon_count": len(eol_soon),
            "eol_passed_count": len(eol_passed),
            "still_supported_count": len(still_supported),
            "unknown_status_count": len(unknown_status),
            "formatted_response": formatted_response,
            "categorized_results": {
                "eol_soon": eol_soon,
                "eol_passed": eol_passed, 
                "still_supported": still_supported,
                "unknown_status": unknown_status,
                "failed_analyses": failed_analyses
            }
        }
    
    def _generate_formatted_eol_summary(self, eol_soon, eol_passed, still_supported, unknown_status, failed_analyses, total_items, total_success) -> str:
        """Generate a user-friendly formatted summary of EOL analysis results"""
        
        response_parts = []
        
        # Header
        response_parts.append(f"# 📊 Inventory EOL Analysis Summary")
        response_parts.append(f"**Total Items Analyzed**: {total_items} | **Successful**: {total_success} | **Failed**: {len(failed_analyses)}")
        response_parts.append("")
        
        # Critical items (EOL soon or passed)
        if eol_soon or eol_passed:
            response_parts.append("## 🚨 **ATTENTION REQUIRED**")
            
            if eol_passed:
                response_parts.append(f"### ❌ **End of Life Reached** ({len(eol_passed)} items)")
                for item in eol_passed[:10]:  # Limit to first 10
                    eol_date_display = ""
                    if item.get('eol_date') and item['eol_date'] != "Unknown":
                        eol_date_display = f" - **EOL Date: {item['eol_date']}**"
                    response_parts.append(f"- **{item['name']}** {item['version']}{eol_date_display} - Requires immediate action")
                if len(eol_passed) > 10:
                    response_parts.append(f"- ... and {len(eol_passed) - 10} more items")
                response_parts.append("")
            
            if eol_soon:
                response_parts.append(f"### ⚠️ **EOL Approaching** ({len(eol_soon)} items)")
                for item in eol_soon[:10]:  # Limit to first 10
                    eol_date_display = ""
                    if item.get('eol_date') and item['eol_date'] != "Unknown":
                        eol_date_display = f" - **EOL Date: {item['eol_date']}**"
                    response_parts.append(f"- **{item['name']}** {item['version']}{eol_date_display} - Plan migration")
                if len(eol_soon) > 10:
                    response_parts.append(f"- ... and {len(eol_soon) - 10} more items")
                response_parts.append("")
        
        # Supported items
        if still_supported:
            response_parts.append(f"## ✅ **Currently Supported** ({len(still_supported)} items)")
            # Show first few items
            for item in still_supported[:5]:
                eol_date_display = ""
                if item.get('eol_date') and item['eol_date'] != "Unknown":
                    eol_date_display = f" - **EOL Date: {item['eol_date']}**"
                response_parts.append(f"- **{item['name']}** {item['version']}{eol_date_display}")
            if len(still_supported) > 5:
                response_parts.append(f"- ... and {len(still_supported) - 5} more supported items")
            response_parts.append("")
        
        # Unknown status
        if unknown_status:
            response_parts.append(f"## ❓ **Status Unknown** ({len(unknown_status)} items)")
            response_parts.append("These items require manual review:")
            for item in unknown_status[:5]:
                eol_date_display = ""
                if item.get('eol_date') and item['eol_date'] != "Unknown":
                    eol_date_display = f" - **Possible EOL Date: {item['eol_date']}**"
                response_parts.append(f"- **{item['name']}** {item['version']}{eol_date_display}")
            if len(unknown_status) > 5:
                response_parts.append(f"- ... and {len(unknown_status) - 5} more items")
            response_parts.append("")
        
        # Failed analyses
        if failed_analyses:
            response_parts.append(f"## ⚠️ **Analysis Failed** ({len(failed_analyses)} items)")
            for failed in failed_analyses[:5]:
                item_name = failed["item"]["name"]
                response_parts.append(f"- **{item_name}** - Could not determine EOL status")
            if len(failed_analyses) > 5:
                response_parts.append(f"- ... and {len(failed_analyses) - 5} more failed items")
            response_parts.append("")
        
        # Recommendations
        response_parts.append("## 💡 **Recommendations**")
        if eol_passed:
            response_parts.append("- **Immediate Action**: Replace or upgrade EOL products")
        if eol_soon:
            response_parts.append("- **Plan Ahead**: Schedule migrations for products approaching EOL")
        if unknown_status or failed_analyses:
            response_parts.append("- **Manual Review**: Research EOL status for unknown items")
        response_parts.append("- **Regular Monitoring**: Set up periodic EOL checks for your inventory")
        
        return "\n".join(response_parts)
    
    def _determine_routing_decision(self, query_type: str, task_type: str) -> str:
        """Determine how to route the request based on query and task type"""
        if task_type == "MIXED_INVENTORY_EOL":
            return "specialized_mixed_inventory_eol_workflow"
        elif task_type == "INVENTORY_ONLY":
            return "inventory_specialists"
        elif task_type == "INTERNET_EOL":
            return "internet_search_agents"
        elif task_type == "EOL_ONLY":
            return "eol_specialists"
        elif query_type in ["os_inventory", "software_inventory"]:
            return "direct_tools"
        else:
            return "magentic_one_team"
    
    def _format_workflow_result_as_chat_response(self, workflow_result: Dict[str, Any], user_message: str, start_time: float, conversation_id: int, cache_key: str) -> Dict[str, Any]:
        """Format workflow result into standard chat response format"""
        
        end_time = time.time()
        response_time = end_time - start_time
        
        # Extract the formatted summary from workflow result
        final_summary = workflow_result.get("final_summary", {})
        formatted_response = final_summary.get("formatted_response", "No results available")
        
        # Create citations from successful EOL analyses
        citations = []
        for analysis in workflow_result.get("eol_analyses", []):
            if analysis.get("status") == "success":
                citations.append({
                    "source": analysis.get("specialist_used", "Unknown"),
                    "query": analysis.get("eol_result", {}).get("query", ""),
                    "type": "eol_analysis"
                })
        
        # Build response metadata
        response_metadata = {
            "workflow_type": "mixed_inventory_eol",
            "steps_completed": workflow_result.get("steps_completed", []),
            "total_items_analyzed": final_summary.get("total_items_analyzed", 0),
            "successful_analyses": final_summary.get("successful_analyses", 0),
            "failed_analyses": final_summary.get("failed_analyses", 0),
            "response_time": response_time,
            "conversation_id": conversation_id,
            "magentic_one_used": False,  # This workflow bypasses Magentic-One
            "specialists_used": list(set([a.get("specialist_used", "") for a in workflow_result.get("eol_analyses", [])]))
        }
        
        # Cache the response
        chat_response = {
            "response": formatted_response,
            "metadata": response_metadata,
            "citations": citations,
            "conversation_history": self.conversation_history,
            "agent_communications": self.agent_interaction_logs[-10:] if len(self.agent_interaction_logs) > 10 else self.agent_interaction_logs,
            "errors": workflow_result.get("errors", [])
        }
        
        # Cache successful responses
        if not workflow_result.get("errors"):
            self._cache_response(cache_key, chat_response)
        
        # Update conversation history
        self.conversation_history.append({
            "timestamp": datetime.now().isoformat(),
            "user_message": user_message,
            "response": formatted_response,
            "metadata": response_metadata,
            "conversation_id": conversation_id
        })
        
        # Log completion
        self._log_orchestrator_event("inventory_eol_workflow_chat_complete", {
            "conversation_id": conversation_id,
            "response_time": response_time,
            "total_items": final_summary.get("total_items_analyzed", 0),
            "successful_analyses": final_summary.get("successful_analyses", 0),
            "user_message_preview": user_message[:100]
        })
        
        return chat_response

    def _format_workflow_result_as_chat_response_with_confirmation(self, workflow_result: Dict[str, Any], user_message: str, start_time: float, conversation_id: int, confirmed: bool, original_message: str) -> Dict[str, Any]:
        """Format workflow result into standard chat response format with confirmation context"""
        
        end_time = time.time()
        response_time = end_time - start_time
        
        # Extract the formatted summary from workflow result
        final_summary = workflow_result.get("final_summary", {})
        formatted_response = final_summary.get("formatted_response", "No results available")
        
        # Create citations from successful EOL analyses
        citations = []
        for analysis in workflow_result.get("eol_analyses", []):
            if analysis.get("status") == "success":
                citations.append({
                    "source": analysis.get("specialist_used", "Unknown"),
                    "query": analysis.get("eol_result", {}).get("query", ""),
                    "type": "eol_analysis"
                })
        
        # Build response metadata with confirmation context
        response_metadata = {
            "workflow_type": "mixed_inventory_eol",
            "steps_completed": workflow_result.get("steps_completed", []),
            "total_items_analyzed": final_summary.get("total_items_analyzed", 0),
            "successful_analyses": final_summary.get("successful_analyses", 0),
            "failed_analyses": final_summary.get("failed_analyses", 0),
            "response_time": response_time,
            "conversation_id": conversation_id,
            "magentic_one_used": False,  # This workflow bypasses Magentic-One
            "specialists_used": list(set([a.get("specialist_used", "") for a in workflow_result.get("eol_analyses", [])])),
            "confirmation_context": {
                "confirmed": confirmed,
                "original_message": original_message
            }
        }
        
        # Build chat response
        chat_response = {
            "response": formatted_response,
            "metadata": response_metadata,
            "citations": citations,
            "conversation_history": self.conversation_history,
            "agent_communications": self.agent_interaction_logs[-10:] if len(self.agent_interaction_logs) > 10 else self.agent_interaction_logs,
            "errors": workflow_result.get("errors", []),
            "system": "magentic_one_confirmation",
            "session_id": self.session_id
        }
        
        # Update conversation history
        self.conversation_history.append({
            "timestamp": datetime.now().isoformat(),
            "user_message": user_message,
            "response": formatted_response,
            "metadata": response_metadata,
            "conversation_id": conversation_id,
            "confirmation_context": {
                "confirmed": confirmed,
                "original_message": original_message
            }
        })
        
        # Log completion with confirmation context
        self._log_orchestrator_event("inventory_eol_workflow_confirmation_complete", {
            "conversation_id": conversation_id,
            "response_time": response_time,
            "total_items": final_summary.get("total_items_analyzed", 0),
            "successful_analyses": final_summary.get("successful_analyses", 0),
            "user_message_preview": user_message[:100],
            "confirmation_context": {
                "confirmed": confirmed,
                "original_message": original_message[:100] if original_message else None
            }
        })
        
        return chat_response

    def _init_orchestrator_logging(self):
        """Initialize comprehensive orchestrator logging structures"""
        self.init_start_time = time.time()
        
        # Orchestrator behavior logs
        self.orchestrator_logs = []
        self.agent_interaction_logs = []
        self.task_planning_logs = []
        self.performance_metrics = defaultdict(list)
        
        # Track conversation flow
        self.conversation_flow = []
        
        # Agent usage statistics
        self.agent_usage_stats = defaultdict(int)
        self.tool_usage_stats = defaultdict(int)
        self.failed_request_count = 0
        self.successful_request_count = 0
        
        # Enhanced monitoring
        self.error_patterns = defaultdict(int)
        self.response_time_tracking = []
        self.agent_performance_tracking = defaultdict(list)
        
        # Error and recovery tracking
        self.error_logs = []
        self.recovery_actions = []
        
        # Resource usage tracking  
        self.memory_usage_tracking = []
        self.concurrent_request_tracking = []
        
        # Initialization flags for lazy loading
        self._traditional_agents_initialized = False
        self._magentic_one_initialized = False
    
    def _initialize_agent(self, agent_type: str):
        """
        Centralized agent factory that handles all agent initialization in one place.
        This eliminates redundant agent instantiation code scattered across multiple methods.
        
        Args:
            agent_type: The type of agent to initialize (e.g., 'websurfer', 'azure_ai', 'microsoft', etc.)
            
        Returns:
            The initialized agent instance or None if initialization fails
        """
        try:
            if agent_type == 'websurfer':
                return WebsurferEOLAgent(self.model_client)
            elif agent_type == 'azure_ai':
                # Azure AI Agent Service (Modern replacement for deprecated Bing Search)
                return AzureAIAgentEOLAgent()
            elif agent_type == 'microsoft':
                return MicrosoftEOLAgent()
            elif agent_type == 'ubuntu':
                return UbuntuEOLAgent()
            elif agent_type == 'python':
                return PythonEOLAgent()
            elif agent_type == 'nodejs':
                return NodeJSEOLAgent()
            elif agent_type == 'oracle':
                return OracleEOLAgent()
            elif agent_type == 'php':
                return PHPEOLAgent()
            elif agent_type == 'postgresql':
                return PostgreSQLEOLAgent()
            elif agent_type == 'redhat':
                return RedHatEOLAgent()
            elif agent_type == 'vmware':
                return VMwareEOLAgent()
            elif agent_type == 'apache':
                return ApacheEOLAgent()
            elif agent_type == 'general':
                return EndOfLifeAgent()
            elif agent_type == 'playwright':
                return PlaywrightEOLAgent()
            else:
                logger.warning(f"⚠️ Unknown agent type: {agent_type}")
                return None
                
        except Exception as e:
            logger.error(f"❌ Failed to initialize {agent_type} agent: {e}")
            return None

    def _create_log_entry(self, log_type: str, **kwargs) -> Dict[str, Any]:
        """
        Helper method to create standardized log entries with common fields.
        Reduces code duplication across logging methods.
        
        Args:
            log_type: The type of log entry (orchestrator_event, agent_interaction, task_planning)
            **kwargs: Additional fields specific to the log type
            
        Returns:
            Dictionary with standardized log structure
        """
        # Cache commonly used values to avoid repeated calculations
        timestamp = datetime.now().isoformat()
        conversation_id = len(self.conversation_history)
        
        base_log = {
            "timestamp": timestamp,
            "session_id": self.session_id,
            "conversation_id": conversation_id
        }
        
        # Add specific fields based on log type
        base_log.update(kwargs)
        return base_log

    # Lazy loading properties for all agents
    @property
    def websurfer_eol_agent(self):
        """Lazy loading for WebSurfer EOL agent"""
        if not hasattr(self, '_websurfer_eol_agent'):
            self._websurfer_eol_agent = self._initialize_agent('websurfer')
        return self._websurfer_eol_agent

    @property
    def azure_ai_eol_agent(self):
        """Lazy loading for Azure AI EOL agent"""
        if not hasattr(self, '_azure_ai_eol_agent'):
            self._azure_ai_eol_agent = self._initialize_agent('azure_ai')
        return self._azure_ai_eol_agent

    @property
    def microsoft_eol_agent(self):
        """Lazy loading for Microsoft EOL agent"""
        if not hasattr(self, '_microsoft_eol_agent'):
            self._microsoft_eol_agent = self._initialize_agent('microsoft')
        return self._microsoft_eol_agent

    @property
    def ubuntu_eol_agent(self):
        """Lazy loading for Ubuntu EOL agent"""
        if not hasattr(self, '_ubuntu_eol_agent'):
            self._ubuntu_eol_agent = self._initialize_agent('ubuntu')
        return self._ubuntu_eol_agent

    @property
    def python_eol_agent(self):
        """Lazy loading for Python EOL agent"""
        if not hasattr(self, '_python_eol_agent'):
            self._python_eol_agent = self._initialize_agent('python')
        return self._python_eol_agent

    @property
    def nodejs_eol_agent(self):
        """Lazy loading for NodeJS EOL agent"""
        if not hasattr(self, '_nodejs_eol_agent'):
            self._nodejs_eol_agent = self._initialize_agent('nodejs')
        return self._nodejs_eol_agent

    @property
    def oracle_eol_agent(self):
        """Lazy loading for Oracle EOL agent"""
        if not hasattr(self, '_oracle_eol_agent'):
            self._oracle_eol_agent = self._initialize_agent('oracle')
        return self._oracle_eol_agent

    @property
    def php_eol_agent(self):
        """Lazy loading for PHP EOL agent"""
        if not hasattr(self, '_php_eol_agent'):
            self._php_eol_agent = self._initialize_agent('php')
        return self._php_eol_agent

    @property
    def postgresql_eol_agent(self):
        """Lazy loading for PostgreSQL EOL agent"""
        if not hasattr(self, '_postgresql_eol_agent'):
            self._postgresql_eol_agent = self._initialize_agent('postgresql')
        return self._postgresql_eol_agent

    @property
    def redhat_eol_agent(self):
        """Lazy loading for RedHat EOL agent"""
        if not hasattr(self, '_redhat_eol_agent'):
            self._redhat_eol_agent = self._initialize_agent('redhat')
        return self._redhat_eol_agent

    @property
    def vmware_eol_agent(self):
        """Lazy loading for VMware EOL agent"""
        if not hasattr(self, '_vmware_eol_agent'):
            self._vmware_eol_agent = self._initialize_agent('vmware')
        return self._vmware_eol_agent

    @property
    def apache_eol_agent(self):
        """Lazy loading for Apache EOL agent"""
        if not hasattr(self, '_apache_eol_agent'):
            self._apache_eol_agent = self._initialize_agent('apache')
        return self._apache_eol_agent

    @property
    def endoflife_agent(self):
        """Lazy loading for General EOL agent (EndOfLife API)"""
        if not hasattr(self, '_endoflife_agent'):
            self._endoflife_agent = self._initialize_agent('general')
        return self._endoflife_agent

    @property
    def playwright_eol_agent(self):
        """Lazy loading for Playwright EOL agent"""
        if not hasattr(self, '_playwright_eol_agent'):
            self._playwright_eol_agent = self._initialize_agent('playwright')
        return self._playwright_eol_agent

    def _setup_magentic_one_agents(self):
        """Setup specialized agents for Magentic-One system with comprehensive logging"""
        
        if not MAGENTIC_ONE_IMPORTS_OK:
            logger.warning("⚠️ Magentic-One not available - cannot setup agents")
            self._log_error_and_recovery("magentic_one_unavailable", 
                {"imports_ok": False}, 
                "fallback_to_traditional_agents")
            return
        
        logger.info("🔧 Setting up Magentic-One specialized agents...")
        agents_init_start = time.time()
        
        self._log_orchestrator_event("magentic_one_agents_setup_start", {
            "agent_count": 15,
            "agents": ["OSInventoryAnalyst", "SoftwareInventoryAnalyst", "MicrosoftEOLSpecialist", "PythonEOLSpecialist", "NodeJSEOLSpecialist", "OracleEOLSpecialist", "PHPEOLSpecialist", "PostgreSQLEOLSpecialist", "RedHatEOLSpecialist", "UbuntuEOLSpecialist", "VMwareEOLSpecialist", "ApacheEOLSpecialist", "AzureAIEOLSpecialist", "WebSurferEOLSpecialist", "PlaywrightEOLSpecialist"]
        })
        
        initialized_agents = []
        failed_agents = []
        
        # OS Inventory Analysis Agent
        try:
            agent_start = time.time()
            self.os_inventory_specialist = AssistantAgent(
                name="OSInventoryAnalyst",
                model_client=self.model_client,
                system_message="""You are an expert OS Inventory Analysis Agent in a Magentic-One multi-agent system.

**PRIMARY MISSION**: Operating system discovery, categorization, and analysis across IT environments.

**CORE CAPABILITIES**:
- Operating system discovery and identification
- Platform categorization (Windows, Linux distributions, macOS, etc.)
- Version detection and build information analysis
- Hardware-OS compatibility assessment
- OS licensing and support status evaluation

**AUTONOMOUS OPERATION**:
- Execute OS inventory collection when asked about operating systems or platforms
- Provide comprehensive OS summaries with versions, patch levels, and categorizations
- Coordinate with EOL specialists for OS lifecycle analysis
- Present data in executive-ready format with business insights

**SPECIALIZED TOOLS**:
- get_os_inventory_tool: Complete operating system discovery and classification

**RESPONSE EXCELLENCE**:
- Lead with strategic OS portfolio insights and standardization opportunities
- Categorize operating systems by vendor, version, support status, and criticality
- Include recommendations for OS standardization and upgrade planning
- Highlight security, licensing, and compliance considerations for OS infrastructure

You operate with full autonomy to discover, analyze, and report on OS assets.""",
                tools=[
                    self._get_os_inventory_tool_sync  # Use sync wrapper for Magentic-One
                ]
                )
            agent_time = time.time() - agent_start
            logger.info("✅ OSInventoryAnalyst agent initialized")
            initialized_agents.append("OSInventoryAnalyst")
            self._log_agent_interaction("OSInventoryAnalyst", "initialization", {
                "status": "success",
                "initialization_time": agent_time,
                "tools_count": 1
            })
        except Exception as e:
            logger.error(f"❌ Failed to initialize OSInventoryAnalyst: {e}")
            failed_agents.append({"agent": "OSInventoryAnalyst", "error": str(e)})
            self.os_inventory_specialist = None
            self._log_error_and_recovery("agent_init_failure", 
                {"agent": "OSInventoryAnalyst", "error": str(e), "traceback": traceback.format_exc()}, 
                "continue_with_partial_functionality")
        
        # Software Inventory Analysis Agent
        try:
            agent_start = time.time()
            self.software_inventory_specialist = AssistantAgent(
                name="SoftwareInventoryAnalyst",
                model_client=self.model_client,
                system_message="""You are an expert Software Inventory Analysis Agent in a Magentic-One multi-agent system.

**PRIMARY MISSION**: Software application discovery, analysis, and portfolio management across IT environments.

**CORE CAPABILITIES**:
- Software application discovery and enumeration
- Version detection and license analysis
- Application categorization and vendor mapping
- Usage pattern analysis and optimization insights
- Software asset relationship mapping and dependency analysis

**AUTONOMOUS OPERATION**:
- Execute software inventory collection when asked about applications, packages, or software
- Provide comprehensive software summaries with versions, licenses, and categorizations
- Coordinate with EOL specialists for software lifecycle analysis
- Present data in executive-ready format with business insights

**SPECIALIZED TOOLS**:
- get_software_inventory_tool: Detailed software application analysis and enumeration

**RESPONSE EXCELLENCE**:
- Lead with strategic software portfolio insights and optimization opportunities
- Categorize software by vendor, type, criticality, and standardization level
- Include recommendations for software portfolio optimization and risk mitigation
- Highlight licensing, security, and compliance considerations for software assets

You operate with full autonomy to discover, analyze, and report on software assets.""",
                tools=[
                    self._get_software_inventory_tool_sync  # Use sync wrapper for Magentic-One
                ]
                )
            agent_time = time.time() - agent_start
            logger.info("✅ SoftwareInventoryAnalyst agent initialized")
            initialized_agents.append("SoftwareInventoryAnalyst")
            self._log_agent_interaction("SoftwareInventoryAnalyst", "initialization", {
                "status": "success",
                "initialization_time": agent_time,
                "tools_count": 1
            })
        except Exception as e:
            logger.error(f"❌ Failed to initialize SoftwareInventoryAnalyst: {e}")
            failed_agents.append({"agent": "SoftwareInventoryAnalyst", "error": str(e)})
            self.software_inventory_specialist = None
            self._log_error_and_recovery("agent_init_failure", 
                {"agent": "SoftwareInventoryAnalyst", "error": str(e), "traceback": traceback.format_exc()}, 
                "continue_with_partial_functionality")
        
        # Microsoft EOL Specialist Agent
        try:
            agent_start = time.time()
            self.microsoft_eol_specialist = AssistantAgent(
                name="MicrosoftEOLSpecialist",
                model_client=self.model_client,
                system_message="""You are a specialized Microsoft End-of-Life Analysis Agent in a Magentic-One system.

**EXPERTISE DOMAIN**: Microsoft product lifecycles, support timelines, and migration strategies using web research.

**INVENTORY-GROUNDED ANALYSIS**: When provided with inventory context from the InventoryAnalyst, focus your EOL analysis on the specific Microsoft products found in the user's environment. Prioritize analysis of products that are actually deployed.

**CORE RESPONSIBILITIES**:
- Windows OS EOL analysis (Server, Desktop, all versions) via web search
- SQL Server lifecycle and extended support planning from official sources
- Office 365 and Microsoft 365 transition guidance with web citations
- Azure services and cloud migration EOL considerations from Microsoft docs
- Microsoft development stack EOL (Visual Studio, .NET, etc.) with official sources

**WEB SEARCH TOOLS**:
- web_search_microsoft_eol_tool: Comprehensive web search for Microsoft product lifecycle information with citations

**AUTONOMOUS OPERATION**:
- Use web search to find current Microsoft EOL information from official sources
- When inventory context is available, focus analysis on deployed Microsoft products
- Provide detailed upgrade paths and migration strategies with source citations
- Include extended support options and commercial considerations with web references
- Assess business impact and migration complexity using the latest web information

**RESPONSE EXCELLENCE**:
- Start with inventory-specific findings when available (e.g., "Based on your deployed Windows Server 2016...")
- Provide definitive Microsoft EOL dates with web source citations
- Include mainstream vs extended support distinctions from official pages
- Offer clear upgrade recommendations with business justification and web sources
- Address licensing implications and cost considerations with cited references
- Always include source URLs and citation information for verification

You are the authoritative source for Microsoft product lifecycle analysis using comprehensive web research, enhanced with inventory awareness.""",
                tools=[
                    self._get_software_inventory_tool_sync  # Access to software inventory data
                ]
            )
            agent_time = time.time() - agent_start
            logger.info("✅ MicrosoftEOLSpecialist agent initialized")
            initialized_agents.append("MicrosoftEOLSpecialist")
            self._log_agent_interaction("MicrosoftEOLSpecialist", "initialization", {
                "status": "success",
                "initialization_time": agent_time,
                "tools_count": 1
            })
        except Exception as e:
            logger.error(f"❌ Failed to initialize MicrosoftEOLSpecialist: {e}")
            failed_agents.append({"agent": "MicrosoftEOLSpecialist", "error": str(e)})
            self.microsoft_eol_specialist = None
            self._log_error_and_recovery("agent_init_failure", 
                {"agent": "MicrosoftEOLSpecialist", "error": str(e), "traceback": traceback.format_exc()}, 
                "continue_with_partial_functionality")
        
        # Ubuntu/Linux EOL Specialist Agent
        try:
            agent_start = time.time()
            self.ubuntu_eol_specialist = AssistantAgent(
            name="UbuntuEOLSpecialist",
            model_client=self.model_client,
            system_message="""You are a specialized Linux Distribution End-of-Life Analysis Agent in a Magentic-One system.

**EXPERTISE DOMAIN**: Ubuntu, Debian, and Linux distribution lifecycles using web research.

**INVENTORY-GROUNDED ANALYSIS**: When provided with inventory context from the InventoryAnalyst, focus your EOL analysis on the specific Linux distributions and open-source software found in the user's environment. Prioritize analysis of systems and packages that are actually deployed.

**CORE RESPONSIBILITIES**:
- Ubuntu LTS vs standard release lifecycle analysis via web search
- Extended Security Maintenance (ESM) planning and value assessment from official sources
- Linux distribution upgrade path planning with web citations
- Kernel and package EOL coordination using current web information
- Open source support ecosystem navigation with web references

**WEB SEARCH TOOLS**:
- web_search_ubuntu_eol_tool: Ubuntu and Linux distribution lifecycle web search with citations

**AUTONOMOUS OPERATION**:
- Use web search to find current Linux distribution EOL information from official sources
- When inventory context is available, focus analysis on deployed Linux systems and software
- Distinguish between LTS and standard release timelines using web data
- Evaluate ESM eligibility and commercial support options with web citations
- Provide enterprise-grade migration strategies with sourced references

**RESPONSE EXCELLENCE**:
- Start with inventory-specific findings when available (e.g., "Based on your Ubuntu 18.04 systems...")
- Clearly distinguish LTS vs standard support cycles with web source citations
- Include ESM availability and value proposition with official documentation
- Offer comprehensive upgrade strategies for enterprise environments with web references
- Address compliance and security considerations with cited sources
- Always include source URLs and citation information for verification

You are the authoritative source for Linux distribution lifecycle analysis using comprehensive web research, enhanced with inventory awareness.""",
                tools=[
                    self._get_software_inventory_tool_sync  # Access to software inventory data
                ]
            )
            agent_time = time.time() - agent_start
            logger.info("✅ UbuntuEOLSpecialist agent initialized")
            initialized_agents.append("UbuntuEOLSpecialist")
            self._log_agent_interaction("UbuntuEOLSpecialist", "initialization", {
                "status": "success",
                "initialization_time": agent_time,
                "tools_count": 1
            })
        except Exception as e:
            logger.error(f"❌ Failed to initialize UbuntuEOLSpecialist: {e}")
            failed_agents.append({"agent": "UbuntuEOLSpecialist", "error": str(e)})
            self.ubuntu_eol_specialist = None
            self._log_error_and_recovery("agent_init_failure", 
                {"agent": "UbuntuEOLSpecialist", "error": str(e), "traceback": traceback.format_exc()}, 
                "continue_with_partial_functionality")
        
        # Python EOL Specialist Agent
        try:
            agent_start = time.time()
            self.python_eol_specialist = AssistantAgent(
                name="PythonEOLSpecialist", 
                model_client=self.model_client,
                system_message="""You are a specialized Python End-of-Life Analysis Agent in a Magentic-One system.

**EXPERTISE DOMAIN**: Python language versions, package lifecycles, and ecosystem migration strategies.

**CORE RESPONSIBILITIES**:
- Python version EOL analysis (Python 2.7, 3.x series) via web search
- PyPI package lifecycle and dependency analysis from official sources
- Django, Flask, and framework migration planning with web citations
- Virtual environment and package management best practices
- Security patch availability and CVE analysis with web references

**AUTONOMOUS OPERATION**: Use web search to find current Python ecosystem EOL information from official sources.""",
                tools=[self._get_software_inventory_tool_sync]
            )
            agent_time = time.time() - agent_start
            logger.info("✅ PythonEOLSpecialist agent initialized")
            initialized_agents.append("PythonEOLSpecialist")
        except Exception as e:
            logger.error(f"❌ Failed to initialize PythonEOLSpecialist: {e}")
            failed_agents.append({"agent": "PythonEOLSpecialist", "error": str(e)})
            self.python_eol_specialist = None
            
        # Node.js EOL Specialist Agent
        try:
            agent_start = time.time()
            self.nodejs_eol_specialist = AssistantAgent(
                name="NodeJSEOLSpecialist",
                model_client=self.model_client,
                system_message="""You are a specialized Node.js End-of-Life Analysis Agent in a Magentic-One system.

**EXPERTISE DOMAIN**: Node.js runtime versions, npm package ecosystems, and JavaScript framework lifecycles.

**CORE RESPONSIBILITIES**:
- Node.js LTS and current release lifecycle analysis via web search
- npm package vulnerability and EOL assessment from official sources
- React, Angular, Vue.js framework migration planning with web citations
- Package dependency analysis and security considerations
- Frontend/backend JavaScript ecosystem EOL coordination with web references

**AUTONOMOUS OPERATION**: Use web search to find current Node.js ecosystem EOL information from official sources.""",
                tools=[self._get_software_inventory_tool_sync]
            )
            agent_time = time.time() - agent_start
            logger.info("✅ NodeJSEOLSpecialist agent initialized")
            initialized_agents.append("NodeJSEOLSpecialist")
        except Exception as e:
            logger.error(f"❌ Failed to initialize NodeJSEOLSpecialist: {e}")
            failed_agents.append({"agent": "NodeJSEOLSpecialist", "error": str(e)})
            self.nodejs_eol_specialist = None
            
        # Oracle EOL Specialist Agent
        try:
            agent_start = time.time()
            self.oracle_eol_specialist = AssistantAgent(
                name="OracleEOLSpecialist",
                model_client=self.model_client,
                system_message="""You are a specialized Oracle End-of-Life Analysis Agent in a Magentic-One system.

**EXPERTISE DOMAIN**: Oracle database versions, middleware products, and enterprise software lifecycles.

**CORE RESPONSIBILITIES**:
- Oracle Database version EOL and extended support analysis via web search
- WebLogic, Fusion Middleware lifecycle planning from official sources
- Java SE/EE version coordination with Oracle support policies
- Oracle Cloud migration considerations and timeline planning
- Enterprise licensing and support cost analysis with web references

**AUTONOMOUS OPERATION**: Use web search to find current Oracle product EOL information from official sources.""",
                tools=[self._get_software_inventory_tool_sync]
            )
            agent_time = time.time() - agent_start
            logger.info("✅ OracleEOLSpecialist agent initialized")
            initialized_agents.append("OracleEOLSpecialist")
        except Exception as e:
            logger.error(f"❌ Failed to initialize OracleEOLSpecialist: {e}")
            failed_agents.append({"agent": "OracleEOLSpecialist", "error": str(e)})
            self.oracle_eol_specialist = None
            
        # PHP EOL Specialist Agent
        try:
            agent_start = time.time()
            self.php_eol_specialist = AssistantAgent(
                name="PHPEOLSpecialist",
                model_client=self.model_client,
                system_message="""You are a specialized PHP End-of-Life Analysis Agent in a Magentic-One system.

**EXPERTISE DOMAIN**: PHP language versions, framework lifecycles, and web application migration strategies.

**CORE RESPONSIBILITIES**:
- PHP version EOL analysis and security support timelines via web search
- Laravel, Symfony, WordPress framework migration planning from official sources
- Composer package dependency analysis and vulnerability assessment
- Web server compatibility and migration considerations
- LAMP/LEMP stack coordination and upgrade planning with web references

**AUTONOMOUS OPERATION**: Use web search to find current PHP ecosystem EOL information from official sources.""",
                tools=[self._get_software_inventory_tool_sync]
            )
            agent_time = time.time() - agent_start
            logger.info("✅ PHPEOLSpecialist agent initialized")
            initialized_agents.append("PHPEOLSpecialist")
        except Exception as e:
            logger.error(f"❌ Failed to initialize PHPEOLSpecialist: {e}")
            failed_agents.append({"agent": "PHPEOLSpecialist", "error": str(e)})
            self.php_eol_specialist = None
            
        # PostgreSQL EOL Specialist Agent
        try:
            agent_start = time.time()
            self.postgresql_eol_specialist = AssistantAgent(
                name="PostgreSQLEOLSpecialist",
                model_client=self.model_client,
                system_message="""You are a specialized PostgreSQL End-of-Life Analysis Agent in a Magentic-One system.

**EXPERTISE DOMAIN**: PostgreSQL database versions, extension lifecycles, and migration strategies.

**CORE RESPONSIBILITIES**:
- PostgreSQL major version EOL and support timeline analysis via web search
- Extension and plugin compatibility assessment from official sources
- Database migration planning and compatibility considerations
- High availability and replication version coordination
- Cloud PostgreSQL service migration planning with web references

**AUTONOMOUS OPERATION**: Use web search to find current PostgreSQL EOL information from official sources.""",
                tools=[self._get_software_inventory_tool_sync]
            )
            agent_time = time.time() - agent_start
            logger.info("✅ PostgreSQLEOLSpecialist agent initialized")
            initialized_agents.append("PostgreSQLEOLSpecialist")
        except Exception as e:
            logger.error(f"❌ Failed to initialize PostgreSQLEOLSpecialist: {e}")
            failed_agents.append({"agent": "PostgreSQLEOLSpecialist", "error": str(e)})
            self.postgresql_eol_specialist = None
            
        # Red Hat EOL Specialist Agent
        try:
            agent_start = time.time()
            self.redhat_eol_specialist = AssistantAgent(
                name="RedHatEOLSpecialist",
                model_client=self.model_client,
                system_message="""You are a specialized Red Hat End-of-Life Analysis Agent in a Magentic-One system.

**EXPERTISE DOMAIN**: Red Hat Enterprise Linux, middleware, and enterprise solution lifecycles.

**CORE RESPONSIBILITIES**:
- RHEL version EOL and Extended Life Cycle Support analysis via web search
- Red Hat OpenShift, Ansible, and middleware lifecycle planning from official sources
- Subscription management and support tier coordination
- Migration planning for enterprise Red Hat environments
- Hybrid cloud and container platform EOL considerations with web references

**AUTONOMOUS OPERATION**: Use web search to find current Red Hat product EOL information from official sources.""",
                tools=[self._get_software_inventory_tool_sync]
            )
            agent_time = time.time() - agent_start
            logger.info("✅ RedHatEOLSpecialist agent initialized")
            initialized_agents.append("RedHatEOLSpecialist")
        except Exception as e:
            logger.error(f"❌ Failed to initialize RedHatEOLSpecialist: {e}")
            failed_agents.append({"agent": "RedHatEOLSpecialist", "error": str(e)})
            self.redhat_eol_specialist = None
            
        # VMware EOL Specialist Agent
        try:
            agent_start = time.time()
            self.vmware_eol_specialist = AssistantAgent(
                name="VMwareEOLSpecialist",
                model_client=self.model_client,
                system_message="""You are a specialized VMware End-of-Life Analysis Agent in a Magentic-One system.

**EXPERTISE DOMAIN**: VMware virtualization products, cloud solutions, and infrastructure lifecycles.

**CORE RESPONSIBILITIES**:
- vSphere, ESXi version EOL and support timeline analysis via web search
- VMware Cloud Foundation and NSX lifecycle planning from official sources
- Virtual infrastructure migration and compatibility assessment
- Licensing model changes and support transition planning
- Alternative virtualization platform evaluation with web references

**AUTONOMOUS OPERATION**: Use web search to find current VMware product EOL information from official sources.""",
                tools=[self._get_software_inventory_tool_sync]
            )
            agent_time = time.time() - agent_start
            logger.info("✅ VMwareEOLSpecialist agent initialized")
            initialized_agents.append("VMwareEOLSpecialist")
        except Exception as e:
            logger.error(f"❌ Failed to initialize VMwareEOLSpecialist: {e}")
            failed_agents.append({"agent": "VMwareEOLSpecialist", "error": str(e)})
            self.vmware_eol_specialist = None
            
        # Apache EOL Specialist Agent
        try:
            agent_start = time.time()
            self.apache_eol_specialist = AssistantAgent(
                name="ApacheEOLSpecialist",
                model_client=self.model_client,
                system_message="""You are a specialized Apache End-of-Life Analysis Agent in a Magentic-One system.

**EXPERTISE DOMAIN**: Apache web server, middleware, and open-source project lifecycles.

**CORE RESPONSIBILITIES**:
- Apache HTTP Server version EOL and security support analysis via web search
- Apache Tomcat, Kafka, Spark lifecycle planning from official sources
- Web server security and performance migration considerations
- Module and extension compatibility assessment
- Alternative web server evaluation and migration planning with web references

**AUTONOMOUS OPERATION**: Use web search to find current Apache project EOL information from official sources.""",
                tools=[self._get_software_inventory_tool_sync]
            )
            agent_time = time.time() - agent_start
            logger.info("✅ ApacheEOLSpecialist agent initialized")
            initialized_agents.append("ApacheEOLSpecialist")
        except Exception as e:
            logger.error(f"❌ Failed to initialize ApacheEOLSpecialist: {e}")
            failed_agents.append({"agent": "ApacheEOLSpecialist", "error": str(e)})
            self.apache_eol_specialist = None
            
        # Azure AI EOL Specialist Agent
        try:
            agent_start = time.time()
            self.azure_ai_eol_specialist = AssistantAgent(
                name="AzureAIEOLSpecialist",
                model_client=self.model_client,
                system_message="""You are a specialized Azure AI-Powered End-of-Life Analysis Agent in a Magentic-One system.

**EXPERTISE DOMAIN**: Advanced EOL analysis using Azure AI Agent Service with Bing grounding for comprehensive web research.

**CORE RESPONSIBILITIES**:
- Advanced EOL analysis using Azure AI Agent Service with real-time web grounding
- Cross-platform software lifecycle research with AI-enhanced accuracy
- Complex technology stack EOL coordination and analysis
- Emerging technology and cloud service lifecycle assessment
- AI-powered trend analysis and migration recommendation generation

**AUTONOMOUS OPERATION**: Use Azure AI Agent Service with Bing grounding for comprehensive EOL research across all technology platforms.""",
                tools=[self._get_software_inventory_tool_sync]
            )
            agent_time = time.time() - agent_start
            logger.info("✅ AzureAIEOLSpecialist agent initialized")
            initialized_agents.append("AzureAIEOLSpecialist")
        except Exception as e:
            logger.error(f"❌ Failed to initialize AzureAIEOLSpecialist: {e}")
            failed_agents.append({"agent": "AzureAIEOLSpecialist", "error": str(e)})
            self.azure_ai_eol_specialist = None
            
        # WebSurfer EOL Specialist Agent
        try:
            agent_start = time.time()
            self.websurfer_eol_specialist = AssistantAgent(
                name="WebSurferEOLSpecialist",
                model_client=self.model_client,
                system_message="""You are a specialized Web Research End-of-Life Analysis Agent in a Magentic-One system.

**EXPERTISE DOMAIN**: Comprehensive web research for EOL information across all technology platforms and vendors.

**CORE RESPONSIBILITIES**:
- Comprehensive web research for EOL information across all technology platforms
- Vendor documentation analysis and official source verification
- Community-driven project lifecycle assessment and analysis
- Cross-reference verification of EOL dates and support timelines
- Alternative solution research and migration pathway identification

**AUTONOMOUS OPERATION**: Use advanced web surfing capabilities to research EOL information from official sources, vendor documentation, and community resources.""",
                tools=[self._get_software_inventory_tool_sync]
            )
            agent_time = time.time() - agent_start
            logger.info("✅ WebSurferEOLSpecialist agent initialized")
            initialized_agents.append("WebSurferEOLSpecialist")
        except Exception as e:
            logger.error(f"❌ Failed to initialize WebSurferEOLSpecialist: {e}")
            failed_agents.append({"agent": "WebSurferEOLSpecialist", "error": str(e)})
            self.websurfer_eol_specialist = None
        
        # Playwright EOL Specialist Agent
        try:
            agent_start = time.time()
            self.playwright_eol_specialist = AssistantAgent(
                name="PlaywrightEOLSpecialist",
                model_client=self.model_client,
                system_message="""You are a specialized Playwright-based End-of-Life Analysis Agent in a Magentic-One system.

**EXPERTISE DOMAIN**: Headless browser automation for EOL information extraction from search engines and official documentation.

**INVENTORY-GROUNDED ANALYSIS**: When provided with inventory context from the InventoryAnalyst, focus your EOL analysis on the specific software and operating systems found in the user's environment. Prioritize analysis of products that are actually deployed.

**CORE RESPONSIBILITIES**:
- Headless Chromium-based EOL information extraction from Bing search results
- Multi-selector fallback strategy for robust data extraction
- International date format recognition and confidence scoring
- Container-friendly browser configuration for production environments
- Enhanced date pattern matching with very_high/high/medium/low confidence levels

**WEB SEARCH TOOLS**:
- Uses Playwright async API with headless Chromium to search Bing for EOL dates
- Extracts structured EOL information from search result snippets
- Provides source URLs for verification

**AUTONOMOUS OPERATION**:
- When inventory context is available, focus analysis on deployed systems and software
- Use Playwright to navigate Bing search and extract EOL information
- Try multiple CSS selectors for robust extraction (.b_ans, .answer_container, [data-snippet], etc.)
- Parse dates in multiple international formats ("31 May 2025", "January 12, 2027", etc.)
- Return structured response with confidence scoring

**RESPONSE EXCELLENCE**:
- Start with inventory-specific findings when available (e.g., "Based on your deployed Windows Server 2016...")
- Provide EOL dates with confidence scores (very_high 95%, high 85%, medium 70%, low 50%)
- Include source URLs from Bing search results
- Offer clear upgrade recommendations when EOL is approaching
- Always include disclaimers to verify with official documentation

**TECHNICAL CAPABILITIES**:
- Headless mode by default (configurable via PLAYWRIGHT_HEADLESS env var)
- Container-safe browser args (--no-sandbox, --disable-setuid-sandbox, etc.)
- Multi-selector fallback for varying Bing HTML structures
- Enhanced logging for debugging and monitoring

You are the authoritative source for Playwright-based EOL research, enhanced with inventory awareness and confidence scoring.""",
                tools=[self._get_software_inventory_tool_sync]
            )
            agent_time = time.time() - agent_start
            logger.info("✅ PlaywrightEOLSpecialist agent initialized")
            initialized_agents.append("PlaywrightEOLSpecialist")
        except Exception as e:
            logger.error(f"❌ Failed to initialize PlaywrightEOLSpecialist: {e}")
            failed_agents.append({"agent": "PlaywrightEOLSpecialist", "error": str(e)})
            self.playwright_eol_specialist = None
        
        # Log final agent initialization summary
        total_agents_time = time.time() - agents_init_start
        
        logger.info(f"✅ Magentic-One specialized agents initialized: {len(initialized_agents)}/{len(initialized_agents) + len(failed_agents)} successful")
        
        self._log_orchestrator_event("magentic_one_agents_setup_complete", {
            "total_initialization_time": total_agents_time,
            "initialized_agents": initialized_agents,
            "failed_agents": failed_agents,
            "success_rate": len(initialized_agents) / (len(initialized_agents) + len(failed_agents)) if (initialized_agents or failed_agents) else 1.0
        })
        
        self._log_performance_metric("agent_setup_time", total_agents_time, {
            "agent_count": len(initialized_agents) + len(failed_agents),
            "successful_agents": len(initialized_agents)
        })
    
    def _setup_magentic_one_team(self):
        """Setup Magentic-One team with orchestrator and specialized agents"""
        
        if not MAGENTIC_ONE_IMPORTS_OK:
            logger.warning("⚠️ Magentic-One not available - cannot setup team")
            self.team = None
            return
        
        logger.info("🔧 Setting up Magentic-One team with orchestrator...")
        
        # Create the agent list for Magentic-One team
        agents = [
            self.os_inventory_specialist,
            self.software_inventory_specialist,
            self.microsoft_eol_specialist, 
            self.ubuntu_eol_specialist
        ]
        
        # Create Magentic-One team with built-in orchestrator
        try:
            # Configure team to use only our specialized agents, disable web surfing
            self.team = MagenticOneGroupChat(
                participants=agents,
                model_client=self.model_client,
                termination_condition=MaxMessageTermination(max_messages=20),
                # WebSurfer functionality handled by WebsurferEOLAgent class
                web_surfer=self.websurfer_eol_agent
            )
            logger.info("✅ Magentic-One team initialized with orchestrator and specialized agents (WebSurfer functionality via WebsurferEOLAgent)")
            
        except TypeError:
            # Fallback if web_surfer parameter is not supported
            try:
                self.team = MagenticOneGroupChat(
                    participants=agents,
                    model_client=self.model_client,
                    termination_condition=MaxMessageTermination(max_messages=20)
                )
                logger.info("✅ Magentic-One team initialized with orchestrator and specialized agents (fallback mode)")
            except Exception as fallback_error:
                logger.error(f"❌ Failed to initialize Magentic-One team (fallback): {fallback_error}")
                self.team = None
                
        except Exception as e:
            logger.error(f"❌ Failed to initialize Magentic-One team: {e}")
            self.team = None
    
    async def chat(self, user_message: str, timeout_seconds: int = 60) -> Dict[str, Any]:
        """
        Main chat interface using Magentic-One orchestrator system
        
        Args:
            user_message: User's input message
            timeout_seconds: Maximum time to wait for response
            
        Returns:
            Dict containing response, metadata, and conversation details
        """
        
        start_time = time.time()
        conversation_id = len(self.conversation_history) + 1
        
        # Performance optimization: Lazy load Magentic-One components only when needed
        self._ensure_magentic_one_initialized()
        
        # Log chat initiation
        self._log_orchestrator_event("chat_session_start", {
            "user_message_preview": user_message[:200] + "..." if len(user_message) > 200 else user_message,
            "user_message_length": len(user_message),
            "timeout_seconds": timeout_seconds,
            "conversation_id": conversation_id,
            "magentic_one_available": MAGENTIC_ONE_IMPORTS_OK and self.team is not None
        })
        
        try:
            logger.info(f"🎯 Processing user message with Magentic-One: {user_message[:100]}...")
            
            # Performance optimization: Check cache for common queries
            cache_key = self._generate_cache_key(user_message, timeout_seconds)
            cached_response = self._get_cached_response(cache_key)
            if cached_response:
                logger.info("⚡ Returning cached response for performance")
                self._log_orchestrator_event("cache_hit", {
                    "cache_key": cache_key[:50] + "...",
                    "conversation_id": conversation_id
                })
                return cached_response
            
            if not MAGENTIC_ONE_IMPORTS_OK or not self.team:
                # Fallback to direct tool execution if Magentic-One not available
                self._log_orchestrator_event("fallback_to_direct_response", {
                    "reason": "magentic_one_unavailable" if not MAGENTIC_ONE_IMPORTS_OK else "team_not_initialized"
                })
                return await self._fallback_direct_response(user_message)
            
            # Enhanced query classification for intelligent routing
            query_type, task_type = self._classify_request(user_message)
            
            self._log_orchestrator_event("query_classification", {
                "user_message_preview": user_message[:100],
                "classified_as": query_type,
                "task_type": task_type,
                "routing_decision": self._determine_routing_decision(query_type, task_type)
            })
            
            # Route INVENTORY_ONLY tasks to appropriate inventory specialists
            if task_type == "INVENTORY_ONLY":
                return await self._route_inventory_only_task(user_message, conversation_id, start_time, cache_key)
            
            # Route INTERNET_EOL tasks directly to internet search agents
            if task_type == "INTERNET_EOL":
                return await self._route_internet_eol_task(user_message, conversation_id, start_time, cache_key, timeout_seconds)
            
            # Route EOL_ONLY tasks to appropriate EOL specialists  
            if task_type == "EOL_ONLY":
                return await self._route_eol_only_task(user_message, conversation_id, start_time, cache_key, timeout_seconds)
            
            # Route MIXED_INVENTORY_EOL to specialized workflow
            if task_type == "MIXED_INVENTORY_EOL":
                logger.info(f"🔄 Routing to specialized mixed inventory+EOL workflow")
                self._log_orchestrator_event("specialized_workflow_routing", {
                    "workflow_type": "mixed_inventory_eol",
                    "user_message_preview": user_message[:100],
                    "reason": "mixed_inventory_eol_task_detected"
                })
                
                planning_data = {
                    "task": user_message,
                    "task_type": task_type,
                    "conversation_id": conversation_id,
                    "timeout_seconds": timeout_seconds
                }
                
                workflow_result = await self.execute_mixed_inventory_eol_workflow(user_message, planning_data)
                
                # Format workflow result into standard chat response
                return self._format_workflow_result_as_chat_response(workflow_result, user_message, start_time, conversation_id, cache_key)
            
            # Route simple inventory queries directly to tools for performance
            if query_type in ["os_inventory", "software_inventory"]:
                logger.info(f"🎯 Routing {query_type} query directly to tools for optimal performance")
                self._log_orchestrator_event("performance_optimization", {
                    "optimization_type": "direct_tool_routing",
                    "query_type": query_type,
                    "reason": "simple_inventory_query_optimization"
                })
                return await self._fallback_direct_response(user_message)
            
            # Use Magentic-One team for complex analysis requiring agent coordination
            logger.info(f"🚀 Running Magentic-One team conversation for {query_type} analysis...")
            
            # Log task planning initiation with enhanced orchestrator reasoning
            self._log_task_planning("task_initiation", {
                "task": user_message,
                "available_agents": ["InventoryAnalyst", "MicrosoftEOLSpecialist", "PythonEOLSpecialist", "NodeJSEOLSpecialist", "OracleEOLSpecialist", "PHPEOLSpecialist", "PostgreSQLEOLSpecialist", "RedHatEOLSpecialist", "UbuntuEOLSpecialist", "VMwareEOLSpecialist", "ApacheEOLSpecialist", "AzureAIEOLSpecialist", "WebSurferEOLSpecialist"],
                "orchestrator": "MagenticOneGroupChat",
                "session_context": {
                    "conversation_id": conversation_id,
                    "timeout_constraint": timeout_seconds,
                    "processing_mode": "comprehensive"
                }
            })
            
            # Log orchestrator coordination strategy
            self._log_orchestrator_event("agent_coordination_start", {
                "coordination_strategy": "adaptive_specialist_selection",
                "quality_requirements": "high_accuracy_with_citations",
                "expected_workflow": ["task_analysis", "agent_selection", "web_search", "validation", "synthesis"],
                "performance_targets": {
                    "response_time": f"<{timeout_seconds}s",
                    "citation_count": ">=2",
                    "accuracy_threshold": ">90%"
                }
            })
            
            # Execute the task using Magentic-One's orchestrator
            # The orchestrator automatically handles task planning, agent coordination, and progress tracking
            self._log_orchestrator_event("task_execution_start", {
                "execution_mode": "magentic_one_orchestrator",
                "task_complexity": self._assess_task_complexity(user_message),
                "resource_allocation": "full_specialist_team",
                "monitoring_level": "comprehensive"
            })
            
            team_execution_start = time.time()
            
            # Handle async generator from run_stream with timeout
            result = None
            try:
                # Set a shorter timeout for team execution (30 seconds)
                team_timeout = min(30, timeout_seconds * 0.5)
                # team.run_stream may return either an async generator or a coroutine
                # that resolves to an async generator. Handle both cases.
                stream_candidate = self.team.run_stream(task=user_message)
                if asyncio.iscoroutine(stream_candidate):
                    try:
                        stream_result = await stream_candidate
                    except Exception as e:
                        logger.exception("Error awaiting team.run_stream coroutine during team execution")
                        # Fall back to a simple iterator that yields the exception
                        async def _error_gen():
                            yield repr(e)
                        stream_result = _error_gen()
                else:
                    stream_result = stream_candidate
                
                # Collect all results from the async generator with timeout
                async for chunk in stream_result:
                    result = chunk  # Keep the latest result
                    
                    # Check if we've exceeded the team timeout
                    current_execution_time = time.time() - team_execution_start
                    if current_execution_time > team_timeout:
                        self._log_orchestrator_event("team_timeout_exceeded", {
                            "timeout_limit": team_timeout,
                            "execution_time": current_execution_time,
                            "fallback_action": "direct_tool_response"
                        })
                        # Force fallback to direct response
                        return await self._fallback_direct_response(user_message, conversation_id)
                        
            except Exception as e:
                team_execution_time = time.time() - team_execution_start
                error_message = str(e)
                
                # Check if this is a web surfing error
                if "web_surfer" in error_message.lower() or "multimodalwebsurfer" in error_message.lower():
                    self._log_orchestrator_event("web_surfing_error_detected", {
                        "error": error_message,
                        "execution_time": team_execution_time,
                        "fallback_action": "direct_tool_response_without_web_search"
                    })
                    logger.warning("⚠️ Web surfing error detected, falling back to direct tools")
                else:
                    self._log_orchestrator_event("team_execution_error", {
                        "error": error_message,
                        "execution_time": team_execution_time,
                        "fallback_action": "direct_tool_response"
                    })
                
                # Fallback to direct response on any team execution error
                return await self._fallback_direct_response(user_message, conversation_id)
            
            team_execution_time = time.time() - team_execution_start
            
            # Log task execution completion with orchestrator analysis
            self._log_task_planning("task_execution_complete", {
                "execution_time": team_execution_time,
                "result_type": type(result).__name__,
                "orchestrator_assessment": {
                    "execution_efficiency": "optimal" if team_execution_time < timeout_seconds * 0.5 else "acceptable",
                    "resource_utilization": "balanced",
                    "quality_achieved": "comprehensive"
                }
            })
            
            # Log orchestrator decision-making for result processing
            self._log_orchestrator_event("result_processing_start", {
                "processing_strategy": "extract_and_validate",
                "validation_criteria": ["response_completeness", "citation_presence", "accuracy_indicators"],
                "synthesis_approach": "comprehensive_summary_with_sources"
            })
            
            processing_time = time.time() - start_time
            
            # Extract the final response from Magentic-One results
            if hasattr(result, 'messages') and result.messages:
                final_message = result.messages[-1]
                response_content = getattr(final_message, 'content', str(result))
                
                # Log message analysis
                self._log_orchestrator_event("response_extraction", {
                    "total_messages": len(result.messages),
                    "final_message_sender": getattr(final_message, 'source', 'unknown'),
                    "response_length": len(response_content)
                })
            else:
                response_content = str(result)
                self._log_orchestrator_event("response_extraction", {
                    "total_messages": 0,
                    "fallback_to_string": True,
                    "response_length": len(response_content)
                })
            
            # Track conversation
            conversation_entry = {
                "timestamp": datetime.now().isoformat(),
                "user_message": user_message,
                "response": response_content,
                "processing_time": processing_time,
                "system": "magentic_one",
                "conversation_id": conversation_id
            }
            self.conversation_history.append(conversation_entry)
            
            # Log conversation flow
            self.conversation_flow.append({
                "conversation_id": conversation_id,
                "timestamp": datetime.now().isoformat(),
                "flow_type": "magentic_one_orchestrated",
                "user_input_length": len(user_message),
                "response_length": len(response_content),
                "processing_time": processing_time,
                "team_execution_time": team_execution_time
            })
            
            # Log performance metrics
            self._log_performance_metric("chat_processing_time", processing_time, {
                "system": "magentic_one",
                "team_execution_time": team_execution_time,
                "overhead_time": processing_time - team_execution_time,
                "conversation_id": conversation_id
            })
            
            # Analyze response for success indicators
            response_analysis = {
                "contains_data": any(keyword in response_content.lower() for keyword in ['server', 'windows', 'linux', 'software', 'version']),
                "contains_eol_info": any(keyword in response_content.lower() for keyword in ['end of life', 'eol', 'support ends', 'deprecated']),
                "contains_recommendations": any(keyword in response_content.lower() for keyword in ['recommend', 'suggest', 'upgrade', 'migrate']),
                "error_indicators": any(keyword in response_content.lower() for keyword in ['error', 'failed', 'unable', 'timeout'])
            }
            
            self._log_orchestrator_event("response_analysis", response_analysis)
            
            # Log successful completion
            self._log_orchestrator_event("chat_session_complete", {
                "conversation_id": conversation_id,
                "total_processing_time": processing_time,
                "team_execution_time": team_execution_time,
                "response_analysis": response_analysis,
                "success": True
            })
            
            logger.info(f"✅ Magentic-One chat completed successfully in {processing_time:.2f}s")
            
            # Cache the response for performance on similar queries
            response_data = {
                "response": response_content,
                "agents_used": ["MagenticOneOrchestrator", "InventoryAnalyst", "MicrosoftEOLSpecialist", "PythonEOLSpecialist", "NodeJSEOLSpecialist", "OracleEOLSpecialist", "PHPEOLSpecialist", "PostgreSQLEOLSpecialist", "RedHatEOLSpecialist", "UbuntuEOLSpecialist", "VMwareEOLSpecialist", "ApacheEOLSpecialist", "AzureAIEOLSpecialist", "WebSurferEOLSpecialist"],
                "processing_time": processing_time,
                "session_id": self.session_id,
                "system": "magentic_one",
                "conversation_id": conversation_id,
                "metadata": {
                    "orchestrator": "MagenticOneOrchestrator",
                    "planning": "Autonomous task decomposition and coordination",
                    "specialized_agents": 14,
                    "timeout_seconds": timeout_seconds,
                    "team_execution_time": team_execution_time,
                    "response_analysis": response_analysis
                }
            }
            
            # Cache the response for future similar queries
            self._cache_response(cache_key, response_data)
            
            return response_data
            
        except Exception as e:
            error_time = time.time() - start_time
            logger.error(f"❌ Magentic-One chat failed: {e}")
            
            # Log error details
            self._log_error_and_recovery("chat_session_failure", {
                "conversation_id": conversation_id,
                "error": str(e),
                "traceback": traceback.format_exc(),
                "processing_time_before_error": error_time,
                "user_message_preview": user_message[:200]
            }, "fallback_to_direct_response")
            
            self._log_orchestrator_event("chat_session_complete", {
                "conversation_id": conversation_id,
                "total_processing_time": error_time,
                "success": False,
                "error": str(e)
            })
            processing_time = time.time() - start_time
            
            # Fallback to direct response in case of error
            return await self._fallback_direct_response(user_message, error=str(e))
    
    async def chat_with_confirmation(
        self, 
        message: str, 
        confirmed: bool = False, 
        original_message: str = None,
        timeout_seconds: int = 60
    ) -> Dict[str, Any]:
        """
        Chat interface with user confirmation handling for Magentic-One orchestrator system
        
        Args:
            message: User's input message or confirmation response
            confirmed: Whether the user has confirmed an action
            original_message: Original message if this is a confirmation response
            timeout_seconds: Maximum time to wait for response
            
        Returns:
            Dict containing response, metadata, and conversation details
        """
        
        start_time = time.time()
        conversation_id = len(self.conversation_history) + 1
        
        # Log chat with confirmation initiation
        self._log_orchestrator_event("chat_with_confirmation_start", {
            "message_preview": message[:200] + "..." if len(message) > 200 else message,
            "message_length": len(message),
            "confirmed": confirmed,
            "has_original_message": original_message is not None,
            "timeout_seconds": timeout_seconds,
            "conversation_id": conversation_id,
            "magentic_one_available": MAGENTIC_ONE_IMPORTS_OK and self.team is not None
        })
        
        try:
            # Handle confirmation logic
            if confirmed and original_message:
                # User confirmed - proceed with original action
                self._log_orchestrator_event("user_confirmation_received", {
                    "original_message": original_message[:200],
                    "confirmation_message": message[:200],
                    "action": "proceeding_with_confirmed_request"
                })
                
                # Use the original message for processing
                processing_message = original_message
            elif not confirmed and original_message:
                # User declined - provide alternative response
                self._log_orchestrator_event("user_confirmation_declined", {
                    "original_message": original_message[:200],
                    "decline_message": message[:200],
                    "action": "providing_alternative_response"
                })
                
                # Provide a helpful response without executing the declined action
                response_content = (
                    "I understand you've decided not to proceed with that action. "
                    "Is there anything else I can help you with regarding your infrastructure analysis? "
                    "I can provide information, recommendations, or analysis without making any changes."
                )
                
                processing_time = time.time() - start_time
                
                return {
                    "response": response_content,
                    "agents_used": ["MagenticOneOrchestrator"],
                    "processing_time": processing_time,
                    "session_id": self.session_id,
                    "system": "magentic_one_confirmation",
                    "conversation_id": conversation_id,
                    "metadata": {
                        "orchestrator": "MagenticOneOrchestrator",
                        "confirmation_status": "declined",
                        "action_taken": "alternative_response_provided",
                        "timeout_seconds": timeout_seconds
                    }
                }
            else:
                # Regular message processing
                processing_message = message
            
            logger.info(f"🎯 Processing message with confirmation handling: {processing_message[:100]}...")
            
            if not MAGENTIC_ONE_IMPORTS_OK or not self.team:
                # Fallback to direct tool execution if Magentic-One not available
                self._log_orchestrator_event("fallback_to_direct_response", {
                    "reason": "magentic_one_unavailable" if not MAGENTIC_ONE_IMPORTS_OK else "team_not_initialized",
                    "confirmation_context": True
                })
                return await self._fallback_direct_response_with_confirmation(
                    processing_message, confirmed, original_message
                )
            
            # Enhanced query classification for intelligent routing
            query_type, task_type = self._classify_request(processing_message)
            self._log_orchestrator_event("query_classification", {
                "user_message_preview": processing_message[:100],
                "classified_as": query_type,
                "task_type": task_type,
                "routing_decision": "specialized_workflow" if task_type in ["EOL_ONLY", "MIXED_INVENTORY_EOL", "INTERNET_EOL", "INVENTORY_ONLY"] else "magentic_one_team",
                "confirmation_context": True
            })
            
            # Route INVENTORY_ONLY tasks to appropriate inventory specialists
            if task_type == "INVENTORY_ONLY":
                logger.info(f"🎯 Routing INVENTORY_ONLY task directly to inventory specialists")
                self._log_orchestrator_event("performance_optimization", {
                    "optimization_type": "direct_inventory_routing",
                    "query_type": query_type,
                    "task_type": task_type,
                    "reason": "inventory_only_query_optimization",
                    "confirmation_context": True
                })
                # Generate cache key for inventory routing
                cache_key = self._generate_cache_key(processing_message, timeout_seconds)
                return await self._route_inventory_only_task(
                    processing_message, conversation_id, start_time, cache_key
                )
            
            # Route INTERNET_EOL tasks directly to internet search agents
            if task_type == "INTERNET_EOL":
                logger.info(f"🎯 Routing INTERNET_EOL task directly to internet search specialists")
                self._log_orchestrator_event("performance_optimization", {
                    "optimization_type": "direct_internet_eol_routing",
                    "query_type": query_type,
                    "task_type": task_type,
                    "reason": "internet_eol_query_optimization",
                    "confirmation_context": True
                })
                # Generate cache key for internet EOL routing
                cache_key = self._generate_cache_key(processing_message, timeout_seconds)
                return await self._route_internet_eol_task(
                    processing_message, conversation_id, start_time, cache_key, timeout_seconds
                )
            
            # Route EOL_ONLY tasks to appropriate EOL specialists  
            if task_type == "EOL_ONLY":
                logger.info(f"🎯 Routing EOL_ONLY task directly to EOL specialists")
                self._log_orchestrator_event("performance_optimization", {
                    "optimization_type": "direct_eol_routing",
                    "query_type": query_type,
                    "task_type": task_type,
                    "reason": "eol_only_query_optimization",
                    "confirmation_context": True
                })
                # Generate cache key for EOL routing
                cache_key = self._generate_cache_key(processing_message, timeout_seconds)
                return await self._route_eol_only_task(
                    processing_message, conversation_id, start_time, cache_key, timeout_seconds
                )
            
            # Route MIXED_INVENTORY_EOL to specialized workflow
            if task_type == "MIXED_INVENTORY_EOL":
                logger.info(f"🔄 Routing to specialized mixed inventory+EOL workflow with confirmation context")
                self._log_orchestrator_event("specialized_workflow_routing", {
                    "workflow_type": "mixed_inventory_eol",
                    "user_message_preview": processing_message[:100],
                    "reason": "mixed_inventory_eol_task_detected",
                    "confirmation_context": True
                })
                
                # Create a conversation_id for this workflow
                conversation_id = len(self.conversation_history) + 1
                
                planning_data = {
                    "task": processing_message,
                    "task_type": task_type,
                    "conversation_id": conversation_id,
                    "timeout_seconds": timeout_seconds,
                    "confirmation_context": {
                        "confirmed": confirmed,
                        "original_message": original_message
                    }
                }
                
                workflow_result = await self.execute_mixed_inventory_eol_workflow(processing_message, planning_data)
                
                # Format workflow result into standard chat response with confirmation context
                return self._format_workflow_result_as_chat_response_with_confirmation(
                    workflow_result, processing_message, start_time, conversation_id, confirmed, original_message
                )
            
            # Route simple inventory queries directly to tools for performance (legacy support)
            if query_type in ["os_inventory", "software_inventory"]:
                logger.info(f"🎯 Routing {query_type} query (task_type: {task_type}) directly to tools for optimal performance")
                self._log_orchestrator_event("performance_optimization", {
                    "optimization_type": "direct_tool_routing",
                    "query_type": query_type,
                    "task_type": task_type,
                    "reason": "simple_inventory_query_optimization",
                    "confirmation_context": True
                })
                return await self._fallback_direct_response_with_confirmation(
                    processing_message, confirmed, original_message
                )
            
            # Use Magentic-One team for complex analysis requiring agent coordination
            logger.info(f"🚀 Running Magentic-One team conversation for {query_type} analysis with confirmation context...")
            
            # Log task planning initiation with confirmation context
            self._log_task_planning("task_initiation_with_confirmation", {
                "task": processing_message,
                "confirmation_context": {
                    "confirmed": confirmed,
                    "has_original": original_message is not None
                },
                "available_agents": ["InventoryAnalyst", "MicrosoftEOLSpecialist", "PythonEOLSpecialist", "NodeJSEOLSpecialist", "OracleEOLSpecialist", "PHPEOLSpecialist", "PostgreSQLEOLSpecialist", "RedHatEOLSpecialist", "UbuntuEOLSpecialist", "VMwareEOLSpecialist", "ApacheEOLSpecialist", "AzureAIEOLSpecialist", "WebSurferEOLSpecialist"],
                "orchestrator": "MagenticOneGroupChat",
                "session_context": {
                    "conversation_id": conversation_id,
                    "timeout_constraint": timeout_seconds,
                    "processing_mode": "confirmation_aware"
                }
            })
            
            # Execute the task using Magentic-One's orchestrator
            team_execution_start = time.time()
            
            # Ensure team is in a clean state before running
            try:
                # Check if team is already running and reset if needed
                if hasattr(self.team, '_running') and getattr(self.team, '_running', False):
                    logger.warning("⚠️ Team appears to be running, attempting to reset...")
                    # Force reset team state if possible
                    if hasattr(self.team, 'reset'):
                        await self.team.reset()
                    elif hasattr(self.team, '_running'):
                        setattr(self.team, '_running', False)
            except Exception as reset_error:
                logger.warning(f"⚠️ Team reset failed: {reset_error}")
            
            # Handle async generator from run_stream with timeout
            result = None
            try:
                # Set a shorter timeout for team execution (30 seconds)
                team_timeout = min(30, timeout_seconds * 0.5)
                # team.run_stream may return either an async generator or a coroutine
                # that resolves to an async generator. Handle both cases.
                stream_candidate = self.team.run_stream(task=processing_message)
                if asyncio.iscoroutine(stream_candidate):
                    try:
                        stream_result = await stream_candidate
                    except Exception as e:
                        logger.exception("Error awaiting team.run_stream coroutine during processing_message execution")
                        async def _error_gen2():
                            yield repr(e)
                        stream_result = _error_gen2()
                else:
                    stream_result = stream_candidate
                
                # Collect all results from the async generator with timeout
                async for chunk in stream_result:
                    result = chunk  # Keep the latest result
                    
                    # Check if we've exceeded the team timeout
                    current_execution_time = time.time() - team_execution_start
                    if current_execution_time > team_timeout:
                        self._log_orchestrator_event("team_timeout_exceeded_confirmation", {
                            "timeout_limit": team_timeout,
                            "execution_time": current_execution_time,
                            "fallback_action": "direct_tool_response_with_confirmation",
                            "confirmation_context": True
                        })
                        # Force fallback to direct response with confirmation context
                        return await self._fallback_direct_response_with_confirmation(
                            processing_message, confirmed, original_message
                        )
                        
            except ValueError as ve:
                if "already running" in str(ve):
                    logger.warning("⚠️ Team was already running, falling back to direct response")
                    return await self._fallback_direct_response_with_confirmation(
                        processing_message, confirmed, original_message
                    )
                else:
                    raise ve
            except Exception as e:
                team_execution_time = time.time() - team_execution_start
                error_message = str(e)
                
                # Check if this is a web surfing error
                if "web_surfer" in error_message.lower() or "multimodalwebsurfer" in error_message.lower():
                    self._log_orchestrator_event("web_surfing_error_detected_confirmation", {
                        "error": error_message,
                        "execution_time": team_execution_time,
                        "fallback_action": "direct_tool_response_with_confirmation_without_web_search",
                        "confirmation_context": True
                    })
                    logger.warning("⚠️ Web surfing error detected in confirmation context, falling back to direct tools")
                else:
                    self._log_orchestrator_event("team_execution_error_confirmation", {
                        "error": error_message,
                        "execution_time": team_execution_time,
                        "fallback_action": "direct_tool_response_with_confirmation",
                        "confirmation_context": True
                    })
                
                # Fallback to direct response on any team execution error
                return await self._fallback_direct_response_with_confirmation(
                    processing_message, confirmed, original_message
                )
            
            team_execution_time = time.time() - team_execution_start
            
            # Extract response content similar to regular chat method
            if hasattr(result, 'messages') and result.messages:
                final_message = result.messages[-1]
                response_content = getattr(final_message, 'content', str(result))
            else:
                response_content = str(result)
            
            processing_time = time.time() - start_time
            
            # Track conversation with confirmation context
            conversation_entry = {
                "timestamp": datetime.now().isoformat(),
                "user_message": message,
                "original_message": original_message,
                "confirmed": confirmed,
                "response": response_content,
                "processing_time": processing_time,
                "system": "magentic_one_confirmation",
                "conversation_id": conversation_id
            }
            self.conversation_history.append(conversation_entry)
            
            # Log successful completion with confirmation context
            self._log_orchestrator_event("chat_with_confirmation_complete", {
                "conversation_id": conversation_id,
                "total_processing_time": processing_time,
                "team_execution_time": team_execution_time,
                "confirmation_status": "confirmed" if confirmed else "initial_request",
                "success": True
            })
            
            logger.info(f"✅ Magentic-One chat with confirmation completed successfully in {processing_time:.2f}s")
            
            return {
                "response": response_content,
                "agents_used": ["MagenticOneOrchestrator", "InventoryAnalyst", "MicrosoftEOLSpecialist", "PythonEOLSpecialist", "NodeJSEOLSpecialist", "OracleEOLSpecialist", "PHPEOLSpecialist", "PostgreSQLEOLSpecialist", "RedHatEOLSpecialist", "UbuntuEOLSpecialist", "VMwareEOLSpecialist", "ApacheEOLSpecialist", "AzureAIEOLSpecialist", "WebSurferEOLSpecialist"],
                "processing_time": processing_time,
                "session_id": self.session_id,
                "system": "magentic_one_confirmation",
                "conversation_id": conversation_id,
                "total_exchanges": len(self.agent_interaction_logs),
                "agents_involved": list(set(log.get("agent_name", "unknown") for log in self.agent_interaction_logs[-20:])),
                "conversation_messages": [{"role": "user", "content": message}, {"role": "assistant", "content": response_content}],
                "agent_communications": self.agent_interaction_logs[-10:] if len(self.agent_interaction_logs) > 10 else self.agent_interaction_logs,
                "metadata": {
                    "orchestrator": "MagenticOneOrchestrator",
                    "planning": "Autonomous task decomposition with confirmation awareness",
                    "specialized_agents": 14,
                    "timeout_seconds": timeout_seconds,
                    "team_execution_time": team_execution_time,
                    "confirmation_status": "confirmed" if confirmed else "initial_request",
                    "original_message_provided": original_message is not None,
                    "total_agent_interactions": len(self.agent_interaction_logs)
                }
            }
            
        except Exception as e:
            error_time = time.time() - start_time
            logger.error(f"❌ Magentic-One chat with confirmation failed: {e}")
            
            # Log error details with confirmation context
            self._log_error_and_recovery("chat_with_confirmation_failure", {
                "conversation_id": conversation_id,
                "error": str(e),
                "traceback": traceback.format_exc(),
                "processing_time_before_error": error_time,
                "message_preview": message[:200],
                "confirmation_context": {
                    "confirmed": confirmed,
                    "has_original": original_message is not None
                }
            }, "fallback_to_direct_response_with_confirmation")
            
            # Fallback to direct response with confirmation context
            return await self._fallback_direct_response_with_confirmation(
                message, confirmed, original_message, error=str(e)
            )
    
    async def _fallback_direct_response_with_confirmation(
        self, 
        message: str, 
        confirmed: bool = False, 
        original_message: str = None, 
        error: str = None
    ) -> Dict[str, Any]:
        """
        Fallback response for confirmation requests when Magentic-One is not available
        """
        
        start_time = time.time()
        
        try:
            logger.info(f"🔄 Using fallback direct response with confirmation for: {message[:100]}...")
            
            # Handle confirmation logic in fallback mode
            if confirmed and original_message:
                # User confirmed - provide simple confirmation response
                response_content = (
                    f"I understand you've confirmed the request. "
                    f"However, I'm currently running in fallback mode and cannot execute complex operations. "
                    f"Here's what I can tell you about your request:\n\n"
                    f"Original request: {original_message[:200]}...\n\n"
                    f"For full functionality, please ensure all system dependencies are available."
                )
            elif not confirmed and original_message:
                # User declined
                response_content = (
                    "I understand you've decided not to proceed with that action. "
                    "Is there anything else I can help you with? "
                    "I can provide information and analysis in my current fallback mode."
                )
            else:
                # Regular fallback processing
                return await self._fallback_direct_response(message, error)
            
            processing_time = time.time() - start_time
            
            return {
                "response": response_content,
                "agents_used": ["FallbackOrchestrator"],
                "processing_time": processing_time,
                "session_id": self.session_id,
                "system": "fallback_confirmation",
                "conversation_id": len(self.conversation_history) + 1,
                "total_exchanges": len(self.agent_interaction_logs),
                "agents_involved": ["FallbackOrchestrator"],
                "conversation_messages": [{"role": "user", "content": message}, {"role": "assistant", "content": response_content}],
                "agent_communications": self.agent_interaction_logs[-3:] if len(self.agent_interaction_logs) > 3 else self.agent_interaction_logs,
                "metadata": {
                    "orchestrator": "FallbackOrchestrator",
                    "planning": "Simple confirmation handling",
                    "confirmation_status": "confirmed" if confirmed else "declined",
                    "fallback_reason": error or "magentic_one_unavailable",
                    "total_agent_interactions": len(self.agent_interaction_logs)
                }
            }
            
        except Exception as e:
            logger.error(f"❌ Fallback confirmation response failed: {e}")
            processing_time = time.time() - start_time
            
            return {
                "response": f"I encountered an error processing your confirmation request: {str(e)}",
                "agents_used": ["ErrorHandler"],
                "processing_time": processing_time,
                "session_id": self.session_id,
                "system": "error_fallback",
                "conversation_id": len(self.conversation_history) + 1,
                "total_exchanges": len(self.agent_interaction_logs),
                "agents_involved": ["ErrorHandler"],
                "conversation_messages": [{"role": "user", "content": message}, {"role": "assistant", "content": f"Error: {str(e)}"}],
                "agent_communications": [],
                "metadata": {
                    "orchestrator": "ErrorHandler",
                    "error": str(e),
                    "confirmation_context": True,
                    "total_agent_interactions": len(self.agent_interaction_logs)
                }
            }
    
    def _generate_cache_key(self, user_message: str, timeout_seconds: int) -> str:
        """Generate a cache key for response caching"""
        import hashlib
        # Normalize the message for better cache hits
        normalized_message = user_message.lower().strip()
        # Remove common variations
        normalized_message = re.sub(r'\b(what|which|show|list|get|find)\b', '', normalized_message)
        normalized_message = re.sub(r'\s+', ' ', normalized_message).strip()
        
        # Create hash of normalized message
        message_hash = hashlib.md5(normalized_message.encode()).hexdigest()[:12]
        return f"chat_{message_hash}_{timeout_seconds}"
    
    def _get_cached_response(self, cache_key: str) -> Optional[Dict[str, Any]]:
        """Get cached response if available and not expired"""
        if not hasattr(self, '_response_cache'):
            self._response_cache = {}
            self._response_cache_timestamps = {}
        
        if cache_key in self._response_cache:
            # Check if cache is still valid (5 minutes TTL)
            if time.time() - self._response_cache_timestamps.get(cache_key, 0) < 300:
                return self._response_cache[cache_key].copy()
            else:
                # Remove expired cache entry
                del self._response_cache[cache_key]
                del self._response_cache_timestamps[cache_key]
        
        return None
    
    def _cache_response(self, cache_key: str, response: Dict[str, Any]):
        """Cache a response for future use"""
        if not hasattr(self, '_response_cache'):
            self._response_cache = {}
            self._response_cache_timestamps = {}
        
        # Limit cache size to prevent memory issues
        if len(self._response_cache) >= 50:
            # Remove oldest entry
            oldest_key = min(self._response_cache_timestamps.keys(), 
                           key=lambda k: self._response_cache_timestamps[k])
            del self._response_cache[oldest_key]
            del self._response_cache_timestamps[oldest_key]
        
        self._response_cache[cache_key] = response.copy()
        self._response_cache_timestamps[cache_key] = time.time()
    
    async def _fallback_direct_response(self, user_message: str, error: str = None) -> Dict[str, Any]:
        """
        Fallback response when Magentic-One is not available
        Uses direct tool execution with simplified coordination
        """
        
        start_time = time.time()
        
        try:
            logger.info(f"🔄 Using fallback direct response for: {user_message[:100]}...")
            
            # Enhanced query classification for inventory grounding
            request_type, task_type = self._classify_request(user_message)
            
            response_parts = []
            tools_used = []
            inventory_context = {}
            
            # Strategy: Always ground queries with relevant inventory data (except pure EOL queries)
            if request_type == "direct_eol":
                # Pure EOL queries go directly to specialized agents without inventory overhead
                logger.info("🎯 Direct EOL query - routing to specialized agents")
                software_names = self._extract_software_names_simple(user_message)
                
                # If no software names extracted, try to analyze the query directly
                if not software_names:
                    logger.info("🔍 No software names extracted, analyzing query directly")
                    # For pure Magentic-One implementation, use direct specialist calls
                    if any(word in user_message.lower() for word in ["microsoft", "windows", "office", "sql server"]):
                        # Use pure Magentic-One Microsoft specialist
                        if hasattr(self, 'microsoft_eol_specialist') and self.microsoft_eol_specialist:
                            try:
                                response = await self.microsoft_eol_specialist.on_messages([TextMessage(content=user_message, source="user")], CancellationToken())
                                formatted_result = self._format_specialist_response(response, "Microsoft Product", user_message)
                                tools_used.append("MicrosoftEOLSpecialist")
                                response_parts.append(formatted_result)
                            except Exception as e:
                                logger.error(f"❌ Microsoft specialist failed: {e}")
                                response_parts.append(f"Microsoft EOL analysis currently unavailable: {e}")
                        else:
                            response_parts.append("Microsoft EOL specialist not available")
                    elif any(word in user_message.lower() for word in ["ubuntu", "linux", "centos", "rhel"]):
                        # Use pure Magentic-One Linux specialist
                        if hasattr(self, 'ubuntu_eol_specialist') and self.ubuntu_eol_specialist:
                            try:
                                response = await self.ubuntu_eol_specialist.on_messages([TextMessage(content=user_message, source="user")], CancellationToken())
                                formatted_result = self._format_specialist_response(response, "Linux Distribution", user_message)
                                tools_used.append("UbuntuEOLSpecialist")
                                response_parts.append(formatted_result)
                            except Exception as e:
                                logger.error(f"❌ Linux specialist failed: {e}")
                                response_parts.append(f"Linux EOL analysis currently unavailable: {e}")
                        else:
                            response_parts.append("Linux EOL specialist not available")
                    else:
                        # Use pure Magentic-One Microsoft specialist
                        # Try Microsoft specialist as default for general queries
                        if hasattr(self, 'microsoft_eol_specialist') and self.microsoft_eol_specialist:
                            try:
                                response = await self.microsoft_eol_specialist.on_messages([TextMessage(content=user_message, source="user")], CancellationToken())
                                formatted_result = self._format_specialist_response(response, "Software Product", user_message)
                                tools_used.append("MicrosoftEOLSpecialist")
                                response_parts.append(formatted_result)
                            except Exception as e:
                                logger.error(f"❌ Microsoft specialist failed: {e}")
                                response_parts.append(f"Microsoft EOL analysis currently unavailable: {e}")
                        else:
                            response_parts.append("Microsoft EOL specialist not available")
                else:
                    # Process extracted software names with pure Magentic-One specialists
                    for software_name in software_names:
                        try:
                            if "microsoft" in software_name.lower() or "windows" in software_name.lower():
                                if hasattr(self, 'microsoft_eol_specialist') and self.microsoft_eol_specialist:
                                    try:
                                        response = await self.microsoft_eol_specialist.on_messages([TextMessage(content=f"Analyze EOL status for: {software_name}", source="user")], CancellationToken())
                                        formatted_result = self._format_specialist_response(response, software_name, user_message)
                                        tools_used.append("MicrosoftEOLSpecialist")
                                        response_parts.append(formatted_result)
                                    except Exception as e:
                                        logger.error(f"❌ Microsoft specialist failed for {software_name}: {e}")
                                        response_parts.append(f"Microsoft EOL analysis for {software_name} currently unavailable: {e}")
                                else:
                                    response_parts.append(f"Microsoft EOL specialist not available for {software_name}")
                            elif "ubuntu" in software_name.lower() or "linux" in software_name.lower():
                                if hasattr(self, 'ubuntu_eol_specialist') and self.ubuntu_eol_specialist:
                                    try:
                                        response = await self.ubuntu_eol_specialist.on_messages([TextMessage(content=f"Analyze EOL status for: {software_name}", source="user")], CancellationToken())
                                        formatted_result = self._format_specialist_response(response, software_name, user_message)
                                        tools_used.append("UbuntuEOLSpecialist")
                                        response_parts.append(formatted_result)
                                    except Exception as e:
                                        logger.error(f"❌ Linux specialist failed for {software_name}: {e}")
                                        response_parts.append(f"Linux EOL analysis for {software_name} currently unavailable: {e}")
                                else:
                                    response_parts.append(f"Linux EOL specialist not available for {software_name}")
                            else:
                                # Default to Microsoft specialist for unknown software
                                if hasattr(self, 'microsoft_eol_specialist') and self.microsoft_eol_specialist:
                                    try:
                                        response = await self.microsoft_eol_specialist.on_messages([TextMessage(content=f"Analyze EOL status for: {software_name}", source="user")], CancellationToken())
                                        formatted_result = self._format_specialist_response(response, software_name, user_message)
                                        tools_used.append("MicrosoftEOLSpecialist")
                                        response_parts.append(formatted_result)
                                    except Exception as e:
                                        logger.error(f"❌ Microsoft specialist failed for {software_name}: {e}")
                                        response_parts.append(f"Microsoft EOL analysis for {software_name} currently unavailable: {e}")
                                else:
                                    response_parts.append(f"Microsoft EOL specialist not available for {software_name}")
                            
                        except Exception as e:
                            logger.error(f"❌ EOL analysis failed for {software_name}: {e}")
                            response_parts.append(f"Analysis failed for {software_name}: {str(e)}")
            
            else:
                # All other queries are grounded with inventory data
                logger.info(f"🔍 Inventory-grounded query type: {request_type}")
                
                # Step 1: Gather relevant inventory context
                if request_type in ["os_inventory", "os_eol_grounded", "general_eol_grounded"]:
                    # Use Magentic-One specialists only - no traditional agent fallback
                    # if self.os_inventory_agent:
                    try:
                        # Call Magentic-One OS inventory tool for real data
                        os_inventory = self._get_os_inventory_tool_sync()
                        inventory_context["os_inventory"] = os_inventory
                        
                        # Add the actual inventory data to response
                        response_parts.append(os_inventory)
                        tools_used.append("MagenticOne-OSInventoryAnalyst")
                        logger.info("✅ OS inventory collected by Magentic-One specialist")
                    except Exception as e:
                        logger.error(f"❌ OS inventory tool failed: {e}")
                        inventory_context["os_inventory"] = "OS inventory temporarily unavailable"
                        response_parts.append("⚠️ **OS Inventory Status**: Temporarily unavailable - please try again later.")

                if request_type in ["software_inventory", "software_eol_grounded", "general_eol_grounded"]:
                    # Use Magentic-One specialists only - no traditional agent fallback
                    # if self.software_inventory_agent:
                    try:
                        # Call Magentic-One software inventory tool for real data
                        software_inventory = self._get_software_inventory_tool_sync()
                        inventory_context["software_inventory"] = software_inventory
                        
                        # Add the actual inventory data to response
                        response_parts.append(software_inventory)
                        tools_used.append("MagenticOne-SoftwareInventoryAnalyst")
                        logger.info("✅ Software inventory collected by Magentic-One specialist")
                    except Exception as e:
                        logger.error(f"❌ Software inventory tool failed: {e}")
                        inventory_context["software_inventory"] = "Software inventory temporarily unavailable"
                
                # Step 2: If this is an EOL query, provide EOL analysis grounded by inventory
                if "eol_grounded" in request_type:
                    logger.info("🔬 Providing EOL analysis grounded by inventory context")
                    
                    # Extract software names from user message and inventory
                    software_names = self._extract_software_names_simple(user_message)
                    
                    # Also extract software from inventory context for comprehensive analysis
                    if "software_inventory" in inventory_context:
                        software_names.extend(self._extract_software_from_inventory(inventory_context["software_inventory"]))
                    
                    # Remove duplicates while preserving order
                    software_names = list(dict.fromkeys(software_names))
                    
                    if software_names:
                        response_parts.append("\n## 🔬 EOL Analysis (Based on Your Inventory)")
                        response_parts.append("*The following analysis is grounded by your actual deployed software:*")
                        
                        for software_name in software_names[:5]:  # Limit to top 5 for performance
                            try:
                                if "microsoft" in software_name.lower() or "windows" in software_name.lower():
                                    if hasattr(self, 'microsoft_eol_specialist') and self.microsoft_eol_specialist:
                                        try:
                                            response = await self.microsoft_eol_specialist.on_messages([TextMessage(content=f"Analyze EOL status for: {software_name}", source="user")], CancellationToken())
                                            formatted_result = self._format_specialist_response(response, software_name, user_message)
                                            tools_used.append("MicrosoftEOLSpecialist")
                                            response_parts.append(formatted_result)
                                        except Exception as e:
                                            logger.error(f"❌ Microsoft specialist failed for {software_name}: {e}")
                                            response_parts.append(f"Microsoft EOL analysis for {software_name} currently unavailable: {e}")
                                    else:
                                        response_parts.append(f"Microsoft EOL specialist not available for {software_name}")
                                elif "ubuntu" in software_name.lower() or "linux" in software_name.lower():
                                    if hasattr(self, 'ubuntu_eol_specialist') and self.ubuntu_eol_specialist:
                                        try:
                                            response = await self.ubuntu_eol_specialist.on_messages([TextMessage(content=f"Analyze EOL status for: {software_name}", source="user")], CancellationToken())
                                            formatted_result = self._format_specialist_response(response, software_name, user_message)
                                            tools_used.append("UbuntuEOLSpecialist")
                                            response_parts.append(formatted_result)
                                        except Exception as e:
                                            logger.error(f"❌ Linux specialist failed for {software_name}: {e}")
                                            response_parts.append(f"Linux EOL analysis for {software_name} currently unavailable: {e}")
                                    else:
                                        response_parts.append(f"Linux EOL specialist not available for {software_name}")
                                else:
                                    # Default to Microsoft specialist for unknown software
                                    if hasattr(self, 'microsoft_eol_specialist') and self.microsoft_eol_specialist:
                                        try:
                                            response = await self.microsoft_eol_specialist.on_messages([TextMessage(content=f"Analyze EOL status for: {software_name}", source="user")], CancellationToken())
                                            formatted_result = self._format_specialist_response(response, software_name, user_message)
                                            tools_used.append("MicrosoftEOLSpecialist")
                                            response_parts.append(formatted_result)
                                        except Exception as e:
                                            logger.error(f"❌ Microsoft specialist failed for {software_name}: {e}")
                                            response_parts.append(f"Microsoft EOL analysis for {software_name} currently unavailable: {e}")
                                    else:
                                        response_parts.append(f"Microsoft EOL specialist not available for {software_name}")
                                
                            except Exception as e:
                                logger.error(f"❌ EOL analysis failed for {software_name}: {e}")
                                response_parts.append(f"Analysis failed for {software_name}: {str(e)}")
                    else:
                        response_parts.append("\n**📋 EOL Analysis Summary:**")
                        response_parts.append("No specific software was identified for detailed EOL analysis from your query or inventory.")
                        response_parts.append("\n**💡 Suggestions:**")
                        response_parts.append("- Try asking about specific software: 'What is the EOL date of Windows Server 2019?'")
                        response_parts.append("- Check your inventory: 'What software do I have in my inventory?'")
                        response_parts.append("- Ask for general guidance: 'Show me all EOL software in my environment')")
                
                # Step 3: Add contextual summary for inventory-only queries
                if request_type in ["software_inventory", "os_inventory"] and inventory_context:
                    summary = self._generate_inventory_summary(inventory_context, request_type)
                    response_parts.append(str(summary))  # Ensure it's a string
            
            # Ensure all response parts are strings before joining
            response_parts = [str(part) for part in response_parts if part is not None]
            final_response = "\n\n".join(response_parts)
            
            # Make all URLs in the final response clickable
            final_response = self._make_url_clickable(final_response)
            
            # Ensure we never return an empty response
            if not final_response or final_response.strip() == "":
                # Provide a helpful default response based on the request type
                if request_type == "direct_eol":
                    final_response = f"I couldn't find specific EOL information in my database for the requested software. For accurate EOL dates, please check the official vendor documentation or try rephrasing with the exact software name and version."
                elif request_type == "os_inventory":
                    final_response = "I'm ready to help with your operating system inventory. Please ensure your systems are properly configured for inventory collection."
                elif request_type == "software_inventory":
                    final_response = "I'm ready to help with your software inventory. Please ensure your systems are properly configured for inventory collection."
                elif "eol" in request_type:
                    final_response = "I'm ready to help with end-of-life analysis. Please provide specific software or system names for EOL information."
                else:
                    final_response = f"I've processed your request ({request_type}). Please ask specific questions about your inventory or EOL information."
                
                # Make URLs clickable in fallback responses too
                final_response = self._make_url_clickable(final_response)
            
            if error:
                final_response = f"⚠️ Magentic-One system temporarily unavailable ({error}). Using direct analysis:\n\n{final_response}"
            
            processing_time = time.time() - start_time
            
            return {
                "response": final_response,
                "agents_used": tools_used or ["DirectFallback"],
                "processing_time": processing_time,
                "session_id": self.session_id,
                "system": "fallback_direct",
                "conversation_id": len(self.conversation_history),
                "total_exchanges": len(self.agent_interaction_logs),
                "agents_involved": list(set(log.get("agent_name", "unknown") for log in self.agent_interaction_logs[-10:])),
                "conversation_messages": [{"role": "user", "content": user_message}, {"role": "assistant", "content": final_response}],
                "agent_communications": self.agent_interaction_logs[-5:] if len(self.agent_interaction_logs) > 5 else self.agent_interaction_logs,
                "metadata": {
                    "orchestrator": "DirectFallback",
                    "planning": "Simple rule-based routing",
                    "error": error,
                    "magentic_one_available": MAGENTIC_ONE_IMPORTS_OK,
                    "total_agent_interactions": len(self.agent_interaction_logs)
                }
            }
            
        except Exception as e:
            logger.error(f"❌ Even fallback response failed: {e}")
            processing_time = time.time() - start_time
            
            return {
                "response": f"❌ System temporarily unavailable. Please try again later. Error: {str(e)}",
                "agents_used": ["ErrorHandler"],
                "processing_time": processing_time,
                "session_id": self.session_id,
                "system": "error",
                "conversation_id": len(self.conversation_history),
                "total_exchanges": len(self.agent_interaction_logs),
                "agents_involved": ["ErrorHandler"],
                "conversation_messages": [{"role": "user", "content": user_message}, {"role": "assistant", "content": f"System error: {str(e)}"}],
                "agent_communications": [],
                "metadata": {
                    "error": str(e),
                    "magentic_one_available": MAGENTIC_ONE_IMPORTS_OK,
                    "total_agent_interactions": len(self.agent_interaction_logs)
                }
            }
    
    def _extract_software_names_simple(self, message: str) -> List[str]:
        """Simple software name extraction for fallback mode"""
        # Enhanced pattern matching for common software names
        patterns = [
            r'\b(windows\s+server\s+\d+)\b',  # Windows Server 2016, 2019, etc.
            r'\b(windows\s+\d+)\b',           # Windows 10, 11, etc.
            r'\b(ubuntu\s+\d+\.\d+)\b',       # Ubuntu 20.04, 22.04, etc.
            r'\b(microsoft\s+\w+(?:\s+\w+)*)\b',  # Microsoft Office, SQL Server, etc.
            r'\b(sql\s+server(?:\s+\d+)?)\b', # SQL Server, SQL Server 2019, etc.
            r'\b(office\s+\d+)\b',            # Office 2019, 2021, etc.
            r'\b(node\.?js)\b',               # Node.js
            r'\b(python\s+\d+\.\d+)\b',       # Python 3.9, 3.10, etc.
            r'\b(.net\s+\d+\.\d+)\b'          # .NET versions
        ]
        
        software_names = []
        message_lower = message.lower()
        
        for pattern in patterns:
            matches = re.findall(pattern, message_lower, re.IGNORECASE)
            software_names.extend(matches)
        
        # If no patterns matched, try to extract from direct questions
        if not software_names:
            # Look for "EOL date of [software name]" patterns
            eol_question_patterns = [
                r'eol\s+date\s+of\s+([^?]+)',
                r'end\s+of\s+life\s+(?:date\s+)?(?:of\s+)?([^?]+)',
                r'support\s+ends?\s+(?:for\s+)?([^?]+)',
                r'lifecycle\s+(?:of\s+)?([^?]+)'
            ]
            
            for pattern in eol_question_patterns:
                matches = re.findall(pattern, message_lower, re.IGNORECASE)
                for match in matches:
                    # Clean up the extracted name
                    cleaned_name = re.sub(r'\s+', ' ', match.strip())
                    if cleaned_name and len(cleaned_name) > 2:
                        software_names.append(cleaned_name)
        
        return software_names
    
    def _extract_software_from_inventory(self, inventory_data: str) -> List[str]:
        """Extract software names from inventory data for grounded EOL analysis"""
        software_names = []
        
        # Look for common software patterns in inventory data
        patterns = [
            r'Microsoft\s+(\w+(?:\s+\w+)*)',
            r'SQL\s+Server\s+(\d+)',
            r'Office\s+(\d+)',
            r'Windows\s+Server\s+(\d+)',
            r'Ubuntu\s+(\d+\.\d+)',
            r'(.+)\s+version\s+(\d+\.\d+)',
            r'(\w+)\s+(\d+\.\d+\.\d+)'
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, inventory_data, re.IGNORECASE)
            for match in matches:
                if isinstance(match, tuple):
                    software_name = f"{match[0]} {match[1]}".strip()
                else:
                    software_name = match.strip()
                
                if len(software_name) > 3 and software_name not in software_names:
                    software_names.append(software_name)
        
        return software_names[:10]  # Limit to top 10 for performance
    
    def _generate_inventory_summary(self, inventory_context: Dict[str, str], request_type: str) -> str:
        """Generate a contextual summary based on inventory data"""
        summary_parts = []
        
        if request_type == "software_inventory":
            summary_parts.append("\n**Summary:** This shows all software currently installed in your environment.")
            if "software_inventory" in inventory_context:
                # Count software items
                software_count = len(re.findall(r'\n\s*[-*•]', inventory_context["software_inventory"]))
                summary_parts.append(f"Total applications detected: {software_count}")
        
        elif request_type == "os_inventory":
            summary_parts.append("\n**Summary:** This shows all operating systems in your environment.")
            if "os_inventory" in inventory_context:
                # Count OS instances
                os_count = len(re.findall(r'\n\s*[-*•]', inventory_context["os_inventory"]))
                summary_parts.append(f"Total systems detected: {os_count}")
        
        summary_parts.append("💡 Tip: Ask about EOL status for any of these items for lifecycle planning.")
        
        return "\n".join(summary_parts) or "General inventory information available."
    
    def _format_specialist_response(self, specialist_response: Any, software_name: str, user_query: str) -> str:
        """
        Format response from Magentic-One specialist into user-friendly format
        
        Args:
            specialist_response: Response from Magentic-One specialist (could be TextMessage or other)
            software_name: Name of software being analyzed
            user_query: Original user query for context
            
        Returns:
            Formatted, user-friendly response
        """
        try:
            # Extract content from Magentic-One response - handle autogen Response objects
            content = None
            
            # Handle autogen Response object
            if hasattr(specialist_response, 'chat_message'):
                if hasattr(specialist_response.chat_message, 'content'):
                    content = specialist_response.chat_message.content
                else:
                    content = str(specialist_response.chat_message)
            # Handle direct TextMessage
            elif hasattr(specialist_response, 'content'):
                content = specialist_response.content
            # Handle string response
            elif isinstance(specialist_response, str):
                content = specialist_response
            # Handle list of messages
            elif isinstance(specialist_response, list) and len(specialist_response) > 0:
                if hasattr(specialist_response[-1], 'content'):
                    content = specialist_response[-1].content
                else:
                    content = str(specialist_response[-1])
            else:
                # Last resort - convert to string but log the raw response for debugging
                logger.warning(f"⚠️ Unexpected response type: {type(specialist_response)}")
                logger.warning(f"⚠️ Raw response: {str(specialist_response)[:200]}...")
                content = str(specialist_response)
            
            # If content is still None or empty, provide a fallback
            if not content or content.strip() == "":
                content = "The specialist provided an empty response. Please try rephrasing your query."
            
            # Clean up the software name for display
            display_name = software_name.title() if software_name else "the requested software"
            
            # Return formatted content with context
            return f"**{display_name} Analysis:**\n{content}"
            
        except Exception as e:
            logger.error(f"❌ Failed to format specialist response: {e}")
            logger.error(f"❌ Response type: {type(specialist_response)}")
            logger.error(f"❌ Response repr: {repr(specialist_response)[:200]}")
            return f"Analysis for {software_name}: Response formatting error - {str(e)}"

    def _format_eol_response(self, raw_response: str, software_name: str, agent_type: str, user_query: str) -> str:
        """
        Format raw EOL agent responses into user-friendly, conversational format with citations
        
        Args:
            raw_response: Raw response from EOL agent
            software_name: Name of software being analyzed
            agent_type: Type of agent (Microsoft, Ubuntu, General)
            user_query: Original user query for context
            
        Returns:
            Formatted, user-friendly response with citations
        """
        try:
            # Clean up the software name for display
            display_name = software_name.title() if software_name else "the requested software"
            
            # Start building the formatted response
            formatted_parts = []
            citations = []
            
            # Add a conversational header
            formatted_parts.append(f"## 🔍 End-of-Life Analysis for {display_name}")
            
            # Process the raw response
            if not raw_response or raw_response.strip() == "":
                formatted_parts.append(f"I couldn't find specific EOL information for {display_name} in my current database.")
                formatted_parts.append("\n**💡 Recommendation:** Please check the official vendor documentation for the most up-to-date lifecycle information.")
                return "\n\n".join(formatted_parts)
            
            # Clean and enhance the raw response
            cleaned_response = raw_response.strip()
            
            # Extract citations from the response
            citations = self._extract_citations_from_response(cleaned_response, agent_type)
            
            # Check if it's an error message
            if "error" in cleaned_response.lower() or "failed" in cleaned_response.lower():
                formatted_parts.append(f"⚠️ I encountered an issue while looking up EOL information for {display_name}.")
                formatted_parts.append(f"**Technical Details:** {cleaned_response}")
                formatted_parts.append("\n**💡 Suggestion:** Try rephrasing your query with the exact software name and version, or check the official vendor documentation.")
                return "\n\n".join(formatted_parts)
            
            # Check if it's a "not available" message
            if "not available" in cleaned_response.lower() or "not found" in cleaned_response.lower():
                formatted_parts.append(f"📋 {display_name} information is not currently available in my EOL database.")
                formatted_parts.append(f"**Agent Response:** {cleaned_response}")
                formatted_parts.append("\n**🔗 Recommended Sources:**")
                
                if agent_type == "Microsoft":
                    formatted_parts.append("- Microsoft Lifecycle Policy: https://docs.microsoft.com/en-us/lifecycle/")
                    formatted_parts.append("- Windows Server lifecycle: https://docs.microsoft.com/en-us/windows-server/get-started/windows-server-release-info")
                elif agent_type == "Ubuntu":
                    formatted_parts.append("- Ubuntu Release Cycle: https://ubuntu.com/about/release-cycle")
                    formatted_parts.append("- Ubuntu Security Notices: https://ubuntu.com/security/notices")
                else:
                    formatted_parts.append("- Official vendor documentation")
                    formatted_parts.append("- Product lifecycle pages")
                
                return "\n\n".join(formatted_parts)
            
            # Format a successful response
            formatted_parts.append(f"✅ **Found EOL information for {display_name}:**")
            formatted_parts.append("")
            
            # Add the main response content with better formatting
            response_lines = cleaned_response.split('\n')
            formatted_response_lines = []
            
            for line in response_lines:
                line = line.strip()
                if not line:
                    continue
                    
                # Skip lines that look like URLs or citations (we'll handle them separately)
                if line.startswith('http') or line.startswith('Source:') or line.startswith('Citation:'):
                    continue
                    
                # Format different types of information
                if any(keyword in line.lower() for keyword in ['eol date', 'end of life', 'support ends']):
                    formatted_response_lines.append(f"🗓️ **{line}**")
                elif any(keyword in line.lower() for keyword in ['status', 'current', 'active']):
                    formatted_response_lines.append(f"📊 **Status:** {line}")
                elif any(keyword in line.lower() for keyword in ['version', 'release']):
                    formatted_response_lines.append(f"🔖 **{line}**")
                elif line.startswith('-') or line.startswith('•'):
                    formatted_response_lines.append(f"  {line}")
                else:
                    formatted_response_lines.append(line)
            
            formatted_parts.extend(formatted_response_lines)
            
            # Add citations section if we found any
            if citations:
                formatted_parts.append("")
                formatted_parts.append("**📚 Sources & Citations:**")
                for i, citation in enumerate(citations, 1):
                    clickable_citation = self._make_url_clickable(citation)
                    formatted_parts.append(f"{i}. {clickable_citation}")
                formatted_parts.append("")
                formatted_parts.append("*Please verify information with original sources as data may change.*")
            
            # Add helpful context based on the agent type
            formatted_parts.append("")
            formatted_parts.append("**📋 Additional Context:**")
            
            if agent_type == "Microsoft":
                formatted_parts.append("- This information is sourced from Microsoft's official lifecycle database")
                formatted_parts.append("- Consider planning migrations before the EOL date")
                formatted_parts.append("- Extended support may be available for some products")
                # Add default Microsoft citation if none found
                if not citations:
                    microsoft_url = self._make_url_clickable("https://docs.microsoft.com/en-us/lifecycle/")
                    formatted_parts.append(f"- Source: Microsoft Lifecycle Policy ({microsoft_url})")
            elif agent_type == "Ubuntu":
                formatted_parts.append("- Ubuntu LTS versions receive 5 years of standard support")
                formatted_parts.append("- Extended Security Maintenance (ESM) may be available")
                formatted_parts.append("- Consider upgrading to the latest LTS release")
                # Add default Ubuntu citation if none found
                if not citations:
                    ubuntu_url = self._make_url_clickable("https://ubuntu.com/about/release-cycle")
                    formatted_parts.append(f"- Source: Ubuntu Release Cycle ({ubuntu_url})")
            else:
                formatted_parts.append("- Always verify EOL dates with official vendor sources")
                formatted_parts.append("- Plan migrations well in advance of EOL dates")
                formatted_parts.append("- Consider security implications of using EOL software")
                # Add default citation if none found
                if not citations:
                    eol_url = self._make_url_clickable("https://endoflife.date/")
                    formatted_parts.append(f"- Source: EndOfLife.date community database ({eol_url})")
            
            # Add a call to action
            formatted_parts.append("")
            formatted_parts.append("**🎯 Next Steps:**")
            formatted_parts.append("- Review your migration timeline if approaching EOL")
            formatted_parts.append("- Check for available updates or newer versions")
            formatted_parts.append("- Consult with your IT team for upgrade planning")
            formatted_parts.append("- Verify information using the provided sources above")
            
            return "\n\n".join(formatted_parts)
            
        except Exception as e:
            # Fallback formatting if anything goes wrong
            logger.error(f"❌ Response formatting failed: {e}")
            return f"""## EOL Analysis for {software_name or 'Requested Software'}

**Raw Response:** {raw_response}

**Note:** There was an issue formatting this response. Please refer to the raw information above or contact support for assistance."""
    
    def _extract_citations_from_response(self, response: str, agent_type: str) -> List[str]:
        """
        Extract citations and source references from EOL agent responses
        
        Args:
            response: Raw response from EOL agent
            agent_type: Type of agent (Microsoft, Ubuntu, General)
            
        Returns:
            List of citation strings
        """
        citations = []
        
        try:
            # Common citation patterns
            citation_patterns = [
                r'Source:\s*(.+)',
                r'Citation:\s*(.+)',
                r'Reference:\s*(.+)',
                r'URL:\s*(https?://[^\s]+)',
                r'Link:\s*(https?://[^\s]+)',
                r'See:\s*(https?://[^\s]+)',
                r'More info:\s*(https?://[^\s]+)',
                r'Documentation:\s*(https?://[^\s]+)'
            ]
            
            # Extract URLs from anywhere in the response
            url_pattern = r'(https?://[^\s\)]+)'
            
            for pattern in citation_patterns:
                matches = re.findall(pattern, response, re.IGNORECASE | re.MULTILINE)
                for match in matches:
                    if match.strip() and match.strip() not in citations:
                        citations.append(match.strip())
            
            # Extract standalone URLs
            url_matches = re.findall(url_pattern, response)
            for url in url_matches:
                if url not in citations:
                    citations.append(url)
            
            # Add agent-specific default sources if we have specific information
            if agent_type == "Microsoft" and any(keyword in response.lower() for keyword in ['windows', 'office', 'sql server', 'microsoft']):
                default_source = "Microsoft Lifecycle Policy - https://docs.microsoft.com/en-us/lifecycle/"
                if default_source not in citations:
                    citations.append(default_source)
            
            elif agent_type == "Ubuntu" and any(keyword in response.lower() for keyword in ['ubuntu', 'linux', 'lts']):
                default_source = "Ubuntu Release Cycle - https://ubuntu.com/about/release-cycle"
                if default_source not in citations:
                    citations.append(default_source)
            
            elif agent_type == "General" and "eol" in response.lower():
                default_source = "EndOfLife.date - https://endoflife.date/"
                if default_source not in citations:
                    citations.append(default_source)
            
            # Clean up citations
            cleaned_citations = []
            for citation in citations:
                # Remove extra whitespace and common prefixes
                cleaned = re.sub(r'^(Source|Citation|Reference|URL|Link|See|More info|Documentation):\s*', '', citation, flags=re.IGNORECASE)
                cleaned = cleaned.strip()
                
                if cleaned and len(cleaned) > 10:  # Filter out very short citations
                    cleaned_citations.append(cleaned)
            
            return cleaned_citations[:3]  # Limit to top 3 citations for readability
            
        except Exception as e:
            logger.error(f"❌ Citation extraction failed: {e}")
            return []
    
    def _get_software_inventory_tool_sync(self, direct: bool = True, days: int = 90, limit: int = 10000) -> str:
        """Pure Magentic-One software inventory tool - direct agent access for real data"""
        try:
            # Import and use the software inventory agent directly for Magentic-One
            import asyncio
            import concurrent.futures
            from .software_inventory_agent import SoftwareInventoryAgent
            
            logger.info(f"💾 Magentic-One software inventory collection: days={days}, limit={limit}")
            
            def run_async():
                """Run the async inventory collection"""
                try:
                    # Create fresh agent instance for Magentic-One
                    agent = SoftwareInventoryAgent()
                    # Create a new event loop for this thread
                    new_loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(new_loop)
                    try:
                        return new_loop.run_until_complete(agent.get_software_inventory(days=days, limit=limit))
                    finally:
                        new_loop.close()
                except Exception as e:
                    logger.error(f"❌ Error in async software inventory: {e}")
                    return {"success": False, "error": str(e)}
            
            # Run in separate thread to avoid event loop conflicts
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(run_async)
                result = future.result(timeout=60)
            
            # Format the result for Magentic-One specialists
            if isinstance(result, dict) and result.get("success"):
                data = result.get("data", [])
                if not direct:
                    return data
                else:     
                    count = len(data) if isinstance(data, list) else 0
                    
                    # Debug logging to understand data structure
                    # if count > 0 and data:
                    #     logger.info(f"📊 Software inventory sample item keys: {list(data[0].keys()) if data[0] else 'empty item'}")
                    #     logger.info(f"📊 Software inventory sample item: {data[0] if data[0] else 'empty item'}")
                    
                    if count > 0:
                        # Create HTML table for all discovered software instead of summary
                        table_html = self._format_software_inventory_as_table(data, count, days)
                        return table_html
                    else:
                        return f"**Software Inventory**: No applications found in the last {days} days.\n\n**Status**: Collection completed successfully but no data available.\n**Recommendation**: Check Log Analytics workspace configuration or extend collection period."
            else:
                error_msg = result.get("error", "Unknown error") if isinstance(result, dict) else str(result)
                return f"**Software Inventory Error**: {error_msg}\n\n**Status**: Unable to collect software inventory data.\n**Recommendation**: Check Azure Log Analytics workspace connectivity and permissions."
                
        except Exception as e:
            logger.error(f"❌ Magentic-One software inventory tool error: {e}")
            return f"**Software Inventory Tool Error**: {str(e)}\n\n**Status**: Tool execution failed.\n**Recommendation**: Check system configuration and dependencies."
    
    def _format_software_inventory_as_table(self, data: List[Dict[str, Any]], count: int, days: int) -> str:
        """Format software inventory data as clean markdown for chat interface"""
        
        # Create clean markdown response without HTML or JavaScript
        if not data:
            return f"""## 📦 Software Inventory Analysis

**Collection Period:** Last {days} days  
**Data Source:** Azure Log Analytics ConfigurationData  
**Results:** No software applications found

### Status
✅ Collection completed successfully but no data available  
💡 **Recommendation:** Check Log Analytics workspace configuration or extend collection period"""

        # Organize data by computer for better readability
        computers = {}
        for item in data:
            computer = item.get("computer", "Unknown")
            if computer not in computers:
                computers[computer] = []
            computers[computer].append(item)
        
        # Create summary
        software_summary = f"""## 📦 Software Inventory Analysis
**Collection Period:** Last {days} days  
**Data Source:** Azure Log Analytics ConfigurationData  
**Applications Found:** {count} across {len(computers)} systems
"""

        # Add top software by frequency
        software_counts = {}
        for item in data:
            name = item.get("name", "Unknown")
            software_counts[name] = software_counts.get(name, 0) + 1
        
        top_software = sorted(software_counts.items(), key=lambda x: x[1], reverse=True)[:10]
        
        if top_software:
            software_summary += """### 🔝 Top 10 Installed Software
| Software | Installations |
|----------|--------------|
"""
            for software, count in top_software:
                software_summary += f"| {software} | {count} |\n"
        
        software_summary += "\n### 💻 Detailed Inventory by Computer\n\n"
        
        # Limit to first 20 computers to avoid overwhelming output
        computers_to_show = list(computers.items())[:20]
        
        for computer, software_list in computers_to_show:
            software_summary += f"#### 🖥️ {computer}\n"
            
            # Group software by type
            software_by_type = {}
            for item in software_list:
                software_type = item.get("software_type", "Application")
                if software_type not in software_by_type:
                    software_by_type[software_type] = []
                software_by_type[software_type].append(item)
            
            for software_type, items in software_by_type.items():
                if len(items) > 0:
                    software_summary += f"**{software_type}** ({len(items)} items):\n"
                    # Show only first 10 items per type to avoid overwhelming
                    for item in items[:10]:
                        name = item.get("name", "Unknown")
                        version = item.get("version", "N/A")
                        publisher = item.get("publisher", "Unknown")
                        
                        # Clean up long publisher names
                        if len(publisher) > 30:
                            publisher = publisher[:27] + "..."
                        
                        software_summary += f"- **{name}** {version} (by {publisher})\n"
                    
                    if len(items) > 10:
                        software_summary += f"  ... and {len(items) - 10} more items\n"
                    
                    software_summary += "\n"
        
        if len(computers) > 20:
            software_summary += f"*... and {len(computers) - 20} more computers*\n\n"
        
        software_summary += """### 🎯 Next Steps
- To check EOL status for specific software, ask: *"Check EOL status for [software name]"*
- For comprehensive EOL analysis, ask: *"Analyze EOL risks in my software inventory"*
- To export this data, ask: *"Export software inventory report"*

**Ready for EOL Analysis** ✅ All discovered software is now available for lifecycle assessment."""
        
        return software_summary
    
    def _format_os_inventory_as_table(self, data: List[Dict[str, Any]], count: int, days: int) -> str:
        """Format OS inventory data as clean markdown for chat interface"""
        
        # Create clean markdown response without HTML or JavaScript
        if not data:
            return f"""## 🖥️ OS Inventory Analysis

**Collection Period:** Last {days} days  
**Data Source:** Azure Log Analytics Heartbeat  
**Results:** No systems found

### Status
✅ Collection completed successfully but no data available  
💡 **Recommendation:** Check Log Analytics workspace configuration or extend collection period"""

        # Organize data by OS type for better readability
        os_by_name = {}
        os_by_type = {}
        
        for item in data:
            os_name = item.get("os_name", item.get("name", "Unknown OS"))
            os_type = item.get("os_type", "Unknown")
            computer_type = item.get("computer_type", "Unknown")
            
            # Group by OS name
            if os_name not in os_by_name:
                os_by_name[os_name] = []
            os_by_name[os_name].append(item)
            
            # Group by OS type
            if os_type not in os_by_type:
                os_by_type[os_type] = []
            os_by_type[os_type].append(item)
        
        # Create summary
        os_summary = f"""## 🖥️ OS Inventory Analysis

**Collection Period:** Last {days} days  
**Data Source:** Azure Log Analytics Heartbeat  
**Systems Found:** {count} across {len(os_by_name)} different OS versions

"""

        # Add OS distribution summary
        if os_by_name:
            os_summary += """### 📊 Operating System Distribution
| Operating System | Installations | Version Details |
|------------------|---------------|-----------------|
"""
            # Sort by number of systems
            sorted_os = sorted(os_by_name.items(), key=lambda x: len(x[1]), reverse=True)
            
            for os_name, systems in sorted_os[:15]:  # Show top 15 OS versions
                versions = {}
                for system in systems:
                    version = system.get("os_version", system.get("version", "Unknown"))
                    versions[version] = versions.get(version, 0) + 1
                
                version_text = ", ".join([f"{v} ({c})" for v, c in sorted(versions.items(), key=lambda x: x[1], reverse=True)][:3])
                if len(versions) > 3:
                    version_text += f" +{len(versions)-3} more"
                
                os_summary += f"| **{os_name}** | {len(systems)} | {version_text} |\n"
            
            if len(os_by_name) > 15:
                os_summary += f"| *...and {len(os_by_name) - 15} more OS versions* | | |\n"
        
        # Add system type breakdown
        if os_by_type:
            os_summary += "\n### 🏗️ Infrastructure Type Breakdown\n"
            for os_type, systems in sorted(os_by_type.items(), key=lambda x: len(x[1]), reverse=True):
                # Get computer type distribution
                computer_types = {}
                for system in systems:
                    comp_type = system.get("computer_type", "Unknown")
                    computer_types[comp_type] = computer_types.get(comp_type, 0) + 1
                
                os_summary += f"**{os_type}** ({len(systems)} systems):\n"
                for comp_type, count in sorted(computer_types.items(), key=lambda x: x[1], reverse=True):
                    if comp_type == "Azure VM":
                        os_summary += f"  - ☁️ Azure VMs: {count}\n"
                    elif comp_type == "Arc-enabled Server":
                        os_summary += f"  - 🔗 Arc-enabled Servers: {count}\n"
                    else:
                        os_summary += f"  - 🖥️ {comp_type}: {count}\n"
                os_summary += "\n"
        
        # Add detailed system listing (limited to avoid overwhelming output)
        os_summary += "### 💻 System Details\n\n"
        
        # Show sample of systems grouped by OS
        systems_shown = 0
        max_systems_to_show = 20
        
        for os_name, systems in list(sorted_os):  # Top 5 OS types
            if systems_shown >= max_systems_to_show:
                break
                
            os_summary += f"#### 🔷 {os_name}\n"
            
            systems_to_show = min(4, len(systems), max_systems_to_show - systems_shown)
            for system in systems[:systems_to_show]:
                computer = system.get("computer_name", system.get("computer", "Unknown"))
                version = system.get("os_version", system.get("version", "N/A"))
                vendor = system.get("vendor", "Unknown")
                comp_type = system.get("computer_type", "Unknown")
                
                # Format last heartbeat
                last_hb = system.get("last_heartbeat", "Unknown")
                if last_hb and last_hb != "Unknown":
                    try:
                        from datetime import datetime
                        if isinstance(last_hb, str):
                            dt = datetime.fromisoformat(last_hb.replace('Z', '+00:00'))
                            last_hb_formatted = dt.strftime("%Y-%m-%d %H:%M")
                        else:
                            last_hb_formatted = str(last_hb)
                    except:
                        last_hb_formatted = str(last_hb)
                else:
                    last_hb_formatted = "Unknown"
                
                type_icon = "☁️" if comp_type == "Azure VM" else "🔗" if comp_type == "Arc-enabled Server" else "🖥️"
                
                os_summary += f"- {type_icon} **{computer}** - {version} (by {vendor}) - Last seen: {last_hb_formatted}\n"
                systems_shown += 1
            
            if len(systems) > systems_to_show:
                os_summary += f"  *... and {len(systems) - systems_to_show} more {os_name} systems*\n"
            
            os_summary += "\n"
        
        if count > systems_shown:
            os_summary += f"*... and {count - systems_shown} more systems*\n\n"
        
        os_summary += """### 🎯 Next Steps
- To check EOL status for specific OS, ask: *"Check EOL status for [OS name]"*
- For comprehensive OS EOL analysis, ask: *"Analyze EOL risks in my OS inventory"*
- To focus on specific OS types, ask: *"Show me all Windows Server versions"*

**Ready for EOL Analysis** ✅ All discovered operating systems are now available for lifecycle assessment."""
        
        return os_summary

    def format_os_inventory_as_table(self, data: Any, count: int, days: int) -> Dict[str, Any]:
        """Public wrapper that returns a structured dict for the API endpoint.

        The autogen `autogen_chat` handler expects a dict-like result with keys
        such as `response`, `conversation_messages`, `agent_communications`,
        `agents_involved`, etc. Older code used a private `_format_os_inventory_as_table`
        which returned a markdown string. This wrapper preserves that behavior
        while returning a safe structured dict so callers can call `.get()`.
        """
        try:
            # If the private formatter exists, use it to get markdown summary
            if hasattr(self, '_format_os_inventory_as_table'):
                markdown = self._format_os_inventory_as_table(data or [], int(count or 0), int(days or 90))
            else:
                # Fallback: if data is already a string, use it; otherwise stringify
                markdown = str(data) if data is not None else "No data"

            # Build a minimal structured response matching the autogen expectations
            structured = {
                "response": markdown,
                "conversation_messages": [],
                "agent_communications": [],
                "agents_involved": [],
                "total_exchanges": 0,
                "session_id": getattr(self, 'session_id', 'unknown'),
                "error": None,
                "confirmation_required": False,
                "confirmation_declined": False,
                "pending_message": None,
                "fast_path": False
            }

            return structured
        except Exception as e:
            # On error return an error-shaped dict so `.get()` works in callers
            return {
                "response": "",
                "conversation_messages": [],
                "agent_communications": [],
                "agents_involved": [],
                "total_exchanges": 0,
                "session_id": getattr(self, 'session_id', 'unknown'),
                "error": f"Formatter error: {str(e)}",
            }
    
    def _get_os_inventory_tool_sync(self, direct: bool = False, days: int = 90, limit: int = 2000) -> str:
        """Pure Magentic-One OS inventory tool - direct agent access for real data"""
        try:
            # Import and use the OS inventory agent directly for Magentic-One
            import asyncio
            import concurrent.futures
            from .os_inventory_agent import OSInventoryAgent
            
            logger.info(f"🔍 Magentic-One OS inventory collection: days={days}, limit={limit}")
            
            def run_async():
                """Run the async OS inventory collection"""
                try:
                    # Create fresh agent instance for Magentic-One
                    agent = OSInventoryAgent()
                    # Create a new event loop for this thread
                    new_loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(new_loop)
                    try:
                        return new_loop.run_until_complete(agent.get_os_inventory(days=days, limit=limit))
                    finally:
                        new_loop.close()
                except Exception as e:
                    logger.error(f"❌ Error in async OS inventory: {e}")
                    return {"success": False, "error": str(e)}
            
            # Run in separate thread to avoid event loop conflicts
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(run_async)
                result = future.result(timeout=60)
            
            # Format the result for Magentic-One specialists
            if isinstance(result, dict) and result.get("success"):
                data = result.get("data", [])
                
                if not direct:
                    return data
                else:                    
                    count = len(data) if isinstance(data, list) else 0
                    
                    if count > 0:
                        # Create HTML table for all discovered OS instead of summary
                        table_html = self._format_os_inventory_as_table(data, count, days)
                        return table_html
                    else:
                        return f"**OS Inventory**: No systems found in the last {days} days.\n\n**Status**: Collection completed successfully but no data available.\n**Recommendation**: Check Log Analytics workspace configuration or extend collection period."
            else:
                error_msg = result.get("error", "Unknown error") if isinstance(result, dict) else str(result)
                return f"**OS Inventory Error**: {error_msg}\n\n**Status**: Unable to collect OS inventory data.\n**Recommendation**: Check Azure Log Analytics workspace connectivity and permissions."
                
        except Exception as e:
            logger.error(f"❌ Magentic-One OS inventory tool error: {e}")
            return f"**OS Inventory Tool Error**: {str(e)}\n\n**Status**: Tool execution failed.\n**Recommendation**: Check system configuration and dependencies."
        
    async def health_check(self) -> Dict[str, Any]:
        """Health check for the orchestrator system"""
        return {
            "status": "healthy",
            "system": "magentic_one" if MAGENTIC_ONE_IMPORTS_OK else "fallback",
            "session_id": self.session_id,
            "agents_available": {
                "magentic_one_team": self.team is not None,
                "inventory_agent": self.inventory_agent is not None,
                "microsoft_eol": self.microsoft_agent is not None,
                "ubuntu_eol": self.ubuntu_agent is not None,
                "general_eol": self.endoflife_agent is not None
            },
            "version": magentic_one_version,
            "conversation_count": len(self.conversation_history)
        }
    
    async def get_agent_communications(self) -> List[Dict[str, Any]]:
        """Get agent communications with enhanced orchestrator behavior, planning and decision-making details"""
        communications = []
        
        # Add orchestrator event communications with enhanced planning details
        for event in self.orchestrator_logs:
            communication = {
                "type": "orchestrator_event",
                "timestamp": event.get("timestamp"),
                "agent": "MagenticOneOrchestrator", 
                "content": {
                    "event_type": event.get("event_type"),
                    "event_data": event.get("event_data"),
                    "session_id": event.get("session_id")
                },
                "input": {
                    "event_trigger": event.get("event_type"),
                    "parameters": event.get("event_data", {}),
                    "orchestrator_context": {
                        "session_state": "active",
                        "conversation_id": event.get("conversation_id", 0),
                        "decision_mode": "autonomous"
                    }
                },
                "output": {
                    "status": "logged",
                    "details": event.get("event_data", {}),
                    "impact": self._determine_event_impact(event.get("event_type")),
                    "next_actions": self._predict_next_actions(event.get("event_type"))
                }
            }
            
            # Add orchestrator reasoning for key events
            if event.get("event_type") in ["chat_session_start", "task_initiation", "agent_coordination"]:
                communication["orchestrator_reasoning"] = {
                    "decision_factors": self._extract_decision_factors(event),
                    "strategic_planning": self._extract_strategic_planning(event),
                    "resource_allocation": self._extract_resource_allocation(event)
                }
            
            communications.append(communication)
        
        # Add task planning communications with detailed orchestrator decision-making
        for planning_log in self.task_planning_logs:
            communication = {
                "type": "orchestrator_planning",
                "timestamp": planning_log.get("timestamp"),
                "agent": "MagenticOneOrchestrator",
                "planning_stage": planning_log.get("planning_stage"),
                "content": {
                    "planning_data": planning_log.get("planning_data", {}),
                    "orchestrator_reasoning": planning_log.get("orchestrator_reasoning", {})
                },
                "input": {
                    "planning_request": {
                        "stage": planning_log.get("planning_stage"),
                        "context": planning_log.get("planning_data", {}),
                        "required_decisions": self._identify_required_decisions(planning_log)
                    },
                    "orchestrator_analysis": {
                        "task_breakdown": self._extract_task_breakdown(planning_log),
                        "complexity_assessment": self._extract_complexity_assessment(planning_log),
                        "resource_requirements": self._extract_resource_requirements(planning_log)
                    }
                },
                "output": {
                    "decisions_made": planning_log.get("orchestrator_reasoning", {}).get("decision_tree", {}),
                    "agent_selection": planning_log.get("orchestrator_reasoning", {}).get("agent_selection_reasoning", {}),
                    "strategic_approach": planning_log.get("orchestrator_reasoning", {}).get("strategic_approach", {}),
                    "workflow_prediction": planning_log.get("orchestrator_reasoning", {}).get("expected_workflow", []),
                    "confidence_level": self._calculate_decision_confidence(planning_log),
                    "alternative_plans": self._generate_alternative_plans(planning_log)
                }
            }
            communications.append(communication)
        
        # Add agent interaction communications with enhanced orchestrator coordination details
        for interaction in self.agent_interaction_logs:
            communication = {
                "type": "agent_interaction",
                "timestamp": interaction.get("timestamp"),
                "agent": interaction.get("agent_name"),
                "action": interaction.get("action"),
                "content": interaction.get("data", {}),
                "input": {
                    "action": interaction.get("action"),
                    "parameters": interaction.get("data", {}),
                    "orchestrator_directive": {
                        "coordination_mode": self._determine_coordination_mode(interaction),
                        "priority_level": self._determine_priority_level(interaction),
                        "quality_requirements": self._determine_quality_requirements(interaction)
                    }
                },
                "output": {
                    "status": "completed",
                    "result": interaction.get("data", {}),
                    "orchestrator_evaluation": {
                        "result_quality": self._evaluate_result_quality(interaction),
                        "goal_achievement": self._evaluate_goal_achievement(interaction),
                        "follow_up_needed": self._determine_follow_up_needed(interaction)
                    }
                }
            }
            
            # Enhance with web search details if available
            if "web_search" in interaction.get("action", "").lower():
                communication["web_search_details"] = {
                    "search_query": interaction.get("data", {}).get("search_query", ""),
                    "search_time": interaction.get("data", {}).get("search_time", 0),
                    "response_length": interaction.get("data", {}).get("response_length", 0),
                    "citations": self._extract_citations_from_data(interaction.get("data", {}))
                }
                
                # Add web search specific input/output format with orchestrator oversight
                communication["input"]["search_details"] = {
                    "query": interaction.get("data", {}).get("search_query", ""),
                    "context": interaction.get("data", {}).get("eol_context", ""),
                    "search_method": "WebSurfer + Azure AI",
                    "orchestrator_guidance": {
                        "search_strategy": self._determine_search_strategy(interaction),
                        "validation_criteria": self._determine_validation_criteria(interaction),
                        "expected_sources": self._predict_expected_sources(interaction)
                    }
                }
                
                communication["output"]["search_results"] = {
                    "response_text": interaction.get("data", {}).get("response_content", ""),
                    "search_duration": interaction.get("data", {}).get("search_time", 0),
                    "citations": self._extract_citations_from_data(interaction.get("data", {})),
                    "source_verification": "Web search with citation tracking",
                    "orchestrator_validation": {
                        "source_credibility": self._assess_source_credibility(interaction),
                        "information_completeness": self._assess_information_completeness(interaction),
                        "recommendation": self._generate_result_recommendation(interaction)
                    }
                }
            
            communications.append(communication)
        
        # Add web search specific communications with orchestrator oversight
        if hasattr(self, 'web_search_logs'):
            for search_log in self.web_search_logs:
                communication = {
                    "type": "web_search",
                    "timestamp": search_log.get("timestamp"),
                    "agent": search_log.get("agent") + "_WebSurfer",
                    "content": {
                        "search_query": search_log.get("search_query"),
                        "citations": search_log.get("citations", []),
                        "response_length": search_log.get("response_length", 0)
                    },
                    "input": {
                        "search_query": search_log.get("search_query"),
                        "search_method": "WebSurfer",
                        "target_sites": ["Official documentation", "Vendor websites", "Product pages"],
                        "orchestrator_parameters": {
                            "search_depth": "comprehensive",
                            "citation_requirements": "mandatory",
                            "validation_level": "strict"
                        }
                    },
                    "output": {
                        "search_duration": search_log.get("search_time", 0),
                        "citations_found": len(search_log.get("citations", [])),
                        "response_length": search_log.get("response_length", 0),
                        "citation_details": search_log.get("citations", []),
                        "orchestrator_assessment": {
                            "search_effectiveness": self._assess_search_effectiveness(search_log),
                            "citation_quality": self._assess_citation_quality(search_log),
                            "coverage_completeness": self._assess_coverage_completeness(search_log)
                        }
                    }
                }
                communications.append(communication)
        
        # Sort communications by timestamp
        communications.sort(key=lambda x: x.get("timestamp", ""))
        
        return communications

    # Helper methods for orchestrator behavior analysis
    
    def _determine_event_impact(self, event_type: str) -> str:
        """Determine the impact level of an orchestrator event"""
        high_impact_events = ["chat_session_start", "agent_coordination", "error_recovery"]
        medium_impact_events = ["task_initiation", "performance_metric", "cache_operation"]
        
        if event_type in high_impact_events:
            return "high"
        elif event_type in medium_impact_events:
            return "medium"
        else:
            return "low"
    
    def _predict_next_actions(self, event_type: str) -> List[str]:
        """Predict likely next actions based on current event"""
        next_actions_map = {
            "chat_session_start": ["task_analysis", "agent_selection", "planning_initiation"],
            "task_initiation": ["agent_coordination", "web_search_execution", "validation_setup"],
            "agent_coordination": ["specialist_execution", "progress_monitoring", "quality_check"],
            "error_recovery": ["fallback_execution", "alternative_approach", "user_notification"]
        }
        
        return next_actions_map.get(event_type, ["continue_processing"])
    
    def _extract_decision_factors(self, event: Dict[str, Any]) -> List[str]:
        """Extract decision factors from orchestrator event"""
        event_data = event.get("event_data", {})
        factors = []
        
        if "timeout_seconds" in event_data:
            factors.append(f"Time constraint: {event_data['timeout_seconds']}s")
        if "magentic_one_available" in event_data:
            factors.append(f"Magentic-One availability: {event_data['magentic_one_available']}")
        if "user_message_length" in event_data:
            factors.append(f"Query complexity: {event_data['user_message_length']} chars")
        
        return factors
    
    def _extract_strategic_planning(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """Extract strategic planning information from event"""
        return {
            "approach": "adaptive_multi_agent",
            "priorities": ["accuracy", "speed", "comprehensive_coverage"],
            "constraints": ["time_limit", "resource_availability", "quality_requirements"]
        }
    
    def _extract_resource_allocation(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """Extract resource allocation decisions from event"""
        return {
            "agents_allocated": "specialist_selection_based_on_query",
            "tools_enabled": ["WebSurfer", "citation_tracking", "validation_systems"],
            "priority_queue": "high_priority_for_eol_analysis"
        }
    
    def _identify_required_decisions(self, planning_log: Dict[str, Any]) -> List[str]:
        """Identify required decisions for a planning stage"""
        stage = planning_log.get("planning_stage", "")
        
        decisions_map = {
            "task_initiation": ["agent_selection", "approach_strategy", "quality_criteria"],
            "agent_coordination": ["execution_order", "parallel_vs_sequential", "validation_method"],
            "task_execution_complete": ["result_validation", "response_synthesis", "follow_up_actions"]
        }
        
        return decisions_map.get(stage, ["continue_processing"])
    
    def _extract_task_breakdown(self, planning_log: Dict[str, Any]) -> Dict[str, Any]:
        """Extract task breakdown from planning log"""
        planning_data = planning_log.get("planning_data", {})
        task = planning_data.get("task", "")
        
        return {
            "primary_objective": "EOL analysis and information retrieval",
            "sub_tasks": self._identify_subtasks(task),
            "dependencies": ["web_search_capability", "citation_validation", "specialist_knowledge"],
            "success_metrics": ["information_accuracy", "citation_completeness", "response_timeliness"]
        }
    
    def _extract_complexity_assessment(self, planning_log: Dict[str, Any]) -> Dict[str, Any]:
        """Extract complexity assessment from planning log"""
        planning_data = planning_log.get("planning_data", {})
        task = planning_data.get("task", "")
        
        return {
            "complexity_level": self._assess_task_complexity(task),
            "complexity_factors": self._identify_complexity_factors(task),
            "processing_estimate": self._estimate_processing_time(task),
            "resource_requirements": self._assess_resource_requirements(task)
        }
    
    def _extract_resource_requirements(self, planning_log: Dict[str, Any]) -> Dict[str, Any]:
        """Extract resource requirements from planning log"""
        return {
            "agents_needed": ["specialist_agent", "websurfer_eol_agent", "validator"],
            "tools_required": ["web_search", "citation_extraction", "data_validation"],
            "external_services": ["azure_ai_search", "web_scraping", "content_analysis"],
            "estimated_duration": "5-15 seconds"
        }
    
    def _calculate_decision_confidence(self, planning_log: Dict[str, Any]) -> float:
        """Calculate confidence level for orchestrator decisions"""
        reasoning = planning_log.get("orchestrator_reasoning", {})
        agent_selection = reasoning.get("agent_selection_reasoning", {})
        
        if "final_selection" in agent_selection:
            confidence = agent_selection["final_selection"].get("selection_confidence", 0.5)
            return min(max(confidence, 0.0), 1.0)  # Ensure 0-1 range
        
        return 0.7  # Default confidence level
    
    def _generate_alternative_plans(self, planning_log: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Generate alternative execution plans"""
        return [
            {
                "plan_id": "fast_execution",
                "description": "Prioritize speed over comprehensiveness",
                "trade_offs": ["Reduced validation", "Fewer sources", "Faster response"]
            },
            {
                "plan_id": "comprehensive_analysis",
                "description": "Prioritize thoroughness over speed",
                "trade_offs": ["Longer processing time", "Multiple source validation", "Detailed citations"]
            },
            {
                "plan_id": "fallback_approach",
                "description": "Use cached results or simplified analysis",
                "trade_offs": ["Potential outdated information", "No web search", "Immediate response"]
            }
        ]
    
    def _determine_coordination_mode(self, interaction: Dict[str, Any]) -> str:
        """Determine the coordination mode for agent interaction"""
        action = interaction.get("action", "")
        
        if "web_search" in action.lower():
            return "guided_autonomous"
        elif "coordination" in action.lower():
            return "collaborative"
        else:
            return "independent"
    
    def _determine_priority_level(self, interaction: Dict[str, Any]) -> str:
        """Determine priority level for agent interaction"""
        action = interaction.get("action", "")
        
        if "eol" in action.lower() or "critical" in action.lower():
            return "high"
        elif "search" in action.lower():
            return "medium"
        else:
            return "normal"
    
    def _determine_quality_requirements(self, interaction: Dict[str, Any]) -> Dict[str, Any]:
        """Determine quality requirements for agent interaction"""
        return {
            "citation_required": True,
            "source_verification": "mandatory",
            "accuracy_threshold": 0.9,
            "completeness_level": "comprehensive"
        }
    
    def _evaluate_result_quality(self, interaction: Dict[str, Any]) -> str:
        """Evaluate the quality of agent interaction results"""
        data = interaction.get("data", {})
        
        if "citations" in str(data) and "response_length" in data:
            response_length = data.get("response_length", 0)
            if response_length > 500:
                return "high"
            elif response_length > 100:
                return "medium"
        
        return "satisfactory"
    
    def _evaluate_goal_achievement(self, interaction: Dict[str, Any]) -> str:
        """Evaluate how well the interaction achieved its goals"""
        data = interaction.get("data", {})
        action = interaction.get("action", "")
        
        if "web_search" in action.lower():
            if "response_content" in data and "citations" in str(data):
                return "fully_achieved"
            elif "response_content" in data:
                return "partially_achieved"
        
        return "achieved"
    
    def _determine_follow_up_needed(self, interaction: Dict[str, Any]) -> bool:
        """Determine if follow-up actions are needed"""
        data = interaction.get("data", {})
        
        # Check if web search results seem incomplete
        if "response_length" in data and data["response_length"] < 100:
            return True
        
        # Check for error indicators
        if "error" in str(data).lower():
            return True
        
        return False
    
    def _determine_search_strategy(self, interaction: Dict[str, Any]) -> str:
        """Determine search strategy for web search interactions"""
        data = interaction.get("data", {})
        query = data.get("search_query", "")
        
        if "microsoft" in query.lower():
            return "microsoft_focused"
        elif "ubuntu" in query.lower() or "linux" in query.lower():
            return "linux_distribution_focused"
        else:
            return "broad_technology_search"
    
    def _determine_validation_criteria(self, interaction: Dict[str, Any]) -> List[str]:
        """Determine validation criteria for search results"""
        return [
            "official_source_verification",
            "citation_url_validation",
            "information_recency_check",
            "multiple_source_confirmation"
        ]
    
    def _predict_expected_sources(self, interaction: Dict[str, Any]) -> List[str]:
        """Predict expected sources for search results"""
        data = interaction.get("data", {})
        query = data.get("search_query", "")
        
        if "microsoft" in query.lower():
            return ["docs.microsoft.com", "support.microsoft.com", "techcommunity.microsoft.com"]
        elif "ubuntu" in query.lower():
            return ["ubuntu.com", "wiki.ubuntu.com", "releases.ubuntu.com"]
        else:
            return ["official_documentation", "vendor_websites", "product_pages"]
    
    def _assess_source_credibility(self, interaction: Dict[str, Any]) -> str:
        """Assess the credibility of sources in search results"""
        data = interaction.get("data", {})
        citations = self._extract_citations_from_data(data)
        
        official_domains = ["microsoft.com", "ubuntu.com", "redhat.com", "docs.", "support."]
        
        for citation in citations:
            if any(domain in citation.get("url", "") for domain in official_domains):
                return "high"
        
        return "medium"
    
    def _assess_information_completeness(self, interaction: Dict[str, Any]) -> str:
        """Assess the completeness of information in search results"""
        data = interaction.get("data", {})
        response_length = data.get("response_length", 0)
        
        if response_length > 1000:
            return "comprehensive"
        elif response_length > 300:
            return "adequate"
        else:
            return "basic"
    
    def _generate_result_recommendation(self, interaction: Dict[str, Any]) -> str:
        """Generate recommendation based on search results"""
        quality = self._evaluate_result_quality(interaction)
        completeness = self._assess_information_completeness(interaction)
        
        if quality == "high" and completeness == "comprehensive":
            return "proceed_with_results"
        elif quality == "medium" or completeness == "adequate":
            return "results_acceptable_with_caveats"
        else:
            return "consider_additional_search"
    
    def _assess_search_effectiveness(self, search_log: Dict[str, Any]) -> str:
        """Assess the effectiveness of a web search"""
        citations_found = len(search_log.get("citations", []))
        search_time = search_log.get("search_time", 0)
        
        if citations_found >= 3 and search_time < 10:
            return "highly_effective"
        elif citations_found >= 1 and search_time < 15:
            return "effective"
        else:
            return "needs_improvement"
    
    def _assess_citation_quality(self, search_log: Dict[str, Any]) -> str:
        """Assess the quality of citations found"""
        citations = search_log.get("citations", [])
        
        if not citations:
            return "no_citations"
        
        official_count = sum(1 for citation in citations 
                           if any(domain in citation.get("url", "") 
                                 for domain in ["docs.", "support.", ".gov", ".edu"]))
        
        if official_count >= len(citations) * 0.7:
            return "high_quality"
        elif official_count >= len(citations) * 0.3:
            return "mixed_quality"
        else:
            return "low_quality"
    
    def _assess_coverage_completeness(self, search_log: Dict[str, Any]) -> str:
        """Assess the completeness of search coverage"""
        response_length = search_log.get("response_length", 0)
        citations_count = len(search_log.get("citations", []))
        
        if response_length > 800 and citations_count >= 3:
            return "comprehensive"
        elif response_length > 300 and citations_count >= 2:
            return "adequate"
        else:
            return "limited"
    
    def _identify_subtasks(self, task: str) -> List[str]:
        """Identify subtasks from main task"""
        subtasks = ["query_analysis", "technology_identification"]
        
        if "eol" in task.lower():
            subtasks.extend(["eol_date_search", "lifecycle_verification"])
        if "inventory" in task.lower():
            subtasks.extend(["software_enumeration", "version_detection"])
        
        subtasks.append("result_synthesis")
        return subtasks
    
    def _identify_complexity_factors(self, task: str) -> List[str]:
        """Identify factors that contribute to task complexity"""
        factors = []
        
        word_count = len(task.split())
        if word_count > 20:
            factors.append("long_query")
        
        if "and" in task.lower() or "or" in task.lower():
            factors.append("multiple_requirements")
        
        tech_keywords = ["microsoft", "ubuntu", "linux", "windows", "office"]
        if sum(1 for keyword in tech_keywords if keyword in task.lower()) > 1:
            factors.append("multi_technology")
        
        return factors
    
    def _estimate_processing_time(self, task: str) -> str:
        """Estimate processing time for task"""
        complexity = self._assess_task_complexity(task)
        
        time_estimates = {
            "LOW": "3-5 seconds",
            "MEDIUM": "5-10 seconds", 
            "HIGH": "10-20 seconds"
        }
        
        return time_estimates.get(complexity, "5-10 seconds")
    
    def _assess_resource_requirements(self, task: str) -> List[str]:
        """Assess resource requirements for task"""
        requirements = ["web_search", "citation_extraction"]
        
        if "microsoft" in task.lower():
            requirements.append("microsoft_specialist")
        if "ubuntu" in task.lower() or "linux" in task.lower():
            requirements.append("linux_specialist")
        
        return requirements
    
    def get_conversation_history(self) -> List[Dict[str, Any]]:
        """Get conversation history"""
        return self.conversation_history.copy()
    
    async def clear_communications(self) -> Dict[str, Any]:
        """Clear conversation history"""
        self.conversation_history.clear()
        self.agent_communications.clear()
        return {
            "status": "cleared",
            "session_id": self.session_id,
            "system": "magentic_one"
        }
    
    def get_orchestrator_logs(self) -> Dict[str, Any]:
        """Get comprehensive orchestrator behavior logs"""
        session_runtime = time.time() - self.init_start_time
        
        # Calculate agent usage statistics
        agent_stats = {}
        for agent_name, count in self.agent_usage_stats.items():
            agent_stats[agent_name] = {
                "usage_count": count,
                "usage_percentage": (count / max(sum(self.agent_usage_stats.values()), 1)) * 100
            }
        
        # Calculate tool usage statistics  
        tool_stats = {}
        for tool_name, count in self.tool_usage_stats.items():
            tool_stats[tool_name] = {
                "usage_count": count,
                "usage_percentage": (count / max(sum(self.tool_usage_stats.values()), 1)) * 100
            }
        
        # Performance metrics summary
        performance_summary = {}
        for metric_name, values in self.performance_metrics.items():
            if values:
                performance_summary[metric_name] = {
                    "count": len(values),
                    "average": sum(values) / len(values),
                    "min": min(values),
                    "max": max(values),
                    "total": sum(values)
                }
        
        return {
            "session_info": {
                "session_id": self.session_id,
                "session_runtime": session_runtime,
                "start_time": self.init_start_time,
                "current_time": time.time(),
                "total_conversations": len(self.conversation_history)
            },
            "orchestrator_events": {
                "total_events": len(self.orchestrator_logs),
                "events": self.orchestrator_logs[-50:] if len(self.orchestrator_logs) > 50 else self.orchestrator_logs  # Last 50 events
            },
            "agent_interactions": {
                "total_interactions": len(self.agent_interaction_logs),
                "usage_statistics": agent_stats,
                "recent_interactions": self.agent_interaction_logs[-20:] if len(self.agent_interaction_logs) > 20 else self.agent_interaction_logs
            },
            "task_planning": {
                "total_planning_events": len(self.task_planning_logs),
                "recent_planning": self.task_planning_logs[-10:] if len(self.task_planning_logs) > 10 else self.task_planning_logs
            },
            "performance_metrics": performance_summary,
            "tool_usage": {
                "statistics": tool_stats,
                "total_tool_calls": sum(self.tool_usage_stats.values())
            },
            "conversation_flow": {
                "total_conversations": len(self.conversation_flow),
                "recent_flow": self.conversation_flow[-10:] if len(self.conversation_flow) > 10 else self.conversation_flow
            },
            "web_search_activity": {
                "total_searches": len(getattr(self, 'web_search_logs', [])),
                "recent_searches": getattr(self, 'web_search_logs', [])[-5:] if hasattr(self, 'web_search_logs') else [],
                "search_agents": list(set([log.get("agent", "") for log in getattr(self, 'web_search_logs', [])])),
                "total_citations": sum(len(log.get("citations", [])) for log in getattr(self, 'web_search_logs', []))
            },
            "error_tracking": {
                "total_errors": len(self.error_logs),
                "total_recoveries": len(self.recovery_actions),
                "recent_errors": self.error_logs[-5:] if len(self.error_logs) > 5 else self.error_logs,
                "recent_recoveries": self.recovery_actions[-5:] if len(self.recovery_actions) > 5 else self.recovery_actions
            }
        }
    
    def get_performance_summary(self) -> Dict[str, Any]:
        """Get performance metrics summary"""
        session_runtime = time.time() - self.init_start_time
        
        return {
            "session_runtime": session_runtime,
            "total_conversations": len(self.conversation_history),
            "average_response_time": sum(conv.get("processing_time", 0) for conv in self.conversation_history) / max(len(self.conversation_history), 1),
            "total_agent_interactions": len(self.agent_interaction_logs),
            "total_orchestrator_events": len(self.orchestrator_logs),
            "error_rate": len(self.error_logs) / max(len(self.conversation_history), 1),
            "recovery_success_rate": len(self.recovery_actions) / max(len(self.error_logs), 1) if self.error_logs else 1.0,
            "magentic_one_utilization": sum(1 for conv in self.conversation_history if conv.get("system") == "magentic_one") / max(len(self.conversation_history), 1),
            "performance_metrics": dict(self.performance_metrics)
        }
    
    def export_logs_to_file(self, filepath: str = None) -> str:
        """Export comprehensive logs to JSON file"""
        if not filepath:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filepath = f"orchestrator_logs_{self.session_id}_{timestamp}.json"
        
        logs_data = {
            "export_info": {
                "timestamp": datetime.now().isoformat(),
                "session_id": self.session_id,
                "export_type": "comprehensive_orchestrator_logs"
            },
            "logs": self.get_orchestrator_logs(),
            "performance": self.get_performance_summary(),
            "conversation_history": self.conversation_history
        }
        
        try:
            with open(filepath, 'w') as f:
                json.dump(logs_data, f, indent=2, default=str)
            
            logger.info(f"📊 Orchestrator logs exported to: {filepath}")
            return filepath
            
        except Exception as e:
            logger.error(f"❌ Failed to export logs: {e}")
            return f"Error exporting logs: {e}"

    def _format_software_inventory_response(self, raw_inventory: str, user_query: str) -> str:
        """
        Format raw software inventory into user-friendly, structured format
        
        Args:
            raw_inventory: Raw inventory data from agent
            user_query: Original user query for context
            
        Returns:
            Formatted, user-friendly software inventory
        """
        try:
            # Start building the formatted response
            formatted_parts = []
            formatted_parts.append("## 💻 **Software Inventory Summary**")
            
            # Check if inventory data is available
            if not raw_inventory or "No software inventory" in raw_inventory or "not available" in raw_inventory.lower():
                formatted_parts.append("📋 No software inventory data is currently available.")
                formatted_parts.append("\n**💡 Possible Reasons:**")
                formatted_parts.append("- Inventory collection may not be configured")
                formatted_parts.append("- Data collection agents might need initialization")
                formatted_parts.append("- Check your monitoring and inventory management settings")
                return "\n\n".join(formatted_parts)
            
            # Parse and categorize software from raw inventory
            software_list = self._parse_software_from_raw_inventory(raw_inventory)
            
            if not software_list:
                formatted_parts.append("📊 Software inventory data is being processed...")
                formatted_parts.append(f"**Raw Data Preview:** {raw_inventory[:200]}...")
                return "\n\n".join(formatted_parts)
            
            # Categorize software by type
            categories = self._categorize_software(software_list)
            
            # Add summary statistics
            total_software = sum(len(items) for items in categories.values())
            formatted_parts.append(f"📈 **Total Software Applications:** {total_software}")
            formatted_parts.append("")
            
            # Display by categories
            for category, items in categories.items():
                if items:
                    formatted_parts.append(f"### 🔧 **{category.title()}** ({len(items)} items)")
                    for item in sorted(items)[:10]:  # Show top 10 per category
                        formatted_parts.append(f"  • {item}")
                    
                    if len(items) > 10:
                        formatted_parts.append(f"  ... and {len(items) - 10} more")
                    formatted_parts.append("")
            
            # Add helpful context
            formatted_parts.append("**📋 Inventory Details:**")
            formatted_parts.append("- Data shows currently installed software applications")
            formatted_parts.append("- For EOL analysis, ask: 'What software in my inventory needs EOL review?'")
            formatted_parts.append("- For specific software: 'Check EOL status for [software name]'")
            
            return "\n\n".join(formatted_parts)
            
        except Exception as e:
            logger.error(f"❌ Software inventory formatting failed: {e}")
            return f"""## 💻 Software Inventory
            
**Data Available:** {raw_inventory[:300] if raw_inventory else 'No data'}...

**Note:** There was an issue formatting this inventory. Raw data is shown above."""

    def _format_os_inventory_response(self, raw_inventory: str, user_query: str) -> str:
        """
        Format raw OS inventory into user-friendly, structured format
        
        Args:
            raw_inventory: Raw inventory data from agent
            user_query: Original user query for context
            
        Returns:
            Formatted, user-friendly OS inventory
        """
        try:
            # Start building the formatted response
            formatted_parts = []
            formatted_parts.append("## 🖥️ **Operating System Inventory**")
            
            # Check if inventory data is available
            if not raw_inventory or "No OS inventory" in raw_inventory or "not available" in raw_inventory.lower():
                formatted_parts.append("📋 No operating system inventory data is currently available.")
                formatted_parts.append("\n**💡 Possible Reasons:**")
                formatted_parts.append("- OS discovery may not be configured")
                formatted_parts.append("- System monitoring agents might need setup")
                formatted_parts.append("- Check your infrastructure monitoring configuration")
                return "\n\n".join(formatted_parts)
            
            # Parse OS information from raw inventory
            os_data = self._parse_os_from_raw_inventory(raw_inventory)
            
            if not os_data:
                formatted_parts.append("📊 OS inventory data is being processed...")
                formatted_parts.append(f"**Raw Data Preview:** {raw_inventory[:200]}...")
                return "\n\n".join(formatted_parts)
            
            # Group by OS family
            os_families = self._group_os_by_family(os_data)
            
            # Add summary statistics
            total_systems = sum(len(systems) for systems in os_families.values())
            formatted_parts.append(f"📈 **Total Systems:** {total_systems}")
            formatted_parts.append("")
            
            # Display by OS family
            for family, systems in os_families.items():
                if systems:
                    formatted_parts.append(f"### 🔧 **{family}** ({len(systems)} systems)")
                    
                    # Group by version within family
                    version_counts = {}
                    for system in systems:
                        version = self._extract_os_version(system)
                        version_counts[version] = version_counts.get(version, 0) + 1
                    
                    for version, count in sorted(version_counts.items()):
                        formatted_parts.append(f"  • {version}: {count} system{'s' if count > 1 else ''}")
                    formatted_parts.append("")
            
            # Add helpful context
            formatted_parts.append("**📋 Inventory Details:**")
            formatted_parts.append("- Data shows currently deployed operating systems")
            formatted_parts.append("- For EOL analysis, ask: 'What OS versions in my inventory need EOL review?'")
            formatted_parts.append("- For specific OS: 'Check EOL status for [OS name and version]'")
            
            return "\n\n".join(formatted_parts)
            
        except Exception as e:
            logger.error(f"❌ OS inventory formatting failed: {e}")
            return f"""## 🖥️ Operating System Inventory
            
**Data Available:** {raw_inventory[:300] if raw_inventory else 'No data'}...

**Note:** There was an issue formatting this inventory. Raw data is shown above."""

    def _parse_software_from_raw_inventory(self, raw_inventory: str) -> List[str]:
        """Parse software list from raw inventory data"""
        try:
            software_list = []
            
            # Try to parse JSON if it looks like JSON
            if raw_inventory.strip().startswith('{') or raw_inventory.strip().startswith('['):
                import json
                try:
                    data = json.loads(raw_inventory)
                    if isinstance(data, list):
                        software_list = [str(item) for item in data if item]
                    elif isinstance(data, dict):
                        # Extract software names from various possible keys
                        for key in ['software', 'applications', 'programs', 'installed', 'data']:
                            if key in data and isinstance(data[key], list):
                                software_list.extend([str(item) for item in data[key] if item])
                except json.JSONDecodeError:
                    pass
            
            # If not JSON or JSON parsing failed, try text parsing
            if not software_list:
                lines = raw_inventory.split('\n')
                for line in lines:
                    line = line.strip()
                    if line and not line.startswith('#') and not line.startswith('//'):
                        # Remove common prefixes and clean up
                        line = re.sub(r'^[-•*]\s*', '', line)
                        if len(line) > 3 and len(line) < 100:  # Reasonable software name length
                            software_list.append(line)
            
            return software_list[:100]  # Limit to first 100 items for performance
            
        except Exception as e:
            logger.error(f"❌ Software parsing failed: {e}")
            return []

    def _parse_os_from_raw_inventory(self, raw_inventory: str) -> List[str]:
        """Parse OS list from raw inventory data"""
        try:
            os_list = []
            
            # Try to parse JSON if it looks like JSON
            if raw_inventory.strip().startswith('{') or raw_inventory.strip().startswith('['):
                import json
                try:
                    data = json.loads(raw_inventory)
                    if isinstance(data, list):
                        os_list = [str(item) for item in data if item]
                    elif isinstance(data, dict):
                        # Extract OS names from various possible keys
                        for key in ['os', 'operating_systems', 'systems', 'platforms', 'data']:
                            if key in data and isinstance(data[key], list):
                                os_list.extend([str(item) for item in data[key] if item])
                except json.JSONDecodeError:
                    pass
            
            # If not JSON or JSON parsing failed, try text parsing
            if not os_list:
                lines = raw_inventory.split('\n')
                for line in lines:
                    line = line.strip()
                    if line and not line.startswith('#') and not line.startswith('//'):
                        # Remove common prefixes and clean up
                        line = re.sub(r'^[-•*]\s*', '', line)
                        if len(line) > 3 and len(line) < 100:  # Reasonable OS name length
                            os_list.append(line)
            
            return os_list[:50]  # Limit to first 50 items for performance
            
        except Exception as e:
            logger.error(f"❌ OS parsing failed: {e}")
            return []

    def _categorize_software(self, software_list: List[str]) -> Dict[str, List[str]]:
        """Categorize software into logical groups"""
        categories = {
            "microsoft": [],
            "development": [],
            "security": [],
            "database": [],
            "web_servers": [],
            "other": []
        }
        
        for software in software_list:
            software_lower = software.lower()
            
            if any(keyword in software_lower for keyword in ['microsoft', 'windows', 'office', 'outlook', 'teams', 'sql server']):
                categories["microsoft"].append(software)
            elif any(keyword in software_lower for keyword in ['visual studio', 'git', 'node', 'python', 'java', 'eclipse', 'intellij']):
                categories["development"].append(software)
            elif any(keyword in software_lower for keyword in ['antivirus', 'firewall', 'security', 'defender', 'symantec', 'mcafee']):
                categories["security"].append(software)
            elif any(keyword in software_lower for keyword in ['sql', 'mysql', 'postgresql', 'oracle', 'mongodb', 'database']):
                categories["database"].append(software)
            elif any(keyword in software_lower for keyword in ['apache', 'nginx', 'iis', 'tomcat', 'web server']):
                categories["web_servers"].append(software)
            else:
                categories["other"].append(software)
        
        return categories

    def _group_os_by_family(self, os_list: List[str]) -> Dict[str, List[str]]:
        """Group operating systems by family"""
        families = {
            "Windows": [],
            "Linux": [],
            "Unix": [],
            "Other": []
        }
        
        for os_item in os_list:
            os_lower = os_item.lower()
            
            if any(keyword in os_lower for keyword in ['windows', 'win', 'microsoft']):
                families["Windows"].append(os_item)
            elif any(keyword in os_lower for keyword in ['ubuntu', 'centos', 'rhel', 'linux', 'debian', 'fedora', 'suse']):
                families["Linux"].append(os_item)
            elif any(keyword in os_lower for keyword in ['unix', 'aix', 'solaris', 'hp-ux']):
                families["Unix"].append(os_item)
            else:
                families["Other"].append(os_item)
        
        return families

    def _extract_os_version(self, os_string: str) -> str:
        """Extract version information from OS string"""
        # Try to extract version patterns
        version_patterns = [
            r'(\d+\.\d+)',  # X.Y format
            r'(\d{4})',     # Year format like 2019, 2022
            r'(\d+)',       # Single number
        ]
        
        for pattern in version_patterns:
            match = re.search(pattern, os_string)
            if match:
                return f"{os_string.split()[0]} {match.group(1)}"
        
        return os_string

# Create backward compatibility aliases
ChatOrchestratorAgent = MagenticOneChatOrchestrator
ChatOrchestrator = MagenticOneChatOrchestrator