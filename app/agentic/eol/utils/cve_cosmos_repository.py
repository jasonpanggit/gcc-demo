"""
Cosmos DB repository for CVE data persistence.

Handles CRUD operations for UnifiedCVE models in Cosmos DB.
"""
from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Optional, List, Dict, Any

try:
    from azure.cosmos import exceptions as cosmos_exceptions
    from azure.cosmos.aio import CosmosClient
    COSMOS_IMPORTS_OK = True
except Exception:
    COSMOS_IMPORTS_OK = False

try:
    from models.cve_models import UnifiedCVE
    from utils.logging_config import get_logger
except ModuleNotFoundError:
    from app.agentic.eol.models.cve_models import UnifiedCVE
    from app.agentic.eol.utils.logging_config import get_logger


logger = get_logger(__name__)


CVE_DATA_INDEXING_POLICY: Dict[str, Any] = {
    "indexingMode": "consistent",
    "automatic": True,
    "includedPaths": [{"path": "/*"}],
    "excludedPaths": [{"path": "/\"_etag\"/?"}],
    "compositeIndexes": [
        [
            {"path": "/published_date", "order": "ascending"},
            {"path": "/cve_id", "order": "ascending"},
        ],
        [
            {"path": "/published_date", "order": "descending"},
            {"path": "/cve_id", "order": "descending"},
        ],
        [
            {"path": "/last_modified_date", "order": "ascending"},
            {"path": "/cve_id", "order": "ascending"},
        ],
        [
            {"path": "/last_modified_date", "order": "descending"},
            {"path": "/cve_id", "order": "descending"},
        ],
        [
            {"path": "/cvss_v3/base_score", "order": "ascending"},
            {"path": "/cve_id", "order": "ascending"},
        ],
        [
            {"path": "/cvss_v3/base_score", "order": "descending"},
            {"path": "/cve_id", "order": "descending"},
        ],
        [
            {"path": "/cvss_v3/base_severity", "order": "ascending"},
            {"path": "/cvss_v3/base_score", "order": "ascending"},
            {"path": "/cve_id", "order": "ascending"},
        ],
        [
            {"path": "/cvss_v3/base_severity", "order": "descending"},
            {"path": "/cvss_v3/base_score", "order": "descending"},
            {"path": "/cve_id", "order": "descending"},
        ],
    ],
}


