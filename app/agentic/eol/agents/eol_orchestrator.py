"""
EOL Orchestrator Agent - Streamlined and fully autonomous EOL data gathering for eol.html interface
"""
import asyncio
import uuid
import re
import logging
import time
from typing import Dict, List, Any, Optional, Union
from datetime import datetime, timedelta

from .endoflife_agent import EndOfLifeAgent
from .microsoft_agent import MicrosoftEOLAgent
from .redhat_agent import RedHatEOLAgent
from .ubuntu_agent import UbuntuEOLAgent
from .inventory_agent import InventoryAgent
from .os_inventory_agent import OSInventoryAgent
from .software_inventory_agent import SoftwareInventoryAgent
from .azure_ai_agent import AzureAIAgentEOLAgent
from .oracle_agent import OracleEOLAgent
from .vmware_agent import VMwareEOLAgent
from .apache_agent import ApacheEOLAgent
from .nodejs_agent import NodeJSEOLAgent
from .postgresql_agent import PostgreSQLEOLAgent
from .php_agent import PHPEOLAgent
from .python_agent import PythonEOLAgent
from .playwright_agent import PlaywrightEOLAgent

# Import logger
try:
    from utils import get_logger
    logger = get_logger(__name__)
except ImportError:
    import logging
    logger = logging.getLogger(__name__)

