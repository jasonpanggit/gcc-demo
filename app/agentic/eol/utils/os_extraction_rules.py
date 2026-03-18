"""Custom OS extraction rule storage and matching helpers."""
from __future__ import annotations

import logging
import re
import uuid
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


DEFAULT_OS_EXTRACTION_RULES: List[Dict[str, Any]] = [
    {
        "id": "default-windows-server-name",
        "name": "Windows Server family from OS name",
        "pattern": r"^(?:microsoft\s+)?windows\s+server\s+(?P<version>20\d{2}|19\d{2}|2012\s*r2|2008\s*r2|2003)\b(?:[-_\s]+[a-z0-9]+(?:[-_][a-z0-9]+)*)?$",
        "source_scope": "os_name",
        "derived_name_template": "windows server",
        "derived_version_template": "{version}",
        "priority": 5,
        "enabled": True,
        "notes": "Normalize Windows Server names that already contain the release year in the OS name.",
        "flags": "IGNORECASE",
    },
    {
        "id": "default-windowsserver-azure-image",
        "name": "WindowsServer Azure image SKU",
        "pattern": r"^windowsserver\s+(?P<version>20\d{2}|19\d{2})(?:[-_\s]+[a-z0-9]+(?:[-_][a-z0-9]+)*)?$",
        "source_scope": "os_name",
        "derived_name_template": "windows server",
        "derived_version_template": "{version}",
        "priority": 10,
        "enabled": True,
        "notes": "Normalize Azure VM image names such as WindowsServer 2025-datacenter-g2 or azure-edition to the Windows Server family and release year.",
        "flags": "IGNORECASE",
    },
    {
        "id": "default-windows-server-kernel-63",
        "name": "Windows Server kernel 6.3",
        "pattern": r"^(?:microsoft\s+)?windows\s+server\b.*\b6\.3\b$",
        "source_scope": "combined",
        "derived_name_template": "windows server",
        "derived_version_template": "2012 r2",
        "priority": 15,
        "enabled": True,
        "notes": "Map Windows Server kernel version 6.3 to Windows Server 2012 R2.",
        "flags": "IGNORECASE",
    },
    {
        "id": "default-windows-server-kernel-62",
        "name": "Windows Server kernel 6.2",
        "pattern": r"^(?:microsoft\s+)?windows\s+server\b.*\b6\.2\b$",
        "source_scope": "combined",
        "derived_name_template": "windows server",
        "derived_version_template": "2012",
        "priority": 16,
        "enabled": True,
        "notes": "Map Windows Server kernel version 6.2 to Windows Server 2012.",
        "flags": "IGNORECASE",
    },
    {
        "id": "default-windows-server-kernel-61",
        "name": "Windows Server kernel 6.1",
        "pattern": r"^(?:microsoft\s+)?windows\s+server\b.*\b6\.1\b$",
        "source_scope": "combined",
        "derived_name_template": "windows server",
        "derived_version_template": "2008 r2",
        "priority": 17,
        "enabled": True,
        "notes": "Map Windows Server kernel version 6.1 to Windows Server 2008 R2.",
        "flags": "IGNORECASE",
    },
    {
        "id": "default-windows-server-kernel-60",
        "name": "Windows Server kernel 6.0",
        "pattern": r"^(?:microsoft\s+)?windows\s+server\b.*\b6\.0\b$",
        "source_scope": "combined",
        "derived_name_template": "windows server",
        "derived_version_template": "2008",
        "priority": 18,
        "enabled": True,
        "notes": "Map Windows Server kernel version 6.0 to Windows Server 2008.",
        "flags": "IGNORECASE",
    },
    {
        "id": "default-windows-server-kernel-52",
        "name": "Windows Server kernel 5.2",
        "pattern": r"^(?:microsoft\s+)?windows\s+server\b.*\b5\.2\b$",
        "source_scope": "combined",
        "derived_name_template": "windows server",
        "derived_version_template": "2003",
        "priority": 19,
        "enabled": True,
        "notes": "Map Windows Server kernel version 5.2 to Windows Server 2003.",
        "flags": "IGNORECASE",
    },
    {
        "id": "default-windows-client",
        "name": "Windows client family",
        "pattern": r"^(?P<name>windows)\s+(?P<version>\d+(?:\.\d+)?)\b(?:[-_\s]+[a-z0-9]+(?:[-_][a-z0-9]+)*)?$",
        "source_scope": "os_name",
        "derived_name_template": "windows",
        "derived_version_template": "{version|raw_version}",
        "priority": 30,
        "enabled": True,
        "notes": "Normalize Windows client OS names such as Windows 10 and Windows 11.",
        "flags": "IGNORECASE",
    },
    {
        "id": "default-ubuntu-family",
        "name": "Ubuntu family",
        "pattern": r"^(?P<name>ubuntu)\b(?:[-_\s]+(?P<version>\d+\.\d+))?.*$",
        "source_scope": "os_name",
        "derived_name_template": "ubuntu",
        "derived_version_template": "{version|raw_version}",
        "priority": 40,
        "enabled": True,
        "notes": "Normalize Ubuntu family names while preferring an explicit release from the OS name, then raw version.",
        "flags": "IGNORECASE",
    },
    {
        "id": "default-rhel-family",
        "name": "RHEL family",
        "pattern": r"^(?:(?P<name>rhel)|red\s+hat(?:\s+enterprise(?:\s+linux)?)?)\b(?:[-_\s]+(?P<version>\d+(?:\.\d+)?))?.*$",
        "source_scope": "os_name",
        "derived_name_template": "rhel",
        "derived_version_template": "{version|raw_version}",
        "priority": 41,
        "enabled": True,
        "notes": "Normalize Red Hat Enterprise Linux family names to the rhel canonical family.",
        "flags": "IGNORECASE",
    },
    {
        "id": "default-centos-family",
        "name": "CentOS family",
        "pattern": r"^(?P<name>centos)\b(?:[-_\s]+(?P<version>\d+(?:\.\d+)?))?.*$",
        "source_scope": "os_name",
        "derived_name_template": "centos",
        "derived_version_template": "{version|raw_version}",
        "priority": 42,
        "enabled": True,
        "notes": "Normalize CentOS family names and preserve the release from the OS name or raw version.",
        "flags": "IGNORECASE",
    },
    {
        "id": "default-debian-family",
        "name": "Debian family",
        "pattern": r"^(?P<name>debian)\b(?:[-_\s]+(?P<version>\d+(?:\.\d+)?))?.*$",
        "source_scope": "os_name",
        "derived_name_template": "debian",
        "derived_version_template": "{version|raw_version}",
        "priority": 43,
        "enabled": True,
        "notes": "Normalize Debian family names and preserve the release from the OS name or raw version.",
        "flags": "IGNORECASE",
    },
]


