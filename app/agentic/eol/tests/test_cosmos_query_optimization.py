"""
Integration tests for Cosmos DB query optimization components.

Tests the optimised query builders, QuerySpec data class, QueryBenchmark
summary generation, indexing policy structure, and end-to-end
discovery → container → query pipeline with mock Cosmos containers.

Run with: pytest -m integration tests/test_cosmos_query_optimization.py -v
"""

from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MOCK_SUB = "sub-cosmos-test-001"


# ---------------------------------------------------------------------------
# Mock Cosmos container fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_container():
    """Mock Cosmos DB container with in-memory query simulation."""
    container = MagicMock()
    stored: Dict[str, Dict[str, Any]] = {}

    def upsert(body, **kw):
        stored[body.get("id", str(len(stored)))] = body
        return body

    def query(query: str, parameters=None, **kw):
        params = {p["name"]: p["value"] for p in (parameters or [])}
        results = list(stored.values())

        if "@rtype" in params:
            results = [d for d in results if d.get("resource_type", "").lower() == params["@rtype"].lower()]
        if "@loc" in params:
            results = [d for d in results if d.get("location") == params["@loc"]]
        if "@docId" in params:
            results = [d for d in results if d.get("id") == params["@docId"]]
        if "@tagVal" in params and "@tagKey" in params:
            results = [d for d in results if d.get("tags", {}).get(params["@tagKey"]) == params["@tagVal"]]
        if "@pattern" in params:
            pat = params["@pattern"].lower()
            results = [d for d in results if pat in d.get("resource_name", "").lower()]
        if "@since" in params:
            results = [d for d in results if d.get("last_seen", "") >= params["@since"]]

        return iter(results)

    container.upsert_item = MagicMock(side_effect=upsert)
    container.query_items = MagicMock(side_effect=query)
    container._stored = stored
    return container


@pytest.fixture
def populated_container(mock_container):
    """Container pre-loaded with sample resource documents."""
    now = datetime.now(timezone.utc).isoformat()
    docs = [
        {"id": "vm1", "resource_name": "vm-web-01", "resource_type": "microsoft.compute/virtualmachines",
         "location": "eastus", "resource_group": "rg-prod", "subscription_id": MOCK_SUB,
         "tags": {"environment": "prod", "team": "platform"}, "selected_properties": {"vm_size": "Standard_D4s_v3"},
         "last_seen": now},
        {"id": "vm2", "resource_name": "vm-web-02", "resource_type": "microsoft.compute/virtualmachines",
         "location": "westus2", "resource_group": "rg-prod", "subscription_id": MOCK_SUB,
         "tags": {"environment": "prod"}, "selected_properties": {"vm_size": "Standard_D2s_v3"},
         "last_seen": now},
        {"id": "vm3", "resource_name": "vm-db-01", "resource_type": "microsoft.compute/virtualmachines",
         "location": "eastus", "resource_group": "rg-data", "subscription_id": MOCK_SUB,
         "tags": {"environment": "staging"}, "selected_properties": {"vm_size": "Standard_E4s_v3"},
         "last_seen": "2025-01-01T00:00:00Z"},
        {"id": "st1", "resource_name": "stproddata01", "resource_type": "microsoft.storage/storageaccounts",
         "location": "eastus", "resource_group": "rg-prod", "subscription_id": MOCK_SUB,
         "tags": {"environment": "prod"}, "selected_properties": {"access_tier": "Hot"},
         "last_seen": now},
        {"id": "nic1", "resource_name": "nic-web-01", "resource_type": "microsoft.network/networkinterfaces",
         "location": "eastus", "resource_group": "rg-prod", "subscription_id": MOCK_SUB,
         "tags": {}, "selected_properties": {},
         "relationships": {"parent": "vm1", "children": [], "dependencies": ["vnet1"]},
         "last_seen": now},
    ]
    for doc in docs:
        mock_container.upsert_item(doc)
    return mock_container


# ---------------------------------------------------------------------------
# Test: QuerySpec
# ---------------------------------------------------------------------------

