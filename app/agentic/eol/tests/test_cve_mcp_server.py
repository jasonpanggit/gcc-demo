"""Unit tests for CVE MCP server tools.

Tests all 4 CVE MCP tools with mocked dependencies.
These tests are local-only and not committed per .gitignore.
"""
import pytest
import json
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone


@pytest.fixture
def mock_cve_service():
    """Mock CVE service."""
    service = AsyncMock()

    # Mock CVE data
    mock_cve = MagicMock()
    mock_cve.cve_id = "CVE-2024-1234"
    mock_cve.dict.return_value = {
        "cve_id": "CVE-2024-1234",
        "description": "Critical vulnerability in test package",
        "cvss_v3": {
            "base_score": 9.8,
            "base_severity": "CRITICAL"
        },
        "published_date": "2024-01-15T00:00:00Z"
    }

    service.get_cve.return_value = mock_cve
    service.search_cves.return_value = [mock_cve]

    return service


@pytest.fixture
def mock_cve_scanner():
    """Mock CVE scanner."""
    scanner = AsyncMock()

    mock_scan_result = MagicMock()
    mock_scan_result.scan_id = "scan-123"
    mock_scan_result.status = "pending"
    mock_scan_result.total_vms = 5
    mock_scan_result.scanned_vms = 0
    mock_scan_result.total_matches = 0
    mock_scan_result.started_at = datetime.now(timezone.utc).isoformat()

    scanner.start_scan.return_value = "scan-123"
    scanner.get_scan_status.return_value = mock_scan_result

    return scanner


@pytest.fixture
def mock_patch_mapper():
    """Mock CVE patch mapper."""
    mapper = AsyncMock()

    mock_patch = MagicMock()
    mock_patch.kb_number = "KB5012345"
    mock_patch.package_name = "test-package"
    mock_patch.title = "Security Update for Test Package"
    mock_patch.priority = "critical"
    mock_patch.affected_vm_count = 3
    mock_patch.vendor = "Microsoft"

    mock_mapping = MagicMock()
    mock_mapping.patches = [mock_patch]
    mock_mapping.priority_score = 95
    mock_mapping.total_affected_vms = 3
    mock_mapping.recommendation = "Apply immediately"

    mapper.get_patches_for_cve.return_value = mock_mapping

    return mapper


@pytest.fixture
def mock_patch_client():
    """Mock patch MCP client."""
    client = AsyncMock()
    client.install_vm_patches.return_value = {
        "operation_url": "https://management.azure.com/...",
        "status": "started"
    }
    return client


@pytest.mark.asyncio
async def test_search_cve_by_id(mock_cve_service):
    """Test direct CVE lookup by ID."""
    from mcp_servers.cve_mcp_server import search_cve

    with patch('utils.cve_service.get_cve_service', return_value=mock_cve_service):
        result = await search_cve(cve_id="CVE-2024-1234")

        data = json.loads(result.text)
        assert data["success"] is True
        assert data["count"] == 1
        assert data["cves"][0]["cve_id"] == "CVE-2024-1234"
        assert data["tool_name"] == "search_cve"

        mock_cve_service.get_cve.assert_called_once_with("CVE-2024-1234")


@pytest.mark.asyncio
async def test_search_cve_by_keyword(mock_cve_service):
    """Test CVE search by keyword."""
    from mcp_servers.cve_mcp_server import search_cve

    with patch('utils.cve_service.get_cve_service', return_value=mock_cve_service):
        result = await search_cve(keyword="critical vulnerability")

        data = json.loads(result.text)
        assert data["success"] is True
        assert data["count"] >= 0
        assert data["tool_name"] == "search_cve"

        mock_cve_service.search_cves.assert_called_once()
        call_args = mock_cve_service.search_cves.call_args
        assert call_args[0][0]["keyword"] == "critical vulnerability"


