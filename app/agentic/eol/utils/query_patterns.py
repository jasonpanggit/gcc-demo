"""
Centralized Query Pattern Definitions

This module provides a single source of truth for all query pattern matching
across the EOL Multi-Agent application. It consolidates patterns for EOL queries,
inventory requests, and approaching EOL detection.

Classes:
    QueryPatterns: Pattern matching utilities for query intent analysis

Example:
    >>> from utils.query_patterns import QueryPatterns
    >>> QueryPatterns.matches_eol_pattern("what is the eol for windows server 2016")
    True
    >>> intent = QueryPatterns.analyze_query_intent("show me software inventory")
    >>> intent['intent_type']
    'inventory'
"""
import re
from typing import Any, Dict, List, Optional, Set, TYPE_CHECKING

if TYPE_CHECKING:
    from utils.sre_tool_registry import SREDomain


class QueryPatterns:
    """
    Centralized query pattern definitions for EOL analysis.
    
    This class provides static methods and pattern lists for matching user queries
    against known patterns for EOL information, inventory requests, and related
    queries. All agents should use this class for consistent query interpretation.
    
    Attributes:
        EOL_PATTERNS: List of patterns indicating EOL information requests
        APPROACHING_EOL_PATTERNS: Patterns for approaching EOL queries  
        INVENTORY_PATTERNS: Regex patterns for inventory requests
        OS_INVENTORY_PATTERNS: Patterns specific to OS inventory
        SOFTWARE_INVENTORY_PATTERNS: Patterns specific to software inventory queries
    """
    
    # EOL-related patterns
    EOL_PATTERNS = [
        'end of life', 'end-of-life', 'eol', 'support status',
        'lifecycle', 'when does', 'reach end', 'support end',
        'retire', 'deprecated', 'sunset', 'maintenance end',
        'expiry', 'expires', 'expiration'
    ]
    
    # Approaching EOL patterns (more specific)
    APPROACHING_EOL_PATTERNS = [
        'approaching end', 'approaching eol', 'software approaching',
        'expiring soon', 'ending support', 'near end of life',
        'within a year', 'next year', 'soon to expire',
        'what software is approaching', 'which software is ending',
        'software nearing', 'close to eol'
    ]
    
    # Inventory-related regex patterns
    INVENTORY_PATTERNS = [
        r'show\s+(?:me\s+)?(?:the\s+)?inventory',
        r'(?:get|retrieve|fetch)\s+(?:the\s+)?inventory',
        r'what\s+softwares?',
        r'list\s+(?:all\s+)?(?:the\s+)?(?:installed\s+)?softwares?',
        r'inventory\s+(?:of|for)',
        r'softwares?\s+(?:inventory|list)',
        r'show\s+(?:all\s+)?softwares?',
        r'show\s+(?:all\s+)?applications',
        r'what\s+(?:is\s+)?installed'
    ]
    
    # OS inventory patterns
    OS_INVENTORY_PATTERNS = [
        r'(?:show|list|get)\s+(?:the\s+)?(?:operating\s+)?systems?',
        r'what\s+(?:operating\s+)?systems?',
        r'os\s+inventory',
        r'operating\s+system\s+(?:list|inventory)'
    ]

    # Software-focused inventory patterns
    SOFTWARE_INVENTORY_PATTERNS = [
        r'what\s+softwares?',
        r'list\s+(?:all\s+)?(?:the\s+)?(?:installed\s+)?softwares?',
        r'softwares?\s+(?:inventory|list)',
        r'show\s+(?:all\s+)?softwares?',
        r'show\s+(?:all\s+)?applications',
        r'what\s+(?:is\s+)?installed',
        r'softwares?\s+installed\s+on',
        r'applications?\s+installed\s+on'
    ]

    # ── Domain intent patterns for MCP tool routing ──
    # Each domain maps to MCP tool sources the orchestrator should include.
    # Patterns are matched as simple substring (lowercase) for low-latency classification.

    SRE_PATTERNS = [
        'health check', 'resource health', 'check health', 'incident', 'triage',
        'troubleshoot', 'diagnose', 'diagnostic', 'remediation', 'remediate',
        'restart', 'scale resource', 'bottleneck', 'performance metric',
        'performance issue', 'postmortem', 'root cause', 'mttr',
        'dora metric', 'alert correlation', 'correlate alert',
        'error log', 'search logs', 'log analysis',
        'container app health', 'aks health', 'app service health',
        'check_resource_health', 'triage_incident',
        'safe restart', 'execute restart', 'execute scale',
        'teams notification', 'teams alert', 'on-call',
        'plan remediation', 'remediation plan',
        'resource dependency', 'dependency chain',
        'capacity recommend', 'baseline metric',
        # VM health/status intents (must remain in SRE scope)
        'vm health', 'vms health', 'virtual machine health',
        'vm status', 'vms status', 'virtual machine status',
        'health of my vm', 'health of my vms', 'health of my virtual machines',
        # Container app list/discovery intents (SRE scope: container_app_list lives in sre source)
        'list container app', 'list my container app', 'show container app',
        'show my container app', 'what container app', 'display container app',
        'enumerate container app', 'get container app', 'container apps running',
        # High-signal incident/health terms
        '503', '500', '504', 'timeout', 'latency', 'unavailable',
        'outage', 'degraded', 'failure rate', 'error rate',
        'oom', 'out of memory', 'memory leak',
        'replica', 'replicas', 'crashloop', 'crashloopbackoff',
        'pod', 'container restart', 'service down', 'not responding',
    ]

    COST_PATTERNS = [
        'cost', 'spending', 'spend', 'budget', 'billing',
        'orphaned resource', 'unused resource', 'idle resource',
        'cost optim', 'cost recommend', 'cost analysis', 'cost anomal',
        'right-sizing', 'reserved instance', 'savings',
        'cost breakdown', 'cost spike',
    ]

    SECURITY_PATTERNS = [
        'security score', 'secure score', 'security posture',
        'security recommend', 'compliance', 'cis benchmark',
        'nist', 'pci-dss', 'pci dss', 'azure policy',
        'defender for cloud', 'security finding',
        'vulnerability', 'attack surface',
    ]

    SLO_PATTERNS = [
        'slo', 'sli', 'service level', 'error budget',
        'burn rate', 'reliability target', 'availability target',
        'latency target', 'uptime', 'nines', '99.9', '99.99', '99.999',
        'three nines', 'four nines', 'five nines',
    ]

    MONITORING_PATTERNS = [
        'workbook', 'monitor resource', 'monitoring',
        'kql query', 'kql', 'log analytics query',
        'alert rule', 'scheduled query', 'monitor community',
        'azure monitor', 'deploy workbook', 'deploy alert',
        'deploy query', 'saved search',
    ]

    APP_INSIGHTS_PATTERNS = [
        'app insights', 'application insights', 'distributed trac',
        'trace', 'operation id', 'request telemetry',
        'dependency map', 'service dependency', 'p95', 'p99',
        'request latency', 'failure rate',
    ]

    RESOURCE_MANAGEMENT_PATTERNS = [
        'subscription', 'resource group', 'list resource',
        'show resource', 'azure resource', 'tenant',
        'virtual machine', 'virtual network', 'storage account', 'key vault',
        'network security', 'vnet', 'subnet', 'nsg',
        'load balancer', 'public ip', 'dns', 'route table',
        'app service plan', 'function app',
        'container registry', 'acr',
        'event hub', 'service bus',
        'cosmos', 'sql database', 'mysql', 'postgres',
        'resource groups', 'vnets', 'subnets',
    ]

    NETWORK_PATTERNS = [
        'virtual network', 'vnet', 'vnets', 'subnet', 'subnets',
        'nsg', 'network security group',
        'route table', 'udr', 'effective route',
        'vpn gateway', 'express route', 'expressroute',
        'app gateway', 'application gateway', 'waf',
        'private endpoint', 'private link',
        'dns resolution', 'dns lookup',
        'network connectivity', 'connectivity test',
        'peering', 'vnet peering',
        'firewall', 'azure firewall',
        'load balancer', 'public ip', 'network interface',
    ]

    CLI_PATTERNS = [
        'container app', 'containerapp',
        'az command', 'az cli', 'run command',
        'avd', 'virtual desktop', 'hostpool',
    ]

    CAPABILITIES_PATTERNS = [
        'what can you', 'what can you do', 'what can you help',
        'capabilities', 'help me with', 'what do you do',
        'example prompt', 'how to use', 'available tools',
        'what tools', 'show capabilities', 'describe capabilities',
        'what are you', 'what are your',
    ]

    # Map domain → MCP source labels that should be included
    # when that domain is detected. "always" sources are included regardless.
    # 'meta' includes monitor_agent and sre_agent meta-tools.
    DOMAIN_SOURCE_MAP: Dict[str, List[str]] = {
        'sre':                 ['sre', 'azure_cli', 'meta'],
        'cost':                ['sre', 'meta'],
        'security':            ['sre', 'meta'],
        'slo':                 ['sre', 'meta'],
        'app_insights':        ['sre', 'meta'],
        'monitoring':          ['monitor', 'azure_cli', 'meta'],
        'eol':                 ['os_eol', 'inventory'],
        'inventory':           ['inventory', 'os_eol'],
        'resource_management': ['azure', 'azure_cli'],
        'network':             ['network', 'azure'],
        'cli':                 ['azure_cli'],
        'capabilities':        ['meta'],
    }

    # Sources to always include (meta-tools, general discovery)
    ALWAYS_INCLUDE_SOURCES: List[str] = []  # populated by ToolRouter with meta-tools

    @classmethod
    def classify_domains(cls, query: str) -> Dict[str, bool]:
        """Classify which operational domains a query belongs to.

        Returns a dict of domain_name → bool for all known domains.
        Multiple domains can be True simultaneously (e.g., a cost + SRE query).
        """
        q = query.lower()
        vm_health_intent = bool(re.search(r"\b(vms?|virtual\s+machines?)\b", q)) and bool(
            re.search(r"\b(health|healthy|status|unhealthy|degraded|availability)\b", q),
        )

        return {
            'sre': vm_health_intent or any(p in q for p in cls.SRE_PATTERNS),
            'cost': any(p in q for p in cls.COST_PATTERNS),
            'security': any(p in q for p in cls.SECURITY_PATTERNS),
            'slo': any(p in q for p in cls.SLO_PATTERNS),
            'monitoring': any(p in q for p in cls.MONITORING_PATTERNS),
            'app_insights': any(p in q for p in cls.APP_INSIGHTS_PATTERNS),
            'eol': cls.matches_eol_pattern(query) or cls.matches_approaching_eol_pattern(query),
            'inventory': cls.matches_inventory_pattern(query),
            'resource_management': any(p in q for p in cls.RESOURCE_MANAGEMENT_PATTERNS),
            'network': any(p in q for p in cls.NETWORK_PATTERNS),
            'cli': any(p in q for p in cls.CLI_PATTERNS),
            'capabilities': any(p in q for p in cls.CAPABILITIES_PATTERNS),
        }

    @classmethod
    def get_relevant_sources(cls, query: str) -> List[str]:
        """Return the list of MCP source labels relevant to the query.

        If no domain matches (ambiguous/novel query), returns an empty list
        which signals the caller to include ALL sources (no filtering).
        """
        domains = cls.classify_domains(query)
        active_domains = [d for d, active in domains.items() if active]

        if not active_domains:
            return []  # No confident match → caller should use full catalog

        sources: set[str] = set()
        for domain in active_domains:
            for src in cls.DOMAIN_SOURCE_MAP.get(domain, []):
                sources.add(src)

        return sorted(sources)
    
    @classmethod
    def matches_eol_pattern(cls, query: str) -> bool:
        """
        Check if query matches EOL patterns
        
        Args:
            query: User query string
            
        Returns:
            True if query contains EOL-related terms
        """
        query_lower = query.lower()
        return any(pattern in query_lower for pattern in cls.EOL_PATTERNS)
    
    @classmethod
    def matches_approaching_eol_pattern(cls, query: str) -> bool:
        """
        Check if query matches approaching EOL patterns
        
        Args:
            query: User query string
            
        Returns:
            True if query asks about software approaching EOL
        """
        query_lower = query.lower()
        return any(pattern in query_lower for pattern in cls.APPROACHING_EOL_PATTERNS)
    
    @classmethod
    def matches_inventory_pattern(cls, query: str) -> bool:
        """
        Check if query matches inventory patterns
        
        Args:
            query: User query string
            
        Returns:
            True if query requests software inventory
        """
        return any(re.search(pattern, query, re.IGNORECASE) for pattern in cls.INVENTORY_PATTERNS)
    
    @classmethod
    def matches_os_inventory_pattern(cls, query: str) -> bool:
        """
        Check if query matches OS inventory patterns
        
        Args:
            query: User query string
            
        Returns:
            True if query requests OS inventory
        """
        return any(re.search(pattern, query, re.IGNORECASE) for pattern in cls.OS_INVENTORY_PATTERNS)

    @classmethod
    def matches_software_inventory_pattern(cls, query: str) -> bool:
        """Check if query matches software inventory patterns."""
        return any(
            re.search(pattern, query, re.IGNORECASE)
            for pattern in cls.SOFTWARE_INVENTORY_PATTERNS
        )
    
    @classmethod
    def get_matched_patterns(cls, query: str, pattern_list: List[str], use_regex: bool = False) -> List[str]:
        """
        Get list of patterns that match the query
        
        Args:
            query: User query string
            pattern_list: List of patterns to check
            use_regex: Whether patterns are regex (default False for simple string matching)
            
        Returns:
            List of matched patterns
        """
        if use_regex:
            return [pattern for pattern in pattern_list if re.search(pattern, query, re.IGNORECASE)]
        else:
            query_lower = query.lower()
            return [pattern for pattern in pattern_list if pattern in query_lower]
    
    @classmethod
    def analyze_query_intent(cls, query: str) -> Dict[str, Any]:
        """
        Analyze user query and classify its intent.
        
        Performs comprehensive analysis of a user query to determine what type
        of information or action is being requested. This method checks the query
        against multiple pattern lists and returns a detailed classification.
        
        The intent analysis is used by agents to determine which specialized
        agent(s) should handle the query and what type of response is expected.
        
        Args:
            query: User query string to analyze. Should be natural language text
                  such as "what is the EOL for Windows Server 2016" or
                  "show me software inventory approaching end of life".
            
        Returns:
            Dictionary containing detailed intent analysis with the following keys:
                - query (str): Original query text
                - is_eol_query (bool): True if asking about EOL dates/status
                - is_approaching_eol_query (bool): True if asking about upcoming EOL
                - is_inventory_query (bool): True if requesting software inventory
                - is_os_inventory_query (bool): True if requesting OS inventory
                - matched_eol_patterns (List[str]): EOL patterns that matched
                - matched_approaching_patterns (List[str]): Approaching EOL patterns matched
                - intent_type (str): Primary intent classification
                - confidence (float): Confidence score 0.0-1.0
        
        Example:
            >>> intent = QueryPatterns.analyze_query_intent(
            ...     "show me software approaching end of life"
            ... )
            >>> intent['intent_type']
            'approaching_eol'
            >>> intent['confidence']
            0.9
        """
        return {
            "query": query,
            "is_eol_query": cls.matches_eol_pattern(query),
            "is_approaching_eol_query": cls.matches_approaching_eol_pattern(query),
            "is_inventory_query": cls.matches_inventory_pattern(query),
            "is_os_inventory_query": cls.matches_os_inventory_pattern(query),
            "is_software_inventory_query": cls.matches_software_inventory_pattern(query),
            "matched_eol_patterns": cls.get_matched_patterns(query, cls.EOL_PATTERNS),
            "matched_approaching_patterns": cls.get_matched_patterns(query, cls.APPROACHING_EOL_PATTERNS),
            "matched_inventory_patterns": cls.get_matched_patterns(query, cls.INVENTORY_PATTERNS, use_regex=True),
            "matched_os_patterns": cls.get_matched_patterns(query, cls.OS_INVENTORY_PATTERNS, use_regex=True),
            "matched_software_inventory_patterns": cls.get_matched_patterns(
                query,
                cls.SOFTWARE_INVENTORY_PATTERNS,
                use_regex=True,
            ),
        }



