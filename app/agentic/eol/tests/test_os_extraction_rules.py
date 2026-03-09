import pytest

from utils.normalization import derive_os_name_version, normalize_os_name_version
from utils.os_extraction_rules import OSExtractionRulesStore


def test_derive_os_name_version_tracks_windows_server_default_rule_strategy():
    derived = derive_os_name_version("Microsoft Windows Server 2025 Datacenter", "10.0")

    assert derived["normalized_name"] == "windows server"
    assert derived["normalized_version"] == "2025"
    assert derived["strategy"] == "custom_regex"
    assert derived["rule_id"] == "default-windows-server-name"


def test_normalize_os_name_version_returns_os_family_and_release_only():
    normalized_name, normalized_version = normalize_os_name_version(
        "Microsoft Windows Server 2022 Datacenter",
        "10.0",
    )

    assert normalized_name == "windows server"
    assert normalized_version == "2022"


def test_derive_os_name_version_uses_default_rule_for_azure_image_sku():
    derived = derive_os_name_version("WindowsServer 2025-datacenter-azure-edition", None)

    assert derived["normalized_name"] == "windows server"
    assert derived["normalized_version"] == "2025"
    assert derived["strategy"] == "custom_regex"
    assert derived["rule_id"] == "default-windowsserver-azure-image"


def test_derive_os_name_version_uses_default_rule_fallback_to_raw_version():
    derived = derive_os_name_version("Ubuntu LTS", "22.04")

    assert derived["normalized_name"] == "ubuntu"
    assert derived["normalized_version"] == "22.04"
    assert derived["strategy"] == "custom_regex"
    assert derived["rule_id"] == "default-ubuntu-family"


def test_os_extraction_rules_store_includes_seeded_defaults_when_no_persisted_rules(monkeypatch):
    store = OSExtractionRulesStore()

    monkeypatch.setattr(store, "_container", lambda: None)

    rules = store.get_rules()
    windows_server_rule = next(item for item in rules if item["id"] == "default-windows-server-name")

    assert windows_server_rule["is_default"] is True
    assert windows_server_rule["is_seeded"] is True
    assert windows_server_rule["rule_origin"] == "default"
    assert windows_server_rule["is_overridden"] is False


def test_os_extraction_rules_store_merges_default_override_and_custom_rule(monkeypatch):
    store = OSExtractionRulesStore()
    persisted_rules = [
        {
            "id": "default-windows-server-name",
            "name": "Windows Server family from OS name",
            "pattern": r"^(?:microsoft\s+)?windows\s+server\s+(?P<version>20\d{2})$",
            "source_scope": "os_name",
            "derived_name_template": "windows server",
            "derived_version_template": "{version}",
            "priority": 1,
            "enabled": True,
            "notes": "override",
            "flags": "IGNORECASE",
        },
        {
            "id": "custom-ubuntu-preview",
            "name": "Ubuntu preview",
            "pattern": r"^(?P<name>ubuntu) preview$",
            "source_scope": "os_name",
            "derived_name_template": "ubuntu",
            "derived_version_template": "preview",
            "priority": 70,
            "enabled": True,
            "notes": "custom",
            "flags": "IGNORECASE",
        },
    ]

    class DummyContainer:
        def read_item(self, item, partition_key):
            return {"rules": persisted_rules}

    monkeypatch.setattr(store, "_container", lambda: DummyContainer())

    rules = store.get_rules()
    default_override = next(item for item in rules if item["id"] == "default-windows-server-name")
    custom_rule = next(item for item in rules if item["id"] == "custom-ubuntu-preview")

    assert default_override["priority"] == 1
    assert default_override["is_default"] is True
    assert default_override["is_overridden"] is True
    assert default_override["notes"] == "override"
    assert custom_rule["is_default"] is False
    assert custom_rule["rule_origin"] == "custom"


@pytest.mark.asyncio
async def test_os_extraction_rules_store_update_rule_replaces_existing_rule(monkeypatch):
    store = OSExtractionRulesStore()
    existing_rule = {
        "id": "rule-1",
        "name": "Windows Server release",
        "pattern": r"(?P<name>windows server)\s+(?P<version>20\d{2})",
        "source_scope": "combined",
        "derived_name_template": "{name}",
        "derived_version_template": "{version}",
        "priority": 100,
        "enabled": True,
        "notes": "original",
        "flags": "IGNORECASE",
    }

    saved_payload = {}

    monkeypatch.setattr(store, "get_rules", lambda: [existing_rule])

    async def fake_save_rules(rules):
        saved_payload["rules"] = rules
        return rules

    monkeypatch.setattr(store, "save_rules", fake_save_rules)

    updated = await store.update_rule("rule-1", {
        "pattern": r"(?P<name>windows server)\s+(?P<version>20\d{2}|2012 r2)",
        "priority": 10,
        "notes": "updated",
        "enabled": False,
    })

    assert updated is not None
    assert updated["id"] == "rule-1"
    assert updated["priority"] == 10
    assert updated["enabled"] is False
    assert updated["notes"] == "updated"
    assert "2012 r2" in updated["pattern"]
    assert saved_payload["rules"][0]["id"] == "rule-1"


@pytest.mark.asyncio
async def test_os_extraction_rules_store_delete_default_rule_resets_override(monkeypatch):
    store = OSExtractionRulesStore()
    persisted_rule = {
        "id": "default-windows-server-name",
        "name": "Windows Server family from OS name",
        "pattern": r"^(?:microsoft\s+)?windows\s+server\s+(?P<version>20\d{2})$",
        "source_scope": "os_name",
        "derived_name_template": "windows server",
        "derived_version_template": "{version}",
        "priority": 1,
        "enabled": False,
        "notes": "override",
        "flags": "IGNORECASE",
    }

    monkeypatch.setattr(store, "_get_persisted_rules", lambda: [persisted_rule])

    saved_payload = {}

    async def fake_save_rules(rules):
        saved_payload["rules"] = rules
        return store._merge_rules(rules)

    monkeypatch.setattr(store, "save_rules", fake_save_rules)

    deleted = await store.delete_rule("default-windows-server-name")

    assert deleted is True
    assert saved_payload["rules"] == []