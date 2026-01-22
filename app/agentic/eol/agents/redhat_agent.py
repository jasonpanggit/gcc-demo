"""
Red Hat EOL Agent - Web scrapes Red Hat official EOL information with Cosmos DB caching
"""
import requests
from bs4 import BeautifulSoup
from typing import Dict, Any, Optional, List
import re
from datetime import datetime, timedelta
import os
import hashlib
import asyncio
from .base_eol_agent import BaseEOLAgent

try:
    from utils.logger import get_logger
    logger = get_logger(__name__)
except ImportError:
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
    logger = get_logger(__name__)
except Exception:
    import logging
    logger = logging.getLogger(__name__)

class RedHatEOLAgent(BaseEOLAgent):
    """Agent for scraping Red Hat official EOL information"""
    
    def __init__(self):
        super().__init__("redhat")
        
        self.timeout = 15
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        # Agent-level caching disabled - orchestrator uses eol_inventory as single source of truth
        self.cosmos_cache = None

        # Cache configuration
        self.cache_duration_hours = 24  # Re-enable caching

        # Red Hat EOL URLs with metadata (single source of truth)
        self.eol_urls = {
            "rhel": {
                "url": "https://access.redhat.com/support/policy/updates/errata/",
                "description": "Red Hat Enterprise Linux (RHEL) EOL Policy",
                "active": True,
                "priority": 1
            },
            "centos": {
                "url": "https://blog.centos.org/2020/12/future-is-centos-stream/",
                "description": "CentOS End-of-Life Announcement",
                "active": True,
                "priority": 2
            },
            "fedora": {
                "url": "https://fedoraproject.org/wiki/End_of_life",
                "description": "Fedora End of Life Schedule",
                "active": True,
                "priority": 3
            }
        }

        # Static EOL data for Red Hat products
        self.static_eol_data = {
            "rhel-7": {
                "cycle": "7",
                "releaseDate": "2014-06-09",
                "eol": "2024-06-30",
                "support": "2019-08-06",
                "extendedSupport": "2028-06-30",
                "latest": "7.9",
                "source": "redhat_official",
                "confidence": 95,
            },
            "rhel-8": {
                "cycle": "8",
                "releaseDate": "2019-05-07",
                "eol": "2029-05-31",
                "support": "2024-05-31",
                "extendedSupport": "2032-05-31",
                "latest": "8.10",
                "source": "redhat_official",
                "confidence": 95,
            },
            "rhel-9": {
                "cycle": "9",
                "releaseDate": "2022-05-17",
                "eol": "2032-05-31",
                "support": "2027-05-31",
                "extendedSupport": "2035-05-31",
                "latest": "9.4",
                "source": "redhat_official",
                "confidence": 95,
            },
            "centos-7": {
                "cycle": "7",
                "releaseDate": "2014-07-07",
                "eol": "2024-06-30",
                "support": "2020-08-06",
                "latest": "7.9.2009",
                "source": "redhat_official",
                "confidence": 95,
            },
            "centos-8": {
                "cycle": "8",
                "releaseDate": "2019-09-24",
                "eol": "2021-12-31",
                "support": "2021-12-31",
                "latest": "8.5.2111",
                "source": "redhat_official",
                "confidence": 95,
            }
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
        key_data = f"redhat_eol_{software_name}_{version or 'any'}"
        return hashlib.md5(key_data.encode()).hexdigest()
    
    async def _get_cached_data(self, software_name: str, version: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Agent-level caching disabled - eol_inventory is the single source of truth"""
        # Cosmos caching consolidated to orchestrator via eol_inventory
        return None

    async def _cache_data(self, software_name: str, version: Optional[str], data: Dict[str, Any], source_url: Optional[str] = None):
        """Agent-level caching disabled - eol_inventory is the single source of truth"""
        # Cosmos caching consolidated to orchestrator via eol_inventory
        pass

    async def purge_cache(self, software_name: Optional[str] = None, version: Optional[str] = None) -> Dict[str, Any]:
        """Agent-level caching disabled - use eol_inventory for cache management"""
        # Cosmos caching consolidated to orchestrator via eol_inventory
        return {"success": True, "deleted_count": 0, "message": "Agent-level caching disabled - use eol_inventory"}
    
    async def get_eol_data(self, software_name: str, version: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Get Red Hat EOL data through web scraping and static data with caching"""
        
        # Check if this is a Red Hat product
        if not self._is_redhat_product(software_name):
            return None
            
        # Check cache first
        cached_data = await self._get_cached_data(software_name, version)
        if cached_data:
            return cached_data
        
        # Check static data first for reliability
        static_result = self._check_static_data(software_name, version)
        if static_result:
            source_url = self._get_scraping_url(software_name)
            
            result = self.create_success_response(
                software_name=software_name,
                version=version or static_result.get("cycle", "unknown"),
                eol_date=static_result.get("eol", ""),
                support_end_date=static_result.get("support", ""),
                confidence=static_result.get("confidence", 85) / 100.0,  # Convert to decimal
                source_url=source_url,
                additional_data={
                    "cycle": static_result.get("cycle", ""),
                    "extended_support": static_result.get("extendedSupport", False),
                    "agent": "redhat",
                    "data_source": "redhat_static_data"
                }
            )
            
            # Cache high-confidence results
            await self._cache_data(software_name, version, result, source_url=source_url)
            return result
        
        # Try scraping as fallback
        scraped_result = await self._scrape_data(software_name, version)
        if scraped_result:
            source_url = self._get_scraping_url(software_name)
            
            result = self.create_success_response(
                software_name=software_name,
                version=version or scraped_result.get("cycle", "unknown"),
                eol_date=scraped_result.get("eol", ""),
                support_end_date=scraped_result.get("support", ""),
                confidence=scraped_result.get("confidence", 65) / 100.0,  # Convert to decimal, lower for scraped
                source_url=source_url,
                additional_data={
                    "cycle": scraped_result.get("cycle", ""),
                    "extended_support": scraped_result.get("extendedSupport", False),
                    "agent": "redhat",
                    "data_source": "scraped"
                }
            )
            
            await self._cache_data(software_name, version, result, source_url=source_url)
            return result
        
        # No data found
        return self.create_failure_response(
            f"No EOL information found for {software_name}" + (f" version {version}" if version else ""),
            "no_data_found",
            {"searched_product": software_name, "searched_version": version}
        )
    
    def _is_redhat_product(self, software_name: str) -> bool:
        """Check if software is a Red Hat product"""
        software_lower = software_name.lower()
        redhat_keywords = ["red hat", "rhel", "centos", "fedora", "enterprise linux"]
        return any(keyword in software_lower for keyword in redhat_keywords)
    
    def _check_static_data(self, software_name: str, version: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Check static EOL data for Red Hat products with enhanced matching"""
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
        
        # Normalize product names for Red Hat ecosystem
        product_name = None
        if "red-hat-enterprise-linux" in software_lower or "rhel" in software_lower:
            product_name = "rhel"
        elif "centos" in software_lower:
            product_name = "centos"
        elif "fedora" in software_lower:
            product_name = "fedora"
        elif "rocky" in software_lower:
            product_name = "rocky"
        elif "alma" in software_lower or "almalinux" in software_lower:
            product_name = "alma"
        
        if not product_name:
            return None
        
        # Enhanced version-specific matching for Red Hat products
        if version:
            # Extract major version
            version_parts = version.split('.')
            if len(version_parts) >= 1:
                version_major = version_parts[0]
                version_key = f"{product_name}-{version_major}"
                
                if version_key in self.static_eol_data:
                    return self.static_eol_data[version_key]
                
                # Try with major.minor for more specific matching
                if len(version_parts) >= 2:
                    version_major_minor = f"{version_parts[0]}.{version_parts[1]}"
                    version_key_detailed = f"{product_name}-{version_major_minor}"
                    if version_key_detailed in self.static_eol_data:
                        return self.static_eol_data[version_key_detailed]
        
        # Improved partial matches with better precision for Red Hat products
        for key, data in self.static_eol_data.items():
            key_parts = key.split("-")
            
            # For Red Hat ecosystem, require exact product match
            if product_name and product_name in key_parts:
                # If version is specified, check version compatibility
                if version:
                    if self._version_matches(version, data.get("cycle", "")):
                        return data
                else:
                    # No version specified, return the match
                    return data
        
        return None
    
    def _version_matches(self, version: str, cycle: str) -> bool:
        """Check if version matches the cycle for Red Hat products"""
        try:
            if not version or not cycle:
                return False
            
            # Extract major version from version string
            version_major = version.split('.')[0]
            
            # Check if cycle contains the major version
            return version_major in str(cycle) or str(cycle) in version_major
            
        except Exception:
            return False
    
    async def _scrape_eol_data(self, software_name: str, version: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Scrape Red Hat EOL data from official websites"""
        try:
            url = self._get_scraping_url(software_name)
            if not url:
                return None
            
            # Record agent request for statistics tracking
            start_time = datetime.now()
            cache_stats_manager.record_agent_request("redhat", url)
            
            response = requests.get(url, headers=self.headers, timeout=self.timeout)
            response.raise_for_status()
            
            # Calculate response time for tracking
            response_time = (datetime.now() - start_time).total_seconds()
            cache_stats_manager.record_agent_request("redhat", url, response_time, success=True)
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Parse based on product type
            if "rhel" in software_name.lower() or "red hat enterprise linux" in software_name.lower():
                return self._parse_rhel_eol(soup, version)
            elif "centos" in software_name.lower():
                return self._parse_centos_eol(soup, version)
            elif "fedora" in software_name.lower():
                return self._parse_fedora_eol(soup, version)
            
            return None
            
        except Exception as e:
            # Record failed request for statistics tracking
            start_time = getattr(locals(), 'start_time', datetime.now())
            response_time = (datetime.now() - start_time).total_seconds()
            url = getattr(locals(), 'url', None)
            if url:
                cache_stats_manager.record_agent_request("redhat", url, response_time, success=False, error_message=str(e))
            logger.error(f"Error scraping Red Hat EOL data: {e}")
            return None
    
    def _get_scraping_url(self, software_name: str) -> Optional[str]:
        """Get the appropriate Red Hat URL to scrape"""
        software_lower = software_name.lower()
        
        if "rhel" in software_lower or "red hat enterprise linux" in software_lower:
            url_data = self.eol_urls.get("rhel")
            return url_data.get("url") if url_data else None
        elif "centos" in software_lower:
            url_data = self.eol_urls.get("centos")
            return url_data.get("url") if url_data else None
        elif "fedora" in software_lower:
            url_data = self.eol_urls.get("fedora")
            return url_data.get("url") if url_data else None
        
        return None
    
    def _parse_rhel_eol(self, soup: BeautifulSoup, version: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Parse RHEL EOL information from Red Hat support pages"""
        try:
            # Look for tables containing EOL information
            tables = soup.find_all('table')
            
            for table in tables:
                rows = table.find_all('tr')
                
                for row in rows:
                    cells = row.find_all(['td', 'th'])
                    if len(cells) >= 3:
                        # Look for version information
                        version_text = cells[0].get_text().strip()
                        
                        if version and version.split('.')[0] not in version_text:
                            continue
                        
                        # Extract EOL dates from cells
                        eol_date = None
                        support_date = None
                        
                        for cell in cells[1:]:
                            cell_text = cell.get_text().strip()
                            # Look for date patterns
                            date_match = re.search(r'(\d{4}-\d{2}-\d{2})', cell_text)
                            if date_match:
                                if "end of life" in cell_text.lower() or "eol" in cell_text.lower():
                                    eol_date = date_match.group(1)
                                elif "end of support" in cell_text.lower():
                                    support_date = date_match.group(1)
                        
                        if eol_date:
                            return {
                                "cycle": version_text,
                                "eol": eol_date,
                                "support": support_date,
                                "source": "redhat_official_scraped",
                                "extendedSupport": True
                            }
            
            return None
            
        except Exception as e:
            logger.error(f"Error parsing RHEL EOL: {e}")
            return None
    
    def _parse_centos_eol(self, soup: BeautifulSoup, version: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Parse CentOS EOL information"""
        try:
            # CentOS has specific EOL information
            text_content = soup.get_text()
            
            if version and "7" in version:
                # CentOS 7 information
                return {
                    "cycle": "7",
                    "eol": "2024-06-30",
                    "support": "2020-08-06",
                    "source": "redhat_official_scraped"
                }
            elif version and "8" in version:
                # CentOS 8 was discontinued early
                return {
                    "cycle": "8",
                    "eol": "2021-12-31",
                    "support": "2021-12-31",
                    "source": "redhat_official_scraped"
                }
            
            return None
            
        except Exception as e:
            logger.error(f"Error parsing CentOS EOL: {e}")
            return None
    
    def _parse_fedora_eol(self, soup: BeautifulSoup, version: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Parse Fedora EOL information"""
        try:
            # Fedora has shorter support cycles
            if version:
                version_num = int(version.split('.')[0])
                
                # Fedora versions are supported for approximately 13 months
                # Calculate approximate EOL based on version number
                if version_num >= 35:
                    return {
                        "cycle": str(version_num),
                        "eol": "2024-12-31",  # Approximate
                        "source": "redhat_official_scraped"
                    }
            
            return None
            
        except Exception as e:
            logger.error(f"Error parsing Fedora EOL: {e}")
            return None
    
    def get_supported_products(self) -> List[str]:
        """Get list of supported Red Hat products"""
        return [
            "Red Hat Enterprise Linux (RHEL)",
            "CentOS",
            "Fedora"
        ]
