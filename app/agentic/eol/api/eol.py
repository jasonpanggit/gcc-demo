"""
End-of-Life (EOL) Search and Management API Module

This module provides endpoints for searching, verifying, and managing End-of-Life
data for software and operating systems. It orchestrates multiple specialized agents
to query various EOL data sources and consolidate results.

Key Features:
    - Multi-agent EOL data search across specialized sources
    - Software and OS inventory EOL risk analysis
    - EOL result verification and manual caching
    - Agent response history tracking and management
    - Internet-only search mode for web scraping

Endpoints:
    GET  /api/eol - Get EOL data for software
    POST /api/search/eol - Search EOL data with orchestrator
    POST /api/analyze - Comprehensive EOL risk analysis
    POST /api/verify-eol-result - Verify and cache EOL result
    POST /api/cache-eol-result - Manually cache EOL result
    GET  /api/eol-agent-responses - Get agent response history
    POST /api/eol-agent-responses/clear - Clear response history

Author: GitHub Copilot
Date: October 2025
"""

from typing import Optional
from datetime import datetime
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from utils.logger import logger
from utils.response_models import StandardResponse
from utils.endpoint_decorators import (
    standard_endpoint,
    write_endpoint,
    readonly_endpoint,
    with_timeout_and_stats
)

# Import main module dependencies
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from main import get_eol_orchestrator, get_chat_orchestrator

# Create router for EOL endpoints
router = APIRouter(tags=["EOL Search & Management"])


# ============================================================================
# PYDANTIC MODELS
# ============================================================================

class SoftwareSearchRequest(BaseModel):
    """Request model for EOL search."""
    software_name: str
    software_version: Optional[str] = None
    search_hints: Optional[str] = None
    search_internet_only: bool = False


class VerifyEOLRequest(BaseModel):
    """Request model for EOL verification."""
    software_name: str
    software_version: Optional[str] = None
    agent_name: Optional[str] = None
    source_url: Optional[str] = None
    verification_status: Optional[str] = "verified"  # "verified" or "failed"


class CacheEOLRequest(BaseModel):
    """Request model for manual EOL caching."""
    software_name: str
    software_version: Optional[str] = None


class MultiAgentResponse(BaseModel):
    """Response model for multi-agent operations."""
    session_id: str
    analysis_result: dict
    communication_history: list
    timestamp: str


# ============================================================================
# EOL QUERY ENDPOINTS
# ============================================================================

@router.get("/api/eol", response_model=StandardResponse)
@standard_endpoint(agent_name="eol_search", timeout_seconds=30)
async def get_eol(name: str, version: Optional[str] = None):
    """
    Get EOL data using multi-agent system with prioritized sources.
    
    Searches for end-of-life information across multiple specialized agents
    (Microsoft, Red Hat, endoflife.date, etc.) and returns consolidated results.
    
    Args:
        name: Software name to search for (required)
        version: Specific version to check (optional)
    
    Returns:
        StandardResponse with EOL data including dates, support status, and sources.
    
    Raises:
        HTTPException: 404 if no EOL data found, 500 for other errors
    
    Example Response:
        {
            "success": true,
            "software_name": "Windows Server 2012 R2",
            "version": null,
            "primary_source": "microsoft_lifecycle",
            "eol_data": {
                "eol_date": "2023-10-10",
                "support_end": "2023-10-10",
                "status": "expired"
            },
            "all_sources": {
                "microsoft_lifecycle": {...},
                "endoflife_date": {...}
            },
            "timestamp": "2025-10-15T10:45:00Z"
        }
    """
    eol_data = await get_eol_orchestrator().get_eol_data(name, version)
    
    if not eol_data.get("data"):
        raise HTTPException(status_code=404, detail=f"No EOL data found for {name}")
    
    return {
        "software_name": name,
        "version": version,
        "primary_source": eol_data["primary_source"],
        "eol_data": eol_data["data"],
        "all_sources": eol_data.get("all_sources", {}),
        "timestamp": datetime.utcnow().isoformat()
    }