@pytest.mark.asyncio
async def test_search_cve_with_filters(mock_cve_service):
    """Test CVE search with CVSS and severity filters."""
    from mcp_servers.cve_mcp_server import search_cve

    with patch('utils.cve_service.get_cve_service', return_value=mock_cve_service):
        result = await search_cve(
            severity="CRITICAL",
            cvss_min=9.0,
            cvss_max=10.0,
            limit=10
        )

        data = json.loads(result.text)
        assert data["success"] is True
        assert data["tool_name"] == "search_cve"

        call_args = mock_cve_service.search_cves.call_args
        filters = call_args[0][0]
        assert filters["severity"] == "CRITICAL"
        assert filters["cvss_min"] == 9.0
        assert filters["cvss_max"] == 10.0


@pytest.mark.asyncio
async def test_search_cve_not_found(mock_cve_service):
    """Test CVE lookup when CVE doesn't exist."""
    from mcp_servers.cve_mcp_server import search_cve

    mock_cve_service.get_cve.return_value = None

    with patch('utils.cve_service.get_cve_service', return_value=mock_cve_service):
        result = await search_cve(cve_id="CVE-9999-9999")

        data = json.loads(result.text)
        assert data["success"] is False
        assert "not found" in data["error"]
        assert data["tool_name"] == "search_cve"


@pytest.mark.asyncio
async def test_scan_inventory_single_vm(mock_cve_scanner):
    """Test VM-specific CVE scan."""
    from mcp_servers.cve_mcp_server import scan_inventory

    with patch('utils.cve_scanner.get_cve_scanner', return_value=mock_cve_scanner):
        result = await scan_inventory(
            subscription_id="sub-123",
            resource_group="rg-test",
            vm_name="vm-prod-01"
        )

        data = json.loads(result.text)
        assert data["success"] is True
        assert data["scan_id"] == "scan-123"
        assert data["status"] == "pending"
        assert data["tool_name"] == "scan_inventory"

        mock_cve_scanner.start_scan.assert_called_once()


@pytest.mark.asyncio
async def test_scan_inventory_subscription(mock_cve_scanner):
    """Test full subscription CVE scan."""
    from mcp_servers.cve_mcp_server import scan_inventory

    with patch('utils.cve_scanner.get_cve_scanner', return_value=mock_cve_scanner):
        result = await scan_inventory(subscription_id="sub-123")

        data = json.loads(result.text)
        assert data["success"] is True
        assert "scan_id" in data
        assert data["tool_name"] == "scan_inventory"


@pytest.mark.asyncio
async def test_get_patches_found(mock_patch_mapper):
    """Test getting patches for CVE with available patches."""
    from mcp_servers.cve_mcp_server import get_patches

    with patch('utils.cve_patch_mapper.get_cve_patch_mapper', return_value=mock_patch_mapper):
        result = await get_patches(cve_id="CVE-2024-1234")

        data = json.loads(result.text)
        assert data["success"] is True
        assert data["cve_id"] == "CVE-2024-1234"
        assert data["total_patches"] == 1
        assert data["patches"][0]["kb_number"] == "KB5012345"
        assert data["priority_score"] == 95
        assert data["tool_name"] == "get_patches"


@pytest.mark.asyncio
async def test_get_patches_not_found(mock_patch_mapper):
    """Test getting patches for CVE without available patches."""
    from mcp_servers.cve_mcp_server import get_patches

    mock_mapping = MagicMock()
    mock_mapping.patches = []
    mock_patch_mapper.get_patches_for_cve.return_value = mock_mapping

    with patch('utils.cve_patch_mapper.get_cve_patch_mapper', return_value=mock_patch_mapper):
        result = await get_patches(cve_id="CVE-2024-9999")

        data = json.loads(result.text)
        assert data["success"] is True
        assert data["patches"] == []
        assert "No patches found" in data["message"]
        assert data["tool_name"] == "get_patches"


@pytest.mark.asyncio
async def test_trigger_remediation_dry_run(mock_patch_mapper, mock_patch_client):
    """Test remediation in dry_run mode (plan only)."""
    from mcp_servers.cve_mcp_server import trigger_remediation

    with patch('utils.cve_patch_mapper.get_cve_patch_mapper', return_value=mock_patch_mapper), \
         patch('utils.patch_mcp_client.get_patch_mcp_client', return_value=mock_patch_client):

        result = await trigger_remediation(
            cve_id="CVE-2024-1234",
            vm_name="vm-prod-01",
            subscription_id="sub-123",
            resource_group="rg-test",
            dry_run=True
        )

        data = json.loads(result.text)
        assert data["success"] is True
        assert data["mode"] == "dry_run"
        assert len(data["patches"]) == 1
        assert "Call with confirmed=True to execute" in data["message"]
        assert data["tool_name"] == "trigger_remediation"

        # Should NOT call install
        mock_patch_client.install_vm_patches.assert_not_called()


