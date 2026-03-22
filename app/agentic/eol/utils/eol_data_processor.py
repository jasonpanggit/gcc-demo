"""EOL data processing helpers extracted from EOLOrchestratorAgent.

These functions process and standardize raw EOL data returned by agents/pipeline
into a normalized shape suitable for the frontend and database persistence.
"""
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


def extract_eol_date(data: Dict[str, Any]) -> Optional[str]:
    """Extract EOL date from various data formats."""
    date_fields = [
        "eol_date",
        "end_of_life",
        "eol",
        "support_end",
        "support_end_date",
        "support",
        "end_date",
        "retirement_date",
    ]
    for field in date_fields:
        if field in data and data[field]:
            date_value = data[field]
            if isinstance(date_value, str):
                return date_value
            if isinstance(date_value, datetime):
                return date_value.isoformat()
    return None


def extract_support_end_date(data: Dict[str, Any]) -> Optional[str]:
    """Extract support end date from known fields."""
    support_fields = [
        "support_end_date",
        "support_end",
        "support",
        "extended_support_end",
        "extended_support",
    ]
    for field in support_fields:
        if field in data and data[field]:
            value = data[field]
            if isinstance(value, str):
                return value
            if isinstance(value, datetime):
                return value.isoformat()
    return None


def process_eol_data(raw_data: Dict[str, Any], software_name: str, version: Optional[str]) -> Dict[str, Any]:
    """Process and standardize EOL data from various sources."""
    processed = {
        "software_name": software_name,
        "version": version,
        "eol_date": extract_eol_date(raw_data),
        "support_end_date": extract_support_end_date(raw_data),
        "status": "Unknown",
        "support_status": raw_data.get("support_status", "Unknown"),
        "risk_level": "unknown",
        "days_until_eol": None,
        "source": raw_data.get("source", "Unknown"),
        "confidence": raw_data.get("confidence", 0.5),
    }

    # If EOL is missing but we have support end, treat support end as primary lifecycle date
    if not processed["eol_date"] and processed["support_end_date"]:
        processed["eol_date"] = processed["support_end_date"]

    # Calculate risk level and days until EOL
    if processed["eol_date"]:
        try:
            eol_date = datetime.fromisoformat(processed["eol_date"].replace("Z", "+00:00"))
            now = datetime.now(timezone.utc)
            if eol_date.tzinfo is None:
                eol_date = eol_date.replace(tzinfo=timezone.utc)
            days_diff = (eol_date - now).days

            processed["days_until_eol"] = days_diff

            if days_diff < 0:
                processed["status"] = "End of Life"
                processed["risk_level"] = "critical"
            elif days_diff <= 90:
                processed["status"] = "Critical - EOL Soon"
                processed["risk_level"] = "critical"
            elif days_diff <= 365:
                processed["status"] = "High Risk - EOL Within 1 Year"
                processed["risk_level"] = "high"
            elif days_diff <= 730:
                processed["status"] = "Medium Risk - EOL Within 2 Years"
                processed["risk_level"] = "medium"
            else:
                processed["status"] = "Active Support"
                processed["risk_level"] = "low"

        except Exception as e:
            logger.warning("Error calculating EOL risk for %s: %s", software_name, str(e))

    return processed
