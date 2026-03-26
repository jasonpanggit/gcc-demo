"""
Red Hat EOL Agent - Web scrapes Red Hat official EOL information
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
    from app.agentic.eol.utils.logger import get_logger
except ModuleNotFoundError:
    try:
        from utils.logger import get_logger
    except ModuleNotFoundError:
        import logging

        def get_logger(name: str):
            return logging.getLogger(name)

logger = get_logger(__name__)

try:
    from app.agentic.eol.utils.cache_stats_manager import CacheStatsManager
    cache_stats_manager = CacheStatsManager()
except ModuleNotFoundError:
    try:
        from utils.cache_stats_manager import CacheStatsManager
        cache_stats_manager = CacheStatsManager()
    except ModuleNotFoundError:
        class DummyCacheStatsManager:
            def record_agent_request(self, agent_name, url, response_time=None, success=True, error_message=None):
                pass
        cache_stats_manager = DummyCacheStatsManager()
except Exception:
    # Dummy implementation for environments without cache_stats_manager
    class DummyCacheStatsManager:
        def record_agent_request(self, agent_name, url, response_time=None, success=True, error_message=None):
            pass
    cache_stats_manager = DummyCacheStatsManager()

class RedHatEOLAgent(BaseEOLAgent):
    """Agent for scraping Red Hat official EOL information"""
    
    def __init__(self):
        super().__init__("redhat")
        
        self.timeout = 15
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }

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
                "url": "https://docs.fedoraproject.org/en-US/releases/eol/",
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
        # Caching consolidated to orchestrator via eol_inventory
        return None

    async def _cache_data(self, software_name: str, version: Optional[str], data: Dict[str, Any], source_url: Optional[str] = None):
        """Agent-level caching disabled - eol_inventory is the single source of truth"""
        # Caching consolidated to orchestrator via eol_inventory
        pass

    async def purge_cache(self, software_name: Optional[str] = None, version: Optional[str] = None) -> Dict[str, Any]:
        """Agent-level caching disabled - use eol_inventory for cache management"""
        # Caching consolidated to orchestrator via eol_inventory
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
        scraped_result = await self._scrape_eol_data(software_name, version)
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

    async def fetch_from_url(self, url: str, software_hint: str) -> Dict[str, Any]:
        """Fetch EOL data from a specific URL for vendor parsing.

        This method is called by the vendor parsing endpoint to scrape
        EOL data from the configured Red Hat URLs.

        Args:
            url: The URL to scrape (must be one of the configured eol_urls)
            software_hint: Software name hint (rhel, centos, or fedora)

        Returns:
            Dict with success, data, confidence, agent_used, source_url
        """
        try:
            # Map URL to product type
            product_type = None
            for key, url_data in self.eol_urls.items():
                if url_data["url"] == url:
                    product_type = key
                    break

            if not product_type:
                return {
                    "success": False,
                    "error": f"URL not in configured Red Hat URLs: {url}",
                    "data": {},
                }

            # Use software_hint to determine what to scrape
            software_name = software_hint or product_type

            # Call existing scraping logic
            result = await self._scrape_eol_data(software_name, version=None)

            if result:
                return {
                    "success": True,
                    "data": {
                        "software_name": software_name,
                        "version": result.get("cycle"),
                        "eol_date": result.get("eol"),
                        "support_end_date": result.get("support"),
                        "confidence": 0.85,  # Scraped data confidence
                        "source": "redhat_agent",
                        "agent_used": "redhat",
                    },
                    "confidence": 0.85,
                    "agent_used": "redhat",
                    "source_url": url,
                }
            else:
                return {
                    "success": False,
                    "error": f"No EOL data found for {software_name}",
                    "data": {},
                }

        except Exception as exc:
            logger.error(f"fetch_from_url failed for {url}: {exc}")
            return {
                "success": False,
                "error": str(exc),
                "data": {},
            }

    async def fetch_all_from_url(self, url: str, software_hint: str) -> List[Dict[str, Any]]:
        """Fetch all available EOL records from a specific URL.

        This is the preferred method for vendor parsing as it can return
        multiple versions/cycles from a single URL scrape.

        Args:
            url: The URL to scrape
            software_hint: Software name hint (rhel, centos, or fedora)

        Returns:
            List of EOL records, each with software_name, version, eol_date, etc.
        """
        try:
            # Map URL to product type
            product_type = None
            for key, url_data in self.eol_urls.items():
                if url_data["url"] == url:
                    product_type = key
                    break

            if not product_type:
                logger.warning(f"URL not in configured Red Hat URLs: {url}")
                return []

            software_name = software_hint or product_type

            # Scrape the page
            start_time = datetime.now()
            cache_stats_manager.record_agent_request("redhat", url)

            response = requests.get(url, headers=self.headers, timeout=self.timeout)
            response.raise_for_status()

            response_time = (datetime.now() - start_time).total_seconds()
            cache_stats_manager.record_agent_request("redhat", url, response_time, success=True)

            soup = BeautifulSoup(response.content, 'html.parser')

            # Parse all versions from the page based on product type
            records = []

            if product_type == "rhel":
                records = self._parse_all_rhel_versions(soup)
            elif product_type == "centos":
                records = self._parse_all_centos_versions(soup)
            elif product_type == "fedora":
                records = self._parse_all_fedora_versions(soup)

            # Convert to vendor parsing format
            formatted_records = []
            for record in records:
                formatted_records.append({
                    "software_name": software_name,
                    "version": record.get("cycle"),
                    "eol": record.get("eol"),
                    "support": record.get("support"),
                    "confidence": 0.85,
                    "source": "redhat_agent",
                })

            return formatted_records

        except Exception as exc:
            logger.error(f"fetch_all_from_url failed for {url}: {exc}")
            # Record failed request
            if 'start_time' in locals():
                response_time = (datetime.now() - start_time).total_seconds()
                cache_stats_manager.record_agent_request("redhat", url, response_time, success=False, error_message=str(exc))
            return []

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
            # Try to parse all versions and find the requested one
            all_versions = self._parse_all_fedora_versions(soup)

            if version and all_versions:
                version_num = version.split('.')[0]
                for record in all_versions:
                    if record.get("cycle") == version_num:
                        return record

            # Fallback: use first available version if no specific version requested
            if all_versions and not version:
                return all_versions[0]

            # Last resort: approximate calculation for version >= 35
            if version:
                version_num = int(version.split('.')[0])
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

    def _parse_all_rhel_versions(self, soup: BeautifulSoup) -> List[Dict[str, Any]]:
        """Parse ALL RHEL versions from the page for bulk vendor parsing.

        Returns:
            List of dicts with cycle, eol, support, source fields
        """
        records = []
        try:
            tables = soup.find_all('table')

            for table in tables:
                rows = table.find_all('tr')

                for row in rows:
                    cells = row.find_all(['td', 'th'])
                    if len(cells) >= 3:
                        version_text = cells[0].get_text().strip()

                        # Skip header rows
                        if 'version' in version_text.lower() or 'release' in version_text.lower():
                            continue

                        eol_date = None
                        support_date = None

                        for cell in cells[1:]:
                            cell_text = cell.get_text().strip()
                            date_match = re.search(r'(\d{4}-\d{2}-\d{2})', cell_text)
                            if date_match:
                                if "end of life" in cell_text.lower() or "eol" in cell_text.lower():
                                    eol_date = date_match.group(1)
                                elif "end of support" in cell_text.lower():
                                    support_date = date_match.group(1)

                        if eol_date or support_date:
                            records.append({
                                "cycle": version_text,
                                "eol": eol_date,
                                "support": support_date,
                                "source": "redhat_official_scraped",
                            })

        except Exception as exc:
            logger.error(f"Error parsing all RHEL versions: {exc}")

        return records

    def _parse_all_centos_versions(self, soup: BeautifulSoup) -> List[Dict[str, Any]]:
        """Parse ALL CentOS versions from the announcement page.

        Returns:
            List of dicts with cycle, eol, support, source fields
        """
        records = []
        try:
            # CentOS announcement page - extract text-based dates
            text_content = soup.get_text()

            # Look for CentOS version mentions and dates
            lines = text_content.split('\n')
            for line in lines:
                # Match patterns like "CentOS 7" or "CentOS Linux 8"
                version_match = re.search(r'CentOS\s+(?:Linux\s+)?(\d+)', line, re.IGNORECASE)
                date_match = re.search(r'(\d{4}-\d{2}-\d{2})', line)

                if version_match and date_match:
                    records.append({
                        "cycle": version_match.group(1),
                        "eol": date_match.group(1),
                        "support": None,
                        "source": "redhat_official_scraped",
                    })

            # Fallback to static data if scraping fails
            if not records:
                for key, value in self.static_eol_data.items():
                    if 'centos' in key:
                        records.append({
                            "cycle": value.get("cycle"),
                            "eol": value.get("eol"),
                            "support": value.get("support"),
                            "source": "redhat_static_data",
                        })

        except Exception as exc:
            logger.error(f"Error parsing all CentOS versions: {exc}")

        return records

    def _parse_all_fedora_versions(self, soup: BeautifulSoup) -> List[Dict[str, Any]]:
        """Parse ALL Fedora versions from the EOL docs page.

        The page structure (as of 2024):
        - URL: https://docs.fedoraproject.org/en-US/releases/eol/
        - Table with columns: Release | EOL since | Maintained for
        - Version format: "F41", "F40", "FC6" (older), "FC1" (oldest)
        - Date format: YYYY-MM-DD (ISO 8601)

        Returns:
            List of dicts with cycle, eol, support, source fields
        """
        records = []
        try:
            # Find the EOL releases table
            tables = soup.find_all('table')

            for table in tables:
                rows = table.find_all('tr')

                for row in rows:
                    cells = row.find_all(['td', 'th'])
                    if len(cells) >= 2:
                        release_text = cells[0].get_text().strip()

                        # Match Fedora version: F41, F40, FC6, FC1
                        # Extract just the number for consistency
                        version_match = re.search(r'F(?:C)?(\d+)', release_text, re.IGNORECASE)
                        if not version_match:
                            continue

                        version_num = version_match.group(1)

                        # The second column contains the EOL date
                        eol_date = None
                        if len(cells) >= 2:
                            eol_text = cells[1].get_text().strip()

                            # Try ISO format: YYYY-MM-DD
                            date_match = re.search(r'(\d{4}-\d{2}-\d{2})', eol_text)
                            if date_match:
                                eol_date = date_match.group(1)
                            else:
                                # Try Month DD, YYYY format
                                date_match = re.search(r'([A-Za-z]+)\s+(\d{1,2}),?\s+(\d{4})', eol_text)
                                if date_match:
                                    try:
                                        month_str, day_str, year_str = date_match.groups()
                                        parsed_date = datetime.strptime(f"{month_str} {day_str} {year_str}", "%B %d %Y")
                                        eol_date = parsed_date.strftime("%Y-%m-%d")
                                    except ValueError:
                                        # Try abbreviated month
                                        try:
                                            parsed_date = datetime.strptime(f"{month_str} {day_str} {year_str}", "%b %d %Y")
                                            eol_date = parsed_date.strftime("%Y-%m-%d")
                                        except ValueError:
                                            pass

                        if eol_date:
                            records.append({
                                "cycle": version_num,
                                "eol": eol_date,
                                "support": None,
                                "source": "redhat_official_scraped",
                            })

        except Exception as exc:
            logger.error(f"Error parsing all Fedora versions: {exc}")

        return records

    def get_supported_products(self) -> List[str]:
        """Get list of supported Red Hat products"""
        return [
            "Red Hat Enterprise Linux (RHEL)",
            "CentOS",
            "Fedora"
        ]
