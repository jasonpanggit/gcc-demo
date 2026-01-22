"""
EndOfLife.date Agent - Queries the endoflife.date API for EOL information
"""
import requests
from typing import Dict, Any, Optional
from datetime import datetime
import hashlib
import asyncio
from .base_eol_agent import BaseEOLAgent
try:
    from utils.logger import get_logger
    logger = get_logger(__name__)
except Exception:
    import logging
    logger = logging.getLogger(__name__)

try:
    from utils.cache_stats_manager import CacheStatsManager
    cache_stats_manager = CacheStatsManager()
except ImportError:
    # Dummy implementation for environments without cache_stats_manager
    class DummyCacheStatsManager:
        def record_agent_request(self, agent_name, url, response_time=None, success=True, error_message=None):
            pass
    cache_stats_manager = DummyCacheStatsManager()

class EndOfLifeAgent(BaseEOLAgent):
    """Agent for querying endoflife.date API"""
    
    def __init__(self):
        super().__init__("endoflife")
        # Agent identification
        self.agent_name = "endoflife"

        self.base_url = "https://endoflife.date/api"
        self.timeout = 10
        
        # Agent-level caching disabled - orchestrator uses eol_inventory as single source of truth
        self.cosmos_cache = None

    def get_urls(self):
        """Return empty list since URLs are dynamically generated from usage statistics"""
        # For endoflife agent, URLs are dynamically generated from actual API usage statistics
        # rather than being statically configured. The frontend agents.html handles this special case.
        return []
    
    def _generate_cache_key(self, software_name: str, version: Optional[str] = None) -> str:
        """Generate a unique cache key for EndOfLife.date EOL data"""
        cache_input = f"endoflife:{software_name.lower()}:{version or 'latest'}"
        return hashlib.md5(cache_input.encode()).hexdigest()

    async def _get_cached_data(self, software_name: str, version: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Agent-level caching disabled - orchestrator handles caching via eol_inventory"""
        # Caching is now centralized in the orchestrator using eol_inventory
        return None

    async def _cache_data(self, software_name: str, version: Optional[str], data: Dict[str, Any], confidence_level: int, source_url: Optional[str] = None) -> None:
        """Agent-level caching disabled - orchestrator handles caching via eol_inventory"""
        # Caching is now centralized in the orchestrator using eol_inventory
        pass

    async def purge_cache(self, software_name: Optional[str] = None, version: Optional[str] = None) -> Dict[str, Any]:
        """Agent-level cache purge disabled - use eol_inventory for cache management"""
        # Caching is now centralized in the orchestrator using eol_inventory
        return {"success": True, "deleted_count": 0, "message": "Agent-level caching disabled - use eol_inventory"}

    async def get_eol_data(self, software_name: str, version: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Enhanced EOL data retrieval with improved search capabilities
        
        Search strategy:
        1. Try exact product name match
        2. Try fuzzy/partial matches with common variations
        3. Search through all products for partial matches
        4. Return best match with confidence score
        """
        
        # Record start time for statistics tracking
        start_time = datetime.now()
        
        # Try cache first
        cached_data = await self._get_cached_data(software_name, version)
        if cached_data:
            # Use cached URL from the data or construct one
            cached_url = cached_data.get('source_url', f"{self.base_url}/{software_name}.json")
            response_time = (datetime.now() - start_time).total_seconds()
            cache_stats_manager.record_agent_request(
                agent_name="endoflife", 
                url=cached_url, 
                response_time=response_time, 
                success=True, 
                error_message=None,
                software_name=software_name,
                version=version or ""
            )
            logger.info(f"📊 Cache hit for {software_name}: {cached_url} ({response_time:.4f}s)")
            return cached_data
        
        # Enhanced search strategy
        search_results = await self._enhanced_product_search(software_name, version)
        
        if search_results:
            # Cache the result
            await self._cache_data(
                software_name, 
                version, 
                search_results, 
                search_results.get('confidence_level', 85),
                search_results.get('source_url')
            )
            return search_results
        
        # No data found - return standardized failure response
        response_time = (datetime.now() - start_time).total_seconds()
        failed_url = f"{self.base_url}/{self._transform_name_for_api(software_name)}.json"
        cache_stats_manager.record_agent_request(
            agent_name="endoflife", 
            url=failed_url, 
            response_time=response_time, 
            success=False, 
            error_message="No EOL data found after enhanced search",
            software_name=software_name,
            version=version or ""
        )
        logger.info(f"📊 No EOL data found for {software_name}: {failed_url} ({response_time:.4f}s)")
        return self.create_failure_response(
            software_name=software_name,
            version=version,
            error_message="No EOL data found after enhanced search"
        )

    async def _enhanced_product_search(self, software_name: str, version: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Enhanced product search using multiple strategies:
        1. Direct API call with transformed name
        2. Fuzzy matching with product variations
        3. Search through all products list
        """
        
        # Strategy 1: Direct API call with exact/transformed name
        direct_result = await self._try_direct_api_call(software_name, version)
        if direct_result:
            return direct_result
        
        # Strategy 2: Try common variations and aliases
        variations_result = await self._try_product_variations(software_name, version)
        if variations_result:
            return variations_result
        
        # Strategy 3: Search through all products for partial matches
        fuzzy_result = await self._try_fuzzy_product_search(software_name, version)
        if fuzzy_result:
            return fuzzy_result
        
        return None

    async def _try_direct_api_call(self, software_name: str, version: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Try direct API call with the given software name"""
        
        api_name = self._transform_name_for_api(software_name)
        url = f"{self.base_url}/{api_name}.json"
        
        start_time = datetime.now()
        cache_stats_manager.record_agent_request("endoflife", url, software_name=software_name, version=version or "")
        
        try:
            response = requests.get(url, timeout=self.timeout)
            response_time = (datetime.now() - start_time).total_seconds()
            
            if response.status_code == 200:
                cache_stats_manager.record_agent_request("endoflife", url, response_time, success=True, software_name=software_name, version=version or "")
                
                data = response.json()
                cycle_data = self._extract_cycle_data(data, version)
                minor_versions = self._collect_minor_versions(data, version)
                
                if cycle_data:
                    logger.info(f"✅ Direct API hit for {software_name} -> {api_name}")
                    return self.create_success_response(
                        software_name=software_name,
                        version=version,
                        eol_date=cycle_data.get('eol'),
                        support_end_date=cycle_data.get('support'),
                        release_date=cycle_data.get('release'),
                        confidence=0.95,
                        source_url=url,
                        additional_data={
                            "product_name": api_name,
                            "search_method": "direct_api",
                            "cycle": cycle_data.get('cycle'),
                            "lts": cycle_data.get('lts'),
                            "latest": cycle_data.get('latest'),
                            "minor_versions": minor_versions,
                        }
                    )
            else:
                cache_stats_manager.record_agent_request("endoflife", url, response_time, success=False, error_message=f"HTTP {response.status_code}", software_name=software_name, version=version or "")
                
        except Exception as e:
            response_time = (datetime.now() - start_time).total_seconds()
            cache_stats_manager.record_agent_request("endoflife", url, response_time, success=False, error_message=str(e), software_name=software_name, version=version or "")
            logger.debug(f"Direct API call failed for {api_name}: {e}")
        
        return None

    async def _try_product_variations(self, software_name: str, version: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Try common product name variations and aliases"""
        
        # Generate product variations
        variations = self._generate_product_variations(software_name)
        
        for variation in variations:
            api_name = self._transform_name_for_api(variation)
            url = f"{self.base_url}/{api_name}.json"
            
            start_time = datetime.now()
            cache_stats_manager.record_agent_request("endoflife", url, software_name=software_name, version=version or "")
            
            try:
                response = requests.get(url, timeout=self.timeout)
                response_time = (datetime.now() - start_time).total_seconds()
                
                if response.status_code == 200:
                    cache_stats_manager.record_agent_request("endoflife", url, response_time, success=True, software_name=software_name, version=version or "")
                    
                    data = response.json()
                    cycle_data = self._extract_cycle_data(data, version)
                    minor_versions = self._collect_minor_versions(data, version)
                    
                    if cycle_data:
                        logger.info(f"✅ Variation match for {software_name} -> {api_name} (via {variation})")
                        return self.create_success_response(
                            software_name=software_name,
                            version=version,
                            eol_date=cycle_data.get('eol'),
                            support_end_date=cycle_data.get('support'),
                            release_date=cycle_data.get('release'),
                            confidence=0.85,
                            source_url=url,
                            additional_data={
                                "product_name": api_name,
                                "search_method": "variation_match",
                                "variation_used": variation,
                                "cycle": cycle_data.get('cycle'),
                                "lts": cycle_data.get('lts'),
                                "latest": cycle_data.get('latest'),
                                "minor_versions": minor_versions,
                            }
                        )
                else:
                    cache_stats_manager.record_agent_request("endoflife", url, response_time, success=False, error_message=f"HTTP {response.status_code}", software_name=software_name, version=version or "")
                    
            except Exception as e:
                response_time = (datetime.now() - start_time).total_seconds()
                cache_stats_manager.record_agent_request("endoflife", url, response_time, success=False, error_message=str(e), software_name=software_name, version=version or "")
                logger.debug(f"Variation {variation} failed: {e}")
        
        return None

    async def _try_fuzzy_product_search(self, software_name: str, version: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Search through all products for fuzzy matches"""
        
        # Get all products
        all_products = await self._get_all_products()
        if not all_products:
            return None
        
        # Find best matches
        matches = self._find_fuzzy_matches(software_name, all_products)
        
        # Try the best matches
        for match in matches[:3]:  # Try top 3 matches
            product_name = match['product']
            url = f"{self.base_url}/{product_name}.json"
            
            start_time = datetime.now()
            cache_stats_manager.record_agent_request("endoflife", url, software_name=software_name, version=version or "")
            
            try:
                response = requests.get(url, timeout=self.timeout)
                response_time = (datetime.now() - start_time).total_seconds()
                
                if response.status_code == 200:
                    cache_stats_manager.record_agent_request("endoflife", url, response_time, success=True, software_name=software_name, version=version or "")
                    
                    data = response.json()
                    cycle_data = self._extract_cycle_data(data, version)
                    minor_versions = self._collect_minor_versions(data, version)
                    
                    if cycle_data:
                        logger.info(f"✅ Fuzzy match for {software_name} -> {product_name} (score: {match['score']:.2f})")
                        return self.create_success_response(
                            software_name=software_name,
                            version=version,
                            eol_date=cycle_data.get('eol'),
                            support_end_date=cycle_data.get('support'),
                            release_date=cycle_data.get('release'),
                            confidence=min(0.75, match['score']),
                            source_url=url,
                            additional_data={
                                "product_name": product_name,
                                "search_method": "fuzzy_match",
                                "match_score": match['score'],
                                "cycle": cycle_data.get('cycle'),
                                "lts": cycle_data.get('lts'),
                                "latest": cycle_data.get('latest'),
                                "minor_versions": minor_versions,
                            }
                        )
                else:
                    cache_stats_manager.record_agent_request("endoflife", url, response_time, success=False, error_message=f"HTTP {response.status_code}", software_name=software_name, version=version or "")
                    
            except Exception as e:
                response_time = (datetime.now() - start_time).total_seconds()
                cache_stats_manager.record_agent_request("endoflife", url, response_time, success=False, error_message=str(e), software_name=software_name, version=version or "")
                logger.debug(f"Fuzzy match {product_name} failed: {e}")
        
        return None

    def _generate_product_variations(self, software_name: str) -> list:
        """Generate common variations of product names"""
        variations = set()
        name_lower = software_name.lower()
        
        # Original name variations
        variations.add(software_name)
        variations.add(name_lower)
        variations.add(name_lower.replace(" ", "-"))
        variations.add(name_lower.replace(" ", "_"))
        variations.add(name_lower.replace("-", ""))
        variations.add(name_lower.replace("_", ""))
        
        # Common software aliases and transformations
        alias_mappings = {
            # Microsoft products
            "microsoft sql server": ["mssqlserver", "sqlserver", "sql-server"],
            "sql server": ["mssqlserver", "sqlserver", "sql-server"],
            "windows server": ["windows-server", "windowsserver"],
            "visual studio": ["visual-studio", "visualstudio", "vs"],
            "internet information services": ["iis"],
            "microsoft office": ["office"],
            
            # Linux distributions
            "red hat enterprise linux": ["rhel", "redhat"],
            "ubuntu": ["ubuntu"],
            "centos": ["centos"],
            "debian": ["debian"],
            "fedora": ["fedora"],
            "suse": ["suse", "opensuse"],
            
            # Programming languages
            "python": ["python"],
            "node.js": ["nodejs", "node"],
            "java": ["java", "openjdk"],
            "dotnet": [".net", "dotnet-core", "aspnet"],
            "php": ["php"],
            "ruby": ["ruby"],
            "go": ["go", "golang"],
            
            # Databases
            "postgresql": ["postgresql", "postgres"],
            "mysql": ["mysql"],
            "mongodb": ["mongodb", "mongo"],
            "redis": ["redis"],
            "elasticsearch": ["elasticsearch", "elastic"],
            
            # Web servers
            "apache": ["apache", "httpd"],
            "nginx": ["nginx"],
            "tomcat": ["tomcat"],
            
            # Other common software
            "docker": ["docker"],
            "kubernetes": ["kubernetes", "k8s"],
            "jenkins": ["jenkins"],
            "gitlab": ["gitlab"],
            "github": ["github"],
        }
        
        # Add specific aliases
        for key, aliases in alias_mappings.items():
            if key in name_lower:
                variations.update(aliases)
        
        # Remove empty strings and return as list
        return [v for v in variations if v]

    async def _get_all_products(self) -> Optional[list]:
        """Get all available products from the API"""
        url = f"{self.base_url}/all.json"
        
        start_time = datetime.now()
        cache_stats_manager.record_agent_request("endoflife", url)
        
        try:
            response = requests.get(url, timeout=self.timeout)
            response_time = (datetime.now() - start_time).total_seconds()
            
            if response.status_code == 200:
                cache_stats_manager.record_agent_request("endoflife", url, response_time, success=True)
                return response.json()
            else:
                cache_stats_manager.record_agent_request("endoflife", url, response_time, success=False, error_message=f"HTTP {response.status_code}")
                
        except Exception as e:
            response_time = (datetime.now() - start_time).total_seconds()
            cache_stats_manager.record_agent_request("endoflife", url, response_time, success=False, error_message=str(e))
            logger.error(f"Failed to get all products: {e}")
        
        return None

    def _find_fuzzy_matches(self, software_name: str, all_products: list) -> list:
        """Find fuzzy matches in the product list"""
        name_lower = software_name.lower()
        matches = []
        
        for product in all_products:
            score = self._calculate_match_score(name_lower, product)
            if score > 0.3:  # Minimum threshold
                matches.append({"product": product, "score": score})
        
        # Sort by score descending
        return sorted(matches, key=lambda x: x['score'], reverse=True)

    def _calculate_match_score(self, search_term: str, product: str) -> float:
        """Calculate similarity score between search term and product name"""
        search_term = search_term.lower()
        product = product.lower()
        
        # Exact match
        if search_term == product:
            return 1.0
        
        # Contains match
        if search_term in product or product in search_term:
            return 0.8
        
        # Word-based matching
        search_words = set(search_term.replace("-", " ").replace("_", " ").split())
        product_words = set(product.replace("-", " ").replace("_", " ").split())
        
        if search_words and product_words:
            intersection = search_words.intersection(product_words)
            union = search_words.union(product_words)
            jaccard_score = len(intersection) / len(union)
            
            # Boost score if all search words are found
            if search_words.issubset(product_words):
                jaccard_score += 0.3
            
            return min(jaccard_score, 1.0)
        
        return 0.0

    def _extract_cycle_data(self, api_data: Any, version: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Extract relevant cycle data from API response"""
        if not api_data:
            return None
        
        # Handle list response (multiple cycles)
        if isinstance(api_data, list):
            if not api_data:
                return None

            # If version specified, choose the best matching cycle (avoid latest patch drift)
            if version:
                exact = self._find_exact_cycle_match(api_data, version)
                if exact:
                    return exact

                version_parts = self._parse_semver_parts(version)
                if version_parts:
                    candidates = []
                    for cycle in api_data:
                        cycle_str = str(cycle.get("cycle", "")).strip()
                        cycle_parts = self._parse_semver_parts(cycle_str)
                        if not cycle_parts:
                            continue

                        if cycle_parts[0] != version_parts[0]:
                            continue

                        if len(version_parts) >= 2 and len(cycle_parts) >= 2:
                            if cycle_parts[1] != version_parts[1]:
                                continue

                        if len(version_parts) >= 3 and len(cycle_parts) >= 3:
                            if cycle_parts[2] != version_parts[2]:
                                continue

                        candidates.append(cycle)

                    best_candidate = self._select_lowest_cycle(candidates)
                    if best_candidate:
                        return best_candidate

                # Fallback: use the first semver-lowest among generic matches
                generic_matches = [
                    cycle for cycle in api_data
                    if self._version_matches_cycle(version, cycle.get("cycle", ""))
                ]
                best_generic = self._select_lowest_cycle(generic_matches)
                if best_generic:
                    return best_generic

            # Return the first (latest) cycle
            return api_data[0]
        
        # Handle dict response (single cycle)
        elif isinstance(api_data, dict):
            return api_data
        
        return None

    def _is_major_only_version(self, version: Optional[str]) -> bool:
        if not version:
            return False
        return bool(re.fullmatch(r"\d+", str(version).strip()))

    def _collect_minor_versions(self, api_data: Any, version: Optional[str]) -> list:
        """Collect minor versions for a major-only query (e.g., 12 -> 12.0, 12.1)."""
        if not self._is_major_only_version(version):
            return []
        if not isinstance(api_data, list):
            return []

        major = str(version).strip()
        minor_versions = []
        for cycle in api_data:
            cycle_str = str(cycle.get("cycle", "")).strip()
            if not cycle_str:
                continue
            if not self._version_matches_cycle(major, cycle_str):
                continue
            parts = self._extract_version_parts(cycle_str)
            if parts and len(parts) >= 2:
                minor_versions.append(cycle_str)

        def sort_key(value: str):
            parts = self._extract_version_parts(value)
            padded = (parts + [0] * (3 - len(parts))) if parts else [0, 0, 0]
            return tuple(padded[:3])

        return sorted(set(minor_versions), key=sort_key)

    def _find_exact_cycle_match(self, api_data: list, version: str) -> Optional[Dict[str, Any]]:
        """Find an exact cycle match by normalized version string."""
        version_str = str(version).strip()
        if not version_str:
            return None

        for cycle in api_data:
            cycle_str = str(cycle.get("cycle", "")).strip()
            if not cycle_str:
                continue
            if cycle_str == version_str or cycle_str.lower() == version_str.lower():
                return cycle

        # Try normalized semver string match
        version_norm = self._normalize_semver_string(version_str)
        if not version_norm:
            return None

        for cycle in api_data:
            cycle_str = str(cycle.get("cycle", "")).strip()
            if not cycle_str:
                continue
            cycle_norm = self._normalize_semver_string(cycle_str)
            if cycle_norm and cycle_norm == version_norm:
                return cycle

        return None

    def _parse_semver_parts(self, value: str) -> Optional[list]:
        """Parse numeric version parts (major.minor.patch) from a string."""
        import re

        if not value:
            return None

        match = re.search(r"\d+(?:\.\d+)*", str(value))
        if not match:
            return None

        parts = match.group(0).split(".")
        try:
            return [int(p) for p in parts if p.isdigit()]
        except ValueError:
            return None

    def _normalize_semver_string(self, value: str) -> Optional[str]:
        """Normalize semver-like strings for comparison."""
        parts = self._parse_semver_parts(value)
        if not parts:
            return None
        return ".".join(str(p) for p in parts)

    def _select_lowest_cycle(self, cycles: list) -> Optional[Dict[str, Any]]:
        """Select the lowest semver cycle from candidates (prefers earliest patch)."""
        if not cycles:
            return None

        def sort_key(cycle):
            cycle_str = str(cycle.get("cycle", "")).strip()
            parts = self._parse_semver_parts(cycle_str) or []
            # Pad to 3 for consistent ordering
            padded = parts + [0] * (3 - len(parts))
            return tuple(padded[:3])

        return sorted(cycles, key=sort_key)[0]
    
    def _transform_name_for_api(self, software_name: str) -> str:
        """Transform software name to endoflife.date API format with comprehensive mappings"""
        name_lower = software_name.lower().strip()
        
        # Comprehensive API name mappings based on endoflife.date API
        api_mappings = {
            # Microsoft products
            "windows-server": "windows-server",
            "microsoft-sql-server": "mssqlserver",
            "sql-server": "mssqlserver",
            "sqlserver": "mssqlserver",
            "microsoft-office": "office",
            "office": "office",
            "internet-information-services": "iis",
            "iis": "iis",
            "visual-studio": "visual-studio",
            "visualstudio": "visual-studio",
            "windows-10": "windows",
            "windows-11": "windows",
            "windows": "windows",
            "dotnet": "dotnet",
            ".net": "dotnet",
            "asp.net": "dotnet",
            "powershell": "powershell",
            "exchange": "exchange",
            "sharepoint": "sharepoint",
            
            # Linux distributions
            "red-hat-enterprise-linux": "rhel",
            "redhat": "rhel",
            "rhel": "rhel",
            "centos": "centos",
            "ubuntu": "ubuntu",
            "debian": "debian",
            "fedora": "fedora",
            "opensuse": "opensuse",
            "suse": "opensuse",
            "alpine": "alpine",
            "amazon-linux": "amazon-linux",
            "oracle-linux": "oracle-linux",
            
            # Programming languages & runtimes
            "python": "python",
            "node.js": "nodejs",
            "nodejs": "nodejs",
            "node": "nodejs",
            "java": "java",
            "openjdk": "openjdk",
            "php": "php",
            "ruby": "ruby",
            "go": "go",
            "golang": "go",
            "rust": "rust",
            "scala": "scala",
            "kotlin": "kotlin",
            "perl": "perl",
            "erlang": "erlang",
            "elixir": "elixir",
            
            # Databases
            "postgresql": "postgresql",
            "postgres": "postgresql",
            "mysql": "mysql",
            "mariadb": "mariadb",
            "mongodb": "mongodb",
            "mongo": "mongodb",
            "redis": "redis",
            "elasticsearch": "elasticsearch",
            "elastic": "elasticsearch",
            "cassandra": "cassandra",
            "couchdb": "couchdb",
            "influxdb": "influxdb",
            "neo4j": "neo4j",
            "sqlite": "sqlite",
            
            # Web servers & proxies
            "apache": "apache",
            "httpd": "apache",
            "nginx": "nginx",
            "tomcat": "tomcat",
            "jetty": "jetty",
            "traefik": "traefik",
            "haproxy": "haproxy",
            "varnish": "varnish",
            
            # Container & orchestration
            "docker": "docker",
            "kubernetes": "kubernetes",
            "k8s": "kubernetes",
            "containerd": "containerd",
            "helm": "helm",
            "istio": "istio",
            "consul": "consul",
            "nomad": "nomad",
            "vault": "vault",
            
            # CI/CD & DevOps
            "jenkins": "jenkins",
            "gitlab": "gitlab",
            "github": "github",
            "bitbucket": "bitbucket",
            "bamboo": "bamboo",
            "teamcity": "teamcity",
            "azure-devops": "azure-devops",
            "travis": "travis-ci",
            "circleci": "circleci",
            
            # Monitoring & observability
            "prometheus": "prometheus",
            "grafana": "grafana",
            "kibana": "kibana",
            "logstash": "logstash",
            "fluentd": "fluentd",
            "jaeger": "jaeger",
            "zipkin": "zipkin",
            "nagios": "nagios",
            "zabbix": "zabbix",
            
            # Message queues & streaming
            "rabbitmq": "rabbitmq",
            "apache-kafka": "kafka",
            "kafka": "kafka",
            "activemq": "activemq",
            "pulsar": "pulsar",
            "nats": "nats",
            
            # Cloud platforms & services
            "aws": "aws",
            "amazon-web-services": "aws",
            "azure": "azure",
            "gcp": "gcp",
            "google-cloud": "gcp",
            "digitalocean": "digitalocean",
            "linode": "linode",
            "vultr": "vultr",
            
            # Security tools
            "vault": "vault",
            "consul": "consul",
            "keycloak": "keycloak",
            "oauth": "oauth",
            "openssl": "openssl",
            
            # Development tools
            "git": "git",
            "subversion": "subversion",
            "svn": "subversion",
            "mercurial": "mercurial",
            "maven": "maven",
            "gradle": "gradle",
            "npm": "npm",
            "yarn": "yarn",
            "pip": "pip",
            "composer": "composer",
            
            # Frontend frameworks
            "angular": "angular",
            "react": "react",
            "vue": "vue",
            "ember": "ember",
            "backbone": "backbone",
            "jquery": "jquery",
            
            # Mobile platforms
            "android": "android",
            "ios": "ios",
            "cordova": "cordova",
            "phonegap": "cordova",
            "ionic": "ionic",
            "xamarin": "xamarin",
            
            # Game engines
            "unity": "unity",
            "unreal": "unreal",
            "godot": "godot",
            
            # Other common software
            "wordpress": "wordpress",
            "drupal": "drupal",
            "joomla": "joomla",
            "magento": "magento",
            "shopify": "shopify",
            "salesforce": "salesforce",
            "tableau": "tableau",
            "powerbi": "powerbi",
            "splunk": "splunk",
        }
        
        # Clean the input
        cleaned_name = name_lower.replace(" ", "-").replace("_", "-")
        
        # Direct mapping
        if cleaned_name in api_mappings:
            return api_mappings[cleaned_name]
        
        # Try variations
        variations = [
            name_lower.replace(" ", "-"),
            name_lower.replace(" ", ""),
            name_lower.replace("-", ""),
            name_lower.replace("_", ""),
            name_lower.replace(" ", "_"),
        ]
        
        for variation in variations:
            if variation in api_mappings:
                return api_mappings[variation]
        
        # Return cleaned name if no mapping found
        return cleaned_name
    
    def _version_matches_cycle(self, version: str, cycle: str) -> bool:
        """Enhanced version matching with multiple strategies"""
        try:
            if not version or not cycle:
                return False
            
            # Convert both to strings for comparison
            version_str = str(version).strip()
            cycle_str = str(cycle).strip()
            
            # Exact match
            if version_str == cycle_str:
                return True
            
            # Case-insensitive match
            if version_str.lower() == cycle_str.lower():
                return True
            
            # Extract numeric parts for version comparison
            version_parts = self._extract_version_parts(version_str)
            cycle_parts = self._extract_version_parts(cycle_str)
            
            if version_parts and cycle_parts:
                # Compare major version
                if version_parts[0] == cycle_parts[0]:
                    # If only major version provided, match
                    if len(version_parts) == 1:
                        return True
                    # Compare major.minor if available
                    if len(version_parts) >= 2 and len(cycle_parts) >= 2:
                        if version_parts[1] == cycle_parts[1]:
                            return True
                
                # Full version match
                if version_parts == cycle_parts:
                    return True
            
            # Substring matching (for cases like "18.04" in "18.04 LTS")
            if version_str in cycle_str or cycle_str in version_str:
                return True
            
            # Handle special cases
            return self._handle_special_version_cases(version_str, cycle_str)
            
        except Exception as e:
            logger.debug(f"Version matching error: {e}")
            return False

    def _extract_version_parts(self, version_str: str) -> list:
        """Extract numeric version parts from version string"""
        import re
        
        # Extract numbers (including decimals)
        parts = re.findall(r'\d+(?:\.\d+)?', version_str)
        
        # Convert to float if decimal, int otherwise
        numeric_parts = []
        for part in parts:
            try:
                if '.' in part:
                    numeric_parts.append(float(part))
                else:
                    numeric_parts.append(int(part))
            except ValueError:
                continue
        
        return numeric_parts

    def _handle_special_version_cases(self, version: str, cycle: str) -> bool:
        """Handle special version matching cases"""
        version_lower = version.lower()
        cycle_lower = cycle.lower()
        
        # LTS matching
        if 'lts' in version_lower or 'lts' in cycle_lower:
            # Remove LTS and compare
            v_clean = version_lower.replace('lts', '').strip()
            c_clean = cycle_lower.replace('lts', '').strip()
            if v_clean == c_clean:
                return True
        
        # Year-based versions
        if len(version) == 4 and len(cycle) == 4:
            try:
                return int(version) == int(cycle)
            except ValueError:
                pass
        
        # Handle version ranges or approximations
        if any(char in version_lower for char in ['~', '^', '>=', '<=', '>', '<']):
            # For now, just strip these and compare
            import re
            v_cleaned = re.sub(r'[~\^<>=]', '', version).strip()
            return self._version_matches_cycle(v_cleaned, cycle)
        
        return False
    
    async def get_product_details(self, product_name: str) -> Optional[Dict[str, Any]]:
        """Get comprehensive product details including all cycles"""
        
        start_time = datetime.now()
        api_name = self._transform_name_for_api(product_name)
        url = f"{self.base_url}/{api_name}.json"
        
        cache_stats_manager.record_agent_request("endoflife", url, software_name=product_name, version="all_cycles")
        
        try:
            response = requests.get(url, timeout=self.timeout)
            response_time = (datetime.now() - start_time).total_seconds()
            
            if response.status_code == 200:
                cache_stats_manager.record_agent_request("endoflife", url, response_time, success=True, software_name=product_name, version="all_cycles")
                
                data = response.json()
                logger.info(f"✅ Product details retrieved for {product_name} -> {api_name}")
                
                return {
                    "source": "endoflife.date",
                    "source_url": url,
                    "product_name": api_name,
                    "search_method": "product_details",
                    "confidence_level": 95,
                    "all_cycles": data if isinstance(data, list) else [data],
                    "latest_cycle": data[0] if isinstance(data, list) and data else data,
                    "total_cycles": len(data) if isinstance(data, list) else 1
                }
            else:
                cache_stats_manager.record_agent_request("endoflife", url, response_time, success=False, error_message=f"HTTP {response.status_code}", software_name=product_name, version="all_cycles")
                
        except Exception as e:
            response_time = (datetime.now() - start_time).total_seconds()
            cache_stats_manager.record_agent_request("endoflife", url, response_time, success=False, error_message=str(e), software_name=product_name, version="all_cycles")
            logger.error(f"Error getting product details for {product_name}: {e}")
        
        return None

    async def search_products(self, search_term: str, limit: int = 10) -> Dict[str, Any]:
        """Search for products matching the search term"""
        
        all_products = await self._get_all_products()
        if not all_products:
            return {
                "source": "endoflife.date",
                "search_term": search_term,
                "matches": [],
                "total_matches": 0
            }
        
        matches = self._find_fuzzy_matches(search_term, all_products)
        limited_matches = matches[:limit]
        
        return {
            "source": "endoflife.date",
            "search_term": search_term,
            "matches": [
                {
                    "product": match["product"],
                    "score": match["score"],
                    "confidence": min(95, int(match["score"] * 100))
                }
                for match in limited_matches
            ],
            "total_matches": len(matches),
            "showing": len(limited_matches)
        }

    def get_supported_products(self) -> Dict[str, Any]:
        """Get list of supported products"""
        try:
            url = f"{self.base_url}/all.json"
            
            # Record agent request for statistics tracking using specific URL
            start_time = datetime.now()
            cache_stats_manager.record_agent_request("endoflife", url)
            
            response = requests.get(url, timeout=self.timeout)
            
            # Calculate response time for tracking
            response_time = (datetime.now() - start_time).total_seconds()
            
            if response.status_code == 200:
                cache_stats_manager.record_agent_request("endoflife", url, response_time, success=True)
                return {
                    "source": "endoflife.date",
                    "products": response.json()
                }
            else:
                cache_stats_manager.record_agent_request("endoflife", url, response_time, success=False, error_message=f"HTTP {response.status_code}")
                
        except Exception as e:
            # Record failed request for statistics tracking
            start_time = getattr(locals(), 'start_time', datetime.now())
            response_time = (datetime.now() - start_time).total_seconds()
            url = getattr(locals(), 'url', f"{self.base_url}/all.json")
            cache_stats_manager.record_agent_request("endoflife", url, response_time, success=False, error_message=str(e))
            logger.error(f"Error getting supported products: {e}")
        
        # Return empty products list if API fails - no builtin fallback
        return {
            "source": "endoflife.date",
            "products": []
        }
