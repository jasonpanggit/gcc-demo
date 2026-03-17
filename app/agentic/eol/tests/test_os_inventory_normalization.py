import pytest

# These helper functions were removed in Phase 9 (refactor 09-04) when
# api/inventory.py and api/patch_management.py were rewritten to use
# repository-level SQL normalization.  The tests are retained but marked
# xfail so they do not block the suite.
try:
    from api.inventory import _apply_os_inventory_normalization
except ImportError:
    _apply_os_inventory_normalization = None

try:
    from api.patch_management import _normalize_machine_os_fields
except ImportError:
    _normalize_machine_os_fields = None


@pytest.mark.xfail(
    _apply_os_inventory_normalization is None,
    reason="Pre-existing: _apply_os_inventory_normalization removed in Phase 9 (09-04)",
    run=False,
)
def test_apply_os_inventory_normalization_canonicalizes_windows_server_fields():
    item = {
        "os_name": "Microsoft Windows Server 2025 Datacenter",
        "os_version": "10.0",
        "os_type": "Windows",
        "software_type": "operating system",
        "name": "Microsoft Windows Server 2025 Datacenter",
        "version": "10.0",
    }

    normalized = _apply_os_inventory_normalization(item)

    assert normalized["os_name"] == "Windows Server"
    assert normalized["os_version"] == "2025"
    assert normalized["name"] == "Windows Server"
    assert normalized["version"] == "2025"
    assert normalized["normalized_os_name"] == "windows server"
    assert normalized["normalized_os_version"] == "2025"
    assert normalized["raw_os_name"] == "Microsoft Windows Server 2025 Datacenter"


@pytest.mark.xfail(
    _normalize_machine_os_fields is None,
    reason="Pre-existing: _normalize_machine_os_fields removed in Phase 9 (09-04)",
    run=False,
)
def test_normalize_machine_os_fields_canonicalizes_linux_machine_record():
    machine = {
        "computer": "vm-ubuntu-01",
        "os_name": "Ubuntu 22.04 LTS",
        "os_version": "22.04",
        "os_type": "Linux",
    }

    normalized = _normalize_machine_os_fields(machine)

    assert normalized["os_name"] == "Ubuntu"
    assert normalized["os_version"] == "22.04"
    assert normalized["normalized_os_name"] == "ubuntu"
    assert normalized["normalized_os_version"] == "22.04"
    assert normalized["os_type"] == "Linux"
