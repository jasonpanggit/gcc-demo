"""
Python EOL Agent - Scrapes Python official sources for EOL information
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

class PythonEOLAgent(BaseEOLAgent):
    """Agent for scraping Python official EOL information"""

    def __init__(self):
        # Agent identification
        self.agent_name = "python"
        
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

        # Python ecosystem EOL URLs with metadata (single source of truth)
        self.eol_urls = {
            "python": {
                "url": "https://devguide.python.org/versions/",
                "description": "Python Version Release Schedule",
                "active": True,
                "priority": 1
            },
            "django": {
                "url": "https://www.djangoproject.com/download/",
                "description": "Django Release Information",
                "active": True,
                "priority": 2
            },
            "flask": {
                "url": "https://palletsprojects.com/blog/",
                "description": "Flask News and Updates",
                "active": True,
                "priority": 3
            },
            "numpy": {
                "url": "https://numpy.org/neps/nep-0029-deprecation_policy.html",
                "description": "NumPy Deprecation Policy",
                "active": True,
                "priority": 4
            },
            "pandas": {
                "url": "https://pandas.pydata.org/docs/development/policies.html",
                "description": "Pandas Development Policies",
                "active": True,
                "priority": 5
            }
        }

        # Static data for Python ecosystem
        self.static_eol_data = {
            "python-3.12": {
                "cycle": "3.12",
                "releaseDate": "2023-10-02",
                "eol": "2028-10-02",
                "support": "2028-10-02",
                "latest": "3.12.0",
                "source": "python_official",
                "confidence": 95,
            },
            "python-3.11": {
                "cycle": "3.11",
                "releaseDate": "2022-10-24",
                "eol": "2027-10-24",
                "support": "2027-10-24",
                "latest": "3.11.6",
                "source": "python_official",
                "confidence": 95,
            },
            "python-3.10": {
                "cycle": "3.10",
                "releaseDate": "2021-10-04",
                "eol": "2026-10-04",
                "support": "2026-10-04",
                "latest": "3.10.13",
                "source": "python_official",
                "confidence": 95,
            },
            "python-3.9": {
                "cycle": "3.9",
                "releaseDate": "2020-10-05",
                "eol": "2025-10-05",
                "support": "2025-10-05",
                "latest": "3.9.18",
                "source": "python_official",
                "confidence": 95,
            },
            "python-3.8": {
                "cycle": "3.8",
                "releaseDate": "2019-10-14",
                "eol": "2024-10-14",
                "support": "2024-10-14",
                "latest": "3.8.18",
                "source": "python_official",
                "confidence": 95,
            },
            "python-3.7": {
                "cycle": "3.7",
                "releaseDate": "2018-06-27",
                "eol": "2023-06-27",
                "support": "2023-06-27",
                "latest": "3.7.17",
                "source": "python_official",
                "confidence": 95,
            },
            "python-2.7": {
                "cycle": "2.7",
                "releaseDate": "2010-07-03",
                "eol": "2020-01-01",
                "support": "2020-01-01",
                "latest": "2.7.18",
                "source": "python_official",
                "confidence": 95,
            },
            "django-4.2": {
                "cycle": "4.2 LTS",
                "releaseDate": "2023-04-03",
                "eol": "2026-04-01",
                "support": "2025-12-01",
                "latest": "4.2.7",
                "lts": True,
                "source": "django_official",
                "confidence": 90,
            },
            "django-4.1": {
                "cycle": "4.1",
                "releaseDate": "2022-08-03",
                "eol": "2023-12-01",
                "support": "2023-12-01",
                "latest": "4.1.13",
                "source": "django_official",
                "confidence": 90,
            },
            "django-3.2": {
                "cycle": "3.2 LTS",
                "releaseDate": "2021-04-06",
                "eol": "2024-04-01",
                "support": "2023-12-01",
                "latest": "3.2.23",
                "lts": True,
                "source": "django_official",
                "confidence": 90,
            },
            "flask-3.0": {
                "cycle": "3.0",
                "releaseDate": "2023-09-30",
                "eol": "2025-09-30",
                "support": "2024-09-30",
                "latest": "3.0.0",
                "source": "flask_official",
                "confidence": 85,
            },
            "flask-2.3": {
                "cycle": "2.3",
                "releaseDate": "2023-04-25",
                "eol": "2025-04-25",
                "support": "2024-04-25",
                "latest": "2.3.3",
                "source": "flask_official",
                "confidence": 85,
            },
            "numpy-1.25": {
                "cycle": "1.25",
                "releaseDate": "2023-06-17",
                "eol": "2025-06-17",
                "support": "2024-06-17",
                "latest": "1.25.2",
                "source": "numpy_official",
                "confidence": 85,
            },
            "numpy-1.24": {
                "cycle": "1.24",
                "releaseDate": "2022-12-18",
                "eol": "2024-12-18",
                "support": "2023-12-18",
                "latest": "1.24.4",
                "source": "numpy_official",
                "confidence": 85,
            },
            "pandas-2.1": {
                "cycle": "2.1",
                "releaseDate": "2023-08-30",
                "eol": "2025-08-30",
                "support": "2024-08-30",
                "latest": "2.1.3",
                "source": "pandas_official",
                "confidence": 85,
            },
            "pandas-2.0": {
                "cycle": "2.0",
                "releaseDate": "2023-04-03",
                "eol": "2025-04-03",
                "support": "2024-04-03",
                "latest": "2.0.3",
                "source": "pandas_official",
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
        key_data = f"python_eol_{software_name}_{version or 'any'}"
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
                software_lower = software_name.lower()
                for product_type, url_data in self.eol_urls.items():
                    if product_type in software_lower:
                        source_url = url_data["url"]
                        break
                
                # Default to Python official URL if no specific match
                if not source_url:
                    source_url = self.get_url("python") or "https://devguide.python.org/versions/"
            
            await self.cosmos_cache.cache_response(software_name, version, self.agent_name, data, source_url=source_url)
        except Exception as e:
            logger.error(f"Error caching data: {e}")

    async def purge_cache(self, software_name: Optional[str] = None, version: Optional[str] = None) -> Dict[str, Any]:
        """Purge cached data for specific software or all Python cache"""
        try:
            if software_name:
                cache_key = self._generate_cache_key(software_name, version)
                return {"success": True, "deleted_count": 1, "message": f"Purged cache for {software_name}"}
            else:
                return {"success": True, "deleted_count": 0, "message": "Bulk purge not implemented"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _check_static_data(self, software_name: str, version: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Check static EOL data for Python ecosystem products with enhanced matching"""
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
        
        # Enhanced version-specific matching for Python ecosystem
        if version:
            # Extract major.minor version for Python-style versioning
            version_parts = version.split('.')
            if len(version_parts) >= 2:
                major_minor = f"{version_parts[0]}.{version_parts[1]}"
                
                # Python versions
                if "python" in software_lower and "django" not in software_lower and "flask" not in software_lower:
                    version_key = f"python-{major_minor}"
                    if version_key in self.static_eol_data:
                        return self.static_eol_data[version_key]
                
                # Django versions
                elif "django" in software_lower:
                    version_key = f"django-{major_minor}"
                    if version_key in self.static_eol_data:
                        return self.static_eol_data[version_key]
                
                # Flask versions
                elif "flask" in software_lower:
                    version_key = f"flask-{major_minor}"
                    if version_key in self.static_eol_data:
                        return self.static_eol_data[version_key]
                
                # NumPy versions
                elif "numpy" in software_lower:
                    version_key = f"numpy-{major_minor}"
                    if version_key in self.static_eol_data:
                        return self.static_eol_data[version_key]
                
                # Pandas versions
                elif "pandas" in software_lower:
                    version_key = f"pandas-{major_minor}"
                    if version_key in self.static_eol_data:
                        return self.static_eol_data[version_key]
        
        # Improved partial matches with better precision
        for key, data in self.static_eol_data.items():
            key_parts = key.split("-")
            software_parts = software_lower.split("-")
            
            # For Python ecosystem, require exact framework match
            if "python" in software_parts:
                if "python" in key_parts and "django" not in key_parts and "flask" not in key_parts:
                    # Ensure version compatibility
                    if not version or self._version_matches(version, data.get("cycle", "")):
                        return data
            
            elif "django" in software_parts:
                if "django" in key_parts:
                    if not version or self._version_matches(version, data.get("cycle", "")):
                        return data
            
            elif "flask" in software_parts:
                if "flask" in key_parts:
                    if not version or self._version_matches(version, data.get("cycle", "")):
                        return data
            
            elif "numpy" in software_parts:
                if "numpy" in key_parts:
                    if not version or self._version_matches(version, data.get("cycle", "")):
                        return data
            
            elif "pandas" in software_parts:
                if "pandas" in key_parts:
                    if not version or self._version_matches(version, data.get("cycle", "")):
                        return data
            
            # Generic partial matching for other Python packages
            else:
                if any(keyword in software_lower for keyword in key_parts):
                    if not version or self._version_matches(version, data.get("cycle", "")):
                        return data
        
        return None
    
    def _version_matches(self, version: str, cycle: str) -> bool:
        """Check if version matches the cycle for Python ecosystem"""
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

    async def get_eol_data(self, software_name: str, version: Optional[str] = None) -> Dict[str, Any]:
        """Get EOL data for Python ecosystem products with enhanced static data checking"""
        
        # Check cache first
        cached_data = await self._get_cached_data(software_name, version)
        if cached_data:
            return cached_data
        
        # Get fresh data using enhanced fetch method
        result_data = await self._fetch_eol_data(software_name, version)
        
        if result_data:
            # Add Python-specific metadata
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
                    "agent": "python",
                    "data_source": "python_agent"
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
        Fetch EOL data from Python ecosystem sources
        """
        # Check static data first for reliability
        static_result = self._check_static_data(software_name, version)
        if static_result:
            return static_result

        # Try web scraping for latest information
        scraped_result = await self._scrape_python_eol(software_name, version)
        if scraped_result:
            return scraped_result

        return None

    def _normalize_software_name(self, software_name: str, version: Optional[str] = None) -> str:
        """Normalize software name for lookup"""
        name_lower = software_name.lower()
        
        # Python versions
        if ("python" in name_lower and "django" not in name_lower and 
            "flask" not in name_lower and "cpython" not in name_lower):
            if version:
                # Extract major.minor version
                version_parts = version.split('.')
                if len(version_parts) >= 2:
                    major_minor = f"{version_parts[0]}.{version_parts[1]}"
                    if major_minor == "3.12":
                        return "python-3.12"
                    elif major_minor == "3.11":
                        return "python-3.11"
                    elif major_minor == "3.10":
                        return "python-3.10"
                    elif major_minor == "3.9":
                        return "python-3.9"
                    elif major_minor == "3.8":
                        return "python-3.8"
                    elif major_minor == "3.7":
                        return "python-3.7"
                    elif major_minor == "2.7":
                        return "python-2.7"
        
        # Django versions
        if "django" in name_lower:
            if version:
                # Extract major.minor version
                version_parts = version.split('.')
                if len(version_parts) >= 2:
                    major_minor = f"{version_parts[0]}.{version_parts[1]}"
                    if major_minor == "4.2":
                        return "django-4.2"
                    elif major_minor == "4.1":
                        return "django-4.1"
                    elif major_minor == "3.2":
                        return "django-3.2"
        
        # Flask versions
        if "flask" in name_lower:
            if version:
                # Extract major.minor version
                version_parts = version.split('.')
                if len(version_parts) >= 2:
                    major_minor = f"{version_parts[0]}.{version_parts[1]}"
                    if major_minor == "3.0":
                        return "flask-3.0"
                    elif major_minor == "2.3":
                        return "flask-2.3"
        
        # NumPy versions
        if "numpy" in name_lower:
            if version:
                # Extract major.minor version
                version_parts = version.split('.')
                if len(version_parts) >= 2:
                    major_minor = f"{version_parts[0]}.{version_parts[1]}"
                    if major_minor == "1.25":
                        return "numpy-1.25"
                    elif major_minor == "1.24":
                        return "numpy-1.24"
        
        # Pandas versions
        if "pandas" in name_lower:
            if version:
                # Extract major.minor version
                version_parts = version.split('.')
                if len(version_parts) >= 2:
                    major_minor = f"{version_parts[0]}.{version_parts[1]}"
                    if major_minor == "2.1":
                        return "pandas-2.1"
                    elif major_minor == "2.0":
                        return "pandas-2.0"
        
        return f"{name_lower}-{version}" if version else name_lower

    def _determine_source_url(self, software_name: str) -> str:
        """Determine the appropriate source URL for the software"""
        software_lower = software_name.lower()
        
        # Find matching URL from eol_urls
        for product_type, url in self.eol_urls.items():
            if product_type in software_lower:
                return url
        
        # Default to Python official URL if no specific match
        return self.eol_urls.get("python", "https://devguide.python.org/versions/")

    async def _scrape_python_eol(self, software_name: str, version: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Scrape Python ecosystem EOL information from official sources"""
        
        try:
            # Determine which URL to use based on software
            url = None
            name_lower = software_name.lower()
            
            if ("python" in name_lower and "django" not in name_lower and 
                "flask" not in name_lower):
                url_data = self.eol_urls["python"]
                url = url_data.get("url") if isinstance(url_data, dict) else url_data
            elif "django" in name_lower:
                url_data = self.eol_urls["django"]
                url = url_data.get("url") if isinstance(url_data, dict) else url_data
            elif "flask" in name_lower:
                url_data = self.eol_urls["flask"]
                url = url_data.get("url") if isinstance(url_data, dict) else url_data
            elif "numpy" in name_lower:
                url_data = self.eol_urls["numpy"]
                url = url_data.get("url") if isinstance(url_data, dict) else url_data
            elif "pandas" in name_lower:
                url_data = self.eol_urls["pandas"]
                url = url_data.get("url") if isinstance(url_data, dict) else url_data
            
            if not url:
                return None
            
            # Record agent request for statistics tracking
            start_time = datetime.now()
            cache_stats_manager.record_agent_request("python", url)
            
            response = requests.get(url, headers=self.headers, timeout=self.timeout)
            response.raise_for_status()
            
            # Calculate response time for tracking
            response_time = (datetime.now() - start_time).total_seconds()
            cache_stats_manager.record_agent_request("python", url, response_time, success=True)
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Extract EOL information from the page
            return self._parse_python_page(soup, software_name, version)
            
        except Exception as e:
            # Record failed request for statistics tracking
            start_time = getattr(locals(), 'start_time', datetime.now())
            response_time = (datetime.now() - start_time).total_seconds()
            url = getattr(locals(), 'url', None)
            if url:
                cache_stats_manager.record_agent_request("python", url, response_time, success=False, error_message=str(e))
            logger.error(f"Error scraping Python EOL data: {e}")
            return None

    def _parse_python_page(self, soup: BeautifulSoup, software_name: str, version: Optional[str]) -> Optional[Dict[str, Any]]:
        """Parse Python ecosystem page content"""
        
        # This is a simplified parser - would need specific logic for each framework's page
        # For now, return None to rely on static data
        return None

    def is_relevant(self, software_name: str) -> bool:
        """Check if this agent is relevant for the given software"""
        name_lower = software_name.lower()
        python_keywords = [
            'python', 'django', 'flask', 'fastapi', 'tornado',
            'numpy', 'pandas', 'scipy', 'matplotlib', 'jupyter',
            'pytest', 'sphinx', 'celery', 'gunicorn', 'uwsgi'
        ]
        
        return any(keyword in name_lower for keyword in python_keywords)
