"""
Microsoft EOL Agent - Scrapes Microsoft official sources for EOL information with Cosmos DB caching
"""
import requests
from bs4 import BeautifulSoup
from typing import Dict, Any, Optional
import re
from datetime import datetime, timedelta
import os
import hashlib
import time
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
    from utils.eol_cache import eol_cache
    from utils.logger import get_logger
    logger = get_logger(__name__)
except ImportError:
    import logging
    logger = logging.getLogger(__name__)
    eol_cache = None


class MicrosoftEOLAgent(BaseEOLAgent):
    """Agent for scraping Microsoft official EOL information with Cosmos DB caching"""

    def __init__(self):
        super().__init__("microsoft")
        
        self.timeout = 15
        self.headers = {
            'User-Agent': (
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                'AppleWebKit/537.36 (KHTML, like Gecko) '
                'Chrome/91.0.4472.124 Safari/537.36'
            )
        }
        # Cosmos caching enabled
        self.cache_duration_hours = 24 * 30  # 30 days
        # Use shared EOL cache singleton (per-instance reference for compatibility)
        self.cosmos_cache = eol_cache

        # Microsoft EOL URLs with metadata (single source of truth)
        self.eol_urls = {
            "windows-server": {
                "url": "https://learn.microsoft.com/en-us/windows/release-health/windows-server-release-info",
                "description": "Windows-Server EOL Information",
                "active": True,
                "priority": 1
            },
            "windows": {
                "url": "https://learn.microsoft.com/en-us/windows/release-health/release-information",
                "description": "Windows EOL Information",
                "active": True,
                "priority": 2
            },
            "sql-server": {
                "url": "https://learn.microsoft.com/en-us/sql/sql-server/end-of-support/sql-server-end-of-life-overview",
                "description": "Sql-Server EOL Information",
                "active": True,
                "priority": 3
            },
            "office": {
                "url": "https://learn.microsoft.com/en-us/lifecycle/products/microsoft-365",
                "description": "Office EOL Information",
                "active": True,
                "priority": 4
            },
            "dotnet": {
                "url": "https://dotnet.microsoft.com/en-us/platform/support/policy",
                "description": "Dotnet EOL Information",
                "active": True,
                "priority": 5
            },
            "visual-studio": {
                "url": "https://learn.microsoft.com/en-us/visualstudio/releases/2022/release-history",
                "description": "Visual-Studio EOL Information",
                "active": True,
                "priority": 6
            },
            "lifecycle": {
                "url": "https://learn.microsoft.com/en-us/lifecycle/products/",
                "description": "Lifecycle EOL Information",
                "active": True,
                "priority": 7
            }
        }

        # Fallback static data for critical Microsoft products with confidence levels
        self.static_eol_data = {
            "windows-server-2016": {
                "cycle": "2016",
                "releaseDate": "2016-10-15",
                "eol": "2027-01-12",
                "support": "2022-01-11",
                "latest": "10.0.14393",
                "extendedSupport": True,
                "source": "microsoft_official",
                "confidence": 95.0,  # High confidence for official data
            },
            "windows-server-2012-r2": {
                "cycle": "2012 R2",
                "releaseDate": "2013-10-17",
                "eol": "2023-10-10",
                "support": "2018-10-09",
                "latest": "6.3.9600",
                "extendedSupport": True,
                "source": "microsoft_official",
                "confidence": 95.0,
            },
            "windows-server-2019": {
                "cycle": "2019",
                "releaseDate": "2018-10-02",
                "eol": "2029-01-09",
                "support": "2024-01-09",
                "latest": "10.0.17763",
                "extendedSupport": True,
                "source": "microsoft_official",
                "confidence": 95.0,
            },
            "windows-server-2022": {
                "cycle": "2022",
                "releaseDate": "2021-08-18",
                "eol": "2031-10-14",
                "support": "2026-10-13",
                "latest": "10.0.20348",
                "extendedSupport": True,
                "source": "microsoft_official",
                "confidence": 95.0,
            },
            "windows-server-2025": {
                "cycle": "2025",
                "releaseDate": "2024-11-01",
                "eol": "2034-10-10",
                "support": "2029-10-09",
                "latest": "10.0.26100",
                "extendedSupport": True,
                "source": "microsoft_official",
                "confidence": 95.0,
            },
            "sql-server-2014": {
                "cycle": "2014",
                "releaseDate": "2014-06-05",
                "eol": "2024-07-09",
                "support": "2019-07-09",
                "latest": "12.0.6024.0",
                "extendedSupport": True,
                "source": "microsoft_official",
                "confidence": 95.0,
            },
            "sql-server-2016": {
                "cycle": "2016",
                "releaseDate": "2016-06-01",
                "eol": "2026-07-14",
                "support": "2021-07-13",
                "latest": "13.0.6419.1",
                "extendedSupport": True,
                "source": "microsoft_official",
                "confidence": 95.0,
            },
            "sql-server-2019": {
                "cycle": "2019",
                "releaseDate": "2019-11-04",
                "eol": "2030-01-08",
                "support": "2025-02-28",
                "latest": "15.0.4375.4",
                "extendedSupport": True,
                "source": "microsoft_official",
                "confidence": 95.0,
            },
            "sql-server-2022": {
                "cycle": "2022",
                "releaseDate": "2022-11-16",
                "eol": "2033-01-11",
                "support": "2028-01-11",
                "latest": "16.0.4025.1",
                "extendedSupport": True,
                "source": "microsoft_official",
                "confidence": 95.0,
            },
            # Microsoft Edge - Always supported with continuous updates
            "microsoft-edge": {
                "cycle": "Continuous",
                "releaseDate": "2020-01-15",
                "eol": "No EOL (Continuous updates)",
                "support": "Active",
                "latest": "Current",
                "extendedSupport": False,
                "source": "microsoft_official",
                "confidence": 95.0,
            },
            "edge": {
                "cycle": "Continuous",
                "releaseDate": "2020-01-15", 
                "eol": "No EOL (Continuous updates)",
                "support": "Active",
                "latest": "Current",
                "extendedSupport": False,
                "source": "microsoft_official",
                "confidence": 95.0,
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
        key_data = f"microsoft_eol_{software_name}_{version or 'any'}"
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
                # Use existing URL mapping method or default to lifecycle URL
                source_url = self._get_scraping_url(software_name) or self.eol_urls.get("lifecycle", "https://learn.microsoft.com/en-us/lifecycle/products/")
            
            await self.cosmos_cache.cache_response(software_name, version, self.agent_name, data, source_url=source_url)
    
    async def purge_cache(self, software_name: Optional[str] = None, version: Optional[str] = None) -> Dict[str, Any]:
        """Purge cached data for specific software or all Microsoft cache"""
        if self.cosmos_cache:
            return await self.cosmos_cache.clear_cache(software_name=software_name, agent_name=self.agent_name)
        return {"success": True, "deleted_count": 0, "message": "Caching not available"}
    
    async def _fetch_eol_data(self, software_name: str, version: str = None) -> Optional[Dict[str, Any]]:
        """
        Fetch EOL data from Microsoft sources
        """
        # Check static data first for reliability
        static_result = self._check_static_data(software_name, version)
        if static_result:
            return static_result

        # Try web scraping for latest information
        scraped_result = await self._scrape_eol_data(software_name, version)
        if scraped_result:
            return scraped_result

        return None
    
    async def get_eol_data(self, software_name: str, version: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Get Microsoft EOL data through web scraping and static data with caching"""
        
        # Check cache first
        cached_data = await self._get_cached_data(software_name, version)
        if cached_data:
            return cached_data
        
        # Get fresh data using our _fetch_eol_data method
        result_data = await self._fetch_eol_data(software_name, version)
        
        if result_data:
            # Add Microsoft-specific metadata
            source_url = self._get_scraping_url(software_name) or "https://docs.microsoft.com/en-us/lifecycle/products/"
            confidence = result_data.get("confidence", 70) / 100.0  # Convert to 0-1 scale

            # Create standardized response
            result = self.create_success_response(
                software_name=software_name,
                version=version,
                eol_date=result_data.get("eol"),
                support_end_date=result_data.get("support"),
                confidence=confidence,
                source_url=source_url,
                additional_data={
                    "cycle": result_data.get("cycle"),
                    "extendedSupport": result_data.get("extendedSupport"),
                    "original_result": result_data
                }
            )
            
            # Cache the result
            await self._cache_data(software_name, version, result, source_url=source_url)
            return result

        return self.create_failure_response(
            software_name=software_name,
            version=version,
            error_message="No Microsoft EOL data found"
        )
    
    def _check_static_data(self, software_name: str, version: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Check static EOL data for Microsoft products"""
        software_lower = software_name.lower().replace(" ", "-")
        
        logger.debug(f"Microsoft agent checking static data for: '{software_name}' -> '{software_lower}', version: {version}")
        
        # Special handling for Edge browser variations
        edge_variations = [
            "microsoft-edge", "edge", "ms-edge", "msedge", 
            "microsoft-edge-browser", "edge-browser"
        ]
        for edge_variant in edge_variations:
            if edge_variant in software_lower or software_lower in edge_variant:
                if "edge" in self.static_eol_data:
                    return self.static_eol_data["edge"]
        
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
            
        if version:
            # Try with version
            version_key = f"{software_lower}-{version.split('.')[0]}"
            if version_key in self.static_eol_data:
                return self.static_eol_data[version_key]
        
        # Special handling for Windows Server with version 10.0 -> map to correct version based on name
        if "windows-server" in software_lower and version and version.startswith("10.0"):
            # For Windows Server with 10.0, need to check the actual OS name to determine version
            # Windows Server 2025 should be mapped correctly based on name containing "2025"
            logger.info(f"Detected Windows Server with version 10.0, software_name: '{software_name}', checking for year in name")
            if "2025" in software_lower and "windows-server-2025" in self.static_eol_data:
                logger.info(f"Mapped Windows Server 10.0 to Windows Server 2025 based on name containing '2025'")
                return self.static_eol_data["windows-server-2025"]
            elif "2022" in software_lower and "windows-server-2022" in self.static_eol_data:
                logger.info(f"Mapped Windows Server 10.0 to Windows Server 2022 based on name containing '2022'")
                return self.static_eol_data["windows-server-2022"]
            elif "2019" in software_lower and "windows-server-2019" in self.static_eol_data:
                logger.info(f"Mapped Windows Server 10.0 to Windows Server 2019 based on name containing '2019'")
                return self.static_eol_data["windows-server-2019"]
            elif "2016" in software_lower and "windows-server-2016" in self.static_eol_data:
                logger.info(f"Mapped Windows Server 10.0 to Windows Server 2016 based on name containing '2016'")
                return self.static_eol_data["windows-server-2016"]
            else:
                # Default to 2025 for Windows Server 10.0 if no specific version found in name
                # This is because Windows Server 2025 is the latest and most likely for new deployments
                logger.info(f"Windows Server with version 10.0 detected but no specific year in name '{software_name}' - defaulting to Windows Server 2025")
                return self.static_eol_data.get("windows-server-2025")
        
        # Improved partial matches with better precision
        for key, data in self.static_eol_data.items():
            key_parts = key.split("-")
            software_parts = software_lower.split("-")
            
            # For Windows Server, require exact version match in partial matching
            if "windows" in software_parts and "server" in software_parts:
                logger.debug(f"Checking Windows Server partial match: software_parts={software_parts}, key_parts={key_parts}")
                # Look for version numbers in both
                software_version = None
                key_version = None
                
                for part in software_parts:
                    if part.isdigit() and len(part) == 4:  # Look for 4-digit years like 2025, 2022, etc.
                        software_version = part
                        break
                
                for part in key_parts:
                    if part.isdigit() and len(part) == 4:  # Look for 4-digit years like 2025, 2022, etc.
                        key_version = part
                        break
                
                logger.debug(f"Extracted versions: software_version={software_version}, key_version={key_version}")
                
                # If both have versions, they must match exactly
                if software_version and key_version:
                    if software_version == key_version:
                        logger.info(f"Found exact Windows Server version match: {software_version} -> {key}")
                        return data
                    else:
                        continue  # Skip this key if versions don't match
                elif software_version and not key_version:
                    continue  # Skip keys without versions if software has version
            
            # For other software, use standard partial matching
            if any(keyword in software_lower for keyword in key_parts):
                if not version or self._version_matches(version, data.get("cycle", "")):
                    return data
        
        return None
    
    async def _scrape_eol_data(self, software_name: str, version: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Scrape Microsoft EOL data from official websites"""
        start_time = time.time()
        url = None
        
        try:
            # Determine which URL to scrape based on software name
            url = self._get_scraping_url(software_name)
            if not url:
                return None
            
            # Record the agent request before making the HTTP call
            cache_stats_manager.record_agent_request(
                agent_name="microsoft", 
                url=url, 
                start_time=start_time
            )
            
            response = requests.get(url, headers=self.headers, timeout=self.timeout)
            response.raise_for_status()
            
            # Calculate response time
            response_time_ms = (time.time() - start_time) * 1000
            
            # Record successful request
            cache_stats_manager.record_agent_request(
                agent_name="microsoft",
                url=url,
                response_time_ms=response_time_ms,
                success=True,
                status_code=response.status_code
            )
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Extract EOL information based on product type
            if "windows-server" in software_name.lower():
                return self._parse_windows_server_eol(soup, version)
            elif "sql-server" in software_name.lower():
                return self._parse_sql_server_eol(soup, version)
            elif "office" in software_name.lower():
                return self._parse_office_eol(soup, version)
            
            return None
            
        except Exception as e:
            # Calculate response time for failed request
            response_time_ms = (time.time() - start_time) * 1000
            
            # Record failed request
            cache_stats_manager.record_agent_request(
                agent_name="microsoft",
                url=url or "unknown",
                response_time_ms=response_time_ms,
                success=False,
                error_message=str(e)
            )
            
            logger.error(f"Error scraping Microsoft EOL data from {url}: {e}")
            return None
    
    def _get_scraping_url(self, software_name: str) -> Optional[str]:
        """Get the appropriate Microsoft URL to scrape"""
        software_lower = software_name.lower()
        
        if "windows server" in software_lower:
            url_data = self.eol_urls.get("windows-server")
            return url_data.get("url") if url_data else None
        elif "sql server" in software_lower:
            url_data = self.eol_urls.get("sql-server")
            return url_data.get("url") if url_data else None
        elif "office" in software_lower:
            url_data = self.eol_urls.get("office")
            return url_data.get("url") if url_data else None
        elif "windows" in software_lower:
            url_data = self.eol_urls.get("windows")
            return url_data.get("url") if url_data else None
        elif ".net" in software_lower or "dotnet" in software_lower:
            url_data = self.eol_urls.get("dotnet")
            return url_data.get("url") if url_data else None
        elif "visual studio" in software_lower:
            url_data = self.eol_urls.get("visual-studio")
            return url_data.get("url") if url_data else None
        
        return None
    
    def _parse_windows_server_eol(self, soup: BeautifulSoup, version: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Parse Windows Server EOL information from Microsoft docs"""
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
                        
                        # Extract dates from subsequent cells
                        eol_date = None
                        support_date = None
                        
                        for cell in cells[1:]:
                            cell_text = cell.get_text().strip()
                            # Look for date patterns
                            date_match = re.search(r'(\d{1,2}/\d{1,2}/\d{4})', cell_text)
                            if date_match:
                                if not support_date:
                                    support_date = date_match.group(1)
                                else:
                                    eol_date = date_match.group(1)
                        
                        if eol_date:
                            return {
                                "cycle": version_text,
                                "eol": self._convert_date_format(eol_date),
                                "support": self._convert_date_format(support_date) if support_date else None,
                                "source": "microsoft_official_scraped",
                                "extendedSupport": True
                            }
            
            return None
            
        except Exception as e:
            logger.error(f"Error parsing Windows Server EOL: {e}")
            return None
    
    def _parse_sql_server_eol(self, soup: BeautifulSoup, version: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Parse SQL Server EOL information from Microsoft docs"""
        try:
            # Look for EOL information in the page content
            text_content = soup.get_text()
            
            # Search for version-specific EOL dates
            if version:
                # Look for patterns like "SQL Server 2016: Extended support until July 14, 2026"
                pattern = rf"SQL Server {version.split('.')[0]}.*?(\d{{1,2}}/\d{{1,2}}/\d{{4}}|\w+ \d{{1,2}}, \d{{4}})"
                match = re.search(pattern, text_content, re.IGNORECASE)
                
                if match:
                    eol_date = match.group(1)
                    return {
                        "cycle": version,
                        "eol": self._convert_date_format(eol_date),
                        "source": "microsoft_official_scraped",
                        "extendedSupport": True
                    }
            
            return None
            
        except Exception as e:
            logger.error(f"Error parsing SQL Server EOL: {e}")
            return None
    
    def _parse_office_eol(self, soup: BeautifulSoup, version: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Parse Office EOL information from Microsoft docs"""
        try:
            # Office EOL is complex, return known information
            if version and "2016" in version:
                return {
                    "cycle": "2016",
                    "eol": "2025-10-14",
                    "support": "2020-10-13",
                    "source": "microsoft_official_scraped",
                    "extendedSupport": True
                }
            elif version and "2019" in version:
                return {
                    "cycle": "2019",
                    "eol": "2025-10-14",
                    "support": "2023-10-10",
                    "source": "microsoft_official_scraped",
                    "extendedSupport": True
                }
            
            return None
            
        except Exception as e:
            logger.error(f"Error parsing Office EOL: {e}")
            return None
    
    def _convert_date_format(self, date_str: str) -> str:
        """Convert various date formats to ISO format"""
        try:
            # Handle different date formats
            if re.match(r'\d{1,2}/\d{1,2}/\d{4}', date_str):
                # MM/DD/YYYY format
                date_obj = datetime.strptime(date_str, '%m/%d/%Y')
            elif re.match(r'\w+ \d{1,2}, \d{4}', date_str):
                # Month DD, YYYY format
                date_obj = datetime.strptime(date_str, '%B %d, %Y')
            else:
                return date_str
            
            return date_obj.strftime('%Y-%m-%d')
            
        except Exception:
            return date_str
    
    def _version_matches(self, version: str, cycle: str) -> bool:
        """Check if version matches the cycle"""
        try:
            if not version or not cycle:
                return False
            
            # Extract major version from version string
            version_major = version.split('.')[0]
            
            # Check if cycle contains the major version
            return version_major in str(cycle)
            
        except Exception:
            return False