@router.post("/api/search/eol")
@with_timeout_and_stats(
    agent_name="orchestrator",
    timeout_seconds=45,
    track_cache=True,
    auto_wrap_response=False
)
async def search_software_eol(request: SoftwareSearchRequest):
    """
    Search for end-of-life information for specific software using the orchestrator.
    
    Uses intelligent agent routing to search across multiple EOL data sources.
    Supports internet-only search mode for web scraping when structured data unavailable.
    
    Args:
        request: SoftwareSearchRequest containing software_name, software_version,
                search_hints, and search_internet_only flag
    
    Returns:
        Dict with EOL result, session_id, communications, and search metadata.
    
    Example Request:
        {
            "software_name": "Oracle Database",
            "software_version": "19c",
            "search_hints": "Enterprise Edition",
            "search_internet_only": false
        }
    
    Example Response:
        {
            "success": true,
            "result": {
                "eol_date": "2027-04-30",
                "extended_support": "2030-04-30"
            },
            "session_id": "uuid-here",
            "communications": [...],
            "search_mode": "multi_agent",
            "agent_used": "oracle_lifecycle",
            "timestamp": "2025-10-15T10:50:00Z"
        }
    """
    # Log the enhanced search request
    version_display = f" v{request.software_version}" if request.software_version else " (no version)"
    search_mode = " [Internet Only]" if request.search_internet_only else ""
    logger.info(f"EOL search request: {request.software_name}{version_display}{search_mode}")
    
    if request.search_hints:
        logger.info(f"Search hints provided: {request.search_hints}")
    
    # Call appropriate search method based on mode
    orchestrator = get_eol_orchestrator()
    
    if request.search_internet_only:
        # Internet-only search mode
        result = await orchestrator.search_software_eol_internet(
            software_name=request.software_name,
            software_version=request.software_version,
            search_hints=request.search_hints
        )
        search_mode = "internet_only"
    else:
        # Standard multi-agent search
        result = await orchestrator.search_software_eol(
            software_name=request.software_name,
            software_version=request.software_version,
            search_hints=request.search_hints
        )
        search_mode = "multi_agent"
    
    # Get communication history
    communications = await orchestrator.get_communication_history()
    
    return {
        "result": result,
        "session_id": orchestrator.session_id,
        "communications": communications,
        "search_mode": search_mode,
        "timestamp": datetime.utcnow().isoformat()
    }


@router.post("/api/analyze")
@write_endpoint(agent_name="analyze_inventory", timeout_seconds=60)
async def analyze_inventory_eol():
    """
    Comprehensive EOL risk analysis using multi-agent orchestration.
    
    Analyzes the entire software and OS inventory to identify EOL risks,
    prioritize updates, and provide actionable recommendations.
    
    Returns:
        MultiAgentResponse with risk analysis, affected systems, and
        communication history from all agents involved.
    
    Example Response:
        {
            "session_id": "uuid-here",
            "analysis_result": {
                "high_risk": 15,
                "medium_risk": 45,
                "low_risk": 200,
                "recommendations": [...]
            },
            "communication_history": [...],
            "timestamp": "2025-10-15T11:00:00Z"
        }
    """
    analysis = await get_eol_orchestrator().analyze_inventory_eol_risks()
    communications = await get_eol_orchestrator().get_communication_history()
    
    return MultiAgentResponse(
        session_id=get_eol_orchestrator().session_id,
        analysis_result=analysis,
        communication_history=communications,
        timestamp=datetime.utcnow().isoformat()
    )


# ============================================================================
# EOL VERIFICATION & CACHING ENDPOINTS
# ============================================================================

