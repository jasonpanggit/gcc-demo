from api.inventory import _apply_os_inventory_normalization
from api.patch_management import _normalize_machine_os_fields


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
