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
import time
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
        super().__init__("nodejs")
        
        self.timeout = 15
        self.headers = {
            'User-Agent': (
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                'AppleWebKit/537.36 (KHTML, like Gecko) '
                'Chrome/91.0.4472.124 Safari/537.36'
            )
        }

        # Agent-level caching disabled - orchestrator uses eol_inventory as single source of truth
        self.cosmos_cache = None

        # Node.js product EOL URLs
                # Nodejs EOL URLs with metadata (single source of truth)
        self.eol_urls = {
            "nodejs": {
                "url": "https://nodejs.org/en/about/previous-releases",
                "description": "Node.js Release Schedule",
                "active": True,
                "priority": 1
            },
            # "npm": {
            #     "url": "https://github.com/npm/cli/releases",
            #     "description": "npm GitHub Releases",
            #     "active": True,
            #     "priority": 2
            # },
            # "yarn": {
            #     "url": "https://github.com/yarnpkg/yarn/releases",
            #     "description": "Yarn GitHub Releases",
            #     "active": True,
            #     "priority": 3
            # }
        }

        # Static data for Node.js versions (disabled)
        # self.static_eol_data = {
            # "nodejs-20": {
            #     "cycle": "20 LTS",
            #     "releaseDate": "2023-04-18",
            #     "eol": "2026-04-30",
            #     "support": "2025-10-30",
            #     "latest": "20.10.0",
            #     "lts": True,
            #     "source": "nodejs_official",
            #     "confidence": 95,
            # },
            # "nodejs-18": {
            #     "cycle": "18 LTS",
            #     "releaseDate": "2022-04-19",
            #     "eol": "2025-04-30",
            #     "support": "2024-10-30",
            #     "latest": "18.19.0",
            #     "lts": True,
            #     "source": "nodejs_official",
            #     "confidence": 95,
            # },
            # "nodejs-16": {
            #     "cycle": "16 LTS",
            #     "releaseDate": "2021-04-20",
            #     "eol": "2024-04-30",
            #     "support": "2023-09-11",
            #     "latest": "16.20.2",
            #     "lts": True,
            #     "source": "nodejs_official",
            #     "confidence": 95,
            # },
            # "nodejs-14": {
            #     "cycle": "14 LTS",
            #     "releaseDate": "2020-04-21",
            #     "eol": "2023-04-30",
            #     "support": "2022-10-30",
            #     "latest": "14.21.3",
            #     "lts": True,
            #     "source": "nodejs_official",
            #     "confidence": 95,
            # },
            # "nodejs-12": {
            #     "cycle": "12 LTS",
            #     "releaseDate": "2019-04-23",
            #     "eol": "2022-04-30",
            #     "support": "2021-10-30",
            #     "latest": "12.22.12",
            #     "lts": True,
            #     "source": "nodejs_official",
            #     "confidence": 95,
            # },
            # "npm-10": {
            #     "cycle": "10",
            #     "releaseDate": "2023-08-08",
            #     "eol": "2025-08-08",
            #     "support": "2024-08-08",
            #     "latest": "10.2.4",
            #     "source": "npm_official",
            #     "confidence": 90,
            # },
            # "npm-9": {
            #     "cycle": "9",
            #     "releaseDate": "2022-08-30",
            #     "eol": "2024-08-30",
            #     "support": "2023-08-30",
            #     "latest": "9.8.1",
            #     "source": "npm_official",
            #     "confidence": 90,
            # },
            # "yarn-4": {
            #     "cycle": "4",
            #     "releaseDate": "2023-10-23",
            #     "eol": "2025-10-23",
            #     "support": "2024-10-23",
            #     "latest": "4.0.2",
            #     "source": "yarn_official",
            #     "confidence": 85,
            # },
            # "yarn-3": {
            #     "cycle": "3",
            #     "releaseDate": "2021-10-04",
            #     "eol": "2024-10-04",
            #     "support": "2023-10-04",
            #     "latest": "3.6.4",
            #     "source": "yarn_official",
            #     "confidence": 85,
            # },
            # "yarn-1": {
            #     "cycle": "1",
            #     "releaseDate": "2016-10-11",
            #     "eol": "2024-04-30",
            #     "support": "2023-04-30",
            #     "latest": "1.22.19",
            #     "source": "yarn_official",
            #     "confidence": 85,
            # },
        # }

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
        """Agent-level caching disabled - eol_inventory is the single source of truth"""
        # Cosmos caching consolidated to orchestrator via eol_inventory
        return None

    async def _cache_data(self, software_name: str, version: Optional[str], data: Dict[str, Any], source_url: Optional[str] = None):
        """Agent-level caching disabled - eol_inventory is the single source of truth"""
        # Cosmos caching consolidated to orchestrator via eol_inventory
        pass

    async def purge_cache(self, software_name: Optional[str] = None, version: Optional[str] = None) -> Dict[str, Any]:
        """Agent-level caching disabled - use eol_inventory for cache management"""
        # Cosmos caching consolidated to orchestrator via eol_inventory
        return {"success": True, "deleted_count": 0, "message": "Agent-level caching disabled - use eol_inventory"}

    async def get_eol_data(self, software_name: str, version: Optional[str] = None) -> Dict[str, Any]:
        """Get EOL data for Node.js ecosystem products with enhanced static data checking"""
        
        # Check cache first
        cached_data = await self._get_cached_data(software_name, version)
        if cached_data:
            return cached_data
        
        # # Get fresh data using enhanced fetch method
        # result_data = await self._fetch_eol_data(software_name, version)
        
        # if result_data:
        #     # Add Node.js-specific metadata
        #     source_url = self._determine_source_url(software_name)
        #     confidence = result_data.get("confidence", 85)
            
        #     result = self.create_success_response(
        #         software_name=software_name,
        #         version=version or result_data.get("cycle", "unknown"),
        #         eol_date=result_data.get("eol", ""),
        #         support_end_date=result_data.get("support", ""),
        #         confidence=confidence / 100.0,  # Convert to decimal
        #         source_url=source_url,
        #         additional_data={
        #             "cycle": result_data.get("cycle", ""),
        #             "extended_support": result_data.get("extendedSupport", False),
        #             "agent": "nodejs",
        #             "data_source": "nodejs_agent"
        #         }
        #     )
            
        #     # Cache the result
        #     await self._cache_data(software_name, version, result, source_url=source_url)
        #     return result

        return self.create_failure_response(
            f"No EOL information found for {software_name}" + (f" version {version}" if version else ""),
            "no_data_found",
            {"searched_product": software_name, "searched_version": version}
        )

    # async def _fetch_eol_data(self, software_name: str, version: str = None) -> Optional[Dict[str, Any]]:
    #     """
    #     Fetch EOL data from Node.js ecosystem sources
    #     """
    #     # Check static data first for reliability
    #     # static_result = self._check_static_data(software_name, version)
    #     # if static_result:
    #     #     return static_result

    #     # Try web scraping for latest information
    #     scraped_result = await self._scrape_nodejs_eol(software_name, version)
    #     if scraped_result:
    #         return scraped_result

    #     return None

    # def _check_static_data(self, software_name: str, version: Optional[str] = None) -> Optional[Dict[str, Any]]:
    #     """Check static EOL data for Node.js ecosystem products (disabled)."""
    #     return None
    
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
            # elif "npm" in name_lower:
            #     url_data = self.eol_urls["npm"]
            #     url = url_data.get("url") if isinstance(url_data, dict) else url_data
            # elif "yarn" in name_lower:
            #     url_data = self.eol_urls["yarn"]
            #     url = url_data.get("url") if isinstance(url_data, dict) else url_data
            
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
            # if "npm" in name_lower:
            #     return self._parse_npm_page(soup, software_name, version)
            # if "yarn" in name_lower:
            #     return self._parse_yarn_page(soup, software_name, version)
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

    async def fetch_all_from_url(self, url: str, software_hint: str, version: Optional[str] = None) -> list[Dict[str, Any]]:
        """Download a Node.js release page and extract all EOL rows."""
        start_time = time.time()
        try:
            cache_stats_manager.record_agent_request(
                agent_name="nodejs",
                url=url,
                start_time=start_time,
            )

            response = requests.get(url, headers=self.headers, timeout=self.timeout)
            response.raise_for_status()
            response_time_ms = (time.time() - start_time) * 1000

            soup = BeautifulSoup(response.content, "html.parser")
            rows = self._parse_nodejs_page_all(soup)
            cache_stats_manager.record_agent_request(
                agent_name="nodejs",
                url=url,
                response_time_ms=response_time_ms,
                success=True,
                status_code=response.status_code,
                records_extracted=len(rows),
            )

            if rows:
                cache_tasks = []
                for row in rows:
                    row_version = row.get("version") or row.get("cycle")
                    response_payload = self.create_success_response(
                        software_name=software_hint,
                        version=row_version,
                        eol_date=row.get("eol"),
                        support_end_date=row.get("support"),
                        release_date=row.get("release"),
                        confidence=0.95,
                        source_url=url,
                        additional_data={
                            "cycle": row.get("cycle"),
                            "status": row.get("status"),
                            "codename": row.get("codename"),
                            "source": row.get("source") or "nodejs_scrape",
                        },
                    )
                    cache_tasks.append(self._cache_data(software_hint, row_version, response_payload, source_url=url))

                if cache_tasks:
                    await asyncio.gather(*cache_tasks, return_exceptions=True)

            return rows
        except Exception as exc:  # pragma: no cover - network errors
            response_time_ms = (time.time() - start_time) * 1000
            cache_stats_manager.record_agent_request(
                agent_name="nodejs",
                url=url,
                response_time_ms=response_time_ms,
                success=False,
                error_message=str(exc),
            )
            logger.error("Error fetching Node.js URL %s: %s", url, exc)
            return []

    async def fetch_from_url(self, url: str, software_hint: str, version: Optional[str] = None) -> Dict[str, Any]:
        """Download a Node.js release page and extract a single EOL row."""
        start_time = time.time()
        try:
            cache_stats_manager.record_agent_request(
                agent_name="nodejs",
                url=url,
                start_time=start_time,
            )

            response = requests.get(url, headers=self.headers, timeout=self.timeout)
            response.raise_for_status()
            response_time_ms = (time.time() - start_time) * 1000

            soup = BeautifulSoup(response.content, "html.parser")
            parsed = self._parse_nodejs_page(soup, software_hint, version)
            if parsed:
                cache_stats_manager.record_agent_request(
                    agent_name="nodejs",
                    url=url,
                    response_time_ms=response_time_ms,
                    success=True,
                    status_code=response.status_code,
                    records_extracted=1,
                )

                result = self.create_success_response(
                    software_name=software_hint,
                    version=parsed.get("version") or parsed.get("cycle") or version,
                    eol_date=parsed.get("eol"),
                    support_end_date=parsed.get("support"),
                    release_date=parsed.get("release"),
                    confidence=0.95,
                    source_url=url,
                    additional_data={
                        "cycle": parsed.get("cycle"),
                        "source": parsed.get("source") or "nodejs_scrape",
                    },
                )

                await self._cache_data(software_hint, result["data"].get("version") or version, result, source_url=url)

                return result

            cache_stats_manager.record_agent_request(
                agent_name="nodejs",
                url=url,
                response_time_ms=response_time_ms,
                success=False,
                status_code=response.status_code,
                records_extracted=0,
            )
            return self.create_failure_response(
                software_name=software_hint,
                version=version,
                error_message="No Node.js EOL data extracted from URL",
            )
        except Exception as exc:  # pragma: no cover - network errors
            response_time_ms = (time.time() - start_time) * 1000
            cache_stats_manager.record_agent_request(
                agent_name="nodejs",
                url=url,
                response_time_ms=response_time_ms,
                success=False,
                error_message=str(exc),
            )
            return self.create_failure_response(
                software_name=software_hint,
                version=version,
                error_message=str(exc),
            )

    def _parse_nodejs_page(self, soup: BeautifulSoup, software_name: str, version: Optional[str]) -> Optional[Dict[str, Any]]:
        """Parse Node.js releases table content."""
        name_lower = (software_name or "").lower()
        if "node" not in name_lower:
            return None

        target_major = None
        if version:
            target_major = version.split('.')[0]
        else:
            match = re.search(r"\b(\d{1,2})\b", software_name)
            if match:
                target_major = match.group(1)

        parsed_rows = self._parse_nodejs_page_all(soup)
        if not parsed_rows:
            return None

        if target_major:
            for row in parsed_rows:
                if row.get("version") == target_major:
                    return row

        return parsed_rows[0]

    def _parse_nodejs_page_all(self, soup: BeautifulSoup) -> list[Dict[str, Any]]:
        """Parse all Node.js releases rows from the table."""
        def _normalize_header(text: str) -> str:
            return re.sub(r"\s+", " ", (text or "").strip().lower())

        def _parse_date(value: Optional[str]) -> Optional[str]:
            if not value:
                return None
            value = value.strip()
            if not value:
                return None
            try:
                parsed = datetime.strptime(value, "%b %d, %Y")
                return parsed.strftime("%Y-%m-%d")
            except Exception:
                return value

        required_headers = {
            "node.js",
            "codename",
            "first released",
            "last updated",
            "status",
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
            parsed_rows: list[Dict[str, Any]] = []
            for row in rows:
                cells = row.find_all(["th", "td"])
                if len(cells) < len(headers):
                    continue

                version_text = cells[header_map["node.js"]].get_text(" ", strip=True)
                if not version_text:
                    continue

                version_match = re.search(r"\d+", version_text)
                if not version_match:
                    continue
                version_value = version_match.group(0)

                codename = cells[header_map["codename"]].get_text(" ", strip=True)
                first_released = _parse_date(cells[header_map["first released"]].get_text(" ", strip=True))
                last_updated = _parse_date(cells[header_map["last updated"]].get_text(" ", strip=True))
                status = cells[header_map["status"]].get_text(" ", strip=True)

                is_eol = "end-of-life" in status.lower()

                parsed_rows.append({
                    "cycle": version_value,
                    "version": version_value,
                    "eol": last_updated if is_eol else None,
                    "support": last_updated if not is_eol else None,
                    "release": first_released,
                    "status": status,
                    "codename": codename,
                    "source": "nodejs_official_scraped",
                })

            if parsed_rows:
                return parsed_rows

        return []

    # def _parse_github_release_page(self, soup: BeautifulSoup, source: str) -> Optional[Dict[str, Any]]:
    #     """Parse GitHub releases page for latest release metadata."""
    #     release_entry = (
    #         soup.find("div", class_="release-entry")
    #         or soup.find("div", class_="js-release-entry")
    #     )

    #     if not release_entry:
    #         return None

    #     tag_element = release_entry.find("a", class_=re.compile(r"release-header__tag|Link--primary"))
    #     if not tag_element:
    #         tag_element = release_entry.find("a", href=re.compile(r"/tag/"))
    #     tag_text = tag_element.get_text(" ", strip=True) if tag_element else ""
    #     version_value = tag_text.lstrip("vV") if tag_text else None

    #     time_element = release_entry.find("relative-time") or release_entry.find("time")
    #     release_date = None
    #     if time_element:
    #         release_date = time_element.get("datetime") or time_element.get_text(" ", strip=True)
    #         if release_date:
    #             try:
    #                 parsed = datetime.fromisoformat(release_date.replace("Z", "+00:00"))
    #                 release_date = parsed.date().isoformat()
    #             except Exception:
    #                 release_date = release_date.split("T")[0]

    #     if not version_value and not release_date:
    #         return None

    #     return {
    #         "cycle": version_value or "unknown",
    #         "version": version_value or "unknown",
    #         "release": release_date,
    #         "support": None,
    #         "eol": None,
    #         "source": source,
    #     }

    # def _parse_npm_page(self, soup: BeautifulSoup, software_name: str, version: Optional[str]) -> Optional[Dict[str, Any]]:
    #     """Parse npm GitHub releases page."""
    #     return self._parse_github_release_page(soup, "npm_official_scraped")

    # def _parse_yarn_page(self, soup: BeautifulSoup, software_name: str, version: Optional[str]) -> Optional[Dict[str, Any]]:
    #     """Parse Yarn GitHub releases page."""
    #     return self._parse_github_release_page(soup, "yarn_official_scraped")

    # def is_relevant(self, software_name: str) -> bool:
    #     """Check if this agent is relevant for the given software"""
    #     name_lower = software_name.lower()
    #     nodejs_keywords = [
    #         'node', 'nodejs', 'npm', 'yarn', 'pnpm', 'bun',
    #         'express', 'react', 'vue', 'angular', 'next'
    #     ]
        
    #     return any(keyword in name_lower for keyword in nodejs_keywords)
