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
    name="list_resource_types",
    description=(
        "List all available resource types in the Azure Monitor Community repository. "
        "Returns workbooks, alerts, and queries."
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
        "Search for Azure service categories by keyword or partial name match. "
        "Use this when you need to find the exact category name for a service. "
        "For example, searching for 'gateway' will find 'Application gateways', 'VPN Gateway', etc."
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
                    if keyword.lower() in cat["name"].lower():
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
            if keyword_lower in cat_name.lower():
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
        "List all available categories for a specific resource type (workbooks, alerts, or queries). "
        "Returns category names with their folder paths. Use search_categories if you need to find a category by keyword."
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
        "List all resources (workbooks, alerts, or queries) in a specific category. "
        "Returns resource metadata including name, path, size, type, and download URL."
    ),
)
async def list_resources(
    context: Context,
    resource_type: Annotated[str, "The resource type: 'workbooks', 'alerts', or 'queries'."],
    category: Annotated[str, "The category name from list_categories."],
    base_path: Annotated[str, "The base folder path from list_categories response."],
) -> list[TextContent]:
    """List resources in a category."""
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
        "List all available Azure service categories from the Azure Monitor Community workbooks repository. "
        "Returns a list of category names (e.g., 'Virtual Machines', 'Storage Accounts', 'Azure Kubernetes Service'). "
        "NOTE: Consider using list_categories(resource_type='workbooks') for more detailed information."
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
        "List all workbooks in a specific Azure service category. "
        "Returns workbook metadata including name, path, size, and download URL. "
        "NOTE: Consider using list_resources() for more flexibility."
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
        "Download and analyze a workbook to extract its content, parameters, and requirements. "
        "Returns the full workbook JSON, extracted parameters with types and defaults, "
        "and a list of required parameters that must be provided for deployment. "
        "NOTE: Consider using get_resource_content() for more flexibility."
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
        "Deploy an Azure Monitor Community workbook to a resource group. "
        "Requires the workbook download URL (from list_resources), target subscription ID, "
        "resource group name, workbook name, location, and any required parameter values. "
        "This fetches the workbook content internally and uses Azure CLI to create the workbook resource."
    ),
)
async def deploy_workbook(
    context: Context,
    download_url: Annotated[
        str,
        "The download URL of the workbook from list_resources or get_resource_content.",
    ],
    subscription_id: Annotated[str, "Azure subscription ID where the workbook will be deployed."],
    resource_group: Annotated[str, "Resource group name for the workbook."],
    workbook_name: Annotated[str, "Name for the deployed workbook."],
    location: Annotated[str, "Azure region (e.g., 'eastus', 'westeurope')."],
    parameters: Annotated[
        Optional[str],
        "JSON string of parameter values as key-value pairs. Required parameters must be included.",
    ] = None,
) -> list[TextContent]:
    """Deploy a workbook using Azure CLI."""
    try:
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
            # Ensure Azure CLI is authenticated with service principal
            import os as os_module
            sp_id = os_module.getenv("AZURE_CLIENT_ID")
            sp_secret = os_module.getenv("AZURE_CLIENT_SECRET")
            tenant_id = os_module.getenv("AZURE_TENANT_ID")
            
            if sp_id and sp_secret and tenant_id:
                logger.info("Authenticating Azure CLI with service principal...")
                login_cmd = [
                    "az", "login",
                    "--service-principal",
                    "--username", sp_id,
                    "--password", sp_secret,
                    "--tenant", tenant_id
                ]
                login_proc = await asyncio.create_subprocess_exec(
                    *login_cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                await login_proc.communicate()
                
                if login_proc.returncode != 0:
                    logger.warning("Azure CLI login failed, deployment may fail if not already authenticated")
            
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
