from datetime import datetime, timezone

import pytest

from utils.nvd_client import NVDClient, DEFAULT_PAGE_SIZE


def _page(cve_ids, total_results):
    return {
        "totalResults": total_results,
        "vulnerabilities": [
            {
                "cve": {
                    "id": cve_id,
                    "descriptions": [{"lang": "en", "value": f"Description for {cve_id}"}],
                    "metrics": {},
                    "weaknesses": [],
                    "configurations": [],
                    "references": [],
                    "published": "2026-03-01T00:00:00.000",
                    "lastModified": "2026-03-02T00:00:00.000",
                }
            }
            for cve_id in cve_ids
        ],
    }


@pytest.mark.asyncio
async def test_fetch_cves_since_paginates_with_smaller_default_page_size():
    client = NVDClient(api_key="test-key")
    calls = []

    async def fake_request(method, url, **kwargs):
        calls.append(url)
        if "startIndex=0" in url:
            return _page(["CVE-2026-0001", "CVE-2026-0002"], 3)
        return _page(["CVE-2026-0003"], 3)

    client._request = fake_request

    results = await client.fetch_cves_since(datetime(2026, 3, 1, tzinfo=timezone.utc))

    assert [item["cve_id"] for item in results] == [
        "CVE-2026-0001",
        "CVE-2026-0002",
        "CVE-2026-0003",
    ]
    assert len(calls) == 2
    assert f"resultsPerPage={DEFAULT_PAGE_SIZE}" in calls[0]
    assert "startIndex=0" in calls[0]
    assert "startIndex=2" in calls[1]


@pytest.mark.asyncio
async def test_search_cves_returns_partial_results_when_later_page_fails():
    client = NVDClient(api_key="test-key")
    calls = []

    async def fake_request(method, url, **kwargs):
        calls.append(url)
        if "startIndex=0" in url:
            return _page(["CVE-2026-0001", "CVE-2026-0002"], 4)
        raise TimeoutError()

    client._request = fake_request

    results = await client.search_cves(query="windows server", resultsPerPage=2)

    assert [item["cve_id"] for item in results] == [
        "CVE-2026-0001",
        "CVE-2026-0002",
    ]
    assert len(calls) == 2


@pytest.mark.asyncio
async def test_search_cves_respects_limit_across_multiple_pages():
    client = NVDClient(api_key="test-key")
    calls = []

    async def fake_request(method, url, **kwargs):
        calls.append(url)
        if "startIndex=0" in url:
            return _page(["CVE-2026-0001", "CVE-2026-0002"], 5)
        if "startIndex=2" in url:
            return _page(["CVE-2026-0003", "CVE-2026-0004"], 5)
        return _page(["CVE-2026-0005"], 5)

    client._request = fake_request

    results = await client.search_cves(query="windows server", limit=3, resultsPerPage=2)

    assert [item["cve_id"] for item in results] == [
        "CVE-2026-0001",
        "CVE-2026-0002",
        "CVE-2026-0003",
    ]
    assert len(calls) == 2