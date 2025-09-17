"""
VMware EOL Agent - Scrapes VMware official sources for EOL information
"""
import requests
from bs4 import BeautifulSoup
from typing import Dict, Any, Optional
import re
from datetime import datetime, timedelta
import json
import hashlib
import asyncio
from utils.eol_cache import eol_cache
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
except Exception:
    import logging
    logger = logging.getLogger(__name__)

class VMwareEOLAgent(BaseEOLAgent):
    """Agent for scraping VMware official EOL information"""

    def __init__(self):
        super().__init__("vmware")
        
        self.timeout = 15
        self.headers = {
            'User-Agent': (
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                'AppleWebKit/537.36 (KHTML, like Gecko) '
                'Chrome/91.0.4472.124 Safari/537.36'
            )
        }
        # Initialize Cosmos DB cache (use shared singleton)
        self.cosmos_cache = eol_cache

        # VMware EOL URLs with metadata (single source of truth)
        self.eol_urls = {
            "vsphere": {
                "url": "https://lifecycle.vmware.com/",
                "description": "VMware Product Lifecycle Matrix",
                "active": True,
                "priority": 1
            },
            "vcenter": {
                "url": "https://lifecycle.vmware.com/",
                "description": "VMware Product Lifecycle Matrix",
                "active": True,
                "priority": 2
            },
            "esxi": {
                "url": "https://lifecycle.vmware.com/",
                "description": "VMware Product Lifecycle Matrix",
                "active": True,
                "priority": 3
            },
            "workstation": {
                "url": "https://lifecycle.vmware.com/",
                "description": "VMware Product Lifecycle Matrix",
                "active": True,
                "priority": 4
            },
            "fusion": {
                "url": "https://lifecycle.vmware.com/",
                "description": "VMware Product Lifecycle Matrix",
                "active": True,
                "priority": 5
            },
            "nsx": {
                "url": "https://lifecycle.vmware.com/",
                "description": "VMware Product Lifecycle Matrix",
                "active": True,
                "priority": 6
            },
            "vsan": {
                "url": "https://lifecycle.vmware.com/",
                "description": "VMware Product Lifecycle Matrix",
                "active": True,
                "priority": 7
            }
        }

        # Static data for major VMware products
        self.static_eol_data = {
            "vsphere-8.0": {
                "cycle": "8.0",
                "releaseDate": "2022-10-11",
                "eol": "2027-10-11",
                "support": "2025-10-11",
                "latest": "8.0 U2",
                "source": "vmware_official",
            },
            "vsphere-7.0": {
                "cycle": "7.0",
                "releaseDate": "2020-04-02",
                "eol": "2025-04-02",
                "support": "2023-04-02",
                "latest": "7.0 U3p",
                "source": "vmware_official",
            },
            "vsphere-6.7": {
                "cycle": "6.7",
                "releaseDate": "2018-04-17",
                "eol": "2023-10-15",
                "support": "2022-10-15",
                "latest": "6.7 U3",
                "source": "vmware_official",
            },
            "esxi-8.0": {
                "cycle": "8.0",
                "releaseDate": "2022-10-11",
                "eol": "2027-10-11",
                "support": "2025-10-11",
                "latest": "8.0 U2",
                "source": "vmware_official",
            },
            "esxi-7.0": {
                "cycle": "7.0",
                "releaseDate": "2020-04-02",
                "eol": "2025-04-02",
                "support": "2023-04-02",
                "latest": "7.0 U3p",
                "source": "vmware_official",
            },
            "esxi-6.7": {
                "cycle": "6.7",
                "releaseDate": "2018-04-17",
                "eol": "2023-10-15",
                "support": "2022-10-15",
                "latest": "6.7 U3",
                "source": "vmware_official",
            },
            "vcenter-8.0": {
                "cycle": "8.0",
                "releaseDate": "2022-10-11",
                "eol": "2027-10-11",
                "support": "2025-10-11",
                "latest": "8.0 U2",
                "source": "vmware_official",
            },
            "vcenter-7.0": {
                "cycle": "7.0",
                "releaseDate": "2020-04-02",
                "eol": "2025-04-02",
                "support": "2023-04-02",
                "latest": "7.0 U3p",
                "source": "vmware_official",
            },
            "workstation-17": {
                "cycle": "17",
                "releaseDate": "2021-09-21",
                "eol": "2026-09-21",
                "support": "2024-09-21",
                "latest": "17.5.0",
                "source": "vmware_official",
            },
            "workstation-16": {
                "cycle": "16",
                "releaseDate": "2020-09-15",
                "eol": "2024-09-15",
                "support": "2023-09-15",
                "latest": "16.2.5",
                "source": "vmware_official",
            },
            "fusion-13": {
                "cycle": "13",
                "releaseDate": "2021-11-16",
                "eol": "2026-11-16",
                "support": "2024-11-16",
                "latest": "13.5.0",
                "source": "vmware_official",
            },
            "nsx-t-4.1": {
                "cycle": "4.1",
                "releaseDate": "2023-03-21",
                "eol": "2028-03-21",
                "support": "2026-03-21",
                "latest": "4.1.2",
                "source": "vmware_official",
            },
            "nsx-t-4.0": {
                "cycle": "4.0",
                "releaseDate": "2022-04-05",
                "eol": "2027-04-05",
                "support": "2025-04-05",
                "latest": "4.0.1",
                "source": "vmware_official",
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
        """Generate a unique cache key for VMware EOL data"""
        cache_input = f"vmware:{software_name.lower()}:{version or 'latest'}"
        return hashlib.md5(cache_input.encode()).hexdigest()

    async def _get_cached_data(self, software_name: str, version: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Retrieve cached EOL data if available"""
        try:
            cached_result = await self.cosmos_cache.get_cached_response(software_name, version, self.agent_name)
            
            if cached_result:
                logger.info(f"✅ Cache hit for VMware {software_name} {version or 'latest'}")
                return cached_result
                
            return None
        except Exception as e:
            logger.error(f"Cache retrieval error for VMware {software_name}: {e}")
            return None

    async def _cache_data(self, software_name: str, version: Optional[str], data: Dict[str, Any], confidence_level: int, source_url: Optional[str] = None) -> None:
        """Cache EOL data regardless of confidence level for comprehensive statistics"""
        try:
            # Always cache data to ensure comprehensive statistics and tracking
            data_to_cache = data.copy()
            data_to_cache['confidence_level'] = confidence_level
            
            # Extract source_url from data if not provided explicitly
            if not source_url and 'source_url' in data:
                source_url = data['source_url']
            
            await self.cosmos_cache.cache_response(
                software_name=software_name, 
                version=version, 
                agent_name=self.agent_name, 
                response_data=data_to_cache,
                source_url=source_url
            )
            logger.info(f"✅ Cached VMware {software_name} {version or 'latest'} (confidence: {confidence_level}%) from {source_url or 'static data'}")
        except Exception as e:
            logger.error(f"Cache storage error for VMware {software_name}: {e}")

    async def purge_cache(self, software_name: Optional[str] = None, version: Optional[str] = None) -> Dict[str, Any]:
        """Purge cached VMware EOL data"""
        try:
            if software_name:
                # Purge specific software/version
                cache_key = self._generate_cache_key(software_name, version)
                result = await self.cosmos_cache.delete_cached_data(cache_key)
                return {
                    "status": "success",
                    "action": "purged_specific",
                    "software": software_name,
                    "version": version,
                    "result": result
                }
            else:
                # Purge all VMware cache entries
                result = await self.cosmos_cache.purge_agent_cache("vmware")
                return {
                    "status": "success", 
                    "action": "purged_all",
                    "agent": "vmware",
                    "result": result
                }
        except Exception as e:
            return {
                "status": "error",
                "action": "purge_failed",
                "error": str(e)
            }

    async def get_eol_data(self, software_name: str, version: Optional[str] = None) -> Dict[str, Any]:
        """Get EOL data for VMware products with enhanced static data checking"""
        
        # Try cache first
        cached_data = await self._get_cached_data(software_name, version)
        if cached_data:
            return cached_data
        
        # Get fresh data using enhanced fetch method
        result_data = await self._fetch_eol_data(software_name, version)
        
        if result_data:
            # Add VMware-specific metadata
            source_url = self._determine_source_url(software_name)
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
                    "agent": "vmware",
                    "data_source": "vmware_agent"
                }
            )
            
            # Cache the result
            await self._cache_data(software_name, version, result, confidence, source_url)
            return result
        
        # No data found - don't cache negative results
        return self.create_failure_response(
            f"No EOL information found for {software_name}" + (f" version {version}" if version else ""),
            "no_data_found",
            {"searched_product": software_name, "searched_version": version}
        )

    async def _fetch_eol_data(self, software_name: str, version: str = None) -> Optional[Dict[str, Any]]:
        """
        Fetch EOL data from VMware sources
        """
        # Check static data first for reliability
        static_result = self._check_static_data(software_name, version)
        if static_result:
            return static_result

        # Try web scraping for latest information
        scraped_result = await self._scrape_vmware_eol(software_name, version)
        if scraped_result:
            return scraped_result

        return None

    def _check_static_data(self, software_name: str, version: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Check static EOL data for VMware products with enhanced matching"""
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
        
        # Enhanced version-specific matching for VMware products
        if version:
            # Extract major.minor version for VMware-style versioning
            version_parts = version.split('.')
            if len(version_parts) >= 2:
                major_minor = f"{version_parts[0]}.{version_parts[1]}"
                
                # vSphere versions
                if "vsphere" in software_lower:
                    version_key = f"vsphere-{major_minor}"
                    if version_key in self.static_eol_data:
                        return self.static_eol_data[version_key]
                
                # ESXi versions
                elif "esxi" in software_lower:
                    version_key = f"esxi-{major_minor}"
                    if version_key in self.static_eol_data:
                        return self.static_eol_data[version_key]
                
                # vCenter versions
                elif "vcenter" in software_lower:
                    version_key = f"vcenter-{major_minor}"
                    if version_key in self.static_eol_data:
                        return self.static_eol_data[version_key]
                
                # NSX versions
                elif "nsx" in software_lower:
                    version_key = f"nsx-{major_minor}"
                    if version_key in self.static_eol_data:
                        return self.static_eol_data[version_key]
        
        # Improved partial matches with better precision
        for key, data in self.static_eol_data.items():
            key_parts = key.split("-")
            software_parts = software_lower.split("-")
            
            # For VMware products, require exact product match
            if "vsphere" in software_parts:
                if "vsphere" in key_parts:
                    if not version or self._version_matches(version, data.get("cycle", "")):
                        return data
            
            elif "esxi" in software_parts:
                if "esxi" in key_parts:
                    if not version or self._version_matches(version, data.get("cycle", "")):
                        return data
            
            elif "vcenter" in software_parts:
                if "vcenter" in key_parts:
                    if not version or self._version_matches(version, data.get("cycle", "")):
                        return data
            
            elif "nsx" in software_parts:
                if "nsx" in key_parts:
                    if not version or self._version_matches(version, data.get("cycle", "")):
                        return data
            
            # Generic partial matching for other VMware products
            else:
                if any(keyword in software_lower for keyword in key_parts):
                    if not version or self._version_matches(version, data.get("cycle", "")):
                        return data
        
        return None
    
    def _version_matches(self, version: str, cycle: str) -> bool:
        """Check if version matches the cycle for VMware products"""
        try:
            if not version or not cycle:
                return False
            
            # Extract major.minor version from version string
            version_parts = version.split('.')
            if len(version_parts) >= 2:
                version_major_minor = f"{version_parts[0]}.{version_parts[1]}"
            else:
                version_major_minor = version_parts[0]
            
            # Check if cycle contains the version
            return version_major_minor in str(cycle) or str(cycle) in version_major_minor
            
        except Exception:
            return False
    
    def _determine_source_url(self, software_name: str) -> str:
        """Determine the appropriate source URL for the software"""
        # VMware uses a centralized lifecycle page
        return "https://lifecycle.vmware.com/"

    def _normalize_software_name(self, software_name: str, version: Optional[str] = None) -> str:
        """Normalize software name for lookup"""
        name_lower = software_name.lower()
        
        # vSphere versions
        if "vsphere" in name_lower:
            if version:
                if "8" in version:
                    return "vsphere-8.0"
                elif "7" in version:
                    return "vsphere-7.0"
                elif "6.7" in version:
                    return "vsphere-6.7"
        
        # ESXi versions
        if "esxi" in name_lower:
            if version:
                if "8" in version:
                    return "esxi-8.0"
                elif "7" in version:
                    return "esxi-7.0"
                elif "6.7" in version:
                    return "esxi-6.7"
        
        # vCenter versions
        if "vcenter" in name_lower:
            if version:
                if "8" in version:
                    return "vcenter-8.0"
                elif "7" in version:
                    return "vcenter-7.0"
        
        # Workstation versions
        if "workstation" in name_lower:
            if version:
                if "17" in version:
                    return "workstation-17"
                elif "16" in version:
                    return "workstation-16"
        
        # Fusion versions
        if "fusion" in name_lower:
            if version:
                if "13" in version:
                    return "fusion-13"
        
        # NSX-T versions
        if "nsx" in name_lower:
            if version:
                if "4.1" in version:
                    return "nsx-t-4.1"
                elif "4.0" in version:
                    return "nsx-t-4.0"
        
        return f"{name_lower}-{version}" if version else name_lower

    async def _scrape_vmware_eol(self, software_name: str, version: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Scrape VMware EOL information from official sources"""
        
        try:
            # VMware lifecycle page
            url = "https://lifecycle.vmware.com/"
            
            # Record agent request for statistics tracking
            start_time = datetime.now()
            cache_stats_manager.record_agent_request("vmware", url)
            
            response = requests.get(url, headers=self.headers, timeout=self.timeout)
            response.raise_for_status()
            
            # Calculate response time for tracking
            response_time = (datetime.now() - start_time).total_seconds()
            cache_stats_manager.record_agent_request("vmware", url, response_time, success=True)
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Extract EOL information from the page
            # This is a simplified extraction - would need more specific parsing
            return self._parse_vmware_page(soup, software_name, version)
            
        except Exception as e:
            # Record failed request for statistics tracking
            start_time = getattr(locals(), 'start_time', datetime.now())
            response_time = (datetime.now() - start_time).total_seconds()
            url = getattr(locals(), 'url', "https://lifecycle.vmware.com/")
            cache_stats_manager.record_agent_request("vmware", url, response_time, success=False, error_message=str(e))
            logger.error(f"Error scraping VMware EOL data: {e}")
            return None

    def _parse_vmware_page(self, soup: BeautifulSoup, software_name: str, version: Optional[str]) -> Optional[Dict[str, Any]]:
        """Parse VMware lifecycle page content"""
        
        # This is a simplified parser - would need specific logic for VMware's dynamic content
        # For now, return None to rely on static data
        return None

    def is_relevant(self, software_name: str) -> bool:
        """Check if this agent is relevant for the given software"""
        name_lower = software_name.lower()
        vmware_keywords = [
            'vmware', 'vsphere', 'esxi', 'vcenter', 'workstation',
            'fusion', 'nsx', 'vsan', 'vrealize', 'vcloud'
        ]
        
        return any(keyword in name_lower for keyword in vmware_keywords)
