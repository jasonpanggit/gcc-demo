"""Focused contract regressions for patch management API normalization."""

import sys
from types import SimpleNamespace

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

import pytest
import pytest_asyncio

from api.patch_management import router as patch_management_router


class FakePatchRepo:
    def __init__(self):
        self.recorded_installs = []

    async def record_install(self, payload):
        self.recorded_installs.append(dict(payload))
        return {"ok": True}


class FakeAioHttpResponse:
    def __init__(self, status=200, *, json_body=None, text_body="", headers=None):
        self.status = status
        self._json_body = json_body
        self._text_body = text_body
        self.headers = headers or {}

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def text(self):
        return self._text_body

    async def json(self, content_type=None):
        return self._json_body


class FakeAioHttpSession:
    def __init__(self, *, post_response=None, get_response=None, **kwargs):
        self._post_response = post_response
        self._get_response = get_response

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def post(self, *args, **kwargs):
        if self._post_response is None:
            raise AssertionError("Unexpected POST request")
        return self._post_response

    def get(self, *args, **kwargs):
        if self._get_response is None:
            raise AssertionError("Unexpected GET request")
        return self._get_response


class FakePatchOSInventoryAgent:
    async def get_os_inventory(self, **_kwargs):
        return {
            "success": True,
            "data": [
                {
                    "computer": "arc-01",
                    "computer_type": "Arc-enabled Server",
                    "resource_id": "/subscriptions/sub-123/resourceGroups/rg-ops/providers/Microsoft.HybridCompute/machines/arc-01",
                    "os_name": "Ubuntu Server",
                    "os_version": "22.04",
                },
                {
                    "computer": "vm-in-os-01",
                    "computer_type": "Azure Virtual Machine",
                    "resource_id": "/subscriptions/sub-123/resourceGroups/rg-ops/providers/Microsoft.Compute/virtualMachines/vm-in-os-01",
                    "os_name": "Windows Server",
                    "os_version": "2022",
                },
            ],
        }


class FakePatchInventoryOrchestrator:
    def __init__(self):
        self.agents = {"os_inventory": FakePatchOSInventoryAgent()}


class FakeResourceInventoryClient:
    async def get_resources(self, *_args, **_kwargs):
        return [
            {
                "resource_name": "vm-01",
                "resource_id": "/subscriptions/sub-123/resourceGroups/rg-ops/providers/Microsoft.Compute/virtualMachines/vm-01",
                "subscription_id": "sub-123",
                "resource_group": "rg-ops",
                "location": "eastus",
                "selected_properties": {
                    "os_image": "Windows Server 2022 Datacenter",
                    "os_type": "Windows",
                    "vm_size": "Standard_D2s_v5",
                },
            }
        ]


@pytest_asyncio.fixture
async def patch_contract_client():
    app = FastAPI()
    app.include_router(patch_management_router)
    app.state.patch_repo = FakePatchRepo()

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        yield client