class CVECosmosRepository:
    """Repository for persisting CVE data to Cosmos DB.

    Container: cve_data
    Partition key: /cve_id
    """

    def __init__(self, cosmos_client, database_name: str, container_name: str = "cve_data"):
        if not COSMOS_IMPORTS_OK:
            raise ImportError("Azure Cosmos DB SDK not available")

        self.cosmos_client = cosmos_client
        self.database_name = database_name
        self.container_name = container_name
        self._container = None

    async def _get_container(self):
        """Get container client (lazy initialization)."""
        if self._container is None:
            database = self.cosmos_client.get_database_client(self.database_name)
            self._container = database.get_container_client(self.container_name)
        return self._container

    async def upsert_cve(self, cve: UnifiedCVE) -> None:
        """Insert or update CVE record.

        Args:
            cve: UnifiedCVE model to persist

        Raises:
            cosmos_exceptions.CosmosHttpResponseError: On Cosmos DB errors
        """
        container = await self._get_container()

        # Convert Pydantic model to dict for Cosmos DB
        doc = cve.model_dump()

        # Ensure id field matches partition key (cve_id)
        doc["id"] = cve.cve_id

        # Convert datetime objects to ISO strings
        doc["published_date"] = cve.published_date.isoformat()
        doc["last_modified_date"] = cve.last_modified_date.isoformat()
        doc["last_synced"] = cve.last_synced.isoformat()

        try:
            await asyncio.to_thread(container.upsert_item, doc)
            logger.debug(f"Upserted CVE {cve.cve_id} to Cosmos DB")
        except cosmos_exceptions.CosmosHttpResponseError as e:
            logger.error(f"Failed to upsert CVE {cve.cve_id}: {e}")
            raise

    async def get_cve(self, cve_id: str) -> Optional[UnifiedCVE]:
        """Retrieve CVE by ID.

        Args:
            cve_id: CVE identifier

        Returns:
            UnifiedCVE model or None if not found
        """
        container = await self._get_container()
        cve_id = cve_id.upper()

        try:
            response = await asyncio.to_thread(
                container.read_item,
                item=cve_id,
                partition_key=cve_id
            )

            # Convert Cosmos doc back to Pydantic model
            return self._doc_to_model(response)

        except cosmos_exceptions.CosmosResourceNotFoundError:
            logger.debug(f"CVE {cve_id} not found in Cosmos DB")
            return None
        except Exception as e:
            logger.error(f"Failed to get CVE {cve_id}: {e}")
            return None

    async def query_cves(
        self,
        filters: Dict[str, Any],
        limit: int = 100,
        offset: int = 0,
        sort_by: str = "published_date",
        sort_order: str = "desc",
    ) -> List[UnifiedCVE]:
        """Query CVEs with filters.

        Args:
            filters: Query filters:
                - severity: CVSS severity (CRITICAL, HIGH, MEDIUM, LOW)
                - min_score: Minimum CVSS score
                - max_score: Maximum CVSS score
                - published_after: ISO date string
                - published_before: ISO date string
                - keyword: Search in description
                - source: Filter by data source
            limit: Max results to return
            offset: Skip first N results

        Returns:
            List of UnifiedCVE models
        """
        container = await self._get_container()

        query_parts, parameters = self._build_where_clause(filters)

        ordered_query_parts = list(query_parts)
        ordered_query_parts.append(self._build_order_by_clause(sort_by, sort_order))
        ordered_query_parts.append(f"OFFSET {offset} LIMIT {limit}")
        ordered_query = " ".join(ordered_query_parts)

        try:
            items = await self._execute_query(
                container=container,
                query=ordered_query,
                parameters=parameters,
            )
            return self._parse_items(items)
        except Exception as e:
            if not self._is_missing_composite_index_error(e):
                logger.error(f"Failed to query CVEs: {e}")
                return []

            logger.warning(
                "CVE query missing composite index; retrying without ORDER BY and sorting client-side: %s",
                e,
            )

            try:
                items = await self._execute_query(
                    container=container,
                    query=" ".join(query_parts),
                    parameters=parameters,
                )
                sorted_cves = self._sort_cves(self._parse_items(items), sort_by=sort_by, sort_order=sort_order)
                return sorted_cves[offset:offset + limit]
            except Exception as retry_error:
                logger.error(f"Failed to query CVEs after composite-index fallback: {retry_error}")
                return []

    async def count_cves(self, filters: Dict[str, Any]) -> int:
        """Count cached CVEs matching the supplied filters."""
        container = await self._get_container()
        query_parts, parameters = self._build_where_clause(filters, select_clause="SELECT VALUE COUNT(1)")
        query = " ".join(query_parts)

        try:
            items = await asyncio.to_thread(
                lambda: list(
                    container.query_items(
                        query=query,
                        parameters=parameters,
                        enable_cross_partition_query=True
                    )
                )
            )

            for item in items:
                return int(item)

            return 0
        except Exception as e:
            logger.error(f"Failed to count CVEs: {e}")
            return 0

    async def _execute_query(
        self,
        *,
        container: Any,
        query: str,
        parameters: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        return await asyncio.to_thread(
            lambda: list(
                container.query_items(
                    query=query,
                    parameters=parameters,
                    enable_cross_partition_query=True,
                )
            )
        )

    def _parse_items(self, items: List[Dict[str, Any]]) -> List[UnifiedCVE]:
        cves = []
        for item in items:
            try:
                cve = self._doc_to_model(item)
                cves.append(cve)
            except Exception as e:
                logger.warning(f"Failed to parse CVE {item.get('id')}: {e}")
        return cves

    @staticmethod
    def _is_missing_composite_index_error(exc: Exception) -> bool:
        text = str(exc or "").lower()
        return "composite index" in text and "order by" in text

    def _sort_cves(
        self,
        cves: List[UnifiedCVE],
        sort_by: str,
        sort_order: str,
    ) -> List[UnifiedCVE]:
        reverse = str(sort_order).lower() != "asc"
        field = (sort_by or "published_date").lower()

        severity_rank = {
            "UNKNOWN": 0,
            "LOW": 1,
            "MEDIUM": 2,
            "HIGH": 3,
            "CRITICAL": 4,
        }

        def score_for(cve: UnifiedCVE) -> float:
            if cve.cvss_v3 and cve.cvss_v3.base_score is not None:
                return cve.cvss_v3.base_score
            if cve.cvss_v2 and cve.cvss_v2.base_score is not None:
                return cve.cvss_v2.base_score
            return -1.0

        def severity_for(cve: UnifiedCVE) -> str:
            if cve.cvss_v3 and cve.cvss_v3.base_severity:
                return cve.cvss_v3.base_severity.upper()
            if cve.cvss_v2 and cve.cvss_v2.base_severity:
                return cve.cvss_v2.base_severity.upper()
            return "UNKNOWN"

        if field == "cve_id":
            key_fn = lambda cve: cve.cve_id
        elif field == "severity":
            key_fn = lambda cve: (severity_rank.get(severity_for(cve), 0), score_for(cve), cve.cve_id)
        elif field == "cvss_score":
            key_fn = lambda cve: (score_for(cve), cve.cve_id)
        elif field == "last_modified_date":
            key_fn = lambda cve: (cve.last_modified_date, cve.cve_id)
        else:
            key_fn = lambda cve: (cve.published_date, cve.cve_id)

        return sorted(cves, key=key_fn, reverse=reverse)

    async def get_cves_modified_since(self, since_date: datetime) -> List[UnifiedCVE]:
        """Get CVEs modified since given date for incremental sync.

        Args:
            since_date: Fetch CVEs modified after this date

        Returns:
            List of UnifiedCVE models
        """
        return await self.query_cves(
            filters={"published_after": since_date.isoformat()},
            limit=10000  # High limit for sync operations
        )

    def _doc_to_model(self, doc: Dict[str, Any]) -> UnifiedCVE:
        """Convert Cosmos DB document to UnifiedCVE model.

        Args:
            doc: Cosmos DB document dict

        Returns:
            UnifiedCVE model
        """
        # Parse datetime strings back to datetime objects
        if isinstance(doc.get("published_date"), str):
            doc["published_date"] = datetime.fromisoformat(doc["published_date"])
        if isinstance(doc.get("last_modified_date"), str):
            doc["last_modified_date"] = datetime.fromisoformat(doc["last_modified_date"])
        if isinstance(doc.get("last_synced"), str):
            doc["last_synced"] = datetime.fromisoformat(doc["last_synced"])

        # Remove Cosmos DB system fields
        doc.pop("_rid", None)
        doc.pop("_self", None)
        doc.pop("_etag", None)
        doc.pop("_attachments", None)
        doc.pop("_ts", None)
        doc.pop("id", None)  # Use cve_id instead

        return UnifiedCVE(**doc)

    def _build_where_clause(
        self,
        filters: Dict[str, Any],
        select_clause: str = "SELECT *"
    ) -> tuple[List[str], List[Dict[str, Any]]]:
        """Build shared Cosmos SQL WHERE clause for query and count operations."""
        query_parts = [f"{select_clause} FROM c WHERE 1=1"]
        parameters: List[Dict[str, Any]] = []

        if "severity" in filters:
            query_parts.append("AND c.cvss_v3.base_severity = @severity")
            parameters.append({"name": "@severity", "value": filters["severity"]})

        if "min_score" in filters:
            query_parts.append("AND c.cvss_v3.base_score >= @min_score")
            parameters.append({"name": "@min_score", "value": filters["min_score"]})

        if "max_score" in filters:
            query_parts.append("AND c.cvss_v3.base_score <= @max_score")
            parameters.append({"name": "@max_score", "value": filters["max_score"]})

        if "published_after" in filters:
            query_parts.append("AND c.published_date >= @published_after")
            parameters.append({"name": "@published_after", "value": filters["published_after"]})

        if "published_before" in filters:
            query_parts.append("AND c.published_date <= @published_before")
            parameters.append({"name": "@published_before", "value": filters["published_before"]})

        if "keyword" in filters:
            query_parts.append(
                "AND (CONTAINS(LOWER(c.description), LOWER(@keyword)) OR CONTAINS(LOWER(c.cve_id), LOWER(@keyword)) OR EXISTS(SELECT VALUE p FROM p IN c.affected_products WHERE CONTAINS(LOWER(REPLACE(REPLACE(CONCAT(p.vendor, ' ', p.product, ' ', p.version), '_', ' '), '-', ' ')), LOWER(@keyword))))"
            )
            parameters.append({"name": "@keyword", "value": filters["keyword"]})

        if "source" in filters:
            query_parts.append("AND ARRAY_CONTAINS(c.sources, @source)")
            parameters.append({"name": "@source", "value": filters["source"]})

        if "vendor" in filters:
            query_parts.append(
                "AND EXISTS(SELECT VALUE p FROM p IN c.affected_products WHERE CONTAINS(LOWER(p.vendor), LOWER(@vendor)))"
            )
            parameters.append({"name": "@vendor", "value": filters["vendor"]})

        if "product" in filters:
            query_parts.append(
                "AND EXISTS(SELECT VALUE p FROM p IN c.affected_products WHERE CONTAINS(LOWER(p.product), LOWER(@product)))"
            )
            parameters.append({"name": "@product", "value": filters["product"]})

        return query_parts, parameters

    def _build_order_by_clause(self, sort_by: str, sort_order: str) -> str:
        direction = "ASC" if str(sort_order).lower() == "asc" else "DESC"
        field = (sort_by or "published_date").lower()

        if field == "cve_id":
            return f"ORDER BY c.cve_id {direction}"
        if field == "cvss_score":
            return f"ORDER BY c.cvss_v3.base_score {direction}, c.cve_id {direction}"
        if field == "severity":
            if direction == "ASC":
                return (
                    "ORDER BY "
                    "IIF(c.cvss_v3.base_severity = 'CRITICAL', 4, "
                    "IIF(c.cvss_v3.base_severity = 'HIGH', 3, "
                    "IIF(c.cvss_v3.base_severity = 'MEDIUM', 2, "
                    "IIF(c.cvss_v3.base_severity = 'LOW', 1, 0)))) ASC, "
                    "c.cvss_v3.base_score ASC, c.cve_id ASC"
                )
            return (
                "ORDER BY "
                "IIF(c.cvss_v3.base_severity = 'CRITICAL', 4, "
                "IIF(c.cvss_v3.base_severity = 'HIGH', 3, "
                "IIF(c.cvss_v3.base_severity = 'MEDIUM', 2, "
                "IIF(c.cvss_v3.base_severity = 'LOW', 1, 0)))) DESC, "
                "c.cvss_v3.base_score DESC, c.cve_id DESC"
            )
        if field == "last_modified_date":
            return f"ORDER BY c.last_modified_date {direction}, c.cve_id {direction}"
        return f"ORDER BY c.published_date {direction}, c.cve_id {direction}"
