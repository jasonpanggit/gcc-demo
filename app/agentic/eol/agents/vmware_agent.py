"""
VMware EOL Agent - Scrapes VMware official sources for EOL information
"""
import requests
from bs4 import BeautifulSoup
from typing import Dict, Any, Optional, List
import re
from datetime import datetime, timedelta
import json
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
        """Agent-level caching disabled - eol_inventory is the single source of truth"""
        # Caching consolidated to orchestrator via eol_inventory
        return None

    async def _cache_data(self, software_name: str, version: Optional[str], data: Dict[str, Any], confidence_level: int, source_url: Optional[str] = None) -> None:
        """Agent-level caching disabled - eol_inventory is the single source of truth"""
        # Caching consolidated to orchestrator via eol_inventory
        pass

    async def purge_cache(self, software_name: Optional[str] = None, version: Optional[str] = None) -> Dict[str, Any]:
        """Agent-level caching disabled - use eol_inventory for cache management"""
        # Caching consolidated to orchestrator via eol_inventory
        return {"status": "success", "action": "disabled", "message": "Agent-level caching disabled - use eol_inventory"}

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

    async def fetch_from_url(self, url: str, software_hint: str) -> Dict[str, Any]:
        """Fetch EOL data from a specific URL for vendor parsing.

        This method is called by the vendor parsing endpoint to scrape
        EOL data from the configured VMware URLs.

        Args:
            url: The URL to scrape (must be one of the configured eol_urls)
            software_hint: Software name hint (vsphere, vcenter, esxi, etc.)

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
                    "error": f"URL not in configured VMware URLs: {url}",
                    "data": {},
                }

            # Use software_hint to determine what to scrape
            software_name = software_hint or product_type

            # Call existing scraping logic
            result = await self._fetch_eol_data(software_name, version=None)

            if result:
                return {
                    "success": True,
                    "data": {
                        "software_name": software_name,
                        "version": result.get("cycle"),
                        "eol_date": result.get("eol"),
                        "support_end_date": result.get("support"),
                        "confidence": 0.85,  # Scraped data confidence
                        "source": "vmware_agent",
                        "agent_used": "vmware",
                    },
                    "confidence": 0.85,
                    "agent_used": "vmware",
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
            software_hint: Software name hint (vsphere, vcenter, esxi, etc.)

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
                logger.warning(f"URL not in configured VMware URLs: {url}")
                return []

            software_name = software_hint or product_type

            # Scrape the page
            start_time = datetime.now()
            cache_stats_manager.record_agent_request("vmware", url)

            response = requests.get(url, headers=self.headers, timeout=self.timeout)
            response.raise_for_status()

            response_time = (datetime.now() - start_time).total_seconds()
            cache_stats_manager.record_agent_request("vmware", url, response_time, success=True)

            soup = BeautifulSoup(response.content, 'html.parser')

            # Parse all versions from the page based on product type
            records = []

            if product_type == "vsphere":
                records = self._parse_all_vsphere_versions(soup)
            elif product_type == "vcenter":
                records = self._parse_all_vcenter_versions(soup)
            elif product_type == "esxi":
                records = self._parse_all_esxi_versions(soup)
            elif product_type == "workstation":
                records = self._parse_all_workstation_versions(soup)
            elif product_type == "fusion":
                records = self._parse_all_fusion_versions(soup)
            elif product_type == "nsx":
                records = self._parse_all_nsx_versions(soup)
            elif product_type == "vsan":
                records = self._parse_all_vsan_versions(soup)

            # Convert to vendor parsing format
            formatted_records = []
            for record in records:
                formatted_records.append({
                    "software_name": software_name,
                    "version": record.get("cycle"),
                    "eol": record.get("eol"),
                    "support": record.get("support"),
                    "confidence": 0.85,
                    "source": "vmware_agent",
                })

            return formatted_records

        except Exception as exc:
            logger.error(f"fetch_all_from_url failed for {url}: {exc}")
            # Record failed request
            if 'start_time' in locals():
                response_time = (datetime.now() - start_time).total_seconds()
                cache_stats_manager.record_agent_request("vmware", url, response_time, success=False, error_message=str(exc))
            return []

    def _parse_all_vsphere_versions(self, soup: BeautifulSoup) -> List[Dict[str, Any]]:
        """Parse ALL vSphere versions from the page for bulk vendor parsing.

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
                        if 'version' in version_text.lower() or 'product' in version_text.lower():
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
                                "source": "vmware_official_scraped",
                            })

        except Exception as exc:
            logger.error(f"Error parsing all vSphere versions: {exc}")

        return records

    def _parse_all_vcenter_versions(self, soup: BeautifulSoup) -> List[Dict[str, Any]]:
        """Parse ALL vCenter versions from the page."""
        # vCenter typically shares the same lifecycle as vSphere
        return self._parse_all_vsphere_versions(soup)

    def _parse_all_esxi_versions(self, soup: BeautifulSoup) -> List[Dict[str, Any]]:
        """Parse ALL ESXi versions from the page."""
        # ESXi typically shares the same lifecycle as vSphere
        return self._parse_all_vsphere_versions(soup)

    def _parse_all_workstation_versions(self, soup: BeautifulSoup) -> List[Dict[str, Any]]:
        """Parse ALL Workstation versions from the page."""
        records = []
        try:
            tables = soup.find_all('table')

            for table in tables:
                rows = table.find_all('tr')

                for row in rows:
                    cells = row.find_all(['td', 'th'])
                    if len(cells) >= 3:
                        version_text = cells[0].get_text().strip()

                        if 'version' in version_text.lower() or 'workstation' in version_text.lower():
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
                                "source": "vmware_official_scraped",
                            })

        except Exception as exc:
            logger.error(f"Error parsing all Workstation versions: {exc}")

        return records

    def _parse_all_fusion_versions(self, soup: BeautifulSoup) -> List[Dict[str, Any]]:
        """Parse ALL Fusion versions from the page."""
        records = []
        try:
            tables = soup.find_all('table')

            for table in tables:
                rows = table.find_all('tr')

                for row in rows:
                    cells = row.find_all(['td', 'th'])
                    if len(cells) >= 3:
                        version_text = cells[0].get_text().strip()

                        if 'version' in version_text.lower() or 'fusion' in version_text.lower():
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
                                "source": "vmware_official_scraped",
                            })

        except Exception as exc:
            logger.error(f"Error parsing all Fusion versions: {exc}")

        return records

    def _parse_all_nsx_versions(self, soup: BeautifulSoup) -> List[Dict[str, Any]]:
        """Parse ALL NSX versions from the page."""
        records = []
        try:
            tables = soup.find_all('table')

            for table in tables:
                rows = table.find_all('tr')

                for row in rows:
                    cells = row.find_all(['td', 'th'])
                    if len(cells) >= 3:
                        version_text = cells[0].get_text().strip()

                        if 'version' in version_text.lower() or 'nsx' in version_text.lower():
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
                                "source": "vmware_official_scraped",
                            })

        except Exception as exc:
            logger.error(f"Error parsing all NSX versions: {exc}")

        return records

    def _parse_all_vsan_versions(self, soup: BeautifulSoup) -> List[Dict[str, Any]]:
        """Parse ALL vSAN versions from the page."""
        records = []
        try:
            tables = soup.find_all('table')

            for table in tables:
                rows = table.find_all('tr')

                for row in rows:
                    cells = row.find_all(['td', 'th'])
                    if len(cells) >= 3:
                        version_text = cells[0].get_text().strip()

                        if 'version' in version_text.lower() or 'vsan' in version_text.lower():
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
                                "source": "vmware_official_scraped",
                            })

        except Exception as exc:
            logger.error(f"Error parsing all vSAN versions: {exc}")

        return records

    def is_relevant(self, software_name: str) -> bool:
        """Check if this agent is relevant for the given software"""
        name_lower = software_name.lower()
        vmware_keywords = [
            'vmware', 'vsphere', 'esxi', 'vcenter', 'workstation',
            'fusion', 'nsx', 'vsan', 'vrealize', 'vcloud'
        ]

        return any(keyword in name_lower for keyword in vmware_keywords)
