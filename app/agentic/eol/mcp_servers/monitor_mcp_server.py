"""Azure Monitor Community Resources MCP Server

Provides MCP-compliant tools to discover, view, and deploy Azure Monitor Community
resources (workbooks, alerts, queries) from https://github.com/microsoft/AzureMonitorCommunity.

Uses HTML scraping to avoid GitHub API rate limits.
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import re
from dataclasses import asdict, dataclass
from typing import Annotated, Any, Dict, List, Optional
from urllib.parse import quote, urljoin, unquote

from mcp.server.fastmcp import Context, FastMCP
from mcp.types import TextContent

try:
    import httpx
    from bs4 import BeautifulSoup
except ImportError:
    httpx = None
    BeautifulSoup = None


_LOG_LEVEL_NAME = os.getenv("WORKBOOK_MCP_LOG_LEVEL", "INFO")
_resolved_log_level = logging.INFO

try:
    _resolved_log_level = getattr(logging, _LOG_LEVEL_NAME.upper())
except AttributeError:
    _resolved_log_level = logging.INFO

logging.basicConfig(level=_resolved_log_level, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# GitHub web interface configuration (for HTML scraping)
GITHUB_WEB_BASE = "https://github.com"
GITHUB_RAW_BASE = "https://raw.githubusercontent.com"
GITHUB_REPO_OWNER = "microsoft"
GITHUB_REPO_NAME = "AzureMonitorCommunity"
GITHUB_BRANCH = "master"

# Log scraping approach at startup
logger.info("Using HTML scraping for GitHub repository - no API token needed")

# Repository folder paths (for web URLs)
REPO_PATHS = {
    "workbooks": ["Azure%20Services", "Workbooks"],
    "alerts": ["Alerts"],
    "queries": ["Queries"],
}


@dataclass
class ResourceMetadata:
    """Metadata for an Azure Monitor Community resource (workbook, alert, query)."""

    name: str
    path: str
    category: str
    resource_type: str
    download_url: str
    size: int
    sha: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class WorkbookMetadata(ResourceMetadata):
    """Backwards compatibility alias."""
    pass


@dataclass
class ResourceContent:
    """Complete resource content with parameters."""

    metadata: ResourceMetadata
    content: Dict[str, Any]
    parameters: List[Dict[str, Any]]
    required_parameters: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "metadata": self.metadata.to_dict(),
            "content": self.content,
            "parameters": self.parameters,
            "required_parameters": self.required_parameters,
        }


@dataclass
class WorkbookContent(ResourceContent):
    """Backwards compatibility alias."""
    pass


_server = FastMCP(name="azure-monitor-community")
_http_client: Optional[httpx.AsyncClient] = None
_cached_metadata: Optional[Dict[str, Any]] = None
_cli_auth_lock = asyncio.Lock()
_cli_auth_completed = False

# Common prefixes/suffixes that users add but categories may omit
_STRIP_PREFIXES = ["azure", "microsoft", "ms"]


def _category_matches(keyword: str, category_name: str) -> bool:
    """Fuzzy match a user keyword against a category name.

    Checks (all case-insensitive):
    1. Exact substring either direction (keyword in category OR category in keyword)
    2. Keyword with common prefixes stripped (e.g. 'azure cosmos db' -> 'cosmos db')
    3. Individual significant words from keyword present in category
    """
    kw = keyword.lower().strip()
    cat = category_name.lower().strip()

    # 1. Bidirectional substring
    if kw in cat or cat in kw:
        return True

    # 2. Strip common prefixes and retry
    kw_words = kw.split()
    if kw_words and kw_words[0] in _STRIP_PREFIXES:
        stripped = " ".join(kw_words[1:])
        if stripped and (stripped in cat or cat in stripped):
            return True

    # 3. Word-level: all significant words (len>=3, not stop-words) must appear in category
    stop_words = {"the", "for", "and", "with", "from", "azure", "microsoft", "ms", "services", "service"}
    significant_words = [w for w in kw_words if len(w) >= 3 and w not in stop_words]
    if significant_words and all(w in cat for w in significant_words):
        return True

    return False


async def _load_cached_metadata() -> Optional[Dict[str, Any]]:
    """Load pre-generated metadata from static file."""
    global _cached_metadata
    if _cached_metadata is not None:
        return _cached_metadata
    
    try:
        # Try to find metadata file relative to this module
        import pathlib
        module_dir = pathlib.Path(__file__).parent.parent
        metadata_path = module_dir / "static" / "data" / "azure_monitor_community_metadata.json"
        
        if not metadata_path.exists():
            logger.warning(f"Metadata file not found at {metadata_path}, will use HTML scraping")
            return None
        
        with open(metadata_path, 'r', encoding='utf-8') as f:
            _cached_metadata = json.load(f)
        
        logger.info(f"Loaded metadata with {_cached_metadata.get('summary', {}).get('total_resources', 0)} resources from cache")
        return _cached_metadata
    except Exception as exc:
        logger.warning(f"Failed to load cached metadata: {exc}. Will use HTML scraping.")
        return None


async def _get_http_client() -> httpx.AsyncClient:
    """Get or create the HTTP client."""
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient(
            timeout=30.0,
            follow_redirects=True,
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
            }
        )
    return _http_client


async def _scrape_github_folder(folder_path: str) -> List[Dict[str, Any]]:
    """Scrape GitHub folder page to get list of files and subdirectories."""
    if httpx is None or BeautifulSoup is None:
        raise RuntimeError("httpx and beautifulsoup4 libraries required. Install with: pip install httpx beautifulsoup4")

    client = await _get_http_client()
    
    # Build GitHub web URL
    url = f"{GITHUB_WEB_BASE}/{GITHUB_REPO_OWNER}/{GITHUB_REPO_NAME}/tree/{GITHUB_BRANCH}/{folder_path}"
    logger.debug(f"Scraping GitHub folder: {url}")

    try:
        response = await client.get(url)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        items = []
        
        # Find all file/folder rows in the repository table
        # GitHub uses <div role="row"> with aria-labelledby attributes
        rows = soup.find_all('div', {'role': 'row', 'class': lambda x: x and 'react-directory-row' in str(x)})
        
        if not rows:
            # Try alternate selector for file table
            file_table = soup.find('div', {'aria-labelledby': 'folders-and-files'})
            if file_table:
                rows = file_table.find_all('div', {'role': 'row'})
        
        for row in rows:
            try:
                # Extract file/folder name and link
                link = row.find('a', {'class': lambda x: x and 'Link' in str(x)})
                if not link or not link.get('href'):
                    continue
                
                href = link.get('href', '')
                name_elem = link.find('span') or link
                name = name_elem.get_text(strip=True)
                
                if not name or name in ['.', '..']:
                    continue
                
                # Determine if it's a file or directory
                is_dir = '/tree/' in href
                is_file = '/blob/' in href
                
                if is_dir:
                    # Extract path from URL
                    path_match = re.search(r'/tree/[^/]+/(.+)', href)
                    if path_match:
                        items.append({
                            "name": name,
                            "path": unquote(path_match.group(1)),
                            "type": "dir"
                        })
                elif is_file:
                    # Extract path from URL
                    path_match = re.search(r'/blob/[^/]+/(.+)', href)
                    if path_match:
                        raw_path = unquote(path_match.group(1))
                        # Construct raw download URL
                        download_url = f"{GITHUB_RAW_BASE}/{GITHUB_REPO_OWNER}/{GITHUB_REPO_NAME}/{GITHUB_BRANCH}/{raw_path}"
                        items.append({
                            "name": name,
                            "path": raw_path,
                            "type": "file",
                            "download_url": download_url
                        })
            except Exception as e:
                logger.debug(f"Error parsing row: {e}")
                continue
        
        logger.debug(f"Found {len(items)} items in {folder_path}")
        return items
        
    except httpx.HTTPStatusError as exc:
        logger.error(f"HTTP error scraping GitHub folder {folder_path}: {exc.response.status_code}")
        return []
    except Exception as exc:
        logger.error(f"Error scraping GitHub folder {folder_path}: {exc}")
        return []


async def _list_categories(resource_type: str) -> List[str]:
    """List all categories for a resource type, with fuzzy matching support."""
    # Try to load from cached metadata first
    metadata = await _load_cached_metadata()
    
    if metadata and "categories" in metadata:
        # Use cached metadata for fast lookup
        all_categories = []
        
        resource_key_map = {
            "workbooks": "workbooks",
            "alerts": "alerts",
            "queries": "queries"
        }
        
        resource_key = resource_key_map.get(resource_type)
        if not resource_key:
            logger.warning(f"Unknown resource type: {resource_type}")
            return []
        
        for cat in metadata["categories"]:
            cat_data = cat.get(resource_key, {})
            if cat_data and cat_data.get("count", 0) > 0:
                category_name = cat["category"]
                all_categories.append({
                    "name": category_name,
                    "path": f"Azure%20Services/{quote(category_name, safe='')}",
                    "base_folder": "Azure Services",
                    "resource_count": cat_data.get("count", 0)
                })
        
        all_categories.sort(key=lambda x: x["name"])
        logger.info(f"Loaded {len(all_categories)} categories for {resource_type} from cached metadata")
        return all_categories
    
    # Fallback to HTML scraping if metadata not available
    logger.info(f"Using HTML scraping fallback for {resource_type} categories")
    paths = REPO_PATHS.get(resource_type, [])
    all_categories = []
    
    for base_path in paths:
        try:
            items = await _scrape_github_folder(base_path)
            for item in items:
                if item.get("type") == "dir":
                    category = item.get("name", "")
                    if category:
                        all_categories.append({
                            "name": category,
                            "path": f"{base_path}/{category}",
                            "base_folder": base_path.replace("%20", " ")
                        })
        except Exception as exc:
            logger.error("Failed to list categories in %s: %s", base_path, exc)
    
    return all_categories


async def _list_workbook_categories() -> List[str]:
    """List all workbook categories (backwards compatibility)."""
    categories = await _list_categories("workbooks")
    return sorted([c["name"] for c in categories])


async def _list_resources_in_category(category: str, resource_type: str, base_path: str) -> List[ResourceMetadata]:
    """List all resources in a specific category, using cached metadata or HTML scraping."""
    logger.info("_list_resources_in_category called with: resource_type=%s, category=%s, base_path=%s", 
                resource_type, category, base_path)
    
    # Try cached metadata first for faster lookups
    metadata = await _load_cached_metadata()
    if metadata and "categories" in metadata:
        # Find matching category (case-insensitive, fuzzy)
        category_lower = category.lower()
        matching_cat = None
        
        for cat in metadata["categories"]:
            cat_name = cat["category"]
            # Exact match (case-insensitive)
            if cat_name.lower() == category_lower:
                matching_cat = cat
                break
            # Partial match
            elif category_lower in cat_name.lower() or cat_name.lower() in category_lower:
                matching_cat = cat
                # Don't break, continue looking for exact match
        
        if matching_cat:
            resource_key_map = {
                "workbooks": "workbooks",
                "alerts": "alerts",
                "queries": "queries"
            }
            resource_key = resource_key_map.get(resource_type)
            if resource_key:
                resources_data = matching_cat.get(resource_key, {}).get("files", [])
                resources = []
                for res_data in resources_data:
                    resources.append(ResourceMetadata(
                        name=res_data.get("name", ""),
                        path=res_data.get("path", ""),
                        category=res_data.get("category", category),
                        resource_type=resource_type,
                        download_url=res_data.get("download_url", ""),
                        size=res_data.get("size", 0),
                        sha=res_data.get("sha", "")
                    ))
                logger.info(f"Found {len(resources)} resources for category '{matching_cat['category']}' from cached metadata")
                return resources
        else:
            logger.warning(f"Category '{category}' not found in cached metadata, trying HTML scraping fallback")
    
    # Fallback to HTML scraping
    logger.info(f"Using HTML scraping fallback for category: {category}")
    
    # For Azure Services categories, search in the resource type subfolder
    # E.g., Azure Services/Application Insights/Workbooks, /Alerts, /Queries
    if base_path.replace("%20", " ") == "Azure Services":
        resource_folder_map = {
            "workbooks": "Workbooks",
            "alerts": "Alerts",
            "queries": "Queries"
        }
        resource_folder = resource_folder_map.get(resource_type, "")
        if resource_folder:
            start_path = f"{base_path}/{quote(category, safe='')}/{resource_folder}"
        else:
            start_path = f"{base_path}/{quote(category, safe='')}"
    else:
        start_path = f"{base_path}/{quote(category, safe='')}"
    
    logger.debug("Starting search path: %s", start_path)
    
    # Determine file extension based on resource type
    extensions = {
        "workbooks": [".workbook", ".md"],
        "alerts": [".json", ".yaml", ".yml", ".md"],
        "queries": [".kql", ".kusto", ".json", ".md"]
    }
    valid_extensions = extensions.get(resource_type, [])
    
    resources = []
    
    async def explore_recursively(path_to_explore: str, current_depth: int = 0, max_depth: int = 3):
        """Recursively explore folders to find resource files using HTML scraping."""
        if current_depth >= max_depth:
            return
        
        try:
            logger.debug("Exploring (depth %d): %s", current_depth, path_to_explore)
            
            items = await _scrape_github_folder(path_to_explore)
            
            for item in items:
                if item.get("type") == "file":
                    name = item.get("name", "")
                    
                    if any(name.endswith(ext) for ext in valid_extensions):
                        resources.append(
                            ResourceMetadata(
                                name=name,
                                path=item.get("path", ""),
                                category=category,
                                resource_type=resource_type,
                                download_url=item.get("download_url", ""),
                                size=0,  # Size not available from HTML scraping
                                sha="",  # SHA not available from HTML scraping
                            )
                        )
                        logger.debug("  Found file: %s", name)
                elif item.get("type") == "dir":
                    # Recursively explore subdirectories
                    subdir_path = item.get("path", "")
                    logger.debug("  Recursing into: %s", subdir_path)
                    await explore_recursively(subdir_path, current_depth + 1, max_depth)
        except Exception as exc:
            logger.debug("Error exploring %s: %s", path_to_explore, exc)
    
    try:
        # Start recursive exploration from the start path
        await explore_recursively(start_path)
        
        logger.info("Found %d %s in category %s (after recursive search)", len(resources), resource_type, category)
        return resources
    except Exception as exc:
        logger.error("Failed to list %s in category %s (base_path: %s): %s", 
                    resource_type, category, base_path, exc, exc_info=True)
        return []


async def _list_workbooks_in_category(category: str) -> List[WorkbookMetadata]:
    """List all workbooks in a specific category (backwards compatibility)."""
    # Try all workbook paths
    for base_path in REPO_PATHS["workbooks"]:
        resources = await _list_resources_in_category(category, "workbooks", base_path)
        if resources:
            return resources
    return []


async def _download_content(download_url: str) -> str:
    """Download content from GitHub."""
    if httpx is None:
        raise RuntimeError("httpx library not available")

    client = await _get_http_client()
    try:
        response = await client.get(download_url)
        response.raise_for_status()
        return response.text
    except Exception as exc:
        logger.error("Failed to download content: %s", exc)
        raise RuntimeError(f"Failed to download content: {exc}") from exc


async def _download_workbook_content(download_url: str) -> str:
    """Download workbook content from GitHub (backwards compatibility)."""
    return await _download_content(download_url)


def _extract_workbook_parameters(content: Dict[str, Any]) -> tuple[List[Dict[str, Any]], List[str]]:
    """Extract parameters from workbook content."""
    parameters = []
    required_params = []

    # Workbooks store parameters in the 'parameters' section
    params_section = content.get("parameters", {})
    if isinstance(params_section, dict):
        for param_name, param_config in params_section.items():
            param_info = {
                "name": param_name,
                "type": param_config.get("type", "unknown"),
                "default_value": param_config.get("value"),
                "description": param_config.get("description", ""),
            }
            parameters.append(param_info)

            # Check if required (no default value or explicitly marked)
            if param_config.get("value") is None or param_config.get("isRequired", False):
                required_params.append(param_name)

    # Also check for common Azure parameter patterns in query items
    items = content.get("items", [])
    if isinstance(items, list):
        for item in items:
            if isinstance(item, dict):
                query = item.get("content", {}).get("query", "")
                if isinstance(query, str):
                    # Find parameter references like {subscription}, {resourceGroup}, etc.
                    param_refs = re.findall(r'\{([^}]+)\}', query)
                    for ref in param_refs:
                        if not any(p["name"] == ref for p in parameters):
                            parameters.append({
                                "name": ref,
                                "type": "string",
                                "default_value": None,
                                "description": f"Parameter used in workbook query: {ref}",
                            })
                            required_params.append(ref)

    return parameters, list(set(required_params))


@_server.tool(
    name="get_service_monitor_resources",
    description=(
        "Find ALL Azure Monitor resources (workbooks, alerts, queries) for a given Azure service in ONE call. "
        "Returns a complete list of available resources with names, types, download URLs, and deployment method. "
        "Use this as the PRIMARY tool when a user asks 'show monitor resources for <service>'. "
        "After results, the user can pick a resource to deploy — workbooks via deploy_workbook, "
        "queries via get_resource_content then CLI saved-search, alerts via get_resource_content then CLI scheduled-query."
    ),
)
async def get_service_monitor_resources(
    context: Context,
    keyword: Annotated[str, "Azure service name or keyword to search for (e.g., 'virtual machines', 'container apps', 'storage')."],
) -> list[TextContent]:
    """Find all monitor resources for a service in one call."""
    try:
        metadata = await _load_cached_metadata()
        if not metadata or "categories" not in metadata:
            return [TextContent(type="text", text=json.dumps({"success": False, "error": "Metadata not available"}, indent=2))]

        keyword_lower = keyword.lower()
        all_resources = []
        matched_categories = []

        for cat in metadata["categories"]:
            cat_name = cat["category"]
            if _category_matches(keyword_lower, cat_name):
                matched_categories.append(cat_name)
                for rt in ["workbooks", "alerts", "queries"]:
                    res_data = cat.get(rt, {})
                    files = res_data.get("files", [])
                    deploy_method = {
                        "workbooks": "deploy_workbook tool",
                        "alerts": "deploy_alert tool",
                        "queries": "deploy_query tool",
                    }
                    for f in files:
                        all_resources.append({
                            "name": f.get("name", ""),
                            "resource_type": rt,
                            "category": cat_name,
                            "download_url": f.get("download_url", ""),
                            "deploy_status": "✅ Deployable",
                            "deploy_method": deploy_method[rt],
                        })

        result = {
            "success": True,
            "keyword": keyword,
            "matched_categories": matched_categories,
            "resources": all_resources,
            "total_count": len(all_resources),
            "by_type": {
                "workbooks": len([r for r in all_resources if r["resource_type"] == "workbooks"]),
                "alerts": len([r for r in all_resources if r["resource_type"] == "alerts"]),
                "queries": len([r for r in all_resources if r["resource_type"] == "queries"]),
            },
            "deployment_instructions": {
                "workbooks": "Use deploy_workbook tool with the download_url, subscription_id, resource_group, workbook_name, and location.",
                "queries": "Use deploy_query tool with download_url, resource_group, workspace_name, query_name, and category. The tool handles KQL formatting automatically.",
                "alerts": "Use deploy_alert tool with download_url, resource_group, scopes (Log Analytics resource ID), alert_name, severity, and threshold. The tool handles KQL extraction automatically.",
            },
        }
        return [TextContent(type="text", text=json.dumps(result, indent=2))]
    except Exception as exc:
        logger.error("Error in get_service_monitor_resources: %s", exc, exc_info=True)
        return [TextContent(type="text", text=json.dumps({"success": False, "error": str(exc)}, indent=2))]


@_server.tool(
    name="list_resource_types",
    description=(
        "List the 3 resource types available in the Azure Monitor Community repository: "
        "workbooks, alerts, and queries. Returns type names and descriptions only — "
        "NOT specific resources. To get actual resources for a service, "
        "use get_service_monitor_resources instead."
    ),
)
async def list_resource_types(context: Context) -> list[TextContent]:
    """List available resource types."""
    result = {
        "success": True,
        "resource_types": list(REPO_PATHS.keys()),
        "descriptions": {
            "workbooks": "Azure Monitor Workbooks for visualization and monitoring",
            "alerts": "Alert rule templates and configurations",
            "queries": "KQL (Kusto Query Language) queries for Azure Monitor"
        }
    }
    return [TextContent(type="text", text=json.dumps(result, indent=2))]


@_server.tool(
    name="search_categories",
    description=(
        "Search for Azure service categories by keyword. Returns matching categories "
        "with per-type resource counts (how many workbooks, alerts, queries exist). "
        "Use this FIRST when the user asks about monitor resources for a service "
        "(e.g., search 'container apps' to find the category and see what's available). "
        "Follow up with list_resources to get the actual resource names."
    ),
)
async def search_categories(
    context: Context,
    keyword: Annotated[str, "Search keyword or partial category name (case-insensitive)"],
    resource_type: Annotated[
        Optional[str],
        "Optional resource type filter: 'workbooks', 'alerts', or 'queries'. If not specified, searches all."
    ] = None,
) -> list[TextContent]:
    """Search for categories by keyword."""
    try:
        metadata = await _load_cached_metadata()
        
        if not metadata or "categories" not in metadata:
            # Fallback: list all categories and filter
            all_results = []
            resource_types = [resource_type] if resource_type else ["workbooks", "alerts", "queries"]
            
            for rt in resource_types:
                categories = await _list_categories(rt)
                for cat in categories:
                    if _category_matches(keyword.lower(), cat["name"]):
                        all_results.append({
                            "category": cat["name"],
                            "resource_type": rt,
                            "path": cat.get("path", ""),
                            "base_folder": cat.get("base_folder", "")
                        })
            
            result = {
                "success": True,
                "keyword": keyword,
                "matches": all_results,
                "count": len(all_results)
            }
            return [TextContent(type="text", text=json.dumps(result, indent=2))]
        
        # Use cached metadata for faster search
        keyword_lower = keyword.lower()
        matches = []
        
        for cat in metadata["categories"]:
            cat_name = cat["category"]
            if _category_matches(keyword_lower, cat_name):
                # Check which resource types have resources for this category
                cat_resources = []
                
                if resource_type:
                    # Filter by specific resource type
                    res_data = cat.get(resource_type, {})
                    if res_data and res_data.get("count", 0) > 0:
                        cat_resources.append({
                            "resource_type": resource_type,
                            "count": res_data.get("count", 0)
                        })
                else:
                    # Include all resource types
                    for rt in ["workbooks", "alerts", "queries"]:
                        res_data = cat.get(rt, {})
                        if res_data and res_data.get("count", 0) > 0:
                            cat_resources.append({
                                "resource_type": rt,
                                "count": res_data.get("count", 0)
                            })
                
                if cat_resources:
                    matches.append({
                        "category": cat_name,
                        "resources": cat_resources,
                        "total_resources": sum(r["count"] for r in cat_resources)
                    })
        
        matches.sort(key=lambda x: (-x["total_resources"], x["category"]))
        
        result = {
            "success": True,
            "keyword": keyword,
            "matches": matches,
            "count": len(matches),
            "hint": f"Use list_resources with the exact category name to see available resources"
        }
        return [TextContent(type="text", text=json.dumps(result, indent=2))]
        
    except Exception as exc:
        logger.error("Error searching categories: %s", exc, exc_info=True)
        result = {
            "success": False,
            "error": str(exc),
            "keyword": keyword
        }
        return [TextContent(type="text", text=json.dumps(result, indent=2))]


@_server.tool(
    name="list_categories",
    description=(
        "List ALL categories for a resource type (workbooks, alerts, or queries). "
        "Returns category names with folder paths and resource counts. "
        "Use search_categories instead if you already know the service name."
    ),
)
async def list_categories(
    context: Context,
    resource_type: Annotated[
        str,
        "The resource type: 'workbooks', 'alerts', or 'queries'. Use list_resource_types to see available types.",
    ],
) -> list[TextContent]:
    """List categories for a resource type."""
    categories = await _list_categories(resource_type)
    result = {
        "success": True,
        "resource_type": resource_type,
        "categories": categories,
        "count": len(categories),
    }
    return [TextContent(type="text", text=json.dumps(result, indent=2))]


@_server.tool(
    name="list_resources",
    description=(
        "List specific resources (workbooks, alerts, or queries) in a category. "
        "Returns resource names, paths, download URLs, and metadata. "
        "Call this for EACH resource type to build a complete list. "
        "Use the download_url from results with get_resource_content or deploy_workbook."
    ),
)
async def list_resources(
    context: Context,
    resource_type: Annotated[str, "The resource type: 'workbooks', 'alerts', or 'queries'."],
    category: Annotated[str, "The category name (e.g., 'Virtual machines', 'Storage Accounts')."],
    base_path: Annotated[Optional[str], "The base folder path. Defaults to 'Azure Services' if not provided."] = None,
) -> list[TextContent]:
    """List resources in a category."""
    if not base_path:
        base_path = "Azure%20Services"
    logger.info("list_resources tool called with: resource_type=%s, category=%s, base_path=%s", 
                resource_type, category, base_path)
    
    try:
        resources = await _list_resources_in_category(category, resource_type, base_path)
        result = {
            "success": True,
            "resource_type": resource_type,
            "category": category,
            "resources": [r.to_dict() for r in resources],
            "count": len(resources),
        }
        logger.info("list_resources tool returning %d resources", len(resources))
        return [TextContent(type="text", text=json.dumps(result, indent=2))]
    except Exception as exc:
        logger.error("Error in list_resources tool: %s", exc, exc_info=True)
        result = {
            "success": False,
            "error": str(exc),
            "resource_type": resource_type,
            "category": category,
            "base_path": base_path,
        }
        return [TextContent(type="text", text=json.dumps(result, indent=2))]


@_server.tool(
    name="list_workbook_categories",
    description=(
        "DEPRECATED — use list_categories(resource_type='workbooks') instead. "
        "Lists workbook category names only, without resource counts or paths."
    ),
)
async def list_workbook_categories(context: Context) -> list[TextContent]:
    """List all workbook categories."""
    categories = await _list_workbook_categories()
    result = {
        "success": True,
        "categories": categories,
        "count": len(categories),
    }
    return [TextContent(type="text", text=json.dumps(result, indent=2))]


@_server.tool(
    name="list_workbooks",
    description=(
        "DEPRECATED — use list_resources(resource_type='workbooks', category=...) instead. "
        "Lists workbooks in a category but only supports workbooks, not alerts or queries."
    ),
)
async def list_workbooks(
    context: Context,
    category: Annotated[
        str,
        "The Azure service category name (e.g., 'Virtual Machines', 'Storage Accounts'). "
        "Use list_workbook_categories to get available categories.",
    ],
) -> list[TextContent]:
    """List workbooks in a category."""
    workbooks = await _list_workbooks_in_category(category)
    result = {
        "success": True,
        "category": category,
        "workbooks": [wb.to_dict() for wb in workbooks],
        "count": len(workbooks),
    }
    return [TextContent(type="text", text=json.dumps(result, indent=2))]


@_server.tool(
    name="get_resource_content",
    description=(
        "Download and analyze any resource (workbook, alert, or query) to view its complete content. "
        "For workbooks: extracts parameters and requirements. "
        "For alerts: shows alert rule configuration. "
        "For queries: displays KQL query text."
    ),
)
async def get_resource_content(
    context: Context,
    download_url: Annotated[str, "The download URL of the resource from list_resources or list_workbooks."],
    resource_type: Annotated[str, "The resource type: 'workbooks', 'alerts', or 'queries'."],
) -> list[TextContent]:
    """Get detailed resource content."""
    try:
        content_str = await _download_content(download_url)
        
        # Try to parse as JSON
        try:
            content = json.loads(content_str)
        except json.JSONDecodeError:
            # For KQL queries or other text content
            result = {
                "success": True,
                "resource_type": resource_type,
                "content": content_str,
                "is_text": True,
            }
            return [TextContent(type="text", text=json.dumps(result, indent=2))]

        # Extract parameters for workbooks
        parameters = []
        required_params = []
        if resource_type == "workbooks":
            parameters, required_params = _extract_workbook_parameters(content)

        result = {
            "success": True,
            "resource_type": resource_type,
            "content": content,
            "parameters": parameters,
            "required_parameters": required_params,
            "parameter_count": len(parameters),
            "required_count": len(required_params),
        }
        return [TextContent(type="text", text=json.dumps(result, indent=2))]
    except Exception as exc:
        logger.error("Failed to get resource content: %s", exc)
        result = {
            "success": False,
            "error": str(exc),
        }
        return [TextContent(type="text", text=json.dumps(result, indent=2))]


@_server.tool(
    name="get_workbook_details",
    description=(
        "DEPRECATED — use get_resource_content(download_url, resource_type='workbooks') instead. "
        "Downloads a workbook and extracts parameters. Identical to get_resource_content for workbooks."
    ),
)
async def get_workbook_details(
    context: Context,
    download_url: Annotated[
        str,
        "The download URL of the workbook from list_workbooks result.",
    ],
) -> list[TextContent]:
    """Get detailed workbook information including parameters."""
    return await get_resource_content(context, download_url, "workbooks")


@_server.tool(
    name="deploy_workbook",
    description=(
        "Deploy an Azure Monitor Community workbook to Azure. "
        "Creates the workbook as a microsoft.insights/workbooks resource via ARM template. "
        "Requires: download_url (from list_resources), subscription_id, resource_group, "
        "workbook_name, location, and optional parameter values. "
        "This is the ONLY way to deploy workbooks — do NOT use azure_cli_execute_command."
    ),
)
async def deploy_workbook(
    context: Context,
    download_url: Annotated[
        str,
        "The download URL of the workbook from list_resources or get_resource_content.",
    ],
    subscription_id: Annotated[str, "Azure subscription ID where the workbook will be deployed. REQUIRED — cannot be empty."],
    resource_group: Annotated[str, "Resource group name for the workbook. REQUIRED — cannot be empty."],
    workbook_name: Annotated[str, "Name for the deployed workbook. REQUIRED — cannot be empty."],
    location: Annotated[str, "Azure region (e.g., 'eastus', 'westeurope'). REQUIRED — cannot be empty."],
    parameters: Annotated[
        Optional[str],
        "JSON string of parameter values as key-value pairs. Required parameters must be included.",
    ] = None,
) -> list[TextContent]:
    """Deploy a workbook using Azure CLI."""
    try:
        # Validate required parameters
        missing = []
        if not subscription_id or not subscription_id.strip():
            missing.append("subscription_id")
        if not resource_group or not resource_group.strip():
            missing.append("resource_group")
        if not workbook_name or not workbook_name.strip():
            missing.append("workbook_name")
        if not location or not location.strip():
            missing.append("location")
        if not download_url or not download_url.strip():
            missing.append("download_url")
        if missing:
            return [TextContent(type="text", text=json.dumps({
                "success": False,
                "error": f"Missing required parameters: {', '.join(missing)}. "
                          "Ask the user to provide these values before deploying.",
                "missing_params": missing,
            }, indent=2))]

        # Fetch workbook content from download URL
        logger.info(f"Fetching workbook content from: {download_url}")
        workbook_content_str = await _download_content(download_url)
        
        # Parse and validate workbook content
        content = json.loads(workbook_content_str)

        # Parse parameter values
        param_values = {}
        if parameters:
            param_values = json.loads(parameters) if isinstance(parameters, str) else parameters

        # Update workbook content with parameter values
        if "parameters" in content and isinstance(content["parameters"], dict):
            for param_name, value in param_values.items():
                if param_name in content["parameters"]:
                    content["parameters"][param_name]["value"] = value

        # Create deployment template
        template = {
            "$schema": "https://schema.management.azure.com/schemas/2019-04-01/deploymentTemplate.json#",
            "contentVersion": "1.0.0.0",
            "parameters": {},
            "resources": [
                {
                    "type": "microsoft.insights/workbooks",
                    "name": workbook_name,
                    "location": location,
                    "apiVersion": "2021-03-08",
                    "kind": "shared",
                    "properties": {
                        "displayName": workbook_name,
                        "serializedData": json.dumps(content),
                        "version": "1.0",
                        "sourceId": f"/subscriptions/{subscription_id}/resourceGroups/{resource_group}",
                        "category": "workbook",
                    },
                }
            ],
        }

        # Use Azure CLI to deploy
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as tf:
            json.dump(template, tf)
            template_file = tf.name

        try:
            # Ensure Azure CLI is authenticated
            await _ensure_cli_auth()
            
            # Build Azure CLI command
            cmd = [
                "az", "deployment", "group", "create",
                "--subscription", subscription_id,
                "--resource-group", resource_group,
                "--template-file", template_file,
                "--name", f"deploy-workbook-{workbook_name}",
            ]

            # Execute deployment
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()

            if proc.returncode == 0:
                result = {
                    "success": True,
                    "message": "Workbook deployed successfully",
                    "workbook_name": workbook_name,
                    "resource_group": resource_group,
                    "location": location,
                    "output": stdout.decode("utf-8") if stdout else "",
                }
            else:
                result = {
                    "success": False,
                    "error": f"Deployment failed with exit code {proc.returncode}",
                    "stderr": stderr.decode("utf-8") if stderr else "",
                    "stdout": stdout.decode("utf-8") if stdout else "",
                }
        finally:
            os.unlink(template_file)

        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    except Exception as exc:
        logger.error("Failed to deploy workbook: %s", exc)
        result = {
            "success": False,
            "error": str(exc),
        }
        return [TextContent(type="text", text=json.dumps(result, indent=2))]


async def _ensure_cli_auth() -> None:
    """Authenticate Azure CLI with service principal if env vars are set.

    Mirrors the robust pattern from azure_cli_executor_server:
    - Uses a lock + flag so login only happens once across all deploy calls
    - Sets up HOME / AZURE_CONFIG_DIR for containerised environments
    - Tries both env-var naming conventions (AZURE_SP_CLIENT_ID and AZURE_CLIENT_ID)
    - Sets the active subscription if AZURE_SUBSCRIPTION_ID is set
    """
    global _cli_auth_completed
    from pathlib import Path

    if _cli_auth_completed:
        return

    async with _cli_auth_lock:
        if _cli_auth_completed:
            return

        # Ensure HOME is valid (containers sometimes lack it)
        home_dir = os.environ.get("HOME")
        if not home_dir or not os.path.isdir(home_dir):
            home_dir = "/tmp"
            os.environ["HOME"] = home_dir
            logger.warning("HOME not set or inaccessible; defaulting to %s", home_dir)
        Path(home_dir).mkdir(parents=True, exist_ok=True)

        config_dir = os.environ.get("AZURE_CONFIG_DIR")
        if not config_dir:
            config_dir = os.path.join(home_dir, ".azure")
            os.environ["AZURE_CONFIG_DIR"] = config_dir
        Path(config_dir).mkdir(parents=True, exist_ok=True)

        # Try both env-var naming conventions
        sp_id = os.getenv("AZURE_SP_CLIENT_ID") or os.getenv("AZURE_CLIENT_ID")
        sp_secret = os.getenv("AZURE_SP_CLIENT_SECRET") or os.getenv("AZURE_CLIENT_SECRET")
        tenant_id = os.getenv("AZURE_TENANT_ID")

        if not all([sp_id, sp_secret, tenant_id]):
            logger.warning(
                "Service principal env vars not set (need AZURE_SP_CLIENT_ID/AZURE_CLIENT_ID, "
                "AZURE_SP_CLIENT_SECRET/AZURE_CLIENT_SECRET, AZURE_TENANT_ID). "
                "Deploy commands will rely on existing az login session."
            )
            _cli_auth_completed = True  # Don't retry every call
            return

        logger.info("Authenticating Azure CLI with service principal (client %s…)...", sp_id[:8] if sp_id else "?")
        login_proc = await asyncio.create_subprocess_exec(
            "az", "login", "--service-principal",
            "-u", sp_id, "-p", sp_secret, "--tenant", tenant_id,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await login_proc.communicate()

        if login_proc.returncode != 0:
            err_msg = (stderr or stdout or b"").decode("utf-8", errors="replace")
            logger.error("Azure CLI login failed (exit %d): %s", login_proc.returncode, err_msg[:300])
            raise RuntimeError(f"az login failed: {err_msg[:300]}")

        # Set active subscription if configured
        sub_id = os.getenv("AZURE_SUBSCRIPTION_ID")
        if sub_id:
            logger.info("Setting active Azure subscription %s", sub_id)
            await asyncio.create_subprocess_exec(
                "az", "account", "set", "--subscription", sub_id,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )

        logger.info("Azure CLI authentication completed successfully for monitor deploy tools")
        _cli_auth_completed = True


@_server.tool(
    name="deploy_query",
    description=(
        "Deploy a KQL query from Azure Monitor Community as a saved search in a Log Analytics workspace. "
        "Downloads the .kql file, cleans up formatting (removes problematic newlines), and deploys via "
        "'az monitor log-analytics workspace saved-search create'. "
        "REQUIRED: resource_group and workspace_name MUST be non-empty — ask the user if not known. "
        "To discover workspaces, use azure_cli_execute_command with 'az monitor log-analytics workspace list'. "
        "This is the correct way to deploy queries — do NOT construct CLI commands manually."
    ),
)
async def deploy_query(
    context: Context,
    download_url: Annotated[str, "The download URL of the .kql query from list_resources or get_service_monitor_resources."],
    resource_group: Annotated[str, "Azure resource group containing the Log Analytics workspace. REQUIRED — cannot be empty."],
    workspace_name: Annotated[str, "Name of the Log Analytics workspace. REQUIRED — cannot be empty. Use 'az monitor log-analytics workspace list' to discover."],
    query_name: Annotated[str, "Display name for the saved search (e.g., 'Container Apps Console Logs')."],
    category: Annotated[str, "Category for the saved search (e.g., 'Container Apps', 'Virtual Machines')."] = "General",
) -> list[TextContent]:
    """Deploy a KQL query as a saved search."""
    try:
        # Validate required parameters
        missing = []
        if not resource_group or not resource_group.strip():
            missing.append("resource_group")
        if not workspace_name or not workspace_name.strip():
            missing.append("workspace_name")
        if not download_url or not download_url.strip():
            missing.append("download_url")
        if missing:
            return [TextContent(type="text", text=json.dumps({
                "success": False,
                "error": f"Missing required parameters: {', '.join(missing)}. "
                          "Ask the user to provide these values. "
                          "To list available workspaces, run: az monitor log-analytics workspace list --output table",
                "missing_params": missing,
            }, indent=2))]

        # Download the KQL content
        kql_content = await _download_content(download_url)

        # Clean the KQL: strip comment header lines (// ...), collapse newlines to single spaces
        lines = kql_content.strip().splitlines()
        # Separate comment lines from query lines
        query_lines = []
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("//"):
                continue  # Skip comment lines
            query_lines.append(stripped)

        # Join remaining lines with single space (KQL is whitespace-insensitive for newlines)
        clean_kql = " ".join(line for line in query_lines if line)

        if not clean_kql:
            return [TextContent(type="text", text=json.dumps({
                "success": False, "error": "Downloaded KQL file is empty or contains only comments."
            }, indent=2))]

        logger.info("Deploying query '%s' (%d chars) to workspace '%s'", query_name, len(clean_kql), workspace_name)

        await _ensure_cli_auth()

        # Sanitize the saved-search name for CLI (alphanumeric + hyphens)
        safe_name = re.sub(r'[^a-zA-Z0-9-]', '-', query_name).strip('-').lower()

        cmd = [
            "az", "monitor", "log-analytics", "workspace", "saved-search", "create",
            "--resource-group", resource_group,
            "--workspace-name", workspace_name,
            "--name", safe_name,
            "--category", category,
            "--display-name", query_name,
            "--saved-query", clean_kql,
        ]

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()

        if proc.returncode == 0:
            result = {
                "success": True,
                "message": f"Query '{query_name}' deployed as saved search",
                "query_name": query_name,
                "saved_search_name": safe_name,
                "workspace_name": workspace_name,
                "resource_group": resource_group,
                "category": category,
                "output": stdout.decode("utf-8")[:500] if stdout else "",
            }
        else:
            result = {
                "success": False,
                "error": f"Deployment failed (exit code {proc.returncode})",
                "stderr": stderr.decode("utf-8")[:500] if stderr else "",
                "stdout": stdout.decode("utf-8")[:500] if stdout else "",
            }

        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    except Exception as exc:
        logger.error("Failed to deploy query: %s", exc, exc_info=True)
        return [TextContent(type="text", text=json.dumps({"success": False, "error": str(exc)}, indent=2))]


@_server.tool(
    name="deploy_alert",
    description=(
        "Deploy a KQL alert rule from Azure Monitor Community as a scheduled query alert in Azure Monitor. "
        "Downloads the alert template, extracts the KQL query, and deploys via "
        "'az monitor scheduled-query create'. "
        "REQUIRED: resource_group and scopes MUST be non-empty — ask the user if not known. "
        "scopes is the full Log Analytics workspace resource ID (e.g., /subscriptions/.../resourceGroups/.../providers/Microsoft.OperationalInsights/workspaces/...). "
        "This is the correct way to deploy alerts — do NOT construct CLI commands manually."
    ),
)
async def deploy_alert(
    context: Context,
    download_url: Annotated[str, "The download URL of the alert from list_resources or get_service_monitor_resources."],
    resource_group: Annotated[str, "Azure resource group for the alert rule. REQUIRED — cannot be empty."],
    scopes: Annotated[str, "Full resource ID of the Log Analytics workspace to scope the alert to. REQUIRED — cannot be empty."],
    alert_name: Annotated[str, "Display name for the alert rule."],
    severity: Annotated[int, "Alert severity: 0=Critical, 1=Error, 2=Warning, 3=Informational, 4=Verbose."] = 2,
    threshold: Annotated[int, "Threshold count that triggers the alert."] = 0,
    evaluation_frequency: Annotated[str, "How often the query runs (e.g., '5m', '15m', '1h')."] = "5m",
    window_size: Annotated[str, "Time window for each evaluation (e.g., '5m', '15m', '1h')."] = "5m",
    action_groups: Annotated[Optional[str], "Resource ID of the action group to notify. Optional."] = None,
) -> list[TextContent]:
    """Deploy a KQL alert as a scheduled query rule."""
    try:
        # Validate required parameters
        missing = []
        if not resource_group or not resource_group.strip():
            missing.append("resource_group")
        if not scopes or not scopes.strip():
            missing.append("scopes (Log Analytics workspace resource ID)")
        if not download_url or not download_url.strip():
            missing.append("download_url")
        if missing:
            return [TextContent(type="text", text=json.dumps({
                "success": False,
                "error": f"Missing required parameters: {', '.join(missing)}. "
                          "Ask the user to provide these values. "
                          "To list available workspaces and get resource IDs, run: "
                          "az monitor log-analytics workspace list --query '[].{name:name, id:id, resourceGroup:resourceGroup}' --output table",
                "missing_params": missing,
            }, indent=2))]

        # Download the alert content
        content_str = await _download_content(download_url)

        # Try to extract KQL from JSON alert template
        kql_query = content_str.strip()
        try:
            content = json.loads(content_str)
            # Common alert template patterns
            kql_query = (
                content.get("query")
                or content.get("properties", {}).get("query")
                or content.get("savedSearchQuery")
                or content_str.strip()
            )
        except json.JSONDecodeError:
            pass  # Treat as raw KQL

        # Clean KQL: strip comments, collapse newlines
        lines = kql_query.strip().splitlines()
        query_lines = [line.strip() for line in lines if line.strip() and not line.strip().startswith("//")]
        clean_kql = " ".join(query_lines)

        if not clean_kql:
            return [TextContent(type="text", text=json.dumps({
                "success": False, "error": "Could not extract KQL query from alert template."
            }, indent=2))]

        logger.info("Deploying alert '%s' (%d chars KQL) scoped to '%s'", alert_name, len(clean_kql), scopes)

        await _ensure_cli_auth()

        cmd = [
            "az", "monitor", "scheduled-query", "create",
            "--resource-group", resource_group,
            "--name", alert_name,
            "--scopes", scopes,
            "--condition", f"count '{clean_kql}' > {threshold}",
            "--severity", str(severity),
            "--evaluation-frequency", evaluation_frequency,
            "--window-size", window_size,
        ]
        if action_groups:
            cmd.extend(["--action-groups", action_groups])

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()

        if proc.returncode == 0:
            result = {
                "success": True,
                "message": f"Alert rule '{alert_name}' deployed successfully",
                "alert_name": alert_name,
                "resource_group": resource_group,
                "severity": severity,
                "output": stdout.decode("utf-8")[:500] if stdout else "",
            }
        else:
            result = {
                "success": False,
                "error": f"Deployment failed (exit code {proc.returncode})",
                "stderr": stderr.decode("utf-8")[:500] if stderr else "",
                "stdout": stdout.decode("utf-8")[:500] if stdout else "",
            }

        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    except Exception as exc:
        logger.error("Failed to deploy alert: %s", exc, exc_info=True)
        return [TextContent(type="text", text=json.dumps({"success": False, "error": str(exc)}, indent=2))]


def main() -> None:
    """Entry point for the MCP server."""
    if httpx is None:
        logger.error("httpx library not available. Install with: pip install httpx")
        return

    tool_registry = getattr(_server, "_tools", {})
    if isinstance(tool_registry, dict):
        tool_names = sorted(tool_registry.keys())
    else:
        tool_names = sorted(getattr(tool, "name", str(tool)) for tool in tool_registry)

    logger.info(
        "Starting Azure Monitor Community MCP server with %d registered tool(s): %s",
        len(tool_names),
        ", ".join(tool_names) if tool_names else "(none)",
    )

    try:
        _server.run()
    except KeyboardInterrupt:
        pass
    finally:
        if _http_client:
            asyncio.run(_http_client.aclose())
        logger.info("Azure Monitor Community MCP server stopped")


if __name__ == "__main__":
    main()
