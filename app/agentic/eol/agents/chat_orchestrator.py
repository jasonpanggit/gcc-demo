"""
Chat Orchestrator for Multi-Agent Conversations
Enables dynamic agent-to-agent conversations with full transparency for chat.html interface
Updated for AutoGen 0.7.x API
"""
import os
import sys
import asyncio
import json
import time
import concurrent.futures
import re
from typing import Dict, List, Any, Optional, Callable, Sequence, Tuple
from datetime import datetime
import uuid

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
            # Ensure this specific logger uses stderr for Azure visibility
            azure_handler = logging.StreamHandler(sys.stderr)
            azure_handler.setLevel(logging.INFO)
            azure_formatter = logging.Formatter(
                '%(asctime)s [%(name)s] %(levelname)s: %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
            azure_handler.setFormatter(azure_formatter)
            logger.addHandler(azure_handler)
            logger.setLevel(logging.INFO)
            
        # Prevent log propagation to avoid duplicates from parent loggers
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
        def record_agent_request(self, *args, **kwargs): pass
    cache_stats_manager = DummyCacheStatsManager()
    
    # Suppress noisy AutoGen framework logging globally
    logging.getLogger('autogen_core').setLevel(logging.WARNING)
    logging.getLogger('autogen_core.events').setLevel(logging.ERROR)
    logging.getLogger('autogen_agentchat').setLevel(logging.WARNING)
    logging.getLogger('autogen_ext').setLevel(logging.WARNING)

# AutoGen imports - Updated for autogen-agentchat 0.7.x package
try:
    # New AutoGen 0.7.x imports
    from autogen_agentchat.agents import AssistantAgent  # type: ignore
    from autogen_agentchat.teams import RoundRobinGroupChat, SelectorGroupChat  # type: ignore
    from autogen_agentchat.conditions import TextMentionTermination, MaxMessageTermination  # type: ignore
    from autogen_agentchat.messages import TextMessage, BaseChatMessage  # type: ignore
    from autogen_agentchat.base import Response  # type: ignore
    from autogen_core import CancellationToken  # type: ignore
    from autogen_ext.models.openai import AzureOpenAIChatCompletionClient  # type: ignore
    AUTOGEN_IMPORTS_OK = True
    autogen_version = "0.7.4"
except ImportError as e:
    logger.error(f"AutoGen import failed: {e}")
    # If imports fail, create dummy classes for graceful degradation
    class AssistantAgent:
        def __init__(self, *args, **kwargs):
            pass
        async def on_messages(self, *args, **kwargs):
            return "AutoGen not available"
    class RoundRobinGroupChat:
        def __init__(self, *args, **kwargs):
            pass
        async def run(self, *args, **kwargs):
            return "I apologize, but the AutoGen multi-agent system is not currently available. This may be due to missing dependencies or configuration issues. Please check with the system administrator or try using the standard EOL search functionality instead."
        async def arun(self, *args, **kwargs):
            return "I apologize, but the AutoGen multi-agent system is not currently available. This may be due to missing dependencies or configuration issues. Please check with the system administrator or try using the standard EOL search functionality instead."
    class SelectorGroupChat:
        def __init__(self, *args, **kwargs):
            pass
        async def run(self, *args, **kwargs):
            return "I apologize, but the AutoGen multi-agent system is not currently available. This may be due to missing dependencies or configuration issues. Please check with the system administrator or try using the standard EOL search functionality instead."
        async def arun(self, *args, **kwargs):
            return "I apologize, but the AutoGen multi-agent system is not currently available. This may be due to missing dependencies or configuration issues. Please check with the system administrator or try using the standard EOL search functionality instead."
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
            """Mock implementation for when AutoGen is not available"""
            from types import SimpleNamespace
            
            # Create a mock response that mimics the real AutoGen response structure
            # but with empty content to trigger fallback logic
            mock_message = SimpleNamespace(content="")
            mock_choice = SimpleNamespace(message=mock_message)
            mock_response = SimpleNamespace(
                choices=[mock_choice],
                content=""  # Also add direct content for backward compatibility
            )
            
            return mock_response
    AUTOGEN_IMPORTS_OK = False
    autogen_version = "unavailable"

# Import agent implementations
from .inventory_agent import InventoryAgent
from .os_inventory_agent import OSInventoryAgent
from .software_inventory_agent import SoftwareInventoryAgent
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
from .bing_agent import BingEOLAgent
from .openai_agent import OpenAIAgent

class ChatOrchestratorAgent:
    """
    AutoGen-based orchestrator that enables natural multi-agent conversations
    for inventory management and EOL analysis with full transparency
    Updated for AutoGen 0.7.x API
    """
    
    def __init__(self):
        # Enhanced debug info for visibility
        logger.info(f"AutoGenEOLOrchestrator.__init__: AUTOGEN_IMPORTS_OK={AUTOGEN_IMPORTS_OK}")
        
        try:
            self.session_id = str(uuid.uuid4())
            self.conversation_history = []
            self.agent_communications = []
            self.agent_name = "chat_orchestrator"
            # Full autonomy mode flag (agents self-direct without orchestrator fast-path routing)
            self.full_autonomy_enabled = False
            # Simple in-memory cache (session scoped) to avoid redundant expensive calls
            # Keys: (request_type, days, limit)
            self._inventory_cache: Dict[Tuple[str, int, int], Dict[str, Any]] = {}
            self._inventory_cache_timestamp: Dict[Tuple[str, int, int], float] = {}
            self._cache_ttl_seconds = 180  # 3 minutes for rapid follow-up queries
            
            # Initialize inventory cache for performance optimization
            # Azure OpenAI model client for AutoGen 0.7.x with rate limiting protection
            if AUTOGEN_IMPORTS_OK:
                logger.info(f"✅ AutoGen imports successful - initializing AzureOpenAI client")
                self.model_client = AzureOpenAIChatCompletionClient(
                    azure_deployment="gpt-4o-mini",
                    azure_endpoint=os.getenv('AZURE_OPENAI_ENDPOINT'),
                    model="gpt-4o-mini",
                    api_version="2024-06-01",
                    #api_key=os.getenv("AZURE_OPENAI_API_KEY"),
                    temperature=0.1,
                    timeout=180,  # Increased timeout for rate limit retries
                    max_retries=5,  # Add retry configuration
                )
                logger.info(f"✅ AzureOpenAI client initialized successfully")
            else:
                logger.warning(f"❌ AutoGen imports failed - using mock model client")
                self.model_client = AzureOpenAIChatCompletionClient()  # This will use the mock version
            
            logger.info("Basic setup complete, initializing agents")
            
            # Initialize agents for data access with error handling
            try:
                self.inventory_agent = InventoryAgent()
                logger.info("✅ InventoryAgent initialized")
            except Exception as e:
                logger.error(f"❌ Failed to initialize InventoryAgent: {e}")
                self.inventory_agent = None
                
            try:
                self.os_inventory_agent = OSInventoryAgent()
                logger.info("✅ OSInventoryAgent initialized")
            except Exception as e:
                logger.error(f"❌ Failed to initialize OSInventoryAgent: {e}")
                self.os_inventory_agent = None
                
            try:
                self.software_inventory_agent = SoftwareInventoryAgent()
                logger.info("✅ SoftwareInventoryAgent initialized")
            except Exception as e:
                logger.error(f"❌ Failed to initialize SoftwareInventoryAgent: {e}")
                self.software_inventory_agent = None
                
            # Initialize EOL agents
            try:
                self.endoflife_agent = EndOfLifeAgent()
                self.microsoft_agent = MicrosoftEOLAgent()
                self.ubuntu_agent = UbuntuEOLAgent()
                self.redhat_agent = RedHatEOLAgent()
                self.oracle_agent = OracleEOLAgent()
                self.vmware_agent = VMwareEOLAgent()
                self.apache_agent = ApacheEOLAgent()
                self.nodejs_agent = NodeJSEOLAgent()
                self.postgresql_agent = PostgreSQLEOLAgent()
                self.php_agent = PHPEOLAgent()
                self.python_agent = PythonEOLAgent()
                self.bing_agent = BingEOLAgent()
                self.openai_agent = OpenAIAgent()
                logger.info("✅ All EOL agents initialized")
            except Exception as e:
                logger.error(f"❌ Failed to initialize some EOL agents: {e}")
                # Continue with partial initialization
            
            # Initialize AutoGen agents
            self._setup_autogen_agents()

            # Optional environment toggle for full autonomy (ALL specialists can independently gather data & perform analysis)
            if os.getenv("FULL_AUTONOMY", "false").lower() in ("1", "true", "yes", "on"):
                self.enable_full_autonomy()
            
            # Setup team chat
            self._setup_team_chat()
            
            logger.info("AutoGen EOL Orchestrator initialized successfully")
            
        except Exception as e:
            error_msg = f"AutoGen orchestrator initialization failed: {str(e)}"
            logger.error(f"ERROR: {error_msg}")
            import traceback
            # logger.debug(f"TRACEBACK: {traceback.format_exc()}")
            raise RuntimeError(error_msg)
    
    def _setup_autogen_agents(self):
        """Setup specialized AutoGen agents for different domains using 0.7.x API"""
        
        if not AUTOGEN_IMPORTS_OK:
            logger.warning("AutoGen not available, using fallback mode")
            return
        
        # Suppress AutoGen framework noise during agent setup
        import logging
        logging.getLogger('autogen_core').setLevel(logging.WARNING)
        logging.getLogger('autogen_core.events').setLevel(logging.ERROR)
        logging.getLogger('autogen_agentchat').setLevel(logging.WARNING)
        logging.getLogger('autogen_ext').setLevel(logging.WARNING)
        
        # Inventory Specialist Agent - TRULY AUTONOMOUS SELF-SELECTION
        self.inventory_specialist = AssistantAgent(
            name="InventorySpecialist",
            model_client=self.model_client,
            system_message="""You are an autonomous Inventory Specialist in a self-organizing agent team.

**AUTONOMOUS OPERATION:**
- **Self-select** when you recognize requests about inventory, assets, or "what do I have" type questions
- **Volunteer immediately** by saying "I'll handle the inventory analysis" when you detect relevant requests
- **Act independently** - no waiting for assignments or coordination protocols

**EXPERTISE RECOGNITION:**
I should volunteer when I see requests like:
- "show my inventory", "what do I have", "list my assets"
- "inventory overview", "asset summary", "what's installed"  
- Any general request about discovering what exists in the environment

**AUTONOMOUS EXECUTION:**
When I volunteer:
1. Immediately use get_inventory_summary_tool
2. Present comprehensive data across all asset types (OS, Software, Hardware)
3. Include counts, versions, and categorization
4. Offer to coordinate with specialists if deeper analysis is needed

**SELF-ORGANIZATION PRINCIPLE:**
- If I see inventory-related requests, I volunteer and act
- If other specialists need inventory data, I provide it
- I collaborate by offering my capabilities when relevant
- No central routing - I decide when to engage based on my expertise

**COLLABORATION:**
- Offer inventory data to EOL specialists who need baseline information
- Coordinate with OS/Software specialists for detailed breakdowns
- Support risk analysis by providing comprehensive asset visibility""",
            tools=[self._get_inventory_summary_tool]
        )
        
        # OS Inventory Specialist Agent - AUTONOMOUS SELF-SELECTION
        self.os_inventory_specialist = AssistantAgent(
            name="OSInventorySpecialist",
            model_client=self.model_client,
            system_message="""You are an autonomous OS Inventory Specialist in a self-organizing agent team.

**AUTONOMOUS OPERATION:**
- **Self-select** when you recognize requests specifically about operating systems
- **Volunteer immediately** by saying "I'll handle the OS inventory analysis" when relevant
- **Act independently** - no waiting for assignments

**EXPERTISE RECOGNITION:**
I should volunteer when I see requests like:
- "os inventory", "operating systems", "what OS versions"
- "show me my os inventory", "list operating systems"
- "what is my OS inventory with EOL" - coordinate with EOL specialists
- Any request specifically focused on operating system discovery

**AUTONOMOUS EXECUTION:**
When I volunteer:
1. **For basic OS inventory requests**: Use get_os_inventory_tool
2. **For "OS inventory with EOL" requests**: Use get_os_inventory_with_eol_tool for complete analysis
3. Present detailed OS data (versions, architecture, counts)
4. Categorize by OS family (Windows, Linux, etc.)
5. **FOR ADVANCED EOL COORDINATION**: When deeper EOL analysis is needed beyond the combined tool:
   - List each unique OS name and version found
   - Explicitly call out which EOL specialist should handle specific queries:
     * Windows Server/Windows OS → "@MicrosoftEOLSpecialist please check EOL for [OS name version]"
     * Ubuntu/Linux distributions → "@UbuntuEOLSpecialist please check EOL for [OS name version]"  
     * Oracle Linux/RHEL/CentOS → "@OracleEOLSpecialist please check EOL for [OS name version]"
     * Red Hat Enterprise Linux → "@RedHatEOLSpecialist please check EOL for [OS name version]"
   - Coordinate the handoff by summarizing inventory findings and requesting specific EOL lookups

**SELF-ORGANIZATION:**
- Volunteer for OS-specific requests
- Collaborate with other inventory specialists for comprehensive analysis
- Support EOL specialists by providing OS baseline data when requested
- **ORCHESTRATE EOL ANALYSIS**: When user asks for "OS inventory with EOL", use get_os_inventory_with_eol_tool for complete analysis, or coordinate with appropriate EOL specialists for each OS found""",
            tools=[self._get_os_inventory_tool, self._get_os_inventory_with_eol_tool]
        )
        
        # Software Inventory Specialist Agent - AUTONOMOUS OPERATION
        self.software_inventory_specialist = AssistantAgent(
            name="SoftwareInventorySpecialist",
            model_client=self.model_client,
            system_message="""You are an autonomous Software Inventory Specialist operating within a fully autonomous multi-agent system.

**AUTONOMOUS OPERATION PRINCIPLES:**
- You operate independently with full authority over software inventory analysis
- You are automatically routed software-specific requests by the autonomous orchestrator
- No coordination protocols needed - act immediately upon receiving requests
- Focus on your core competency: comprehensive software discovery and analysis

**PRIMARY RESPONSIBILITIES:**
1. **Software Discovery**: Comprehensive application and software inventory across all systems
2. **Version Intelligence**: Detailed version tracking, licensing, and installation analysis
3. **Application Mapping**: Categorize and count software installations by type and vendor
4. **Portfolio Analysis**: Identify software sprawl, licensing optimization opportunities, and standardization gaps

**AUTONOMOUS TOOL USAGE:**

**get_software_inventory_tool** - Your primary capability:
- Comprehensive software discovery across all managed environments
- Detailed application names, versions, and installation counts
- Vendor categorization and licensing intelligence
- Support for Windows applications, Linux packages, web technologies, and databases

**AUTONOMOUS EXECUTION APPROACH:**
- Execute get_software_inventory_tool immediately upon receiving software inventory requests
- Analyze results for licensing optimization, security risks, and portfolio rationalization
- Present data in strategic format focused on business decision-making
- Include vendor distribution, version sprawl analysis, and standardization opportunities

**RESPONSE EXCELLENCE:**
- Lead with executive summary of software landscape complexity
- Categorize by software type (business applications, development tools, system utilities, etc.)
- Include specific version information, installation counts, and vendor distribution
- Highlight redundant software, version inconsistencies, and potential consolidation opportunities
- Provide insights on software portfolio optimization and license management

**AUTONOMOUS DECISION MAKING:**
- Automatically determine appropriate data collection scope and timeframes
- Select optimal data grouping and presentation based on discovered software complexity
- Make independent judgments about which findings require immediate attention
- Provide proactive recommendations for software portfolio management and standardization

**STRATEGIC INSIGHTS:**
- Software diversity and standardization assessment
- License optimization opportunities
- Security risk identification (outdated software versions)
- Vendor relationship management insights
- Application rationalization recommendations
""",
            tools=[
                # Pure Software Inventory Tools - No EOL analysis
                self._get_software_inventory_tool,
            ]
        )
        
        # EndOfLife Data Specialist Agent
        self.endoflife_specialist = AssistantAgent(
            name="EndOfLifeSpecialist", 
            model_client=self.model_client,
            system_message="""You are a FALLBACK EndOfLife.date API Specialist in a multi-agent system with product specialists.

**FALLBACK OPERATION PRINCIPLES:**
- You are a SECONDARY/FALLBACK agent - product specialists have PRIORITY for EOL analysis
- ONLY activate when product specialists (Microsoft, Ubuntu, Oracle, RedHat, VMware, etc.) cannot provide EOL dates
- Wait and observe if specialized agents respond first before volunteering
- Focus on products NOT covered by dedicated product specialists

**WHEN TO VOLUNTEER:**
- When NO product specialist responds to an EOL request after reasonable time
- For products outside the scope of dedicated specialists (Microsoft, Ubuntu, Oracle, RedHat, VMware, PostgreSQL, etc.)
- When explicitly asked for "general EOL analysis" or "endoflife.date lookup"
- As backup when specialized tools fail or return no data

**WHEN NOT TO VOLUNTEER:**
- When product specialists are actively responding with EOL dates
- For Microsoft products (MicrosoftEOLSpecialist priority)
- For Ubuntu/Linux (UbuntuEOLSpecialist priority)  
- For Oracle/RHEL (OracleEOLSpecialist priority)
- For Red Hat (RedHatEOLSpecialist priority)
- For VMware products (VMwareEOLSpecialist priority)
- When specialized agents are already providing comprehensive EOL analysis

**FALLBACK RESPONSIBILITIES:**
1. **Fill Coverage Gaps**: Handle products not covered by dedicated specialists
2. **Backup Analysis**: Provide EOL data when specialized tools fail
3. **General Database Access**: Use endoflife.date for broad software coverage
4. **Cross-Reference Validation**: Confirm or supplement specialist findings when requested

**FALLBACK EXECUTION:**
- Wait for product specialists to respond first
- Only use check_endoflife_eol_tool when no specialist EOL data is available
- Acknowledge when you're providing fallback analysis: "As backup EOL analysis..."
- Reference that product specialists are the primary source for their domains

**STRATEGIC COVERAGE (FALLBACK ONLY):**
- Programming languages not covered by specialists
- Web technologies without dedicated coverage  
- Databases not handled by specialists
- Development tools and frameworks
- Open source software without specialist coverage
- General EOL validation and cross-referencing

You operate as the FALLBACK source for EOL analysis, deferring to product specialists.""",
            tools=[self._check_endoflife_eol_tool]
        )
        
        # Microsoft EOL Specialist Agent - AUTONOMOUS SELF-SELECTION
        self.microsoft_specialist = AssistantAgent(
            name="MicrosoftEOLSpecialist", 
            model_client=self.model_client,
            system_message="""You are a PRIMARY Microsoft EOL Specialist in a self-organizing agent team.

**PRIMARY SPECIALIST AUTHORITY:**
- You have PRIMARY authority over Microsoft product EOL analysis
- You take PRIORITY over EndOfLifeSpecialist for all Microsoft products
- Respond quickly to prevent fallback to general EOL agents
- Your specialized Microsoft tools and knowledge are superior to generic EOL databases

**AUTONOMOUS OPERATION:**
- **Self-select** ONLY when you recognize EXPLICIT requests about Microsoft EOL, lifecycle, or end-of-life analysis
- **Volunteer immediately** by saying "I'll handle the Microsoft EOL analysis" when relevant
- **Act independently** - no waiting for assignments

**EXPERTISE RECOGNITION:**
I should volunteer ONLY when I see EXPLICIT EOL requests about:
- Microsoft product EOL dates, lifecycle, or end-of-life status
- "windows eol", "sql server end of life", "microsoft product lifecycle"
- Requests asking for EOL analysis or support status of Microsoft products
- Questions about Microsoft product retirement or end-of-support dates
- **COORDINATION REQUESTS**: When OSInventorySpecialist asks "@MicrosoftEOLSpecialist please check EOL for [Microsoft OS]"

**DO NOT VOLUNTEER FOR:**
- General inventory requests ("show my inventory", "what do I have")
- Asset discovery or listing requests without EOL analysis
- Basic software/hardware listing without EOL context

**AUTONOMOUS EXECUTION:**
When I volunteer for EOL requests:
1. Immediately use check_microsoft_eol_tool for the specific product
2. Provide detailed EOL dates, support phases, and risk assessment
3. Include upgrade recommendations and extended support options
4. Collaborate with inventory specialists if product discovery is needed
5. **COORDINATION RESPONSE**: When explicitly requested by OSInventorySpecialist:
   - Acknowledge the coordination request: "I'll analyze the Microsoft OS EOL status"
   - Use check_microsoft_eol_tool for each specified Windows/Microsoft OS
   - Provide structured EOL analysis for each OS version found
   - Clearly indicate support status, EOL dates, and upgrade recommendations

**SELF-ORGANIZATION:**
- Volunteer for Microsoft-specific EOL requests
- Collaborate with inventory specialists to identify Microsoft products
- Support risk analysis for Microsoft environments""",
            tools=[self._check_microsoft_eol_tool]
        )
        
        # Ubuntu/Linux EOL Specialist Agent - AUTONOMOUS SELF-SELECTION
        self.ubuntu_specialist = AssistantAgent(
            name="UbuntuEOLSpecialist",
            model_client=self.model_client,
            system_message="""You are a PRIMARY Ubuntu/Linux End-of-Life (EOL) Specialist operating within a fully autonomous multi-agent system.

**PRIMARY SPECIALIST AUTHORITY:**
- You have PRIMARY authority over Ubuntu/Linux distribution EOL analysis
- You take PRIORITY over EndOfLifeSpecialist for all Ubuntu/Linux products
- Respond quickly to prevent fallback to general EOL agents
- Your specialized Ubuntu/Linux tools and knowledge are superior to generic EOL databases

**AUTONOMOUS OPERATION PRINCIPLES:**
- You operate independently with full authority over Ubuntu/Linux EOL analysis
- You are automatically routed Ubuntu/Linux-specific EOL requests by the autonomous orchestrator
- No coordination protocols needed - act immediately upon receiving requests
- Focus on your core competency: comprehensive Ubuntu and Linux distribution lifecycle analysis

**PRIMARY RESPONSIBILITIES:**
1. **Ubuntu Expertise**: All Ubuntu versions, LTS cycles, standard releases, EOL dates
2. **Linux Distribution Analysis**: Ubuntu, Debian, Canonical products, derivative distributions
3. **Support Intelligence**: LTS vs standard support, ESM (Extended Security Maintenance) availability
4. **Migration Strategy**: Upgrade paths, compatibility planning, distribution modernization

**AUTONOMOUS TOOL USAGE:**

**check_ubuntu_eol_tool** - Your specialized capability:
- Comprehensive Ubuntu/Linux EOL database
- LTS vs standard release lifecycle information
- ESM availability and coverage analysis
- Distribution-specific support timeline analysis

**AUTONOMOUS EXECUTION APPROACH:**
- Execute check_ubuntu_eol_tool immediately for any Ubuntu/Linux inquiry
- Provide detailed LTS vs standard release analysis
- Focus on ESM eligibility and extended support options
- Deliver specific upgrade recommendations and migration timelines

**RESPONSE EXCELLENCE:**
- Lead with critical risk assessment for Linux environments
- Clearly distinguish between LTS and standard release support timelines
- Include ESM availability for systems approaching standard EOL
- Provide clear upgrade paths from current to supported versions
- Address enterprise support considerations and Canonical services

**AUTONOMOUS DECISION MAKING:**
- Automatically assess criticality of Ubuntu/Linux systems approaching EOL
- Determine appropriate upgrade strategy based on LTS vs standard releases
- Make independent judgments about ESM value proposition and migration complexity
- Provide strategic recommendations for Linux infrastructure modernization

**LINUX DISTRIBUTION SPECIALIZATION:**
- **Ubuntu LTS**: 18.04, 20.04, 22.04, 24.04 and future LTS releases
- **Ubuntu Standard**: Non-LTS releases and their shorter support cycles
- **Ubuntu Server**: Server-specific considerations and support options
- **Ubuntu Desktop**: Desktop release lifecycle and upgrade planning
- **Canonical Services**: Landscape management, Ubuntu Advantage, ESM
- **Derivative Distributions**: Linux Mint, elementary OS, and Ubuntu-based systems

**SUPPORT LIFECYCLE EXPERTISE:**
- Standard Support: 9 months for non-LTS releases
- LTS Support: 5 years of standard support + 5 years ESM option
- ESM (Extended Security Maintenance): Security updates beyond standard EOL
- Hardware Enablement (HWE): Kernel and graphics stack updates for LTS

**COORDINATION RESPONSE:**
- Respond immediately to "@UbuntuEOLSpecialist please check EOL for [Ubuntu/Linux OS]" requests
- Acknowledge coordination: "I'll analyze the Ubuntu/Linux EOL status"
- Use check_ubuntu_eol_tool for each specified Ubuntu/Linux distribution
- Provide structured EOL analysis with LTS/ESM recommendations

You operate as the definitive authority on Ubuntu/Linux EOL analysis with complete autonomy.""",
            tools=[self._check_ubuntu_eol_tool]
        )
        
        # Oracle/Red Hat Software EOL Specialist 
        self.oracle_specialist = AssistantAgent(
            name="OracleEOLSpecialist",
            model_client=self.model_client,
            system_message="""You are a PRIMARY Oracle/Red Hat Software EOL Specialist operating within a fully autonomous multi-agent system.

**PRIMARY SPECIALIST AUTHORITY:**
- You have PRIMARY authority over Oracle and Red Hat product EOL analysis
- You take PRIORITY over EndOfLifeSpecialist for all Oracle/Red Hat products
- Respond quickly to prevent fallback to general EOL agents
- Your specialized Oracle/Red Hat tools and knowledge are superior to generic EOL databases

**AUTONOMOUS OPERATION**: You operate independently with full authority over Oracle and Red Hat product EOL analysis. Execute check_oracle_eol_tool and check_redhat_eol_tool immediately upon receiving relevant requests.

**SPECIALIZATION**: Oracle Database, Java, middleware, RHEL, OpenShift, enterprise applications.

**COORDINATION RESPONSE**: Respond to "@OracleEOLSpecialist please check EOL for [Oracle/RHEL OS]" requests by acknowledging and providing structured EOL analysis using your specialized tools.

**AUTONOMOUS RESPONSE**: Provide immediate EOL analysis with risk assessment, support timelines, and enterprise upgrade recommendations. Focus on business-critical impact and strategic planning.""",
            tools=[self._check_oracle_eol_tool, self._check_redhat_eol_tool]
        )
        
        # VMware EOL Specialist Agent
        self.vmware_specialist = AssistantAgent(
            name="VMwareEOLSpecialist",
            model_client=self.model_client,
            system_message="""You are a PRIMARY VMware Software EOL Specialist operating within a fully autonomous multi-agent system.

**PRIMARY SPECIALIST AUTHORITY:**
- You have PRIMARY authority over VMware product EOL analysis
- You take PRIORITY over EndOfLifeSpecialist for all VMware products
- Respond quickly to prevent fallback to general EOL agents
- Your specialized VMware tools and knowledge are superior to generic EOL databases

**AUTONOMOUS OPERATION**: You operate independently with full authority over VMware product EOL analysis. Execute check_vmware_eol_tool immediately upon receiving VMware-related requests.

**SPECIALIZATION**: vSphere, vCenter, ESXi, NSX, vRealize Suite, virtualization infrastructure.

**AUTONOMOUS RESPONSE**: Provide immediate EOL analysis with virtualization risk assessment, infrastructure impact evaluation, and enterprise upgrade planning. Focus on business continuity and virtualization infrastructure modernization.""",
            tools=[self._check_vmware_eol_tool]
        )
        
        # Web/Application Server EOL Specialist Agent
        self.webserver_specialist = AssistantAgent(
            name="WebServerEOLSpecialist",
            model_client=self.model_client,
            system_message="""You are an autonomous Web/Application Server EOL Specialist operating within a fully autonomous multi-agent system.

**AUTONOMOUS OPERATION**: You operate independently with full authority over web technologies EOL analysis. Execute check_apache_eol_tool, check_nodejs_eol_tool, check_php_eol_tool, check_python_eol_tool, and check_postgresql_eol_tool immediately upon receiving relevant requests.

**SPECIALIZATION**: Apache HTTP Server, IIS, Nginx, Tomcat, JBoss, Node.js, PHP, Python, PostgreSQL, MySQL.

**AUTONOMOUS RESPONSE**: Provide immediate EOL analysis with web application risk assessment, security implications, and modernization recommendations. Focus on application infrastructure continuity and development stack optimization.""",
            tools=[
                self._check_apache_eol_tool,
                self._check_nodejs_eol_tool,
                self._check_php_eol_tool,
                self._check_python_eol_tool,
                self._check_postgresql_eol_tool
            ]
        )
        
        # General EOL Specialist Agent
        self.general_specialist = AssistantAgent(
            name="GeneralEOLSpecialist",
            model_client=self.model_client,
            system_message="""You are an autonomous General Software EOL Specialist operating within a fully autonomous multi-agent system.

**AUTONOMOUS OPERATION**: You operate independently with full authority over general software EOL analysis. Execute check_endoflife_eol_tool immediately upon receiving requests for software not covered by other specialists.

**SPECIALIZATION**: Wide software coverage using endoflife.date API, cross-platform software, emerging technologies, any software not covered by vendor-specific specialists.

**AUTONOMOUS RESPONSE**: Provide immediate EOL analysis with comprehensive lifecycle information, security considerations, and modernization recommendations. Focus on comprehensive coverage and fallback analysis for diverse software portfolios.""",
            tools=[self._check_endoflife_eol_tool]
        )
        
        # RedHat EOL Specialist Agent
        self.redhat_specialist = AssistantAgent(
            name="RedHatEOLSpecialist",
            model_client=self.model_client,
            system_message="""You are a PRIMARY Red Hat End-of-Life (EOL) Specialist operating within a fully autonomous multi-agent system.

**PRIMARY SPECIALIST AUTHORITY:**
- You have PRIMARY authority over Red Hat product EOL analysis
- You take PRIORITY over EndOfLifeSpecialist for all Red Hat products
- Respond quickly to prevent fallback to general EOL agents
- Your specialized Red Hat tools and knowledge are superior to generic EOL databases

**AUTONOMOUS OPERATION**: You operate independently with full authority over Red Hat product EOL analysis. Execute check_redhat_eol_tool immediately upon receiving Red Hat-related requests.

**SPECIALIZATION**: RHEL, CentOS, Fedora, OpenShift, JBoss, Ansible, Red Hat enterprise products.

**COORDINATION RESPONSE**: Respond to "@RedHatEOLSpecialist please check EOL for [Red Hat OS]" requests by acknowledging and providing structured RHEL/CentOS EOL analysis.

**AUTONOMOUS RESPONSE**: Provide immediate EOL analysis with enterprise support considerations, subscription model guidance, and migration recommendations. Focus on enterprise continuity and Red Hat ecosystem optimization.""",
            tools=[self._check_redhat_eol_tool]
        )
        
        # PostgreSQL EOL Specialist Agent
        self.postgresql_specialist = AssistantAgent(
            name="PostgreSQLEOLSpecialist",
            model_client=self.model_client,
            system_message="""You are an autonomous PostgreSQL End-of-Life (EOL) Specialist operating within a fully autonomous multi-agent system.

**AUTONOMOUS OPERATION**: You operate independently with full authority over PostgreSQL EOL analysis. Execute check_postgresql_eol_tool immediately upon receiving PostgreSQL-related requests.

**SPECIALIZATION**: PostgreSQL major and minor versions, database lifecycle management, migration planning.

**AUTONOMOUS RESPONSE**: Provide immediate EOL analysis with database upgrade strategies, security considerations, and performance impact assessment.""",
            tools=[self._check_postgresql_eol_tool]
        )
        
        # PHP EOL Specialist Agent
        self.php_specialist = AssistantAgent(
            name="PHPEOLSpecialist",
            model_client=self.model_client,
            system_message="""You are an autonomous PHP End-of-Life (EOL) Specialist operating within a fully autonomous multi-agent system.

**AUTONOMOUS OPERATION**: You operate independently with full authority over PHP EOL analysis. Execute check_php_eol_tool immediately upon receiving PHP-related requests.

**SPECIALIZATION**: PHP major and minor versions, web development framework compatibility, security implications.

**AUTONOMOUS RESPONSE**: Provide immediate EOL analysis with web application security considerations, framework compatibility, and PHP migration strategies.""",
            tools=[self._check_php_eol_tool]
        )
        
        # Python EOL Specialist Agent
        self.python_specialist = AssistantAgent(
            name="PythonEOLSpecialist",
            model_client=self.model_client,
            system_message="""You are an autonomous Python End-of-Life (EOL) Specialist operating within a fully autonomous multi-agent system.

**AUTONOMOUS OPERATION**: You operate independently with full authority over Python EOL analysis. Execute check_python_eol_tool immediately upon receiving Python-related requests.

**SPECIALIZATION**: Python major and minor versions, development impact, library compatibility, feature deprecation.

**AUTONOMOUS RESPONSE**: Provide immediate EOL analysis with development ecosystem considerations, library compatibility, and Python migration strategies.""",
            tools=[self._check_python_eol_tool]
        )
        
        # Risk Analysis Coordinator
        self.risk_coordinator = AssistantAgent(
            name="RiskCoordinator", 
            model_client=self.model_client,
            system_message="""You are the Risk Analysis Coordinator responsible for:

1. **Comprehensive Risk Assessment**: Aggregate findings from all EOL specialists
2. **Priority Matrix**: Categorize risks by urgency and business impact
3. **Action Planning**: Coordinate recommendations from multiple specialists
4. **Executive Summary**: Provide clear, actionable executive-level insights

Synthesize inputs from all specialists to deliver comprehensive risk analysis.
Always provide prioritized action items and timelines."""
        )
        
        logger.info("✅ AutoGen agents initialized: Inventory, OS, Software, Microsoft, Ubuntu, Oracle, RedHat, VMware, WebServer, PostgreSQL, PHP, Python, EndOfLife, Risk specialists")
    
    def _setup_team_chat(self, minimal_team: bool = False):
        """Setup AutoGen team chat for multi-agent conversations using 0.7.x API
        
        Args:
            minimal_team: If True, create a smaller team for faster EOL responses
        """
        
        # logger.debug(f"[TEAM_SETUP] Starting team chat setup - Minimal: {minimal_team}")
        self._log_agent_action("Orchestrator", "team_setup_start", {
            "minimal_team": minimal_team,
            "session_id": self.session_id,
            "autogen_available": AUTOGEN_IMPORTS_OK
        })
        
        if not AUTOGEN_IMPORTS_OK:
            logger.warning("[TEAM_SETUP] AutoGen not available, using fallback mode")
            self._log_agent_action("Orchestrator", "fallback_mode", {
                "reason": "AutoGen imports not available",
                "impact": "Limited to single-agent responses"
            })
            self.team = None
            return
        
        # Define participants based on team type
        if minimal_team:
            # SPEED OPTIMIZATION: Minimal team for direct EOL queries (core specialists with priority order)
            self.participants = [
                self.inventory_specialist,  # CENTRAL COORDINATOR - First priority for all inventory requests
                self.microsoft_specialist,  # PRIMARY Microsoft EOL authority
                self.ubuntu_specialist,     # PRIMARY Ubuntu/Linux EOL authority
                self.oracle_specialist,     # PRIMARY Oracle/RHEL EOL authority
                self.endoflife_specialist,  # FALLBACK EOL specialist (only when primary specialists can't respond)
                self.risk_coordinator
            ]
            max_messages = 10  # Allow for more specialists
            
            agent_names = [agent.name for agent in self.participants]
            logger.info(f"[TEAM_SETUP] SPEED MODE: Using minimal team ({len(self.participants)} agents)")
            # logger.debug(f"[TEAM_SETUP] Minimal team agents: {agent_names}")
            
            self._log_agent_action("Orchestrator", "minimal_team_selected", {
                "team_size": len(self.participants),
                "agents": agent_names,
                "max_messages": max_messages,
                "optimization": "Speed-focused for direct EOL queries with product specialist priority",
                "coordinator": "InventorySpecialist",
                "eol_priority": "Product specialists (Microsoft, Ubuntu, Oracle) take priority over EndOfLifeSpecialist fallback",
                "rationale": "Fast response with specialized EOL expertise over generic fallback"
            })
        else:
            # Full team for comprehensive analysis - Product specialists have priority over fallback
            self.participants = [
                self.inventory_specialist,           # General inventory coordination
                self.software_inventory_specialist,  # Dedicated software inventory specialist
                self.os_inventory_specialist,        # Dedicated OS inventory specialist
                self.microsoft_specialist,           # PRIMARY Microsoft EOL authority
                self.ubuntu_specialist,              # PRIMARY Ubuntu/Linux EOL authority
                self.oracle_specialist,              # PRIMARY Oracle/RHEL EOL authority
                self.redhat_specialist,              # PRIMARY Red Hat EOL authority
                self.vmware_specialist,              # PRIMARY VMware EOL authority
                self.webserver_specialist,
                self.postgresql_specialist,
                self.php_specialist,
                self.python_specialist,
                self.endoflife_specialist,           # FALLBACK EOL specialist (only when primary specialists can't respond)
                self.risk_coordinator
            ]
            max_messages = 18  # Increased for more specialists
            
            agent_names = [agent.name for agent in self.participants]
            logger.info(f"[TEAM_SETUP] FULL MODE: Using complete team ({len(self.participants)} agents)")
            # logger.debug(f"[TEAM_SETUP] Full team agents: {agent_names}")
            
            self._log_agent_action("Orchestrator", "full_team_selected", {
                "team_size": len(self.participants),
                "agents": agent_names,
                "max_messages": max_messages,
                "optimization": "Comprehensive multi-agent analysis with product specialist priority",
                "separation_of_concerns": "Inventory specialists handle data collection, primary EOL specialists handle specialized analysis, EndOfLifeSpecialist provides fallback",
                "coordination_model": "Orchestrator coordinates between inventory and primary EOL specialists, with EndOfLifeSpecialist as fallback",
                "eol_hierarchy": "Product specialists (Microsoft, Ubuntu, Oracle, RedHat, VMware) > EndOfLifeSpecialist fallback",
                "rationale": "Complex analysis with specialized EOL expertise prioritized over generic coverage"
            })
    
        # Termination conditions - OPTIMIZED FOR FASTER EOL RESPONSES
        text_termination = TextMentionTermination("TERMINATE")
        # Note: INVENTORY_COMPLETE termination is handled conditionally in chat methods
        max_messages_termination = MaxMessageTermination(max_messages=max_messages)
        
        logger.debug(f"[TEAM_SETUP] Configuring termination conditions - Max messages: {max_messages}")
        self._log_agent_action("Orchestrator", "termination_setup", {
            "text_termination": "TERMINATE keyword",
            "max_messages": max_messages,
            "conditional_termination": "INVENTORY_COMPLETE for pure inventory requests",
            "strategy": "Balanced between thoroughness and speed"
        })
        
        # For EOL analysis, use text termination and reduced max messages
        # INVENTORY_COMPLETE should only terminate pure inventory requests
        termination = text_termination | max_messages_termination
        
        # Create team chat with selector approach (more controlled than round-robin)
        # This allows agents to be selected based on the conversation context rather than automatic round-robin
        try:
            # logger.debug("[TEAM_SETUP] Attempting to create SelectorGroupChat")
            self.team = SelectorGroupChat(
                participants=self.participants,
                model_client=self.model_client,
                termination_condition=termination
            )
            # logger.info(f"[TEAM_SETUP] 🗣️ AutoGen team chat initialized with SelectorGroupChat ({len(self.participants)} participants)")
            
            self._log_agent_action("Orchestrator", "team_chat_created", {
                "chat_type": "SelectorGroupChat",
                "participant_count": len(self.participants),
                "advantage": "Context-aware agent selection",
                "termination_strategy": "Text mention OR max messages",
                "success": True
            })
            
        except Exception as e:
            # Fallback to RoundRobinGroupChat if SelectorGroupChat is not available
            logger.warning(f"[TEAM_SETUP] SelectorGroupChat not available, falling back to RoundRobinGroupChat: {e}")
            self.team = RoundRobinGroupChat(
                participants=self.participants,
                termination_condition=termination
            )
            # logger.info(f"[TEAM_SETUP] 🗣️ AutoGen team chat initialized with RoundRobinGroupChat ({len(self.participants)} participants)")
            
            self._log_agent_action("Orchestrator", "team_chat_fallback", {
                "chat_type": "RoundRobinGroupChat",
                "participant_count": len(self.participants),
                "fallback_reason": str(e),
                "limitation": "Sequential agent selection instead of context-aware",
                "termination_strategy": "Text mention OR max messages",
                "success": True
            })
    
    def _run_async_safely(self, coro):
        """Helper method to run async coroutines safely from sync context"""
        import asyncio
        import concurrent.futures
        
        try:
            # Try to get the current event loop
            loop = asyncio.get_running_loop()
            # If we're in an async context, we need to run in a thread with new loop
            def run_in_new_loop():
                new_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(new_loop)
                try:
                    return new_loop.run_until_complete(coro)
                finally:
                    new_loop.close()
            
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(run_in_new_loop)
                return future.result(timeout=30)  # Reduced timeout for faster response
                
        except RuntimeError:
            # No running event loop, we can use asyncio.run directly
            try:
                return asyncio.run(coro)
            except Exception as e:
                logger.error(f"Error in _run_async_safely with asyncio.run: {str(e)}")
                # Return error dict instead of raising exception
                return {
                    "success": False,
                    "error": f"Error executing async operation: {str(e)}",
                    "error_type": type(e).__name__,
                    "data": [],
                    "count": 0
                }
        except Exception as e:
            logger.error(f"Error in _run_async_safely: {str(e)}")
            # Return error dict instead of raising exception
            return {
                "success": False,
                "error": f"Error executing async operation: {str(e)}",
                "error_type": type(e).__name__,
                "data": [],
                "count": 0
            }
    
    # ----------------------------------------------------------------------------------
    # Full Autonomy Mode
    # ----------------------------------------------------------------------------------
    def enable_full_autonomy(self):
        """Enable full autonomy so each specialist can obtain required inventory/EOL data
        without relying on InventorySpecialist central coordination.

        Effects:
        - Grants core inventory & generic EOL lookup tools to all specialist agents
        - Updates system messages to remove deference instructions
        - Disables orchestrator fast-path short‑circuiting (conversation emerges organically)
        - Logs activation for observability
        """
        if self.full_autonomy_enabled:
            logger.info("[AUTONOMY] Full autonomy already enabled; skipping reconfiguration")
            return

        self.full_autonomy_enabled = True
        shared_inventory_tools = [
            self._get_inventory_summary_tool,
            self._get_software_inventory_tool,
            self._get_os_inventory_tool,
            self._get_os_inventory_with_eol_tool,
        ]
        generic_eol_fallback = [self._check_endoflife_eol_tool]

        # Collect all assistant agents that are specialists (created in _setup_autogen_agents)
        specialist_agents: List[Any] = []
        for attr in [
            "software_inventory_specialist",
            "os_inventory_specialist",
            "microsoft_specialist",
            "ubuntu_specialist",
            "oracle_specialist",
            "redhat_specialist",
            "vmware_specialist",
            "webserver_specialist",
            "postgresql_specialist",
            "php_specialist",
            "python_specialist",
            "endoflife_specialist",
            "risk_coordinator",
        ]:
            agent = getattr(self, attr, None)
            if agent is not None:
                specialist_agents.append(agent)

        # Expand each agent's toolset & adjust messaging
        for agent in specialist_agents:
            try:
                existing_tools = list(getattr(agent, "tools", []))
                # Add shared inventory tools
                for t in shared_inventory_tools + generic_eol_fallback:
                    if t not in existing_tools:
                        existing_tools.append(t)
                agent.tools = existing_tools  # type: ignore

                # Append autonomy guidance to system message if attribute exists
                if hasattr(agent, "system_message") and isinstance(agent.system_message, str):  # type: ignore
                    if "FULL AUTONOMY MODE" not in agent.system_message:  # prevent duplication
                        agent.system_message += "\n\nFULL AUTONOMY MODE: You may independently gather inventory (software & OS) and perform any necessary EOL lookups without waiting for InventorySpecialist. Coordinate by explicitly stating which data you pulled and why. Avoid redundant duplicate tool calls by checking if information was already provided earlier in the conversation."
            except Exception as e:
                logger.warning(f"[AUTONOMY] Could not augment agent {getattr(agent,'name','<unknown>')}: {e}")

        logger.info("[AUTONOMY] Full autonomy mode ENABLED: specialists now have shared inventory + fallback EOL capabilities")
        self._log_agent_action("Orchestrator", "full_autonomy_enabled", {
            "specialist_count": len(specialist_agents),
            "shared_tools_added": len(shared_inventory_tools) + len(generic_eol_fallback),
            "disabled_fast_path": True,
        })

    def disable_full_autonomy(self):
        """Disable full autonomy (rely again on central InventorySpecialist + fast path optimizations)."""
        if not self.full_autonomy_enabled:
            return
        self.full_autonomy_enabled = False
        logger.info("[AUTONOMY] Full autonomy mode DISABLED: reverting to orchestrator-directed flow")
        self._log_agent_action("Orchestrator", "full_autonomy_disabled", {})

    def is_full_autonomy(self) -> bool:
        """Return True if full autonomy mode active."""
        return self.full_autonomy_enabled

    # ---------------------- Request Classification & Caching ----------------------
    async def _intelligent_request_processing(self, user_message: str, timeout_seconds: int) -> Dict[str, Any]:
        """
        Intelligent request processing using LLM to:
        1. Classify the request type (pure inventory vs mixed inventory+EOL)
        2. Determine which tools are needed based on classification
        3. Execute tools appropriately for the request type
        4. Synthesize the tool responses into a comprehensive answer
        """
        try:
            start_time = time.time()
            
            # Step 1: Classify the request to determine processing approach
            classification_start = time.time()
            logger.info(f"🧠 REQUEST CLASSIFICATION START | Analyzing request type")
            
            request_type = await self._classify_request(user_message)
            
            classification_duration = time.time() - classification_start
            logger.info(f"🧠 REQUEST CLASSIFICATION COMPLETE | Duration: {classification_duration:.2f}s | Type: {request_type}")
            
            # Step 2: LLM determines which tools to use based on classification
            tool_selection_start = time.time()
            logger.info(f"🔧 TOOL SELECTION START | LLM analyzing request to determine required tools")
            
            tools_to_use = await self._llm_determine_tools(user_message)
            
            tool_selection_duration = time.time() - tool_selection_start
            logger.info(f"🔧 TOOL SELECTION COMPLETE | Duration: {tool_selection_duration:.2f}s | Tools: {tools_to_use}")
            
            if not tools_to_use:
                return {
                    "response": "I couldn't determine how to help with your request. Please be more specific about what inventory or EOL information you need.",
                    "conversation_messages": [],
                    "agent_communications": self.agent_communications[-5:],
                    "session_id": self.session_id,
                    "agents_involved": ["Orchestrator"],
                    "total_exchanges": 1
                }
            
            # Step 3: Execute tools based on request type
            tool_execution_start = time.time()
            logger.info(f"⚙️ EXECUTION START | Processing {len(tools_to_use)} tools for {request_type}")
            
            if request_type == "PURE_INVENTORY":
                # For pure inventory requests, just execute inventory tools without EOL integration
                execution_results = await self._execute_tools_simple(tools_to_use, user_message)
            else:
                # For mixed requests or EOL requests, use coordinated execution
                execution_results = await self._execute_tools_coordinated(tools_to_use, user_message)
            
            tool_execution_duration = time.time() - tool_execution_start
            logger.info(f"⚙️ EXECUTION COMPLETE | Duration: {tool_execution_duration:.2f}s | Results: {len(execution_results)}")
            
            if not execution_results:
                return {
                    "response": "I wasn't able to gather the requested information. This could be due to system connectivity or access issues.",
                    "conversation_messages": [],
                    "agent_communications": self.agent_communications[-10:],
                    "session_id": self.session_id,
                    "agents_involved": ["Orchestrator"],
                    "total_exchanges": 1,
                    "error": "No tool results available"
                }
            
            # Step 4: Handle response synthesis based on result type
            synthesis_start = time.time()
            logger.info(f"🧠 RESPONSE SYNTHESIS START | LLM analyzing tool results to create response")
            
            # Check if we have an integrated response (inventory+EOL combined)
            if "integrated_response" in execution_results:
                synthesized_response = execution_results["integrated_response"]
                logger.info(f"🔄 USING INTEGRATED RESPONSE | Skipping LLM synthesis for mixed inventory+EOL query")
            else:
                # Use LLM synthesis for regular tool results
                synthesized_response = await self._llm_synthesize_response(user_message, execution_results)
            
            synthesis_duration = time.time() - synthesis_start
            total_duration = time.time() - start_time
            logger.info(f"🧠 RESPONSE SYNTHESIS COMPLETE | Duration: {synthesis_duration:.2f}s | Total: {total_duration:.2f}s")
            
            # Create final response
            return self._create_intelligent_response(
                user_message,
                synthesized_response,
                execution_results,
                list(tools_to_use),
                total_duration
            )
            
        except Exception as e:
            logger.error(f"Intelligent processing error: {e}")
            return self._create_error_response(f"Intelligent processing failed: {str(e)}")

    async def _execute_tools_simple(self, tools_to_use: List[str], user_message: str) -> Dict[str, str]:
        """Execute tools simply for pure inventory requests without EOL integration"""
        results = {}
        
        for tool_name in tools_to_use:
            try:
                logger.info(f"🛠️ EXECUTING SIMPLE TOOL | {tool_name}")
                result = await self._execute_tool(tool_name, user_message)
                if result:
                    # Log the result for debugging
                    result_preview = str(result)[:200] + "..." if len(str(result)) > 200 else str(result)
                    logger.info(f"✅ SIMPLE TOOL SUCCESS | {tool_name} | Data length: {len(str(result))} | Preview: {result_preview}")
                    
                    results[tool_name] = result
                else:
                    logger.warning(f"⚠️ SIMPLE TOOL NO DATA | {tool_name} | Result was None or empty")
            except Exception as e:
                logger.error(f"❌ SIMPLE TOOL ERROR | {tool_name} | Error: {str(e)}")
                results[tool_name] = f"Error executing {tool_name}: {str(e)}"
        
        return results

    async def _execute_tools_coordinated(self, tools_to_use: List[str], user_message: str) -> Dict[str, str]:
        """Execute tools in a coordinated fashion where inventory results can inform EOL lookups"""
        results = {}
        inventory_data = {}
        
        # Step 1: Execute inventory tools first
        inventory_tools = [tool for tool in tools_to_use if "inventory" in tool]
        for tool_name in inventory_tools:
            try:
                logger.info(f"🛠️ EXECUTING INVENTORY TOOL | {tool_name}")
                result = await self._execute_tool(tool_name, user_message)
                if result:
                    # Log more details about the result for debugging
                    result_preview = str(result)[:200] + "..." if len(str(result)) > 200 else str(result)
                    logger.info(f"✅ INVENTORY SUCCESS | {tool_name} | Data length: {len(str(result))} | Preview: {result_preview}")
                    
                    results[tool_name] = result
                    inventory_data[tool_name] = result
                else:
                    logger.warning(f"⚠️ INVENTORY NO DATA | {tool_name} | Result was None or empty")
            except Exception as e:
                logger.error(f"❌ INVENTORY ERROR | {tool_name} | Error: {str(e)}")
                results[tool_name] = f"Error executing {tool_name}: {str(e)}"
        
        # Step 2: Extract products from inventory data for targeted EOL analysis
        discovered_products = []
        for inv_tool, inv_data in inventory_data.items():
            # Only process data for product extraction if it's valid inventory data (not error messages)
            if (inv_data and 
                not inv_data.startswith("❌") and 
                "agent not available" not in inv_data and
                not inv_data.startswith("Error getting") and
                "No inventory summary available" not in inv_data):
                
                products = self._extract_products_from_inventory_data(inv_data)
                discovered_products.extend(products)
                logger.info(f"🔍 PRODUCT EXTRACTION | {inv_tool} | Found: {len(products)} products")
            else:
                logger.warning(f"🔍 PRODUCT EXTRACTION SKIPPED | {inv_tool} | Reason: Error response detected")
        
        # Step 3: For mixed queries, integrate EOL data into inventory instead of separate sections
        if inventory_data and any("inventory" in tool.lower() for tool in tools_to_use):
            logger.info(f"🔄 MIXED QUERY DETECTED | Integrating EOL data into inventory display")
            
            # Create integrated inventory+EOL response
            integrated_response = await self._create_integrated_inventory_eol_response(
                inventory_data, discovered_products, user_message
            )
            
            if integrated_response and not integrated_response.startswith("No inventory data available"):
                return {"integrated_response": integrated_response}
            else:
                # If integration failed, provide fallback with raw inventory data
                logger.warning(f"🔄 INTEGRATION FAILED | Falling back to raw inventory data")
                fallback_response = "## Inventory Data (Raw)\n\n"
                for tool_name, tool_data in inventory_data.items():
                    if tool_data:
                        fallback_response += f"### {tool_name.replace('_', ' ').title()}\n{tool_data}\n\n"
                
                if fallback_response.strip() != "## Inventory Data (Raw)":
                    return {"integrated_response": fallback_response}
        
        # Step 3 (original): Execute EOL tools based on both user request and discovered products
        eol_tools = [tool for tool in tools_to_use if "eol" in tool]
        
        for tool_name in eol_tools:
            try:
                logger.info(f"🛠️ EXECUTING EOL TOOL | {tool_name}")
                # Use discovered products to inform EOL lookup
                result = await self._execute_eol_tool_with_products(tool_name, user_message, discovered_products)
                if result:
                    results[tool_name] = result
                    logger.info(f"✅ EOL SUCCESS | {tool_name} | Data length: {len(str(result))}")
                else:
                    logger.warning(f"⚠️ EOL NO DATA | {tool_name}")
            except Exception as e:
                logger.error(f"❌ EOL ERROR | {tool_name} | Error: {str(e)}")
                results[tool_name] = f"Error executing {tool_name}: {str(e)}"
        
        return results

    async def _create_integrated_inventory_eol_response(self, inventory_data: Dict[str, str], 
                                                      discovered_products: List[Dict], 
                                                      user_message: str) -> str:
        """Create an integrated response that shows inventory with EOL data for each item"""
        try:
            integrated_sections = []
            
            for inv_tool, inv_data in inventory_data.items():
                # Check if this is an error message that should be shown to user
                if (not inv_data or inv_data.strip() == ""):
                    logger.warning(f"🔄 SKIPPING EMPTY DATA | Tool: {inv_tool}")
                    continue
                
                # If it's a helpful error message (like configuration issues), show it to user
                if (inv_data.startswith("❌ **Software Inventory Configuration Issue**") or
                    inv_data.startswith("❌ **OS Inventory Configuration Issue**")):
                    logger.info(f"🔄 PASSING THROUGH CONFIG ERROR | Tool: {inv_tool}")
                    section_title = inv_tool.replace('_', ' ').title()
                    integrated_sections.append(f"## {section_title}\n\n{inv_data}")
                    continue
                    
                # Check for other error patterns that should be skipped from processing
                if (inv_data.startswith("❌") or 
                    inv_data.startswith("Error getting") or 
                    "agent not available" in inv_data or
                    "No inventory summary available" in inv_data or
                    inv_data.strip() == "No data available"):
                    logger.warning(f"🔄 SKIPPING ERROR DATA | Tool: {inv_tool} | Error: {inv_data[:100]}...")
                    continue
                
                logger.info(f"🔄 INTEGRATING EOL DATA | Processing {inv_tool}")
                
                # Parse inventory data and add EOL information to each item
                enhanced_inventory = await self._enhance_inventory_with_eol(inv_data, discovered_products)
                
                section_title = inv_tool.replace('_', ' ').title()
                integrated_sections.append(f"## {section_title}\n\n{enhanced_inventory}")
            
            if integrated_sections:
                logger.info(f"✅ INTEGRATED RESPONSE SUCCESS | Sections: {len(integrated_sections)}")
                return "\n\n".join(integrated_sections)
            else:
                # Better debugging when no sections are available
                logger.warning(f"❌ NO INTEGRATED SECTIONS | Available tools: {list(inventory_data.keys())}")
                for tool, data in inventory_data.items():
                    logger.warning(f"❌ TOOL DATA DEBUG | {tool}: {data[:200] if data else 'None'}...")
                
                return "No inventory data available for EOL analysis. This may be due to missing Azure credentials, Log Analytics configuration, or network connectivity issues."
                
        except Exception as e:
            logger.error(f"❌ INTEGRATED RESPONSE ERROR | {str(e)}")
            return f"Error creating integrated response: {str(e)}"

    async def _enhance_inventory_with_eol(self, inventory_data: str, discovered_products: List[Dict]) -> str:
        """Enhance inventory data by adding EOL information to each relevant item"""
        try:
            lines = inventory_data.split('\n')
            enhanced_lines = []
            
            # Sort products to prioritize those with versions and longer names (more specific first)
            sorted_products = sorted(discovered_products, key=lambda p: (
                0 if p.get("version") and p.get("version") != "Unknown" else 1,  # Products with versions first
                -len(p.get("name", "")),  # Longer names first (more specific)
                p.get("name", "")  # Alphabetical as tiebreaker
            ))
            
            for line in lines:
                enhanced_line = line
                
                # Check if this line contains a product we have discovered
                for product in sorted_products:
                    
                    product_name = product.get("name", "").lower()
                    product_version = product.get("version", "")
                    
                    # More precise matching: check both product name AND version are in the line
                    line_lower = line.lower().replace(" ", "")
                    product_name_clean = product_name.replace(" ", "")
                    
                    # For products with versions, ensure both name and version match
                    if product_version and product_version != "Unknown":
                        name_match = product_name_clean in line_lower
                        version_match = product_version in line
                        
                        if name_match and version_match:
                            logger.info(f"🔍 ENHANCING LINE | Found {product_name} {product_version} in inventory")
                            
                            # Get EOL data for this specific product
                            eol_data = await self._get_eol_data_for_product(product)
                            
                            if eol_data and "No EOL data found" not in eol_data:
                                # Add EOL data to the line
                                enhanced_line = f"{line}\n    📅 **EOL Information**: {eol_data.strip()}"
                                logger.info(f"✅ EOL DATA ADDED | {product_name} {product_version}")
                            else:
                                enhanced_line = f"{line}\n    ⚠️ **EOL Status**: No EOL data available"
                            break
                    else:
                        # For products without version info, use original logic
                        if product_name_clean in line_lower:
                            logger.info(f"🔍 ENHANCING LINE | Found {product_name} (no version) in inventory")
                            
                            # Get EOL data for this specific product
                            eol_data = await self._get_eol_data_for_product(product)
                            
                            if eol_data and "No EOL data found" not in eol_data:
                                # Add EOL data to the line
                                enhanced_line = f"{line}\n    📅 **EOL Information**: {eol_data.strip()}"
                                logger.info(f"✅ EOL DATA ADDED | {product_name}")
                            else:
                                enhanced_line = f"{line}\n    ⚠️ **EOL Status**: No EOL data available"
                            break
                
                enhanced_lines.append(enhanced_line)
            
            return '\n'.join(enhanced_lines)
            
        except Exception as e:
            logger.error(f"❌ INVENTORY ENHANCEMENT ERROR | {str(e)}")
            return inventory_data  # Return original data if enhancement fails

    async def _get_eol_data_for_product(self, product: Dict[str, str]) -> str:
        """Get EOL data for a specific product"""
        try:
            product_name = product.get("name", "")
            product_version = product.get("version", "")
            product_type = product.get("type", "")
            
            # Determine which EOL specialist to use
            if any(term in product_name.lower() for term in ["windows", "microsoft"]):
                return self._check_microsoft_eol_tool(product_name, product_version)
            elif "ubuntu" in product_name.lower():
                return self._check_ubuntu_eol_tool(product_name, product_version)
            elif any(term in product_name.lower() for term in ["rhel", "red hat"]):
                return self._check_redhat_eol_tool(product_name, product_version)
            elif "python" in product_name.lower():
                return self._check_python_eol_tool(product_name, product_version)
            else:
                # Use generic EOL tool as fallback
                if hasattr(self, 'endoflife_agent'):
                    query = f"EOL information for {product_name} {product_version}"
                    return self.endoflife_agent._get_eol_data(query)
                else:
                    return "EOL agent not available"
                    
        except Exception as e:
            logger.error(f"❌ PRODUCT EOL LOOKUP ERROR | {product_name}: {str(e)}")
            return f"Error getting EOL data: {str(e)}"

    def _extract_products_from_inventory_data(self, inventory_data: str) -> List[Dict[str, str]]:
        """Extract product names and versions from inventory data string"""
        products = []
        
        if not inventory_data:
            return products
        
        lines = inventory_data.split('\n')
        for line in lines:
            line = line.strip()
            if not line or line.startswith('#') or line.startswith('//'):
                continue
                
            # Try to extract OS information
            if any(os_term in line.lower() for os_term in ["windows", "ubuntu", "rhel", "centos", "debian", "suse"]):
                # Extract OS name and version
                if "windows" in line.lower():
                    if "server" in line.lower():
                        if "2025" in line: products.append({"name": "Windows Server", "version": "2025", "type": "OS"})
                        elif "2022" in line: products.append({"name": "Windows Server", "version": "2022", "type": "OS"})
                        elif "2019" in line: products.append({"name": "Windows Server", "version": "2019", "type": "OS"})
                        elif "2016" in line: products.append({"name": "Windows Server", "version": "2016", "type": "OS"})
                        else: products.append({"name": "Windows Server", "version": "Unknown", "type": "OS"})
                    else:
                        if "11" in line: products.append({"name": "Windows", "version": "11", "type": "OS"})
                        elif "10" in line: products.append({"name": "Windows", "version": "10", "type": "OS"})
                        else: products.append({"name": "Windows", "version": "Unknown", "type": "OS"})
                elif "ubuntu" in line.lower():
                    import re
                    version_match = re.search(r'(\d+\.\d+)', line)
                    version = version_match.group(1) if version_match else "Unknown"
                    products.append({"name": "Ubuntu", "version": version, "type": "OS"})
                elif "rhel" in line.lower() or "red hat" in line.lower():
                    import re
                    version_match = re.search(r'(\d+)', line)
                    version = version_match.group(1) if version_match else "Unknown"
                    products.append({"name": "Red Hat Enterprise Linux", "version": version, "type": "OS"})
                    
            # Try to extract software information
            elif any(software_term in line.lower() for software_term in ["python", "java", "node", "php", "apache", "nginx", "mysql", "postgresql"]):
                import re
                for software in ["python", "java", "node", "php", "apache", "nginx", "mysql", "postgresql"]:
                    if software in line.lower():
                        version_match = re.search(rf'{software}[^\d]*(\d+(?:\.\d+)*)', line, re.IGNORECASE)
                        version = version_match.group(1) if version_match else "Unknown"
                        products.append({"name": software.title(), "version": version, "type": "Software"})
                        break
        
        # Remove duplicates
        unique_products = []
        seen = set()
        for product in products:
            key = f"{product['name']}-{product['version']}"
            if key not in seen:
                seen.add(key)
                unique_products.append(product)
        
        return unique_products

    async def _execute_eol_tool_with_products(self, tool_name: str, user_message: str, discovered_products: List[Dict]) -> str:
        """Execute EOL tool with intelligent product routing based on discovered inventory"""
        try:
            # Smart product-to-specialist mapping
            relevant_products = self._find_products_for_eol_tool(tool_name, discovered_products)
            
            if relevant_products:
                results = []
                logger.info(f"🎯 EOL SPECIALIST | {tool_name} handling {len(relevant_products)} products")
                
                for product in relevant_products[:5]:  # Process up to 5 products per specialist
                    logger.info(f"🔍 EOL LOOKUP | {product['name']} {product['version']} → {tool_name}")
                    
                    # Execute targeted EOL lookup for this specific product
                    result = await self._execute_targeted_eol_lookup(tool_name, product)
                    
                    if result and "No EOL data found" not in result and "Error" not in result:
                        results.append(f"**{product['name']} {product['version']}**:\n{result}")
                        logger.info(f"✅ EOL DATA FOUND | {product['name']} {product['version']}")
                    else:
                        logger.warning(f"⚠️ EOL NO DATA | {product['name']} {product['version']}")
                
                if results:
                    return "\n\n".join(results)
                else:
                    return f"No EOL data found for products relevant to {tool_name}"
            else:
                # No relevant products found, but tool was selected - run generic query
                logger.info(f"🔄 FALLBACK MODE | {tool_name} no specific products, running generic query")
                return await self._execute_tool(tool_name, user_message)
                
        except Exception as e:
            logger.error(f"EOL tool execution error for {tool_name}: {e}")
            return f"Error executing {tool_name}: {str(e)}"

    def _find_products_for_eol_tool(self, tool_name: str, discovered_products: List[Dict]) -> List[Dict]:
        """Intelligently map discovered products to appropriate EOL specialists"""
        relevant_products = []
        
        for product in discovered_products:
            product_name = product["name"].lower()
            product_type = product.get("type", "").lower()
            
            # Microsoft EOL Specialist
            if tool_name == "microsoft_eol":
                if any(term in product_name for term in [
                    "windows", "office", "sql server", "exchange", "sharepoint", 
                    ".net", "visual studio", "azure", "iis", "hyper-v"
                ]):
                    relevant_products.append(product)
            
            # Ubuntu EOL Specialist  
            elif tool_name == "ubuntu_eol":
                if "ubuntu" in product_name:
                    relevant_products.append(product)
            
            # Red Hat EOL Specialist
            elif tool_name == "redhat_eol":
                if any(term in product_name for term in [
                    "red hat", "rhel", "centos", "fedora", "red hat enterprise"
                ]):
                    relevant_products.append(product)
            
            # Oracle EOL Specialist
            elif tool_name == "oracle_eol":
                if any(term in product_name for term in [
                    "oracle", "java", "mysql", "virtualbox"
                ]):
                    relevant_products.append(product)
            
            # Python EOL Specialist
            elif tool_name == "python_eol":
                if "python" in product_name:
                    relevant_products.append(product)
            
            # Node.js EOL Specialist
            elif tool_name == "nodejs_eol":
                if any(term in product_name for term in ["node", "nodejs", "npm"]):
                    relevant_products.append(product)
            
            # PHP EOL Specialist
            elif tool_name == "php_eol":
                if "php" in product_name:
                    relevant_products.append(product)
            
            # PostgreSQL EOL Specialist
            elif tool_name == "postgresql_eol":
                if "postgresql" in product_name or "postgres" in product_name:
                    relevant_products.append(product)
            
            # Apache EOL Specialist
            elif tool_name == "apache_eol":
                if any(term in product_name for term in ["apache", "httpd", "tomcat"]):
                    relevant_products.append(product)
            
            # VMware EOL Specialist
            elif tool_name == "vmware_eol":
                if any(term in product_name for term in ["vmware", "esxi", "vcenter", "workstation"]):
                    relevant_products.append(product)
            
            # EndOfLife.date (Generic) Specialist
            elif tool_name == "endoflife_eol":
                # Handle products not covered by specific specialists
                covered_by_others = any(specialist in product_name for specialist in [
                    "windows", "ubuntu", "red hat", "rhel", "oracle", "java", 
                    "python", "node", "php", "postgresql", "apache", "vmware"
                ])
                if not covered_by_others:
                    relevant_products.append(product)
        
        return relevant_products

    async def _execute_targeted_eol_lookup(self, tool_name: str, product: Dict[str, str]) -> str:
        """Execute targeted EOL lookup for a specific product using appropriate specialist"""
        try:
            product_name = product["name"]
            version = product["version"]
            
            if tool_name == "microsoft_eol":
                return self._check_microsoft_eol_tool(product_name, version)
            elif tool_name == "ubuntu_eol":
                return self._check_ubuntu_eol_tool(product_name, version)
            elif tool_name == "redhat_eol":
                return self._check_redhat_eol_tool(product_name, version)
            elif tool_name == "oracle_eol":
                return self._check_oracle_eol_tool(product_name, version)
            elif tool_name == "python_eol":
                return self._check_python_eol_tool(product_name, version)
            elif tool_name == "nodejs_eol":
                return self._check_nodejs_eol_tool(product_name, version)
            elif tool_name == "php_eol":
                return self._check_php_eol_tool(product_name, version)
            elif tool_name == "postgresql_eol":
                return self._check_postgresql_eol_tool(product_name, version)
            elif tool_name == "apache_eol":
                return self._check_apache_eol_tool(product_name, version)
            elif tool_name == "vmware_eol":
                return self._check_vmware_eol_tool(product_name, version)
            else:  # endoflife_eol or unknown
                return self._check_endoflife_eol_tool(product_name, version)
                
        except Exception as e:
            logger.error(f"Targeted EOL lookup error for {product_name}: {e}")
            return f"Error checking EOL for {product_name}: {str(e)}"

    async def _llm_determine_tools(self, user_message: str) -> List[str]:
        """Use LLM to determine which tools are needed for the request"""
        tools_prompt = f"""
You are an intelligent workflow orchestrator for a software inventory and EOL (End-of-Life) analysis system.

Your job is to understand user requests and plan the COMPLETE WORKFLOW needed to satisfy them.

UNDERSTANDING THE SYSTEM WORKFLOW:

**For inventory-only requests:**
- User wants to see what they have installed
- Use inventory tools: os_inventory, software_inventory

**For EOL-only requests:**  
- User knows specific products and wants EOL dates
- Use specific EOL tools: microsoft_eol, ubuntu_eol, etc.

**For MIXED requests (inventory + EOL analysis):**
- User wants to see their inventory AND get EOL dates for everything found
- WORKFLOW: 
  1. First run inventory tools to discover what's installed
  2. System will automatically extract specific products from inventory results
  3. System will automatically route each product to appropriate EOL specialists
  4. System will correlate everything into unified response

AVAILABLE TOOLS:

**INVENTORY TOOLS** (discover what's installed):
- **os_inventory**: Discovers operating systems (Windows Server 2019, Ubuntu 20.04, RHEL 8, etc.)
- **software_inventory**: Discovers installed software/applications (Python, Apache, MySQL, etc.)

**EOL SPECIALIST TOOLS** (get EOL dates for specific products):
- **microsoft_eol**: Windows, Windows Server, Office, SQL Server, .NET, Visual Studio
- **ubuntu_eol**: Ubuntu Linux versions and flavors  
- **redhat_eol**: RHEL, CentOS, Fedora, Red Hat enterprise products
- **oracle_eol**: Oracle Database, Oracle products, Java (Oracle-owned)
- **python_eol**: Python language versions and packages
- **nodejs_eol**: Node.js runtime and npm packages
- **php_eol**: PHP language and framework versions
- **postgresql_eol**: PostgreSQL database versions
- **apache_eol**: Apache HTTP Server, Tomcat, other Apache projects
- **vmware_eol**: VMware ESXi, vCenter, Workstation products
- **endoflife_eol**: Generic products not covered by specific specialists

USER REQUEST: "{user_message}"

ANALYSIS EXAMPLES:

**"What software do I have?"**
→ Pure inventory request
→ Tools: ["software_inventory"]

**"Show my OS inventory"** 
→ Pure inventory request
→ Tools: ["os_inventory"]

**"When does Windows Server 2019 expire?"**
→ Direct EOL lookup (user knows specific product)
→ Tools: ["microsoft_eol"]

**"What is the EOL date of Windows Server 2025?"**
→ Direct EOL lookup (user knows specific product)
→ Tools: ["microsoft_eol"]

**"When does Ubuntu 20.04 reach end of life?"**
→ Direct EOL lookup (user knows specific product)  
→ Tools: ["ubuntu_eol"]

**"Show my OS inventory with EOL date for each OS"**
→ MIXED REQUEST: Need inventory + EOL analysis
→ Workflow: Get OS inventory, then system will extract each OS and check EOL dates
→ Tools: ["os_inventory", "microsoft_eol", "ubuntu_eol", "redhat_eol", "endoflife_eol"]

**"List all software and check EOL dates"**
→ MIXED REQUEST: Need software inventory + EOL analysis  
→ Workflow: Get software inventory, then system will extract each software and check EOL dates
→ Tools: ["software_inventory", "python_eol", "nodejs_eol", "php_eol", "apache_eol", "endoflife_eol"]

**"Perform EOL risk assessment"**
→ MIXED REQUEST: Need complete inventory + comprehensive EOL analysis
→ Tools: ["os_inventory", "software_inventory", "microsoft_eol", "ubuntu_eol", "redhat_eol", "python_eol", "nodejs_eol", "php_eol", "postgresql_eol", "apache_eol", "endoflife_eol"]

CRITICAL TOOL SELECTION RULES:

1. **EOL-ONLY queries**: User asks about specific product EOL dates
   - Keywords: "EOL", "expire", "end of life", "support end" + specific product name
   - Tools: ONLY the relevant EOL specialist (NO inventory tools)
   - Examples: "When does X expire?", "What is EOL date of Y?"

2. **INVENTORY-ONLY queries**: User asks what they have installed
   - Keywords: "inventory", "what do I have", "show my", "list" + NO EOL terms
   - Tools: ONLY inventory tools (NO EOL tools)

3. **MIXED queries**: User wants inventory AND EOL analysis together
   - Keywords: "inventory" + "EOL" or "risk assessment" or "with EOL dates"
   - Tools: Inventory + ALL relevant EOL specialists

Based on the user request above, determine the appropriate tools.

Respond with JSON array of tool names ONLY (no explanations):
["tool1", "tool2", "tool3"]
"""

        try:
            # Check if model client is available
            if not self.model_client:
                raise Exception("Model client not initialized")
                
            response = await self.model_client.create([{
                "role": "user", 
                "content": tools_prompt
            }])
            
            import json
            response_content = response.content.strip()
            logger.debug(f"🧠 LLM RAW RESPONSE | Content: '{response_content}'")
            
            try:
                selected_tools = json.loads(response_content)
            except json.JSONDecodeError as json_err:
                logger.warning(f"🧠 LLM JSON PARSE ERROR | Content: '{response_content}' | Error: {json_err}")
                raise Exception(f"Invalid JSON response: {response_content}")
            
            # Validate tools
            available_tools = [
                "os_inventory", "software_inventory", "microsoft_eol", "ubuntu_eol", 
                "redhat_eol", "oracle_eol", "python_eol", "nodejs_eol", "php_eol",
                "postgresql_eol", "apache_eol", "vmware_eol", "endoflife_eol"
            ]
            
            validated_tools = [tool for tool in selected_tools if tool in available_tools]
            
            logger.info(f"🧠 LLM TOOL SELECTION | Query: '{user_message}' | LLM Raw: {response_content} | Validated: {validated_tools}")
            return validated_tools
            
        except Exception as e:
            logger.warning(f"LLM tool selection failed: {e} (Type: {type(e).__name__}), using fallback")
            # Enhanced fallback logic
            message_lower = user_message.lower()
            fallback_tools = []
            
            # Check for MIXED queries first (inventory + EOL together)
            has_eol_terms = any(term in message_lower for term in ["eol", "end of life", "expire", "expiration", "support end"])
            has_inventory_terms = any(term in message_lower for term in ["inventory", "show", "list", "what do i have"])
            
            if has_eol_terms and has_inventory_terms:
                # MIXED REQUEST: Need both inventory and EOL analysis
                logger.info(f"🔄 FALLBACK SELECTION | MIXED Query detected: '{user_message}'")
                
                # Add inventory tools based on context
                if any(term in message_lower for term in ["software", "application", "program", "package", "app"]):
                    fallback_tools.append("software_inventory")
                elif any(term in message_lower for term in ["os", "operating system"]):
                    fallback_tools.append("os_inventory")
                else:
                    # Default to both for comprehensive EOL risk assessment
                    fallback_tools.extend(["os_inventory", "software_inventory"])
                
                # Add ALL relevant EOL specialists for comprehensive analysis
                fallback_tools.extend([
                    "microsoft_eol", "ubuntu_eol", "redhat_eol", "oracle_eol", 
                    "python_eol", "nodejs_eol", "php_eol", "postgresql_eol", 
                    "apache_eol", "vmware_eol", "endoflife_eol"
                ])
                
                logger.info(f"🔄 FALLBACK SELECTION | MIXED Query: '{user_message}' → Tools: {fallback_tools}")
                return fallback_tools
            
            # EOL-only queries (no inventory terms)
            elif has_eol_terms and not has_inventory_terms:
                # This is a pure EOL query - determine which specialist
                if any(term in message_lower for term in ["windows", "microsoft", "office", "sql server", "azure"]):
                    fallback_tools.append("microsoft_eol")
                elif "ubuntu" in message_lower:
                    fallback_tools.append("ubuntu_eol")
                elif any(term in message_lower for term in ["rhel", "redhat", "red hat", "centos"]):
                    fallback_tools.append("redhat_eol")
                elif any(term in message_lower for term in ["python", "pip"]):
                    fallback_tools.append("python_eol")
                elif any(term in message_lower for term in ["node", "nodejs", "npm"]):
                    fallback_tools.append("nodejs_eol")
                elif any(term in message_lower for term in ["php"]):
                    fallback_tools.append("php_eol")
                elif any(term in message_lower for term in ["postgresql", "postgres"]):
                    fallback_tools.append("postgresql_eol")
                elif any(term in message_lower for term in ["apache", "httpd"]):
                    fallback_tools.append("apache_eol")
                elif any(term in message_lower for term in ["vmware", "esxi", "vcenter"]):
                    fallback_tools.append("vmware_eol")
                else:
                    fallback_tools.append("endoflife_eol")
                    
                logger.info(f"🔄 FALLBACK SELECTION | EOL-only Query: '{user_message}' → Tools: {fallback_tools}")
                return fallback_tools
            
            # Inventory-only queries (if no EOL terms detected)
            if any(term in message_lower for term in ["software", "application", "program", "package", "app"]):
                fallback_tools.append("software_inventory")
            elif any(term in message_lower for term in ["os", "operating system", "windows", "linux", "ubuntu"]):
                fallback_tools.append("os_inventory")
            elif any(term in message_lower for term in ["inventory", "show", "list", "what do i have"]):
                # For general inventory, include both but prioritize based on context
                if "software" in message_lower or "application" in message_lower:
                    fallback_tools.append("software_inventory")
                elif "os" in message_lower or "operating" in message_lower:
                    fallback_tools.append("os_inventory") 
                else:
                    # Default to software inventory for general "what do I have" questions
                    fallback_tools.extend(["software_inventory", "os_inventory"])
            
            # Default if nothing detected
            if not fallback_tools:
                fallback_tools = ["software_inventory"]
            
            logger.info(f"🔄 FALLBACK SELECTION | Query: '{user_message}' → Tools: {fallback_tools}")
            return fallback_tools

    async def _execute_tool(self, tool_name: str, user_message: str) -> str:
        """Execute a specific tool and return its result"""
        try:
            if tool_name == "os_inventory":
                return self._get_os_inventory_tool(365)  # Use 365 days instead of "all"
            elif tool_name == "software_inventory":
                return self._get_software_inventory_tool(365)  # Use 365 days instead of "all"
            elif tool_name == "microsoft_eol":
                # Temporarily skip LLM extraction to avoid message format issues
                # Use pattern matching directly
                logger.info(f"🔄 Using pattern matching for Microsoft EOL (bypassing LLM)")
                products = self._fallback_pattern_extraction(user_message)
                ms_products = [p for p in products if p.get("specialist") == "microsoft"]
                
                if ms_products:
                    results = []
                    processed_products = set()  # Track processed products to avoid duplicates
                    
                    for product in ms_products[:3]:
                        product_name = product.get("name", "").lower()
                        product_version = product.get("version", "")
                        product_key = f"{product_name}_{product_version}"
                        
                        # Skip if we've already processed this product
                        if product_key in processed_products:
                            continue
                        processed_products.add(product_key)
                        
                        result = self._check_microsoft_eol_tool(product.get("name", ""), product_version)
                        logger.info(f"🔍 MS PRODUCT RESULT | {product.get('name', '')} {product_version} | Result length: {len(result) if result else 0}")
                        
                        if result and "No EOL data found" not in result and "Error" not in result:
                            results.append(result)
                            logger.info(f"✅ ADDED TO RESULTS | {product.get('name', '')} | Total results: {len(results)}")
                        else:
                            logger.warning(f"⚠️ FILTERED OUT | {product.get('name', '')} | Reason: {result[:100] if result else 'No result'}")
                    
                    logger.info(f"📊 MS PRODUCTS PROCESSING COMPLETE | Found {len(ms_products)} products, Valid results: {len(results)}")
                    
                    if results:
                        logger.info(f"✅ RETURNING RESULTS | Count: {len(results)}")
                        return "\n\n".join(results)
                    else:
                        # If we found MS products but no valid EOL data, try generic fallback
                        logger.info(f"🔄 Microsoft products found but no valid EOL data, trying generic Windows lookup")
                        return self._check_microsoft_eol_tool("Windows", "")
                else:
                    # No Microsoft products detected, use generic fallback
                    logger.info(f"🔄 No Microsoft products detected, using generic Windows lookup")
                    return self._check_microsoft_eol_tool("Windows", "")
            elif tool_name == "ubuntu_eol":
                return self._check_ubuntu_eol_tool("Ubuntu", "")
            elif tool_name == "redhat_eol":
                return self._check_redhat_eol_tool("RHEL", "")
            elif tool_name == "oracle_eol":
                return self._check_oracle_eol_tool("Oracle", "")
            elif tool_name == "python_eol":
                return self._check_python_eol_tool("Python", "")
            elif tool_name == "nodejs_eol":
                return self._check_nodejs_eol_tool("Node.js", "")
            elif tool_name == "php_eol":
                return self._check_php_eol_tool("PHP", "")
            elif tool_name == "postgresql_eol":
                return self._check_postgresql_eol_tool("PostgreSQL", "")
            elif tool_name == "apache_eol":
                return self._check_apache_eol_tool("Apache", "")
            elif tool_name == "vmware_eol":
                return self._check_vmware_eol_tool("VMware", "")
            elif tool_name == "endoflife_eol":
                # Try to extract any product from the message
                products = await self._extract_software_names_from_query(user_message)
                if products:
                    product = products[0]
                    return self._check_endoflife_eol_tool(product.get("name", ""), product.get("version", ""))
                else:
                    return self._check_endoflife_eol_tool("General", "")
            else:
                return f"Unknown tool: {tool_name}"
                
        except Exception as e:
            logger.error(f"Tool execution error for {tool_name}: {e}")
            return f"Error executing {tool_name}: {str(e)}"

    async def _llm_synthesize_response(self, user_message: str, tool_results: Dict[str, str]) -> str:
        """Use LLM to synthesize tool results into a comprehensive response"""
        
        # Prepare tool results summary
        tools_summary = []
        for tool_name, result in tool_results.items():
            # Truncate long results for the prompt
            truncated_result = result[:1000] + "..." if len(result) > 1000 else result
            tools_summary.append(f"**{tool_name}**:\n{truncated_result}")
        
        synthesis_prompt = f"""
You are an expert system analyst providing comprehensive responses about software inventory and EOL information.

USER REQUEST: "{user_message}"

TOOL RESULTS:
{chr(10).join(tools_summary)}

Create a professional, comprehensive response that:

1. **Directly answers the user's question**
2. **Organizes information logically** (inventory first, then EOL analysis)
3. **Highlights important findings** (especially EOL dates and risks)
4. **Uses clear formatting** with headers, bullet points, and emphasis
5. **Provides actionable insights** when possible

Guidelines:
- Be specific and detailed, not generic
- If inventory is shown, format it clearly
- If EOL information is provided, highlight critical dates
- If both inventory and EOL are requested, combine them intelligently
- Use professional markdown formatting
- Focus on the data, not pleasantries

Response:
"""

        try:
            response = await self.model_client.create([{
                "role": "user", 
                "content": synthesis_prompt
            }])
            
            synthesized = response.content.strip()
            logger.info(f"🧠 SYNTHESIS SUCCESS | Response length: {len(synthesized)}")
            return synthesized
            
        except Exception as e:
            logger.error(f"LLM synthesis error: {e}")
            # Fallback to basic concatenation
            fallback_response = f"## Results for: {user_message}\n\n"
            for tool_name, result in tool_results.items():
                fallback_response += f"### {tool_name.replace('_', ' ').title()}\n{result}\n\n"
            return fallback_response

    def _create_intelligent_response(
        self, 
        user_message: str, 
        synthesized_response: str,
        tool_results: Dict[str, str],
        tools_used: List[str],
        processing_time: float
    ) -> Dict[str, Any]:
        """Create the final intelligent response"""
        
        conversation_messages = [
            {
                "speaker": "user",
                "content": user_message,
                "timestamp": datetime.utcnow().isoformat(),
                "message_type": "UserMessage"
            },
            {
                "speaker": "IntelligentOrchestrator", 
                "content": synthesized_response,
                "timestamp": datetime.utcnow().isoformat(),
                "message_type": "AssistantMessage"
            }
        ]
        
        return {
            "response": synthesized_response,
            "conversation_messages": conversation_messages,
            "agent_communications": self.agent_communications[-20:],
            "session_id": self.session_id,
            "agents_involved": ["IntelligentOrchestrator"] + [f"{tool}_tool" for tool in tools_used],
            "total_exchanges": len(conversation_messages),
            "tools_used": tools_used,
            "processing_time": processing_time,
            "approach": "intelligent_llm_orchestration"
        }

    async def _classify_request(self, message: str) -> str:
        """Use LLM to intelligently classify request and determine routing strategy."""
        # Basic validation
        message_clean = message.strip()
        
        if not message_clean or len(message_clean) < 2:
            return "INVALID_REQUEST"
        
        # Use LLM for intelligent classification
        return await self._llm_classify_request(message_clean)

    async def _llm_classify_request(self, message: str) -> str:
        """Use LLM to intelligently classify the user request"""
        classification_prompt = f"""
You are an intelligent request classifier for a software inventory and EOL (End of Life) analysis system. 

Analyze this user request and classify it into exactly ONE of these categories:

**PURE_INVENTORY**: User only wants to see their software/system inventory without any EOL analysis
- Examples: "show my inventory", "list all software", "what operating systems do I have", "what OS versions do I have", "what software do I have", "show my OS inventory"

**SIMPLE_EOL**: User wants specific EOL information for known software/products (direct lookup, no analysis needed)  
- Examples: "what is the EOL date for Windows Server 2025?", "when does Python 3.8 expire?", "support end date for Office 2019"

**EOL_ANALYSIS**: User wants comprehensive EOL risk analysis, assessment, or recommendations
- Examples: "perform EOL risk assessment", "analyze EOL vulnerabilities", "what are my EOL risks", "EOL analysis report"

**MIXED_REQUEST**: User wants both inventory information AND EOL analysis together
- Examples: "show inventory with EOL analysis", "OS inventory with EOL dates", "software inventory and EOL risks"

**INVALID_REQUEST**: Request is unclear, empty, or unrelated to inventory/EOL

USER REQUEST: "{message}"

Respond with ONLY the classification category (e.g., "SIMPLE_EOL"). No explanations.
"""

        try:
            # Use the model client to get classification
            response = await self.model_client.create([{
                "role": "user", 
                "content": classification_prompt
            }])
            
            classification = response.content.strip().upper()
            
            # Validate classification - if empty or invalid, use fallback
            valid_classifications = ["PURE_INVENTORY", "SIMPLE_EOL", "EOL_ANALYSIS", "MIXED_REQUEST", "INVALID_REQUEST"]
            if classification in valid_classifications and classification:
                logger.info(f"🧠 LLM CLASSIFICATION | Request: '{message[:50]}...' → {classification}")
                return classification
            else:
                logger.warning(f"Invalid LLM classification '{classification}', falling back to keyword-based classification")
                return self._fallback_keyword_classification(message)
                
        except Exception as e:
            logger.error(f"LLM classification error: {e}, falling back to keyword-based classification")
            return self._fallback_keyword_classification(message)

    def _fallback_keyword_classification(self, message: str) -> str:
        """Fallback keyword-based classification if LLM fails"""
        message_clean = message.strip().lower()
        
        # Check for pure inventory patterns first (more specific) - BUT ONLY if no EOL terms
        pure_inventory_keywords = ["what software do i have", "show my inventory", "list all software", 
                                 "software inventory", "what operating systems", "os inventory",
                                 "what os versions", "what os do i have", "show my os", "list os",
                                 "what do i have", "list my", "show me my", "os versions",
                                 "operating system versions", "show operating systems"]
        
        # First check for EOL terms that would make this a mixed request
        eol_terms = ["eol", "end of life", "analysis", "risk", "expire", "support end", "date"]
        has_eol_terms = any(eol_term in message_clean for eol_term in eol_terms)
        
        if any(keyword in message_clean for keyword in pure_inventory_keywords) and not has_eol_terms:
            logger.info(f"🔍 FALLBACK CLASSIFICATION | Pure inventory detected: {message_clean}")
            return "PURE_INVENTORY"
        
        # More general inventory patterns (only if no EOL terms)
        if (any(keyword in message_clean for keyword in ["inventory", "list", "show", "what", "versions"]) and 
            any(keyword in message_clean for keyword in ["software", "os", "operating", "system", "have"]) and
            not has_eol_terms):
            logger.info(f"🔍 FALLBACK CLASSIFICATION | General inventory (no EOL): {message_clean}")
            return "PURE_INVENTORY"
        
        # Simple EOL lookups (check this BEFORE mixed requests to avoid false positives)
        if (any(keyword in message_clean for keyword in ["eol date", "support end", "when does", "expire"]) and 
              any(keyword in message_clean for keyword in ["windows", "office", "ubuntu", "python", "php", "apache"])):
            logger.info(f"🔍 FALLBACK CLASSIFICATION | Simple EOL lookup: {message_clean}")
            return "SIMPLE_EOL"
        
        # Check for mixed requests (inventory + EOL terms) - but exclude simple EOL patterns
        if (has_eol_terms and 
            any(keyword in message_clean for keyword in ["inventory", "show", "list"]) and
            not any(keyword in message_clean for keyword in ["eol date", "support end", "when does", "expire"])):
            logger.info(f"🔍 FALLBACK CLASSIFICATION | Mixed request (inventory + EOL): {message_clean}")
            return "MIXED_REQUEST"
        
        # EOL analysis requests
        elif any(keyword in message_clean for keyword in ["eol analysis", "risk assessment", "comprehensive"]):
            logger.info(f"🔍 FALLBACK CLASSIFICATION | EOL analysis: {message_clean}")
            return "EOL_ANALYSIS"
        
        # Default to mixed request for unclear cases
        else:
            logger.info(f"🔍 FALLBACK CLASSIFICATION | Mixed/unclear request: {message_clean}")
            return "MIXED_REQUEST"

    def _get_cached_inventory(self, key: Tuple[str, int, int]) -> Optional[Dict[str, Any]]:
        ts = self._inventory_cache_timestamp.get(key)
        if ts and (time.time() - ts) < self._cache_ttl_seconds:
            return self._inventory_cache.get(key)
        # Expired
        if key in self._inventory_cache:
            self._inventory_cache.pop(key, None)
            self._inventory_cache_timestamp.pop(key, None)
        return None

    def _cache_inventory(self, key: Tuple[str, int, int], value: Dict[str, Any]):
        self._inventory_cache[key] = value
        self._inventory_cache_timestamp[key] = time.time()
        self._log_agent_action("Orchestrator", "inventory_cache_update", {"key": list(key), "ttl_seconds": self._cache_ttl_seconds, "stored_items": value.get("count")})

    # Cache Management Methods
    # Tool definitions for AutoGen 0.7.x API
    def _get_software_inventory_tool(self, days: int = 90, limit: int = 5000, inventory_only: bool = True, page_size: int = None) -> str:
        """Tool for getting software inventory data - SHOWS ALL ITEMS WITH OPTIONAL PAGINATION
        
        This tool retrieves and displays complete software inventory data:
        - Uses FULL specified limit (5000 by default) - NO dynamic reduction
        - Bypasses load-based limit adjustments to ensure complete inventory visibility
        - Shows all retrieved items up to the specified limit
        - Supports pagination through page_size parameter
        - Backend software_inventory_agent supports up to 10,000 items
        
        Args:
            days: Number of days to look back for data (default 90)
            limit: Maximum items to retrieve from data source (default 5000) - FULL LIMIT USED
            inventory_only: Whether this is inventory-only request (affects termination marker)
            page_size: Optional pagination size for very large inventories (None = show all)
        """
        tool_start_time = datetime.utcnow()
        
        # For inventory queries, use the full limit to ensure complete data retrieval
        # Dynamic limit adjustment is bypassed to guarantee users see their complete inventory
        # logger.debug(f"[TOOL_EXEC] Software inventory tool started - Days: {days}, Limit: {limit} (full limit, no dynamic reduction), Inventory only: {inventory_only}")
        
        self._log_agent_action("InventorySpecialist", "tool_execution_start", {
            "tool": "get_software_inventory",
            "parameters": {
                "days": days,
                "limit": limit,
                "inventory_only": inventory_only,
                "dynamic_adjustment": "disabled_for_complete_inventory"
            },
            "start_time": tool_start_time.isoformat(),
            "caller": "AutoGen agent"
        })
        
        try:
            # Delegate to the specialized software inventory agent
            software_agent = self.software_inventory_agent
            if not software_agent:
                error_msg = "❌ **Software Inventory Configuration Issue**\n\nThe software inventory agent is not available. This usually indicates:\n- Missing Azure Log Analytics workspace configuration (LOG_ANALYTICS_WORKSPACE_ID)\n- Missing Azure authentication credentials\n- Network connectivity issues\n\nPlease check the Azure environment configuration and ensure LOG_ANALYTICS_WORKSPACE_ID and authentication are properly set up."
                logger.error(f"[TOOL_EXEC] ❌ Software inventory tool error: Software inventory agent not available")
                
                self._log_agent_action("InventorySpecialist", "tool_execution_failed", {
                    "tool": "get_software_inventory",
                    "error": "Software inventory agent not available",
                    "error_type": "agent_unavailable",
                    "duration_seconds": (datetime.utcnow() - tool_start_time).total_seconds(),
                    "likely_cause": "Azure configuration missing"
                })
                
                return error_msg
            
            # logger.debug(f"[TOOL_EXEC] Calling software inventory agent")
            cache_key = ("software", days, limit)
            cached = self._get_cached_inventory(cache_key)
            if cached:
                result = cached
                self._log_agent_action("Orchestrator", "inventory_cache_hit", {"key": list(cache_key), "source": "software"})
            else:
                result = self._run_async_safely(software_agent.get_software_inventory(days=days, limit=limit))
                if isinstance(result, dict) and result.get("success"):
                    self._cache_inventory(cache_key, result)
            
            execution_duration = (datetime.utcnow() - tool_start_time).total_seconds()
            # logger.debug(f"[TOOL_EXEC] Software inventory query completed in {execution_duration:.2f}s")
            
            # Handle case where result might not be a dictionary
            if not isinstance(result, dict):
                error_msg = f"Invalid result type from inventory agent: {type(result).__name__} - {str(result)[:200]}"
                logger.error(f"[TOOL_EXEC] ❌ Software inventory tool error: {error_msg}")
                
                self._log_agent_action("InventorySpecialist", "tool_execution_failed", {
                    "tool": "get_software_inventory",
                    "error": error_msg,
                    "error_type": "invalid_result_type",
                    "result_type": type(result).__name__,
                    "duration_seconds": execution_duration
                })
                
                return f"❌ **Error getting software inventory:** {error_msg}"
            
            success = result.get("success", False)
            data_count = len(result.get("data", []))
            total_count = result.get("count", 0)
            
            self._log_agent_action("InventorySpecialist", "tool_execution_complete", {
                "tool": "get_software_inventory",
                "success": success,
                "data_items_returned": data_count,
                "total_items_found": total_count,
                "duration_seconds": execution_duration,
                "data_source": "Log Analytics ConfigurationData table",
                "query_efficiency": {
                    "items_per_second": data_count / execution_duration if execution_duration > 0 else 0,
                    "result_limited": data_count < total_count if total_count > 0 else False
                }
            })
            
            if success:
                
                data = result.get("data", [])
                count = result.get("count", 0)
                
                # Format response for agents - Show ALL items with pagination-friendly format
                if count > 0:
                    response = f"""✅ **Software Inventory Retrieved Successfully**

📊 **Summary:**
- Total items found: {count}
- Query period: Last {days} days
- Data source: Log Analytics ConfigurationData table
- Showing all {len(data)} items retrieved

📋 **Complete Software Inventory:**

"""
                    
                    # Apply pagination if page_size is specified for very large inventories
                    items_to_display = data
                    pagination_info = ""
                    
                    if page_size and len(data) > page_size:
                        # Show first page and add pagination info
                        items_to_display = data[:page_size]
                        remaining_items = len(data) - page_size
                        pagination_info = f"""

📄 **Pagination Info:**
- Showing first {page_size} of {len(data)} items
- {remaining_items} more items available
- To see all items, request without page limits or use specific filters

"""
                    
                    # Display the items (either all or paginated)
                    for i, item in enumerate(items_to_display, 1):
                        response += f"{i}. **{item.get('name', 'Unknown')}** v{item.get('version', 'N/A')}\n"
                        # Handle computers array - show computer count and first few computers
                        computers = item.get('computers', [])
                        computer_count = item.get('computer_count', len(computers) if isinstance(computers, list) else 0)
                        if computer_count > 0:
                            if isinstance(computers, list) and len(computers) > 0:
                                if len(computers) <= 3:
                                    response += f"   - Computers ({computer_count}): {', '.join(computers)}\n"
                                else:
                                    response += f"   - Computers ({computer_count}): {', '.join(computers[:3])}, ... and {len(computers)-3} more\n"
                            else:
                                response += f"   - Computer count: {computer_count}\n"
                        response += f"   - Publisher: {item.get('publisher', 'Unknown')}\n"
                        response += f"   - Software Type: {item.get('software_type', 'Application')}\n"
                        if item.get('last_seen'):
                            response += f"   - Last Seen: {item.get('last_seen')}\n"
                        response += "\n"
                    
                    # Add pagination info if applicable
                    response += pagination_info
                    
                    response += "This is complete inventory data from Log Analytics."
                    
                    # INVENTORY PAGINATION UPDATE:
                    # - Removed artificial 20-item display limit from software inventory
                    # - Increased default limits: Software 1000→5000, OS 500→2000, OS+EOL 300→1000
                    # - CRITICAL: Disabled dynamic limit reduction for inventory queries
                    # - Backend agents now receive FULL specified limits (5000/2000) 
                    # - All retrieved items are now displayed to user
                    # - Frontend chat.html already supports scrollable inventory tables
                    # - Users can now see their complete inventory without arbitrary truncation
                    
                    # Only add INVENTORY_COMPLETE for pure inventory requests
                    if inventory_only:
                        response += "\n\nINVENTORY_COMPLETE"
                    
                    self._log_agent_action("InventorySpecialist", "get_software_inventory_result", {
                        "count": count,
                        "total_items": len(data)
                    })
                    
                    return response
                else:
                    result = f"✅ Software inventory query successful but no software data found in the last {days} days."
                    if inventory_only:
                        result += "\n\nINVENTORY_COMPLETE"
                    return result
            else:
                error = result.get("error", "Unknown error")
                error_type = result.get("error_type", "Unknown")
                
                self._log_agent_action("InventorySpecialist", "get_software_inventory_error", {
                    "error": error,
                    "error_type": error_type
                })
                
                return f"❌ **Software Inventory Error:** {error}\n\nError Type: {error_type}\n\nPlease check the Log Analytics workspace configuration and connectivity."
                
        except Exception as e:
            error_msg = f"Error getting software inventory: {str(e)}"
            # logger.debug(f"[DEBUG] Software inventory tool error: {error_msg}")
            
            self._log_agent_action("InventorySpecialist", "get_software_inventory_exception", {"error": error_msg})
            return f"❌ **Exception in Software Inventory Tool:** {error_msg}"
    
    def _get_os_inventory_tool(self, days: int = 90, limit: int = 2000, inventory_only: bool = True) -> str:
        """Tool for getting operating system inventory data - SHOWS ALL OS ITEMS
        
        This tool retrieves and displays complete OS inventory data:
        - Uses FULL specified limit (2000 by default) - NO dynamic reduction
        - Bypasses load-based limit adjustments to ensure complete OS inventory visibility
        - No artificial item limits - shows all retrieved OS instances
        - Backend os_inventory_agent supports up to 2000 items by default
        
        Args:
            days: Number of days to look back for data (default 90)
            limit: Maximum items to retrieve from data source (default 2000) - FULL LIMIT USED
            inventory_only: Whether this is inventory-only request (affects termination marker)
        """
        try:
            # For OS inventory queries, use the full limit to ensure complete data retrieval
            # Dynamic limit adjustment is bypassed to guarantee users see their complete OS inventory
            # logger.debug(f"[DEBUG] Getting OS inventory: days={days}, limit={limit} (full limit, no dynamic reduction), inventory_only={inventory_only}")
            
            # Delegate to the specialized OS inventory agent
            os_agent = self.os_inventory_agent
            if not os_agent:
                error_msg = "❌ **OS Inventory Configuration Issue**\n\nThe OS inventory agent is not available. This usually indicates:\n- Missing Azure Log Analytics workspace configuration (LOG_ANALYTICS_WORKSPACE_ID)\n- Missing Azure authentication credentials\n- Network connectivity issues\n\nPlease check the Azure environment configuration and ensure LOG_ANALYTICS_WORKSPACE_ID and authentication are properly set up."
                logger.error(f"❌ OS inventory tool error: OS inventory agent not available")
                return error_msg
            
            cache_key = ("os", days, limit)
            cached = self._get_cached_inventory(cache_key)
            if cached:
                result = cached
                self._log_agent_action("Orchestrator", "inventory_cache_hit", {"key": list(cache_key), "source": "os"})
            else:
                result = self._run_async_safely(os_agent.get_os_inventory(days=days, limit=limit))
                if isinstance(result, dict) and result.get("success"):
                    self._cache_inventory(cache_key, result)
            
            # Handle case where result might not be a dictionary
            if not isinstance(result, dict):
                error_msg = f"Invalid result type from OS inventory agent: {type(result).__name__} - {str(result)[:200]}"
                logger.error(f"❌ OS inventory tool error: {error_msg}")
                return f"❌ **Error getting OS inventory:** {error_msg}"
            
            self._log_agent_action("InventorySpecialist", "get_os_inventory", {
                "days": days, 
                "limit": limit,
                "success": result.get("success", False)
            })
            
            if result.get("success"):
                
                data = result.get("data", [])
                count = result.get("count", 0)
                
                # Format response for agents
                if count > 0:
                    # Show summary plus all OS items
                    response = f"""✅ **Operating System Inventory Retrieved Successfully**

📊 **Summary:**
- Total OS items found: {count}
- Query period: Last {days} days
- Data source: Log Analytics Heartbeat table
- All OS items:

"""
                    for i, item in enumerate(data, 1):
                        response += f"{i}. **{item.get('os_name', 'Unknown')}** v{item.get('os_version', 'N/A')}\n"
                        response += f"   - Computer: {item.get('computer_name', 'Unknown')}\n"
                        response += f"   - OS Type: {item.get('os_type', 'Unknown')}\n"
                        response += f"   - Vendor: {item.get('vendor', 'Unknown')}\n"
                        if item.get('computer_environment'):
                            response += f"   - Environment: {item.get('computer_environment')}\n"
                        if item.get('days_since_heartbeat') is not None:
                            days_since = item.get('days_since_heartbeat', 0)
                            if days_since == 0:
                                response += f"   - Status: ✅ Active (last seen today)\n"
                            elif days_since <= 7:
                                response += f"   - Status: 🟡 Recently active ({days_since} days ago)\n"
                            else:
                                response += f"   - Status: 🔴 Inactive ({days_since} days ago)\n"
                        response += "\n"
                    
                    response += "This is OS inventory data from Log Analytics."
                    
                    # Only add INVENTORY_COMPLETE for pure inventory requests
                    if inventory_only:
                        response += "\n\nINVENTORY_COMPLETE"
                    
                    self._log_agent_action("InventorySpecialist", "get_os_inventory_result", {
                        "count": count,
                        "total_items": len(data)
                    })
                    
                    return response
                else:
                    result = f"✅ OS inventory query successful but no operating system data found in the last {days} days."
                    if inventory_only:
                        result += "\n\nINVENTORY_COMPLETE"
                    return result
            else:
                error = result.get("error", "Unknown error")
                error_type = result.get("error_type", "Unknown")
                
                self._log_agent_action("InventorySpecialist", "get_os_inventory_error", {
                    "error": error,
                    "error_type": error_type
                })
                
                return f"❌ **OS Inventory Error:** {error}\n\nError Type: {error_type}\n\nPlease check the Log Analytics workspace configuration and Heartbeat data availability."
                
        except Exception as e:
            error_msg = f"Error getting OS inventory: {str(e)}"
            # logger.debug(f"[DEBUG] OS inventory tool error: {error_msg}")
            
            self._log_agent_action("InventorySpecialist", "get_os_inventory_exception", {"error": error_msg})
            return f"❌ **Exception in OS Inventory Tool:** {error_msg}"

    def _get_os_inventory_with_eol_tool(self, days: int = 90, limit: int = 1000) -> str:
        """Tool for getting OS inventory WITH automatic EOL analysis for detected operating systems
        
        Increased default limit from 300 to 1000 for comprehensive OS coverage with EOL analysis.
        """
        try:
            # For OS+EOL inventory queries, use the full limit to ensure complete data retrieval
            logger.info(f"🖥️ OS INVENTORY + EOL | Starting combined OS inventory and EOL analysis - Limit: {limit} (full limit, no dynamic reduction)")
            
            # Step 1: Get OS inventory data
            os_agent = self.os_inventory_agent
            if not os_agent:
                error_msg = "❌ **OS Inventory Configuration Issue**\n\nThe OS inventory agent is not available. This usually indicates:\n- Missing Azure Log Analytics workspace configuration (LOG_ANALYTICS_WORKSPACE_ID)\n- Missing Azure authentication credentials\n- Network connectivity issues\n\nPlease check the Azure environment configuration and ensure LOG_ANALYTICS_WORKSPACE_ID and authentication are properly set up."
                logger.error(f"❌ OS inventory + EOL tool error: OS inventory agent not available")
                return error_msg
            
            cache_key = ("os_eol_combo_raw", days, limit)
            cached = self._get_cached_inventory(cache_key)
            if cached:
                result = cached
                self._log_agent_action("Orchestrator", "inventory_cache_hit", {"key": list(cache_key), "source": "os_eol_combo_raw"})
            else:
                result = self._run_async_safely(os_agent.get_os_inventory(days=days, limit=limit))
                if isinstance(result, dict) and result.get("success"):
                    self._cache_inventory(cache_key, result)
            
            if not isinstance(result, dict) or not result.get("success"):
                error = result.get("error", "Unknown error") if isinstance(result, dict) else str(result)
                return f"❌ **Error getting OS inventory:** {error}"
            
            data = result.get("data", [])
            count = result.get("count", 0)
            
            if count == 0:
                return f"✅ OS inventory query successful but no operating system data found in the last {days} days."
            
            # Step 2: Build inventory response
            response = f"""✅ **Operating System Inventory with EOL Analysis**

📊 **OS Inventory Summary:**
- Total OS items found: {count}
- Query period: Last {days} days
- Data source: Log Analytics Heartbeat table

📋 **Detailed OS Inventory with EOL Status:**

"""
            
            # Step 3: Process each OS and check EOL
            microsoft_oses_checked = set()
            
            for i, item in enumerate(data, 1):
                os_name = item.get('os_name', 'Unknown')
                os_version = item.get('os_version', 'N/A')
                computer_name = item.get('computer_name', 'Unknown')
                os_type = item.get('os_type', 'Unknown')
                vendor = item.get('vendor', 'Unknown')
                
                response += f"{i}. **{os_name}** v{os_version}\n"
                response += f"   - Computer: {computer_name}\n"
                response += f"   - OS Type: {os_type}\n"
                response += f"   - Vendor: {vendor}\n"
                
                # Add heartbeat status
                if item.get('days_since_heartbeat') is not None:
                    days_since = item.get('days_since_heartbeat', 0)
                    if days_since == 0:
                        response += f"   - Status: ✅ Active (last seen today)\n"
                    elif days_since <= 7:
                        response += f"   - Status: 🟡 Recently active ({days_since} days ago)\n"
                    else:
                        response += f"   - Status: 🔴 Inactive ({days_since} days ago)\n"
                
                # Step 4: Check EOL for Microsoft operating systems using smart search
                if self._is_microsoft_os(os_name):
                    # Create a unique key for this OS to avoid duplicate checks
                    os_key = f"{os_name}-{os_version}".lower()
                    if os_key not in microsoft_oses_checked:
                        microsoft_oses_checked.add(os_key)
                        logger.info(f"🔍 Smart EOL search for Microsoft OS: {os_name} {os_version}")
                        
                        try:
                            # Use smart EOL search that tries specific first, then falls back
                            eol_result = self._smart_eol_search(os_name, os_version, "microsoft")
                            if eol_result and "No EOL data found" not in eol_result and "Error" not in eol_result:
                                response += f"   - 📅 **EOL Analysis:** {eol_result.strip()}\n"
                            else:
                                response += f"   - 📅 **EOL Status:** No EOL data available for this version\n"
                        except Exception as e:
                            logger.error(f"Error in smart EOL search for {os_name}: {e}")
                            response += f"   - 📅 **EOL Status:** Error checking EOL data\n"
                    else:
                        response += f"   - 📅 **EOL Status:** (Same as above {os_name} {os_version})\n"
                else:
                    # For non-Microsoft OSes, use smart search with appropriate specialist
                    os_key = f"{os_name}-{os_version}".lower()
                    if os_key not in microsoft_oses_checked:  # Reuse same tracking set for all OSes
                        microsoft_oses_checked.add(os_key)
                        
                        # Determine the appropriate specialist
                        specialist = "endoflife"  # Default
                        if "ubuntu" in os_name.lower():
                            specialist = "ubuntu"
                        elif "red hat" in os_name.lower() or "rhel" in os_name.lower():
                            specialist = "redhat"
                        
                        logger.info(f"🔍 Smart EOL search for {specialist.title()} OS: {os_name} {os_version}")
                        
                        try:
                            eol_result = self._smart_eol_search(os_name, os_version, specialist)
                            if eol_result and "No EOL data found" not in eol_result and "Error" not in eol_result:
                                response += f"   - 📅 **EOL Analysis:** {eol_result.strip()}\n"
                            else:
                                response += f"   - 📅 **EOL Status:** No EOL data available for this version\n"
                        except Exception as e:
                            logger.error(f"Error in smart EOL search for {os_name}: {e}")
                            response += f"   - 📅 **EOL Status:** Error checking EOL data\n"
                    else:
                        response += f"   - 📅 **EOL Status:** (Same as above {os_name} {os_version})\n"
                
                response += "\n"
            
            # Summary of EOL findings
            if microsoft_oses_checked:
                response += f"\n🔍 **EOL Analysis Summary:**\n"
                response += f"- Microsoft OSes analyzed: {len(microsoft_oses_checked)}\n"
                response += f"- Total OS instances: {count}\n"
                response += f"- For detailed EOL recommendations, ask for specific OS analysis\n"
            
            self._log_agent_action("InventorySpecialist", "get_os_inventory_with_eol_result", {
                "count": count,
                "microsoft_oses_checked": len(microsoft_oses_checked),
                "total_items": len(data)
            })
            
            return response
            
        except Exception as e:
            error_msg = f"Error getting OS inventory with EOL: {str(e)}"
            logger.error(f"❌ OS inventory + EOL tool error: {error_msg}")
            self._log_agent_action("InventorySpecialist", "get_os_inventory_with_eol_error", {"error": error_msg})
            return error_msg

    def _is_microsoft_os(self, os_name: str) -> bool:
        """Helper method to identify Microsoft operating systems"""
        if not os_name:
            return False
        
        os_name_lower = os_name.lower()
        microsoft_os_keywords = [
            'windows', 'microsoft', 'windows server', 'windows 10', 'windows 11', 
            'windows 8', 'windows 7', 'windows vista', 'windows xp'
        ]
        
        return any(keyword in os_name_lower for keyword in microsoft_os_keywords)
    
    def _smart_eol_search(self, os_name: str, os_version: str, specialist: str) -> str:
        """
        Intelligent EOL search that tries multiple search strategies:
        1. First: exact OS name + version
        2. If confidence < 80% or no results: OS name only  
        3. If still no results: normalized OS name
        Returns only the best single result with highest confidence
        """
        logger.info(f"🔍 SMART EOL SEARCH START | OS: {os_name} | Version: {os_version} | Specialist: {specialist}")
        
        search_attempts = []
        best_result = None
        best_confidence = 0.0
        
        try:
            # Strategy 1: Try exact OS name + version
            logger.info(f"🔍 Strategy 1: Exact match - '{os_name}' + '{os_version}'")
            result1 = self._call_specialist_eol_tool(specialist, os_name, os_version)
            
            confidence1 = self._extract_confidence_from_result(result1)
            search_attempts.append({"strategy": "exact", "query": f"{os_name} {os_version}", "confidence": confidence1, "result": result1})
            
            if confidence1 >= 80.0 and "No EOL data found" not in result1 and "Error" not in result1:
                logger.info(f"✅ Strategy 1 SUCCESS | Confidence: {confidence1}% | Using exact match result")
                return result1
            
            # Strategy 2: Try OS name only
            logger.info(f"🔍 Strategy 2: OS name only - '{os_name}'")
            result2 = self._call_specialist_eol_tool(specialist, os_name, None)
            
            confidence2 = self._extract_confidence_from_result(result2)
            search_attempts.append({"strategy": "name_only", "query": os_name, "confidence": confidence2, "result": result2})
            
            if confidence2 >= 80.0 and "No EOL data found" not in result2 and "Error" not in result2:
                logger.info(f"✅ Strategy 2 SUCCESS | Confidence: {confidence2}% | Using OS name only result")
                return result2
            
            # Strategy 3: Try normalized OS name (remove extra descriptors)
            normalized_name = self._normalize_os_name(os_name)
            if normalized_name != os_name:
                logger.info(f"🔍 Strategy 3: Normalized name - '{normalized_name}'")
                result3 = self._call_specialist_eol_tool(specialist, normalized_name, None)
                
                confidence3 = self._extract_confidence_from_result(result3)
                search_attempts.append({"strategy": "normalized", "query": normalized_name, "confidence": confidence3, "result": result3})
                
                if confidence3 >= 80.0 and "No EOL data found" not in result3 and "Error" not in result3:
                    logger.info(f"✅ Strategy 3 SUCCESS | Confidence: {confidence3}% | Using normalized name result")
                    return result3
            
            # Choose the best result from all attempts
            for attempt in search_attempts:
                if (attempt["confidence"] > best_confidence and 
                    "No EOL data found" not in attempt["result"] and 
                    "Error" not in attempt["result"]):
                    best_confidence = attempt["confidence"]
                    best_result = attempt["result"]
            
            if best_result:
                logger.info(f"✅ SMART SEARCH COMPLETE | Best confidence: {best_confidence}% | Using best available result")
                return best_result
            else:
                logger.warning(f"❌ SMART SEARCH FAILED | No valid results found from any strategy")
                return "No reliable EOL data found for this OS"
                
        except Exception as e:
            logger.error(f"❌ SMART EOL SEARCH ERROR | {e}")
            return f"Error in smart EOL search: {str(e)}"
    
    def _call_specialist_eol_tool(self, specialist: str, software_name: str, version: str = None) -> str:
        """
        Call the appropriate EOL specialist tool based on the specialist type
        """
        try:
            if specialist == "microsoft":
                return self._check_microsoft_eol_tool(software_name, version)
            elif specialist == "ubuntu":
                return self._check_ubuntu_eol_tool(software_name, version)
            elif specialist == "redhat":
                return self._check_redhat_eol_tool(software_name, version)
            elif specialist == "oracle":
                return self._check_oracle_eol_tool(software_name, version)
            elif specialist == "apache":
                return self._check_apache_eol_tool(software_name, version)
            elif specialist == "python":
                return self._check_python_eol_tool(software_name, version)
            elif specialist == "nodejs":
                return self._check_nodejs_eol_tool(software_name, version)
            elif specialist == "php":
                return self._check_php_eol_tool(software_name, version)
            elif specialist == "postgresql":
                return self._check_postgresql_eol_tool(software_name, version)
            elif specialist == "vmware":
                return self._check_vmware_eol_tool(software_name, version)
            else:  # Default to endoflife.date for unknown specialists
                return self._check_endoflife_eol_tool(software_name, version)
        except Exception as e:
            logger.error(f"❌ SPECIALIST TOOL ERROR | Specialist: {specialist} | Software: {software_name} | Error: {e}")
            return f"Error calling {specialist} EOL tool: {str(e)}"
    
    def _normalize_os_name(self, os_name: str) -> str:
        """
        Normalize OS name by removing edition descriptors and extra details
        Examples:
        - "Windows Server 2025 Datacenter Azure Edition" -> "Windows Server 2025"
        - "Ubuntu 20.04.3 LTS" -> "Ubuntu 20.04"
        - "Red Hat Enterprise Linux 8.5" -> "Red Hat Enterprise Linux 8"
        """
        normalized = os_name.strip()
        
        # Microsoft Windows normalizations
        if "windows" in normalized.lower():
            # Remove edition descriptors
            editions_to_remove = [
                "datacenter", "standard", "enterprise", "professional", "home", "education",
                "azure edition", "core", "essentials", "foundation", "web edition",
                "starter", "ultimate", "business", "oem"
            ]
            
            for edition in editions_to_remove:
                normalized = normalized.replace(f" {edition}", "").replace(f" {edition.title()}", "")
            
            # Clean up extra spaces
            normalized = " ".join(normalized.split())
        
        # Ubuntu normalizations
        elif "ubuntu" in normalized.lower():
            # Remove point releases and LTS descriptor
            import re
            # Keep major.minor version, remove point releases
            normalized = re.sub(r'(\d+\.\d+)\.\d+', r'\1', normalized)
            normalized = normalized.replace(" LTS", "")
        
        # Red Hat normalizations  
        elif "red hat" in normalized.lower() or "rhel" in normalized.lower():
            import re
            # Keep major version only for RHEL
            normalized = re.sub(r'(\d+)\.\d+', r'\1', normalized)
        
        # General cleanup
        normalized = " ".join(normalized.split())  # Remove extra spaces
        
        logger.info(f"🔧 OS NAME NORMALIZATION | Original: '{os_name}' -> Normalized: '{normalized}'")
        return normalized
    
    def _extract_confidence_from_result(self, eol_result: str) -> float:
        """
        Extract confidence percentage from EOL result text
        Returns 0.0 if no confidence found or result indicates error/no data
        """
        if not eol_result or "Error" in eol_result or "No EOL data found" in eol_result or "No Microsoft EOL data found" in eol_result:
            return 0.0
        
        try:
            import re
            # Look for confidence percentage in the result (matches "Confidence" followed by any characters and then percentage)
            confidence_match = re.search(r'Confidence.*?(\d+)%', eol_result, re.IGNORECASE | re.UNICODE)
            if confidence_match:
                confidence = float(confidence_match.group(1))
                logger.debug(f"📊 CONFIDENCE EXTRACTED | Found: {confidence}%")
                return confidence
            else:
                # If no explicit confidence but we have valid EOL data, assume reasonable confidence
                if "End of Life Date:" in eol_result or "Support End Date:" in eol_result:
                    logger.debug(f"📊 CONFIDENCE ESTIMATED | No explicit confidence, but valid EOL data found: 75%")
                    return 75.0
                else:
                    logger.debug(f"📊 CONFIDENCE DEFAULT | No confidence or EOL data indicators: 0%")
                    return 0.0
        except Exception as e:
            logger.warning(f"⚠️ CONFIDENCE EXTRACTION ERROR | {e} | Defaulting to 0%")
            return 0.0
    
    def _check_microsoft_eol_tool(self, software_name: str, version: str = None) -> str:
        """Tool for checking Microsoft software EOL status"""
        tool_start_time = datetime.utcnow()
        # logger.debug(f"[TOOL_EXEC] Microsoft EOL tool started - Software: {software_name}, Version: {version}")
        
        self._log_agent_action("MicrosoftEOLSpecialist", "eol_check_start", {
            "tool": "check_microsoft_eol",
            "software_name": software_name,
            "version": version,
            "start_time": tool_start_time.isoformat(),
            "data_source": "Microsoft Lifecycle API"
        })
        
        try:
            # Use the helper method to safely run async code
            # logger.debug(f"[TOOL_EXEC] Calling Microsoft agent for EOL data")
            eol_data = self._run_async_safely(self.microsoft_agent.get_eol_data(software_name, version))
            
            execution_duration = (datetime.utcnow() - tool_start_time).total_seconds()
            # logger.debug(f"[TOOL_EXEC] Microsoft EOL check completed in {execution_duration:.2f}s")
            
            self._log_agent_action("MicrosoftEOLSpecialist", "eol_check_complete", {
                "tool": "check_microsoft_eol",
                "software_name": software_name,
                "version": version,
                "duration_seconds": execution_duration,
                "data_found": bool(eol_data),
                "full_data": eol_data  # Include full data for extraction
            })
            
            if eol_data:
                self._log_agent_action("MicrosoftEOLSpecialist", "eol_data_processing", {
                    "software_name": software_name,
                    "data_type": type(eol_data).__name__,
                    "processing_action": "formatting_for_agents"
                })
                
                formatted_result = self._format_eol_data_for_agents("Microsoft", software_name, eol_data)
                
                self._log_agent_action("MicrosoftEOLSpecialist", "eol_check_success", {
                    "software_name": software_name,
                    "version": version,
                    "result_length": len(formatted_result),
                    "duration_seconds": execution_duration,
                    "status": "success"
                })
                
                return formatted_result
            else:
                no_data_msg = f"No Microsoft EOL data found for {software_name}"
                self._log_agent_action("MicrosoftEOLSpecialist", "eol_check_no_data", {
                    "software_name": software_name,
                    "version": version,
                    "duration_seconds": execution_duration,
                    "status": "no_data_found"
                })
                return no_data_msg
                
        except Exception as e:
            execution_duration = (datetime.utcnow() - tool_start_time).total_seconds()
            error_msg = f"Error checking Microsoft EOL: {str(e)}"
            logger.error(f"[TOOL_EXEC] Microsoft EOL tool exception after {execution_duration:.2f}s: {error_msg}")
            
            self._log_agent_action("MicrosoftEOLSpecialist", "eol_check_exception", {
                "tool": "check_microsoft_eol",
                "software_name": software_name,
                "version": version,
                "error": str(e),
                "duration_seconds": execution_duration,
                "error_type": "exception"
            })
            
            return error_msg
    
    def _check_ubuntu_eol_tool(self, software_name: str, version: str = None) -> str:
        """Tool for checking Ubuntu software EOL status"""
        tool_start_time = datetime.utcnow()
        
        self._log_agent_action("UbuntuEOLSpecialist", "eol_check_start", {
            "tool": "check_ubuntu_eol",
            "software_name": software_name,
            "version": version,
            "start_time": tool_start_time.isoformat(),
            "data_source": "Ubuntu EOL Database"
        })
        
        try:
            # Use the helper method to safely run async code
            eol_data = self._run_async_safely(self.ubuntu_agent.get_eol_data(software_name, version))
            
            execution_duration = (datetime.utcnow() - tool_start_time).total_seconds()
            
            self._log_agent_action("UbuntuEOLSpecialist", "eol_check_complete", {
                "tool": "check_ubuntu_eol",
                "software_name": software_name,
                "version": version,
                "duration_seconds": execution_duration,
                "data_found": bool(eol_data),
                "full_data": eol_data  # Include full data for extraction
            })
            
            if eol_data:
                self._log_agent_action("UbuntuEOLSpecialist", "eol_data_processing", {
                    "software_name": software_name,
                    "data_type": type(eol_data).__name__,
                    "processing_action": "formatting_for_agents"
                })
                
                formatted_result = self._format_eol_data_for_agents("Ubuntu", software_name, eol_data)
                
                self._log_agent_action("UbuntuEOLSpecialist", "eol_check_success", {
                    "software_name": software_name,
                    "version": version,
                    "result_length": len(formatted_result),
                    "duration_seconds": execution_duration,
                    "status": "success"
                })
                
                return formatted_result
            else:
                no_data_msg = f"No Ubuntu EOL data found for {software_name}"
                self._log_agent_action("UbuntuEOLSpecialist", "eol_check_no_data", {
                    "software_name": software_name,
                    "version": version,
                    "duration_seconds": execution_duration,
                    "status": "no_data_found"
                })
                return no_data_msg
                
        except Exception as e:
            execution_duration = (datetime.utcnow() - tool_start_time).total_seconds()
            error_msg = f"Error checking Ubuntu EOL: {str(e)}"
            logger.error(f"Ubuntu EOL tool exception after {execution_duration:.2f}s: {error_msg}")
            
            self._log_agent_action("UbuntuEOLSpecialist", "eol_check_exception", {
                "tool": "check_ubuntu_eol",
                "software_name": software_name,
                "version": version,
                "error": str(e),
                "duration_seconds": execution_duration,
                "error_type": "exception"
            })
            
            return error_msg
    
    def _check_oracle_eol_tool(self, software_name: str, version: str = None) -> str:
        """Tool for checking Oracle software EOL status"""
        tool_start_time = datetime.utcnow()
        
        self._log_agent_action("OracleEOLSpecialist", "eol_check_start", {
            "tool": "check_oracle_eol",
            "software_name": software_name,
            "version": version,
            "start_time": tool_start_time.isoformat(),
            "data_source": "Oracle Lifecycle Database"
        })
        
        try:
            # Use the helper method to safely run async code
            eol_data = self._run_async_safely(self.oracle_agent.get_eol_data(software_name, version))
            
            execution_duration = (datetime.utcnow() - tool_start_time).total_seconds()
            
            self._log_agent_action("OracleEOLSpecialist", "eol_check_complete", {
                "tool": "check_oracle_eol",
                "software_name": software_name,
                "version": version,
                "duration_seconds": execution_duration,
                "data_found": bool(eol_data),
                "full_data": eol_data  # Include full data for extraction
            })
            
            if eol_data:
                self._log_agent_action("OracleEOLSpecialist", "eol_data_processing", {
                    "software_name": software_name,
                    "data_type": type(eol_data).__name__,
                    "processing_action": "formatting_for_agents"
                })
                
                formatted_result = self._format_eol_data_for_agents("Oracle", software_name, eol_data)
                
                self._log_agent_action("OracleEOLSpecialist", "eol_check_success", {
                    "software_name": software_name,
                    "version": version,
                    "result_length": len(formatted_result),
                    "duration_seconds": execution_duration,
                    "status": "success"
                })
                
                return formatted_result
            else:
                no_data_msg = f"No Oracle EOL data found for {software_name}"
                self._log_agent_action("OracleEOLSpecialist", "eol_check_no_data", {
                    "software_name": software_name,
                    "version": version,
                    "duration_seconds": execution_duration,
                    "status": "no_data_found"
                })
                return no_data_msg
                
        except Exception as e:
            execution_duration = (datetime.utcnow() - tool_start_time).total_seconds()
            error_msg = f"Error checking Oracle EOL: {str(e)}"
            logger.error(f"Oracle EOL tool exception after {execution_duration:.2f}s: {error_msg}")
            
            self._log_agent_action("OracleEOLSpecialist", "eol_check_exception", {
                "tool": "check_oracle_eol",
                "software_name": software_name,
                "version": version,
                "error": str(e),
                "duration_seconds": execution_duration,
                "error_type": "exception"
            })
            
            return error_msg
    
    def _check_redhat_eol_tool(self, software_name: str, version: str = None) -> str:
        """Tool for checking Red Hat software EOL status"""
        tool_start_time = datetime.utcnow()
        
        self._log_agent_action("RedHatEOLSpecialist", "eol_check_start", {
            "tool": "check_redhat_eol",
            "software_name": software_name,
            "version": version,
            "start_time": tool_start_time.isoformat(),
            "data_source": "Red Hat Lifecycle Database"
        })
        
        try:
            # Use the helper method to safely run async code
            eol_data = self._run_async_safely(self.redhat_agent.get_eol_data(software_name, version))
            
            execution_duration = (datetime.utcnow() - tool_start_time).total_seconds()
            
            self._log_agent_action("RedHatEOLSpecialist", "eol_check_complete", {
                "tool": "check_redhat_eol",
                "software_name": software_name,
                "version": version,
                "duration_seconds": execution_duration,
                "data_found": bool(eol_data),
                "full_data": eol_data  # Include full data for extraction
            })
            
            if eol_data:
                self._log_agent_action("RedHatEOLSpecialist", "eol_data_processing", {
                    "software_name": software_name,
                    "data_type": type(eol_data).__name__,
                    "processing_action": "formatting_for_agents"
                })
                
                formatted_result = self._format_eol_data_for_agents("Red Hat", software_name, eol_data)
                
                self._log_agent_action("RedHatEOLSpecialist", "eol_check_success", {
                    "software_name": software_name,
                    "version": version,
                    "result_length": len(formatted_result),
                    "duration_seconds": execution_duration,
                    "status": "success"
                })
                
                return formatted_result
            else:
                no_data_msg = f"No Red Hat EOL data found for {software_name}"
                self._log_agent_action("RedHatEOLSpecialist", "eol_check_no_data", {
                    "software_name": software_name,
                    "version": version,
                    "duration_seconds": execution_duration,
                    "status": "no_data_found"
                })
                return no_data_msg
                
        except Exception as e:
            execution_duration = (datetime.utcnow() - tool_start_time).total_seconds()
            error_msg = f"Error checking Red Hat EOL: {str(e)}"
            logger.error(f"Red Hat EOL tool exception after {execution_duration:.2f}s: {error_msg}")
            
            self._log_agent_action("RedHatEOLSpecialist", "eol_check_exception", {
                "tool": "check_redhat_eol",
                "software_name": software_name,
                "version": version,
                "error": str(e),
                "duration_seconds": execution_duration,
                "error_type": "exception"
            })
            
            return error_msg
    
    def _check_vmware_eol_tool(self, software_name: str, version: str = None) -> str:
        """Tool for checking VMware software EOL status"""
        tool_start_time = datetime.utcnow()
        
        self._log_agent_action("VMwareEOLSpecialist", "eol_check_start", {
            "tool": "check_vmware_eol",
            "software_name": software_name,
            "version": version,
            "start_time": tool_start_time.isoformat(),
            "data_source": "VMware Lifecycle Database"
        })
        
        try:
            eol_data = self._run_async_safely(self.vmware_agent.get_eol_data(software_name, version))
            
            execution_duration = (datetime.utcnow() - tool_start_time).total_seconds()
            
            self._log_agent_action("VMwareEOLSpecialist", "eol_check_complete", {
                "tool": "check_vmware_eol",
                "software_name": software_name,
                "version": version,
                "duration_seconds": execution_duration,
                "data_found": bool(eol_data),
                "full_data": eol_data  # Include full data for extraction
            })
            
            if eol_data:
                self._log_agent_action("VMwareEOLSpecialist", "eol_data_processing", {
                    "software_name": software_name,
                    "data_type": type(eol_data).__name__,
                    "processing_action": "formatting_for_agents"
                })
                
                formatted_result = self._format_eol_data_for_agents("VMware", software_name, eol_data)
                
                self._log_agent_action("VMwareEOLSpecialist", "eol_check_success", {
                    "software_name": software_name,
                    "version": version,
                    "result_length": len(formatted_result),
                    "duration_seconds": execution_duration,
                    "status": "success"
                })
                
                return formatted_result
            else:
                no_data_msg = f"No VMware EOL data found for {software_name}"
                self._log_agent_action("VMwareEOLSpecialist", "eol_check_no_data", {
                    "software_name": software_name,
                    "version": version,
                    "duration_seconds": execution_duration,
                    "status": "no_data_found"
                })
                return no_data_msg
                
        except Exception as e:
            execution_duration = (datetime.utcnow() - tool_start_time).total_seconds()
            error_msg = f"Error checking VMware EOL: {str(e)}"
            logger.error(f"VMware EOL tool exception after {execution_duration:.2f}s: {error_msg}")
            
            self._log_agent_action("VMwareEOLSpecialist", "eol_check_exception", {
                "tool": "check_vmware_eol",
                "software_name": software_name,
                "version": version,
                "error": str(e),
                "duration_seconds": execution_duration,
                "error_type": "exception"
            })
            
            return error_msg
    
    def _check_apache_eol_tool(self, software_name: str, version: str = None) -> str:
        """Tool for checking Apache software EOL status"""
        tool_start_time = datetime.utcnow()
        
        self._log_agent_action("ApacheEOLSpecialist", "eol_check_start", {
            "tool": "check_apache_eol",
            "software_name": software_name,
            "version": version,
            "start_time": tool_start_time.isoformat(),
            "data_source": "Apache EOL Database"
        })
        
        try:
            eol_data = self._run_async_safely(self.apache_agent.get_eol_data(software_name, version))
            
            execution_duration = (datetime.utcnow() - tool_start_time).total_seconds()
            
            self._log_agent_action("ApacheEOLSpecialist", "eol_check_complete", {
                "tool": "check_apache_eol",
                "software_name": software_name,
                "version": version,
                "duration_seconds": execution_duration,
                "data_found": bool(eol_data),
                "full_data": eol_data  # Include full data for extraction
            })
            
            if eol_data:
                self._log_agent_action("ApacheEOLSpecialist", "eol_data_processing", {
                    "software_name": software_name,
                    "data_type": type(eol_data).__name__,
                    "processing_action": "formatting_for_agents"
                })
                
                formatted_result = self._format_eol_data_for_agents("Apache", software_name, eol_data)
                
                self._log_agent_action("ApacheEOLSpecialist", "eol_check_success", {
                    "software_name": software_name,
                    "version": version,
                    "result_length": len(formatted_result),
                    "duration_seconds": execution_duration,
                    "status": "success"
                })
                
                return formatted_result
            else:
                no_data_msg = f"No Apache EOL data found for {software_name}"
                self._log_agent_action("ApacheEOLSpecialist", "eol_check_no_data", {
                    "software_name": software_name,
                    "version": version,
                    "duration_seconds": execution_duration,
                    "status": "no_data_found"
                })
                return no_data_msg
                
        except Exception as e:
            execution_duration = (datetime.utcnow() - tool_start_time).total_seconds()
            error_msg = f"Error checking Apache EOL: {str(e)}"
            logger.error(f"Apache EOL tool exception after {execution_duration:.2f}s: {error_msg}")
            
            self._log_agent_action("ApacheEOLSpecialist", "eol_check_exception", {
                "tool": "check_apache_eol",
                "software_name": software_name,
                "version": version,
                "error": str(e),
                "duration_seconds": execution_duration,
                "error_type": "exception"
            })
            
            return error_msg
    
    def _check_nodejs_eol_tool(self, software_name: str, version: str = None) -> str:
        """Tool for checking Node.js EOL status"""
        tool_start_time = datetime.utcnow()
        
        self._log_agent_action("NodeJSEOLSpecialist", "eol_check_start", {
            "tool": "check_nodejs_eol",
            "software_name": software_name,
            "version": version,
            "start_time": tool_start_time.isoformat(),
            "data_source": "Node.js EOL Database"
        })
        
        try:
            eol_data = self._run_async_safely(self.nodejs_agent.get_eol_data(software_name, version))
            
            execution_duration = (datetime.utcnow() - tool_start_time).total_seconds()
            
            self._log_agent_action("NodeJSEOLSpecialist", "eol_check_complete", {
                "tool": "check_nodejs_eol",
                "software_name": software_name,
                "version": version,
                "duration_seconds": execution_duration,
                "data_found": bool(eol_data),
                "full_data": eol_data  # Include full data for extraction
            })
            
            if eol_data:
                self._log_agent_action("NodeJSEOLSpecialist", "eol_data_processing", {
                    "software_name": software_name,
                    "data_type": type(eol_data).__name__,
                    "processing_action": "formatting_for_agents"
                })
                
                formatted_result = self._format_eol_data_for_agents("Node.js", software_name, eol_data)
                
                self._log_agent_action("NodeJSEOLSpecialist", "eol_check_success", {
                    "software_name": software_name,
                    "version": version,
                    "result_length": len(formatted_result),
                    "duration_seconds": execution_duration,
                    "status": "success"
                })
                
                return formatted_result
            else:
                no_data_msg = f"No Node.js EOL data found for {software_name}"
                self._log_agent_action("NodeJSEOLSpecialist", "eol_check_no_data", {
                    "software_name": software_name,
                    "version": version,
                    "duration_seconds": execution_duration,
                    "status": "no_data_found"
                })
                return no_data_msg
                
        except Exception as e:
            execution_duration = (datetime.utcnow() - tool_start_time).total_seconds()
            error_msg = f"Error checking Node.js EOL: {str(e)}"
            logger.error(f"Node.js EOL tool exception after {execution_duration:.2f}s: {error_msg}")
            
            self._log_agent_action("NodeJSEOLSpecialist", "eol_check_exception", {
                "tool": "check_nodejs_eol",
                "software_name": software_name,
                "version": version,
                "error": str(e),
                "duration_seconds": execution_duration,
                "error_type": "exception"
            })
            
            return error_msg
    
    def _check_postgresql_eol_tool(self, software_name: str, version: str = None) -> str:
        """Tool for checking PostgreSQL EOL status"""
        tool_start_time = datetime.utcnow()
        
        self._log_agent_action("PostgreSQLEOLSpecialist", "eol_check_start", {
            "tool": "check_postgresql_eol",
            "software_name": software_name,
            "version": version,
            "start_time": tool_start_time.isoformat(),
            "data_source": "PostgreSQL official EOL data"
        })
        
        try:
            eol_data = self._run_async_safely(self.postgresql_agent.get_eol_data(software_name, version))
            
            execution_duration = (datetime.utcnow() - tool_start_time).total_seconds()
            
            self._log_agent_action("PostgreSQLEOLSpecialist", "eol_check_complete", {
                "tool": "check_postgresql_eol",
                "software_name": software_name,
                "version": version,
                "duration_seconds": execution_duration,
                "data_found": bool(eol_data),
                "full_data": eol_data  # Include full data for extraction
            })
            
            if eol_data:
                self._log_agent_action("PostgreSQLEOLSpecialist", "eol_data_processing", {
                    "software_name": software_name,
                    "version": version,
                    "data_type": type(eol_data).__name__,
                    "processing_action": "formatting_for_agents"
                })
                
                formatted_result = self._format_eol_data_for_agents("PostgreSQL", software_name, eol_data)
                
                self._log_agent_action("PostgreSQLEOLSpecialist", "eol_check_success", {
                    "software_name": software_name,
                    "version": version,
                    "result_length": len(formatted_result),
                    "duration_seconds": execution_duration,
                    "status": "success"
                })
                
                return formatted_result
            else:
                no_data_msg = f"No PostgreSQL EOL data found for {software_name}"
                self._log_agent_action("PostgreSQLEOLSpecialist", "eol_check_no_data", {
                    "software_name": software_name,
                    "version": version,
                    "duration_seconds": execution_duration,
                    "status": "no_data_found"
                })
                return no_data_msg
                
        except Exception as e:
            execution_duration = (datetime.utcnow() - tool_start_time).total_seconds()
            error_msg = f"Error checking PostgreSQL EOL: {str(e)}"
            logger.error(f"PostgreSQL EOL tool exception after {execution_duration:.2f}s: {error_msg}")
            
            self._log_agent_action("PostgreSQLEOLSpecialist", "eol_check_exception", {
                "tool": "check_postgresql_eol",
                "software_name": software_name,
                "version": version,
                "error": str(e),
                "duration_seconds": execution_duration,
                "error_type": "exception"
            })
            
            return error_msg
    
    def _check_php_eol_tool(self, software_name: str, version: str = None) -> str:
        """Tool for checking PHP EOL status"""
        tool_start_time = datetime.utcnow()
        
        self._log_agent_action("PHPEOLSpecialist", "eol_check_start", {
            "tool": "check_php_eol",
            "software_name": software_name,
            "version": version,
            "start_time": tool_start_time.isoformat(),
            "data_source": "PHP official EOL data"
        })
        
        try:
            eol_data = self._run_async_safely(self.php_agent.get_eol_data(software_name, version))
            
            execution_duration = (datetime.utcnow() - tool_start_time).total_seconds()
            
            self._log_agent_action("PHPEOLSpecialist", "eol_check_complete", {
                "tool": "check_php_eol",
                "software_name": software_name,
                "version": version,
                "duration_seconds": execution_duration,
                "data_found": bool(eol_data),
                "full_data": eol_data  # Include full data for extraction
            })
            
            if eol_data:
                self._log_agent_action("PHPEOLSpecialist", "eol_data_processing", {
                    "software_name": software_name,
                    "version": version,
                    "data_type": type(eol_data).__name__,
                    "processing_action": "formatting_for_agents"
                })
                
                formatted_result = self._format_eol_data_for_agents("PHP", software_name, eol_data)
                
                self._log_agent_action("PHPEOLSpecialist", "eol_check_success", {
                    "software_name": software_name,
                    "version": version,
                    "result_length": len(formatted_result),
                    "duration_seconds": execution_duration,
                    "status": "success"
                })
                
                return formatted_result
            else:
                no_data_msg = f"No PHP EOL data found for {software_name}"
                self._log_agent_action("PHPEOLSpecialist", "eol_check_no_data", {
                    "software_name": software_name,
                    "version": version,
                    "duration_seconds": execution_duration,
                    "status": "no_data_found"
                })
                return no_data_msg
                
        except Exception as e:
            execution_duration = (datetime.utcnow() - tool_start_time).total_seconds()
            error_msg = f"Error checking PHP EOL: {str(e)}"
            logger.error(f"PHP EOL tool exception after {execution_duration:.2f}s: {error_msg}")
            
            self._log_agent_action("PHPEOLSpecialist", "eol_check_exception", {
                "tool": "check_php_eol",
                "software_name": software_name,
                "version": version,
                "error": str(e),
                "duration_seconds": execution_duration,
                "error_type": "exception"
            })
            
            return error_msg
    
    def _check_python_eol_tool(self, software_name: str, version: str = None) -> str:
        """Tool for checking Python EOL status"""
        tool_start_time = datetime.utcnow()
        
        self._log_agent_action("PythonEOLSpecialist", "eol_check_start", {
            "tool": "check_python_eol",
            "software_name": software_name,
            "version": version,
            "start_time": tool_start_time.isoformat(),
            "data_source": "Python official EOL data"
        })
        
        try:
            eol_data = self._run_async_safely(self.python_agent.get_eol_data(software_name, version))
            
            execution_duration = (datetime.utcnow() - tool_start_time).total_seconds()
            
            self._log_agent_action("PythonEOLSpecialist", "eol_check_complete", {
                "tool": "check_python_eol",
                "software_name": software_name,
                "version": version,
                "duration_seconds": execution_duration,
                "data_found": bool(eol_data),
                "full_data": eol_data  # Include full data for extraction
            })
            
            if eol_data:
                self._log_agent_action("PythonEOLSpecialist", "eol_data_processing", {
                    "software_name": software_name,
                    "version": version,
                    "data_type": type(eol_data).__name__,
                    "processing_action": "formatting_for_agents"
                })
                
                formatted_result = self._format_eol_data_for_agents("Python", software_name, eol_data)
                
                self._log_agent_action("PythonEOLSpecialist", "eol_check_success", {
                    "software_name": software_name,
                    "version": version,
                    "result_length": len(formatted_result),
                    "duration_seconds": execution_duration,
                    "status": "success"
                })
                
                return formatted_result
            else:
                no_data_msg = f"No Python EOL data found for {software_name}"
                self._log_agent_action("PythonEOLSpecialist", "eol_check_no_data", {
                    "software_name": software_name,
                    "version": version,
                    "duration_seconds": execution_duration,
                    "status": "no_data_found"
                })
                return no_data_msg
                
        except Exception as e:
            execution_duration = (datetime.utcnow() - tool_start_time).total_seconds()
            error_msg = f"Error checking Python EOL: {str(e)}"
            logger.error(f"Python EOL tool exception after {execution_duration:.2f}s: {error_msg}")
            
            self._log_agent_action("PythonEOLSpecialist", "eol_check_exception", {
                "tool": "check_python_eol",
                "software_name": software_name,
                "version": version,
                "error": str(e),
                "duration_seconds": execution_duration,
                "error_type": "exception"
            })
            
            return error_msg
    
    def _get_inventory_summary_tool(self) -> str:
        """Tool for getting inventory summary from the coordination agent"""
        try:
            self._log_agent_action("InventorySpecialist", "get_inventory_summary", {})
            
            # Use the helper method to safely run async code
            summary = self._run_async_safely(self.inventory_agent.get_inventory_summary())
            
            if summary:
                self._log_agent_action("InventorySpecialist", "get_inventory_summary_result", 
                                     {"summary_count": len(summary.get('software', []))})
                return str(summary)
            else:
                return "No inventory summary available"
                
        except Exception as e:
            error_msg = f"Error getting inventory summary: {str(e)}"
            self._log_agent_action("InventorySpecialist", "get_inventory_summary_error", {"error": error_msg})
            return error_msg
    
    def _check_endoflife_eol_tool(self, software_name: str, version: str = None) -> str:
        """Tool for checking general software EOL using endoflife.date database"""
        tool_start_time = datetime.utcnow()
        
        self._log_agent_action("EndOfLifeSpecialist", "eol_check_start", {
            "tool": "check_endoflife_eol",
            "software_name": software_name,
            "version": version,
            "start_time": tool_start_time.isoformat(),
            "data_source": "EndOfLife.date API"
        })
        
        try:
            # Use the helper method to safely run async code
            eol_data = self._run_async_safely(self.endoflife_agent.get_eol_data(software_name, version))
            
            execution_duration = (datetime.utcnow() - tool_start_time).total_seconds()
            
            self._log_agent_action("EndOfLifeSpecialist", "eol_check_complete", {
                "tool": "check_endoflife_eol",
                "software_name": software_name,
                "version": version,
                "duration_seconds": execution_duration,
                "data_found": bool(eol_data),
                "full_data": eol_data  # Include full data for extraction
            })
            
            if eol_data:
                self._log_agent_action("EndOfLifeSpecialist", "eol_data_processing", {
                    "software_name": software_name,
                    "data_type": type(eol_data).__name__,
                    "processing_action": "formatting_for_agents"
                })
                
                formatted_result = self._format_eol_data_for_agents("EndOfLife.date", software_name, eol_data)
                
                self._log_agent_action("EndOfLifeSpecialist", "eol_check_success", {
                    "software_name": software_name,
                    "version": version,
                    "result_length": len(formatted_result),
                    "duration_seconds": execution_duration,
                    "status": "success"
                })
                
                return formatted_result
            else:
                no_data_msg = f"No EOL data found for {software_name} in endoflife.date database"
                self._log_agent_action("EndOfLifeSpecialist", "eol_check_no_data", {
                    "software_name": software_name,
                    "version": version,
                    "duration_seconds": execution_duration,
                    "status": "no_data_found"
                })
                return no_data_msg
                
        except Exception as e:
            execution_duration = (datetime.utcnow() - tool_start_time).total_seconds()
            error_msg = f"Error checking endoflife EOL: {str(e)}"
            logger.error(f"EndOfLife EOL tool exception after {execution_duration:.2f}s: {error_msg}")
            
            self._log_agent_action("EndOfLifeSpecialist", "eol_check_exception", {
                "tool": "check_endoflife_eol",
                "software_name": software_name,
                "version": version,
                "error": str(e),
                "duration_seconds": execution_duration,
                "error_type": "exception"
            })
            
            return error_msg
    
    def _format_inventory_for_agents(self, inventory_items: List[Dict[str, Any]]) -> str:
        """Format inventory data for agent consumption"""
        formatted = ""
        for item in inventory_items:
            name = item.get('name', 'Unknown')
            version = item.get('version', 'Unknown')
            computer = item.get('computer', 'Unknown')
            formatted += f"• {name} v{version} (on {computer})\n"
        return formatted
    
    def _format_eol_data_for_agents(self, source: str, software_name: str, eol_data: Dict[str, Any]) -> str:
        """Format EOL data for agent consumption - supports both legacy and standardized formats"""
        result = f"**{source} EOL Analysis for {software_name}:**\n\n"
        
        # Handle standardized BaseEOLAgent format
        if isinstance(eol_data, dict) and "success" in eol_data:
            if eol_data["success"] and eol_data.get("data"):
                data = eol_data["data"]
                
                # Extract key information from standardized format
                if data.get("eol_date"):
                    result += f"🗓️ **End of Life Date:** {data['eol_date']}\n"
                
                if data.get("support_end_date"):
                    result += f"🛡️ **Support End Date:** {data['support_end_date']}\n"
                
                if data.get("release_date"):
                    result += f"📅 **Release Date:** {data['release_date']}\n"
                
                if data.get("version"):
                    result += f"🔄 **Version/Cycle:** {data['version']}\n"
                
                if data.get("status"):
                    result += f"📊 **Status:** {data['status']}\n"
                
                # Add risk level using standardized field
                if data.get("risk_level"):
                    risk_level = data["risk_level"].lower()
                    if risk_level == "critical":
                        result += "🚨 **Risk Level:** CRITICAL - Immediate attention required\n"
                    elif risk_level == "high":
                        result += "⚠️ **Risk Level:** HIGH - High priority update needed\n"
                    elif risk_level == "medium":
                        result += "⚡ **Risk Level:** MEDIUM - Update recommended\n"
                    elif risk_level == "low":
                        result += "✅ **Risk Level:** LOW - Currently supported\n"
                    else:
                        result += f"❓ **Risk Level:** {risk_level.upper()}\n"
                
                # Add days until EOL if available
                if data.get("days_until_eol") is not None:
                    days = data["days_until_eol"]
                    if days < 0:
                        result += f"⏰ **Days Since EOL:** {abs(days)} days ago\n"
                    else:
                        result += f"⏰ **Days Until EOL:** {days} days\n"
                
                # Add confidence level
                if data.get("confidence"):
                    confidence_pct = int(data["confidence"] * 100)
                    result += f"🎯 **Confidence:** {confidence_pct}%\n"
                
                # Add source URL if available
                if data.get("source_url"):
                    result += f"\n📖 **Source:** {data['source_url']}\n"
                elif eol_data.get("source"):
                    result += f"\n📖 **Source:** {eol_data['source']}\n"
                
                # Add additional data if present
                if data.get("cycle"):
                    result += f"🔄 **Release Cycle:** {data['cycle']}\n"
                if data.get("lts"):
                    result += f"🔒 **LTS Release:** {data['lts']}\n"
                if data.get("latest"):
                    result += f"📦 **Latest Version:** {data['latest']}\n"
                
            else:
                # Handle failure response
                error = eol_data.get("error", {})
                result += f"❌ **Error:** {error.get('message', 'No EOL data found')}\n"
                if error.get("code"):
                    result += f"🏷️ **Error Code:** {error['code']}\n"
            
            return result
        
        # Legacy format handling - keep existing logic for backward compatibility
        # Handle nested eol_info structure (Microsoft agent format)
        if "eol_info" in eol_data:
            eol_info = eol_data["eol_info"]
        else:
            eol_info = eol_data
        
        if eol_info.get("eol"):
            result += f"🗓️ **End of Life Date:** {eol_info['eol']}\n"
        
        if eol_info.get("support"):
            result += f"🛡️ **Support End Date:** {eol_info['support']}\n"
        
        if eol_info.get("latest"):
            result += f"📦 **Latest Version:** {eol_info['latest']}\n"
        
        if eol_info.get("lts"):
            result += f"🔒 **LTS Release:** {eol_info['lts']}\n"
        
        if eol_info.get("cycle"):
            result += f"🔄 **Release Cycle:** {eol_info['cycle']}\n"
        
        if eol_info.get("releaseDate"):
            result += f"📅 **Release Date:** {eol_info['releaseDate']}\n"
        
        # Calculate risk level for legacy format
        if eol_info.get("eol"):
            try:
                from datetime import datetime
                eol_date_str = str(eol_info["eol"])
                
                # Handle different date formats
                if eol_date_str.lower() in ["no eol", "continuous", "active"]:
                    result += "✅ **Risk Level:** LOW - No scheduled EOL (continuous updates)\n"
                else:
                    # Try to parse the date
                    try:
                        if "Z" in eol_date_str:
                            eol_date = datetime.fromisoformat(eol_date_str.replace("Z", "+00:00"))
                        else:
                            eol_date = datetime.fromisoformat(eol_date_str)
                    except:
                        # Try other date formats
                        eol_date = datetime.strptime(eol_date_str, '%Y-%m-%d')
                    
                    days_until_eol = (eol_date - datetime.now()).days
                    
                    if days_until_eol < 0:
                        result += "🚨 **Risk Level:** CRITICAL - Already past EOL\n"
                    elif days_until_eol < 90:
                        result += "⚠️ **Risk Level:** HIGH - EOL within 90 days\n"
                    elif days_until_eol < 365:
                        result += "⚡ **Risk Level:** MEDIUM - EOL within 1 year\n"
                    else:
                        result += "✅ **Risk Level:** LOW - EOL more than 1 year away\n"
                        
            except Exception as e:
                result += "❓ **Risk Level:** Unknown - Unable to parse EOL date\n"
        
        # Add source information for legacy format
        if eol_data.get("source_url"):
            result += f"\n📖 **Source:** {eol_data['source_url']}\n"
        elif eol_data.get("source"):
            result += f"\n📖 **Source:** {eol_data['source']}\n"
        
        return result
    
    def _get_dynamic_timeout(self, base_timeout: int, load_factor: float = 0.0) -> int:
        """
        Calculate dynamic timeout based on system load
        
        Args:
            base_timeout: Base timeout in seconds
            load_factor: System load factor (0.0 = low, 1.0 = high)
        
        Returns:
            Adjusted timeout in seconds
        """
        try:
            # Increase timeout under high load
            load_adjustment = 1.0 + (load_factor * 0.5)  # Up to 50% increase
            
            # Apply adjustment
            adjusted_timeout = int(base_timeout * load_adjustment)
            
            # Ensure reasonable bounds
            min_timeout = base_timeout
            max_timeout = base_timeout * 2  # Never more than double
            final_timeout = max(min_timeout, min(max_timeout, adjusted_timeout))
            
            self._log_agent_action("Orchestrator", "dynamic_timeout_calculation", {
                "base_timeout": base_timeout,
                "load_factor": load_factor,
                "load_adjustment": load_adjustment,
                "final_timeout": final_timeout,
                "increase_percent": round((final_timeout/base_timeout - 1) * 100, 1)
            })
            
            return final_timeout
            
        except Exception as e:
            logger.warning(f"Dynamic timeout calculation failed: {e}, using base timeout {base_timeout}")
            return base_timeout

    def _get_dynamic_limit(self, base_limit: int, load_factor: float = 0.0, environment: str = "production") -> int:
        """
        Calculate dynamic limits based on system load and environment
        
        Args:
            base_limit: Base limit value
            load_factor: System load factor (0.0 = low, 1.0 = high)
            environment: Environment type (development, staging, production)
        
        Returns:
            Adjusted limit value
        """
        try:
            # Environment multipliers
            env_multipliers = {
                "development": 0.5,  # Lower limits for dev
                "staging": 0.8,      # Moderate limits for staging
                "production": 1.0    # Full limits for production
            }
            
            # Load-based adjustment (reduce limits under high load)
            load_adjustment = 1.0 - (load_factor * 0.4)  # Max 40% reduction
            
            # Apply adjustments
            env_multiplier = env_multipliers.get(environment, 1.0)
            adjusted_limit = int(base_limit * env_multiplier * load_adjustment)
            
            # Ensure minimum limits
            min_limit = max(10, base_limit // 10)  # At least 10% of base
            final_limit = max(min_limit, adjusted_limit)
            
            self._log_agent_action("Orchestrator", "dynamic_limit_calculation", {
                "base_limit": base_limit,
                "load_factor": load_factor,
                "environment": environment,
                "env_multiplier": env_multiplier,
                "load_adjustment": load_adjustment,
                "final_limit": final_limit,
                "reduction_percent": round((1 - final_limit/base_limit) * 100, 1)
            })
            
            return final_limit
            
        except Exception as e:
            logger.warning(f"Dynamic limit calculation failed: {e}, using base limit {base_limit}")
            return base_limit

    def _get_system_load_factor(self) -> float:
        """
        Calculate system load factor based on various metrics
        
        Returns:
            Load factor between 0.0 (low) and 1.0 (high)
        """
        try:
            import psutil
            
            # CPU usage (weight: 0.4)
            cpu_percent = psutil.cpu_percent(interval=0.1)
            cpu_load = min(cpu_percent / 80.0, 1.0)  # 80% CPU = full load
            
            # Memory usage (weight: 0.3)
            memory = psutil.virtual_memory()
            memory_load = memory.percent / 100.0
            
            # Recent agent communications (weight: 0.3)
            recent_comms = len([c for c in self.agent_communications[-50:] 
                               if (datetime.utcnow() - datetime.fromisoformat(c.get("timestamp", "1970-01-01T00:00:00"))).seconds < 300])
            comm_load = min(recent_comms / 20.0, 1.0)  # 20 communications in 5 min = high
            
            # Weighted average
            load_factor = (cpu_load * 0.4) + (memory_load * 0.3) + (comm_load * 0.3)
            
            self._log_agent_action("Orchestrator", "system_load_assessment", {
                "cpu_percent": cpu_percent,
                "memory_percent": memory.percent,
                "recent_communications": recent_comms,
                "cpu_load": round(cpu_load, 3),
                "memory_load": round(memory_load, 3),
                "comm_load": round(comm_load, 3),
                "final_load_factor": round(load_factor, 3)
            })
            
            return min(load_factor, 1.0)
            
        except ImportError:
            # logger.debug("psutil not available, using default load factor")
            return 0.2  # Default moderate load
        except Exception as e:
            logger.warning(f"Load factor calculation failed: {e}, using default")
            return 0.2

    def _log_agent_action(self, agent_name: str, action: str, data: Dict[str, Any]):
        """Log agent actions for transparency in UI with enhanced task tracking"""
        log_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "session_id": self.session_id,
            "agent_name": agent_name,
            "action": action,
            "data": data,
            "task_type": self._determine_task_type(action, data),
            "status": self._determine_task_status(action, data)
        }
        
        self.agent_communications.append(log_entry)
        logger.info(f"🤖 {agent_name} -> {action}: {json.dumps(data, default=str)}")
    
    def _determine_task_type(self, action: str, data: Dict[str, Any]) -> str:
        """Determine the task type based on action and data"""
        try:
            if "inventory" in action.lower():
                return "inventory"
            elif "eol" in action.lower():
                return "eol_analysis"
            elif "tool" in action.lower():
                return "tool_execution"
            elif "team" in action.lower():
                return "team_management"
            elif "conversation" in action.lower() or "chat" in action.lower():
                return "conversation"
            else:
                return "system"
        except Exception:
            return "unknown"
    
    def _determine_task_status(self, action: str, data: Dict[str, Any]) -> str:
        """Determine the task status based on action and data"""
        try:
            if any(keyword in action.lower() for keyword in ["start", "begin", "init"]):
                return "started"
            elif any(keyword in action.lower() for keyword in ["complete", "success", "finish"]):
                return "completed"
            elif any(keyword in action.lower() for keyword in ["error", "fail", "exception"]):
                return "failed"
            elif "progress" in action.lower():
                return "in_progress"
            else:
                return "active"
        except Exception:
            return "unknown"
    
    def _extract_and_log_tasks_from_message(self, speaker: str, content: str, message: Any):
        """Extract task information from AutoGen messages and log them"""
        try:
            # Log the message itself as a task
            self._log_agent_action(speaker, "message_sent", {
                "content_length": len(content),
                "message_type": type(message).__name__
            })
            
            # Extract tool calls/function calls from content
            if "✅" in content or "❌" in content:
                # This looks like a tool result
                self._log_agent_action(speaker, "tool_result", {
                    "success": "✅" in content,
                    "has_data": len(content) > 100
                })
            
            # Check for specific task patterns
            if "inventory" in content.lower():
                task_type = "inventory_task"
                if "retrieved successfully" in content.lower():
                    self._log_agent_action(speaker, "inventory_completed", {
                        "task": "inventory_retrieval",
                        "status": "success"
                    })
                elif "error" in content.lower():
                    self._log_agent_action(speaker, "inventory_failed", {
                        "task": "inventory_retrieval", 
                        "status": "error"
                    })
                else:
                    self._log_agent_action(speaker, "inventory_requested", {
                        "task": "inventory_retrieval",
                        "status": "initiated"
                    })
            
            if "eol" in content.lower() or "end of life" in content.lower():
                if "analysis for" in content.lower():
                    self._log_agent_action(speaker, "eol_analysis_completed", {
                        "task": "eol_analysis",
                        "status": "success"
                    })
                else:
                    self._log_agent_action(speaker, "eol_analysis_requested", {
                        "task": "eol_analysis",
                        "status": "initiated"
                    })
            
            # Check for risk assessment
            if "risk" in content.lower() and ("high" in content.lower() or "medium" in content.lower() or "low" in content.lower()):
                self._log_agent_action(speaker, "risk_assessment_completed", {
                    "task": "risk_assessment",
                    "status": "completed"
                })
            
            # Check for recommendations
            if "recommend" in content.lower() or "should" in content.lower():
                self._log_agent_action(speaker, "recommendation_provided", {
                    "task": "recommendation",
                    "status": "completed"
                })
                
        except Exception as e:
            logger.error(f"Error extracting tasks from message: {e}")
    
    def _determine_task_type(self, action: str, data: Dict[str, Any]) -> str:
        """Determine the type of task being performed"""
        if "inventory" in action.lower():
            return "inventory_retrieval"
        elif "eol" in action.lower():
            return "eol_analysis"
        elif "tool" in action.lower() or "function" in action.lower():
            return "tool_execution"
        elif "message" in action.lower():
            return "communication"
        elif "error" in action.lower() or "exception" in action.lower():
            return "error_handling"
        elif "complete" in action.lower():
            return "task_completion"
        else:
            return "general_action"
    
    def _determine_task_status(self, action: str, data: Dict[str, Any]) -> str:
        """Determine the status of the task"""
        if "error" in action.lower() or "exception" in action.lower():
            return "failed"
        elif "complete" in action.lower() or "result" in action.lower():
            return "completed"
        elif data.get("success", True):  # Default to True if not specified
            return "in_progress"
        else:
            return "failed"
    
    async def _chat_with_retry(self, user_message: str, max_retries: int = 3, minimal_team: bool = False, timeout_seconds: int = 100) -> Dict[str, Any]:
        """
        Chat with automatic retry for rate limiting errors and timeout handling
        
        Args:
            user_message: The user's message
            max_retries: Maximum number of retry attempts
            minimal_team: Use minimal team for faster responses
            timeout_seconds: Maximum time for each attempt (default 50s)
        """
        chat_start_time = datetime.utcnow()
        # logger.debug(f"[CHAT_RETRY] Starting multi-agent conversation with {timeout_seconds}s timeout")
        
        self._log_agent_action("Orchestrator", "multi_agent_chat_start", {
            "max_retries": max_retries,
            "minimal_team": minimal_team,
            "timeout_seconds": timeout_seconds,
            "session_id": self.session_id,
            "start_time": chat_start_time.isoformat(),
            "strategy": "Minimal team for speed" if minimal_team else "Full team for comprehensive analysis"
        })
        
        for attempt in range(max_retries + 1):
            attempt_start_time = datetime.utcnow()
            # logger.debug(f"[CHAT_RETRY] Attempt {attempt + 1}/{max_retries + 1} - Setting up team chat (timeout: {timeout_seconds}s)")
            
            self._log_agent_action("Orchestrator", "chat_attempt_start", {
                "attempt": attempt + 1,
                "max_attempts": max_retries + 1,
                "minimal_team": minimal_team,
                "timeout_seconds": timeout_seconds,
                "attempt_start_time": attempt_start_time.isoformat(),
                "previous_failures": attempt > 0
            })
            
            try:
                # Create a fresh team instance for this conversation to avoid "team already running" errors
                # logger.debug(f"[CHAT_RETRY] Creating fresh team instance for new conversation (attempt {attempt + 1}, minimal_team={minimal_team})")
                self._setup_team_chat(minimal_team=minimal_team)
                
                if not self.team:
                    logger.error("[CHAT_RETRY] Failed to create team chat - AutoGen not available")
                    self._log_agent_action("Orchestrator", "team_creation_failed", {
                        "reason": "AutoGen not available",
                        "fallback": "Single-agent response required"
                    })
                    raise Exception("AutoGen team chat not available")
                
                # Create cancellation token for the conversation
                cancellation_token = CancellationToken()
                # logger.debug(f"[CHAT_RETRY] Created cancellation token, starting team conversation with {timeout_seconds}s timeout")
                
                self._log_agent_action("Orchestrator", "team_conversation_start", {
                    "team_type": type(self.team).__name__,
                    "participant_count": len(self.participants),
                    "participants": [agent.name for agent in self.participants]
                })
                
                # Run the team chat with timeout handling
                conversation_start = datetime.utcnow()
                # logger.debug(f"[CHAT_RETRY] Starting team.run() with {timeout_seconds}s timeout")
                
                try:
                    # Use asyncio.wait_for to enforce timeout
                    result = await asyncio.wait_for(
                        self.team.run(task=user_message, cancellation_token=cancellation_token),
                        timeout=timeout_seconds
                    )
                    conversation_duration = (datetime.utcnow() - conversation_start).total_seconds()
                    
                    # logger.debug(f"[CHAT_RETRY] Team conversation completed in {conversation_duration:.2f}s")
                    self._log_agent_action("Orchestrator", "team_conversation_complete", {
                        "duration_seconds": conversation_duration,
                        "message_count": len(result.messages) if hasattr(result, 'messages') else 0,
                        "termination_reason": getattr(result, 'termination_reason', 'unknown'),
                        "timeout_seconds": timeout_seconds,
                        "success": True
                    })
                    
                except asyncio.TimeoutError:
                    conversation_duration = (datetime.utcnow() - conversation_start).total_seconds()
                    # logger.error(f"[CHAT_RETRY] Team conversation timed out after {conversation_duration:.2f}s (limit: {timeout_seconds}s)")
                    
                    self._log_agent_action("Orchestrator", "team_conversation_timeout", {
                        "duration_seconds": conversation_duration,
                        "timeout_seconds": timeout_seconds,
                        "attempt": attempt + 1,
                        "action": "retrying_with_minimal_team" if not minimal_team else "timeout_exceeded"
                    })
                    
                    # If this was a full team and we timed out, try with minimal team
                    if not minimal_team and attempt < max_retries:
                        logger.info(f"[CHAT_RETRY] Retrying with minimal team due to timeout")
                        continue
                    else:
                        # Final timeout - return a graceful response
                        timeout_response = f"""⏱️ **Request Timeout**

The multi-agent analysis took longer than expected ({timeout_seconds} seconds). This can happen with complex queries that require extensive agent coordination.

**What you can try:**
• 🔄 **Retry your request** - sometimes it works faster on the second try
• 🏃 **Use simpler queries** like "show my inventory" for faster responses  
• 📊 **Try specific requests** like "what software do I have" or "show OS versions"

**Your original request:** {user_message[:200]}{'...' if len(user_message) > 200 else ''}"""

                        return {
                            "response": timeout_response,
                            "conversation_messages": [],
                            "agent_communications": self.agent_communications[-20:],
                            "session_id": self.session_id,
                            "agents_involved": [],
                            "total_exchanges": 0,
                            "timeout": True,
                            "timeout_seconds": timeout_seconds,
                            "duration_seconds": conversation_duration
                        }
                
                # Extract conversation messages from the result and capture task details
                # logger.debug(f"[CHAT_RETRY] Processing {len(result.messages)} messages from team conversation")
                self._log_agent_action("Orchestrator", "message_processing_start", {
                    "total_messages": len(result.messages),
                    "processing_start": datetime.utcnow().isoformat()
                })
                
                conversation_messages = []
                agents_involved = set()
                message_types = {}
                agent_message_counts = {}
                
                for i, message in enumerate(result.messages):
                    try:
                        speaker = getattr(message, 'source', 'Unknown')
                        content = ""
                        
                        # Handle different message types
                        if hasattr(message, 'content'):
                            content = str(message.content)
                        elif hasattr(message, 'to_text'):
                            content = message.to_text()
                        else:
                            content = str(message)
                        
                        message_type = type(message).__name__
                        
                        # Track message statistics
                        agents_involved.add(speaker)
                        agent_message_counts[speaker] = agent_message_counts.get(speaker, 0) + 1
                        message_types[message_type] = message_types.get(message_type, 0) + 1
                        
                        # logger.debug(f"[CHAT_RETRY] Message {i+1}: {speaker} ({message_type})")
                        
                        # Capture task information from message content
                        self._extract_and_log_tasks_from_message(speaker, content, message)
                        
                        conversation_messages.append({
                            "speaker": speaker,
                            "content": content,
                            "timestamp": datetime.utcnow().isoformat(),
                            "message_type": message_type,
                            "sequence": i + 1
                        })
                        
                    except Exception as e:
                        # logger.debug(f"[CHAT_RETRY] Error processing message {i+1}: {e}")
                        conversation_messages.append({
                            "speaker": "System",
                            "content": f"Error processing message: {str(e)}",
                            "timestamp": datetime.utcnow().isoformat(),
                            "message_type": "Error",
                            "sequence": i + 1
                        })
                
                self._log_agent_action("Orchestrator", "message_processing_complete", {
                    "processed_messages": len(conversation_messages),
                    "agents_involved": list(agents_involved),
                    "agent_message_counts": agent_message_counts,
                    "message_types": message_types,
                    "most_active_agent": max(agent_message_counts.items(), key=lambda x: x[1])[0] if agent_message_counts else None
                })
                
                # Get the final response (last message from an agent)
                # logger.debug("[CHAT_RETRY] Extracting final response from conversation")
                final_response = "I apologize, but I couldn't process your request."
                inventory_complete = False
                final_agent = None
                
                for message in reversed(conversation_messages):
                    if message["speaker"] not in ["User", "System"]:
                        final_response = message["content"]
                        final_agent = message["speaker"]
                        
                        # Check if inventory specialist completed its work
                        if "INVENTORY_COMPLETE" in final_response:
                            inventory_complete = True
                            # Remove the INVENTORY_COMPLETE marker from the response
                            final_response = final_response.replace("INVENTORY_COMPLETE", "").strip()
                            # logger.debug("[CHAT_RETRY] INVENTORY_COMPLETE marker detected - inventory task finished")
                        
                        break
                
                self._log_agent_action("Orchestrator", "final_response_extracted", {
                    "final_agent": final_agent,
                    "response_length": len(final_response),
                    "inventory_complete": inventory_complete,
                    "response_preview": final_response[:200] + "..." if len(final_response) > 200 else final_response
                })
                
                # If inventory was completed, ensure no further agent collaboration
                if inventory_complete:
                    # logger.debug("[CHAT_RETRY] Processing inventory completion - filtering messages")
                    self._log_agent_action("Orchestrator", "inventory_completion_processing", {
                        "action": "Filtering conversation to prevent unnecessary agent collaboration",
                        "original_message_count": len(conversation_messages)
                    })
                    
                    # Filter out any potential follow-up attempts from other agents
                    filtered_messages = []
                    inventory_done = False
                    for message in conversation_messages:
                        if message["speaker"] == "InventorySpecialist" and "INVENTORY_COMPLETE" in message["content"]:
                            inventory_done = True
                            # Clean the message content
                            message["content"] = message["content"].replace("INVENTORY_COMPLETE", "").strip()
                            filtered_messages.append(message)
                            break  # Stop processing after inventory specialist responds
                        elif not inventory_done:
                            filtered_messages.append(message)
                    
                    conversation_messages = filtered_messages
                    
                    self._log_agent_action("Orchestrator", "inventory_completion_filtered", {
                        "filtered_message_count": len(conversation_messages),
                        "messages_removed": len(result.messages) - len(conversation_messages),
                        "termination_reason": "inventory_complete"
                    })
                
                # Calculate final metrics
                total_duration = (datetime.utcnow() - chat_start_time).total_seconds()
                attempt_duration = (datetime.utcnow() - attempt_start_time).total_seconds()
                
                # Prepare response with full transparency
                response = {
                    "response": final_response,
                    "conversation_messages": conversation_messages,
                    "agent_communications": self.agent_communications[-20:],  # Last 20 actions
                    "session_id": self.session_id,
                    "agents_involved": list(agents_involved),
                    "total_exchanges": len(conversation_messages),
                    "termination_reason": getattr(result, 'termination_reason', 'completed'),
                    "retry_attempt": attempt + 1,
                    "total_duration_seconds": total_duration,
                    "attempt_duration_seconds": attempt_duration,
                    "final_agent": final_agent,
                    "inventory_complete": inventory_complete
                }
                
                # logger.debug(f"[CHAT_RETRY] Chat completed successfully in {total_duration:.2f}s")
                self._log_agent_action("Orchestrator", "chat_success", {
                    "success": True,
                    "total_duration_seconds": total_duration,
                    "attempt_duration_seconds": attempt_duration,
                    "agents_involved": response["agents_involved"],
                    "total_exchanges": response["total_exchanges"],
                    "termination_reason": response["termination_reason"],
                    "retry_attempt": attempt + 1,
                    "final_agent": final_agent,
                    "response_length": len(final_response),
                    "efficiency_metrics": {
                        "messages_per_second": len(conversation_messages) / attempt_duration if attempt_duration > 0 else 0,
                        "chars_per_second": len(final_response) / attempt_duration if attempt_duration > 0 else 0,
                        "team_type": "minimal" if minimal_team else "full"
                    }
                })
                
                return response
                
            except Exception as e:
                error_msg = str(e)
                attempt_duration = (datetime.utcnow() - attempt_start_time).total_seconds()
                
                # logger.debug(f"[CHAT_RETRY] Chat attempt {attempt + 1} failed after {attempt_duration:.2f}s: {error_msg}")
                
                # Determine error type and appropriate handling
                is_rate_limit_error = (
                    "429" in error_msg or 
                    "Rate limit" in error_msg or 
                    "rate limit" in error_msg or
                    "Too Many Requests" in error_msg or
                    "quota" in error_msg.lower()
                )
                
                is_network_error = (
                    "connection" in error_msg.lower() or
                    "timeout" in error_msg.lower() or
                    "network" in error_msg.lower()
                )
                
                is_auth_error = (
                    "401" in error_msg or
                    "403" in error_msg or
                    "unauthorized" in error_msg.lower() or
                    "authentication" in error_msg.lower()
                )
                
                error_category = "unknown"
                if is_rate_limit_error:
                    error_category = "rate_limit"
                elif is_network_error:
                    error_category = "network"
                elif is_auth_error:
                    error_category = "authentication"
                else:
                    error_category = "system"
                
                self._log_agent_action("Orchestrator", "chat_attempt_failed", {
                    "attempt": attempt + 1,
                    "max_attempts": max_retries + 1,
                    "error_message": error_msg,
                    "error_category": error_category,
                    "attempt_duration_seconds": attempt_duration,
                    "is_retryable": is_rate_limit_error or is_network_error,
                    "retries_remaining": max_retries - attempt
                })
                
                if (is_rate_limit_error or is_network_error) and attempt < max_retries:
                    # Calculate exponential backoff delay
                    base_delay = 10 if is_rate_limit_error else 5
                    delay = min(60, (2 ** attempt) * base_delay)  # Rate limit: 10s, 20s, 40s, max 60s
                    
                    # logger.debug(f"[CHAT_RETRY] {error_category.title()} error detected, waiting {delay}s before retry {attempt + 2}/{max_retries + 1}")
                    
                    self._log_agent_action("Orchestrator", "retry_with_backoff", {
                        "error_category": error_category,
                        "attempt": attempt + 1,
                        "delay_seconds": delay,
                        "next_attempt": attempt + 2,
                        "retry_strategy": "exponential_backoff",
                        "base_delay": base_delay
                    })
                    
                    await asyncio.sleep(delay)
                    continue
                else:
                    # Not a retryable error or max retries exceeded
                    total_duration = (datetime.utcnow() - chat_start_time).total_seconds()
                    
                    self._log_agent_action("Orchestrator", "chat_failed_permanently", {
                        "final_error": error_msg,
                        "error_category": error_category,
                        "total_attempts": attempt + 1,
                        "total_duration_seconds": total_duration,
                        "retries_exhausted": attempt >= max_retries,
                        "non_retryable_error": not (is_rate_limit_error or is_network_error)
                    })
                    
                    logger.error(f"[CHAT_RETRY] Permanent failure after {attempt + 1} attempts in {total_duration:.2f}s")
                    raise e
        
        # If we get here, all retries were exhausted due to retryable errors
        total_duration = (datetime.utcnow() - chat_start_time).total_seconds()
        self._log_agent_action("Orchestrator", "chat_retries_exhausted", {
            "total_attempts": max_retries + 1,
            "total_duration_seconds": total_duration,
            "failure_reason": "All retry attempts exhausted",
            "recommendation": "Try again later or contact support"
        })
        
        raise Exception(f"All {max_retries + 1} attempts failed due to retryable errors (rate limiting, network issues)")

    async def chat_with_confirmation(self, user_message: str, confirmed: bool = False, original_message: str = None, timeout_seconds: int = 120) -> Dict[str, Any]:
        """
        Enhanced chat interface with user confirmation for complex multi-agent requests
        
        Args:
            user_message: The user's message
            confirmed: Whether the user has confirmed to proceed with multi-agent analysis
            original_message: The original message if this is a confirmation response
            timeout_seconds: Maximum time for the conversation
        """
        try:
            # FAST PATH: Check if AutoGen is not available and handle simple queries directly
            if not AUTOGEN_IMPORTS_OK:
                # logger.info(f"🚀 FAST PATH: AutoGen not available, handling simple query directly")
                request_type = self._classify_request(user_message)
                if request_type == "PURE_INVENTORY":
                    return await self._fallback_inventory_response(user_message)
                elif request_type == "EOL_ANALYSIS":
                    return await self._fallback_eol_response(user_message)
            
            # Clear agent communications for fresh interaction tracking (except for confirmations)
            if not confirmed:
                # logger.info(f"🧹 CHAT START | Clearing communications for new conversation - User: {user_message[:50]}{'...' if len(user_message) > 50 else ''}")
                await self.clear_communications()
            
            # If this is a confirmation response and user confirmed, use the original message
            if confirmed and original_message:
                user_message = original_message
                self._log_agent_action("User", "confirmed_proceeding", {})
                # Proceed directly to multi-agent conversation (skip confirmation logic)
                return await self._proceed_with_multi_agent_chat(user_message, timeout_seconds=timeout_seconds)
            
            # If user explicitly declined, provide helpful alternatives
            confirmation_decline_keywords = ["no", "cancel", "stop", "don't proceed", "skip"]
            if any(keyword in user_message.lower() for keyword in confirmation_decline_keywords):
                decline_message = """✅ **Request Cancelled**

No problem! Here are some alternatives you can try:

🔍 **Quick Inventory Queries** (no multi-agent analysis):
- "Show me my software inventory"
- "Get OS inventory"  
- "List software" 

📊 **Specific Information**:
- "What is [software name] EOL date?"
- "Check Windows Server versions"

💡 **Tip**: For simple data retrieval, use "inventory" requests which are much faster and don't require multi-agent coordination.

What would you like to do instead?"""
                
                self._log_agent_action("User", "confirmation_declined", {})
                
                return {
                    "response": decline_message,
                    "conversation_messages": [
                        {
                            "speaker": "user",
                            "content": user_message,
                            "timestamp": datetime.utcnow().isoformat(),
                            "message_type": "UserMessage"
                        },
                        {
                            "speaker": "Orchestrator",
                            "content": decline_message,
                            "timestamp": datetime.utcnow().isoformat(),
                            "message_type": "AssistantMessage"
                        }
                    ],
                    "agent_communications": self.agent_communications[-20:],
                    "session_id": self.session_id,
                    "agents_involved": ["Orchestrator"],
                    "total_exchanges": 2,
                    "confirmation_declined": True
                }
            
            # Proceed with normal chat logic (which includes confirmation checks)
            return await self.chat(user_message)
            
        except Exception as e:
            error_msg = f"Error in confirmation chat: {str(e)}"
            # logger.debug(f"[DEBUG] Confirmation chat error: {error_msg}")
            
            return {
                "response": "I encountered an error processing your confirmation. Please try again.",
                "error": error_msg,
                "agent_communications": self.agent_communications[-20:],
                "session_id": self.session_id,
                "conversation_messages": [],
                "agents_involved": [],
                "total_exchanges": 0
            }
    
    async def _proceed_with_inventory_only_chat(self, user_message: str, timeout_seconds: int = 60) -> Dict[str, Any]:
        """
        Handle pure inventory requests using inventory specialists only.
        This prevents EOL agents from being unnecessarily involved in simple inventory requests.
        """
        try:
            self._log_agent_action("Orchestrator", "inventory_only_start", {
                "message": user_message[:100],
                "timeout": timeout_seconds,
                "approach": "inventory_specialists_only"
            })

            # Create inventory-only team
            inventory_specialists = [
                self.inventory_specialist,
                self.os_inventory_specialist,
                self.software_inventory_specialist
            ]
            
            # Filter out None agents
            available_specialists = [agent for agent in inventory_specialists if agent is not None]
            
            if not available_specialists or not AUTOGEN_IMPORTS_OK:
                # Fallback to direct inventory call
                return await self._fallback_inventory_response(user_message)
            
            # Create temporary inventory team
            text_termination = TextMentionTermination("TERMINATE") | TextMentionTermination("INVENTORY_COMPLETE")
            max_messages_termination = MaxMessageTermination(max_messages=8)
            termination = text_termination | max_messages_termination
            
            try:
                inventory_team = SelectorGroupChat(
                    participants=available_specialists,
                    model_client=self.model_client,
                    termination_condition=termination
                )
            except Exception as e:
                # Fallback to RoundRobinGroupChat if SelectorGroupChat is not available
                logger.warning(f"SelectorGroupChat not available for inventory team, falling back to RoundRobinGroupChat: {e}")
                inventory_team = RoundRobinGroupChat(
                    participants=available_specialists,
                    termination_condition=termination
                )
            
            # Run the inventory-focused conversation
            message = TextMessage(content=user_message, source="user")
            
            conversation_start = time.time()
            result = await asyncio.wait_for(
                inventory_team.run(task=message),
                timeout=timeout_seconds
            )
            conversation_duration = time.time() - conversation_start
            
            self._log_agent_action("Orchestrator", "inventory_only_complete", {
                "duration": conversation_duration,
                "specialists_used": len(available_specialists),
                "approach": "inventory_focused_team"
            })
            
            return self._process_inventory_team_result(result, user_message)
            
        except asyncio.TimeoutError:
            return self._create_timeout_response(user_message, timeout_seconds)
        except Exception as e:
            logger.error(f"Inventory-only chat error: {e}")
            return await self._fallback_inventory_response(user_message)
    
    async def _proceed_with_simple_eol_query(self, user_message: str, timeout_seconds: int = 60) -> Dict[str, Any]:
        """
        Handle simple EOL date/info queries without full analysis.
        Uses direct EOL tool calls for quick responses.
        """
        try:
            self._log_agent_action("Orchestrator", "simple_eol_start", {
                "message": user_message[:100],
                "timeout": timeout_seconds,
                "approach": "direct_eol_lookup"
            })

            # Extract software names from the query
            software_names = await self._extract_software_names_from_query(user_message)
            
            if not software_names:
                return {
                    "response": "I couldn't identify specific software in your query. Please specify which software you'd like EOL information for (e.g., 'What is the EOL date for Windows Server 2025?').",
                    "conversation_messages": [{"speaker": "EOLSpecialist", "message": "Please specify software name for EOL lookup"}],
                    "agent_communications": [],
                    "session_id": self.session_id,
                    "agents_involved": ["EOLSpecialist"],
                    "total_exchanges": 1,
                    "approach": "simple_eol_query"
                }
            
            # Perform direct EOL lookups using appropriate product specialists
            eol_results = []
            agents_used = []
            
            for software_item in software_names[:3]:  # Limit to 3 software items for performance
                software_name = software_item.get('name', software_item) if isinstance(software_item, dict) else software_item
                version = software_item.get('version', '') if isinstance(software_item, dict) else ''
                specialist_type = software_item.get('specialist', 'endoflife') if isinstance(software_item, dict) else self._determine_eol_specialist(software_name)
                
                logger.info(f"🎯 DIRECT EOL LOOKUP | Software: {software_name} | Version: {version} | Specialist: {specialist_type}")
                
                # Route to appropriate specialist tool
                eol_result = None
                specialist_name = "Unknown"
                
                try:
                    if specialist_type == "microsoft":
                        eol_result = self._check_microsoft_eol_tool(software_name, version)
                        specialist_name = "MicrosoftEOLSpecialist"
                    elif specialist_type == "ubuntu":
                        eol_result = self._check_ubuntu_eol_tool(software_name, version)
                        specialist_name = "UbuntuEOLSpecialist"
                    elif specialist_type == "oracle":
                        eol_result = self._check_oracle_eol_tool(software_name, version)
                        specialist_name = "OracleEOLSpecialist"
                    elif specialist_type == "redhat":
                        eol_result = self._check_redhat_eol_tool(software_name, version)
                        specialist_name = "RedHatEOLSpecialist"
                    elif specialist_type == "vmware":
                        eol_result = self._check_vmware_eol_tool(software_name, version)
                        specialist_name = "VMwareEOLSpecialist"
                    elif specialist_type == "apache":
                        eol_result = self._check_apache_eol_tool(software_name, version)
                        specialist_name = "ApacheEOLSpecialist"
                    elif specialist_type == "nodejs":
                        eol_result = self._check_nodejs_eol_tool(software_name, version)
                        specialist_name = "NodeJSEOLSpecialist"
                    elif specialist_type == "postgresql":
                        eol_result = self._check_postgresql_eol_tool(software_name, version)
                        specialist_name = "PostgreSQLEOLSpecialist"
                    elif specialist_type == "php":
                        eol_result = self._check_php_eol_tool(software_name, version)
                        specialist_name = "PHPEOLSpecialist"
                    elif specialist_type == "python":
                        eol_result = self._check_python_eol_tool(software_name, version)
                        specialist_name = "PythonEOLSpecialist"
                    else:
                        # Fallback to EndOfLife.date
                        eol_result = self._check_endoflife_eol_tool(software_name, version)
                        specialist_name = "EndOfLifeSpecialist"
                    
                    if eol_result and "No EOL data found" not in eol_result and "Error" not in eol_result:
                        eol_results.append({
                            "software": software_name,
                            "version": version,
                            "specialist": specialist_name,
                            "result": eol_result
                        })
                        
                        if specialist_name not in agents_used:
                            agents_used.append(specialist_name)
                        
                        logger.info(f"✅ EOL DATA FOUND | Software: {software_name} | Specialist: {specialist_name}")
                    else:
                        logger.info(f"❌ NO EOL DATA | Software: {software_name} | Specialist: {specialist_name}")
                        
                except Exception as tool_error:
                    logger.error(f"EOL tool error for {software_name}: {tool_error}")

            # Format simple response
            if eol_results:
                response = "Here are the EOL details you requested:\n\n"
                for item in eol_results:
                    version_info = f" (Version: {item['version']})" if item['version'] else ""
                    response += f"**{item['software']}{version_info}** (via {item['specialist']}):\n{item['result']}\n\n"
            else:
                software_list = [item.get('name', item) if isinstance(item, dict) else item for item in software_names]
                response = f"I couldn't find EOL information for the specified software: {', '.join(software_list)}. The product specialists I consulted didn't have data for these items."

            self._log_agent_action("Orchestrator", "simple_eol_complete", {
                "software_count": len(software_names),
                "results_found": len(eol_results),
                "specialists_used": agents_used,
                "approach": "direct_specialist_lookup"
            })
            
            return {
                "response": response,
                "conversation_messages": [{"speaker": "ProductEOLSpecialist", "message": response}],
                "agent_communications": self.agent_communications[-10:],
                "session_id": self.session_id,
                "agents_involved": agents_used if agents_used else ["ProductEOLSpecialist"],
                "total_exchanges": 1,
                "approach": "simple_eol_query"
            }
            
        except Exception as e:
            logger.error(f"Simple EOL query error: {e}")
            return {
                "response": f"I encountered an error while looking up EOL information. Please try again or request a full EOL analysis.",
                "conversation_messages": [{"speaker": "EOLAssistant", "message": "EOL lookup error"}],
                "agent_communications": [],
                "session_id": self.session_id,
                "agents_involved": ["EOLAssistant"],
                "total_exchanges": 1,
                "error": str(e)
            }

    async def _extract_software_names_from_query(self, query: str) -> List[Dict[str, str]]:
        """Use LLM to intelligently extract software names, versions and determine specialists from query.
        
        Returns list of dictionaries with:
        - 'name': Software name
        - 'version': Version if detected
        - 'specialist': Appropriate specialist type
        - 'confidence': Confidence score (high/medium/low)
        """
        try:
            return await self._llm_extract_software_info(query)
        except Exception as e:
            logger.warning(f"LLM software extraction failed: {e}, falling back to pattern matching")
            return self._fallback_pattern_extraction(query)

    async def _llm_extract_software_info(self, query: str) -> List[Dict[str, str]]:
        """Use LLM to extract software information from query"""
        extraction_prompt = f"""
You are an expert software analyst. Extract software/product information from this user query.

For each software/product mentioned, provide:
- name: Standardized product name
- version: Specific version if mentioned (or "latest" if asking about current/newest)  
- specialist: Which specialist should handle this (from list below)
- confidence: high/medium/low based on query clarity

SPECIALIST MAPPING:
- microsoft: Windows, Office, SQL Server, Azure, Exchange, SharePoint, .NET, Visual Studio
- ubuntu: Ubuntu Linux (all versions)
- redhat: RHEL, CentOS, Fedora, Red Hat products
- oracle: Oracle Database, Oracle products, Java (Oracle-owned)
- python: Python language and packages
- nodejs: Node.js, npm packages
- php: PHP language and frameworks  
- postgresql: PostgreSQL database
- apache: Apache HTTP Server, Tomcat, other Apache projects
- vmware: VMware products (ESXi, vCenter, Workstation)
- endoflife: Generic/other products not covered above

USER QUERY: "{query}"

Respond in JSON format ONLY:
[{{"name": "Product Name", "version": "X.X", "specialist": "specialist_type", "confidence": "high"}}]

If no software is clearly identified, return: []
"""

        try:
            import json
            response = await self.model_client.create([{
                "role": "user", 
                "content": extraction_prompt
            }])
            
            # Parse JSON response
            software_list = json.loads(response.content.strip())
            
            # Validate structure
            if isinstance(software_list, list):
                validated_list = []
                valid_specialists = ["microsoft", "ubuntu", "redhat", "oracle", "python", "nodejs", "php", "postgresql", "apache", "vmware", "endoflife"]
                
                for item in software_list:
                    if isinstance(item, dict) and all(key in item for key in ["name", "version", "specialist", "confidence"]):
                        if item["specialist"] in valid_specialists:
                            validated_list.append({
                                'name': item["name"],
                                'version': item["version"],
                                'specialist': item["specialist"],
                                'confidence': item["confidence"],
                                'matched_pattern': f"LLM_EXTRACTED: {item['name']}"
                            })
                
                product_summary = ', '.join([f"{item['name']} ({item['specialist']})" for item in validated_list])
                logger.info(f"🧠 LLM SOFTWARE EXTRACTION | Found {len(validated_list)} products: {product_summary}")
                return validated_list
            
            return []
            
        except json.JSONDecodeError:
            logger.error("Invalid JSON from LLM software extraction")
            return []
        except Exception as e:
            logger.error(f"LLM software extraction error: {e}")
            raise

    def _fallback_pattern_extraction(self, query: str) -> List[Dict[str, str]]:
        """Fallback pattern-based extraction if LLM fails"""
        query_lower = query.lower()
        
        # Enhanced software patterns with version detection
        software_patterns = {
            # Microsoft products
            "windows server": {
                "patterns": ["windows server 2025", "windows server 2022", "windows server 2019", "windows server 2016", "windows server"],
                "specialist": "microsoft"
            },
            "windows": {
                "patterns": ["windows 11", "windows 10", "windows 8", "windows 7", "windows"],
                "specialist": "microsoft"
            },
            "office": {
                "patterns": ["office 365", "office 2021", "office 2019", "office 2016", "microsoft office"],
                "specialist": "microsoft"
            },
            "azure": {
                "patterns": ["azure", "azure ad", "azure sql"],
                "specialist": "microsoft"
            },
            "sql server": {
                "patterns": ["sql server 2022", "sql server 2019", "sql server 2017", "sql server"],
                "specialist": "microsoft"
            },
            # Linux distributions
            "ubuntu": {
                "patterns": ["ubuntu 24.04", "ubuntu 22.04", "ubuntu 20.04", "ubuntu 18.04", "ubuntu"],
                "specialist": "ubuntu"
            },
            "red hat": {
                "patterns": ["red hat enterprise", "rhel", "red hat"],
                "specialist": "redhat"
            },
            # Programming languages
            "python": {
                "patterns": ["python 3.12", "python 3.11", "python 3.10", "python 3", "python 2", "python"],
                "specialist": "python"
            },
            "node.js": {
                "patterns": ["node.js", "nodejs", "node"],
                "specialist": "nodejs"
            },
            "php": {
                "patterns": ["php 8", "php 7", "php"],
                "specialist": "php"
            },
            # Databases
            "postgresql": {
                "patterns": ["postgresql", "postgres"],
                "specialist": "postgresql"
            },
            "oracle": {
                "patterns": ["oracle database", "oracle"],
                "specialist": "oracle"
            },
            # Web servers
            "apache": {
                "patterns": ["apache httpd", "apache"],
                "specialist": "apache"
            },
            # Virtualization
            "vmware": {
                "patterns": ["vmware vsphere", "vmware esxi", "vmware"],
                "specialist": "vmware"
            }
        }
        
        found_software = []
        matched_text = set()  # Track what parts of the query we've already matched
        
        # Sort patterns by specificity (longer patterns first to prioritize specific matches)
        sorted_patterns = []
        for software_name, config in software_patterns.items():
            for pattern in config["patterns"]:
                sorted_patterns.append((len(pattern), software_name, pattern, config["specialist"]))
        
        # Sort by pattern length (descending) to prioritize more specific patterns
        sorted_patterns.sort(reverse=True)
        
        # Look for specific patterns with versions, avoiding overlaps
        for pattern_len, software_name, pattern, specialist in sorted_patterns:
            if pattern in query_lower:
                # Check if this pattern overlaps with already matched text
                pattern_start = query_lower.find(pattern)
                pattern_end = pattern_start + len(pattern)
                pattern_range = set(range(pattern_start, pattern_end))
                
                # Skip if this pattern overlaps with already matched text
                if pattern_range & matched_text:
                    continue
                
                # Mark this text as matched to prevent overlaps
                matched_text.update(pattern_range)
                
                # Extract version if present
                version = self._extract_version_from_pattern(query_lower, pattern)
                found_software.append({
                    "name": software_name,
                    "version": version,
                    "specialist": specialist,
                    "confidence": "medium", 
                    "matched_pattern": pattern
                })
                
                logger.info(f"🔍 PATTERN MATCH | {software_name} {version} (pattern: {pattern})")
                break
        
        # If no specific patterns matched, try to extract generic software names
        if not found_software:
            import re
            # Look for potential software names (capitalized words, version numbers)
            words = re.findall(r'\b[A-Za-z][A-Za-z0-9]*(?:\s+[0-9.]+)?\b', query)
            for word_group in words[:2]:  # Limit to prevent noise
                if len(word_group) > 3:
                    found_software.append({
                        "name": word_group,
                        "version": "",
                        "specialist": "endoflife",
                        "confidence": "low",
                        "matched_pattern": "generic"
                    })
        
        return found_software[:3]  # Limit to 3 items

    def _extract_version_from_pattern(self, query: str, pattern: str) -> str:
        """Extract version number from the matched pattern"""
        import re
        
        # First, check if the pattern itself contains a version number
        version_in_pattern = re.search(r'(\d+(?:\.\d+)*)', pattern)
        if version_in_pattern:
            return version_in_pattern.group(1)
        
        # If pattern doesn't have version, look for version numbers after the pattern in the query
        escaped_pattern = re.escape(pattern)
        version_after_pattern = re.search(rf'{escaped_pattern}\s*(\d+(?:\.\d+)*)', query)
        if version_after_pattern:
            return version_after_pattern.group(1)
        
        # Look for any version numbers in the vicinity of the software name
        pattern_start = query.find(pattern)
        if pattern_start != -1:
            # Look in a window around the pattern (before and after)
            window_start = max(0, pattern_start - 10)
            window_end = min(len(query), pattern_start + len(pattern) + 10)
            window_text = query[window_start:window_end]
            
            version_in_window = re.search(r'(\d+(?:\.\d+)*)', window_text)
            if version_in_window:
                return version_in_window.group(1)
        
        return ""

    def _determine_eol_specialist(self, software_name: str) -> str:
        """Determine which EOL specialist to use for a given software"""
        software_lower = software_name.lower()
        
        # Microsoft products
        if any(keyword in software_lower for keyword in ["windows", "office", "azure", "sql server", "microsoft"]):
            return "microsoft"
        
        # Linux distributions
        elif "ubuntu" in software_lower:
            return "ubuntu"
        elif any(keyword in software_lower for keyword in ["red hat", "rhel"]):
            return "redhat"
        
        # Programming languages
        elif "python" in software_lower:
            return "python"
        elif any(keyword in software_lower for keyword in ["node", "nodejs"]):
            return "nodejs"
        elif "php" in software_lower:
            return "php"
        
        # Databases
        elif any(keyword in software_lower for keyword in ["postgresql", "postgres"]):
            return "postgresql"
        elif "oracle" in software_lower:
            return "oracle"
        
        # Web servers
        elif "apache" in software_lower:
            return "apache"
        
        # Virtualization
        elif "vmware" in software_lower:
            return "vmware"
        
        # Default to EndOfLife.date for unknown software
        else:
            return "endoflife"
    
    async def _proceed_with_eol_focused_chat(self, user_message: str, timeout_seconds: int = 60) -> Dict[str, Any]:
        """
        Handle EOL analysis requests using EOL specialists with minimal inventory support.
        Uses a focused team for faster EOL responses.
        """
        try:
            self._log_agent_action("Orchestrator", "eol_focused_start", {
                "message": user_message[:100],
                "timeout": timeout_seconds,
                "approach": "eol_specialists_focused"
            })

            # Use minimal team for faster EOL responses (similar to existing minimal_team logic)
            self._setup_team_chat(minimal_team=True)
            
            if not self.team:
                return await self._fallback_eol_response(user_message)
            
            # Run the EOL-focused conversation
            message = TextMessage(content=user_message, source="user")
            
            conversation_start = time.time()
            result = await asyncio.wait_for(
                self.team.run(task=message),
                timeout=timeout_seconds
            )
            conversation_duration = time.time() - conversation_start
            
            self._log_agent_action("Orchestrator", "eol_focused_complete", {
                "duration": conversation_duration,
                "approach": "minimal_eol_team"
            })
            
            return self._process_autonomous_team_result(result, user_message)
            
        except asyncio.TimeoutError:
            return self._create_timeout_response(user_message, timeout_seconds)
        except Exception as e:
            logger.error(f"EOL-focused chat error: {e}")
            return await self._fallback_eol_response(user_message)
    
    async def _fallback_inventory_response(self, user_message: str) -> Dict[str, Any]:
        """Fallback response for inventory requests when AutoGen is not available"""
        try:
            message_lower = user_message.lower()
            
            # Determine what type of inventory data is needed
            if any(keyword in message_lower for keyword in ["os", "operating system", "version"]):
                # Try to get OS inventory specifically
                try:
                    os_data = self._run_async_safely(self.os_inventory_agent.get_os_inventory(days=90, limit=100))
                    if os_data and os_data.get("success") and os_data.get("data"):
                        response = f"✅ **Operating System Inventory**\n\n"
                        response += f"Found {len(os_data['data'])} operating systems:\n\n"
                        for i, os_item in enumerate(os_data['data'][:10], 1):  # Show first 10
                            response += f"{i}. **{os_item.get('os_name', 'Unknown')}** v{os_item.get('os_version', 'N/A')}\n"
                            response += f"   - Computer: {os_item.get('computer_name', 'Unknown')}\n"
                            response += f"   - OS Type: {os_item.get('os_type', 'Unknown')}\n\n"
                    else:
                        response = "❌ Unable to retrieve OS inventory data. Please check the system configuration."
                except Exception as e:
                    response = f"❌ Error retrieving OS inventory: {str(e)}"
                    
            elif any(keyword in message_lower for keyword in ["software", "applications", "programs"]):
                # Try to get software inventory specifically
                try:
                    software_data = self._run_async_safely(self.software_inventory_agent.get_software_inventory(days=90, limit=100))
                    if software_data and software_data.get("success") and software_data.get("data"):
                        response = f"✅ **Software Inventory**\n\n"
                        response += f"Found {len(software_data['data'])} software items:\n\n"
                        for i, sw_item in enumerate(software_data['data'][:10], 1):  # Show first 10
                            response += f"{i}. **{sw_item.get('name', 'Unknown')}** v{sw_item.get('version', 'N/A')}\n"
                            response += f"   - Publisher: {sw_item.get('publisher', 'Unknown')}\n\n"
                    else:
                        response = "❌ Unable to retrieve software inventory data. Please check the system configuration."
                except Exception as e:
                    response = f"❌ Error retrieving software inventory: {str(e)}"
            else:
                # Try to get general inventory summary
                inventory_summary = self._run_async_safely(self.inventory_agent.get_inventory_summary())
                
                if inventory_summary:
                    response = f"✅ **Inventory Summary**\n\n{str(inventory_summary)}"
                else:
                    response = "❌ Unable to retrieve inventory data. Please check the system configuration."
            
            return {
                "response": response,
                "conversation_messages": [
                    {
                        "speaker": "user",
                        "content": user_message,
                        "timestamp": datetime.utcnow().isoformat(),
                        "message_type": "UserMessage"
                    },
                    {
                        "speaker": "InventoryAgent",
                        "content": response,
                        "timestamp": datetime.utcnow().isoformat(),
                        "message_type": "AssistantMessage"
                    }
                ],
                "agent_communications": self.agent_communications[-10:],
                "session_id": self.session_id,
                "agents_involved": ["InventoryAgent"],
                "total_exchanges": 2
            }
        except Exception as e:
            logger.error(f"Fallback inventory response error: {e}")
            return self._create_error_response(f"Error retrieving inventory data: {str(e)}")
    
    async def _fallback_eol_response(self, user_message: str) -> Dict[str, Any]:
        """Fallback response for EOL requests when AutoGen is not available"""
        response = """❌ **EOL Analysis Unavailable**

The multi-agent EOL analysis system is currently unavailable. For EOL information, you can:

1. Use the standard EOL search interface
2. Check endoflife.date directly for software lifecycle information
3. Contact your system administrator for assistance

Would you like me to try a simpler approach to get basic EOL information?"""
        
        return {
            "response": response,
            "conversation_messages": [
                {
                    "speaker": "user",
                    "content": user_message,
                    "timestamp": datetime.utcnow().isoformat(),
                    "message_type": "UserMessage"
                },
                {
                    "speaker": "EOLAgent",
                    "content": response,
                    "timestamp": datetime.utcnow().isoformat(),
                    "message_type": "AssistantMessage"
                }
            ],
            "agent_communications": self.agent_communications[-10:],
            "session_id": self.session_id,
            "agents_involved": ["EOLAgent"],
            "total_exchanges": 2
        }
    
    def _process_inventory_team_result(self, result, original_message: str) -> Dict[str, Any]:
        """Process results from inventory-only team conversation"""
        try:
            if hasattr(result, 'messages') and result.messages:
                conversation_messages = []
                agents_involved = set()
                
                # Add user message first
                conversation_messages.append({
                    "speaker": "user", 
                    "content": original_message,
                    "timestamp": datetime.utcnow().isoformat(),
                    "message_type": "UserMessage"
                })
                
                # Process agent messages
                for msg in result.messages:
                    if hasattr(msg, 'source') and hasattr(msg, 'content'):
                        speaker = msg.source
                        agents_involved.add(speaker)
                        
                        conversation_messages.append({
                            "speaker": speaker,
                            "content": msg.content,
                            "timestamp": datetime.utcnow().isoformat(),
                            "message_type": "AssistantMessage"
                        })
                
                # Get the final response
                final_response = result.messages[-1].content if result.messages else "Inventory analysis completed."
                
                self._log_agent_action("Orchestrator", "inventory_team_complete", {
                    "total_messages": len(result.messages),
                    "agents_involved": list(agents_involved),
                    "conversation_completed": True
                })
                
                return {
                    "response": final_response,
                    "conversation_messages": conversation_messages,
                    "agent_communications": self.agent_communications[-15:],
                    "session_id": self.session_id,
                    "agents_involved": list(agents_involved),
                    "total_exchanges": len(conversation_messages)
                }
            else:
                return self._create_error_response("No valid response from inventory team")
                
        except Exception as e:
            logger.error(f"Error processing inventory team result: {e}")
            return self._create_error_response(f"Error processing inventory results: {str(e)}")

    async def _llm_select_agents(self, user_message: str) -> List[str]:
        """Use LLM to intelligently select relevant agents based on the user query"""
        selection_prompt = f"""
You are an intelligent agent selector for a multi-agent software inventory and EOL (End of Life) analysis system.

Analyze this user request and select the most relevant agents from the available specialists:

AVAILABLE AGENTS:
- **inventory_specialist**: For asset discovery, software inventory, system scanning, OS identification
- **microsoft_eol_specialist**: For Windows, Office, SQL Server, Azure, Exchange, SharePoint, .NET products
- **ubuntu_eol_specialist**: For Ubuntu Linux versions and lifecycle information  
- **oracle_eol_specialist**: For Oracle Database, Oracle products, Java (Oracle-owned)
- **redhat_eol_specialist**: For RHEL, CentOS, Fedora, Red Hat enterprise products
- **python_eol_specialist**: For Python language versions and package lifecycle
- **nodejs_eol_specialist**: For Node.js, npm packages, JavaScript runtime
- **php_eol_specialist**: For PHP language and framework lifecycle
- **postgresql_eol_specialist**: For PostgreSQL database versions
- **apache_eol_specialist**: For Apache HTTP Server, Tomcat, other Apache projects
- **vmware_eol_specialist**: For VMware ESXi, vCenter, Workstation products
- **endoflife_specialist**: For generic products not covered by other specialists

USER REQUEST: "{user_message}"

Select 2-4 most relevant agents. Prioritize:
1. **Inventory specialist** if user needs asset discovery or software listing
2. **Specific product specialists** if user mentions particular software
3. **Generic EOL specialist** for products not covered by dedicated specialists

Respond with JSON array of agent names ONLY:
["agent1", "agent2", "agent3"]
"""

        try:
            response = await self.model_client.create([{
                "role": "user", 
                "content": selection_prompt
            }])
            
            import json
            selected_agents = json.loads(response.content.strip())
            
            # Validate agent selection
            available_agents = [
                "inventory_specialist", "microsoft_eol_specialist", "ubuntu_eol_specialist",
                "oracle_eol_specialist", "redhat_eol_specialist", "python_eol_specialist",
                "nodejs_eol_specialist", "php_eol_specialist", "postgresql_eol_specialist", 
                "apache_eol_specialist", "vmware_eol_specialist", "endoflife_specialist"
            ]
            
            validated_agents = [agent for agent in selected_agents if agent in available_agents]
            
            # Ensure we have at least inventory specialist for mixed requests
            if not validated_agents:
                validated_agents = ["inventory_specialist", "endoflife_specialist"]
            
            logger.info(f"🧠 AGENT SELECTION | Selected: {validated_agents}")
            return validated_agents
            
        except (json.JSONDecodeError, Exception) as e:
            logger.warning(f"LLM agent selection failed: {e}, using default selection")
            # Fallback to basic selection
            if any(keyword in user_message.lower() for keyword in ["inventory", "software", "applications"]):
                return ["inventory_specialist", "endoflife_specialist"]
            else:
                return ["inventory_specialist", "microsoft_eol_specialist", "endoflife_specialist"]

    async def _proceed_with_mixed_request(self, user_message: str, timeout_seconds: int = 120) -> Dict[str, Any]:
        """
        Handle mixed requests that require both inventory gathering AND EOL analysis.
        This is the core functionality for queries like "Show my OS inventory with EOL dates"
        """
        try:
            start_time = time.time()
            logger.info(f"🔀 MIXED REQUEST START | Message: {user_message[:100]}")
            
            self._log_agent_action("Orchestrator", "mixed_request_start", {
                "message": user_message[:100],
                "timeout": timeout_seconds,
                "approach": "inventory_plus_eol_analysis"
            })

            # Step 1: Gather inventory data
            inventory_start = time.time()
            logger.info(f"📊 INVENTORY PHASE START | Gathering system inventory")
            
            inventory_data = []
            
            # Try to get OS inventory
            if any(term in user_message.lower() for term in ["os", "operating system", "windows", "linux", "ubuntu"]):
                os_data = self._get_os_inventory_tool(365)  # Use 365 days instead of "all"
                if os_data and "No OS data found" not in os_data:
                    inventory_data.append({"type": "OS", "data": os_data})
                    logger.info(f"✅ OS INVENTORY | Found OS data")
            
            # Try to get software inventory if requested
            if any(term in user_message.lower() for term in ["software", "application", "program"]):
                software_data = self._get_software_inventory_tool(365)  # Use 365 days instead of "all"
                if software_data and "No software data found" not in software_data:
                    inventory_data.append({"type": "Software", "data": software_data})
                    logger.info(f"✅ SOFTWARE INVENTORY | Found software data")
            
            inventory_duration = time.time() - inventory_start
            logger.info(f"📊 INVENTORY PHASE COMPLETE | Duration: {inventory_duration:.2f}s | Items: {len(inventory_data)}")
            
            if not inventory_data:
                return {
                    "response": "I wasn't able to gather inventory data from your systems. This could be due to connectivity issues or access permissions. Please ensure the system is accessible and try again.",
                    "conversation_messages": [],
                    "agent_communications": self.agent_communications[-10:],
                    "session_id": self.session_id,
                    "agents_involved": ["InventorySpecialist"],
                    "total_exchanges": 1,
                    "error": "No inventory data available"
                }

            # Step 2: Perform EOL analysis on found inventory
            eol_start = time.time()
            logger.info(f"🔍 EOL ANALYSIS START | Analyzing {len(inventory_data)} inventory categories")
            
            eol_analysis_results = []
            
            for inventory_item in inventory_data:
                item_type = inventory_item["type"]
                item_data = inventory_item["data"]
                
                # Parse software/OS names from inventory data
                extracted_products = self._extract_products_from_inventory(item_data)
                
                for product in extracted_products:
                    logger.info(f"🎯 ANALYZING EOL | Product: {product['name']} | Version: {product.get('version', 'N/A')}")
                    
                    # Get EOL information for this product
                    eol_info = await self._get_eol_for_product(product["name"], product.get("version", ""))
                    
                    if eol_info:
                        eol_analysis_results.append({
                            "category": item_type,
                            "product": product["name"],
                            "version": product.get("version", "Unknown"),
                            "eol_info": eol_info
                        })

            eol_duration = time.time() - eol_start
            total_duration = time.time() - start_time
            logger.info(f"🔍 EOL ANALYSIS COMPLETE | Duration: {eol_duration:.2f}s | Total: {total_duration:.2f}s")

            # Step 3: Format comprehensive response
            return self._format_mixed_request_response(
                user_message, 
                inventory_data, 
                eol_analysis_results,
                total_duration
            )

        except Exception as e:
            logger.error(f"Mixed request error: {e}")
            return self._create_error_response(f"Mixed request processing failed: {str(e)}")

    def _extract_products_from_inventory(self, inventory_data: str) -> List[Dict[str, str]]:
        """Extract product names and versions from inventory data"""
        products = []
        
        # Look for common patterns in inventory data
        lines = inventory_data.split('\n')
        for line in lines:
            line = line.strip()
            if not line or line.startswith('#') or line.startswith('//'):
                continue
                
            # Try to extract OS information
            if any(os_term in line.lower() for os_term in ["windows", "ubuntu", "rhel", "centos", "debian", "suse"]):
                # Extract OS name and version
                if "windows" in line.lower():
                    if "server" in line.lower():
                        if "2025" in line: products.append({"name": "Windows Server", "version": "2025"})
                        elif "2022" in line: products.append({"name": "Windows Server", "version": "2022"})
                        elif "2019" in line: products.append({"name": "Windows Server", "version": "2019"})
                        elif "2016" in line: products.append({"name": "Windows Server", "version": "2016"})
                        else: products.append({"name": "Windows Server", "version": "Unknown"})
                    else:
                        if "11" in line: products.append({"name": "Windows", "version": "11"})
                        elif "10" in line: products.append({"name": "Windows", "version": "10"})
                        else: products.append({"name": "Windows", "version": "Unknown"})
                elif "ubuntu" in line.lower():
                    import re
                    version_match = re.search(r'(\d+\.\d+)', line)
                    version = version_match.group(1) if version_match else "Unknown"
                    products.append({"name": "Ubuntu", "version": version})
                elif "rhel" in line.lower() or "red hat" in line.lower():
                    import re
                    version_match = re.search(r'(\d+)', line)
                    version = version_match.group(1) if version_match else "Unknown"
                    products.append({"name": "Red Hat Enterprise Linux", "version": version})
                    
            # Try to extract software information
            elif any(software_term in line.lower() for software_term in ["python", "java", "node", "php", "apache", "nginx", "mysql", "postgresql"]):
                import re
                for software in ["python", "java", "node", "php", "apache", "nginx", "mysql", "postgresql"]:
                    if software in line.lower():
                        version_match = re.search(rf'{software}[^\d]*(\d+(?:\.\d+)*)', line, re.IGNORECASE)
                        version = version_match.group(1) if version_match else "Unknown"
                        products.append({"name": software.title(), "version": version})
                        break
        
        # Remove duplicates
        unique_products = []
        seen = set()
        for product in products:
            key = f"{product['name']}-{product['version']}"
            if key not in seen:
                seen.add(key)
                unique_products.append(product)
        
        return unique_products

    async def _get_eol_for_product(self, product_name: str, version: str) -> str:
        """Get EOL information for a specific product"""
        try:
            # Determine which specialist to use
            specialist_type = self._determine_eol_specialist(product_name)
            
            # Call appropriate EOL tool
            if specialist_type == "microsoft":
                return self._check_microsoft_eol_tool(product_name, version)
            elif specialist_type == "ubuntu":
                return self._check_ubuntu_eol_tool(product_name, version)
            elif specialist_type == "redhat":
                return self._check_redhat_eol_tool(product_name, version)
            elif specialist_type == "oracle":
                return self._check_oracle_eol_tool(product_name, version)
            elif specialist_type == "python":
                return self._check_python_eol_tool(product_name, version)
            elif specialist_type == "nodejs":
                return self._check_nodejs_eol_tool(product_name, version)
            elif specialist_type == "php":
                return self._check_php_eol_tool(product_name, version)
            elif specialist_type == "postgresql":
                return self._check_postgresql_eol_tool(product_name, version)
            elif specialist_type == "apache":
                return self._check_apache_eol_tool(product_name, version)
            elif specialist_type == "vmware":
                return self._check_vmware_eol_tool(product_name, version)
            else:
                return self._check_endoflife_eol_tool(product_name, version)
                
        except Exception as e:
            logger.error(f"EOL lookup error for {product_name}: {e}")
            return f"Error getting EOL data for {product_name}: {str(e)}"

    def _format_mixed_request_response(
        self, 
        user_message: str, 
        inventory_data: List[Dict], 
        eol_analysis: List[Dict],
        processing_time: float
    ) -> Dict[str, Any]:
        """Format the comprehensive response for mixed requests"""
        
        # Build the response message
        response_parts = []
        response_parts.append("# 📊 System Inventory with EOL Analysis\n")
        
        if inventory_data:
            response_parts.append("## 🖥️ **Inventory Summary**")
            for item in inventory_data:
                response_parts.append(f"- **{item['type']}**: Found and analyzed")
            response_parts.append("")
        
        if eol_analysis:
            response_parts.append("## ⚠️ **EOL Analysis Results**")
            
            # Group by category
            categories = {}
            for result in eol_analysis:
                cat = result["category"]
                if cat not in categories:
                    categories[cat] = []
                categories[cat].append(result)
            
            for category, results in categories.items():
                response_parts.append(f"### {category}:")
                for result in results:
                    product = result["product"]
                    version = result["version"]
                    eol_info = result["eol_info"]
                    
                    response_parts.append(f"**{product} {version}**:")
                    response_parts.append(f"```")
                    response_parts.append(eol_info[:500] + "..." if len(eol_info) > 500 else eol_info)
                    response_parts.append(f"```")
                    response_parts.append("")
        else:
            response_parts.append("## ℹ️ **EOL Information**")
            response_parts.append("No specific EOL data was found for the discovered products. This could mean:")
            response_parts.append("- The products are current and supported")
            response_parts.append("- EOL information is not publicly available")
            response_parts.append("- Product names may need more specific identification")
        
        response_parts.append(f"\n*Analysis completed in {processing_time:.1f} seconds*")
        
        final_response = "\n".join(response_parts)
        
        # Create conversation messages
        conversation_messages = [
            {
                "speaker": "user",
                "content": user_message,
                "timestamp": datetime.utcnow().isoformat(),
                "message_type": "UserMessage"
            },
            {
                "speaker": "MixedRequestOrchestrator", 
                "content": final_response,
                "timestamp": datetime.utcnow().isoformat(),
                "message_type": "AssistantMessage"
            }
        ]
        
        return {
            "response": final_response,
            "conversation_messages": conversation_messages,
            "agent_communications": self.agent_communications[-20:],
            "session_id": self.session_id,
            "agents_involved": ["InventorySpecialist", "EOLSpecialist", "MixedRequestOrchestrator"],
            "total_exchanges": len(conversation_messages),
            "inventory_items": len(inventory_data),
            "eol_analyses": len(eol_analysis),
            "processing_time": processing_time,
            "approach": "inventory_plus_eol_analysis"
        }

    async def _proceed_with_autonomous_team_chat(self, user_message: str, timeout_seconds: int = 90) -> Dict[str, Any]:
        """
        Enhanced autonomous team chat using LLM to intelligently select relevant agents.
        Agents are selected based on query analysis rather than hardcoded rules.
        
        Args:
            user_message: The user's message
            timeout_seconds: Maximum time for the conversation
        """
        try:
            start_time = time.time()
            logger.info(f"🤖 AUTONOMOUS CHAT START | Timeout: {timeout_seconds}s | Message: {user_message[:100]}")
            
            self._log_agent_action("Orchestrator", "autonomous_team_start", {
                "message": user_message[:100],
                "timeout": timeout_seconds,
                "approach": "llm_guided_agent_selection"
            })

            # Use LLM to intelligently select relevant agents
            setup_start = time.time()
            logger.info(f"🧠 AGENT SELECTION START | Using LLM to determine optimal team")
            selected_agents = self._llm_select_agents(user_message)
            
            # Setup team with selected agents
            self._setup_team_chat(minimal_team=False, selected_agents=selected_agents)
            setup_duration = time.time() - setup_start
            logger.info(f"🔧 TEAM SETUP COMPLETE | Duration: {setup_duration:.2f}s | Team available: {self.team is not None}")
            
            if not self.team:
                # AutoGen not available, provide fallback response
                fallback_message = """I apologize, but the AutoGen multi-agent system is not currently available. This may be due to missing dependencies or configuration issues.

For inventory requests, I can still help you with:
- Basic inventory information
- Simple software lookups
- Direct API calls

Would you like me to try a simpler approach to get your inventory data?"""
                
                return {
                    "response": fallback_message,
                    "conversation_messages": [
                        {
                            "speaker": "user",
                            "content": user_message,
                            "timestamp": datetime.utcnow().isoformat(),
                            "message_type": "UserMessage"
                        },
                        {
                            "speaker": "Orchestrator",
                            "content": fallback_message,
                            "timestamp": datetime.utcnow().isoformat(),
                            "message_type": "AssistantMessage"
                        }
                    ],
                    "agent_communications": self.agent_communications[-20:],
                    "session_id": self.session_id,
                    "agents_involved": ["Orchestrator"],
                    "total_exchanges": 2,
                    "error": "AutoGen not available"
                }

            # Create initial message that encourages agent self-selection
            prompt_start = time.time()
            autonomous_prompt = f"""User Request: {user_message}

Agents: This is a truly autonomous team environment. Each specialist should:
1. **Self-evaluate** if this request matches your expertise domain
2. **Volunteer immediately** if you can contribute (say "I'll handle [specific part]")
3. **Collaborate autonomously** - no central routing or assignments
4. **Act independently** within your domain of expertise

The user is looking for help with their request. Which agents recognize this as matching their specialty?"""

            prompt_duration = time.time() - prompt_start
            logger.info(f"📝 PROMPT READY | Duration: {prompt_duration:.2f}s | Agents: {len(self.participants)}")
            
            # Start the autonomous conversation with faster timeout
            team_run_start = time.time()
            logger.info(f"🚀 TEAM RUN START | Timeout: {timeout_seconds}s | Beginning autonomous team conversation")
            result = await asyncio.wait_for(
                self.team.run(task=autonomous_prompt),
                timeout=timeout_seconds
            )
            team_run_duration = time.time() - team_run_start
            logger.info(f"🚀 TEAM RUN COMPLETE | Duration: {team_run_duration:.2f}s | Result type: {type(result).__name__}")
            
            # Process result with timeout protection (since it's sync, wrap it)
            try:
                process_start = time.time()
                logger.info(f"⚙️ RESULT PROCESSING START | Beginning result processing")
                
                def process_result_sync():
                    return self._process_autonomous_team_result(result, user_message)
                
                # Run sync function in thread pool to make it awaitable with timeout
                processed_result = await asyncio.wait_for(
                    asyncio.get_event_loop().run_in_executor(None, process_result_sync),
                    timeout=30  # Give result processing max 30 seconds
                )
                
                process_duration = time.time() - process_start
                total_duration = time.time() - start_time
                logger.info(f"⚙️ RESULT PROCESSING COMPLETE | Process: {process_duration:.2f}s | Total: {total_duration:.2f}s")
                return processed_result
                
            except asyncio.TimeoutError:
                process_duration = time.time() - process_start
                total_duration = time.time() - start_time
                logger.warning(f"⚙️ RESULT PROCESSING TIMEOUT | Process: {process_duration:.2f}s | Total: {total_duration:.2f}s")
                # Return quick response if processing is slow
                return {
                    "response": "The agents completed their analysis successfully, but result processing took longer than expected. Please check the agent communications panel for details.",
                    "conversation_messages": [],
                    "agent_communications": self.agent_communications[-10:],
                    "session_id": self.session_id,
                    "agents_involved": ["AutonomousTeam"],
                    "total_exchanges": 1,
                    "processing_timeout": True
                }
            
        except asyncio.TimeoutError:
            total_duration = time.time() - start_time
            logger.warning(f"🚀 TEAM RUN TIMEOUT | Duration: {total_duration:.2f}s | Timeout: {timeout_seconds}s")
            return self._create_timeout_response(user_message, timeout_seconds)
        except Exception as e:
            total_duration = time.time() - start_time
            error_msg = f"Autonomous team chat error: {str(e)}"
            logger.error(f"🚀 TEAM RUN ERROR | Duration: {total_duration:.2f}s | Error: {error_msg}")
            return self._create_error_response(error_msg)

    def _process_autonomous_team_result(self, result, original_message: str) -> Dict[str, Any]:
        """Process the result from autonomous team conversation"""
        try:
            process_start = time.time()
            logger.info(f"🔄 RESULT ANALYSIS START | Result type: {type(result).__name__}")
            
            if hasattr(result, 'messages') and result.messages:
                messages_start = time.time()
                messages = result.messages
                final_response = messages[-1].content if messages else "No response generated"
                messages_duration = time.time() - messages_start
                logger.info(f"📨 MESSAGES PROCESSED | Count: {len(messages)} | Duration: {messages_duration:.2f}s")
                
                # Extract which agents participated (limit processing for performance)
                agents_start = time.time()
                agents_involved = []
                for msg in messages[-10:]:  # Only check last 10 messages for performance
                    if hasattr(msg, 'source') and msg.source not in agents_involved:
                        agents_involved.append(msg.source)
                agents_duration = time.time() - agents_start
                logger.info(f"👥 AGENTS EXTRACTED | Count: {len(agents_involved)} | Duration: {agents_duration:.2f}s")
                
                log_start = time.time()
                self._log_agent_action("Orchestrator", "autonomous_team_complete", {
                    "agents_participated": agents_involved,
                    "total_messages": len(messages),
                    "self_organization": "success"
                })
                log_duration = time.time() - log_start
                logger.info(f"📝 LOGGING COMPLETE | Duration: {log_duration:.2f}s")
                
                # Optimize conversation message processing
                conv_start = time.time()
                conversation_messages = []
                for msg in messages[-20:]:  # Limit to last 20 messages for performance
                    conversation_messages.append({
                        "speaker": msg.source if hasattr(msg, 'source') else "unknown",
                        "message": msg.content if hasattr(msg, 'content') else str(msg)
                    })
                conv_duration = time.time() - conv_start
                logger.info(f"💬 CONVERSATION FORMATTED | Messages: {len(conversation_messages)} | Duration: {conv_duration:.2f}s")
                
                total_process_duration = time.time() - process_start
                logger.info(f"🔄 RESULT ANALYSIS COMPLETE | Total: {total_process_duration:.2f}s")
                
                return {
                    "response": final_response,
                    "conversation_messages": conversation_messages,
                    "agent_communications": self.agent_communications[-15:],  # Reduced from 20 to 15
                    "session_id": self.session_id,
                    "agents_involved": agents_involved,
                    "total_exchanges": len(messages),
                    "autonomous_approach": True
                }
            else:
                # Handle case where result format is different
                response_text = str(result) if result else "No response from autonomous team"
                
                return {
                    "response": response_text,
                    "conversation_messages": [{"speaker": "AutonomousTeam", "message": response_text}],
                    "agent_communications": self.agent_communications[-10:],
                    "session_id": self.session_id,
                    "agents_involved": ["AutonomousTeam"],
                    "total_exchanges": 1,
                    "autonomous_approach": True
                }
                
        except Exception as e:
            logger.error(f"Error processing autonomous team result: {e}")
            return self._create_error_response(f"Error processing team response: {str(e)}")

    async def _proceed_with_multi_agent_chat(self, user_message: str, minimal_team: bool = False, timeout_seconds: int = 50) -> Dict[str, Any]:
        """
        Proceed with multi-agent conversation after user confirmation

        Args:
            user_message: The user's message
            minimal_team: Use minimal team for faster responses
            timeout_seconds: Maximum time for the conversation
        """
        try:
            # Log the user's intent to proceed
            self._log_agent_action("User", "message", {})

            # Use the new AutoGen 0.7.x API with retry logic
            team_type = "minimal" if minimal_team else "full"
            # logger.debug(f"[DEBUG] Starting confirmed team chat ({team_type} team, {timeout_seconds}s timeout)")

            # Call the retry wrapper which handles rate-limited retries and timeouts
            return await self._chat_with_retry(user_message, max_retries=3, minimal_team=minimal_team, timeout_seconds=timeout_seconds)

        except Exception as e:
            error_msg = f"Error proceeding with multi-agent chat: {str(e)}"
            # logger.debug(f"[DEBUG] _proceed_with_multi_agent_chat error: {error_msg}")
            self._log_agent_action("Orchestrator", "proceed_multi_agent_error", {"error": error_msg})
            return {
                "response": "I encountered an error while starting the multi-agent chat.",
                "error": error_msg,
                "agent_communications": self.agent_communications[-20:],
                "session_id": getattr(self, 'session_id', None),
                "conversation_messages": [],
                "agents_involved": [],
                "total_exchanges": 0
            }

    async def chat(self, user_message: str, timeout_seconds: int = 180) -> Dict[str, Any]:
        """
        Main chat interface using AutoGen team chat (0.7.x API)
        Returns conversation with full agent communication transparency
        
        Args:
            user_message: User's input message
            timeout_seconds: Maximum time to wait for response (default 60s, dynamically adjusted)
        """
        try:
            # START COMPREHENSIVE LOGGING WITH DYNAMIC TIMEOUT TRACKING
            session_start_time = time.time()
            
            # Apply dynamic timeout adjustment
            load_factor = self._get_system_load_factor()
            dynamic_timeout = self._get_dynamic_timeout(timeout_seconds, load_factor)
            logger.info(f"ORCHESTRATOR START | Session: {self.session_id} | Timeout: {dynamic_timeout}s")
            
            # Clear agent communications for fresh interaction tracking
            clear_start = time.time()
            logger.info(f"🧹 CHAT START | Clearing communications for new conversation")
            await self.clear_communications()
            clear_duration = time.time() - clear_start
            logger.info(f"🧹 CLEAR COMPLETE | Duration: {clear_duration:.2f}s")
            
            # Check if AutoGen is properly available first
            if not AUTOGEN_IMPORTS_OK:
                error_msg = "AutoGen framework is not available. Please install autogen-agentchat package."
                logger.error(f"CRITICAL ERROR | AutoGen not available: {error_msg}")
                
                self._log_agent_action("Orchestrator", "unavailable_error", {"error": error_msg})
                
                return {
                    "response": "The AutoGen multi-agent framework is currently not available. Please contact your administrator to install the required AutoGen packages.",
                    "conversation_messages": [],
                    "agent_communications": self.agent_communications[-15:],
                    "session_id": self.session_id,
                    "agents_involved": [],
                    "total_exchanges": 0,
                    "error": error_msg
                }
            
            # INTELLIGENT REQUEST PROCESSING - Let LLM determine tools and synthesize response
            intent_analysis_start = time.time()
            logger.info(f"🧠 INTELLIGENT PROCESSING START | Using LLM to determine tools and synthesize response")
            
            result = await self._intelligent_request_processing(user_message, dynamic_timeout)
            
            intent_analysis_duration = time.time() - intent_analysis_start
            logger.info(f"🧠 INTELLIGENT PROCESSING COMPLETE | Duration: {intent_analysis_duration:.2f}s")
            
            return result
                
        except Exception as e:
            logger.error(f"ORCHESTRATOR ERROR | Session: {self.session_id} | Error: {str(e)}")
            return self._create_error_response(str(e))

    def _create_error_response(self, error_message: str) -> Dict[str, Any]:
        """Create a standardized error response"""
        return {
            "response": f"I encountered an error processing your request: {error_message}",
            "conversation_messages": [],
            "agent_communications": self.agent_communications[-15:],
            "session_id": self.session_id,
            "agents_involved": [],
            "total_exchanges": 0,
            "error": error_message
        }

    def _create_timeout_response(self, user_message: str, timeout_seconds: int) -> Dict[str, Any]:
        """Create a standardized timeout response with available communications"""
        timeout_msg = f"⏱️ The request timed out after {timeout_seconds} seconds. The agents were working on your request but needed more time to complete the analysis."
        
        # Check if we have any partial communications to show
        if self.agent_communications:
            timeout_msg += f"\n\n📋 I was able to capture {len(self.agent_communications)} agent interactions before timing out. You can see the progress in the Agent Communications panel."
            
            # Try to extract any partial results from the communications
            for comm in reversed(self.agent_communications[-5:]):  # Check last 5 communications
                if comm.get('action') == 'agent_response' and comm.get('output'):
                    try:
                        output_data = comm.get('output', {})
                        if isinstance(output_data, dict) and 'content' in output_data:
                            timeout_msg += f"\n\n🔍 Partial result from {comm.get('agent', 'agent')}: {output_data['content'][:200]}..."
                            break
                    except:
                        pass
        else:
            timeout_msg += "\n\n🤖 No agent communications were captured, which may indicate a configuration issue."
        
        return {
            "response": timeout_msg,
            "conversation_messages": [],
            "agent_communications": self.agent_communications[-20:],  # Show recent communications
            "session_id": self.session_id,
            "agents_involved": list(set(comm.get('agent', 'unknown') for comm in self.agent_communications[-10:])),
            "total_exchanges": len(self.agent_communications),
            "error": f"Timeout after {timeout_seconds} seconds"
        }

    async def _proceed_with_multi_agent_chat(self, user_message: str, eol_focus: bool, dynamic_timeout: int) -> Dict[str, Any]:
        """Proceed with multi-agent conversation for complex requests using AutoGen 0.7.x"""
        try:
            logger.info(f"MULTI-AGENT CONVERSATION | Timeout: {dynamic_timeout}s | EOL Focus: {eol_focus}")
            
            self._log_agent_action("Orchestrator", "multi_agent_conversation_start", {
                "dynamic_timeout": dynamic_timeout,
                "eol_focus": eol_focus,
                "conversation_type": "full_autonomous"
            })
            
            # For AutoGen 0.7.x, use the simplified team approach
            # Create the team based on focus
            if eol_focus:
                team = RoundRobinGroupChat([
                    self.inventory_specialist,
                    self.eol_specialist,
                    self.security_specialist
                ])
            else:
                team = RoundRobinGroupChat([
                    self.inventory_specialist,
                    self.eol_specialist,
                    self.security_specialist,
                    self.software_specialist,
                    self.os_specialist
                ])
            
            # Set termination conditions
            termination = MaxMessageTermination(max_messages=15) | TextMentionTermination("TASK_COMPLETE")
            
            # Start the conversation with improved prompt
            initial_message = TextMessage(
                content=f"""User Request: {user_message}

Please work together to provide a comprehensive response. Use your specialized tools to gather relevant inventory and EOL information. 

Each agent should:
1. Use appropriate tools to gather data
2. Share findings with the team  
3. Build upon other agents' discoveries
4. Provide actionable insights

When the analysis is complete, end with 'TASK_COMPLETE'.""",
                source="user"
            )
            
            # Run the team conversation
            result = await team.run(
                task=initial_message,
                termination_condition=termination,
                cancellation_token=CancellationToken()
            )
            
            # Process the response
            return self._process_team_response(result, user_message)
            
        except Exception as e:
            logger.error(f"Multi-agent conversation failed: {e}")
            return self._create_error_response(str(e))

    def _process_team_response(self, result: Response, user_message: str) -> Dict[str, Any]:
        """Process the response from AutoGen 0.7.x team conversation"""
        try:
            logger.info(f"[TEAM_RESPONSE] Processing team response - Result type: {type(result)}")
            
            # Extract the conversation messages
            conversation_messages = []
            agents_involved = set()
            
            if hasattr(result, 'messages') and result.messages:
                logger.info(f"[TEAM_RESPONSE] Found {len(result.messages)} messages in result")
                for i, msg in enumerate(result.messages):
                    if hasattr(msg, 'source') and hasattr(msg, 'content'):
                        speaker = msg.source if msg.source != "user" else "user_proxy"
                        agents_involved.add(speaker)
                        
                        # logger.debug(f"[TEAM_RESPONSE] Message {i}: {speaker} -> {msg.content[:100]}...")
                        
                        conversation_messages.append({
                            "speaker": speaker,
                            "content": msg.content,
                            "timestamp": datetime.utcnow().isoformat(),
                            "message_type": "AssistantMessage" if speaker != "user_proxy" else "UserMessage"
                        })
            else:
                logger.warning(f"[TEAM_RESPONSE] No messages found in result - hasattr messages: {hasattr(result, 'messages')}")
            
            # Get the final response (last message)
            final_response = ""
            if conversation_messages:
                final_response = conversation_messages[-1]["content"]
                logger.info(f"[TEAM_RESPONSE] Final response extracted: {final_response[:100]}...")
            else:
                final_response = "No response generated from multi-agent conversation."
                logger.warning(f"[TEAM_RESPONSE] No conversation messages found, using default response")
            
            response_data = {
                "response": final_response,
                "conversation_messages": conversation_messages,
                "agent_communications": self.agent_communications[-20:],
                "session_id": self.session_id,
                "agents_involved": list(agents_involved),
                "total_exchanges": len(conversation_messages),
                "fast_path": False,
                "autonomous_routing": True,
                "multi_agent_conversation": True
            }
            
            logger.info(f"[TEAM_RESPONSE] Returning response with {len(conversation_messages)} messages, {len(self.agent_communications)} communications")
            return response_data
            
        except Exception as e:
            logger.error(f"Error processing team response: {e}")
            return self._create_error_response(str(e))
    
    def get_agent_communications(self) -> List[Dict[str, Any]]:
        """Get all agent communications for UI display"""
        # logger.debug(f"[DEBUG] Getting agent communications: {len(self.agent_communications)} items")
        # if len(self.agent_communications) > 0:
        #     logger.debug(f"[DEBUG] First communication: {self.agent_communications[0]}")
        #     logger.debug(f"[DEBUG] Last communication: {self.agent_communications[-1]}")
        return self.agent_communications
    
    def get_conversation_history(self) -> List[Dict[str, Any]]:
        """Get conversation history"""
        return [
            {
                "speaker": msg.get("name", "Unknown"),
                "content": msg.get("content", ""),
                "timestamp": datetime.utcnow().isoformat()
            }
            for msg in getattr(self.team, 'messages', [])
        ]
    
    async def health_check(self) -> Dict[str, Any]:
        """Health check for AutoGen orchestrator"""
        try:
            # Get agent names safely
            agent_names = []
            for agent in self.participants:
                try:
                    name = getattr(agent, 'name', f'Agent_{type(agent).__name__}')
                    agent_names.append(name)
                except Exception as e:
                    agent_names.append(f'Agent_Error_{str(e)[:50]}')
            
            return {
                "status": "healthy",
                "session_id": self.session_id,
                "agents_count": len(self.participants),
                "agent_names": agent_names,
                "communications_logged": len(self.agent_communications),
                "autogen_version": autogen_version
            }
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "agents_count": 0,
                "autogen_version": autogen_version
            }
    
    def test_logging(self) -> Dict[str, Any]:
        """Test logging functionality - especially useful for Azure App Service debugging"""
        timestamp = datetime.now().isoformat()
        test_id = str(uuid.uuid4())[:8]
        
        # Test all log levels
        # logger.debug(f"🧪 DEBUG Test Log [{test_id}] - {timestamp}")
        # logger.info(f"🧪 INFO Test Log [{test_id}] - {timestamp}")
        # logger.warning(f"🧪 WARNING Test Log [{test_id}] - {timestamp}")
        # logger.error(f"🧪 ERROR Test Log [{test_id}] - {timestamp}")
        
        # Test structured logging
        # logger.info(f"🧪 STRUCTURED Test Log [{test_id}]", extra={
        #     "test_id": test_id,
        #     "timestamp": timestamp,
        #     "environment": "Azure App Service" if os.environ.get('WEBSITE_SITE_NAME') else "Local",
        #     "logger_name": logger.name,
        #     "logger_level": logger.level,
        #     "handler_count": len(logger.handlers)
        # })
        
        # Force immediate flush to stderr for Azure
        if os.environ.get('WEBSITE_SITE_NAME'):
            sys.stderr.flush()
        
        return {
            "test_completed": True,
            "test_id": test_id,
            "timestamp": timestamp,
            "environment": "Azure App Service" if os.environ.get('WEBSITE_SITE_NAME') else "Local",
            "logger_name": logger.name,
            "logger_level": logger.level,
            "handler_count": len(logger.handlers),
            "message": f"Logging test completed. Check Azure App Service logs for messages with ID [{test_id}]"
        }

    async def clear_communications(self) -> Dict[str, Any]:
        """
        Clear agent communications and reset conversation state
        """
        try:
            # Clear agent communications
            communications_count = len(self.agent_communications)
            self.agent_communications.clear()
            
            # Clear team chat messages if possible
            messages_count = 0
            if hasattr(self, 'team') and hasattr(self.team, 'messages'):
                messages_count = len(self.team.messages)
                self.team.messages.clear()
            
            # Reset session ID
            old_session_id = self.session_id
            self.session_id = str(uuid.uuid4())
            
            logger.info(f"🧹 AutoGen communications cleared: {communications_count} communications, {messages_count} messages, session {old_session_id} -> {self.session_id}")
            
            return {
                "success": True,
                "message": "AutoGen communications cleared successfully",
                "details": {
                    "communications_cleared": communications_count,
                    "messages_cleared": messages_count,
                    "old_session_id": old_session_id,
                    "new_session_id": self.session_id,
                    "timestamp": datetime.utcnow().isoformat()
                }
            }
            
        except Exception as e:
            logger.error(f"❌ Error clearing AutoGen communications: {str(e)}")
            return {
                "success": False,
                "error": f"Failed to clear AutoGen communications: {str(e)}"
            }

    async def get_cache_status(self) -> Dict[str, Any]:
        """
        Get AutoGen orchestrator cache and conversation status
        """
        try:
            current_time = datetime.utcnow()
            
            # Get agent communications stats
            communications_count = len(self.agent_communications)
            
            # Get team chat stats
            messages_count = 0
            if hasattr(self, 'team') and hasattr(self.team, 'messages'):
                messages_count = len(self.team.messages)
            
            # Get agent information
            agent_info = {}
            for agent in self.participants:
                try:
                    name = getattr(agent, 'name', f'Agent_{type(agent).__name__}')
                    agent_info[name] = {
                        "status": "available",
                        "type": type(agent).__name__
                    }
                except Exception as e:
                    agent_info[f'Agent_Error'] = {
                        "status": "error",
                        "error": str(e)[:100]
                    }
            
            return {
                "success": True,
                "data": {
                    "agent_communications": {
                        "total_communications": communications_count,
                        "recent_communications": len(self.agent_communications[-10:]) if self.agent_communications else 0,
                        "size_estimate_kb": len(str(self.agent_communications)) // 1024
                    },
                    "team_chat": {
                        "total_messages": messages_count,
                        "size_estimate_kb": len(str(getattr(self.team, 'messages', []))) // 1024
                    },
                    "agents": agent_info,
                    "session": {
                        "session_id": self.session_id,
                        "agents_count": len(self.participants),
                        "autogen_version": autogen_version
                    },
                    "timestamp": current_time.isoformat()
                }
            }
            
        except Exception as e:
            logger.error(f"❌ Error getting AutoGen cache status: {str(e)}")
            return {
                "success": False,
                "error": f"Failed to get AutoGen cache status: {str(e)}"
            }
