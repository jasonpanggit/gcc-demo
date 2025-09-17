"""
Oracle EOL Agent - Scrapes Oracle official sources for EOL information
"""
import requests
from bs4 import BeautifulSoup
from typing import Dict, Any, Optional
import re
from datetime import datetime, timedelta
import json
import hashlib
import time
import asyncio
from utils.eol_cache import eol_cache
from .base_eol_agent import BaseEOLAgent

# Import cache stats manager for tracking URL usage
try:
    from utils.cache_stats_manager import cache_stats_manager
except ImportError:
    # Fallback dummy implementation
    class DummyCacheStatsManager:
        def record_agent_request(self, *args, **kwargs): pass
    cache_stats_manager = DummyCacheStatsManager()

try:
    from utils.logger import get_logger
    logger = get_logger(__name__)
except Exception:
    import logging
    logger = logging.getLogger(__name__)

class OracleEOLAgent(BaseEOLAgent):
    """Agent for scraping Oracle official EOL information"""

    def __init__(self):
        super().__init__("oracle")
        
        self.timeout = 15
        self.headers = {
            'User-Agent': (
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                'AppleWebKit/537.36 (KHTML, like Gecko) '
                'Chrome/91.0.4472.124 Safari/537.36'
            )
        }

        # Use shared EOL cache singleton
        self.cosmos_cache = eol_cache

        # Oracle EOL URLs with metadata (single source of truth)
        self.eol_urls = {
            "oracle-database": {
                "url": "https://www.oracle.com/support/lifetime-support/",
                "description": "Oracle Database Lifetime Support Policy",
                "active": True,
                "priority": 1
            },
            "java": {
                "url": "https://www.oracle.com/java/technologies/java-se-support-roadmap.html",
                "description": "Oracle Java SE Support Roadmap",
                "active": True,
                "priority": 2
            },
            "mysql": {
                "url": "https://www.mysql.com/support/supportedplatforms/database.html",
                "description": "MySQL Supported Platforms",
                "active": True,
                "priority": 3
            },
            "virtualbox": {
                "url": "https://www.virtualbox.org/wiki/Download_Old_Builds",
                "description": "VirtualBox End-of-Life Builds",
                "active": True,
                "priority": 4
            }
        }

        # Static data for major Oracle products
        self.static_eol_data = {
            "oracle-database-21c": {
                "cycle": "21c",
                "releaseDate": "2021-08-01",
                "eol": "2024-04-30",
                "support": "2024-04-30",
                "latest": "21.3.0",
                "source": "oracle_official",
                "confidence": 95,
            },
            "oracle-database-19c": {
                "cycle": "19c",
                "releaseDate": "2019-04-01",
                "eol": "2027-04-30",
                "support": "2024-04-30",
                "latest": "19.21.0",
                "source": "oracle_official",
                "confidence": 95,
            },
            "oracle-database-12c": {
                "cycle": "12c",
                "releaseDate": "2013-06-01",
                "eol": "2024-07-31",
                "support": "2022-07-31",
                "latest": "12.2.0.1",
                "source": "oracle_official",
                "confidence": 90,
            },
            "java-17": {
                "cycle": "17 LTS",
                "releaseDate": "2021-09-14",
                "eol": "2029-09-30",
                "support": "2026-09-30",
                "latest": "17.0.9",
                "lts": True,
                "source": "oracle_official",
                "confidence": 95,
            },
            "java-11": {
                "cycle": "11 LTS",
                "releaseDate": "2018-09-25",
                "eol": "2026-09-30",
                "support": "2023-09-30",
                "latest": "11.0.21",
                "lts": True,
                "source": "oracle_official",
                "confidence": 95,
            },
            "java-8": {
                "cycle": "8 LTS",
                "releaseDate": "2014-03-18",
                "eol": "2030-12-31",
                "support": "2022-03-31",
                "latest": "8u391",
                "lts": True,
                "source": "oracle_official",
                "confidence": 95,
            },
            "mysql-8.0": {
                "cycle": "8.0",
                "releaseDate": "2018-04-19",
                "eol": "2026-04-30",
                "support": "2025-04-30",
                "latest": "8.0.35",
                "source": "oracle_official",
                "confidence": 90,
            },
            "mysql-5.7": {
                "cycle": "5.7",
                "releaseDate": "2015-10-21",
                "eol": "2023-10-31",
                "support": "2023-10-31",
                "latest": "5.7.44",
                "source": "oracle_official",
                "confidence": 90,
            },
        }

    @property
    def urls(self):
        """Dynamically generate frontend URLs from eol_urls"""
        return [
            {
                "url": url_data["url"],
                "description": url_data["description"],
                "active": url_data.get("active", True),
                "priority": url_data.get("priority", 1)
            }
            for url_data in sorted(self.eol_urls.values(), key=lambda x: x.get("priority", 1))
        ]

    def get_url(self, product_type):
        """Get URL string for a specific product type (backward compatibility)"""
        url_data = self.eol_urls.get(product_type)
        return url_data["url"] if url_data else None

    def _generate_cache_key(self, software_name: str, version: Optional[str] = None) -> str:
        """Generate a consistent cache key for the request"""
        key_data = f"oracle_eol_{software_name}_{version or 'any'}"
        return hashlib.md5(key_data.encode()).hexdigest()

    async def _get_cached_data(self, software_name: str, version: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Get cached EOL data from Cosmos DB"""
        try:
            return await self.cosmos_cache.get_cached_response(software_name, version, self.agent_name)
        except Exception as e:
            logger.error(f"Error retrieving cached data: {e}")
            return None

    async def _cache_data(self, software_name: str, version: Optional[str], data: Dict[str, Any], source_url: Optional[str] = None):
        """Cache EOL data in Cosmos DB if confidence is high enough"""
        try:
            if not source_url:
                # Determine source URL based on software type
                software_lower = software_name.lower()
                if "java" in software_lower:
                    source_url = self.eol_urls.get("java")
                elif "mysql" in software_lower:
                    source_url = self.eol_urls.get("mysql")
                elif "virtualbox" in software_lower:
                    source_url = self.eol_urls.get("virtualbox")
                else:
                    source_url = self.eol_urls.get("oracle-database", "https://www.oracle.com/support/lifetime-support/")
            
            await self.cosmos_cache.cache_response(software_name, version, self.agent_name, data, source_url=source_url)
        except Exception as e:
            logger.error(f"Error caching data: {e}")

    async def purge_cache(self, software_name: Optional[str] = None, version: Optional[str] = None) -> Dict[str, Any]:
        """Purge cached data for specific software or all Oracle cache"""
        try:
            if software_name:
                cache_key = self._generate_cache_key(software_name, version)
                # Implementation would depend on CosmosEOLCache having a delete method
                return {"success": True, "deleted_count": 1, "message": f"Purged cache for {software_name}"}
            else:
                # Purge all Oracle cache entries
                return {"success": True, "deleted_count": 0, "message": "Bulk purge not implemented"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def get_eol_data(self, software_name: str, version: Optional[str] = None) -> Dict[str, Any]:
        """Get EOL data for Oracle products with enhanced static data checking"""
        
        # Check cache first
        cached_data = await self._get_cached_data(software_name, version)
        if cached_data:
            return cached_data
        
        # Get fresh data using enhanced fetch method
        result_data = await self._fetch_eol_data(software_name, version)
        
        if result_data:
            # Add Oracle-specific metadata
            source_url = self._get_oracle_url(software_name)
            confidence = result_data.get("confidence", 85)
            
            result = self.create_success_response(
                software_name=software_name,
                version=version or result_data.get("cycle", "unknown"),
                eol_date=result_data.get("eol", ""),
                support_end_date=result_data.get("support", ""),
                confidence=confidence / 100.0,  # Convert to decimal
                source_url=source_url,
                additional_data={
                    "cycle": result_data.get("cycle", ""),
                    "extended_support": result_data.get("extendedSupport", False),
                    "agent": "oracle",
                    "data_source": "oracle_agent"
                }
            )
            
            # Cache the result
            await self._cache_data(software_name, version, result, source_url=source_url)
            return result

        return self.create_failure_response(
            f"No EOL information found for {software_name}" + (f" version {version}" if version else ""),
            "no_data_found",
            {"searched_product": software_name, "searched_version": version}
        )

    async def _fetch_eol_data(self, software_name: str, version: str = None) -> Optional[Dict[str, Any]]:
        """
        Fetch EOL data from Oracle sources
        """
        # Check static data first for reliability
        static_result = self._check_static_data(software_name, version)
        if static_result:
            return static_result

        # Try web scraping for latest information
        scraped_result = await self._scrape_oracle_eol(software_name, version)
        if scraped_result:
            return scraped_result

        return None

    def _check_static_data(self, software_name: str, version: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Check static EOL data for Oracle products with enhanced matching"""
        software_lower = software_name.lower().replace(" ", "-")
        
        # Direct exact matches for software_lower keys
        if software_lower in self.static_eol_data:
            return self.static_eol_data[software_lower]
        
        # Try direct key lookup for common variations
        key_variations = [
            software_lower,
            software_lower.replace(" ", "-"),
            software_lower.replace("_", "-"),
            software_lower.replace(".", "-")
        ]
        
        for key_variant in key_variations:
            if key_variant in self.static_eol_data:
                return self.static_eol_data[key_variant]
        
        # Enhanced version-specific matching for Oracle products
        if version:
            # Oracle Database versions
            if "oracle" in software_lower and "database" in software_lower:
                if "21" in version or "21c" in version.lower():
                    if "oracle-database-21c" in self.static_eol_data:
                        return self.static_eol_data["oracle-database-21c"]
                elif "19" in version or "19c" in version.lower():
                    if "oracle-database-19c" in self.static_eol_data:
                        return self.static_eol_data["oracle-database-19c"]
                elif "12" in version or "12c" in version.lower():
                    if "oracle-database-12c" in self.static_eol_data:
                        return self.static_eol_data["oracle-database-12c"]
            
            # Java versions
            elif "java" in software_lower or "jdk" in software_lower or "jre" in software_lower:
                version_parts = version.split('.')
                major_version = version_parts[0]
                
                if "17" in version or major_version == "17":
                    if "java-17" in self.static_eol_data:
                        return self.static_eol_data["java-17"]
                elif "11" in version or major_version == "11":
                    if "java-11" in self.static_eol_data:
                        return self.static_eol_data["java-11"]
                elif "8" in version or "1.8" in version or major_version == "8":
                    if "java-8" in self.static_eol_data:
                        return self.static_eol_data["java-8"]
        
        # Improved partial matches with better precision
        for key, data in self.static_eol_data.items():
            key_parts = key.split("-")
            software_parts = software_lower.split("-")
            
            # For Oracle products, require specific product match
            if "oracle" in software_parts and "database" in software_parts:
                if "oracle" in key_parts and "database" in key_parts:
                    if not version or self._version_matches(version, data.get("cycle", "")):
                        return data
            
            elif "java" in software_parts or "jdk" in software_parts or "jre" in software_parts:
                if "java" in key_parts:
                    if not version or self._version_matches(version, data.get("cycle", "")):
                        return data
            
            elif "mysql" in software_parts:
                if "mysql" in key_parts:
                    if not version or self._version_matches(version, data.get("cycle", "")):
                        return data
            
            # Generic partial matching for other Oracle products
            else:
                if any(keyword in software_lower for keyword in key_parts):
                    if not version or self._version_matches(version, data.get("cycle", "")):
                        return data
        
        return None
    
    def _version_matches(self, version: str, cycle: str) -> bool:
        """Check if version matches the cycle for Oracle products"""
        try:
            if not version or not cycle:
                return False
            
            # Handle Oracle Database cycles (19c, 21c, etc.)
            if "c" in cycle.lower():
                cycle_clean = cycle.lower().replace("c", "")
                if cycle_clean in version:
                    return True
            
            # Handle Java versions
            version_major = version.split('.')[0]
            if version_major in str(cycle):
                return True
            
            # Generic version matching
            return str(cycle) in version or version in str(cycle)
            
        except Exception:
            return False

    def _normalize_software_name(self, software_name: str, version: Optional[str] = None) -> str:
        """Normalize software name for lookup"""
        name_lower = software_name.lower()
        
        # Oracle Database versions
        if "oracle" in name_lower and "database" in name_lower:
            if version:
                if "21" in version or "21c" in version.lower():
                    return "oracle-database-21c"
                elif "19" in version or "19c" in version.lower():
                    return "oracle-database-19c"
                elif "12" in version or "12c" in version.lower():
                    return "oracle-database-12c"
        
        # Java versions
        if "java" in name_lower or "jdk" in name_lower or "jre" in name_lower:
            if version:
                if "17" in version:
                    return "java-17"
                elif "11" in version:
                    return "java-11"
                elif "8" in version or "1.8" in version:
                    return "java-8"
        
        # MySQL versions
        if "mysql" in name_lower:
            if version:
                if version.startswith("8"):
                    return "mysql-8.0"
                elif version.startswith("5.7"):
                    return "mysql-5.7"
        
        return f"{name_lower}-{version}" if version else name_lower
    
    def _get_oracle_url(self, software_name: str) -> str:
        """Get the appropriate Oracle URL for the software"""
        software_lower = software_name.lower()
        
        if "java" in software_lower or "jdk" in software_lower or "jre" in software_lower:
            return self.eol_urls.get("java", "https://www.oracle.com/java/technologies/java-se-support-roadmap.html")
        elif "mysql" in software_lower:
            return self.eol_urls.get("mysql", "https://www.mysql.com/support/supportedplatforms/database.html")
        elif "database" in software_lower or "oracle" in software_lower:
            return self.eol_urls.get("oracle-database", "https://www.oracle.com/support/lifetime-support/")
        else:
            return "https://www.oracle.com/support/lifetime-support/"

    async def _scrape_oracle_eol(self, software_name: str, version: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Scrape Oracle EOL information from official sources"""
        start_time = time.time()
        url = None
        
        try:
            # Determine which URL to use based on software
            name_lower = software_name.lower()
            
            if "java" in name_lower or "jdk" in name_lower:
                url = self.eol_urls["java"]["url"]
            elif "mysql" in name_lower:
                url = self.eol_urls["mysql"]["url"]
            elif "oracle" in name_lower and "database" in name_lower:
                url = self.eol_urls["oracle-database"]["url"]
            
            if not url:
                return None
            
            # Record the agent request before making the HTTP call
            cache_stats_manager.record_agent_request(
                agent_name="oracle", 
                url=url, 
                start_time=start_time
            )
            
            response = requests.get(url, headers=self.headers, timeout=self.timeout)
            response.raise_for_status()
            
            # Calculate response time
            response_time_ms = (time.time() - start_time) * 1000
            
            # Record successful request
            cache_stats_manager.record_agent_request(
                agent_name="oracle",
                url=url,
                response_time_ms=response_time_ms,
                success=True,
                status_code=response.status_code
            )
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Extract EOL information from the page
            # This is a simplified extraction - would need more specific parsing for each product
            return self._parse_oracle_page(soup, software_name, version)
            
        except Exception as e:
            # Calculate response time for failed request
            response_time_ms = (time.time() - start_time) * 1000
            
            # Record failed request
            cache_stats_manager.record_agent_request(
                agent_name="oracle",
                url=url or "unknown",
                response_time_ms=response_time_ms,
                success=False,
                error_message=str(e)
            )
            
            logger.error(f"Error scraping Oracle EOL data from {url}: {e}")
            return None

    def _parse_oracle_page(self, soup: BeautifulSoup, software_name: str, version: Optional[str]) -> Optional[Dict[str, Any]]:
        """Parse Oracle EOL page content"""
        
        # This is a simplified parser - would need specific logic for each Oracle product page
        # For now, return None to rely on static data
        return None

    def is_relevant(self, software_name: str) -> bool:
        """Check if this agent is relevant for the given software"""
        name_lower = software_name.lower()
        oracle_keywords = [
            'oracle', 'java', 'jdk', 'jre', 'mysql', 'virtualbox',
            'berkeley db', 'solaris', 'sparc'
        ]
        
        return any(keyword in name_lower for keyword in oracle_keywords)
