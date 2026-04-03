"""
Standardized response models for API endpoints
Ensures consistent data format across all endpoints
"""
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union
from datetime import datetime


_COLLECTION_COUNT_KEYS = (
    "items",
    "results",
    "vendors",
    "runs",
    "responses",
    "records",
    "entries",
    "resources",
    "objects",
    "rows",
)


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
            metadata={"source": "database"}
        )
        
        # Error response
        response = StandardResponse.error_response(
            error="Database connection failed",
            metadata={"retry_count": 3}
        )
    """
    success: bool
    data: Union[List[Dict[str, Any]], Dict[str, Any], Any] = field(default_factory=list)
    count: int = 0
    cached: bool = False
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    metadata: Optional[Dict[str, Any]] = None
    message: Optional[str] = None
    error: Optional[str] = None

    @staticmethod
    def derive_count(data: Any) -> int:
        """Infer a stable count value for common payload shapes."""
        if data is None:
            return 0
        if isinstance(data, list):
            return len(data)
        if isinstance(data, dict):
            return 1
        return 1
    
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
        
        if self.message:
            result["message"] = self.message

        if self.error:
            result["error"] = self.error
        
        return result
    
    @classmethod
    def success_response(
        cls,
        data: Union[List[Any], Dict[str, Any], None],
        cached: bool = False,
        metadata: Optional[Dict[str, Any]] = None,
        message: Optional[str] = None,
        count: Optional[int] = None,
    ) -> "StandardResponse":
        """Create a successful response
        
        Args:
            data: Response payload, typically a list or dict depending on the endpoint contract
            cached: Whether data came from cache
            metadata: Optional metadata about the response
            count: Optional explicit count override for wrapped collection payloads
            
        Returns:
            StandardResponse instance
        """
        return cls(
            success=True,
            data=data,
            count=cls.derive_count(data) if count is None else count,
            cached=cached,
            metadata=metadata,
            message=message,
        )
    
    @classmethod
    def error_response(
        cls,
        error: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        message: Optional[str] = None,
        *,
        error_message: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> "StandardResponse":
        """Create an error response
        
        Args:
            error: Error message
            metadata: Optional metadata about the error
            
        Returns:
            StandardResponse instance with error
        """
        error_text = error or error_message or "Unknown error"

        merged_metadata = metadata.copy() if metadata else {}
        if details:
            merged_metadata.update(details)

        return cls(
            success=False,
            data=[],
            count=0,
            error=error_text,
            metadata=merged_metadata or None,
            message=message,
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

    Note:
        Dict responses with a ``success`` field but no explicit ``data`` field are
        normalized by moving their non-standard fields into ``data``.
    """
    def infer_wrapped_dict_count(data: Dict[str, Any]) -> int:
        for key in _COLLECTION_COUNT_KEYS:
            value = data.get(key)
            if isinstance(value, list):
                return len(value)
        return StandardResponse.derive_count(data)

    # Already a StandardResponse
    if isinstance(response, StandardResponse):
        return response.to_dict()
    
    # Already a dict with success key
    if isinstance(response, dict) and "success" in response:
        if "data" in response:
            data = response.get("data", [])
            count = response.get(
                "count",
                infer_wrapped_dict_count(data) if isinstance(data, dict) else StandardResponse.derive_count(data),
            )
        else:
            standard_fields = {
                "success",
                "data",
                "count",
                "cached",
                "timestamp",
                "metadata",
                "message",
                "error",
            }
            data = {key: value for key, value in response.items() if key not in standard_fields}
            count = response.get("count", infer_wrapped_dict_count(data))

        return {
            "success": response.get("success", False),
            "data": data,
            "count": count,
            "cached": response.get("cached", False),
            "timestamp": response.get("timestamp", datetime.utcnow().isoformat()),
            "metadata": response.get("metadata"),
            "message": response.get("message"),
            "error": response.get("error")
        }
    
    # Legacy list format
    if isinstance(response, list):
        return StandardResponse.success_response(response).to_dict()
    
    # Legacy dict without success key
    if isinstance(response, dict):
        return StandardResponse.success_response(
            response,
            count=infer_wrapped_dict_count(response),
        ).to_dict()
    
    # Unknown format
    return StandardResponse.error_response(
        "Invalid response format",
        metadata={"response_type": type(response).__name__}
    ).to_dict()