class TestQuerySpec:
    """Tests for the QuerySpec data class."""

    def test_to_kwargs_with_partition_key(self):
        from utils.resource_inventory_queries import QuerySpec
        spec = QuerySpec(query="SELECT * FROM c", parameters=[], partition_key="sub-123")
        kw = spec.to_kwargs()
        assert kw["partition_key"] == "sub-123"
        assert "enable_cross_partition_query" not in kw

    def test_to_kwargs_cross_partition(self):
        from utils.resource_inventory_queries import QuerySpec
        spec = QuerySpec(query="SELECT * FROM c", parameters=[])
        kw = spec.to_kwargs()
        assert kw["enable_cross_partition_query"] is True
        assert "partition_key" not in kw

    def test_default_max_item_count(self):
        from utils.resource_inventory_queries import QuerySpec
        spec = QuerySpec(query="SELECT * FROM c", parameters=[])
        assert spec.max_item_count == 100
        assert spec.to_kwargs()["max_item_count"] == 100


# ---------------------------------------------------------------------------
# Test: OptimisedQueries against populated container
# ---------------------------------------------------------------------------

class TestOptimisedQueriesWithData:
    """Exercise each query builder against a populated mock container."""

    async def test_vms_in_subscription(self, populated_container):
        from utils.resource_inventory_queries import optimised_queries
        spec = optimised_queries.vms_in_subscription(MOCK_SUB)
        results = list(populated_container.query_items(**spec.to_kwargs()))
        assert len(results) == 3
        assert all("virtualmachines" in r["resource_type"] for r in results)

    async def test_vms_filtered_by_location(self, populated_container):
        from utils.resource_inventory_queries import optimised_queries
        spec = optimised_queries.vms_in_subscription(MOCK_SUB, location="eastus")
        results = list(populated_container.query_items(**spec.to_kwargs()))
        assert len(results) == 2
        assert all(r["location"] == "eastus" for r in results)

    async def test_resources_by_name_web(self, populated_container):
        from utils.resource_inventory_queries import optimised_queries
        spec = optimised_queries.resources_by_name(MOCK_SUB, "web")
        results = list(populated_container.query_items(**spec.to_kwargs()))
        assert len(results) == 3  # vm-web-01, vm-web-02, nic-web-01
        assert all("web" in r["resource_name"] for r in results)

    async def test_resources_by_name_no_match(self, populated_container):
        from utils.resource_inventory_queries import optimised_queries
        spec = optimised_queries.resources_by_name(MOCK_SUB, "zzzznonexistent")
        results = list(populated_container.query_items(**spec.to_kwargs()))
        assert len(results) == 0

    async def test_resources_by_tag_prod(self, populated_container):
        from utils.resource_inventory_queries import optimised_queries
        spec = optimised_queries.resources_by_tag(MOCK_SUB, "environment", "prod")
        results = list(populated_container.query_items(**spec.to_kwargs()))
        assert len(results) == 3  # vm1, vm2, st1
        assert all(r["tags"].get("environment") == "prod" for r in results)

    async def test_resources_by_tag_staging(self, populated_container):
        from utils.resource_inventory_queries import optimised_queries
        spec = optimised_queries.resources_by_tag(MOCK_SUB, "environment", "staging")
        results = list(populated_container.query_items(**spec.to_kwargs()))
        assert len(results) == 1
        assert results[0]["resource_name"] == "vm-db-01"

    async def test_resource_relationships_point_read(self, populated_container):
        from utils.resource_inventory_queries import optimised_queries
        spec = optimised_queries.resource_relationships(MOCK_SUB, "nic1")
        results = list(populated_container.query_items(**spec.to_kwargs()))
        assert len(results) == 1
        assert results[0]["id"] == "nic1"
        assert results[0]["relationships"]["parent"] == "vm1"

    async def test_type_and_location(self, populated_container):
        from utils.resource_inventory_queries import optimised_queries
        spec = optimised_queries.resources_by_type_and_location(
            MOCK_SUB, "Microsoft.Compute/virtualMachines", "eastus"
        )
        results = list(populated_container.query_items(**spec.to_kwargs()))
        assert len(results) == 2
        assert all(r["location"] == "eastus" and "virtualmachines" in r["resource_type"] for r in results)

    async def test_recently_updated(self, populated_container):
        from utils.resource_inventory_queries import optimised_queries
        spec = optimised_queries.recently_updated(MOCK_SUB, "2026-01-01T00:00:00Z")
        results = list(populated_container.query_items(**spec.to_kwargs()))
        # vm3 has last_seen 2025, so should be excluded
        assert all(r["last_seen"] >= "2026-01-01T00:00:00Z" for r in results)
        assert not any(r["id"] == "vm3" for r in results)


