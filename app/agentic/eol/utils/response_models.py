"""
Standardized response models for API endpoints
Ensures consistent data format across all endpoints
"""
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from datetime import datetime


@dataclass
class StandardResponse:
    """Standard API response format for all endpoints
    
    All API endpoints should return data in this format to ensure
    consistency and eliminate frontend data unwrapping logic.
    
    Example:
        # Success response
        response = StandardResponse.success_response(
            data=[{"id": 1, "name": "test"}],
            cached=True,
            metadata={"source": "cosmos_db"}
        )
        
        # Error response
        response = StandardResponse.error_response(
            error="Database connection failed",
            metadata={"retry_count": 3}
        )
    """
    success: bool
    data: List[Dict[str, Any]] = field(default_factory=list)
    count: int = 0
    cached: bool = False
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    metadata: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        result = {
            "success": self.success,
            "data": self.data,
            "count": self.count,
            "cached": self.cached,
            "timestamp": self.timestamp
        }
        
        if self.metadata:
            result["metadata"] = self.metadata
        
        if self.error:
            result["error"] = self.error
        
        return result
    
    @classmethod
    def success_response(cls, data: List[Dict[str, Any]], cached: bool = False, 
                        metadata: Optional[Dict[str, Any]] = None) -> "StandardResponse":
        """Create a successful response
        
        Args:
            data: List of data items (always a list for consistency)
            cached: Whether data came from cache
            metadata: Optional metadata about the response
            
        Returns:
            StandardResponse instance
        """
        return cls(
            success=True,
            data=data,
            count=len(data),
            cached=cached,
            metadata=metadata
        )
    
    @classmethod
    def error_response(cls, error: str, metadata: Optional[Dict[str, Any]] = None) -> "StandardResponse":
        """Create an error response
        
        Args:
            error: Error message
            metadata: Optional metadata about the error
            
        Returns:
            StandardResponse instance with error
        """
        return cls(
            success=False,
            data=[],
            count=0,
            error=error,
            metadata=metadata
        )


@dataclass
class AgentResponse:
    """Response format for agent operations
    
    Used by all agents to return consistent data format.
    Can be converted to StandardResponse for API endpoints.
    
    Example:
        # Agent returns response
        agent_response = AgentResponse(
            success=True,
            data=[{"software": "Windows", "version": "10"}],
            agent_name="os_inventory",
            cached=True
        )
        
        # Convert to standard API response
        api_response = agent_response.to_standard_response()
    """
    success: bool
    data: Any
    agent_name: str
    cached: bool = False
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    error: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    
    def to_standard_response(self) -> StandardResponse:
        """Convert agent response to standard API response
        
        Ensures data is always a list and includes agent metadata.
        
        Returns:
            StandardResponse instance
        """
        # Ensure data is a list
        if isinstance(self.data, list):
            data_list = self.data
        elif isinstance(self.data, dict):
            data_list = [self.data]
        elif self.data is None:
            data_list = []
        else:
            # For other types, wrap in dict
            data_list = [{"value": self.data}]
        
        # Add agent name to metadata
        metadata = self.metadata or {}
        metadata["agent_name"] = self.agent_name
        
        if self.error:
            return StandardResponse.error_response(self.error, metadata)
        else:
            return StandardResponse.success_response(data_list, self.cached, metadata)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        result = {
            "success": self.success,
            "data": self.data,
            "agent_name": self.agent_name,
            "cached": self.cached,
            "timestamp": self.timestamp
        }
        
        if self.metadata:
            result["metadata"] = self.metadata
        
        if self.error:
            result["error"] = self.error
        
        return result


def ensure_standard_format(response: Any) -> Dict[str, Any]:
    """Ensure any response is in standard format
    
    Helper function to handle legacy response formats and convert
    them to the standard format. Useful during migration period.
    
    Args:
        response: Response in any format (dict, list, StandardResponse, etc.)
        
    Returns:
        Dict in standard format
        
    Example:
        # Handle various formats
        result = ensure_standard_format(legacy_response)
        # Always returns {"success": bool, "data": [...], ...}
    """
    # Already a StandardResponse
    if isinstance(response, StandardResponse):
        return response.to_dict()
    
    # Already a dict with success key
    if isinstance(response, dict) and "success" in response:
        # Ensure required fields exist
        return {
            "success": response.get("success", False),
            "data": response.get("data", []),
            "count": response.get("count", len(response.get("data", []))),
            "cached": response.get("cached", False),
            "timestamp": response.get("timestamp", datetime.utcnow().isoformat()),
            "metadata": response.get("metadata"),
            "error": response.get("error")
        }
    
    # Legacy list format
    if isinstance(response, list):
        return StandardResponse.success_response(response).to_dict()
    
    # Legacy dict without success key
    if isinstance(response, dict):
        # Treat as single item
        return StandardResponse.success_response([response]).to_dict()
    
    # Unknown format
    return StandardResponse.error_response(
        "Invalid response format",
        metadata={"response_type": type(response).__name__}
    ).to_dict()
