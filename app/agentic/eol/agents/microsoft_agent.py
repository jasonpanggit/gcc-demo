"""
Microsoft EOL Agent - Scrapes Microsoft official sources for EOL information with Cosmos DB caching
"""
import asyncio
import json
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
    from utils.logger import get_logger
    logger = get_logger(__name__)
except ImportError:
    import logging
    logger = logging.getLogger(__name__)


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
        # Agent-level caching disabled - orchestrator uses eol_inventory as single source of truth
        self.cache_duration_hours = 24 * 30  # 30 days (reference only)
        self.cosmos_cache = None  # Caching handled by orchestrator via eol_inventory

        # Microsoft EOL URLs with metadata (single source of truth)
        self.eol_urls = {
            "windows-server": {
                "url": "https://learn.microsoft.com/en-us/windows/release-health/windows-server-release-info",
                "description": "Windows-Server EOL Information",
                "active": True,
                "priority": 1
            },
            "windows-10": {
                "url": "https://learn.microsoft.com/en-us/windows/release-health/release-information",
                "description": "Windows 10 EOL Information",
                "active": True,
                "priority": 2
            },
            "windows-11": {
                "url": "https://learn.microsoft.com/en-us/windows/release-health/windows11-release-information",
                "description": "Windows 11 EOL Information",
                "active": True,
                "priority": 3
            },
            "sql-server": {
                "url": "https://learn.microsoft.com/en-us/sql/sql-server/end-of-support/sql-server-end-of-life-overview",
                "description": "Sql-Server EOL Information",
                "active": True,
                "priority": 4
            }
        }

        # Static EOL fallback disabled.
        # self.static_eol_data = {}

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
        """Agent-level caching disabled - orchestrator handles caching via eol_inventory"""
        # Caching is now centralized in the orchestrator using eol_inventory
        return None

    async def fetch_from_url(self, url: str, software_hint: str, version: Optional[str] = None) -> Dict[str, Any]:
        """Download a Microsoft lifecycle page and extract EOL data directly from HTML."""
        start_time = time.time()
        try:
            cache_stats_manager.record_agent_request(
                agent_name="microsoft",
                url=url,
                start_time=start_time,
            )

            response = requests.get(url, headers=self.headers, timeout=self.timeout)
            response.raise_for_status()

            response_time_ms = (time.time() - start_time) * 1000

            parsed = await self._scrape_eol_data(software_hint, version)
            if parsed:
                cache_stats_manager.record_agent_request(
                    agent_name="microsoft",
                    url=url,
                    response_time_ms=response_time_ms,
                    success=True,
                    status_code=response.status_code,
                    records_extracted=1,
                )
                conf_val = parsed.get("confidence") or 0.7
                try:
                    conf_val = float(conf_val)
                    if conf_val > 1:
                        conf_val = conf_val / 100.0
                except (TypeError, ValueError):
                    conf_val = 0.7

                return self.create_success_response(
                    software_name=software_hint,
                    version=parsed.get("version") or parsed.get("cycle") or version,
                    eol_date=parsed.get("eol"),
                    support_end_date=parsed.get("support") or parsed.get("support_end_date"),
                    release_date=parsed.get("release"),
                    confidence=conf_val,
                    source_url=url,
                    additional_data={
                        "cycle": parsed.get("cycle"),
                        "source": parsed.get("source") or "microsoft_scrape",
                    },
                )

            cache_stats_manager.record_agent_request(
                agent_name="microsoft",
                url=url,
                response_time_ms=response_time_ms,
                success=False,
                status_code=response.status_code,
                records_extracted=0,
            )

            return self.create_failure_response(
                software_name=software_hint,
                version=version,
                error_message="No EOL data extracted from Microsoft URL",
            )

        except Exception as exc:  # pragma: no cover - network errors
            response_time_ms = (time.time() - start_time) * 1000
            cache_stats_manager.record_agent_request(
                agent_name="microsoft",
                url=url,
                response_time_ms=response_time_ms,
                success=False,
                error_message=str(exc),
            )
            logger.error(f"Failed to fetch Microsoft EOL data from {url}: {exc}")
            return self.create_failure_response(
                software_name=software_hint,
                version=version,
                error_message=f"Failed to parse {url}: {exc}",
            )

    async def fetch_all_from_url(self, url: str, software_hint: str, version: Optional[str] = None) -> list[Dict[str, Any]]:
        """Download a Microsoft lifecycle page and extract all EOL rows from HTML."""
        start_time = time.time()
        try:
            cache_stats_manager.record_agent_request(
                agent_name="microsoft",
                url=url,
                start_time=start_time,
            )

            response = requests.get(url, headers=self.headers, timeout=self.timeout)
            response.raise_for_status()

            response_time_ms = (time.time() - start_time) * 1000

            soup = BeautifulSoup(response.content, "html.parser")
            hint_lower = (software_hint or "").lower()

            records: list[Dict[str, Any]] = []
            if "windows-server" in hint_lower or "windows server" in hint_lower:
                records = self._parse_windows_server_eol(soup) or []
            elif "windows-10" in hint_lower or "windows-11" in hint_lower or "windows" in hint_lower:
                records = self._parse_windows_eol(soup) or []
            elif "sql-server" in hint_lower or "sql server" in hint_lower:
                parsed = self._parse_sql_server_eol(soup, version)
                if parsed:
                    if isinstance(parsed, list):
                        records = parsed
                    else:
                        records = [parsed]
            elif "office" in hint_lower:
                parsed = self._parse_office_eol(soup, version)
                if parsed:
                    records = [parsed]

            cache_stats_manager.record_agent_request(
                agent_name="microsoft",
                url=url,
                response_time_ms=response_time_ms,
                success=True,
                status_code=response.status_code,
                records_extracted=len(records),
            )

            return records

        except Exception as exc:  # pragma: no cover - network errors
            response_time_ms = (time.time() - start_time) * 1000
            cache_stats_manager.record_agent_request(
                agent_name="microsoft",
                url=url,
                response_time_ms=response_time_ms,
                success=False,
                error_message=str(exc),
            )
            logger.error(f"Failed to fetch Microsoft EOL data from {url}: {exc}")
            return []
    
    async def _cache_data(self, software_name: str, version: Optional[str], data: Dict[str, Any], source_url: Optional[str] = None):
        """Agent-level caching disabled - orchestrator handles caching via eol_inventory"""
        # Caching is now centralized in the orchestrator using eol_inventory
        # This method is kept for API compatibility but does nothing
        pass
    
    async def purge_cache(self, software_name: Optional[str] = None, version: Optional[str] = None) -> Dict[str, Any]:
        """Agent-level cache purge disabled - use eol_inventory for cache management"""
        # Caching is now centralized in the orchestrator using eol_inventory
        return {"success": True, "deleted_count": 0, "message": "Agent-level caching disabled - use eol_inventory"}
    
    # async def _fetch_eol_data(self, software_name: str, version: str = None) -> Optional[Dict[str, Any]]:
    #     """
    #     Fetch EOL data from Microsoft sources
    #     """
        # Check static data first for reliability
        # static_result = self._check_static_data(software_name, version)
        # if static_result:
        #     return static_result

        # Try web scraping for latest information
        # scraped_result = await self._scrape_eol_data(software_name, version)
        # if scraped_result:
        #     return scraped_result

        # return None
    
    async def get_eol_data(self, software_name: str, version: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Get Microsoft EOL data through web scraping and static data with caching"""
        # Normalize Windows Server naming to split year as version when missing
        normalized_name, resolved_version = self._normalize_windows_server_name(software_name, version)
        
        # Check cache first
        cached_data = await self._get_cached_data(normalized_name, resolved_version)
        if cached_data:
            return cached_data
        
        # # Get fresh data using our _fetch_eol_data method
        # result_data = await self._fetch_eol_data(normalized_name, resolved_version)
        
        # if result_data:
        #     # Add Microsoft-specific metadata
        #     source_url = self._get_scraping_url(normalized_name) or "https://docs.microsoft.com/en-us/lifecycle/products/"
        #     confidence = result_data.get("confidence", 70) / 100.0  # Convert to 0-1 scale

        #     # Prefer scraped/static version when caller did not provide one
        #     result_version = resolved_version or result_data.get("version") or result_data.get("cycle")

        #     # Create standardized response
        #     result = self.create_success_response(
        #         software_name=normalized_name,
        #         version=result_version,
        #         eol_date=result_data.get("eol"),
        #         support_end_date=result_data.get("support"),
        #         confidence=confidence,
        #         source_url=source_url,
        #         additional_data={
        #             "cycle": result_data.get("cycle"),
        #             "extendedSupport": result_data.get("extendedSupport"),
        #             "original_result": result_data
        #         }
        #     )
            
        #     # Cache the result
        #     await self._cache_data(normalized_name, result_version, result, source_url=source_url)
        #     return result

        return self.create_failure_response(
            software_name=normalized_name,
            version=resolved_version,
            error_message="No Microsoft EOL data found"
        )

    def _normalize_windows_server_name(self, software_name: str, version: Optional[str]) -> (str, Optional[str]):
        """Extract Windows Server year as version when embedded in name."""
        name = software_name or ""
        detected_version = version

        if "windows server" in name.lower() and not version:
            match = re.search(r"windows\s+server\s+(\d{4})", name, re.IGNORECASE)
            if match:
                detected_version = match.group(1)
                return "windows server", detected_version

        return software_name, detected_version

    def _extract_year(self, text: str) -> Optional[str]:
        """Return the first 4-digit year in the given text."""
        try:
            match = re.search(r"(20\d{2}|19\d{2})", text or "")
            return match.group(1) if match else None
        except Exception:
            return None
    
    def _check_static_data(self, software_name: str, version: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Check static EOL data for Microsoft products (disabled)."""
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

            parsed: Optional[Dict[str, Any]] = None
            if "windows-server" in software_name.lower():
                parsed_rows = self._parse_windows_server_eol(soup, version)
                if parsed_rows:
                    parsed = parsed_rows[0]
            elif "sql-server" in software_name.lower():
                parsed = self._parse_sql_server_eol(soup, version)
                if isinstance(parsed, list):
                    parsed = parsed[0] if parsed else None
            elif "office" in software_name.lower():
                parsed = self._parse_office_eol(soup, version)
            elif "windows-10" in software_name.lower():
                parsed_rows = self._parse_windows_eol(soup, version)
                if parsed_rows:
                    parsed = parsed_rows[0]
            elif "windows-11" in software_name.lower():
                parsed_rows = self._parse_windows_eol(soup, version)
                if parsed_rows:
                    parsed = parsed_rows[0]

            return parsed
            
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
        elif "windows-11" in software_lower or "windows 11" in software_lower:
            url_data = self.eol_urls.get("windows-11")
            return url_data.get("url") if url_data else None
        elif "windows-10" in software_lower or "windows 10" in software_lower:
            url_data = self.eol_urls.get("windows-10")
            return url_data.get("url") if url_data else None
        elif "sql server" in software_lower:
            url_data = self.eol_urls.get("sql-server")
            return url_data.get("url") if url_data else None
        elif "office" in software_lower:
            url_data = self.eol_urls.get("office")
            return url_data.get("url") if url_data else None
        elif "windows" in software_lower:
            url_data = self.eol_urls.get("windows-10")
            return url_data.get("url") if url_data else None
        elif ".net" in software_lower or "dotnet" in software_lower:
            url_data = self.eol_urls.get("dotnet")
            return url_data.get("url") if url_data else None
        elif "visual studio" in software_lower:
            url_data = self.eol_urls.get("visual-studio")
            return url_data.get("url") if url_data else None
        
        return None
    
    def _parse_windows_server_eol(self, soup: BeautifulSoup, version: Optional[str] = None) -> Optional[list[Dict[str, Any]]]:
        """Parse Windows Server EOL information from Microsoft docs table."""
        try:
            target_version = version.split('.')[0] if version else None
            tables = soup.find_all('table')

            def _normalize_header(text: str) -> str:
                return re.sub(r"\s+", " ", (text or "").strip().lower())

            def _normalize_value(value: Optional[str]) -> Optional[str]:
                if not value:
                    return None
                cleaned = value.strip()
                if not cleaned:
                    return None
                if "end of updates" in cleaned.lower():
                    return None
                return cleaned

            required_headers = {
                "windows server version",
                "editions",
                "mainstream support end date",
                "extended support end date",
                "availability date",
            }

            for table in tables:
                header_cells = []
                thead = table.find('thead')
                if thead:
                    header_cells = thead.find_all('th')
                if not header_cells:
                    first_row = table.find('tr')
                    if first_row:
                        header_cells = first_row.find_all('th')

                headers = [_normalize_header(th.get_text(" ", strip=True)) for th in header_cells]
                if not headers:
                    continue

                header_map = {name: idx for idx, name in enumerate(headers)}
                if not required_headers.issubset(header_map.keys()):
                    continue

                results: list[Dict[str, Any]] = []
                rows = table.find_all('tr')[1:]
                for row in rows:
                    cells = row.find_all(['td'])
                    if len(cells) < len(headers):
                        continue

                    version_text = cells[header_map["windows server version"]].get_text(" ", strip=True)
                    version_text_clean = re.sub(r"\s*\([^)]*\)", "", version_text).strip()
                    version_year = self._extract_year(version_text_clean) or version_text_clean
                    software_name = re.sub(r"\s+\d{4}.*$", "", version_text_clean).strip() or "windows server"

                    editions_raw = None
                    if "editions" in header_map:
                        editions_raw = _normalize_value(
                            cells[header_map["editions"]].get_text(" ", strip=True)
                        )
                    editions_list = []
                    if editions_raw:
                        editions_list = [e.strip() for e in editions_raw.split(",") if e.strip()]

                    if target_version and target_version not in version_text_clean and target_version != version_year:
                        continue

                    availability_raw = _normalize_value(cells[header_map["availability date"]].get_text(" ", strip=True))
                    mainstream_raw = _normalize_value(cells[header_map["mainstream support end date"]].get_text(" ", strip=True))
                    extended_raw = _normalize_value(cells[header_map["extended support end date"]].get_text(" ", strip=True))

                    latest_update = None
                    latest_revision = None
                    latest_build = None
                    if "latest update" in header_map:
                        latest_update = _normalize_value(cells[header_map["latest update"]].get_text(" ", strip=True))
                    if "latest revision date" in header_map:
                        latest_revision = _normalize_value(cells[header_map["latest revision date"]].get_text(" ", strip=True))
                    if "latest build" in header_map:
                        latest_build = _normalize_value(cells[header_map["latest build"]].get_text(" ", strip=True))

                    edition_values = editions_list or [None]
                    if len(editions_list) == 2:
                        edition_values.append(None)
                    for edition in edition_values:
                        version_value = version_year
                        if edition:
                            version_value = f"{version_year} {edition}"

                        results.append(
                            {
                                "cycle": version_text_clean,
                                "software_name": software_name,
                                "version": version_value,
                                "edition": edition,
                                "eol": self._convert_date_format(extended_raw) if extended_raw else None,
                                "support": self._convert_date_format(mainstream_raw) if mainstream_raw else None,
                                "release": self._convert_date_format(availability_raw) if availability_raw else None,
                                "latest_update": latest_update,
                                "latest_revision_date": self._convert_date_format(latest_revision) if latest_revision else None,
                                "latest_build": latest_build,
                                "source": "microsoft_official_scraped",
                                "extendedSupport": True,
                            }
                        )

                if results:
                    return results

            return None

        except Exception as e:
            logger.error(f"Error parsing Windows Server EOL: {e}")
            return None
    
    def _parse_sql_server_eol(self, soup: BeautifulSoup, version: Optional[str] = None) -> Optional[list[Dict[str, Any]]]:
        """Parse SQL Server lifecycle table for EOL information."""
        try:
            target_version = version.split('.')[0] if version else None

            def _normalize_header(text: str) -> str:
                return re.sub(r"\s+", " ", (text or "").strip().lower())

            def _year_to_date(value: Optional[str]) -> Optional[str]:
                if not value:
                    return None
                match = re.search(r"(20\d{2}|19\d{2})", value)
                if not match:
                    return None
                return f"{match.group(1)}-12-31"

            required_headers = {
                "version",
                "release year",
                "mainstream support end year",
                "extended support end year",
            }

            tables = soup.find_all("table")
            for table in tables:
                header_cells = []
                thead = table.find("thead")
                if thead:
                    header_cells = thead.find_all("th")
                if not header_cells:
                    first_row = table.find("tr")
                    if first_row:
                        header_cells = first_row.find_all("th")

                headers = [_normalize_header(th.get_text(" ", strip=True)) for th in header_cells]
                if not headers:
                    continue

                header_map = {name: idx for idx, name in enumerate(headers)}
                if not required_headers.issubset(header_map.keys()):
                    continue

                rows = table.find_all("tr")[1:]
                results: list[Dict[str, Any]] = []
                for row in rows:
                    cells = row.find_all(["th", "td"])
                    if len(cells) < len(headers):
                        continue

                    version_text = cells[header_map["version"]].get_text(" ", strip=True)
                    if not version_text:
                        continue

                    version_text_clean = re.sub(r"\s*\([^)]*\)", "", version_text).strip()
                    if target_version and target_version.lower() not in version_text_clean.lower():
                        continue

                    if version_text_clean.lower().startswith("sql server"):
                        software_name = "SQL Server"
                        version_value = version_text_clean[len("sql server"):].strip() or version_text_clean
                    else:
                        software_name = "SQL Server"
                        version_value = version_text_clean

                    release_year_raw = cells[header_map["release year"]].get_text(" ", strip=True)
                    mainstream_year_raw = cells[header_map["mainstream support end year"]].get_text(" ", strip=True)
                    extended_year_raw = cells[header_map["extended support end year"]].get_text(" ", strip=True)

                    results.append(
                        {
                            "cycle": version_value,
                            "software_name": software_name,
                            "version": version_value,
                            "release": _year_to_date(release_year_raw),
                            "support": _year_to_date(mainstream_year_raw),
                            "eol": _year_to_date(extended_year_raw),
                            "source": "microsoft_official_scraped",
                            "extendedSupport": True,
                        }
                    )

                if results:
                    return results

            return None

        except Exception as e:
            logger.error(f"Error parsing SQL Server EOL: {e}")
            return None

    def _parse_windows_eol(self, soup: BeautifulSoup, version: Optional[str] = None) -> Optional[list[Dict[str, Any]]]:
        """Parse Windows EOL information from Microsoft release info tables."""
        try:
            target_version = version.strip() if version else None
            tables = soup.find_all("table")

            page_heading = soup.find(["h1", "h2"])
            page_title = page_heading.get_text(" ", strip=True).lower() if page_heading else ""
            base_name = "Windows 11" if "windows 11" in page_title else "Windows 10"

            def _normalize_header(text: str) -> str:
                return re.sub(r"\s+", " ", (text or "").strip().lower())

            def _normalize_value(value: Optional[str]) -> Optional[str]:
                if not value:
                    return None
                cleaned = value.strip()
                if not cleaned:
                    return None
                if "end of updates" in cleaned.lower():
                    return None
                return cleaned

            results: list[Dict[str, Any]] = []
            for table in tables:
                header_cells = []
                thead = table.find("thead")
                if thead:
                    header_cells = thead.find_all("th")
                if not header_cells:
                    first_row = table.find("tr")
                    if first_row:
                        header_cells = first_row.find_all("th")

                headers = [_normalize_header(th.get_text(" ", strip=True)) for th in header_cells]
                if not headers:
                    continue

                header_map = {name: idx for idx, name in enumerate(headers)}
                if "version" not in header_map or "availability date" not in header_map:
                    continue

                end_updates_cols = [
                    name for name in headers
                    if name.startswith("end of updates") or name.endswith("support end date")
                ]
                if not end_updates_cols:
                    continue

                section_title = ""
                section_heading = table.find_previous(["h2", "h3", "h4"])
                if section_heading:
                    section_title = section_heading.get_text(" ", strip=True).lower()

                if "enterprise and iot enterprise" in section_title:
                    software_names = [
                        f"{base_name} Enterprise",
                        f"{base_name} IoT Enterprise",
                    ]
                else:
                    software_names = [base_name]

                rows = table.find_all("tr")[1:]
                for row in rows:
                    cells = row.find_all(["td"])
                    if len(cells) < len(headers):
                        continue

                    version_text = cells[header_map["version"]].get_text(" ", strip=True)
                    if target_version and target_version.lower() not in version_text.lower():
                        continue

                    availability_raw = _normalize_value(
                        cells[header_map["availability date"]].get_text(" ", strip=True)
                    )

                    end_updates_value = None
                    for col_name in end_updates_cols:
                        col_idx = header_map.get(col_name)
                        if col_idx is None:
                            continue
                        candidate = _normalize_value(cells[col_idx].get_text(" ", strip=True))
                        if candidate:
                            end_updates_value = candidate
                            break

                    latest_update = None
                    latest_revision = None
                    latest_build = None
                    if "latest update" in header_map:
                        latest_update = _normalize_value(cells[header_map["latest update"]].get_text(" ", strip=True))
                    if "latest revision date" in header_map:
                        latest_revision = _normalize_value(cells[header_map["latest revision date"]].get_text(" ", strip=True))
                    if "latest build" in header_map:
                        latest_build = _normalize_value(cells[header_map["latest build"]].get_text(" ", strip=True))

                    for software_name in software_names:
                        results.append(
                            {
                                "cycle": version_text,
                                "software_name": software_name,
                                "version": version_text,
                                "eol": self._convert_date_format(end_updates_value) if end_updates_value else None,
                                "release": self._convert_date_format(availability_raw) if availability_raw else None,
                                "latest_update": latest_update,
                                "latest_revision_date": self._convert_date_format(latest_revision) if latest_revision else None,
                                "latest_build": latest_build,
                                "source": "microsoft_official_scraped",
                                "extendedSupport": True,
                            }
                        )

            return results or None

        except Exception as e:
            logger.error(f"Error parsing Windows EOL: {e}")
            return None
    
    def _parse_office_eol(self, soup: BeautifulSoup, version: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Parse Office EOL information from Microsoft docs"""
        try:
            # Office EOL is complex, return known information
            if version and "2016" in version:
                return {
                    "cycle": "2016",
                    "version": "2016",
                    "eol": "2025-10-14",
                    "support": "2020-10-13",
                    "source": "microsoft_official_scraped",
                    "extendedSupport": True
                }
            elif version and "2019" in version:
                return {
                    "cycle": "2019",
                    "version": "2019",
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
