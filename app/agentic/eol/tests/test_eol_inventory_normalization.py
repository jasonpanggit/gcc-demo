import pytest

from utils.eol_inventory import EolInventory


class DummyContainer:
    def __init__(self, docs):
        self.docs = {(doc["id"], doc["software_key"]): dict(doc) for doc in docs}
        self.upserts = []
        self.deletes = []
        self.replacements = []

    def read_item(self, item, partition_key):
        return dict(self.docs[(item, partition_key)])

    def query_items(self, query, parameters=None, enable_cross_partition_query=True):
        if "WHERE c.item_type = 'os'" in query:
            return [dict(doc) for doc in self.docs.values() if doc.get("item_type") == "os"]
        return [dict(doc) for doc in self.docs.values()]

    def upsert_item(self, doc):
        self.upserts.append(dict(doc))
        self.docs[(doc["id"], doc["software_key"])] = dict(doc)

    def delete_item(self, item, partition_key):
        self.deletes.append((item, partition_key))
        self.docs.pop((item, partition_key), None)

    def replace_item(self, item, body):
        self.replacements.append(dict(body))
        self.docs[(body["id"], body["software_key"])] = dict(body)


@pytest.mark.asyncio
async def test_update_record_rekeys_when_normalized_values_change():
    inventory = EolInventory()
    original_doc = {
        "id": "windowsserver 2025-datacenter-g2:any",
        "software_key": "windowsserver 2025-datacenter-g2",
        "version_key": "any",
        "software_name": "windowsserver 2025-datacenter-g2",
        "version": None,
        "eol_date": None,
        "support_end_date": None,
        "release_date": None,
        "status": None,
        "risk_level": None,
        "confidence": None,
        "source": None,
        "source_url": None,
        "agent_used": None,
        "normalized_software_name": "windowsserver 2025-datacenter-g2",
        "normalized_version": None,
        "raw_software_name": "WindowsServer 2025-datacenter-g2",
        "raw_version": None,
        "item_type": "os",
        "data": {},
        "created_at": "2026-03-09T00:00:00+00:00",
        "updated_at": "2026-03-09T00:00:00+00:00",
    }
    container = DummyContainer([original_doc])
    inventory.container = container
    inventory.initialized = True

    updated = await inventory.update_record(
        original_doc["id"],
        original_doc["software_key"],
        {
            "normalized_software_name": "windows server",
            "normalized_version": "2025",
        },
    )

    assert updated is not None
    assert updated["software_key"] == "windows server"
    assert updated["version_key"] == "2025"
    assert updated["id"] == "windows server:2025"
    assert updated["software_name"] == "windows server"
    assert updated["version"] == "2025"
    assert container.upserts[0]["software_key"] == "windows server"
    assert container.deletes == [(original_doc["id"], original_doc["software_key"])]


@pytest.mark.asyncio
async def test_reapply_os_normalization_previews_and_updates_changed_rows():
    inventory = EolInventory()
    original_doc = {
        "id": "windowsserver 2025-datacenter-g2:any",
        "software_key": "windowsserver 2025-datacenter-g2",
        "version_key": "any",
        "software_name": "windowsserver 2025-datacenter-g2",
        "version": None,
        "eol_date": None,
        "support_end_date": None,
        "release_date": None,
        "status": None,
        "risk_level": None,
        "confidence": None,
        "source": None,
        "source_url": None,
        "agent_used": None,
        "normalized_software_name": "windowsserver 2025-datacenter-g2",
        "normalized_version": None,
        "raw_software_name": "WindowsServer 2025-datacenter-g2",
        "raw_version": None,
        "derivation_strategy": "passthrough",
        "derivation_rule_id": None,
        "item_type": "os",
        "data": {},
        "created_at": "2026-03-09T00:00:00+00:00",
        "updated_at": "2026-03-09T00:00:00+00:00",
    }
    container = DummyContainer([original_doc])
    inventory.container = container
    inventory.initialized = True

    preview = await inventory.reapply_os_normalization(apply_changes=False, preview_limit=10)

    assert preview["scanned"] == 1
    assert preview["changed"] == 1
    assert preview["updated"] == 0
    assert preview["items"][0]["proposed"]["normalized_software_name"] == "windows server"
    assert preview["items"][0]["proposed"]["normalized_version"] == "2025"
    assert preview["items"][0]["requires_rekey"] is True

    applied = await inventory.reapply_os_normalization(apply_changes=True, preview_limit=10)

    assert applied["updated"] == 1
    assert container.upserts[0]["software_key"] == "windows server"
    assert container.deletes == [(original_doc["id"], original_doc["software_key"])]