@router.post("/api/verify-eol-result", response_model=StandardResponse)
@write_endpoint(agent_name="verify_eol", timeout_seconds=45)
async def verify_eol_result(request: VerifyEOLRequest):
    """
    Mark EOL result as verified or failed and cache with appropriate priority.
    
    Performs EOL lookup and caches the result with verification status.
    Failed verifications are removed from cache, while verified results
    are cached with high priority.
    
    Args:
        request: VerifyEOLRequest with software name, version, and verification status
    
    Returns:
        StandardResponse with verification details and cache status.
    
    Example Request:
        {
            "software_name": "Adobe Acrobat Reader",
            "software_version": "2020.012.20041",
            "agent_name": "adobe_lifecycle",
            "verification_status": "verified",
            "source_url": "https://adobe.com/lifecycle"
        }
    
    Example Response:
        {
            "success": true,
            "message": "EOL result verified and cached",
            "verification_status": "verified",
            "software_name": "Adobe Acrobat Reader",
            "agent_used": "adobe_lifecycle",
            "cache_updated": true
        }
    """
    verification_status = request.verification_status or "verified"
    is_verified = verification_status == "verified"
    is_failed = verification_status == "failed"
    
    # Get the orchestrator to perform the search 
    result = await get_eol_orchestrator().get_autonomous_eol_data(
        software_name=request.software_name,
        version=request.software_version
    )
    
    # If we have a result, cache it with appropriate verification status
    if result.get('success') and result.get('data'):
        # Use eol_cache to handle verification status
        from utils.cosmos_cache import base_cosmos
        from utils.eol_cache import eol_cache
        if getattr(base_cosmos, 'initialized', False):
            if is_failed:
                # For failed verifications, delete the cache entry to clear it completely
                await eol_cache.delete_failed_cache_entry(
                    software_name=request.software_name,
                    version=request.software_version,
                    agent_name=request.agent_name
                )
                return {
                    "success": True,
                    "message": f"Failed verification - cache entry removed for {request.software_name}",
                    "verification_status": verification_status,
                    "software_name": request.software_name,
                    "software_version": request.software_version,
                    "cache_cleared": True
                }
            else:
                # For verified results, update the cache with verification status
                await eol_cache.cache_response(
                    software_name=request.software_name,
                    version=request.software_version,
                    agent_name=request.agent_name,
                    response_data=result,
                    verified=is_verified,
                    source_url=request.source_url,
                    priority=2  # High priority for verified results
                )
                return {
                    "success": True,
                    "message": f"EOL result verified and cached for {request.software_name}",
                    "verification_status": verification_status,
                    "software_name": request.software_name,
                    "software_version": request.software_version,
                    "agent_used": result.get('agent_used'),
                    "cache_updated": True
                }
        else:
            return {
                "success": True,
                "message": "Verification recorded (Cosmos DB not initialized)",
                "verification_status": verification_status,
                "cache_updated": False
            }
    else:
        return {
            "success": False,
            "message": f"Failed to find EOL data for {request.software_name}",
            "error": "No EOL data found to verify"
        }


@router.post("/api/cache-eol-result", response_model=StandardResponse)
@write_endpoint(agent_name="cache_eol", timeout_seconds=45)
async def cache_eol_result(request: CacheEOLRequest):
    """
    Manually cache EOL result for user validation.
    
    Performs EOL lookup and stores the result in cache for future queries.
    Useful for pre-caching known EOL data or validating cache behavior.
    
    Args:
        request: CacheEOLRequest with software name and version
    
    Returns:
        StandardResponse with cache operation status and agent information.
    
    Example Request:
        {
            "software_name": "MySQL",
            "software_version": "5.7"
        }
    
    Example Response:
        {
            "success": true,
            "message": "EOL result cached for MySQL",
            "software_name": "MySQL",
            "software_version": "5.7",
            "agent_used": "mysql_lifecycle",
            "timestamp": "2025-10-15T11:10:00Z"
        }
    """
    # Get the orchestrator to perform the search and cache it
    result = await get_eol_orchestrator().get_autonomous_eol_data(
        software_name=request.software_name,
        version=request.software_version
    )
    
    # If we have a result, the caching should have been handled by the agent
    if result.get('success') and result.get('data'):
        return {
            "success": True,
            "message": f"EOL result cached for {request.software_name}",
            "software_name": request.software_name,
            "software_version": request.software_version,
            "agent_used": result.get('agent_used'),
            "timestamp": datetime.utcnow().isoformat()
        }
    else:
        return {
            "success": False,
            "message": f"Failed to find EOL data for {request.software_name}",
            "error": "No EOL data found to cache"
        }


# ============================================================================
# EOL AGENT RESPONSE TRACKING ENDPOINTS
# ============================================================================