@pytest.mark.asyncio
async def test_assess_returns_wrapped_object_payload(patch_contract_client, monkeypatch):
    async def fake_get_arm_token():
        return "token"

    fake_response = FakeAioHttpResponse(
        status=202,
        headers={"Azure-AsyncOperation": "https://example.test/operations/assess-42"},
    )

    monkeypatch.setattr("api.patch_management._get_arm_token", fake_get_arm_token)
    monkeypatch.setattr(
        "api.patch_management.aiohttp.ClientSession",
        lambda **kwargs: FakeAioHttpSession(post_response=fake_response, **kwargs),
    )

    response = await patch_contract_client.post(
        "/api/patch-management/assess",
        json={
            "resource_id": "/subscriptions/sub-123/resourceGroups/rg-ops/providers/Microsoft.HybridCompute/machines/vm-arc-01",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["count"] == 1
    assert isinstance(body["data"], dict)
    assert body["data"]["triggered"] is True
    assert body["data"]["machine"] == "vm-arc-01"
    assert body["data"]["operation_url"] == "https://example.test/operations/assess-42"


@pytest.mark.asyncio
async def test_list_machines_returns_wrapped_array_payload_with_metadata_counts(
    patch_contract_client,
    monkeypatch,
):
    monkeypatch.setitem(
        sys.modules,
        "main",
        SimpleNamespace(get_eol_orchestrator=lambda: FakePatchInventoryOrchestrator()),
    )
    monkeypatch.setitem(
        sys.modules,
        "utils.resource_inventory_client",
        SimpleNamespace(get_resource_inventory_client=lambda: FakeResourceInventoryClient()),
    )

    response = await patch_contract_client.get("/api/patch-management/machines")

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["count"] == 2
    assert isinstance(body["data"], list)
    assert {item["vm_type"] for item in body["data"]} == {"arc", "azure-vm"}
    assert body["metadata"]["arc_count"] == 1
    assert body["metadata"]["azure_vm_count"] == 1


@pytest.mark.asyncio
async def test_list_arc_vms_returns_wrapped_array_payload_with_inventory_metadata(
    patch_contract_client,
    monkeypatch,
):
    monkeypatch.setitem(
        sys.modules,
        "main",
        SimpleNamespace(get_eol_orchestrator=lambda: FakePatchInventoryOrchestrator()),
    )

    response = await patch_contract_client.get("/api/patch-management/arc-vms")

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["count"] == 1
    assert isinstance(body["data"], list)
    assert body["data"][0]["computer"] == "arc-01"
    assert body["metadata"]["total_os_inventory"] == 2


@pytest.mark.asyncio
async def test_assess_synchronous_completion_returns_wrapped_object_payload(patch_contract_client, monkeypatch):
    async def fake_get_arm_token():
        return "token"

    fake_response = FakeAioHttpResponse(status=200)

    monkeypatch.setattr("api.patch_management._get_arm_token", fake_get_arm_token)
    monkeypatch.setattr(
        "api.patch_management.aiohttp.ClientSession",
        lambda **kwargs: FakeAioHttpSession(post_response=fake_response, **kwargs),
    )

    response = await patch_contract_client.post(
        "/api/patch-management/assess",
        json={
            "resource_id": "/subscriptions/sub-123/resourceGroups/rg-ops/providers/Microsoft.HybridCompute/machines/vm-arc-01",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["count"] == 1
    assert isinstance(body["data"], dict)
    assert body["data"]["triggered"] is True
    assert body["data"]["machine"] == "vm-arc-01"
    assert body["data"]["vm_type"] == "arc"


@pytest.mark.asyncio
async def test_install_returns_wrapped_object_payload(patch_contract_client, monkeypatch):
    async def fake_get_arm_token():
        return "token"

    fake_response = FakeAioHttpResponse(
        status=202,
        headers={"Azure-AsyncOperation": "https://example.test/operations/42"},
    )

    monkeypatch.setattr("api.patch_management._get_arm_token", fake_get_arm_token)
    monkeypatch.setattr(
        "api.patch_management.aiohttp.ClientSession",
        lambda **kwargs: FakeAioHttpSession(post_response=fake_response, **kwargs),
    )

    response = await patch_contract_client.post(
        "/api/patch-management/install",
        json={
            "resource_id": "/subscriptions/sub-123/resourceGroups/rg-ops/providers/Microsoft.HybridCompute/machines/vm-arc-01",
            "kb_numbers_to_include": ["5030211"],
            "classifications": ["Critical", "Security"],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["count"] == 1
    assert isinstance(body["data"], dict)
    assert body["data"]["machine"] == "vm-arc-01"
    assert body["data"]["status"] == "InProgress"
    assert body["data"]["operation_url"] == "https://example.test/operations/42"
    assert "install-status" in body["message"]


@pytest.mark.asyncio
async def test_install_synchronous_completion_returns_wrapped_object_payload(patch_contract_client, monkeypatch):
    async def fake_get_arm_token():
        return "token"

    fake_response = FakeAioHttpResponse(
        status=200,
        json_body={
            "status": "Succeeded",
            "properties": {
                "installedPatchCount": 2,
                "failedPatchCount": 0,
                "pendingPatchCount": 0,
                "notSelectedPatchCount": 0,
                "excludedPatchCount": 0,
            },
        },
    )

    monkeypatch.setattr("api.patch_management._get_arm_token", fake_get_arm_token)
    monkeypatch.setattr(
        "api.patch_management.aiohttp.ClientSession",
        lambda **kwargs: FakeAioHttpSession(post_response=fake_response, **kwargs),
    )

    response = await patch_contract_client.post(
        "/api/patch-management/install",
        json={
            "resource_id": "/subscriptions/sub-123/resourceGroups/rg-ops/providers/Microsoft.HybridCompute/machines/vm-arc-01",
            "kb_numbers_to_include": ["5030211"],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["count"] == 1
    assert isinstance(body["data"], dict)
    assert body["data"]["machine"] == "vm-arc-01"
    assert body["data"]["subscription_id"] == "sub-123"
    assert body["data"]["resource_group"] == "rg-ops"
    assert body["data"]["status"] == "Completed"
    assert body["data"]["result"]["installed_patch_count"] == 2


@pytest.mark.asyncio
async def test_install_status_returns_wrapped_object_payload(patch_contract_client, monkeypatch):
    async def fake_get_arm_token():
        return "token"

    fake_response = FakeAioHttpResponse(
        status=200,
        json_body={
            "status": "Succeeded",
            "properties": {
                "installedPatchCount": 2,
                "failedPatchCount": 0,
                "pendingPatchCount": 0,
                "notSelectedPatchCount": 1,
                "excludedPatchCount": 0,
            },
        },
    )

    monkeypatch.setattr("api.patch_management._get_arm_token", fake_get_arm_token)
    monkeypatch.setattr(
        "api.patch_management.aiohttp.ClientSession",
        lambda **kwargs: FakeAioHttpSession(get_response=fake_response, **kwargs),
    )

    response = await patch_contract_client.get(
        "/api/patch-management/install-status",
        params={"operation_url": "https://example.test/operations/42"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["count"] == 1
    assert isinstance(body["data"], dict)
    assert body["data"]["status"] == "Succeeded"
    assert body["data"]["is_done"] is True
    assert isinstance(body["data"]["result"], dict)
    assert body["data"]["result"]["installed_patch_count"] == 2


@pytest.mark.asyncio
async def test_last_assessment_returns_wrapped_object_payload(patch_contract_client, monkeypatch):
    async def fake_query_arg(query, subscription_ids):
        if "softwarepatches" in query:
            return [
                {
                    "patchName": "Security Update",
                    "kbId": "5030211",
                    "classifications": "[\"Security\"]",
                    "rebootBehavior": "AlwaysRequiresReboot",
                    "assessmentState": "Available",
                    "publishedDate": "2026-03-01T00:00:00Z",
                }
            ]
        return [
            {
                "resourceGroup": "rg-ops",
                "subscriptionId": "sub-123",
                "osType": "Windows",
                "rebootPending": False,
                "criticalCount": 1,
                "otherCount": 0,
                "lastModified": "2026-03-27T08:00:00Z",
                "status": "Succeeded",
            }
        ]

    monkeypatch.setattr("api.patch_management._query_arg", fake_query_arg)
    monkeypatch.setattr("api.patch_management._trigger_kb_sync_for_patches", lambda machines: None)

    response = await patch_contract_client.get(
        "/api/patch-management/last-assessment",
        params={"machine_name": "vm-arc-01", "subscription_id": "sub-123", "vm_type": "arc"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["count"] == 1
    assert isinstance(body["data"], dict)
    assert body["data"]["found"] is True
    assert body["data"]["machine_name"] == "vm-arc-01"
    assert body["data"]["patches"]["status"] == "Succeeded"
    assert body["data"]["patches"]["available_patches"][0]["kbId"] == "5030211"


@pytest.mark.asyncio
async def test_last_assessment_missing_result_returns_wrapped_found_false_payload(patch_contract_client, monkeypatch):
    async def fake_query_arg(query, subscription_ids):
        return []

    monkeypatch.setattr("api.patch_management._query_arg", fake_query_arg)

    response = await patch_contract_client.get(
        "/api/patch-management/last-assessment",
        params={"machine_name": "vm-arc-01", "subscription_id": "sub-123", "vm_type": "arc"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["count"] == 1
    assert isinstance(body["data"], dict)
    assert body["data"]["found"] is False
    assert body["data"]["machine_name"] == "vm-arc-01"