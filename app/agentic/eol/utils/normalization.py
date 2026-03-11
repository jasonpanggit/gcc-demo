"""Centralized normalization utilities for consistent cache keys across all agents."""
from dataclasses import dataclass
from typing import Any, List, Tuple, Optional

from .os_extraction_rules import os_extraction_rules_store


import re


KB_EXPLICIT_PATTERN = re.compile(r"\bKB\s*[-:]?\s*(\d{6,8})\b", re.IGNORECASE)
KB_NUMERIC_ONLY_PATTERN = re.compile(r"^\d{6,8}$")


def normalize_kb_id(value: Optional[str], *, allow_bare_numeric: bool = True) -> Optional[str]:
    """Return a canonical KB identifier like KB5050001 when one can be inferred."""
    if not value:
        return None

    text = str(value).strip()
    if not text:
        return None

    explicit_match = KB_EXPLICIT_PATTERN.search(text)
    if explicit_match:
        return f"KB{explicit_match.group(1)}"

    if allow_bare_numeric and KB_NUMERIC_ONLY_PATTERN.fullmatch(text):
        return f"KB{text}"

    return None


def extract_kb_ids(value: Any, *, allow_bare_numeric: bool = False) -> List[str]:
    """Extract ordered unique KB identifiers from text or iterables of text."""
    if value is None:
        return []

    if isinstance(value, (list, tuple, set)):
        results: List[str] = []
        seen = set()
        for item in value:
            for kb_id in extract_kb_ids(item, allow_bare_numeric=allow_bare_numeric):
                if kb_id in seen:
                    continue
                seen.add(kb_id)
                results.append(kb_id)
        return results

    text = str(value)
    results: List[str] = []
    seen = set()

    for match in KB_EXPLICIT_PATTERN.finditer(text):
        kb_id = f"KB{match.group(1)}"
        if kb_id in seen:
            continue
        seen.add(kb_id)
        results.append(kb_id)

    if results:
        return results

    normalized_single = normalize_kb_id(text, allow_bare_numeric=allow_bare_numeric)
    return [normalized_single] if normalized_single else []


def normalize_kb_list(values: Any, *, allow_bare_numeric: bool = False) -> List[str]:
    """Normalize KB identifiers from strings, lists, or mixed payloads into a unique list."""
    return extract_kb_ids(values, allow_bare_numeric=allow_bare_numeric)


@dataclass
class OSDerivationResult:
    raw_name: str
    raw_version: Optional[str]
    normalized_name: str
    normalized_version: Optional[str]
    strategy: str
    rule_id: Optional[str] = None
    rule_name: Optional[str] = None
    source_scope: Optional[str] = None
    pattern: Optional[str] = None
    notes: Optional[str] = None

    def to_dict(self) -> dict[str, Optional[str]]:
        return {
            "raw_name": self.raw_name,
            "raw_version": self.raw_version,
            "normalized_name": self.normalized_name,
            "normalized_version": self.normalized_version,
            "strategy": self.strategy,
            "rule_id": self.rule_id,
            "rule_name": self.rule_name,
            "source_scope": self.source_scope,
            "pattern": self.pattern,
            "notes": self.notes,
        }


def derive_os_name_version(os_name: str, version: Optional[str] = None) -> dict[str, Optional[str]]:
    """Derive canonical OS family + version and include extraction metadata.

    Product-specific normalization is centrally defined in the OS extraction
    rules store. Code only provides generic empty-input and passthrough
    behavior when no rule matches.
    """
    raw_name = (os_name or "").strip()
    raw_version = version.strip() if isinstance(version, str) else version
    if not raw_name:
        return OSDerivationResult(
            raw_name="",
            raw_version=raw_version,
            normalized_name="",
            normalized_version=raw_version,
            strategy="empty_input",
        ).to_dict()

    custom_match = os_extraction_rules_store.match(raw_name, raw_version)
    if custom_match:
        return OSDerivationResult(
            raw_name=raw_name,
            raw_version=raw_version,
            normalized_name=custom_match["normalized_name"],
            normalized_version=custom_match.get("normalized_version"),
            strategy=str(custom_match.get("strategy") or "custom_regex"),
            rule_id=custom_match.get("rule_id"),
            rule_name=custom_match.get("rule_name"),
            source_scope=custom_match.get("source_scope"),
            pattern=custom_match.get("pattern"),
            notes=custom_match.get("notes"),
        ).to_dict()

    return OSDerivationResult(
        raw_name=raw_name,
        raw_version=raw_version,
        normalized_name=raw_name.lower().strip(),
        normalized_version=raw_version,
        strategy="passthrough",
    ).to_dict()