# ---------------------------------------------------------------------------
# Test: QueryBenchmark summary
# ---------------------------------------------------------------------------

class TestBenchmarkSummary:
    """Tests for benchmark report generation."""

    def test_all_passing(self):
        from utils.resource_inventory_queries import BenchmarkResult, QueryBenchmark
        results = [
            BenchmarkResult("q1", request_charge_ru=3.0, latency_ms=50, items_returned=10, meets_target=True),
            BenchmarkResult("q2", request_charge_ru=5.0, latency_ms=80, items_returned=20, meets_target=True),
        ]
        s = QueryBenchmark.summary(results)
        assert s["total_queries"] == 2
        assert s["successful"] == 2
        assert s["failed"] == 0
        assert s["meeting_ru_target"] == 2
        assert s["avg_ru"] == 4.0
        assert s["max_ru"] == 5.0
        assert "no changes needed" in s["recommendations"][0].lower()

    def test_with_failure(self):
        from utils.resource_inventory_queries import BenchmarkResult, QueryBenchmark
        results = [
            BenchmarkResult("q1", request_charge_ru=3.0, meets_target=True),
            BenchmarkResult("q2", error="timeout"),
        ]
        s = QueryBenchmark.summary(results)
        assert s["successful"] == 1
        assert s["failed"] == 1
        assert s["details"][1]["error"] == "timeout"

    def test_over_target_recommendations(self):
        from utils.resource_inventory_queries import BenchmarkResult, QueryBenchmark
        results = [
            BenchmarkResult("find_by_name_pattern", request_charge_ru=15.0, meets_target=False),
            BenchmarkResult("find_by_tag", request_charge_ru=12.0, meets_target=False),
        ]
        s = QueryBenchmark.summary(results)
        assert s["meeting_ru_target"] == 0
        assert len(s["recommendations"]) == 2

    def test_empty_results(self):
        from utils.resource_inventory_queries import QueryBenchmark
        s = QueryBenchmark.summary([])
        assert s["total_queries"] == 0
        assert s["avg_ru"] == 0.0


# ---------------------------------------------------------------------------
# Test: ESTIMATED_RU_COSTS completeness
# ---------------------------------------------------------------------------

class TestEstimatedRUCosts:
    """Ensure cost documentation covers all benchmark queries."""

    def test_all_queries_documented(self):
        from utils.resource_inventory_queries import ESTIMATED_RU_COSTS
        expected = ["find_all_vms", "find_by_name_pattern", "find_by_tag",
                     "get_relationships", "type_and_location", "counts_by_type", "recently_updated"]
        for q in expected:
            assert q in ESTIMATED_RU_COSTS, f"Missing cost estimate for {q}"

    def test_entries_have_required_fields(self):
        from utils.resource_inventory_queries import ESTIMATED_RU_COSTS
        for name, entry in ESTIMATED_RU_COSTS.items():
            for field in ("description", "estimated_ru", "index_used", "strategy"):
                assert field in entry, f"Query {name} missing field: {field}"


# ---------------------------------------------------------------------------
# Test: Indexing policy structure
# ---------------------------------------------------------------------------