def classify_sre_domain(query: str) -> "SREDomain":
    """Map a user query to its primary SREDomain for tool-subset selection.

    Uses QueryPatterns.classify_domains() (cheap substring matching) to detect
    the dominant SRE sub-domain.  Falls back to GENERAL when ambiguous.

    Returns:
        SREDomain enum value.  Deferred import so callers without SREToolRegistry
        installed do not see an ImportError at module load time.
    """
    try:
        try:
            from app.agentic.eol.utils.sre_tool_registry import SREDomain
        except ModuleNotFoundError:
            from utils.sre_tool_registry import SREDomain  # type: ignore[import-not-found]
    except Exception:
        # If SREDomain is not available, return a sentinel string the caller
        # can handle (sre_orchestrator always guards with hasattr checks).
        return "general"  # type: ignore[return-value]

    q = query.lower()
    domains = QueryPatterns.classify_domains(query)

    # Priority order mirrors SREGateway's triage heuristic:
    # incident > health > performance > rca > cost/security > remediation
    if domains.get("sre"):
        # Refine within SRE using tighter sub-domain signals
        if any(p in q for p in ("root cause", "rca", "postmortem", "post-mortem", "why did", "cause of", "trace dependency")):
            return SREDomain.RCA
        if any(p in q for p in ("restart", "remediation", "remediate", "scale", "fix it", "fix this", "resolve", "rollback", "clear cache")):
            return SREDomain.REMEDIATION
        if any(p in q for p in ("incident", "triage", "alert", "outage", "error log", "log search", "failed request", "spike", "exception")):
            return SREDomain.INCIDENT
        if any(p in q for p in ("performance", "slow", "latency", "p95", "p99", "cpu", "memory", "bottleneck", "throughput", "anomaly", "burn rate")):
            return SREDomain.PERFORMANCE
        if any(p in q for p in ("health", "up", "down", "unavailable", "503", "500", "504", "timeout", "status", "diagnostic")):
            return SREDomain.HEALTH
        return SREDomain.GENERAL

    if domains.get("cost") or domains.get("security"):
        return SREDomain.COST_SECURITY

    return SREDomain.GENERAL


# Convenience functions for backward compatibility
def matches_eol_pattern(query: str) -> bool:
    """Check if query matches EOL patterns"""
    return QueryPatterns.matches_eol_pattern(query)


def matches_approaching_eol_pattern(query: str) -> bool:
    """Check if query matches approaching EOL patterns"""
    return QueryPatterns.matches_approaching_eol_pattern(query)


def matches_inventory_pattern(query: str) -> bool:
    """Check if query matches inventory patterns"""
    return QueryPatterns.matches_inventory_pattern(query)


def analyze_query_intent(query: str) -> Dict[str, Any]:
    """Analyze query intent"""
    return QueryPatterns.analyze_query_intent(query)
