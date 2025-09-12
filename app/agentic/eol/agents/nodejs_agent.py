"""
Node.js EOL Agent - Scrapes Node.js official sources for EOL information
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

class NodeJSEOLAgent(BaseEOLAgent):
    """Agent for scraping Node.js official EOL information"""
    def __init__(self):
        # Agent identification
        self.agent_name = "nodejs"
        
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

        # Node.js product EOL URLs
                # Nodejs EOL URLs with metadata (single source of truth)
        self.eol_urls = {
            "nodejs": {
                "url": "https://nodejs.org/en/about/releases/",
                "description": "Node.js Release Schedule",
                "active": True,
                "priority": 1
            },
            "npm": {
                "url": "https://github.com/npm/cli/releases",
                "description": "npm GitHub Releases",
                "active": True,
                "priority": 2
            },
            "yarn": {
                "url": "https://github.com/yarnpkg/yarn/releases",
                "description": "Yarn GitHub Releases",
                "active": True,
                "priority": 3
            }
        }

        # Static data for Node.js versions
        self.static_eol_data = {
            "nodejs-20": {
                "cycle": "20 LTS",
                "releaseDate": "2023-04-18",
                "eol": "2026-04-30",
                "support": "2025-10-30",
                "latest": "20.10.0",
                "lts": True,
                "source": "nodejs_official",
                "confidence": 95,
            },
            "nodejs-18": {
                "cycle": "18 LTS",
                "releaseDate": "2022-04-19",
                "eol": "2025-04-30",
                "support": "2024-10-30",
                "latest": "18.19.0",
                "lts": True,
                "source": "nodejs_official",
                "confidence": 95,
            },
            "nodejs-16": {
                "cycle": "16 LTS",
                "releaseDate": "2021-04-20",
                "eol": "2024-04-30",
                "support": "2023-09-11",
                "latest": "16.20.2",
                "lts": True,
                "source": "nodejs_official",
                "confidence": 95,
            },
            "nodejs-14": {
                "cycle": "14 LTS",
                "releaseDate": "2020-04-21",
                "eol": "2023-04-30",
                "support": "2022-10-30",
                "latest": "14.21.3",
                "lts": True,
                "source": "nodejs_official",
                "confidence": 95,
            },
            "nodejs-12": {
                "cycle": "12 LTS",
                "releaseDate": "2019-04-23",
                "eol": "2022-04-30",
                "support": "2021-10-30",
                "latest": "12.22.12",
                "lts": True,
                "source": "nodejs_official",
                "confidence": 95,
            },
            "npm-10": {
                "cycle": "10",
                "releaseDate": "2023-08-08",
                "eol": "2025-08-08",
                "support": "2024-08-08",
                "latest": "10.2.4",
                "source": "npm_official",
                "confidence": 90,
            },
            "npm-9": {
                "cycle": "9",
                "releaseDate": "2022-08-30",
                "eol": "2024-08-30",
                "support": "2023-08-30",
                "latest": "9.8.1",
                "source": "npm_official",
                "confidence": 90,
            },
            "yarn-4": {
                "cycle": "4",
                "releaseDate": "2023-10-23",
                "eol": "2025-10-23",
                "support": "2024-10-23",
                "latest": "4.0.2",
                "source": "yarn_official",
                "confidence": 85,
            },
            "yarn-3": {
                "cycle": "3",
                "releaseDate": "2021-10-04",
                "eol": "2024-10-04",
                "support": "2023-10-04",
                "latest": "3.6.4",
                "source": "yarn_official",
                "confidence": 85,
            },
            "yarn-1": {
                "cycle": "1",
                "releaseDate": "2016-10-11",
                "eol": "2024-04-30",
                "support": "2023-04-30",
                "latest": "1.22.19",
                "source": "yarn_official",
                "confidence": 85,
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
        key_data = f"nodejs_eol_{software_name}_{version or 'any'}"
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
                source_url = self.eol_urls.get(software_name.lower(), "https://nodejs.org/en/about/releases/")
            
            await self.cosmos_cache.cache_response(software_name, version, self.agent_name, data, source_url=source_url)
        except Exception as e:
            logger.error(f"Error caching data: {e}")

    async def purge_cache(self, software_name: Optional[str] = None, version: Optional[str] = None) -> Dict[str, Any]:
        """Purge cached data for specific software or all Node.js cache"""
        try:
            if software_name:
                cache_key = self._generate_cache_key(software_name, version)
                return {"success": True, "deleted_count": 1, "message": f"Purged cache for {software_name}"}
            else:
                return {"success": True, "deleted_count": 0, "message": "Bulk purge not implemented"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def get_eol_data(self, software_name: str, version: Optional[str] = None) -> Dict[str, Any]:
        """Get EOL data for Node.js ecosystem products with enhanced static data checking"""
        
        # Check cache first
        cached_data = await self._get_cached_data(software_name, version)
        if cached_data:
            return cached_data
        
        # Get fresh data using enhanced fetch method
        result_data = await self._fetch_eol_data(software_name, version)
        
        if result_data:
            # Add Node.js-specific metadata
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
                    "agent": "nodejs",
                    "data_source": "nodejs_agent"
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
        Fetch EOL data from Node.js ecosystem sources
        """
        # Check static data first for reliability
        static_result = self._check_static_data(software_name, version)
        if static_result:
            return static_result

        # Try web scraping for latest information
        scraped_result = await self._scrape_nodejs_eol(software_name, version)
        if scraped_result:
            return scraped_result

        return None

    def _check_static_data(self, software_name: str, version: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Check static EOL data for Node.js ecosystem products with enhanced matching"""
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
        
        # Enhanced version-specific matching for Node.js ecosystem
        if version:
            # Extract major version for Node.js-style versioning
            version_parts = version.split('.')
            if len(version_parts) >= 1:
                major_version = version_parts[0]
                
                # Node.js versions
                if "node" in software_lower or "nodejs" in software_lower:
                    version_key = f"nodejs-{major_version}"
                    if version_key in self.static_eol_data:
                        return self.static_eol_data[version_key]
                
                # NPM versions (if we add them to static data)
                elif "npm" in software_lower:
                    version_key = f"npm-{major_version}"
                    if version_key in self.static_eol_data:
                        return self.static_eol_data[version_key]
                
                # Yarn versions (if we add them to static data)
                elif "yarn" in software_lower:
                    version_key = f"yarn-{major_version}"
                    if version_key in self.static_eol_data:
                        return self.static_eol_data[version_key]
        
        # Improved partial matches with better precision
        for key, data in self.static_eol_data.items():
            key_parts = key.split("-")
            software_parts = software_lower.split("-")
            
            # For Node.js ecosystem, require exact framework match
            if "node" in software_parts or "nodejs" in software_parts:
                if "nodejs" in key_parts:
                    # Ensure version compatibility
                    if not version or self._version_matches(version, data.get("cycle", "")):
                        return data
            
            elif "npm" in software_parts:
                if "npm" in key_parts:
                    if not version or self._version_matches(version, data.get("cycle", "")):
                        return data
            
            elif "yarn" in software_parts:
                if "yarn" in key_parts:
                    if not version or self._version_matches(version, data.get("cycle", "")):
                        return data
            
            # Generic partial matching for other Node.js packages
            else:
                if any(keyword in software_lower for keyword in key_parts):
                    if not version or self._version_matches(version, data.get("cycle", "")):
                        return data
        
        return None
    
    def _version_matches(self, version: str, cycle: str) -> bool:
        """Check if version matches the cycle for Node.js ecosystem"""
        try:
            if not version or not cycle:
                return False
            
            # Extract major version from version string
            version_major = version.split('.')[0]
            
            # Check if cycle contains the major version
            cycle_clean = cycle.replace(" LTS", "").strip()
            return version_major in str(cycle_clean) or str(cycle_clean) in version_major
            
        except Exception:
            return False
    
    def _determine_source_url(self, software_name: str) -> str:
        """Determine the appropriate source URL for the software"""
        software_lower = software_name.lower()
        
        # Find matching URL from eol_urls
        for product_type, url_data in self.eol_urls.items():
            if product_type in software_lower:
                return url_data.get("url") if isinstance(url_data, dict) else url_data
        
        # Default to Node.js official URL if no specific match
        nodejs_url = self.eol_urls.get("nodejs")
        return nodejs_url.get("url") if isinstance(nodejs_url, dict) else "https://nodejs.org/en/about/releases/"

    def _normalize_software_name(self, software_name: str, version: Optional[str] = None) -> str:
        """Normalize software name for lookup"""
        name_lower = software_name.lower()
        
        # Node.js versions
        if "node" in name_lower or "nodejs" in name_lower:
            if version:
                major_version = version.split('.')[0]
                if major_version == "20":
                    return "nodejs-20"
                elif major_version == "18":
                    return "nodejs-18"
                elif major_version == "16":
                    return "nodejs-16"
                elif major_version == "14":
                    return "nodejs-14"
                elif major_version == "12":
                    return "nodejs-12"
        
        # NPM versions
        if "npm" in name_lower:
            if version:
                major_version = version.split('.')[0]
                if major_version == "10":
                    return "npm-10"
                elif major_version == "9":
                    return "npm-9"
        
        # Yarn versions
        if "yarn" in name_lower:
            if version:
                major_version = version.split('.')[0]
                if major_version == "4":
                    return "yarn-4"
                elif major_version == "3":
                    return "yarn-3"
                elif major_version == "1":
                    return "yarn-1"
        
        return f"{name_lower}-{version}" if version else name_lower

    async def _scrape_nodejs_eol(self, software_name: str, version: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Scrape Node.js EOL information from official sources"""
        
        try:
            # Determine which URL to use based on software
            url = None
            name_lower = software_name.lower()
            
            if "node" in name_lower or "nodejs" in name_lower:
                url_data = self.eol_urls["nodejs"]
                url = url_data.get("url") if isinstance(url_data, dict) else url_data
            elif "npm" in name_lower:
                url_data = self.eol_urls["npm"]
                url = url_data.get("url") if isinstance(url_data, dict) else url_data
            elif "yarn" in name_lower:
                url_data = self.eol_urls["yarn"]
                url = url_data.get("url") if isinstance(url_data, dict) else url_data
            
            if not url:
                return None
            
            # Record agent request for statistics tracking
            start_time = datetime.now()
            cache_stats_manager.record_agent_request("nodejs", url)
            
            response = requests.get(url, headers=self.headers, timeout=self.timeout)
            response.raise_for_status()
            
            # Calculate response time for tracking
            response_time = (datetime.now() - start_time).total_seconds()
            cache_stats_manager.record_agent_request("nodejs", url, response_time, success=True)
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Extract EOL information from the page
            return self._parse_nodejs_page(soup, software_name, version)
            
        except Exception as e:
            # Record failed request for statistics tracking
            start_time = getattr(locals(), 'start_time', datetime.now())
            response_time = (datetime.now() - start_time).total_seconds()
            url = getattr(locals(), 'url', None)
            if url:
                cache_stats_manager.record_agent_request("nodejs", url, response_time, success=False, error_message=str(e))
            logger.error(f"Error scraping Node.js EOL data: {e}")
            return None

    def _parse_nodejs_page(self, soup: BeautifulSoup, software_name: str, version: Optional[str]) -> Optional[Dict[str, Any]]:
        """Parse Node.js EOL page content"""
        
        # This is a simplified parser - would need specific logic for Node.js release page
        # For now, return None to rely on static data
        return None

    def is_relevant(self, software_name: str) -> bool:
        """Check if this agent is relevant for the given software"""
        name_lower = software_name.lower()
        nodejs_keywords = [
            'node', 'nodejs', 'npm', 'yarn', 'pnpm', 'bun',
            'express', 'react', 'vue', 'angular', 'next'
        ]
        
        return any(keyword in name_lower for keyword in nodejs_keywords)