class EOLOrchestratorAgent:
    """
    Autonomous EOL orchestrator that efficiently coordinates EOL data gathering
    from multiple specialized agents with intelligent routing and caching.
    """
    
    def __init__(self):
        self.session_id = str(uuid.uuid4())
        self.start_time = datetime.utcnow()
        
        # Replace Cosmos-backed comms with in-memory log (per process)
        self._comms_log: List[Dict[str, Any]] = []
        self.agent_name = "eol_orchestrator"
        
        # EOL Response Tracking - Track all agent responses for detailed history
        self.eol_agent_responses = []

        # Check if mock mode is enabled via environment variable
        import os
        use_mock = os.getenv("USE_MOCK_DATA", "false").lower() == "true"
        
        # Initialize inventory agents (with mock support)
        if use_mock:
            try:
                from tests.mock_agents import MockSoftwareInventoryAgent, MockOSInventoryAgent
                logger.info("🧪 Initializing EOL Orchestrator in MOCK MODE")
                software_agent = MockSoftwareInventoryAgent()
                os_agent = MockOSInventoryAgent()
            except ImportError as e:
                logger.warning(f"Failed to import mock agents: {e}. Falling back to real agents.")
                software_agent = SoftwareInventoryAgent()
                os_agent = OSInventoryAgent()
        else:
            software_agent = SoftwareInventoryAgent()
            os_agent = OSInventoryAgent()

        # Initialize only essential agents for EOL analysis
        self.agents = {
            # Inventory agents
            "inventory": InventoryAgent(),
            "os_inventory": os_agent,
            "software_inventory": software_agent,
            
            # EOL data sources (prioritized by reliability)
            "endoflife": EndOfLifeAgent(),
            "microsoft": MicrosoftEOLAgent(),
            "redhat": RedHatEOLAgent(),
            "ubuntu": UbuntuEOLAgent(),
            "oracle": OracleEOLAgent(),
            "vmware": VMwareEOLAgent(),
            "apache": ApacheEOLAgent(),
            "nodejs": NodeJSEOLAgent(),
            "postgresql": PostgreSQLEOLAgent(),
            "php": PHPEOLAgent(),
            "python": PythonEOLAgent(),
            "azure_ai": AzureAIAgentEOLAgent(),
            "playwright": PlaywrightEOLAgent(),  # Web search fallback agent
        }
        
        # Agent routing map for efficient lookups
        self.vendor_routing = {
            # Microsoft ecosystem
            "microsoft": ["windows", "office", "sql server", "iis", "visual studio", ".net", 
                         "azure", "sharepoint", "exchange", "teams", "power bi", "dynamics"],
            
            # Red Hat ecosystem  
            "redhat": ["red hat", "rhel", "centos", "fedora", "openshift", "ansible"],
            
            # Ubuntu ecosystem
            "ubuntu": ["ubuntu", "canonical", "snap"],
            
            # Oracle ecosystem
            "oracle": ["oracle", "java", "jdk", "jre", "openjdk", "mysql", "virtualbox",
                      "solaris", "weblogic", "graalvm"],
            
            # VMware ecosystem
            "vmware": ["vmware", "vsphere", "esxi", "vcenter", "workstation", "fusion",
                      "nsx", "vsan", "vrealize", "horizon", "tanzu"],
            
            # Apache ecosystem
            "apache": ["apache", "httpd", "tomcat", "kafka", "spark", "maven", "cassandra",
                      "solr", "lucene", "struts", "camel", "activemq", "zookeeper"],
            
            # Node.js ecosystem
            "nodejs": ["node", "nodejs", "npm", "yarn", "express", "react", "vue", "angular",
                      "next", "gatsby", "electron", "typescript"],
            
            # PostgreSQL ecosystem
            "postgresql": ["postgresql", "postgres", "postgis", "pgbouncer", "timescaledb"],
            
            # PHP ecosystem
            "php": ["php", "composer", "laravel", "symfony", "drupal", "wordpress"],
            
            # Python ecosystem
            "python": ["python", "pip", "django", "flask", "pandas", "numpy", "jupyter"]
        }
        
        # Cache for EOL results (in-memory for session)
        self.eol_cache = {}
        self.cache_ttl = 3600  # 1 hour cache
        
        logger.info(f"🚀 Autonomous EOL Orchestrator initialized with {len(self.agents)} agents")
        
    async def log_communication(self, agent_name: str, action: str, data: Dict[str, Any], result: Optional[Dict[str, Any]] = None):
        """Log agent communication (in-memory only; Cosmos removed)"""
        try:
            communication = {
                "id": str(uuid.uuid4()),
                "sessionId": self.session_id,
                "timestamp": datetime.utcnow().isoformat(),
                "agentName": agent_name,
                "action": action,
                "input": data,
                "output": result,
            }
            # Keep last 100 entries
            self._comms_log.append(communication)
            if len(self._comms_log) > 100:
                self._comms_log = self._comms_log[-100:]
        except Exception as e:
            logger.error(f"Error logging communication: {str(e)}")
            # Don't append anything if there's an error

    async def get_os_inventory_with_eol(self, days: int = 90):
        """
        Get OS inventory with automatic EOL analysis - core function for inventory.html
        """
        try:
            start_time = time.time()
            logger.info(f"🔍 Starting OS inventory with EOL analysis (last {days} days)")
            
            # Get OS inventory
            os_agent = self.agents["os_inventory"]
            os_inventory_result = await os_agent.get_os_inventory(days=days)
            
            if not os_inventory_result.get("success") or not os_inventory_result.get("data"):
                return {
                    "success": False,
                    "error": "Failed to retrieve OS inventory",
                    "data": []
                }
            
            os_inventory = os_inventory_result["data"]
            logger.info(f"📊 Retrieved {len(os_inventory)} OS inventory items")
            
            # Process each OS item for EOL analysis
            eol_analysis_tasks = []
            for os_item in os_inventory:
                task = self._analyze_os_item_eol(os_item)
                eol_analysis_tasks.append(task)
            
            # Execute EOL analysis in parallel with concurrency limit
            semaphore = asyncio.Semaphore(10)  # Limit concurrent requests
            async def sem_task(task):
                async with semaphore:
                    return await task
            
            eol_results = await asyncio.gather(
                *[sem_task(task) for task in eol_analysis_tasks],
                return_exceptions=True
            )
            
            # Combine OS inventory with EOL data
            enriched_inventory = []
            for i, os_item in enumerate(os_inventory):
                eol_result = eol_results[i] if i < len(eol_results) else None
                
                enriched_item = {**os_item}  # Copy original item
                
                if isinstance(eol_result, dict) and eol_result.get("success"):
                    eol_data = eol_result.get("eol_data", {})
                    enriched_item.update({
                        "eol_date": eol_data.get("eol_date"),
                        "eol_status": eol_data.get("status", "Unknown"),
                        "support_status": eol_data.get("support_status"),
                        "risk_level": eol_data.get("risk_level", "unknown"),
                        "days_until_eol": eol_data.get("days_until_eol"),
                        "eol_source": eol_data.get("source"),
                        "eol_confidence": eol_data.get("confidence", 0.5)
                    })
                else:
                    enriched_item.update({
                        "eol_date": None,
                        "eol_status": "Unknown",
                        "support_status": "Unknown",
                        "risk_level": "unknown",
                        "days_until_eol": None,
                        "eol_source": None,
                        "eol_confidence": 0.0
                    })
                
                enriched_inventory.append(enriched_item)
            
            # Calculate summary statistics
            total_items = len(enriched_inventory)
            items_with_eol = len([item for item in enriched_inventory if item.get("eol_date")])
            critical_items = len([item for item in enriched_inventory if item.get("risk_level") == "critical"])
            high_risk_items = len([item for item in enriched_inventory if item.get("risk_level") == "high"])
            
            execution_time = time.time() - start_time
            logger.info(f"✅ OS inventory EOL analysis completed in {execution_time:.2f}s")
            logger.info(f"📈 {items_with_eol}/{total_items} items have EOL data, {critical_items} critical, {high_risk_items} high risk")
            
            return {
                "success": True,
                "data": enriched_inventory,
                "summary": {
                    "total_items": total_items,
                    "items_with_eol": items_with_eol,
                    "critical_items": critical_items,
                    "high_risk_items": high_risk_items,
                    "analysis_time": execution_time,
                    "cache_hits": sum(1 for result in eol_results if isinstance(result, dict) and result.get("cache_hit", False))
                },
                "session_id": self.session_id,
                "timestamp": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"❌ Error in OS inventory EOL analysis: {str(e)}")
            return {
                "success": False,
                "error": f"OS inventory EOL analysis failed: {str(e)}",
                "data": []
            }

    async def _analyze_os_item_eol(self, os_item):
        """
        Analyze a single OS item for EOL information
        """
        try:
            os_name = os_item.get("os_name") or os_item.get("name", "")
            os_version = os_item.get("os_version") or os_item.get("version", "")
            
            if not os_name:
                return {"success": False, "error": "No OS name provided"}
            
            # Create cache key
            cache_key = f"os_eol_{os_name}_{os_version}".lower().replace(" ", "_")
            
            # Check cache first
            if cache_key in self.eol_cache:
                cache_entry = self.eol_cache[cache_key]
                if datetime.utcnow() - cache_entry["timestamp"] < timedelta(seconds=self.cache_ttl):
                    return {"success": True, "eol_data": cache_entry["data"], "cache_hit": True}
            
            # Get EOL data using autonomous routing
            eol_result = await self.get_autonomous_eol_data(os_name, os_version, item_type="os")
            
            if eol_result.get("success") and eol_result.get("data"):
                eol_data = self._process_eol_data(eol_result["data"], os_name, os_version)
                
                # Cache the result
                self.eol_cache[cache_key] = {
                    "data": eol_data,
                    "timestamp": datetime.utcnow()
                }
                
                return {"success": True, "eol_data": eol_data, "cache_hit": False}
            
            return {"success": False, "error": "No EOL data found"}
            
        except Exception as e:
            logger.error(f"Error analyzing OS item EOL: {str(e)}")
            return {"success": False, "error": str(e)}

    async def get_autonomous_eol_data(self, software_name, version=None, item_type="software", search_internet_only=False):
        """
        Autonomous EOL data retrieval with intelligent agent routing
        
        Args:
            software_name: Name of the software to search for
            version: Version of the software (optional)
            item_type: Type of item (software, os, etc.)
            search_internet_only: If True, skip all specialized agents and use only Playwright web search
        """
        try:
            await self.log_communication("eol_orchestrator", "get_autonomous_eol_data", {
                "software_name": software_name,
                "version": version,
                "item_type": item_type,
                "search_internet_only": search_internet_only
            })
            
            software_name_lower = software_name.lower()
            
            # If search_internet_only is True, use ONLY the playwright agent
            if search_internet_only:
                logger.info(f"🌐 Internet-only search mode: Using Playwright agent exclusively for '{software_name}'")
                target_agents = ["playwright"]
                
                await self.log_communication("eol_orchestrator", "agent_selection", {
                    "software_name": software_name,
                    "version": version,
                    "selected_agents": target_agents,
                    "selection_method": "internet_only_mode"
                })
            else:
                # Determine optimal agents for this software
                target_agents = self._route_to_agents(software_name_lower, item_type)
                
                # add fallback agent (always include EndOfLifeAgent as fallback)
                if "endoflife" not in target_agents:
                    target_agents.append("endoflife")
                
                await self.log_communication("eol_orchestrator", "agent_selection", {
                    "software_name": software_name,
                    "version": version,
                    "selected_agents": target_agents,
                    "selection_method": "intelligent_routing"
                })
            
            logger.debug(f"🎯 Routing '{software_name}' to agents: {target_agents}")
            
            # Execute searches in priority order with early termination
            best_result = None
            best_confidence = 0.0
            best_agent_name = None
            
            for agent_name in target_agents:
                if agent_name not in self.agents:
                    continue
                
                try:
                    agent = self.agents[agent_name]
                    
                    await self.log_communication(agent_name, "get_eol_data", {
                        "software_name": software_name,
                        "version": version
                    })
                    
                    # Call appropriate method based on agent capabilities
                    if hasattr(agent, 'get_eol_data'):
                        result = await agent.get_eol_data(software_name, version)
                    elif hasattr(agent, 'search_eol'):
                        result = await agent.search_eol(software_name, version)
                    else:
                        await self.log_communication(agent_name, "get_eol_data", {
                            "software_name": software_name,
                            "version": version
                        }, {"error": "No compatible method found"})
                        continue
                    
                    # All agents now return standardized responses, no normalization needed
                    
                    # Check if the response indicates success
                    if result and result.get("success") and result.get("data"):
                        confidence = self._calculate_confidence(result, agent_name, software_name)
                        
                        await self.log_communication(agent_name, "get_eol_data", {
                            "software_name": software_name,
                            "version": version
                        }, {
                            "success": True,
                            "confidence": confidence,
                            "data_found": True,
                            "standardized": True
                        })
                        
                        if confidence > best_confidence:
                            best_result = result
                            best_confidence = confidence
                            best_agent_name = agent_name
                            
                            # Early termination for high-confidence vendor-specific results
                            if confidence >= 0.9 and agent_name != "endoflife":
                                logger.debug(f"✅ Early termination: high confidence result from {agent_name}")
                                break
                    else:
                        # Log failed attempt with more details
                        error_msg = result.get("error", {}).get("message", "No valid EOL data found") if result else "No response"
                        await self.log_communication(agent_name, "get_eol_data", {
                            "software_name": software_name,
                            "version": version
                        }, {
                            "success": False, 
                            "data_found": False,
                            "error": error_msg,
                            "standardized": bool(result)
                        })
                
                except Exception as e:
                    logger.warning(f"Agent {agent_name} failed for {software_name}: {str(e)}")
                    await self.log_communication(agent_name, "get_eol_data", {
                        "software_name": software_name,
                        "version": version
                    }, {"error": str(e)})
                    continue
            
            if best_result:
                # Ensure the result has proper success flag and data structure
                if "success" not in best_result:
                    best_result["success"] = True
                
                best_result["confidence"] = best_confidence
                
                # Ensure agent_used is available at top level for frontend compatibility
                if best_agent_name:
                    best_result["agent_used"] = best_agent_name
                    # Also ensure it's in the data object if data exists
                    if "data" in best_result and isinstance(best_result["data"], dict):
                        best_result["data"]["agent_used"] = best_agent_name
                elif "agent_used" not in best_result:
                    # Fallback: try to get agent_used from data object
                    data = best_result.get("data", {})
                    if isinstance(data, dict) and "agent_used" in data:
                        best_result["agent_used"] = data["agent_used"]
                    elif "source" in best_result:
                        best_result["agent_used"] = best_result["source"]
                    else:
                        # Last resort: use first available agent
                        for agent_name in target_agents:
                            if agent_name in self.agents:
                                best_result["agent_used"] = agent_name
                                break
                
                await self.log_communication("eol_orchestrator", "get_autonomous_eol_data", {
                    "software_name": software_name,
                    "version": version
                }, {
                    "success": True,
                    "best_agent": best_result.get("source", "unknown"),
                    "agent_used": best_result.get("agent_used", "unknown"),
                    "confidence": best_confidence,
                    "data_structure": "validated"
                })
                
                # Include communication history in response for frontend display
                best_result["communications"] = self.get_recent_communications()
                
                # Track the EOL agent response for history
                start_time = time.time()
                response_time = time.time() - start_time
                self._track_eol_agent_response(
                    agent_name=best_result.get("agent_used", "unknown"),
                    software_name=software_name,
                    software_version=version,
                    eol_result=best_result,
                    response_time=response_time,
                    query_type="autonomous_search"
                )
                
                logger.info(f"✅ EOL data found for {software_name} (confidence: {best_confidence:.2f}, agent: {best_result.get('agent_used', 'unknown')})")
                return best_result
            
            # Determine appropriate error message based on search mode
            if search_internet_only:
                error_message = "No EOL data found via internet search (Playwright)"
                logger.warning(f"❌ Internet-only search failed for {software_name}")
            else:
                error_message = "No EOL data found from any source including Playwright fallback"
                logger.warning(f"❌ All agents failed to find EOL data for {software_name}")
            
            await self.log_communication("eol_orchestrator", "get_autonomous_eol_data", {
                "software_name": software_name,
                "version": version
            }, {"success": False, "error": error_message})
            
            failure_response = {
                "success": False, 
                "error": error_message,
                "agent_used": "playwright" if search_internet_only else "orchestrator",
                "search_mode": "internet_only" if search_internet_only else "intelligent_routing",
                "communications": self.get_recent_communications()
            }
            
            # Track the failed search for history
            start_time = time.time()
            response_time = time.time() - start_time
            self._track_eol_agent_response(
                agent_name="orchestrator",
                software_name=software_name,
                software_version=version,
                eol_result=failure_response,
                response_time=response_time,
                query_type="autonomous_search"
            )
            
            return failure_response
            
        except Exception as e:
            logger.error(f"Error in autonomous EOL data retrieval: {str(e)}")
            await self.log_communication("eol_orchestrator", "get_autonomous_eol_data", {
                "software_name": software_name,
                "version": version
            }, {"error": str(e)})
            
            error_response = {
                "success": False, 
                "error": str(e),
                "agent_used": "orchestrator",
                "communications": self.get_recent_communications()
            }
            return error_response

    def _route_to_agents(self, software_name_lower, item_type="software"):
        """
        Intelligent agent routing based on software name and type
        """
        target_agents = []
        
        # Vendor-specific routing for higher accuracy
        for vendor, keywords in self.vendor_routing.items():
            if any(keyword in software_name_lower for keyword in keywords):
                target_agents.append(vendor)
        
        # Special handling for OS items
        if item_type == "os":
            if "windows" in software_name_lower:
                target_agents.insert(0, "microsoft")  # Prioritize Microsoft for Windows
            elif any(linux in software_name_lower for linux in ["ubuntu", "debian", "linux"]):
                target_agents.insert(0, "ubuntu")
            elif any(rh in software_name_lower for rh in ["red hat", "rhel", "centos", "fedora"]):
                target_agents.insert(0, "redhat")
        
        # Remove duplicates while preserving order
        seen = set()
        unique_agents = []
        for agent in target_agents:
            if agent not in seen:
                seen.add(agent)
                unique_agents.append(agent)
        
        return unique_agents

    def _calculate_confidence(self, result, agent_name, software_name):
        """
        Calculate confidence score for EOL result
        """
        base_confidence = 0.5
        
        # Vendor-specific agents get higher confidence for their products
        if agent_name in self.vendor_routing:
            keywords = self.vendor_routing[agent_name]
            if any(keyword in software_name.lower() for keyword in keywords):
                base_confidence = 0.9
        
        # Boost confidence based on data quality
        data = result.get("data", {})
        if data.get("eol_date"):
            base_confidence += 0.2
        if data.get("support_status"):
            base_confidence += 0.1
        if data.get("release_date"):
            base_confidence += 0.1
        
        return min(base_confidence, 1.0)

    def _process_eol_data(self, raw_data, software_name, version):
        """
        Process and standardize EOL data from various sources
        """
        processed = {
            "software_name": software_name,
            "version": version,
            "eol_date": self._extract_eol_date(raw_data),
            "status": "Unknown",
            "support_status": raw_data.get("support_status", "Unknown"),
            "risk_level": "unknown",
            "days_until_eol": None,
            "source": raw_data.get("source", "Unknown"),
            "confidence": raw_data.get("confidence", 0.5)
        }
        
        # Calculate risk level and days until EOL
        if processed["eol_date"]:
            try:
                eol_date = datetime.fromisoformat(processed["eol_date"].replace('Z', '+00:00'))
                now = datetime.utcnow().replace(tzinfo=eol_date.tzinfo)
                days_diff = (eol_date - now).days
                
                processed["days_until_eol"] = days_diff
                
                if days_diff < 0:
                    processed["status"] = "End of Life"
                    processed["risk_level"] = "critical"
                elif days_diff <= 90:
                    processed["status"] = "Critical - EOL Soon"
                    processed["risk_level"] = "critical"
                elif days_diff <= 365:
                    processed["status"] = "High Risk - EOL Within 1 Year"
                    processed["risk_level"] = "high"
                elif days_diff <= 730:
                    processed["status"] = "Medium Risk - EOL Within 2 Years"
                    processed["risk_level"] = "medium"
                else:
                    processed["status"] = "Active Support"
                    processed["risk_level"] = "low"
                    
            except Exception as e:
                logger.warning(f"Error calculating EOL risk for {software_name}: {str(e)}")
        
        return processed

    def _extract_eol_date(self, data):
        """
        Extract EOL date from various data formats
        """
        # Common EOL date field names
        date_fields = ["eol_date", "end_of_life", "eol", "support_end", "end_date", "retirement_date"]
        
        for field in date_fields:
            if field in data and data[field]:
                date_value = data[field]
                if isinstance(date_value, str):
                    return date_value
                elif isinstance(date_value, datetime):
                    return date_value.isoformat()
        
        return None

    # Legacy compatibility methods for existing API endpoints
    async def get_eol_data(self, software_name, version=None):
        """Legacy method for backward compatibility"""
        return await self.get_autonomous_eol_data(software_name, version)

    async def get_software_inventory(self, days=90, include_eol=True, use_cache=True):
        """Legacy method for backward compatibility"""
        software_agent = self.agents["software_inventory"]
        return await software_agent.get_software_inventory(days=days)

    async def health_check(self):
        """Quick health check for the orchestrator and its agents"""
        try:
            status = {
                "orchestrator": {
                    "status": "healthy",
                    "session_id": self.session_id,
                    "uptime_seconds": (datetime.utcnow() - self.start_time).total_seconds(),
                    "cache_size": len(self.eol_cache),
                    "agents_count": len(self.agents)
                },
                "agents": {}
            }
            
            # Quick agent checks (non-blocking)
            for agent_name, agent in list(self.agents.items())[:5]:  # Check first 5 agents
                try:
                    if hasattr(agent, 'health_check'):
                        agent_status = await asyncio.wait_for(agent.health_check(), timeout=2.0)
                        status["agents"][agent_name] = agent_status
                    else:
                        status["agents"][agent_name] = {"status": "available"}
                except Exception:
                    status["agents"][agent_name] = {"status": "timeout"}
            
            return {"success": True, "data": status}
            
        except Exception as e:
            return {"success": False, "error": str(e)}

    def clear_communications(self):
        """
        Clear communications cache and reset session state
        """
        try:
            # Clear communications log
            previous_count = len(self._comms_log)
            self._comms_log.clear()
            
            # Clear EOL cache
            cache_size_before = len(self.eol_cache)
            self.eol_cache.clear()
            
            # Reset session ID
            old_session_id = self.session_id
            self.session_id = str(uuid.uuid4())
            
            # Reset start time
            self.start_time = datetime.utcnow()
            
            logger.info(f"🧹 Communications cleared: {previous_count} communications, cache ({cache_size_before} items), session {old_session_id} -> {self.session_id}")
            
            return {
                "success": True,
                "message": f"Cleared {previous_count} communications from session {self.session_id}",
                "details": {
                    "communications_cleared": previous_count,
                    "cache_items_cleared": cache_size_before,
                    "old_session_id": old_session_id,
                    "new_session_id": self.session_id,
                    "timestamp": datetime.utcnow().isoformat()
                }
            }
            
        except Exception as e:
            logger.error(f"❌ Error clearing communications: {str(e)}")
            return {
                "success": False,
                "error": f"Failed to clear communications: {str(e)}"
            }

    def get_recent_communications(self):
        """
        Get recent communications for display in frontend
        Returns actual communication log entries from agents
        """
        try:
            # Return from in-memory log with proper formatting for frontend
            communications = []
            
            # Ensure _comms_log exists and is a list
            if not hasattr(self, '_comms_log') or not isinstance(self._comms_log, list):
                self._comms_log = []
            
            # Convert internal log format to frontend format
            for comm in reversed(self._comms_log[-20:]):  # Get last 20 communications
                # Skip None or invalid communication entries
                if comm is None or not isinstance(comm, dict):
                    continue
                
                # Extra safety check - ensure comm is not None before processing
                try:
                    communications.append({
                        "timestamp": comm.get("timestamp", datetime.utcnow().isoformat()) if comm else datetime.utcnow().isoformat(),
                        "agent_name": comm.get("agentName", "unknown") if comm else "unknown",
                        "action": comm.get("action", "unknown") if comm else "unknown",
                        "status": "completed",  # Default status
                        "input": comm.get("input", {}) if comm else {},
                        "output": comm.get("output", {}) if comm else {},
                        "message": self._format_communication_message(comm) if comm else "Invalid communication",
                        "type": self._determine_message_type(comm) if comm else "error",
                        "session_id": comm.get("sessionId", self.session_id) if comm else self.session_id
                    })
                except Exception as comm_error:
                    logger.error(f"Error processing individual communication: {str(comm_error)}")
                    continue
            
            # If no communications logged yet, add basic session info
            if not communications:
                communications.append({
                    "timestamp": self.start_time.isoformat(),
                    "agent_name": "eol_orchestrator",
                    "action": "session_start",
                    "status": "completed",
                    "input": {},
                    "output": {
                        "session_id": self.session_id,
                        "cache_size": len(self.eol_cache),
                        "uptime_seconds": (datetime.utcnow() - self.start_time).total_seconds()
                    },
                    "message": f"🚀 EOL Orchestrator session started",
                    "type": "info"
                })
            
            return communications
            
        except Exception as e:
            logger.error(f"Error getting recent communications: {str(e)}")
            return [{
                "timestamp": datetime.utcnow().isoformat(),
                "agent_name": "eol_orchestrator",
                "action": "error",
                "status": "failed",
                "input": {},
                "output": {"error": str(e)},
                "message": f"❌ Error retrieving communications: {str(e)}",
                "type": "error"
            }]
    
    def _format_communication_message(self, comm: Dict[str, Any]) -> str:
        """Format communication for display"""
        try:
            if comm is None or not isinstance(comm, dict):
                return "❓ Invalid communication data"
                
            agent = comm.get("agentName", "unknown") if comm else "unknown"
            action = comm.get("action", "unknown") if comm else "unknown"
            input_data = comm.get("input", {}) if comm else {}
            output_data = comm.get("output", {}) if comm else {}
            
            if action == "get_eol_data":
                software = input_data.get("software_name", "unknown") if input_data else "unknown"
                version = input_data.get("version", "") if input_data else ""
                if output_data and not output_data.get("error"):
                    return f"🔍 {agent} found EOL data for {software}" + (f" {version}" if version else "")
                else:
                    return f"❌ {agent} failed to find EOL data for {software}" + (f" {version}" if version else "")
            elif action == "get_autonomous_eol_data":
                software = input_data.get("software_name", "unknown") if input_data else "unknown"
                return f"🎯 Orchestrator routing EOL query for {software}"
            elif action == "agent_selection":
                software = input_data.get("software_name", "unknown") if input_data else "unknown"
                agents = output_data.get("selected_agents", []) if output_data else []
                return f"🔀 Routing {software} to agents: {', '.join(agents)}"
            else:
                return f"📋 {agent}: {action}"
        except Exception as e:
            logger.error(f"Error formatting communication message: {str(e)}")
            return f"❌ Error formatting message: {str(e)}"
    
    def _determine_message_type(self, comm: Dict[str, Any]) -> str:
        """Determine message type for styling"""
        try:
            if comm is None or not isinstance(comm, dict):
                return "error"
                
            output_data = comm.get("output", {}) if comm else {}
            
            if output_data and output_data.get("error"):
                return "error"
            elif output_data and output_data.get("success") == False:
                return "warning"
            elif comm.get("action") in ["get_eol_data", "get_autonomous_eol_data"] and output_data:
                return "success"
            else:
                return "info"
        except Exception as e:
            logger.error(f"Error determining message type: {str(e)}")
            return "error"
    
    async def get_communication_history(self) -> List[Dict[str, Any]]:
        """Get the communication history for this session"""
        # Return from in-memory log  
        return list(reversed(self._comms_log))

    async def get_cache_status(self):
        """
        Get cache status and statistics
        """
        try:
            current_time = datetime.utcnow()
            
            # Calculate cache statistics
            total_items = len(self.eol_cache)
            
            # Calculate cache age statistics
            expired_items = 0
            oldest_timestamp = current_time
            newest_timestamp = None
            
            for cache_entry in self.eol_cache.values():
                entry_time = cache_entry.get("timestamp")
                if entry_time:
                    if isinstance(entry_time, str):
                        entry_time = datetime.fromisoformat(entry_time.replace('Z', '+00:00'))
                    
                    # Check if expired
                    if current_time - entry_time > timedelta(seconds=self.cache_ttl):
                        expired_items += 1
                    
                    # Track oldest and newest
                    if entry_time < oldest_timestamp:
                        oldest_timestamp = entry_time
                    if newest_timestamp is None or entry_time > newest_timestamp:
                        newest_timestamp = entry_time
            
            # Calculate cache size estimation
            cache_size_bytes = len(str(self.eol_cache))
            cache_size_kb = cache_size_bytes // 1024
            
            # Agent status
            agent_status = {}
            for agent_name, agent in self.agents.items():
                agent_status[agent_name] = {
                    "status": "available",
                    "type": type(agent).__name__
                }
            
            return {
                "success": True,
                "data": {
                    "eol_cache": {
                        "total_items": total_items,
                        "expired_items": expired_items,
                        "active_items": total_items - expired_items,
                        "cache_ttl_seconds": self.cache_ttl,
                        "size_bytes": cache_size_bytes,
                        "size_kb": cache_size_kb,
                        "oldest_entry": oldest_timestamp.isoformat() if oldest_timestamp != current_time else None,
                        "newest_entry": newest_timestamp.isoformat() if newest_timestamp else None
                    },
                    "agents": agent_status,
                    "session": {
                        "session_id": self.session_id,
                        "uptime_seconds": (current_time - self.start_time).total_seconds(),
                        "start_time": self.start_time.isoformat()
                    },
                    "timestamp": current_time.isoformat()
                }
            }
            
        except Exception as e:
            logger.error(f"❌ Error getting cache status: {str(e)}")
            return {
                "success": False,
                "error": f"Failed to get cache status: {str(e)}"
            }
    
    def _track_eol_agent_response(self, agent_name: str, software_name: str, software_version: str, eol_result: Dict[str, Any], response_time: float, query_type: str) -> None:
        """Track EOL agent responses for comprehensive history tracking"""
        try:
            # Create comprehensive response tracking entry
            response_entry = {
                "timestamp": datetime.now().isoformat(),
                "agent_name": agent_name,
                "software_name": software_name,
                "software_version": software_version or "Not specified",
                "query_type": query_type,
                "response_time": response_time,
                "success": eol_result.get("success", False),
                "eol_data": eol_result.get("data", {}),
                "error": eol_result.get("error", {}),
                "confidence": eol_result.get("data", {}).get("confidence", 0),
                "source_url": eol_result.get("data", {}).get("source_url", ""),
                "agent_used": eol_result.get("data", {}).get("agent_used", agent_name),
                "session_id": self.session_id,
                "orchestrator_type": "eol_orchestrator"
            }
            
            # Add to tracking list
            self.eol_agent_responses.append(response_entry)
            
            # Keep only the last 50 responses to prevent memory issues
            if len(self.eol_agent_responses) > 50:
                self.eol_agent_responses = self.eol_agent_responses[-50:]
                
            # Log the tracking for debugging
            logger.info(f"📊 [EOL Orchestrator] Tracked EOL response: {agent_name} -> {software_name} ({software_version}) - Success: {response_entry['success']} - Total tracked: {len(self.eol_agent_responses)}")
            
        except Exception as e:
            logger.error(f"❌ Error tracking EOL agent response: {e}")
    
    def get_eol_agent_responses(self) -> List[Dict[str, Any]]:
        """Get all tracked EOL agent responses for this session"""
        return self.eol_agent_responses.copy()
    
    def clear_eol_agent_responses(self) -> None:
        """Clear all tracked EOL agent responses"""
        self.eol_agent_responses.clear()
        logger.info("🧹 [EOL Orchestrator] Cleared EOL agent response tracking history")

# Backward compatibility alias
OrchestratorAgent = EOLOrchestratorAgent