class OSExtractionRulesStore:
    """In-memory store for user-defined OS extraction regex rules."""

    def __init__(self, container_id: str = "os_extraction_rules"):
        self.container_id = container_id
        self.document_id = "default"
        self.partition_key = "os_extraction_rules"
        self._rules_cache: List[Dict[str, Any]] = []
        self._persisted_rules_cache: List[Dict[str, Any]] = []
        self._rules_loaded = False

    def _default_rules(self) -> List[Dict[str, Any]]:
        return [
            self._normalize_rule(rule, index)
            for index, rule in enumerate(DEFAULT_OS_EXTRACTION_RULES)
        ]

    def _default_rule_map(self) -> Dict[str, Dict[str, Any]]:
        return {rule["id"]: rule for rule in self._default_rules()}

    @staticmethod
    def _annotate_rule(
        rule: Dict[str, Any],
        *,
        default_rule: Optional[Dict[str, Any]] = None,
        has_override: bool = False,
    ) -> Dict[str, Any]:
        annotated = deepcopy(rule)
        is_default = default_rule is not None
        annotated["is_default"] = is_default
        annotated["is_seeded"] = is_default
        annotated["rule_origin"] = "default" if is_default else "custom"
        annotated["is_overridden"] = has_override
        return annotated

    def _merge_rules(self, persisted_rules: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        default_map = self._default_rule_map()
        persisted_map = {rule["id"]: rule for rule in persisted_rules}
        merged: List[Dict[str, Any]] = []

        for default_rule in default_map.values():
            persisted_rule = persisted_map.pop(default_rule["id"], None)
            merged.append(
                self._annotate_rule(
                    persisted_rule or default_rule,
                    default_rule=default_rule,
                    has_override=persisted_rule is not None,
                )
            )

        for custom_rule in persisted_map.values():
            merged.append(self._annotate_rule(custom_rule))

        merged.sort(key=lambda item: (item.get("priority", 100), item.get("name", "")))
        return merged

    @staticmethod
    def _normalize_rule(rule: Dict[str, Any], index: int = 0) -> Dict[str, Any]:
        normalized = {
            "id": str(rule.get("id") or f"rule-{index + 1}-{uuid.uuid4().hex[:8]}"),
            "name": str(rule.get("name") or f"Rule {index + 1}").strip(),
            "pattern": str(rule.get("pattern") or "").strip(),
            "source_scope": str(rule.get("source_scope") or "combined").strip().lower(),
            "derived_name_template": str(rule.get("derived_name_template") or "{name}").strip(),
            "derived_version_template": str(rule.get("derived_version_template") or "{version}").strip(),
            "priority": int(rule.get("priority") or 100),
            "enabled": bool(rule.get("enabled", True)),
            "notes": str(rule.get("notes") or "").strip(),
            "flags": str(rule.get("flags") or "IGNORECASE").strip().upper(),
        }
        if normalized["source_scope"] not in {"combined", "os_name", "version"}:
            normalized["source_scope"] = "combined"
        return normalized

    def _parse_flags(self, flag_text: str) -> int:
        flags = 0
        parts = [part.strip().upper() for part in (flag_text or "").split("|") if part.strip()]
        for part in parts:
            if part == "IGNORECASE":
                flags |= re.IGNORECASE
            elif part == "MULTILINE":
                flags |= re.MULTILINE
            elif part == "DOTALL":
                flags |= re.DOTALL
        return flags

    @staticmethod
    def _render_template(template: str, groups: Dict[str, str]) -> str:
        def replace_token(match: re.Match[str]) -> str:
            token = match.group(1)
            options = [part.strip() for part in token.split("|") if part.strip()]
            for option in options:
                value = groups.get(option)
                if value not in (None, ""):
                    return str(value)
            return ""

        return re.sub(r"\{([^{}]+)\}", replace_token, template or "")

    def _ensure_loaded(self) -> None:
        if self._rules_loaded:
            return
        self._rules_loaded = True
        # Use defaults + any persisted rules from in-memory store
        self._rules_cache = self._merge_rules(self._persisted_rules_cache)

    def get_rules(self) -> List[Dict[str, Any]]:
        self._ensure_loaded()
        return deepcopy(self._rules_cache)

    def _get_persisted_rules(self) -> List[Dict[str, Any]]:
        self._ensure_loaded()
        return deepcopy(self._persisted_rules_cache)

    def match(self, raw_name: str, raw_version: Optional[str]) -> Optional[Dict[str, Any]]:
        self._ensure_loaded()
        combined = " ".join(part for part in [raw_name or "", raw_version or ""] if part).strip()
        for rule in self._rules_cache:
            if not rule.get("enabled"):
                continue
            source_scope = rule.get("source_scope") or "combined"
            if source_scope == "os_name":
                candidate = raw_name or ""
            elif source_scope == "version":
                candidate = raw_version or ""
            else:
                candidate = combined
            if not candidate:
                continue
            try:
                match = re.search(rule["pattern"], candidate, self._parse_flags(rule.get("flags", "IGNORECASE")))
            except re.error as exc:
                logger.warning("Skipping invalid OS extraction regex %s: %s", rule.get("id"), exc)
                continue
            if not match:
                continue

            groups = {key: value for key, value in match.groupdict().items() if value is not None}
            groups.setdefault("name", groups.get("os_name", ""))
            groups.setdefault("version", groups.get("os_version", ""))
            groups.setdefault("raw_name", raw_name or "")
            groups.setdefault("raw_version", raw_version or "")
            groups.setdefault("combined", combined)

            derived_name = self._render_template(rule.get("derived_name_template") or "{name}", groups).strip().lower()
            derived_version = self._render_template(rule.get("derived_version_template") or "{version}", groups).strip().lower()
            if not derived_name:
                continue

            return {
                "normalized_name": derived_name,
                "normalized_version": derived_version or None,
                "strategy": "custom_regex",
                "rule_id": rule.get("id"),
                "rule_name": rule.get("name"),
                "source_scope": source_scope,
                "pattern": rule.get("pattern"),
                "matched_text": match.group(0),
                "notes": rule.get("notes") or None,
            }
        return None

    async def save_rules(self, rules: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        normalized_rules = [
            self._normalize_rule(rule, index)
            for index, rule in enumerate(rules or [])
            if isinstance(rule, dict) and str(rule.get("pattern") or "").strip()
        ]
        normalized_rules.sort(key=lambda item: (item.get("priority", 100), item.get("name", "")))
        self._persisted_rules_cache = normalized_rules
        self._rules_cache = self._merge_rules(normalized_rules)
        self._rules_loaded = True
        return deepcopy(self._rules_cache)

    async def add_rule(self, rule: Dict[str, Any]) -> Dict[str, Any]:
        rules = self._get_persisted_rules()
        normalized = self._normalize_rule(rule, len(rules))
        rules = [existing for existing in rules if existing.get("id") != normalized["id"]]
        rules.append(normalized)
        saved = await self.save_rules(rules)
        for item in saved:
            if item.get("id") == normalized["id"]:
                return item
        return normalized

    async def update_rule(self, rule_id: str, rule: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        merged_rules = self.get_rules()
        existing_rule = next((item for item in merged_rules if item.get("id") == rule_id), None)
        if not existing_rule:
            return None

        persisted_rules = self._get_persisted_rules()
        next_rules: List[Dict[str, Any]] = []
        replaced = False

        merged_rule = {**existing_rule, **rule, "id": rule_id}
        normalized_rule = self._normalize_rule(merged_rule, len(persisted_rules))

        for index, existing in enumerate(persisted_rules):
            if existing.get("id") != rule_id:
                next_rules.append(existing)
                continue
            next_rules.append(self._normalize_rule(merged_rule, index))
            replaced = True

        if not replaced:
            next_rules.append(normalized_rule)

        saved = await self.save_rules(next_rules)
        for item in saved:
            if item.get("id") == rule_id:
                return item
        return None

    async def delete_rule(self, rule_id: str) -> bool:
        persisted_rules = self._get_persisted_rules()
        filtered = [rule for rule in persisted_rules if rule.get("id") != rule_id]
        if len(filtered) != len(persisted_rules):
            await self.save_rules(filtered)
            return True

        if rule_id not in self._default_rule_map():
            return False

        await self.save_rules(filtered)
        return True


os_extraction_rules_store = OSExtractionRulesStore()