def normalize_os_name_version(os_name: str, version: Optional[str] = None) -> Tuple[str, Optional[str]]:
    """
    Normalize OS name and version for consistent cache lookups and storage.
    
    This ensures that both cache queries and cache writes use the same keys,
    preventing duplicates from being created.
    
    Args:
        os_name: Original OS name (e.g., "Microsoft Windows Server 2025 Datacenter")
        version: Original version (e.g., "10.0")
    
    Returns:
        Tuple of (normalized_name, normalized_version)
        
    Examples:
        - "Microsoft Windows Server 2025 Datacenter", "10.0" -> "windows server", "2025"
        - "Windows Server 2019", None -> "windows server", "2019"
        - "Ubuntu 22.04", "22.04" -> "ubuntu", "22.04"
    """
    derived = derive_os_name_version(os_name, version)
    return str(derived.get("normalized_name") or ""), derived.get("normalized_version")


def format_normalized_os_name(os_name: Optional[str]) -> str:
    """Return a display-friendly OS family name from a canonical normalized value."""
    normalized = (os_name or "").strip().lower()
    if not normalized:
        return ""
    if normalized == "windows server":
        return "Windows Server"
    if normalized == "windows":
        return "Windows"
    if normalized == "ubuntu":
        return "Ubuntu"
    if normalized == "rhel":
        return "RHEL"
    if normalized == "centos":
        return "CentOS"
    if normalized == "debian":
        return "Debian"
    return " ".join(part.capitalize() for part in normalized.split())


def normalize_os_record(
    os_name: Optional[str],
    os_version: Optional[str] = None,
    os_type: Optional[str] = None,
) -> dict[str, Optional[str]]:
    """Normalize raw OS fields into canonical and display-safe values."""
    raw_name = (os_name or "").strip()
    raw_version = os_version.strip() if isinstance(os_version, str) else os_version
    derived = derive_os_name_version(raw_name, raw_version)

    normalized_name = derived.get("normalized_name") or (raw_name.lower() if raw_name else "")
    normalized_version = derived.get("normalized_version")
    display_name = format_normalized_os_name(normalized_name) or raw_name or "Unknown"
    display_version = normalized_version if normalized_version not in (None, "") else raw_version

    resolved_os_type = (os_type or "").strip()
    if not resolved_os_type:
        resolved_os_type = "Windows" if "windows" in normalized_name else ("Linux" if normalized_name else "Unknown")

    return {
        "raw_os_name": raw_name or None,
        "raw_os_version": raw_version,
        "os_name": display_name,
        "os_version": display_version,
        "normalized_os_name": normalized_name or None,
        "normalized_os_version": normalized_version,
        "os_type": resolved_os_type or None,
        "derivation_strategy": derived.get("strategy"),
        "derivation_rule_id": derived.get("rule_id"),
        "derivation_rule_name": derived.get("rule_name"),
    }


def normalize_software_name_version(software_name: str, version: Optional[str] = None) -> Tuple[str, Optional[str]]:
    """
    Normalize software name and version for consistent cache lookups and storage.
    
    Args:
        software_name: Original software name
        version: Original version
    
    Returns:
        Tuple of (normalized_name, normalized_version)
    """
    if not software_name:
        return "", version
    
    # For now, simple normalization (can be enhanced as needed)
    normalized_name = software_name.lower().strip()
    normalized_version = version.lower().strip() if version else version
    
    return normalized_name, normalized_version
