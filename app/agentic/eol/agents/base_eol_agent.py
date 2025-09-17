"""
Base EOL Agent class that enforces standardized response formats
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class BaseEOLAgent(ABC):
    """Base class for all EOL agents with standardized response format"""
    
    def __init__(self, agent_name=None):
        self.agent_name = agent_name or self.__class__.__name__.replace('EOLAgent', '').lower()
    
    @abstractmethod
    async def get_eol_data(self, software_name: str, version: Optional[str] = None, **kwargs) -> Dict[str, Any]:
        """
        Abstract method that each agent must implement.
        Must return a standardized response format.
        
        Args:
            software_name: Name of the software to check
            version: Optional version to check
            **kwargs: Additional parameters that specific agents may need (e.g., technology_context)
        """
        pass
    
    def create_success_response(self, 
                              software_name: str, 
                              version: Optional[str] = None,
                              eol_date: Optional[str] = None,
                              support_end_date: Optional[str] = None,
                              release_date: Optional[str] = None,
                              status: Optional[str] = None,
                              risk_level: Optional[str] = None,
                              confidence: float = 0.8,
                              source_url: Optional[str] = None,
                              additional_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Create a standardized success response
        """
        response = {
            "success": True,
            "source": self.agent_name,
            "timestamp": datetime.utcnow().isoformat(),
            "data": {
                "software_name": software_name,
                "version": version,
                "eol_date": eol_date,
                "support_end_date": support_end_date,
                "release_date": release_date,
                "status": status or self._determine_status(eol_date),
                "risk_level": risk_level or self._determine_risk_level(eol_date),
                "confidence": confidence,
                "source_url": source_url,
                "agent_used": self.agent_name,  # Add agent_used field for frontend compatibility
                "days_until_eol": self._calculate_days_until_eol(eol_date)
            }
        }
        
        # Add any additional data
        if additional_data:
            response["data"].update(additional_data)
            
        return response
    
    def create_failure_response(self, 
                              software_name: str, 
                              version: Optional[str] = None,
                              error_message: str = "No EOL data found",
                              error_code: Optional[str] = None) -> Dict[str, Any]:
        """
        Create a standardized failure response
        """
        return {
            "success": False,
            "source": self.agent_name,
            "timestamp": datetime.utcnow().isoformat(),
            "error": {
                "message": error_message,
                "code": error_code,
                "software_name": software_name,
                "version": version,
                "agent_used": self.agent_name  # Add agent_used field for frontend compatibility
            },
            "data": None
        }
    
    def _determine_status(self, eol_date: Optional[str]) -> str:
        """Determine status based on EOL date"""
        if not eol_date:
            return "Unknown"
        
        try:
            eol = datetime.fromisoformat(eol_date.replace('Z', '+00:00'))
            now = datetime.utcnow().replace(tzinfo=eol.tzinfo)
            days_diff = (eol - now).days
            
            if days_diff < 0:
                return "End of Life"
            elif days_diff <= 90:
                return "Critical - EOL Soon"
            elif days_diff <= 365:
                return "High Risk - EOL Within 1 Year"
            elif days_diff <= 730:
                return "Medium Risk - EOL Within 2 Years"
            else:
                return "Active Support"
        except Exception:
            return "Unknown"
    
    def _determine_risk_level(self, eol_date: Optional[str]) -> str:
        """Determine risk level based on EOL date"""
        if not eol_date:
            return "unknown"
        
        try:
            eol = datetime.fromisoformat(eol_date.replace('Z', '+00:00'))
            now = datetime.utcnow().replace(tzinfo=eol.tzinfo)
            days_diff = (eol - now).days
            
            if days_diff < 0:
                return "critical"
            elif days_diff <= 90:
                return "critical"
            elif days_diff <= 365:
                return "high"
            elif days_diff <= 730:
                return "medium"
            else:
                return "low"
        except Exception:
            return "unknown"
    
    def _calculate_days_until_eol(self, eol_date: Optional[str]) -> Optional[int]:
        """Calculate days until EOL"""
        if not eol_date:
            return None
        
        try:
            eol = datetime.fromisoformat(eol_date.replace('Z', '+00:00'))
            now = datetime.utcnow().replace(tzinfo=eol.tzinfo)
            return (eol - now).days
        except Exception:
            return None
    
    def normalize_legacy_response(self, legacy_response: Dict[str, Any], software_name: str, version: Optional[str] = None) -> Dict[str, Any]:
        """
        Convert legacy response formats to standardized format
        """
        try:
            # If already in standard format, return as-is
            if "success" in legacy_response and "data" in legacy_response:
                return legacy_response
            
            # Handle endoflife.date format
            if "data" in legacy_response and "source" in legacy_response:
                data = legacy_response.get("data", {})
                return self.create_success_response(
                    software_name=software_name,
                    version=version,
                    eol_date=data.get("eol"),
                    support_end_date=data.get("support"),
                    release_date=data.get("release"),
                    confidence=legacy_response.get("confidence_level", 80) / 100.0,
                    source_url=legacy_response.get("source_url"),
                    additional_data={
                        "cycle": data.get("cycle"),
                        "lts": data.get("lts"),
                        "latest": data.get("latest")
                    }
                )
            
            # Handle Microsoft agent format
            if "cycle" in legacy_response and "eol" in legacy_response:
                return self.create_success_response(
                    software_name=software_name,
                    version=legacy_response.get("cycle"),
                    eol_date=legacy_response.get("eol"),
                    support_end_date=legacy_response.get("support"),
                    confidence=0.9,
                    additional_data={
                        "cycle": legacy_response.get("cycle"),
                        "extendedSupport": legacy_response.get("extendedSupport")
                    }
                )
            
            # If no recognizable format, treat as failure
            return self.create_failure_response(
                software_name=software_name,
                version=version,
                error_message="Unrecognized response format"
            )
            
        except Exception as e:
            logger.error(f"Error normalizing legacy response: {str(e)}")
            return self.create_failure_response(
                software_name=software_name,
                version=version,
                error_message=f"Error normalizing response: {str(e)}"
            )
