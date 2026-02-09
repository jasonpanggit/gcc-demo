"""
Cosmos-backed table for standardized EOL results.

This module provides persistent storage and retrieval for End-of-Life (EOL) data
using Azure Cosmos DB. It serves as the single source of truth for all EOL records.

Key Features:
    - Normalized EOL data storage with consistent schema
    - Confidence-based record updates (only higher confidence overwrites)
    - Efficient querying by software name and version
    - Support for pagination and filtering
    - Automatic timestamp tracking for created/updated records

Constants:
    DEFAULT_CONTAINER_ID: Default Cosmos DB container name
    DEFAULT_TTL_DAYS: Default time-to-live in days (30)
    DEFAULT_OFFER_THROUGHPUT: Default RU/s for container (400)
    PARTITION_PATH: Partition key path for the container
    DEFAULT_CONFIDENCE: Default confidence value when missing (0.0)
    DEFAULT_LIST_LIMIT: Default number of records to return (100)
    MIN_LIST_LIMIT: Minimum allowed list limit (1)
    MIN_LIST_OFFSET: Minimum allowed list offset (0)

Usage:
    from utils.eol_inventory import eol_inventory
    
    # Get EOL data
    result = await eol_inventory.get('Python', '3.9')
    
    # Store EOL data
    success = await eol_inventory.upsert('Python', '3.9', response_data)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any, Dict, Optional, List

from .cosmos_cache import base_cosmos

logger = logging.getLogger(__name__)

# Constants for configuration
DEFAULT_CONTAINER_ID: str = "eol_table"
DEFAULT_TTL_DAYS: int = 30
DEFAULT_OFFER_THROUGHPUT: int = 400
PARTITION_PATH: str = "/software_key"
DEFAULT_CONFIDENCE: float = 0.0
DEFAULT_LIST_LIMIT: int = 100
MIN_LIST_LIMIT: int = 1
MIN_LIST_OFFSET: int = 0


@dataclass
class EolRecord:
    """Data structure for standardized EOL records.
    
    This class represents a complete EOL record with all relevant fields
    for tracking software end-of-life information.
    
    Attributes:
        id (str): Unique identifier (software_name:version)
        software_key (str): Normalized software name for querying
        version_key (str): Normalized version string
        software_name (str): Display name of the software
        version (Optional[str]): Version string or None
        eol_date (Optional[str]): End-of-life date in ISO format
        support_end_date (Optional[str]): Support end date in ISO format
        release_date (Optional[str]): Release date in ISO format
        status (Optional[str]): Current status (e.g., 'active', 'eol')
        risk_level (Optional[str]): Risk assessment level
        confidence (Optional[float]): Confidence score (0-100)
        source (Optional[str]): Data source identifier
        source_url (Optional[str]): URL of the source
        agent_used (Optional[str]): Agent that provided the data
        data (Dict[str, Any]): Complete raw response data
        created_at (str): ISO timestamp when created
        updated_at (Optional[str]): ISO timestamp when last updated
        ttl (Optional[int]): Time-to-live in seconds (None = no expiry)
    """
    id: str
    software_key: str
    version_key: str
    software_name: str
    version: Optional[str]
    eol_date: Optional[str]
    support_end_date: Optional[str]
    release_date: Optional[str]
    status: Optional[str]
    risk_level: Optional[str]
    confidence: Optional[float]
    source: Optional[str]
    source_url: Optional[str]
    agent_used: Optional[str]
    data: Dict[str, Any]
    created_at: str
    updated_at: Optional[str] = None
    ttl: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert the record to a dictionary for storage.
        
        Returns:
            Dict[str, Any]: Dictionary representation, excluding None ttl
        """
        doc = asdict(self)
        if doc.get("ttl") is None:
            doc.pop("ttl", None)
        return doc

    @classmethod
    def from_dict(cls, doc: Dict[str, Any]) -> "EolRecord":
        """Create an EolRecord from a Cosmos DB document.
        
        Args:
            doc (Dict[str, Any]): Document from Cosmos DB
            
        Returns:
            EolRecord: Instance created from the dictionary
        """
        filtered = {
            k: v for k, v in doc.items() if not k.startswith("_") and k != "expires_at"
        }
        return cls(**filtered)

    def to_cached_response(self) -> Dict[str, Any]:
        """Return orchestrator-friendly cached response format.
        
        Converts the internal record format to the format expected by
        the EOL orchestrator and other consuming services.
        
        Returns:
            Dict[str, Any]: Response dictionary with standard fields
        """
        response_data = self.data or {}
        if isinstance(response_data, dict):
            response_data.setdefault("success", True)
        
        return {
            "success": True,
            "source": self.source or "eol_inventory",
            "agent_used": self.agent_used or self.source or "eol_inventory",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "cached": True,
            "cache_source": "cosmos_eol_table",
            "cache_created_at": self.created_at,
            "data": response_data,
        }


