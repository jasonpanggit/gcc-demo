#!/usr/bin/env python3
"""Scrape Azure Monitor Community repository and generate structured metadata.

This script crawls the Azure Monitor Community GitHub repository using HTML scraping
to extract workbooks, alerts, and queries organized by Azure service categories.
Generates a JSON metadata file for the UI to load resources without API rate limits.

Usage:
    python app/agentic/eol/deploy/update_monitor_community_metadata.py

The script writes JSON output to:
    app/agentic/eol/static/data/azure_monitor_community_metadata.json

No GitHub token required - uses HTML scraping to avoid API rate limits.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import quote, unquote

try:
    import httpx
    from bs4 import BeautifulSoup
except ImportError:
    print("Error: Required libraries not found. Install with:")
    print("  pip install httpx beautifulsoup4")
    exit(1)

# Configuration
GITHUB_WEB_BASE = "https://github.com"
GITHUB_RAW_BASE = "https://raw.githubusercontent.com"
GITHUB_REPO_OWNER = "microsoft"
GITHUB_REPO_NAME = "AzureMonitorCommunity"
GITHUB_BRANCH = "master"

OUTPUT_PATH = (
    Path(__file__).resolve()
    .parent
    .parent
    / "static"
    / "data"
    / "azure_monitor_community_metadata.json"
)

USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"

# Logging configuration
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)


@dataclass
class ResourceFile:
    """Represents a single resource file (workbook, alert, or query)."""
    name: str
    path: str
    download_url: str
    category: str
    resource_type: str  # workbooks, alerts, queries
    subfolder: Optional[str] = None  # e.g., "Performance", "Browsing data"
    description: Optional[str] = None  # Parsed description from file content
    display_name: Optional[str] = None  # Display name from file metadata
    
    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class CategoryResources:
    """Resources for a specific Azure service category."""
    category: str
    workbooks: List[ResourceFile] = field(default_factory=list)
    alerts: List[ResourceFile] = field(default_factory=list)
    queries: List[ResourceFile] = field(default_factory=list)
    
    def to_dict(self) -> Dict:
        return {
            "category": self.category,
            "workbooks": {
                "count": len(self.workbooks),
                "files": [f.to_dict() for f in self.workbooks]
            },
            "alerts": {
                "count": len(self.alerts),
                "files": [f.to_dict() for f in self.alerts]
            },
            "queries": {
                "count": len(self.queries),
                "files": [f.to_dict() for f in self.queries]
            },
            "total_resources": len(self.workbooks) + len(self.alerts) + len(self.queries)
        }


async def scrape_github_folder(client: httpx.AsyncClient, folder_path: str) -> List[Dict]:
    """Scrape GitHub folder page to get list of files and subdirectories.
    
    GitHub embeds the file tree data in a JSON script tag rather than rendering HTML.
    We'll extract and parse that JSON data.
    """
    url = f"{GITHUB_WEB_BASE}/{GITHUB_REPO_OWNER}/{GITHUB_REPO_NAME}/tree/{GITHUB_BRANCH}/{folder_path}"
    logger.debug(f"Scraping: {url}")

    try:
        response = await client.get(url)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        items = []
        
        # Find the embedded JSON data
        script_tag = soup.find('script', {'data-target': 'react-app.embeddedData'})
        
        if script_tag and script_tag.string:
            try:
                # Parse the JSON data
                data = json.loads(script_tag.string)
                
                # Extract the tree items
                tree_items = data.get('payload', {}).get('tree', {}).get('items', [])
                
                for item in tree_items:
                    name = item.get('name')
                    path = item.get('path')
                    content_type = item.get('contentType')
                    
                    if not name or not path:
                        continue
                    
                    if content_type == 'directory':
                        items.append({
                            "name": name,
                            "path": path,
                            "type": "dir"
                        })
                    elif content_type == 'file':
                        # Construct raw download URL
                        download_url = f"{GITHUB_RAW_BASE}/{GITHUB_REPO_OWNER}/{GITHUB_REPO_NAME}/{GITHUB_BRANCH}/{path}"
                        items.append({
                            "name": name,
                            "path": path,
                            "type": "file",
                            "download_url": download_url
                        })
                
                logger.debug(f"Found {len(items)} items in {folder_path}")
                return items
                
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse GitHub JSON data: {e}")
                return []
        
        # Fallback: Try the HTML table parsing method if JSON isn't found
        logger.debug("No embedded JSON found, trying HTML parsing...")
        rows = soup.find_all('div', {'role': 'row', 'class': lambda x: x and 'react-directory-row' in str(x)})
        
        if not rows:
            file_table = soup.find('div', {'aria-labelledby': 'folders-and-files'})
            if file_table:
                rows = file_table.find_all('div', {'role': 'row'})
        
        for row in rows:
            try:
                link = row.find('a', {'class': lambda x: x and 'Link' in str(x)})
                if not link or not link.get('href'):
                    continue
                
                href = link.get('href', '')
                name_elem = link.find('span') or link
                name = name_elem.get_text(strip=True)
                
                if not name or name in ['.', '..']:
                    continue
                
                is_dir = '/tree/' in href
                is_file = '/blob/' in href
                
                if is_dir:
                    path_match = re.search(r'/tree/[^/]+/(.+)', href)
                    if path_match:
                        items.append({
                            "name": name,
                            "path": unquote(path_match.group(1)),
                            "type": "dir"
                        })
                elif is_file:
                    path_match = re.search(r'/blob/[^/]+/(.+)', href)
                    if path_match:
                        raw_path = unquote(path_match.group(1))
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
        logger.error(f"HTTP error scraping {folder_path}: {exc.response.status_code}")
        return []
    except Exception as exc:
        logger.error(f"Error scraping {folder_path}: {exc}")
        return []


async def parse_file_description(client: httpx.AsyncClient, download_url: str, file_name: str) -> tuple[Optional[str], Optional[str]]:
    """Parse description and display name from file content.
    
    Returns:
        tuple of (description, display_name)
    """
    try:
        # Only fetch descriptions for smaller files to avoid excessive downloads
        # Skip large workbook files
        if file_name.endswith('.workbook'):
            return None, None
            
        response = await client.get(download_url, timeout=10.0)
        if response.status_code != 200:
            return None, None
            
        content = response.text
        
        # Parse KQL/Kusto files (have metadata in comments at top)
        if file_name.endswith(('.kql', '.kusto')):
            description = None
            display_name = None
            
            for line in content.split('\n')[:20]:  # Only check first 20 lines
                line = line.strip()
                if line.startswith('// Description:'):
                    description = line.replace('// Description:', '').strip()
                elif line.startswith('// Display name:'):
                    display_name = line.replace('// Display name:', '').strip()
                    
            return description, display_name
        
        # Parse JSON files (alerts, some queries)
        elif file_name.endswith('.json'):
            try:
                data = json.loads(content)
                description = data.get('description') or data.get('properties', {}).get('description')
                display_name = data.get('displayName') or data.get('name')
                return description, display_name
            except json.JSONDecodeError:
                return None, None
        
        # Parse YAML files (some alerts)
        elif file_name.endswith(('.yaml', '.yml')):
            # Simple YAML parsing for description field
            description = None
            display_name = None
            for line in content.split('\n')[:30]:
                if 'description:' in line.lower():
                    description = line.split(':', 1)[1].strip().strip('"\'')
                elif 'displayname:' in line.lower() or 'display_name:' in line.lower():
                    display_name = line.split(':', 1)[1].strip().strip('"\'')
            return description, display_name
            
    except Exception as e:
        logger.debug(f"Error parsing description from {file_name}: {e}")
        return None, None
    
    return None, None


async def get_files_recursively(
    client: httpx.AsyncClient,
    path: str,
    category: str,
    resource_type: str,
    max_depth: int = 3,
    current_depth: int = 0,
    parent_folders: List[str] = None
) -> List[ResourceFile]:
    """Recursively get all resource files from a folder."""
    if parent_folders is None:
        parent_folders = []
        
    if current_depth >= max_depth:
        return []
    
    files = []
    
    # Determine valid file extensions based on resource type
    extensions = {
        "workbooks": [".workbook", ".md"],
        "alerts": [".json", ".yaml", ".yml", ".md"],
        "queries": [".kql", ".kusto", ".json", ".md"]
    }
    valid_extensions = extensions.get(resource_type, [])
    
    try:
        items = await scrape_github_folder(client, path)
        
        for item in items:
            if item.get("type") == "file":
                name = item.get("name", "")
                
                # Check if file has valid extension
                if any(name.endswith(ext) for ext in valid_extensions):
                    # Determine subfolder path (e.g., "Performance" for queries in Performance folder)
                    subfolder = "/".join(parent_folders) if parent_folders else None
                    
                    download_url = item.get("download_url", "")
                    
                    # Parse description from file content (async)
                    description, display_name = await parse_file_description(client, download_url, name)
                    
                    files.append(ResourceFile(
                        name=name,
                        path=item.get("path", ""),
                        download_url=download_url,
                        category=category,
                        resource_type=resource_type,
                        subfolder=subfolder,
                        description=description,
                        display_name=display_name
                    ))
                    logger.debug(f"  Found {resource_type}: {name} (subfolder: {subfolder}, desc: {description[:50] if description else 'N/A'})")
                    
            elif item.get("type") == "dir":
                # Recursively explore subdirectories
                subdir_name = item.get("name", "")
                subdir_path = item.get("path", "")
                logger.debug(f"  Recursing into: {subdir_name}")
                
                subfiles = await get_files_recursively(
                    client,
                    subdir_path,
                    category,
                    resource_type,
                    max_depth,
                    current_depth + 1,
                    parent_folders + [subdir_name]
                )
                files.extend(subfiles)
    
    except Exception as e:
        logger.warning(f"Error exploring {path}: {e}")
    
    return files


async def scrape_category(
    client: httpx.AsyncClient,
    category_name: str,
    category_path: str
) -> CategoryResources:
    """Scrape all resources for a single Azure service category."""
    logger.info(f"Processing category: {category_name}")
    
    category_resources = CategoryResources(category=category_name)
    
    # Check for Workbooks subfolder
    workbook_path = f"{category_path}/Workbooks"
    workbooks = await get_files_recursively(
        client, workbook_path, category_name, "workbooks"
    )
    category_resources.workbooks = workbooks
    logger.info(f"  Found {len(workbooks)} workbooks")
    
    # Check for Alerts subfolder
    alerts_path = f"{category_path}/Alerts"
    alerts = await get_files_recursively(
        client, alerts_path, category_name, "alerts"
    )
    category_resources.alerts = alerts
    logger.info(f"  Found {len(alerts)} alerts")
    
    # Check for Queries subfolder
    queries_path = f"{category_path}/Queries"
    queries = await get_files_recursively(
        client, queries_path, category_name, "queries"
    )
    category_resources.queries = queries
    logger.info(f"  Found {len(queries)} queries")
    
    return category_resources


async def scrape_all_categories(client: httpx.AsyncClient) -> List[CategoryResources]:
    """Scrape all Azure service categories."""
    logger.info("Fetching Azure Services categories...")
    
    # Get list of all categories
    items = await scrape_github_folder(client, "Azure%20Services")
    categories = [item for item in items if item.get("type") == "dir"]
    
    logger.info(f"Found {len(categories)} categories")
    
    all_category_resources = []
    
    for category in categories:
        category_name = category.get("name")
        category_path = category.get("path")
        
        try:
            resources = await scrape_category(client, category_name, category_path)
            
            # Only include categories that have at least one resource
            if resources.workbooks or resources.alerts or resources.queries:
                all_category_resources.append(resources)
        except Exception as e:
            logger.error(f"Error processing category {category_name}: {e}")
            continue
    
    return all_category_resources


async def main():
    """Main entry point for the scraper."""
    logger.info("=" * 80)
    logger.info("Azure Monitor Community Metadata Generator")
    logger.info("=" * 80)
    logger.info(f"Repository: {GITHUB_REPO_OWNER}/{GITHUB_REPO_NAME}")
    logger.info(f"Output: {OUTPUT_PATH}")
    logger.info("=" * 80)
    
    async with httpx.AsyncClient(
        timeout=30.0,
        follow_redirects=True,
        headers={"User-Agent": USER_AGENT}
    ) as client:
        # Scrape all categories
        all_categories = await scrape_all_categories(client)
        
        # Calculate totals
        total_workbooks = sum(len(cat.workbooks) for cat in all_categories)
        total_alerts = sum(len(cat.alerts) for cat in all_categories)
        total_queries = sum(len(cat.queries) for cat in all_categories)
        total_resources = total_workbooks + total_alerts + total_queries
        
        # Build metadata structure
        metadata = {
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "repository": f"{GITHUB_REPO_OWNER}/{GITHUB_REPO_NAME}",
            "branch": GITHUB_BRANCH,
            "method": "HTML Scraping (no API token required)",
            "summary": {
                "total_categories": len(all_categories),
                "total_workbooks": total_workbooks,
                "total_alerts": total_alerts,
                "total_queries": total_queries,
                "total_resources": total_resources
            },
            "categories": [cat.to_dict() for cat in all_categories]
        }
        
        # Ensure output directory exists
        OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        
        # Write to file
        with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)
        
        logger.info("=" * 80)
        logger.info("Summary")
        logger.info("=" * 80)
        logger.info(f"Categories:       {len(all_categories)}")
        logger.info(f"Total Workbooks:  {total_workbooks}")
        logger.info(f"Total Alerts:     {total_alerts}")
        logger.info(f"Total Queries:    {total_queries}")
        logger.info(f"Total Resources:  {total_resources}")
        logger.info("=" * 80)
        logger.info(f"✅ Metadata saved to: {OUTPUT_PATH}")
        logger.info("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
