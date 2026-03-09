from datetime import datetime, timezone

import pytest

from utils.cve_cosmos_repository import CVECosmosRepository, CVE_DATA_INDEXING_POLICY


class _FakeContainer:
    def __init__(self, unordered_items):
        self.unordered_items = unordered_items
        self.calls = []

    def query_items(self, query, parameters, enable_cross_partition_query=True):
        self.calls.append(query)
        if "ORDER BY" in query:
            raise Exception("The order by query does not have a corresponding composite index that it can be served from.")
        return list(self.unordered_items)


class _FakeDatabase:
    def __init__(self, container):
        self._container = container

    def get_container_client(self, _container_name):
        return self._container


class _FakeCosmosClient:
    def __init__(self, container):
        self._database = _FakeDatabase(container)

    def get_database_client(self, _database_name):
        return self._database


def _doc(cve_id: str, published_date: str) -> dict:
    return {
        "id": cve_id,
        "cve_id": cve_id,
        "description": f"Description for {cve_id}",
        "published_date": published_date,
        "last_modified_date": published_date,
        "last_synced": published_date,
        "affected_products": [],
        "references": [],
        "vendor_metadata": [],
        "sources": ["nvd"],
    }


@pytest.mark.asyncio
async def test_query_cves_retries_without_order_by_on_composite_index_error():
    container = _FakeContainer(
        unordered_items=[
            _doc("CVE-2026-0001", "2026-01-01T00:00:00+00:00"),
            _doc("CVE-2026-0002", "2026-01-02T00:00:00+00:00"),
        ]
    )
    repository = CVECosmosRepository(_FakeCosmosClient(container), "db")

    results = await repository.query_cves({"keyword": "windows server 2016"}, limit=10, offset=0)

    assert [cve.cve_id for cve in results] == ["CVE-2026-0002", "CVE-2026-0001"]
    assert len(container.calls) == 2
    assert "ORDER BY" in container.calls[0]
    assert "ORDER BY" not in container.calls[1]


def test_cve_data_indexing_policy_has_expected_composite_indexes():
    composite_indexes = CVE_DATA_INDEXING_POLICY["compositeIndexes"]
    assert len(composite_indexes) >= 8
    assert any(index[0]["path"] == "/published_date" for index in composite_indexes)
    assert any(index[0]["path"] == "/last_modified_date" for index in composite_indexes)
    assert any(index[0]["path"] == "/cvss_v3/base_score" for index in composite_indexes)
    assert any(index[0]["path"] == "/cvss_v3/base_severity" for index in composite_indexes)