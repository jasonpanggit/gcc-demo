"""
Bing Search Agent - Uses Bing Search API to find EOL information for unknown software (no Cosmos caching)
"""
import requests
import re
from bs4 import BeautifulSoup
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
import os
import hashlib
import json
from .base_eol_agent import BaseEOLAgent
try:
    from utils.logger import get_logger
    logger = get_logger(__name__)
except Exception:
    import logging
    logger = logging.getLogger(__name__)


class BingEOLAgent(BaseEOLAgent):
    """Agent for searching EOL information using Bing Search API"""
    
    def __init__(self):
        # Agent identification
        self.agent_name = "bing_search"
        
        self.timeout = 15
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        # Bing Search API setup
        self.bing_search_key = os.getenv("BING_SEARCH_API_KEY", "")
        self.bing_search_endpoint = "https://api.bing.microsoft.com/v7.0/search"
        
        # Caching disabled (Cosmos removed)
        self.cache_duration_hours = 0
        
        # Common EOL-related keywords to enhance search queries
        self.eol_keywords = [
            "end of life", "EOL", "end of support", "EOS", "lifecycle", 
            "deprecation", "discontinued", "sunset", "retirement",
            "support end", "maintenance end", "extended support"
        ]
        
        # Date patterns for extracting dates from text
        self.date_patterns = [
            r'\b(\d{4}[-/]\d{1,2}[-/]\d{1,2})\b',  # YYYY-MM-DD or YYYY/MM/DD
            r'\b(\d{1,2}[-/]\d{1,2}[-/]\d{4})\b',  # MM-DD-YYYY or MM/DD/YYYY
            r'\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4}\b',
            r'\b\d{1,2}\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4}\b',
            r'\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2},?\s+\d{4}\b'
        ]
    # logger is module-level
    
    async def get_eol_data(self, software_name: str, software_version: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Get EOL data for software - interface method to match other agents
        """
        result = await self.search_eol_info(software_name, software_version)
        
        if result and not result.get("error"):
            # Convert Bing search result to standardized format
            return self.create_success_response(
                software_name=software_name,
                version=software_version or "unknown",
                eol_date=result.get("eol_date", ""),
                support_end_date=result.get("eol_date", ""),  # Bing doesn't distinguish support vs EOL
                confidence=self._convert_confidence_to_numeric(result.get("confidence", "low")) / 100.0,
                source_url=result.get("sources", [{}])[0].get("url", "") if result.get("sources") else "",
                additional_data={
                    "cycle": software_version or "unknown",
                    "extended_support": False,  # Bing search doesn't provide this info
                    "agent": self.agent_name,
                    "data_source": "bing_search",
                    "search_results_count": result.get("search_results_count", 0)
                }
            )
        
        # No valid result found
        return self.create_failure_response(
            f"No EOL information found for {software_name}" + (f" version {software_version}" if software_version else ""),
            "no_data_found" if not result.get("error") else "search_error",
            {"searched_product": software_name, "searched_version": software_version, "error": result.get("error") if result else None}
        )
    
    def _convert_confidence_to_numeric(self, confidence_str: str) -> int:
        """Convert string confidence to numeric value"""
        confidence_map = {
            "high": 85,
            "medium": 70,
            "low": 50
        }
        return confidence_map.get(confidence_str.lower(), 50)
    
    async def search_eol_info(self, software_name: str, software_version: Optional[str] = None) -> Dict[str, Any]:
        """
        Search for EOL information using Bing Search API
        """
        try:
            # Check cache first
            cache_key = self._generate_cache_key(software_name, software_version)
            cached_result = await self._get_cached_result(cache_key)
            if cached_result:
                return cached_result
            
            # Construct search query
            query = self._build_search_query(software_name, software_version)
            
            # Perform Bing search
            search_results = await self._perform_bing_search(query)
            
            if not search_results:
                return {"error": "No search results found", "software_name": software_name}
            
            # Analyze search results to extract EOL information
            eol_info = await self._analyze_search_results(search_results, software_name, software_version)
            
            # Cache the result
            await self._cache_result(cache_key, eol_info)
            
            return eol_info
            
        except Exception as e:
            return {
                "error": f"Bing search failed: {str(e)}",
                "software_name": software_name,
                "software_version": software_version
            }
    
    def _build_search_query(self, software_name: str, software_version: Optional[str] = None) -> str:
        """Build an optimized search query for EOL information"""
        base_query = f'"{software_name}"'
        
        if software_version:
            base_query += f' "{software_version}"'
        
        # Add EOL-specific terms
        eol_terms = "end of life OR EOL OR \"end of support\" OR lifecycle OR deprecation"
        
        # Construct final query
        query = f'{base_query} ({eol_terms})'
        
        # Add site restrictions for authoritative sources
        authoritative_sites = [
            "site:microsoft.com", "site:redhat.com", "site:ubuntu.com", 
            "site:oracle.com", "site:ibm.com", "site:vmware.com",
            "site:adobe.com", "site:apple.com", "site:google.com",
            "site:endoflife.date"
        ]
        
        # Limit to authoritative sources
        query += f' ({" OR ".join(authoritative_sites)})'
        
        return query
    
    async def _perform_bing_search(self, query: str) -> List[Dict[str, Any]]:
        """Perform Bing search and return results"""
        if not self.bing_search_key:
            # Fallback to web scraping if no API key
            return await self._fallback_web_search(query)
        
        try:
            headers = {
                'Ocp-Apim-Subscription-Key': self.bing_search_key,
                'Content-Type': 'application/json'
            }
            
            params = {
                'q': query,
                'count': 10,  # Number of results to return
                'offset': 0,
                'mkt': 'en-US',
                'responseFilter': 'Webpages'
            }
            
            response = requests.get(
                self.bing_search_endpoint,
                headers=headers,
                params=params,
                timeout=self.timeout
            )
            
            if response.status_code == 200:
                data = response.json()
                return data.get('webPages', {}).get('value', [])
            else:
                logger.error(f"Bing API error: {response.status_code}")
                return []
                
        except Exception as e:
            logger.error(f"Bing search error: {e}")
            return []
    
    async def _fallback_web_search(self, query: str) -> List[Dict[str, Any]]:
        """Fallback web search when Bing API is not available"""
        # Simulate search results by checking common EOL sources
        fallback_urls = [
            f"https://endoflife.date/api/all",
            "https://learn.microsoft.com/en-us/lifecycle/",
            "https://access.redhat.com/support/policy/updates/errata/"
        ]
        
        results = []
        for url in fallback_urls:
            try:
                response = requests.get(url, headers=self.headers, timeout=self.timeout)
                if response.status_code == 200:
                    results.append({
                        'name': f"EOL Information Source",
                        'url': url,
                        'snippet': response.text[:500],
                        'displayUrl': url
                    })
            except:
                continue
        
        return results
    
    async def _analyze_search_results(self, search_results: List[Dict[str, Any]], 
                                    software_name: str, software_version: Optional[str] = None) -> Dict[str, Any]:
        """Analyze search results to extract EOL information"""
        eol_info = {
            "software_name": software_name,
            "software_version": software_version,
            "agent_used": self.agent_name,
            "search_results_count": len(search_results),
            "sources": []
        }
        
        found_dates = []
        found_info = []
        
        for result in search_results[:5]:  # Analyze top 5 results
            try:
                # Extract information from snippet
                snippet = result.get('snippet', '')
                url = result.get('url', '')
                title = result.get('name', '')
                
                # Try to extract content from the page
                page_content = await self._extract_page_content(url)
                full_text = f"{title} {snippet} {page_content}"
                
                # Extract dates from the content
                dates = self._extract_dates_from_text(full_text)
                
                # Look for EOL-specific information
                eol_context = self._extract_eol_context(full_text, software_name, software_version)
                
                source_info = {
                    "url": url,
                    "title": title,
                    "snippet": snippet,
                    "dates_found": dates,
                    "eol_context": eol_context
                }
                
                eol_info["sources"].append(source_info)
                found_dates.extend(dates)
                found_info.extend(eol_context)
                
            except Exception as e:
                logger.error(f"Error analyzing result {result.get('url', 'unknown')}: {e}")
                continue
        
        # Determine the most likely EOL date
        eol_date = self._determine_best_eol_date(found_dates, found_info, software_name, software_version)
        
        if eol_date:
            eol_info["eol_date"] = eol_date
            eol_info["confidence"] = self._calculate_confidence(found_dates, found_info)
            eol_info["risk_level"] = self._assess_risk_level(eol_date)
        else:
            eol_info["eol_date"] = None
            eol_info["confidence"] = "low"
            eol_info["message"] = "No clear EOL date found in search results"
        
        eol_info["description"] = self._generate_description(eol_info)
        
        return eol_info
    
    async def _extract_page_content(self, url: str) -> str:
        """Extract relevant content from a webpage"""
        try:
            response = requests.get(url, headers=self.headers, timeout=self.timeout)
            if response.status_code == 200:
                soup = BeautifulSoup(response.content, 'html.parser')
                
                # Remove script and style elements
                for script in soup(["script", "style"]):
                    script.decompose()
                
                # Extract text content
                text = soup.get_text()
                
                # Clean up text
                lines = (line.strip() for line in text.splitlines())
                chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
                text = ' '.join(chunk for chunk in chunks if chunk)
                
                # Return first 2000 characters to avoid too much data
                return text[:2000]
        except:
            pass
        return ""
    
    def _extract_dates_from_text(self, text: str) -> List[str]:
        """Extract dates from text using regex patterns"""
        dates = []
        
        for pattern in self.date_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for match in matches:
                if isinstance(match, tuple):
                    dates.append(' '.join(match))
                else:
                    dates.append(match)
        
        # Filter and normalize dates
        normalized_dates = []
        for date_str in dates:
            normalized = self._normalize_date(date_str)
            if normalized:
                normalized_dates.append(normalized)
        
        return list(set(normalized_dates))  # Remove duplicates
    
    def _normalize_date(self, date_str: str) -> Optional[str]:
        """Normalize date string to YYYY-MM-DD format"""
        try:
            # Try different date formats
            formats = [
                "%Y-%m-%d", "%Y/%m/%d", "%m-%d-%Y", "%m/%d/%Y",
                "%B %d, %Y", "%B %d %Y", "%d %B %Y",
                "%b %d, %Y", "%b %d %Y"
            ]
            
            for fmt in formats:
                try:
                    date_obj = datetime.strptime(date_str.strip(), fmt)
                    return date_obj.strftime("%Y-%m-%d")
                except ValueError:
                    continue
            
            return None
        except:
            return None
    
    def _extract_eol_context(self, text: str, software_name: str, software_version: Optional[str] = None) -> List[str]:
        """Extract EOL-related context from text"""
        context = []
        
        # Look for sentences containing software name and EOL keywords
        sentences = text.split('.')
        
        for sentence in sentences:
            sentence_lower = sentence.lower()
            
            # Check if sentence mentions the software
            if software_name.lower() in sentence_lower:
                # Check if sentence mentions EOL-related terms
                for keyword in self.eol_keywords:
                    if keyword.lower() in sentence_lower:
                        context.append(sentence.strip())
                        break
        
        return context
    
    def _determine_best_eol_date(self, dates: List[str], context: List[str], 
                                software_name: str, software_version: Optional[str] = None) -> Optional[str]:
        """Determine the most likely EOL date from found dates"""
        if not dates:
            return None
        
        # Filter future dates (EOL dates should be in the future or recent past)
        current_date = datetime.now()
        valid_dates = []
        
        for date_str in dates:
            try:
                date_obj = datetime.strptime(date_str, "%Y-%m-%d")
                # Consider dates within 10 years past or future
                if (current_date - timedelta(days=3650)) <= date_obj <= (current_date + timedelta(days=3650)):
                    valid_dates.append((date_str, date_obj))
            except:
                continue
        
        if not valid_dates:
            return None
        
        # Sort by date and return the most reasonable one
        # Prefer future dates over past dates for EOL
        future_dates = [(d, dt) for d, dt in valid_dates if dt > current_date]
        past_dates = [(d, dt) for d, dt in valid_dates if dt <= current_date]
        
        if future_dates:
            # Return the earliest future date
            future_dates.sort(key=lambda x: x[1])
            return future_dates[0][0]
        elif past_dates:
            # Return the latest past date (most recent EOL)
            past_dates.sort(key=lambda x: x[1], reverse=True)
            return past_dates[0][0]
        
        return valid_dates[0][0] if valid_dates else None
    
    def _calculate_confidence(self, dates: List[str], context: List[str]) -> str:
        """Calculate confidence level based on found information"""
        confidence_score = 0
        
        # More dates found = higher confidence
        if len(dates) >= 3:
            confidence_score += 30
        elif len(dates) >= 2:
            confidence_score += 20
        elif len(dates) >= 1:
            confidence_score += 10
        
        # More context = higher confidence
        if len(context) >= 3:
            confidence_score += 30
        elif len(context) >= 2:
            confidence_score += 20
        elif len(context) >= 1:
            confidence_score += 10
        
        # Check for authoritative sources
        authoritative_domains = ["microsoft.com", "redhat.com", "ubuntu.com", "endoflife.date"]
        for ctx in context:
            for domain in authoritative_domains:
                if domain in ctx.lower():
                    confidence_score += 20
                    break
        
        if confidence_score >= 70:
            return "high"
        elif confidence_score >= 40:
            return "medium"
        else:
            return "low"
    
    def _assess_risk_level(self, eol_date: str) -> str:
        """Assess risk level based on EOL date"""
        try:
            eol_dt = datetime.strptime(eol_date, "%Y-%m-%d")
            current_dt = datetime.now()
            days_until_eol = (eol_dt - current_dt).days
            
            if days_until_eol < 0:
                return "critical"  # Already EOL
            elif days_until_eol < 365:
                return "high"  # EOL within 1 year
            elif days_until_eol < 730:
                return "medium"  # EOL within 2 years
            else:
                return "low"  # EOL more than 2 years away
        except:
            return "unknown"
    
    def _generate_description(self, eol_info: Dict[str, Any]) -> str:
        """Generate a description of the findings"""
        software_name = eol_info.get("software_name", "Unknown software")
        eol_date = eol_info.get("eol_date")
        confidence = eol_info.get("confidence", "unknown")
        
        if eol_date:
            return f"Bing search found EOL information for {software_name}. End of life date: {eol_date} (confidence: {confidence}). Information gathered from {len(eol_info.get('sources', []))} web sources."
        else:
            return f"Bing search completed for {software_name} but no clear EOL date was found. Searched {len(eol_info.get('sources', []))} web sources."
    
    def _generate_cache_key(self, software_name: str, software_version: Optional[str] = None) -> str:
        """Generate cache key for the search"""
        key_data = f"bing_search_{software_name}_{software_version or 'no_version'}"
        return hashlib.md5(key_data.encode()).hexdigest()
    
    async def _get_cached_result(self, cache_key: str) -> Optional[Dict[str, Any]]:
        """Caching disabled - always return None"""
        return None
    
    async def _cache_result(self, cache_key: str, result: Dict[str, Any]) -> None:
        """Caching disabled - no-op"""
        return
