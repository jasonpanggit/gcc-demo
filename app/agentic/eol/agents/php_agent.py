"""
PHP EOL Agent - Scrapes PHP official sources for EOL information
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

class PHPEOLAgent(BaseEOLAgent):
    """Agent for scraping PHP official EOL information"""

    def __init__(self):
        # Agent identification
        self.agent_name = "php"
        
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

        # PHP EOL URLs with metadata (single source of truth)
        self.eol_urls = {
            "php": {
                "url": "https://www.php.net/supported-versions.php",
                "description": "PHP Supported Versions",
                "active": True,
                "priority": 1
            },
            "symfony": {
                "url": "https://symfony.com/releases",
                "description": "Symfony Release Process",
                "active": True,
                "priority": 2
            },
            "laravel": {
                "url": "https://laravel.com/docs/releases",
                "description": "Laravel Release Notes",
                "active": True,
                "priority": 3
            },
            "wordpress": {
                "url": "https://wordpress.org/download/releases/",
                "description": "WordPress Release Archive",
                "active": True,
                "priority": 4
            },
            "drupal": {
                "url": "https://www.drupal.org/project/drupal/releases",
                "description": "Drupal Core Releases",
                "active": True,
                "priority": 5
            }
        }

        # Static data for PHP ecosystem
        self.static_eol_data = {
            "php-8.3": {
                "cycle": "8.3",
                "releaseDate": "2023-11-23",
                "eol": "2026-11-23",
                "support": "2025-11-23",
                "latest": "8.3.0",
                "source": "php_official",
                "confidence": 95,
            },
            "php-8.2": {
                "cycle": "8.2",
                "releaseDate": "2022-12-08",
                "eol": "2025-12-08",
                "support": "2024-12-08",
                "latest": "8.2.13",
                "source": "php_official",
                "confidence": 95,
            },
            "php-8.1": {
                "cycle": "8.1",
                "releaseDate": "2021-11-25",
                "eol": "2024-11-25",
                "support": "2023-11-25",
                "latest": "8.1.26",
                "source": "php_official",
            },
            "php-8.0": {
                "cycle": "8.0",
                "releaseDate": "2020-11-26",
                "eol": "2023-11-26",
                "support": "2022-11-26",
                "latest": "8.0.30",
                "source": "php_official",
            },
            "php-7.4": {
                "cycle": "7.4",
                "releaseDate": "2019-11-28",
                "eol": "2022-11-28",
                "support": "2021-11-28",
                "latest": "7.4.33",
                "source": "php_official",
            },
            "php-7.3": {
                "cycle": "7.3",
                "releaseDate": "2018-12-06",
                "eol": "2021-12-06",
                "support": "2020-12-06",
                "latest": "7.3.33",
                "source": "php_official",
            },
            "symfony-6.4": {
                "cycle": "6.4 LTS",
                "releaseDate": "2023-11-30",
                "eol": "2029-11-30",
                "support": "2027-11-30",
                "latest": "6.4.0",
                "lts": True,
                "source": "symfony_official",
            },
            "symfony-6.3": {
                "cycle": "6.3",
                "releaseDate": "2023-05-31",
                "eol": "2024-01-31",
                "support": "2024-01-31",
                "latest": "6.3.8",
                "source": "symfony_official",
            },
            "symfony-5.4": {
                "cycle": "5.4 LTS",
                "releaseDate": "2021-11-30",
                "eol": "2026-11-30",
                "support": "2024-11-30",
                "latest": "5.4.31",
                "lts": True,
                "source": "symfony_official",
            },
            "laravel-10": {
                "cycle": "10",
                "releaseDate": "2023-02-14",
                "eol": "2025-08-14",
                "support": "2024-08-14",
                "latest": "10.33.0",
                "source": "laravel_official",
            },
            "laravel-9": {
                "cycle": "9 LTS",
                "releaseDate": "2022-02-08",
                "eol": "2025-02-08",
                "support": "2024-02-08",
                "latest": "9.52.16",
                "lts": True,
                "source": "laravel_official",
            },
            "laravel-8": {
                "cycle": "8",
                "releaseDate": "2020-09-08",
                "eol": "2023-01-24",
                "support": "2022-07-26",
                "latest": "8.83.27",
                "source": "laravel_official",
            },
            "wordpress-6.4": {
                "cycle": "6.4",
                "releaseDate": "2023-11-07",
                "eol": "2025-11-07",
                "support": "2024-11-07",
                "latest": "6.4.1",
                "source": "wordpress_official",
            },
            "wordpress-6.3": {
                "cycle": "6.3",
                "releaseDate": "2023-08-08",
                "eol": "2025-08-08",
                "support": "2024-08-08",
                "latest": "6.3.2",
                "source": "wordpress_official",
            },
            "drupal-10": {
                "cycle": "10",
                "releaseDate": "2022-12-15",
                "eol": "2026-12-15",
                "support": "2025-12-15",
                "latest": "10.1.6",
                "source": "drupal_official",
            },
            "drupal-9": {
                "cycle": "9",
                "releaseDate": "2020-06-03",
                "eol": "2023-11-01",
                "support": "2023-11-01",
                "latest": "9.5.11",
                "source": "drupal_official",
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
        """Generate a unique cache key for PHP EOL data"""
        cache_input = f"php:{software_name.lower()}:{version or 'latest'}"
        return hashlib.md5(cache_input.encode()).hexdigest()

    async def _get_cached_data(self, software_name: str, version: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Retrieve cached EOL data if available"""
        try:
            cached_result = await self.cosmos_cache.get_cached_response(software_name, version, self.agent_name)
            
            if cached_result:
                logger.info(f"✅ Cache hit for PHP {software_name} {version or 'latest'}")
                return cached_result
                
            return None
        except Exception as e:
            logger.error(f"Cache retrieval error for PHP {software_name}: {e}")
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
            logger.info(f"✅ Cached PHP {software_name} {version or 'latest'} (confidence: {confidence_level}%) from {source_url or 'static data'}")
        except Exception as e:
            logger.error(f"Cache storage error for PHP {software_name}: {e}")

    async def purge_cache(self, software_name: Optional[str] = None, version: Optional[str] = None) -> Dict[str, Any]:
        """Purge cached PHP EOL data"""
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
                # Purge all PHP cache entries
                result = await self.cosmos_cache.purge_agent_cache("php")
                return {
                    "status": "success", 
                    "action": "purged_all",
                    "agent": "php",
                    "result": result
                }
        except Exception as e:
            return {
                "status": "error",
                "action": "purge_failed",
                "error": str(e)
            }

    async def get_eol_data(self, software_name: str, version: Optional[str] = None) -> Dict[str, Any]:
        """Get EOL data for PHP ecosystem products with Cosmos DB caching"""
        
        # Try cache first
        cached_data = await self._get_cached_data(software_name, version)
        if cached_data:
            return cached_data
        
        # Get fresh data using enhanced fetch method
        result_data = await self._fetch_eol_data(software_name, version)
        
        if result_data:
            # Add PHP-specific metadata
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
                    "agent": "php",
                    "data_source": "php_agent"
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
        Fetch EOL data from PHP ecosystem sources
        """
        # Check static data first for reliability
        static_result = self._check_static_data(software_name, version)
        if static_result:
            return static_result

        # Try web scraping for latest information
        scraped_result = await self._scrape_php_eol(software_name, version)
        if scraped_result:
            return scraped_result

        return None

    def _check_static_data(self, software_name: str, version: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Check static EOL data for PHP ecosystem products with enhanced matching"""
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
        
        # Enhanced version-specific matching for PHP ecosystem
        if version:
            # Extract major.minor version for PHP-style versioning
            version_parts = version.split('.')
            if len(version_parts) >= 2:
                major_minor = f"{version_parts[0]}.{version_parts[1]}"
                
                # PHP versions
                if "php" in software_lower:
                    version_key = f"php-{major_minor}"
                    if version_key in self.static_eol_data:
                        return self.static_eol_data[version_key]
                
                # Laravel versions
                elif "laravel" in software_lower:
                    version_key = f"laravel-{major_minor}"
                    if version_key in self.static_eol_data:
                        return self.static_eol_data[version_key]
                
                # Symfony versions
                elif "symfony" in software_lower:
                    version_key = f"symfony-{major_minor}"
                    if version_key in self.static_eol_data:
                        return self.static_eol_data[version_key]
                
                # Composer versions
                elif "composer" in software_lower:
                    version_key = f"composer-{major_minor}"
                    if version_key in self.static_eol_data:
                        return self.static_eol_data[version_key]
        
        # Improved partial matches with better precision
        for key, data in self.static_eol_data.items():
            key_parts = key.split("-")
            software_parts = software_lower.split("-")
            
            # For PHP ecosystem, require exact framework match
            if "php" in software_parts:
                if "php" in key_parts:
                    # Ensure version compatibility
                    if not version or self._version_matches(version, data.get("cycle", "")):
                        return data
            
            elif "laravel" in software_parts:
                if "laravel" in key_parts:
                    if not version or self._version_matches(version, data.get("cycle", "")):
                        return data
            
            elif "symfony" in software_parts:
                if "symfony" in key_parts:
                    if not version or self._version_matches(version, data.get("cycle", "")):
                        return data
            
            elif "composer" in software_parts:
                if "composer" in key_parts:
                    if not version or self._version_matches(version, data.get("cycle", "")):
                        return data
            
            # Generic partial matching for other PHP packages
            else:
                if any(keyword in software_lower for keyword in key_parts):
                    if not version or self._version_matches(version, data.get("cycle", "")):
                        return data
        
        return None
    
    def _version_matches(self, version: str, cycle: str) -> bool:
        """Check if version matches the cycle for PHP ecosystem"""
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
        software_lower = software_name.lower()
        
        # Find matching URL from eol_urls
        for product_type, url_data in self.eol_urls.items():
            if product_type in software_lower:
                return url_data.get("url") if isinstance(url_data, dict) else url_data
        
        # Default to PHP official URL if no specific match
        return "https://www.php.net/"

    def _normalize_software_name(self, software_name: str, version: Optional[str] = None) -> str:
        """Normalize software name for lookup"""
        name_lower = software_name.lower()
        
        # PHP versions
        if "php" in name_lower and "symfony" not in name_lower and "laravel" not in name_lower:
            if version:
                # Extract major.minor version
                version_parts = version.split('.')
                if len(version_parts) >= 2:
                    major_minor = f"{version_parts[0]}.{version_parts[1]}"
                    if major_minor == "8.3":
                        return "php-8.3"
                    elif major_minor == "8.2":
                        return "php-8.2"
                    elif major_minor == "8.1":
                        return "php-8.1"
                    elif major_minor == "8.0":
                        return "php-8.0"
                    elif major_minor == "7.4":
                        return "php-7.4"
                    elif major_minor == "7.3":
                        return "php-7.3"
        
        # Symfony versions
        if "symfony" in name_lower:
            if version:
                # Extract major.minor version
                version_parts = version.split('.')
                if len(version_parts) >= 2:
                    major_minor = f"{version_parts[0]}.{version_parts[1]}"
                    if major_minor == "6.4":
                        return "symfony-6.4"
                    elif major_minor == "6.3":
                        return "symfony-6.3"
                    elif major_minor == "5.4":
                        return "symfony-5.4"
        
        # Laravel versions
        if "laravel" in name_lower:
            if version:
                major_version = version.split('.')[0]
                if major_version == "10":
                    return "laravel-10"
                elif major_version == "9":
                    return "laravel-9"
                elif major_version == "8":
                    return "laravel-8"
        
        # WordPress versions
        if "wordpress" in name_lower:
            if version:
                # Extract major.minor version
                version_parts = version.split('.')
                if len(version_parts) >= 2:
                    major_minor = f"{version_parts[0]}.{version_parts[1]}"
                    if major_minor == "6.4":
                        return "wordpress-6.4"
                    elif major_minor == "6.3":
                        return "wordpress-6.3"
        
        # Drupal versions
        if "drupal" in name_lower:
            if version:
                major_version = version.split('.')[0]
                if major_version == "10":
                    return "drupal-10"
                elif major_version == "9":
                    return "drupal-9"
        
        return f"{name_lower}-{version}" if version else name_lower

    async def _scrape_php_eol(self, software_name: str, version: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Scrape PHP ecosystem EOL information from official sources"""
        start_time = time.time()
        url = None
        
        try:
            # Determine which URL to use based on software
            name_lower = software_name.lower()
            
            if "php" in name_lower and "symfony" not in name_lower and "laravel" not in name_lower:
                url = self.eol_urls["php"]["url"]
            elif "symfony" in name_lower:
                url = self.eol_urls["symfony"]["url"]
            elif "laravel" in name_lower:
                url = self.eol_urls["laravel"]["url"]
            elif "wordpress" in name_lower:
                url = self.eol_urls["wordpress"]["url"]
            elif "drupal" in name_lower:
                url = self.eol_urls["drupal"]["url"]
            
            if not url:
                return None
            
            # Record the agent request before making the HTTP call
            cache_stats_manager.record_agent_request(
                agent_name="php", 
                url=url, 
                start_time=start_time
            )
            
            response = requests.get(url, headers=self.headers, timeout=self.timeout)
            response.raise_for_status()
            
            # Calculate response time
            response_time_ms = (time.time() - start_time) * 1000
            
            # Record successful request
            cache_stats_manager.record_agent_request(
                agent_name="php",
                url=url,
                response_time_ms=response_time_ms,
                success=True,
                status_code=response.status_code
            )
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Extract EOL information from the page
            return self._parse_php_page(soup, software_name, version)
            
        except Exception as e:
            # Calculate response time for failed request
            response_time_ms = (time.time() - start_time) * 1000
            
            # Record failed request
            cache_stats_manager.record_agent_request(
                agent_name="php",
                url=url or "unknown",
                response_time_ms=response_time_ms,
                success=False,
                error_message=str(e)
            )
            
            logger.error(f"Error scraping PHP EOL data from {url}: {e}")
            return None

    def _parse_php_page(self, soup: BeautifulSoup, software_name: str, version: Optional[str]) -> Optional[Dict[str, Any]]:
        """Parse PHP ecosystem page content"""
        
        # This is a simplified parser - would need specific logic for each framework's page
        # For now, return None to rely on static data
        return None

    def is_relevant(self, software_name: str) -> bool:
        """Check if this agent is relevant for the given software"""
        name_lower = software_name.lower()
        php_keywords = [
            'php', 'symfony', 'laravel', 'wordpress', 'drupal',
            'codeigniter', 'cakephp', 'zend', 'composer'
        ]
        
        return any(keyword in name_lower for keyword in php_keywords)