class TestIndexingPolicies:
    """Verify container indexing policies match expected Cosmos DB format."""

    def test_inventory_policy_has_composite_indexes(self):
        from utils.resource_inventory_cosmos import INVENTORY_INDEXING_POLICY
        policy = INVENTORY_INDEXING_POLICY
        assert policy["indexingMode"] == "consistent"
        assert policy["automatic"] is True
        assert len(policy["compositeIndexes"]) >= 3

    def test_composite_index_paths_valid(self):
        from utils.resource_inventory_cosmos import INVENTORY_INDEXING_POLICY
        for idx, composite in enumerate(INVENTORY_INDEXING_POLICY["compositeIndexes"]):
            assert len(composite) >= 2, f"Composite {idx} needs >= 2 paths"
            for spec in composite:
                assert spec["path"].startswith("/"), f"Path must start with / in composite {idx}"
                assert spec["order"] in ("ascending", "descending")

    def test_metadata_policy_structure(self):
        from utils.resource_inventory_cosmos import METADATA_INDEXING_POLICY
        assert METADATA_INDEXING_POLICY["indexingMode"] == "consistent"
        assert METADATA_INDEXING_POLICY["automatic"] is True

    def test_container_ids_defined(self):
        from utils.resource_inventory_cosmos import INVENTORY_CONTAINER_ID, METADATA_CONTAINER_ID
        assert INVENTORY_CONTAINER_ID == "resource_inventory"
        assert METADATA_CONTAINER_ID == "resource_inventory_metadata"


# ---------------------------------------------------------------------------
# Test: ResourceInventorySetup diagnostics
# ---------------------------------------------------------------------------

class TestSetupDiagnostics:
    """Test setup module status reporting."""

    def test_initial_status(self):
        from utils.resource_inventory_cosmos import ResourceInventorySetup
        setup = ResourceInventorySetup()
        status = setup.get_status()
        assert status["inventory_container_ready"] is False
        assert status["metadata_container_ready"] is False
        assert status["autoscale_max_throughput"] == 4000


# ---------------------------------------------------------------------------
# Test: Pipeline flow - discover → store → query
# ---------------------------------------------------------------------------

class TestPipelineFlow:
    """End-to-end: simulate discovery output → upsert to container → query back."""

    async def test_discovery_to_query(self, mock_container):
        from utils.resource_inventory_queries import optimised_queries

        now = datetime.now(timezone.utc).isoformat()
        discovered = [
            {"id": "vm_a", "resource_name": "vm-alpha", "resource_type": "microsoft.compute/virtualmachines",
             "location": "eastus", "resource_group": "rg-1", "subscription_id": MOCK_SUB,
             "tags": {"environment": "prod"}, "last_seen": now},
            {"id": "vm_b", "resource_name": "vm-beta", "resource_type": "microsoft.compute/virtualmachines",
             "location": "westus2", "resource_group": "rg-1", "subscription_id": MOCK_SUB,
             "tags": {"environment": "dev"}, "last_seen": now},
            {"id": "sa_a", "resource_name": "saprod01", "resource_type": "microsoft.storage/storageaccounts",
             "location": "eastus", "resource_group": "rg-1", "subscription_id": MOCK_SUB,
             "tags": {"environment": "prod"}, "last_seen": now},
        ]

        # Simulate upsert (what the inventory service does after discovery)
        for doc in discovered:
            mock_container.upsert_item(doc)

        # Query VMs only
        spec = optimised_queries.vms_in_subscription(MOCK_SUB)
        vms = list(mock_container.query_items(**spec.to_kwargs()))
        assert len(vms) == 2

        # Query by tag
        spec = optimised_queries.resources_by_tag(MOCK_SUB, "environment", "prod")
        prod = list(mock_container.query_items(**spec.to_kwargs()))
        assert len(prod) == 2  # vm_a + sa_a

        # Query by name
        spec = optimised_queries.resources_by_name(MOCK_SUB, "alpha")
        alpha = list(mock_container.query_items(**spec.to_kwargs()))
        assert len(alpha) == 1
        assert alpha[0]["id"] == "vm_a"

        # Type + location
        spec = optimised_queries.resources_by_type_and_location(
            MOCK_SUB, "microsoft.compute/virtualmachines", "eastus"
        )
        eastus_vms = list(mock_container.query_items(**spec.to_kwargs()))
        assert len(eastus_vms) == 1
        assert eastus_vms[0]["resource_name"] == "vm-alpha"