@pytest.mark.asyncio
async def test_trigger_remediation_confirmed(mock_patch_mapper, mock_patch_client):
    """Test remediation in confirmed mode (execute)."""
    from mcp_servers.cve_mcp_server import trigger_remediation

    with patch('utils.cve_patch_mapper.get_cve_patch_mapper', return_value=mock_patch_mapper), \
         patch('utils.patch_mcp_client.get_patch_mcp_client', return_value=mock_patch_client):

        result = await trigger_remediation(
            cve_id="CVE-2024-1234",
            vm_name="vm-prod-01",
            subscription_id="sub-123",
            resource_group="rg-test",
            dry_run=False,
            confirmed=True
        )

        data = json.loads(result.text)
        assert data["success"] is True
        assert data["mode"] == "confirmed"
        assert "operation_url" in data
        assert data["status"] == "started"
        assert data["tool_name"] == "trigger_remediation"

        # Should call install
        mock_patch_client.install_vm_patches.assert_called_once()


@pytest.mark.asyncio
async def test_trigger_remediation_no_patches(mock_patch_mapper, mock_patch_client):
    """Test remediation when no patches available."""
    from mcp_servers.cve_mcp_server import trigger_remediation

    mock_mapping = MagicMock()
    mock_mapping.patches = []
    mock_patch_mapper.get_patches_for_cve.return_value = mock_mapping

    with patch('utils.cve_patch_mapper.get_cve_patch_mapper', return_value=mock_patch_mapper), \
         patch('utils.patch_mcp_client.get_patch_mcp_client', return_value=mock_patch_client):

        result = await trigger_remediation(
            cve_id="CVE-2024-9999",
            vm_name="vm-prod-01",
            subscription_id="sub-123",
            resource_group="rg-test"
        )

        data = json.loads(result.text)
        assert data["success"] is False
        assert "No patches found" in data["error"]
        assert data["tool_name"] == "trigger_remediation"


@pytest.mark.asyncio
async def test_error_handling():
    """Test that tools return error responses instead of raising exceptions."""
    from mcp_servers.cve_mcp_server import search_cve, scan_inventory, get_patches, trigger_remediation

    # Mock to raise exception
    mock_service = AsyncMock()
    mock_service.get_cve.side_effect = Exception("Test error")

    with patch('utils.cve_service.get_cve_service', return_value=mock_service):
        result = await search_cve(cve_id="CVE-2024-1234")
        data = json.loads(result.text)
        assert data["success"] is False
        assert "error" in data
        assert data["tool_name"] == "search_cve"

    mock_scanner = AsyncMock()
    mock_scanner.start_scan.side_effect = Exception("Scan error")

    with patch('utils.cve_scanner.get_cve_scanner', return_value=mock_scanner):
        result = await scan_inventory(subscription_id="sub-123")
        data = json.loads(result.text)
        assert data["success"] is False
        assert "error" in data
        assert data["tool_name"] == "scan_inventory"

    mock_mapper = AsyncMock()
    mock_mapper.get_patches_for_cve.side_effect = Exception("Mapper error")

    with patch('utils.cve_patch_mapper.get_cve_patch_mapper', return_value=mock_mapper):
        result = await get_patches(cve_id="CVE-2024-1234")
        data = json.loads(result.text)
        assert data["success"] is False
        assert "error" in data
        assert data["tool_name"] == "get_patches"

    with patch('utils.cve_patch_mapper.get_cve_patch_mapper', return_value=mock_mapper):
        result = await trigger_remediation(
            cve_id="CVE-2024-1234",
            vm_name="vm-test",
            subscription_id="sub-123",
            resource_group="rg-test"
        )
        data = json.loads(result.text)
        assert data["success"] is False
        assert "error" in data
        assert data["tool_name"] == "trigger_remediation"