class EolInventory:
    """Lightweight Cosmos helper for standardized EOL records."""

    def __init__(self, container_id: str = "eol_table", default_ttl_days: int = 30):
        self.container_id = container_id
        self.default_ttl_days = default_ttl_days
        # Disable TTL-based expiration in Cosmos; keep defaults for backward compatibility.
        self.default_ttl_seconds: Optional[int] = None
        self.container = None
        self.initialized = False
        self.hit_count = 0
        self.miss_count = 0

    async def initialize(self) -> None:
        if self.initialized:
            return
        try:
            await base_cosmos._initialize_async()
            self.container = base_cosmos.get_container(
                self.container_id,
                partition_path="/software_key",
                offer_throughput=400,
                default_ttl=self.default_ttl_seconds,
            )
            self.initialized = True
            logger.info("✅ EOL table ready (container %s)", self.container_id)
        except Exception as exc:
            logger.warning("EOL table initialization failed: %s", exc)
            self.initialized = False

    def _normalize_name(self, name: str) -> str:
        """Normalize software name for consistent querying.
        
        Args:
            name (str): Software name to normalize
            
        Returns:
            str: Lowercase, trimmed software name
        """
        return (name or "").strip().lower()

    def _normalize_version(self, version: Optional[str]) -> str:
        """Normalize version string for consistent querying.
        
        Args:
            version (Optional[str]): Version string to normalize
            
        Returns:
            str: Lowercase, trimmed version or 'any' if None
        """
        return (version or "any").strip().lower()

    def _build_id(self, software_name: str, version: Optional[str]) -> str:
        """Build a unique record ID from software name and version.
        
        Args:
            software_name (str): Software name
            version (Optional[str]): Version string
            
        Returns:
            str: Unique ID in format 'name:version'
        """
        return f"{self._normalize_name(software_name)}:{self._normalize_version(version)}"

    def _confidence_value(self, value: Optional[float]) -> float:
        """Extract and validate confidence value.
        
        Args:
            value (Optional[float]): Confidence value to validate
            
        Returns:
            float: Valid confidence value or 0.0 if invalid
        """
        try:
            if value is None:
                return DEFAULT_CONFIDENCE
            return float(value)
        except (TypeError, ValueError):
            return DEFAULT_CONFIDENCE

    def _standardize_data(
        self, 
        software_name: str, 
        version: Optional[str], 
        result: Dict[str, Any]
    ) -> Optional[EolRecord]:
        """Convert raw result data into standardized EolRecord format.
        
        This method extracts and normalizes all relevant fields from the
        raw response data into a consistent EolRecord structure.
        
        Args:
            software_name (str): Software name
            version (Optional[str]): Version string
            result (Dict[str, Any]): Raw result data from agent
            
        Returns:
            Optional[EolRecord]: Standardized record or None if invalid
        """
        if not result or not result.get("success"):
            return None
        """Insert or update an EOL record with confidence-based replacement.
        
        This method only updates existing records if the incoming data has
        higher confidence than the current record.
        
        Args:
            software_name (str): Software name
            version (Optional[str]): Version string
            result (Dict[str, Any]): Raw result data from agent
            
        Returns:
            bool: True if upsert succeeded, False otherwise
        
        Example:
            >>> success = await inventory.upsert('Python', '3.9', {
            >>>     'success': True,
            >>>     'data': {'eol_date': '2025-10-05', 'confidence': 95}
            >>> })
        """

        data = result.get("data") or {}
        if not isinstance(data, dict):
            return None

        software_key = self._normalize_name(data.get("software_name") or software_name)
        version_key = self._normalize_version(data.get("version") or version)
        now = datetime.now(timezone.utc)
        record = EolRecord(
            id=self._build_id(software_name, version),
            software_key=software_key,
            version_key=version_key,
            software_name=data.get("software_name") or software_name,
            version=data.get("version") or version,
            eol_date=data.get("eol_date"),
            support_end_date=data.get("support_end_date") or data.get("support"),
            release_date=data.get("release_date"),
            status=data.get("status"),
            risk_level=data.get("risk_level"),
            confidence=data.get("confidence") or result.get("confidence"),
            source=data.get("source") or result.get("source"),
            source_url=data.get("source_url") or result.get("source_url"),
            agent_used=data.get("agent_used") or result.get("agent_used"),
            data=data,
            created_at=now.isoformat(),
            updated_at=now.isoformat(),
            ttl=None,
        )
        return record

    async def get(self, software_name: str, version: Optional[str]) -> Optional[Dict[str, Any]]:
        await self.initialize()
        if not self.container:
            return None
        try:
            software_key = self._normalize_name(software_name)
            version_key = self._normalize_version(version)
            
            logger.debug(
                f"EOL cache query: software_name='{software_name}' -> key='{software_key}', "
                f"version='{version}' -> key='{version_key}'"
            )
            
            query = (
                "SELECT * FROM c WHERE c.software_key = @software_key "
                "AND c.version_key = @version_key"
            )
            params = [
                {"name": "@software_key", "value": software_key},
                {"name": "@version_key", "value": version_key},
            ]
            items = list(
                self.container.query_items(
                    query=query,
                    parameters=params,
                    enable_cross_partition_query=True,
                )
            )
            if not items:
                self.miss_count += 1
                logger.debug("EOL table miss for %s %s", software_name, version or "(any)")
                return None

            items.sort(key=lambda doc: doc.get("created_at", ""), reverse=True)
            record = EolRecord.from_dict(items[0])
            # Basic expiration check in case TTL is not enforced yet
            self.hit_count += 1
            logger.debug(
                f"EOL table hit for {software_name} {version or '(any)'}: "
                f"eol_date={record.eol_date}, confidence={record.confidence}, source={record.source}"
            )
            return record.to_cached_response()
        except Exception as exc:
            logger.debug("EOL table read failed: %s", exc)
            return None

    async def upsert(self, software_name: str, version: Optional[str], result: Dict[str, Any]) -> bool:
        """Upsert an EOL record with confidence-based overwrite logic.
        
        Stores or updates an EOL record in the database. Only overwrites
        existing records if the new data has higher confidence.
        
        Args:
            software_name (str): Name of the software product
            version (Optional[str]): Version string
            result (Dict[str, Any]): EOL data to store
            
        Returns:
            bool: True if successful, False otherwise
        """
        await self.initialize()
        if not self.container:
            logger.warning("EOL table upsert skipped: container not initialized")
            return False

        record = self._standardize_data(software_name, version, result)
        if not record:
            return False

        try:
            existing = None
            try:
                existing = self.container.read_item(
                    item=record.id,
                    partition_key=record.software_key,
                )
            except Exception:
                existing = None

            if existing:
                existing_confidence = self._confidence_value(existing.get("confidence"))
                incoming_confidence = self._confidence_value(record.confidence)
                
                # Only overwrite if incoming confidence is strictly higher
                if incoming_confidence <= existing_confidence:
                    logger.info(
                        f"⏭️ Skipping EOL upsert for {record.software_name} {record.version or 'any'}: "
                        f"existing confidence ({existing_confidence:.2f}) >= incoming ({incoming_confidence:.2f})"
                    )
                    return True
                
                logger.info(
                    f"📝 Updating EOL record for {record.software_name} {record.version or 'any'}: "
                    f"confidence improved from {existing_confidence:.2f} to {incoming_confidence:.2f}"
                )

            record_dict = record.to_dict()
            if existing:
                record_dict["updated_at"] = datetime.now(timezone.utc).isoformat()
                self.container.replace_item(item=record.id, body=record_dict)
                logger.info(f"✅ Updated EOL record: {record.software_name} {record.version or 'any'}")
            else:
                self.container.upsert_item(record_dict)
                logger.info(f"✅ Created new EOL record: {record.software_name} {record.version or 'any'} (confidence: {record.confidence or 0:.2f})")
            return True
        except Exception as exc:
            logger.debug("EOL table upsert failed: %s", exc)
            return False

    async def update_record(self, record_id: str, software_key: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Update specific fields in an existing EOL record.
        
        Args:
            record_id (str): Unique record identifier
            software_key (str): Partition key
            updates (Dict[str, Any]): Fields to update
            
        Returns:
            Optional[Dict[str, Any]]: Updated record or None if failed
        """
        await self.initialize()
        if not self.container:
            return None

        allowed = {
            "software_name",
            "version",
            "eol_date",
            "support_end_date",
            "release_date",
            "status",
            "risk_level",
            "confidence",
            "source",
            "source_url",
            "agent_used",
        }

        try:
            doc = self.container.read_item(item=record_id, partition_key=software_key)
        except Exception as exc:
            logger.debug("EOL table update read failed: %s", exc)
            return None

        for key, value in updates.items():
            if key in allowed:
                doc[key] = value
                if isinstance(doc.get("data"), dict):
                    doc["data"][key] = value

        doc["updated_at"] = datetime.now(timezone.utc).isoformat()

        try:
            self.container.replace_item(item=record_id, body=doc)
            record = EolRecord.from_dict(doc)
            return {
                "id": record.id,
                "software_key": record.software_key,
                "software_name": record.software_name,
                "version": record.version,
                "eol_date": record.eol_date,
                "support_end_date": record.support_end_date,
                "release_date": record.release_date,
                "status": record.status,
                "risk_level": record.risk_level,
                "confidence": record.confidence,
                "source": record.source,
                "source_url": record.source_url,
                "agent_used": record.agent_used,
                "updated_at": doc.get("updated_at"),
            }
        except Exception as exc:
            logger.debug("EOL table update failed: %s", exc)
            return None

    def get_stats(self) -> Dict[str, int]:
        """Get cache hit/miss statistics.
        
        Returns:
            Dict[str, int]: Dictionary with 'hits' and 'misses' counts
        """
        return {"hits": self.hit_count, "misses": self.miss_count}

    async def count_records(
        self,
        *,
        software_name: Optional[str] = None,
        version: Optional[str] = None,
    ) -> int:
        """Count total EOL records matching the filters.
        
        Args:
            software_name (Optional[str]): Filter by software name
            version (Optional[str]): Filter by version
            
        Returns:
            int: Number of matching records
        
        Example:
            >>> count = await inventory.count_records(software_name='Python')
            >>> print(f"Found {count} Python records")
        """
        await self.initialize()
        if not self.container:
            return False
        try:
            self.container.delete_item(item=record_id, partition_key=software_key)
            return True
        except Exception as exc:
            logger.debug("EOL table delete failed: %s", exc)
            return False

    async def delete_record(self, record_id: str, software_key: str) -> bool:
        """Delete a single EOL record from Cosmos DB.
        
        Args:
            record_id (str): The record ID to delete
            software_key (str): The partition key (software_key)
            
        Returns:
            bool: True if deleted successfully, False otherwise
        """
        await self.initialize()
        if not self.container:
            logger.warning("EOL table delete skipped: container not initialized")
            return False
        
        try:
            self.container.delete_item(item=record_id, partition_key=software_key)
            logger.info(f"✅ Deleted EOL record: {record_id}")
            return True
        except Exception as exc:
            logger.debug("EOL table delete failed for %s: %s", record_id, exc)
            return False

    async def delete_records(self, items: List[Dict[str, str]]) -> Dict[str, Any]:
        await self.initialize()
        if not self.container:
            return {
                "deleted": 0,
                "failed": [
                    {"item": item, "error": "Container not initialized"}
                    for item in items
                ],
            }

        deleted = 0
        failed = []
        for item in items:
            record_id = item.get("record_id") if isinstance(item, dict) else None
            software_key = item.get("software_key") if isinstance(item, dict) else None
            if not record_id or not software_key:
                failed.append({"item": item, "error": "Missing record_id or software_key"})
                continue
            try:
                self.container.delete_item(item=record_id, partition_key=software_key)
                deleted += 1
            except Exception as exc:
                logger.debug("EOL table bulk delete failed for %s: %s", record_id, exc)
                failed.append({"item": item, "error": str(exc)})

        return {"deleted": deleted, "failed": failed}

    def get_stats(self) -> Dict[str, int]:
        """Get cache hit/miss statistics.
        
        Returns:
            Dict[str, int]: Dictionary with 'hits' and 'misses' counts
        """
        return {"hits": self.hit_count, "misses": self.miss_count}

    async def count_records(
        self,
        *,
        software_name: Optional[str] = None,
        version: Optional[str] = None,
    ) -> int:
        """Count total EOL records matching the filters.
        
        Args:
            software_name (Optional[str]): Filter by software name
            version (Optional[str]): Filter by version
            
        Returns:
            int: Number of matching records
        """
        await self.initialize()
        if not self.container:
            return 0

        conditions = []
        params = []

        if software_name:
            software_key = self._normalize_name(software_name)
            conditions.append("c.software_key = @software_key")
            params.append({"name": "@software_key", "value": software_key})

        if version:
            version_key = self._normalize_version(version)
            conditions.append("c.version_key = @version_key")
            params.append({"name": "@version_key", "value": version_key})

        query = "SELECT VALUE COUNT(1) FROM c"
        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        try:
            items_iter = self.container.query_items(
                query=query,
                parameters=params,
                enable_cross_partition_query=True,
            )
            result = list(items_iter)
            return result[0] if result else 0
        except Exception as exc:
            logger.debug("EOL table count query failed: %s", exc)
            return 0

    async def list_recent(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
        software_name: Optional[str] = None,
        version: Optional[str] = None,
    ) -> tuple[list[Dict[str, Any]], int]:
        """Return recent EOL records for UI/debug views with pagination.
        
        Args:
            limit: Number of records to return
            offset: Number of records to skip (for pagination)
            software_name: Filter by software name
            version: Filter by version
            
        Returns:
            Tuple of (records list, total count matching filters)
        """
        await self.initialize()
        if not self.container:
            return [], 0

        safe_limit = max(1, limit)
        safe_offset = max(0, offset)

        conditions = []
        params = []

        if software_name:
            software_key = self._normalize_name(software_name)
            conditions.append("c.software_key = @software_key")
            params.append({"name": "@software_key", "value": software_key})

        if version:
            version_key = self._normalize_version(version)
            conditions.append("c.version_key = @version_key")
            params.append({"name": "@version_key", "value": version_key})

        # Get total count
        total_count = await self.count_records(
            software_name=software_name,
            version=version,
        )

        query = "SELECT * FROM c"
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY c._ts DESC"
        query += f" OFFSET {safe_offset} LIMIT {safe_limit}"

        records: list[Dict[str, Any]] = []
        try:
            items_iter = self.container.query_items(
                query=query,
                parameters=params,
                enable_cross_partition_query=True,
            )

            for doc in items_iter:

                try:
                    record = EolRecord.from_dict(doc)
                    records.append(
                        {
                            "id": record.id,
                            "software_key": record.software_key,
                            "version_key": record.version_key,
                            "software_name": record.software_name,
                            "version": record.version,
                            "eol_date": record.eol_date,
                            "support_end_date": record.support_end_date,
                            "release_date": record.release_date,
                            "status": record.status,
                            "risk_level": record.risk_level,
                            "confidence": record.confidence,
                            "source": record.source,
                            "source_url": record.source_url,
                            "agent_used": record.agent_used,
                            "created_at": record.created_at,
                            "updated_at": record.updated_at,
                        }
                    )
                except Exception as record_exc:
                    logger.debug("EOL table record parse failed: %s", record_exc)
                    continue
        except Exception as exc:
            logger.debug("EOL table query failed: %s", exc)

        return records, total_count


eol_inventory = EolInventory()