@router.get("/api/eol-agent-responses", response_model=StandardResponse)
@readonly_endpoint(agent_name="eol_agent_responses", timeout_seconds=15)
async def get_eol_agent_responses():
    """
    Get all tracked EOL agent responses from both Chat and EOL orchestrators.
    
    Retrieves historical EOL search results from all orchestrators, including
    which agents were used, confidence scores, and timestamps.
    
    Returns:
        StandardResponse with list of EOL responses from all sources,
        sorted by timestamp (newest first).
    
    Example Response:
        {
            "success": true,
            "responses": [
                {
                    "software_name": "Windows Server 2012 R2",
                    "agent_used": "microsoft_lifecycle",
                    "confidence": 0.95,
                    "timestamp": "2025-10-15T11:15:00Z",
                    "orchestrator_type": "eol_orchestrator"
                }
            ],
            "count": 45,
            "sources": {
                "chat_orchestrator": 20,
                "eol_orchestrator": 25
            }
        }
    """
    all_responses = []
    
    # Get responses from Chat orchestrator
    chat_orchestrator = get_chat_orchestrator()
    if chat_orchestrator and hasattr(chat_orchestrator, 'get_eol_agent_responses'):
        chat_responses = chat_orchestrator.get_eol_agent_responses()
        # Mark these as from chat orchestrator
        for response in chat_responses:
            response['orchestrator_type'] = 'chat_orchestrator'
        all_responses.extend(chat_responses)
        logger.info(f"🔍 [API] Chat orchestrator returned {len(chat_responses)} EOL responses")
    else:
        logger.warning("🔍 [API] Chat orchestrator not available or missing get_eol_agent_responses method")
    
    # Get responses from EOL orchestrator
    eol_orchestrator = get_eol_orchestrator()
    if eol_orchestrator and hasattr(eol_orchestrator, 'get_eol_agent_responses'):
        eol_responses = eol_orchestrator.get_eol_agent_responses()
        # Mark these as from eol orchestrator
        for response in eol_responses:
            response['orchestrator_type'] = 'eol_orchestrator'
        all_responses.extend(eol_responses)
        logger.info(f"🔍 [API] EOL orchestrator returned {len(eol_responses)} EOL responses")
    else:
        logger.warning("🔍 [API] EOL orchestrator not available or missing get_eol_agent_responses method")
    
    # Sort by timestamp (newest first)
    all_responses.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
    
    logger.info(f"🔍 [API] Total EOL responses returned: {len(all_responses)}")
    
    return {
        "success": True,
        "responses": all_responses,
        "count": len(all_responses),
        "timestamp": datetime.utcnow().isoformat(),
        "sources": {
            "chat_orchestrator": len([r for r in all_responses if r.get('orchestrator_type') == 'chat_orchestrator']),
            "eol_orchestrator": len([r for r in all_responses if r.get('orchestrator_type') == 'eol_orchestrator'])
        }
    }


@router.post("/api/eol-agent-responses/clear", response_model=StandardResponse)
@write_endpoint(agent_name="clear_eol_responses", timeout_seconds=30)
async def clear_eol_agent_responses():
    """
    Clear all tracked EOL agent responses from both orchestrators.
    
    Removes all historical EOL search responses from memory, resetting
    the response tracking for both chat and EOL orchestrators.
    
    Returns:
        StandardResponse indicating success and counts cleared from each source.
    
    Example Response:
        {
            "success": true,
            "message": "EOL agent responses cleared",
            "cleared_counts": {
                "chat_orchestrator": 20,
                "eol_orchestrator": 25
            },
            "total_cleared": 45
        }
    """
    cleared_counts = {
        "chat_orchestrator": 0,
        "eol_orchestrator": 0
    }
    
    # Clear chat orchestrator responses
    chat_orchestrator = get_chat_orchestrator()
    if chat_orchestrator and hasattr(chat_orchestrator, 'clear_eol_agent_responses'):
        count = chat_orchestrator.clear_eol_agent_responses()
        cleared_counts["chat_orchestrator"] = count
        logger.info(f"🧹 [API] Cleared {count} EOL responses from chat orchestrator")
    
    # Clear EOL orchestrator responses
    eol_orchestrator = get_eol_orchestrator()
    if eol_orchestrator and hasattr(eol_orchestrator, 'clear_eol_agent_responses'):
        count = eol_orchestrator.clear_eol_agent_responses()
        cleared_counts["eol_orchestrator"] = count
        logger.info(f"🧹 [API] Cleared {count} EOL responses from EOL orchestrator")
    
    total_cleared = sum(cleared_counts.values())
    
    return {
        "success": True,
        "message": f"Cleared {total_cleared} EOL agent responses",
        "cleared_counts": cleared_counts,
        "total_cleared": total_cleared,
        "timestamp": datetime.utcnow().isoformat()
    }
