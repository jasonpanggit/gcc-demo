"""
Ubuntu EOL Agent - Queries Ubuntu official sources for EOL information
"""
import requests
from typing import Dict, Any, Optional
from datetime import datetime
import logging
from .base_eol_agent import BaseEOLAgent

logger = logging.getLogger(__name__)

class UbuntuEOLAgent(BaseEOLAgent):
    """Agent for querying Ubuntu EOL information"""

    def __init__(self):
        super().__init__("ubuntu")
import requests
from bs4 import BeautifulSoup
from typing import Dict, Any, Optional, List
import re
from datetime import datetime, timedelta
import os
import hashlib

try:
    # Use the shared EOL cache singleton for agent-level caching
    from utils.eol_cache import eol_cache
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
except ImportError:
    import logging
    logger = logging.getLogger(__name__)
    eol_cache = None


class UbuntuEOLAgent:
    """Agent for scraping Ubuntu official EOL information with Cosmos DB caching"""

    def __init__(self):
        # Agent identification
        self.agent_name = "ubuntu"
        
        self.timeout = 15
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }

        # Cosmos caching enabled
        self.cache_duration_hours = 24 * 30  # 30 days
        # Per-instance reference to shared cache
        self.cosmos_cache = eol_cache

        # Ubuntu EOL URLs with metadata (single source of truth)
        self.eol_urls = {
            "ubuntu": {
                "url": "https://wiki.ubuntu.com/Releases",
                "description": "Ubuntu Releases Wiki",
                "active": True,
                "priority": 1
            },
            "ubuntu-releases": {
                "url": "https://ubuntu.com/about/release-cycle",
                "description": "Ubuntu Release Cycle",
                "active": True,
                "priority": 2
            }
        }

        # Static EOL data for Ubuntu releases (subset)
        self.static_eol_data = {
            "ubuntu-16.04": {
                "cycle": "16.04 LTS",
                "codename": "Xenial Xerus",
                "releaseDate": "2016-04-21",
                "eol": "2024-04-21",
                "support": "2021-04-21",
                "extendedSupport": "2026-04-21",
                "lts": True,
                "latest": "16.04.7",
                "source": "ubuntu_official",
                "confidence": 90.0
            },
            "ubuntu-18.04": {
                "cycle": "18.04 LTS",
                "codename": "Bionic Beaver",
                "releaseDate": "2018-04-26",
                "eol": "2028-04-26",
                "support": "2023-04-26",
                "extendedSupport": "2030-04-26",
                "lts": True,
                "latest": "18.04.6",
                "source": "ubuntu_official",
                "confidence": 90.0
            },
            "ubuntu-20.04": {
                "cycle": "20.04 LTS",
                "codename": "Focal Fossa",
                "releaseDate": "2020-04-23",
                "eol": "2030-04-23",
                "support": "2025-04-23",
                "extendedSupport": "2032-04-23",
                "lts": True,
                "latest": "20.04.6",
                "source": "ubuntu_official",
                "confidence": 90.0
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
        key_data = f"ubuntu_eol_{software_name}_{version or 'any'}"
        return hashlib.md5(key_data.encode()).hexdigest()

    async def _get_cached_data(self, software_name: str, version: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Get cached data from Cosmos DB if available"""
        if self.cosmos_cache:
            return await self.cosmos_cache.get_cached_response(software_name, version, self.agent_name)
        return None

    async def _cache_data(self, software_name: str, version: Optional[str], data: Dict[str, Any], source_url: Optional[str] = None):
        """Cache data to Cosmos DB if confidence is high enough"""
        if self.cosmos_cache and data:
            if not source_url:
                # Default to Ubuntu releases URL
                source_url = self.eol_urls.get("ubuntu", "https://wiki.ubuntu.com/Releases")
            
            await self.cosmos_cache.cache_response(software_name, version, self.agent_name, data, source_url=source_url)

    async def purge_cache(self, software_name: Optional[str] = None, version: Optional[str] = None) -> Dict[str, Any]:
        """Purge cached data for specific software or all Ubuntu cache"""
        if self.cosmos_cache:
            return await self.cosmos_cache.clear_cache(software_name=software_name, agent_name=self.agent_name)
        return {"success": True, "deleted_count": 0, "message": "Caching not available"}

    async def get_eol_data(self, software_name: str, version: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Get Ubuntu EOL data through web scraping and static data with caching"""

        # Check if this is an Ubuntu product
        if not self._is_ubuntu_product(software_name):
            return None

        # Check cache first
        cached_data = await self._get_cached_data(software_name, version)
        if cached_data:
            return cached_data

        # Check static data first for accuracy and speed
        static_result = self._check_static_data(software_name, version)
        if static_result:
            result = self.create_success_response(
                software_name=software_name,
                version=version or static_result.get("cycle", "unknown"),
                eol_date=static_result.get("eol", ""),
                support_end_date=static_result.get("support", ""),
                confidence=static_result.get("confidence", 90) / 100.0,  # Convert to decimal
                source_url=self.eol_urls["ubuntu"],
                additional_data={
                    "cycle": static_result.get("cycle", ""),
                    "extended_support": static_result.get("extendedSupport", False),
                    "agent": "ubuntu",
                    "data_source": "ubuntu_static_data"
                }
            )
            await self._cache_data(software_name, version, result, source_url=self.eol_urls["ubuntu"])
            return result

        # Try web scraping for latest information
        scraped_result = await self._scrape_eol_data(software_name, version)
        if scraped_result:
            result = self.create_success_response(
                software_name=software_name,
                version=version or scraped_result.get("cycle", "unknown"),
                eol_date=scraped_result.get("eol", ""),
                support_end_date=scraped_result.get("support", ""),
                confidence=0.75,  # Lower confidence for scraped data
                source_url=self.eol_urls["ubuntu"],
                additional_data={
                    "cycle": scraped_result.get("cycle", ""),
                    "extended_support": scraped_result.get("extendedSupport", False),
                    "agent": "ubuntu",
                    "data_source": "ubuntu_scraped"
                }
            )
            # Cache the web scraping result
            await self._cache_data(software_name, version, result, source_url=self.eol_urls["ubuntu"])
            return result

        return self.create_failure_response(
            f"No EOL information found for {software_name}" + (f" version {version}" if version else ""),
            "no_data_found",
            {"searched_product": software_name, "searched_version": version}
        )

    def _is_ubuntu_product(self, software_name: str) -> bool:
        """Check if software is an Ubuntu product"""
        software_lower = software_name.lower()
        ubuntu_keywords = ["ubuntu", "canonical"]
        return any(keyword in software_lower for keyword in ubuntu_keywords)

    def _check_static_data(self, software_name: str, version: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Check static EOL data for Ubuntu releases with enhanced matching"""
        software_lower = software_name.lower().replace(" ", "-")

        # Must contain "ubuntu" to be relevant
        if "ubuntu" not in software_lower:
            return None

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

        # Enhanced version-specific matching for Ubuntu
        if version:
            # Handle various version formats (22.04, 2022.04, etc.)
            version_normalized = self._normalize_version(version)
            version_key = f"ubuntu-{version_normalized}"

            if version_key in self.static_eol_data:
                return self.static_eol_data[version_key]

            # Try with just the version number
            if version_normalized in self.static_eol_data:
                return self.static_eol_data[version_normalized]

        # Improved partial matches with better precision for Ubuntu releases
        for key, data in self.static_eol_data.items():
            key_parts = key.split("-")
            software_parts = software_lower.split("-")
            
            # For Ubuntu, require "ubuntu" to be present
            if "ubuntu" in software_parts and "ubuntu" in key_parts:
                # If version is specified, check version compatibility
                if version:
                    version_normalized = self._normalize_version(version)
                    # Check if the key contains the version or cycle matches
                    if (version_normalized in key or 
                        version_normalized in data.get("cycle", "") or
                        self._version_matches(version, data.get("cycle", ""))):
                        return data
                else:
                    # No version specified, return latest LTS
                    if data.get("lts", False):
                        return data

        # Return latest LTS if no version specified and no matches found
        if not version:
            for key, data in self.static_eol_data.items():
                if data.get("lts", False):
                    return data

        return None

    def _normalize_version(self, version: str) -> str:
        """Normalize version string for Ubuntu"""
        # Extract version number from various formats
        version_match = re.search(r'(\d{2}\.\d{2})', version)
        if version_match:
            return version_match.group(1)

        # Handle year.month format
        version_match = re.search(r'(\d{4})\.(\d{1,2})', version)
        if version_match:
            year = version_match.group(1)
            month = version_match.group(2).zfill(2)
            return f"{year[-2:]}.{month}"

        return version
    
    def _version_matches(self, version: str, cycle: str) -> bool:
        """Check if version matches the cycle for Ubuntu releases"""
        try:
            if not version or not cycle:
                return False
            
            # Normalize both version and cycle
            version_normalized = self._normalize_version(version)
            cycle_normalized = cycle.replace(" LTS", "").strip()
            
            # Check direct match
            if version_normalized == cycle_normalized:
                return True
            
            # Check if normalized version is contained in cycle
            return version_normalized in cycle_normalized or cycle_normalized in version_normalized
            
        except Exception:
            return False

    async def _scrape_eol_data(self, software_name: str, version: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Scrape Ubuntu EOL data from official websites"""
        try:
            # Record agent request for statistics tracking
            start_time = datetime.now()
            url_data = self.eol_urls["ubuntu"]
            url = url_data.get("url") if isinstance(url_data, dict) else url_data
            cache_stats_manager.record_agent_request("ubuntu", url)
            
            # Try the main releases page
            response = requests.get(url, headers=self.headers, timeout=self.timeout)
            response.raise_for_status()
            
            # Calculate response time for tracking
            response_time = (datetime.now() - start_time).total_seconds()
            cache_stats_manager.record_agent_request("ubuntu", url, response_time, success=True)

            soup = BeautifulSoup(response.content, 'html.parser')
            return self._parse_ubuntu_releases(soup, version)

        except Exception as e:
            # Record failed request for statistics tracking
            start_time = getattr(locals(), 'start_time', datetime.now())
            response_time = (datetime.now() - start_time).total_seconds()
            url_data = getattr(locals(), 'url_data', self.eol_urls["ubuntu"])
            url = url_data.get("url") if isinstance(url_data, dict) else url_data
            cache_stats_manager.record_agent_request("ubuntu", url, response_time, success=False, error_message=str(e))
            logger.debug(f"Error scraping Ubuntu EOL data: {e}")
            return None

    def _parse_ubuntu_releases(self, soup: BeautifulSoup, version: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Parse Ubuntu releases information from wiki"""
        try:
            # Look for tables containing release information
            tables = soup.find_all('table')

            for table in tables:
                # Check if this table contains release information
                headers = table.find_all('th')
                if not any('version' in th.get_text().lower() or 'release' in th.get_text().lower() for th in headers):
                    continue

                rows = table.find_all('tr')

                for row in rows:
                    cells = row.find_all(['td', 'th'])
                    if len(cells) >= 4:
                        # Look for version information
                        version_cell = cells[0].get_text().strip()

                        if version:
                            version_normalized = self._normalize_version(version)
                            if version_normalized not in version_cell:
                                continue

                        # Extract information from cells
                        codename = cells[1].get_text().strip() if len(cells) > 1 else ""
                        release_date = cells[2].get_text().strip() if len(cells) > 2 else ""
                        eol_date = cells[3].get_text().strip() if len(cells) > 3 else ""

                        # Parse dates
                        release_date_iso = self._parse_date(release_date)
                        eol_date_iso = self._parse_date(eol_date)

                        if eol_date_iso:
                            is_lts = "LTS" in version_cell

                            return {
                                "cycle": version_cell,
                                "codename": codename,
                                "releaseDate": release_date_iso,
                                "eol": eol_date_iso,
                                "lts": is_lts,
                                "source": "ubuntu_official_scraped"
                            }

            return None

        except Exception as e:
            logger.debug(f"Error parsing Ubuntu releases: {e}")
            return None

    def _parse_date(self, date_str: str) -> Optional[str]:
        """Parse various date formats to ISO format"""
        if not date_str or date_str.lower() in ['tbd', 'unknown', '-', '']:
            return None

        try:
            # Handle different date formats
            date_patterns = [
                '%Y-%m-%d',      # 2024-04-25
                '%d %B %Y',      # 25 April 2024
                '%B %d, %Y',     # April 25, 2024
                '%Y/%m/%d',      # 2024/04/25
                '%d/%m/%Y'       # 25/04/2024
            ]

            for pattern in date_patterns:
                try:
                    date_obj = datetime.strptime(date_str.strip(), pattern)
                    return date_obj.strftime('%Y-%m-%d')
                except ValueError:
                    continue

            # Handle month year format (assume end of month)
            month_year_match = re.search(r'(\w+)\s+(\d{4})', date_str)
            if month_year_match:
                month_name = month_year_match.group(1)
                year = month_year_match.group(2)

                # Convert month name to number
                month_names = {
                    'january': '01', 'february': '02', 'march': '03', 'april': '04',
                    'may': '05', 'june': '06', 'july': '07', 'august': '08',
                    'september': '09', 'october': '10', 'november': '11', 'december': '12'
                }

                month_num = month_names.get(month_name.lower())
                if month_num:
                    # Use last day of month
                    last_days = {'01': '31', '02': '28', '03': '31', '04': '30',
                               '05': '31', '06': '30', '07': '31', '08': '31',
                               '09': '30', '10': '31', '11': '30', '12': '31'}
                    day = last_days[month_num]
                    return f"{year}-{month_num}-{day}"

            return None

        except Exception:
            return None

    def get_supported_versions(self) -> List[Dict[str, Any]]:
        """Get list of supported Ubuntu versions"""
        supported_versions = []

        for key, data in self.static_eol_data.items():
            eol_date_str = data.get("eol")
            if eol_date_str:
                try:
                    eol_date = datetime.strptime(eol_date_str, '%Y-%m-%d')
                    if eol_date > datetime.now():
                        supported_versions.append({
                            "version": data["cycle"],
                            "codename": data.get("codename", ""),
                            "eol_date": eol_date_str,
                            "lts": data.get("lts", False)
                        })
                except ValueError:
                    continue

        return sorted(supported_versions, key=lambda x: x["eol_date"], reverse=True)

    def get_lts_versions(self) -> List[Dict[str, Any]]:
        """Get list of LTS Ubuntu versions"""
        lts_versions = []

        for key, data in self.static_eol_data.items():
            if data.get("lts", False):
                lts_versions.append({
                    "version": data["cycle"],
                    "codename": data.get("codename", ""),
                    "release_date": data.get("releaseDate", ""),
                    "eol_date": data.get("eol", ""),
                    "support_date": data.get("support", ""),
                    "extended_support": data.get("extendedSupport", "")
                })

        return sorted(lts_versions, key=lambda x: x["release_date"], reverse=True)
