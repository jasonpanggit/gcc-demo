"""
PostgreSQL EOL Agent - Scrapes PostgreSQL official sources for EOL information
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

class PostgreSQLEOLAgent(BaseEOLAgent):
    """Agent for scraping PostgreSQL official EOL information"""

    def __init__(self):
        super().__init__("postgresql")
        
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

        # PostgreSQL EOL URLs with metadata (single source of truth)
        self.eol_urls = {
            "postgresql": {
                "url": "https://www.postgresql.org/support/versioning/",
                "description": "PostgreSQL Versioning Policy",
                "active": True,
                "priority": 1
            },
            "postgis": {
                "url": "https://postgis.net/support/",
                "description": "PostGIS Support Information",
                "active": True,
                "priority": 2
            }
        }

        # Static data for PostgreSQL versions
        self.static_eol_data = {
            "postgresql-16": {
                "cycle": "16",
                "releaseDate": "2023-09-14",
                "eol": "2028-11-09",
                "support": "2028-11-09",
                "latest": "16.1",
                "source": "postgresql_official",
            },
            "postgresql-15": {
                "cycle": "15",
                "releaseDate": "2022-10-13",
                "eol": "2027-11-11",
                "support": "2027-11-11",
                "latest": "15.5",
                "source": "postgresql_official",
            },
            "postgresql-14": {
                "cycle": "14",
                "releaseDate": "2021-09-30",
                "eol": "2026-11-12",
                "support": "2026-11-12",
                "latest": "14.10",
                "source": "postgresql_official",
            },
            "postgresql-13": {
                "cycle": "13",
                "releaseDate": "2020-09-24",
                "eol": "2025-11-13",
                "support": "2025-11-13",
                "latest": "13.13",
                "source": "postgresql_official",
            },
            "postgresql-12": {
                "cycle": "12",
                "releaseDate": "2019-10-03",
                "eol": "2024-11-14",
                "support": "2024-11-14",
                "latest": "12.17",
                "source": "postgresql_official",
            },
            "postgresql-11": {
                "cycle": "11",
                "releaseDate": "2018-10-18",
                "eol": "2023-11-09",
                "support": "2023-11-09",
                "latest": "11.22",
                "source": "postgresql_official",
            },
            "postgresql-10": {
                "cycle": "10",
                "releaseDate": "2017-10-05",
                "eol": "2022-11-10",
                "support": "2022-11-10",
                "latest": "10.23",
                "source": "postgresql_official",
            },
            "postgis-3.4": {
                "cycle": "3.4",
                "releaseDate": "2023-09-18",
                "eol": "2027-09-18",
                "support": "2026-09-18",
                "latest": "3.4.0",
                "source": "postgis_official",
            },
            "postgis-3.3": {
                "cycle": "3.3",
                "releaseDate": "2022-08-27",
                "eol": "2026-08-27",
                "support": "2025-08-27",
                "latest": "3.3.4",
                "source": "postgis_official",
            },
            "postgis-3.2": {
                "cycle": "3.2",
                "releaseDate": "2021-12-18",
                "eol": "2025-12-18",
                "support": "2024-12-18",
                "latest": "3.2.5",
                "source": "postgis_official",
            },
            "postgis-3.1": {
                "cycle": "3.1",
                "releaseDate": "2020-12-18",
                "eol": "2024-12-18",
                "support": "2023-12-18",
                "latest": "3.1.9",
                "source": "postgis_official",
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
        """Generate a unique cache key for PostgreSQL EOL data"""
        cache_input = f"postgresql:{software_name.lower()}:{version or 'latest'}"
        return hashlib.md5(cache_input.encode()).hexdigest()

    async def _get_cached_data(self, software_name: str, version: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Retrieve cached EOL data if available"""
        try:
            cached_result = await self.cosmos_cache.get_cached_response(software_name, version, self.agent_name)
            
            if cached_result:
                logger.info(f"✅ Cache hit for PostgreSQL {software_name} {version or 'latest'}")
                return cached_result
                
            return None
        except Exception as e:
            logger.error(f"Cache retrieval error for PostgreSQL {software_name}: {e}")
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
            logger.info(f"✅ Cached PostgreSQL {software_name} {version or 'latest'} (confidence: {confidence_level}%) from {source_url or 'static data'}")
        except Exception as e:
            logger.error(f"Cache storage error for PostgreSQL {software_name}: {e}")

    async def purge_cache(self, software_name: Optional[str] = None, version: Optional[str] = None) -> Dict[str, Any]:
        """Purge cached PostgreSQL EOL data"""
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
                # Purge all PostgreSQL cache entries
                result = await self.cosmos_cache.purge_agent_cache("postgresql")
                return {
                    "status": "success", 
                    "action": "purged_all",
                    "agent": "postgresql",
                    "result": result
                }
        except Exception as e:
            return {
                "status": "error",
                "action": "purge_failed",
                "error": str(e)
            }

    async def get_eol_data(self, software_name: str, version: Optional[str] = None) -> Dict[str, Any]:
        """Get EOL data for PostgreSQL products with enhanced static data checking"""
        
        # Try cache first
        cached_data = await self._get_cached_data(software_name, version)
        if cached_data:
            return cached_data
        
        # Get fresh data using enhanced fetch method
        result_data = await self._fetch_eol_data(software_name, version)
        
        if result_data:
            # Add PostgreSQL-specific metadata
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
                    "agent": "postgresql",
                    "data_source": "postgresql_agent"
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
        Fetch EOL data from PostgreSQL ecosystem sources
        """
        # Check static data first for reliability
        static_result = self._check_static_data(software_name, version)
        if static_result:
            return static_result

        # Try web scraping for latest information
        scraped_result = await self._scrape_postgresql_eol(software_name, version)
        if scraped_result:
            return scraped_result

        return None

    def _check_static_data(self, software_name: str, version: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Check static EOL data for PostgreSQL ecosystem products with enhanced matching"""
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
        
        # Enhanced version-specific matching for PostgreSQL ecosystem
        if version:
            # Extract major version for PostgreSQL-style versioning
            version_parts = version.split('.')
            if len(version_parts) >= 1:
                major_version = version_parts[0]
                
                # PostgreSQL versions
                if ("postgresql" in software_lower or "postgres" in software_lower) and "postgis" not in software_lower:
                    version_key = f"postgresql-{major_version}"
                    if version_key in self.static_eol_data:
                        return self.static_eol_data[version_key]
                
                # PostGIS versions
                elif "postgis" in software_lower:
                    # PostGIS uses major.minor versioning
                    if len(version_parts) >= 2:
                        major_minor = f"{version_parts[0]}.{version_parts[1]}"
                        version_key = f"postgis-{major_minor}"
                        if version_key in self.static_eol_data:
                            return self.static_eol_data[version_key]
        
        # Improved partial matches with better precision
        for key, data in self.static_eol_data.items():
            key_parts = key.split("-")
            software_parts = software_lower.split("-")
            
            # For PostgreSQL ecosystem, require exact product match
            if ("postgresql" in software_parts or "postgres" in software_parts) and "postgis" not in software_parts:
                if "postgresql" in key_parts:
                    # Ensure version compatibility
                    if not version or self._version_matches(version, data.get("cycle", "")):
                        return data
            
            elif "postgis" in software_parts:
                if "postgis" in key_parts:
                    if not version or self._version_matches(version, data.get("cycle", "")):
                        return data
            
            # Generic partial matching for other PostgreSQL-related packages
            else:
                if any(keyword in software_lower for keyword in key_parts):
                    if not version or self._version_matches(version, data.get("cycle", "")):
                        return data
        
        return None
    
    def _version_matches(self, version: str, cycle: str) -> bool:
        """Check if version matches the cycle for PostgreSQL ecosystem"""
        try:
            if not version or not cycle:
                return False
            
            # Extract major version from version string
            version_major = version.split('.')[0]
            
            # Check if cycle contains the major version
            return version_major in str(cycle) or str(cycle) in version_major
            
        except Exception:
            return False
    
    def _determine_source_url(self, software_name: str) -> str:
        """Determine the appropriate source URL for the software"""
        software_lower = software_name.lower()
        
        # Find matching URL from eol_urls
        for product_type, url_data in self.eol_urls.items():
            if product_type in software_lower:
                return url_data.get("url") if isinstance(url_data, dict) else url_data
        
        # Default to PostgreSQL official URL if no specific match
        return "https://www.postgresql.org/support/versioning/"

    def _normalize_software_name(self, software_name: str, version: Optional[str] = None) -> str:
        """Normalize software name for lookup"""
        name_lower = software_name.lower()
        
        # PostgreSQL versions
        if "postgresql" in name_lower or "postgres" in name_lower:
            if version:
                major_version = version.split('.')[0]
                if major_version == "16":
                    return "postgresql-16"
                elif major_version == "15":
                    return "postgresql-15"
                elif major_version == "14":
                    return "postgresql-14"
                elif major_version == "13":
                    return "postgresql-13"
                elif major_version == "12":
                    return "postgresql-12"
                elif major_version == "11":
                    return "postgresql-11"
                elif major_version == "10":
                    return "postgresql-10"
        
        # PostGIS versions
        if "postgis" in name_lower:
            if version:
                # Extract major.minor version
                version_parts = version.split('.')
                if len(version_parts) >= 2:
                    major_minor = f"{version_parts[0]}.{version_parts[1]}"
                    if major_minor == "3.4":
                        return "postgis-3.4"
                    elif major_minor == "3.3":
                        return "postgis-3.3"
                    elif major_minor == "3.2":
                        return "postgis-3.2"
                    elif major_minor == "3.1":
                        return "postgis-3.1"
        
        return f"{name_lower}-{version}" if version else name_lower

    async def _scrape_postgresql_eol(self, software_name: str, version: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Scrape PostgreSQL EOL information from official sources"""
        
        try:
            # Determine which URL to use based on software
            url = None
            name_lower = software_name.lower()
            
            if "postgresql" in name_lower or "postgres" in name_lower:
                url_data = self.eol_urls["postgresql"]
                url = url_data.get("url") if isinstance(url_data, dict) else url_data
            elif "postgis" in name_lower:
                url_data = self.eol_urls["postgis"]
                url = url_data.get("url") if isinstance(url_data, dict) else url_data
            
            if not url:
                return None
            
            # Record agent request for statistics tracking
            start_time = datetime.now()
            cache_stats_manager.record_agent_request("postgresql", url)
            
            response = requests.get(url, headers=self.headers, timeout=self.timeout)
            response.raise_for_status()
            
            # Calculate response time for tracking
            response_time = (datetime.now() - start_time).total_seconds()
            cache_stats_manager.record_agent_request("postgresql", url, response_time, success=True)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Extract EOL information from the page
            return self._parse_postgresql_page(soup, software_name, version)
            
        except Exception as e:
            # Record failed request for statistics tracking
            start_time = getattr(locals(), 'start_time', datetime.now())
            response_time = (datetime.now() - start_time).total_seconds()
            url = getattr(locals(), 'url', None)
            if url:
                cache_stats_manager.record_agent_request("postgresql", url, response_time, success=False, error_message=str(e))
            logger.error(f"Error scraping PostgreSQL EOL data: {e}")
            return None

    def _parse_postgresql_page(self, soup: BeautifulSoup, software_name: str, version: Optional[str]) -> Optional[Dict[str, Any]]:
        """Parse PostgreSQL EOL page content"""
        
        # This is a simplified parser - would need specific logic for PostgreSQL version page
        # For now, return None to rely on static data
        return None

    def is_relevant(self, software_name: str) -> bool:
        """Check if this agent is relevant for the given software"""
        name_lower = software_name.lower()
        postgresql_keywords = [
            'postgresql', 'postgres', 'postgis', 'pgbouncer',
            'pgpool', 'pg_dump', 'psql', 'timescaledb'
        ]
        
        return any(keyword in name_lower for keyword in postgresql_keywords)
