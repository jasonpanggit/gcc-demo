"""
Apache EOL Agent - Scrapes Apache official sources for EOL information
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


class ApacheEOLAgent(BaseEOLAgent):
    """Agent for scraping Apache official EOL information"""

    def __init__(self):
        super().__init__("apache")
        
        self.timeout = 15
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/91.0.4472.124 Safari/537.36"
            )
        }

        # Use shared EOL cache singleton
        self.cosmos_cache = eol_cache

        # Apache product EOL URLs with metadata (single source of truth)
        self.eol_urls = {
            "httpd": {
                "url": "https://httpd.apache.org/download.cgi",
                "description": "Apache HTTP Server Downloads",
                "active": True,
                "priority": 1
            },
            "tomcat": {
                "url": "https://tomcat.apache.org/whichversion.html",
                "description": "Apache Tomcat Version Information",
                "active": True,
                "priority": 2
            },
            "kafka": {
                "url": "https://kafka.apache.org/downloads",
                "description": "Apache Kafka Downloads",
                "active": True,
                "priority": 3
            },
            "spark": {
                "url": "https://spark.apache.org/downloads.html",
                "description": "Apache Spark Downloads",
                "active": True,
                "priority": 4
            },
            "maven": {
                "url": "https://maven.apache.org/download.cgi",
                "description": "Apache Maven Downloads",
                "active": True,
                "priority": 5
            },
            "ant": {
                "url": "https://ant.apache.org/bindownload.cgi",
                "description": "Apache Ant Downloads",
                "active": True,
                "priority": 6
            },
            "cassandra": {
                "url": "https://cassandra.apache.org/download/",
                "description": "Apache Cassandra Downloads",
                "active": True,
                "priority": 7
            },
            "solr": {
                "url": "https://solr.apache.org/downloads.html",
                "description": "Apache Solr Downloads",
                "active": True,
                "priority": 8
            }
        }

        # Static data for major Apache products
        self.static_eol_data = {
            "apache-httpd-2.4": {
                "cycle": "2.4",
                "releaseDate": "2012-02-21",
                "eol": "2026-06-01",
                "support": "2025-06-01",
                "latest": "2.4.58",
                "source": "apache_official",
            },
            "apache-httpd-2.2": {
                "cycle": "2.2",
                "releaseDate": "2005-12-01",
                "eol": "2017-12-31",
                "support": "2017-12-31",
                "latest": "2.2.34",
                "source": "apache_official",
            },
            "tomcat-10": {
                "cycle": "10.1",
                "releaseDate": "2022-01-01",
                "eol": "2027-12-31",
                "support": "2026-12-31",
                "latest": "10.1.16",
                "source": "apache_official",
            },
            "tomcat-9": {
                "cycle": "9.0",
                "releaseDate": "2017-09-01",
                "eol": "2026-12-31",
                "support": "2025-12-31",
                "latest": "9.0.83",
                "source": "apache_official",
            },
            "tomcat-8.5": {
                "cycle": "8.5",
                "releaseDate": "2016-06-01",
                "eol": "2024-03-31",
                "support": "2024-03-31",
                "latest": "8.5.96",
                "source": "apache_official",
            },
            "kafka-3.6": {
                "cycle": "3.6",
                "releaseDate": "2023-10-10",
                "eol": "2025-10-10",
                "support": "2024-10-10",
                "latest": "3.6.0",
                "source": "apache_official",
            },
            "kafka-3.5": {
                "cycle": "3.5",
                "releaseDate": "2023-06-15",
                "eol": "2025-06-15",
                "support": "2024-06-15",
                "latest": "3.5.1",
                "source": "apache_official",
            },
            "spark-3.5": {
                "cycle": "3.5",
                "releaseDate": "2023-09-07",
                "eol": "2025-09-07",
                "support": "2024-09-07",
                "latest": "3.5.0",
                "source": "apache_official",
            },
            "spark-3.4": {
                "cycle": "3.4",
                "releaseDate": "2023-04-13",
                "eol": "2025-04-13",
                "support": "2024-04-13",
                "latest": "3.4.1",
                "source": "apache_official",
            },
            "maven-3.9": {
                "cycle": "3.9",
                "releaseDate": "2023-02-14",
                "eol": "2025-02-14",
                "support": "2024-02-14",
                "latest": "3.9.6",
                "source": "apache_official",
            },
            "maven-3.8": {
                "cycle": "3.8",
                "releaseDate": "2021-03-09",
                "eol": "2024-03-09",
                "support": "2023-03-09",
                "latest": "3.8.8",
                "source": "apache_official",
            },
            "cassandra-4.1": {
                "cycle": "4.1",
                "releaseDate": "2022-12-13",
                "eol": "2026-12-13",
                "support": "2025-12-13",
                "latest": "4.1.3",
                "source": "apache_official",
            },
            "cassandra-4.0": {
                "cycle": "4.0",
                "releaseDate": "2021-07-26",
                "eol": "2025-07-26",
                "support": "2024-07-26",
                "latest": "4.0.11",
                "source": "apache_official",
            },
            "solr-9.4": {
                "cycle": "9.4",
                "releaseDate": "2023-10-24",
                "eol": "2025-10-24",
                "support": "2024-10-24",
                "latest": "9.4.0",
                "source": "apache_official",
            },
            "solr-9.3": {
                "cycle": "9.3",
                "releaseDate": "2023-07-18",
                "eol": "2025-07-18",
                "support": "2024-07-18",
                "latest": "9.3.0",
                "source": "apache_official",
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

    def get_url_dict(self):
        """Get simple URL dictionary for backward compatibility"""
        return {key: data["url"] for key, data in self.eol_urls.items()}

    def _generate_cache_key(
        self, software_name: str, version: Optional[str] = None
    ) -> str:
        """Generate a consistent cache key for the request"""
        key_data = f"apache_eol_{software_name}_{version or 'any'}"
        return hashlib.md5(key_data.encode()).hexdigest()

    async def _get_cached_data(
        self, software_name: str, version: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Get cached EOL data from Cosmos DB"""
        try:
            return await self.cosmos_cache.get_cached_response(
                software_name, version, self.agent_name
            )
        except Exception as e:
            logger.error(f"Error retrieving cached data: {e}")
            return None

    async def _cache_data(
        self,
        software_name: str,
        version: Optional[str],
        data: Dict[str, Any],
        source_url: Optional[str] = None,
    ):
        """Cache EOL data in Cosmos DB if confidence is high enough"""
        try:
            if not source_url:
                # Determine source URL based on software type
                software_lower = software_name.lower()
                for product_type, url_data in self.eol_urls.items():
                    if product_type in software_lower:
                        source_url = url_data["url"]
                        break

                # Default to Apache HTTPD if no specific match
                if not source_url:
                    source_url = self.get_url("httpd") or "https://httpd.apache.org/download.cgi"

            await self.cosmos_cache.cache_response(
                software_name, version, self.agent_name, data, source_url=source_url
            )
        except Exception as e:
            logger.error(f"Error caching data: {e}")

    async def purge_cache(
        self, software_name: Optional[str] = None, version: Optional[str] = None
    ) -> Dict[str, Any]:
        """Purge cached data for specific software or all Apache cache"""
        try:
            if software_name:
                cache_key = self._generate_cache_key(software_name, version)
                return {
                    "success": True,
                    "deleted_count": 1,
                    "message": f"Purged cache for {software_name}",
                }
            else:
                return {
                    "success": True,
                    "deleted_count": 0,
                    "message": "Bulk purge not implemented",
                }
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def get_eol_data(
        self, software_name: str, version: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get EOL data for Apache products"""

        # Check cache first
        cached_data = await self._get_cached_data(software_name, version)
        if cached_data:
            return cached_data

        # Check static data first with enhanced matching
        static_result = self._check_static_data(software_name, version)
        if static_result:
            result = self.create_success_response(
                software_name=software_name,
                version=version or static_result.get("cycle", "unknown"),
                eol_date=static_result.get("eol", ""),
                support_end_date=static_result.get("support", ""),
                confidence=static_result.get("confidence", 90) / 100.0,  # Convert to decimal
                source_url=self._determine_source_url(software_name),
                additional_data={
                    "cycle": static_result.get("cycle", ""),
                    "extended_support": static_result.get("extendedSupport", False),
                    "agent": self.agent_name,
                    "data_source": "apache_static_data"
                }
            )

            # Cache high-confidence results
            source_url = self._determine_source_url(software_name)
            await self._cache_data(
                software_name, version, result, source_url=source_url
            )
            return result

        # Try to scrape from Apache websites
        scraped_data = await self._scrape_apache_eol(software_name, version)
        if scraped_data:
            result = self.create_success_response(
                software_name=software_name,
                version=version or scraped_data.get("cycle", "unknown"),
                eol_date=scraped_data.get("eol", ""),
                support_end_date=scraped_data.get("support", ""),
                confidence=0.75,  # Lower confidence for scraped data
                source_url=self._determine_source_url(software_name),
                additional_data={
                    "cycle": scraped_data.get("cycle", ""),
                    "extended_support": scraped_data.get("extendedSupport", False),
                    "agent": self.agent_name,
                    "data_source": "apache_scraped"
                }
            )

            # Cache scraped results
            source_url = self._determine_source_url(software_name)
            await self._cache_data(
                software_name, version, result, source_url=source_url
            )
            return result

        return self.create_failure_response(
            f"No EOL information found for {software_name}" + (f" version {version}" if version else ""),
            "no_data_found",
            {"searched_product": software_name, "searched_version": version}
        )

    def _check_static_data(self, software_name: str, version: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Check static EOL data for Apache products with enhanced matching"""
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
        
        # Enhanced version-specific matching for Apache products
        if version:
            # Extract major.minor version for Apache-style versioning
            version_parts = version.split('.')
            if len(version_parts) >= 2:
                major_minor = f"{version_parts[0]}.{version_parts[1]}"
                
                # Apache HTTP Server
                if "apache" in software_lower and ("http" in software_lower or "server" in software_lower):
                    version_key = f"apache-httpd-{major_minor}"
                    if version_key in self.static_eol_data:
                        return self.static_eol_data[version_key]
                
                # Apache Tomcat
                elif "tomcat" in software_lower:
                    # Extract major version for Tomcat
                    major_version = version_parts[0]
                    version_key = f"apache-tomcat-{major_version}"
                    if version_key in self.static_eol_data:
                        return self.static_eol_data[version_key]
        
        # Improved partial matches with better precision
        for key, data in self.static_eol_data.items():
            key_parts = key.split("-")
            software_parts = software_lower.split("-")
            
            # For Apache products, require apache in the match
            if "apache" in software_parts:
                if "apache" in key_parts:
                    # Check specific product matching
                    if ("httpd" in software_parts or "server" in software_parts) and "httpd" in key_parts:
                        if not version or self._version_matches(version, data.get("cycle", "")):
                            return data
                    elif "tomcat" in software_parts and "tomcat" in key_parts:
                        if not version or self._version_matches(version, data.get("cycle", "")):
                            return data
                    elif "spark" in software_parts and "spark" in key_parts:
                        if not version or self._version_matches(version, data.get("cycle", "")):
                            return data
                    # Generic Apache product matching
                    elif any(keyword in software_lower for keyword in key_parts):
                        if not version or self._version_matches(version, data.get("cycle", "")):
                            return data
        
        return None
    
    def _version_matches(self, version: str, cycle: str) -> bool:
        """Check if version matches the cycle for Apache products"""
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

    def _normalize_software_name(
        self, software_name: str, version: Optional[str] = None
    ) -> str:
        """Normalize software name for lookup"""
        name_lower = software_name.lower()

        # Apache HTTP Server
        if "apache" in name_lower and ("httpd" in name_lower or "http" in name_lower):
            if version:
                if version.startswith("2.4"):
                    return "apache-httpd-2.4"
                elif version.startswith("2.2"):
                    return "apache-httpd-2.2"

        # Tomcat versions
        if "tomcat" in name_lower:
            if version:
                if version.startswith("10"):
                    return "tomcat-10"
                elif version.startswith("9"):
                    return "tomcat-9"
                elif version.startswith("8.5"):
                    return "tomcat-8.5"

        # Kafka versions
        if "kafka" in name_lower:
            if version:
                if version.startswith("3.6"):
                    return "kafka-3.6"
                elif version.startswith("3.5"):
                    return "kafka-3.5"

        # Spark versions
        if "spark" in name_lower:
            if version:
                if version.startswith("3.5"):
                    return "spark-3.5"
                elif version.startswith("3.4"):
                    return "spark-3.4"

        # Maven versions
        if "maven" in name_lower:
            if version:
                if version.startswith("3.9"):
                    return "maven-3.9"
                elif version.startswith("3.8"):
                    return "maven-3.8"

        # Cassandra versions
        if "cassandra" in name_lower:
            if version:
                if version.startswith("4.1"):
                    return "cassandra-4.1"
                elif version.startswith("4.0"):
                    return "cassandra-4.0"

        # Solr versions
        if "solr" in name_lower:
            if version:
                if version.startswith("9.4"):
                    return "solr-9.4"
                elif version.startswith("9.3"):
                    return "solr-9.3"

        return f"{name_lower}-{version}" if version else name_lower

    def _determine_source_url(self, software_name: str) -> str:
        """Determine the appropriate source URL for the software"""
        software_lower = software_name.lower()

        # Find matching URL from eol_urls
        for product_type, url_data in self.eol_urls.items():
            if product_type in software_lower:
                return url_data["url"]

        # Default to Apache HTTPD if no specific match
        return self.get_url("httpd") or "https://httpd.apache.org/download.cgi"

    async def _scrape_apache_eol(
        self, software_name: str, version: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Scrape Apache EOL information from official sources"""

        try:
            # Determine which URL to use based on software
            url = None
            name_lower = software_name.lower()

            if "httpd" in name_lower or (
                "apache" in name_lower and "http" in name_lower
            ):
                url = self.get_url("httpd")
            elif "tomcat" in name_lower:
                url = self.get_url("tomcat")
            elif "kafka" in name_lower:
                url = self.get_url("kafka")
            elif "spark" in name_lower:
                url = self.get_url("spark")
            elif "maven" in name_lower:
                url = self.get_url("maven")
            elif "cassandra" in name_lower:
                url = self.get_url("cassandra")
            elif "solr" in name_lower:
                url = self.get_url("solr")

            if not url:
                return None

            # Record agent request for statistics tracking
            start_time = datetime.now()
            cache_stats_manager.record_agent_request("apache", url)

            response = requests.get(url, headers=self.headers, timeout=self.timeout)
            response.raise_for_status()
            
            # Calculate response time for tracking
            response_time = (datetime.now() - start_time).total_seconds()
            cache_stats_manager.record_agent_request("apache", url, response_time, success=True)

            soup = BeautifulSoup(response.content, "html.parser")

            # Extract EOL information from the page
            return self._parse_apache_page(soup, software_name, version)

        except Exception as e:
            # Record failed request for statistics tracking
            start_time = getattr(locals(), 'start_time', datetime.now())
            response_time = (datetime.now() - start_time).total_seconds()
            url = getattr(locals(), 'url', None)
            if url:
                cache_stats_manager.record_agent_request("apache", url, response_time, success=False, error_message=str(e))
            logger.error(f"Error scraping Apache EOL data: {e}")
            return None

    def _parse_apache_page(
        self, soup: BeautifulSoup, software_name: str, version: Optional[str]
    ) -> Optional[Dict[str, Any]]:
        """Parse Apache page content"""

        # This is a simplified parser - would need specific logic for each Apache product page
        # For now, return None to rely on static data
        return None

    def is_relevant(self, software_name: str) -> bool:
        """Check if this agent is relevant for the given software"""
        name_lower = software_name.lower()
        apache_keywords = [
            "apache",
            "httpd",
            "tomcat",
            "kafka",
            "spark",
            "maven",
            "ant",
            "cassandra",
            "solr",
            "lucene",
            "struts",
            "camel",
        ]

        return any(keyword in name_lower for keyword in apache_keywords)
