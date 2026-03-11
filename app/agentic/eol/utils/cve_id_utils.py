"""Helpers for normalizing and validating CVE identifiers."""
from __future__ import annotations

import re
from typing import Iterable, List, Optional


_CVE_ID_PATTERN = re.compile(r"^CVE-\d{4}-\d{4,}$", re.IGNORECASE)


def normalize_cve_id(value: object) -> str:
    """Return a normalized uppercase CVE-like token."""
    return str(value or "").strip().upper()


def is_valid_cve_id(value: object) -> bool:
    """Return True when *value* matches the public CVE identifier format."""
    candidate = normalize_cve_id(value)
    return bool(candidate and _CVE_ID_PATTERN.fullmatch(candidate))


def filter_valid_cve_ids(values: Optional[Iterable[object]]) -> List[str]:
    """Return unique valid CVE identifiers in first-seen order."""
    if not values:
        return []

    filtered: List[str] = []
    seen: set[str] = set()
    for value in values:
        candidate = normalize_cve_id(value)
        if not is_valid_cve_id(candidate) or candidate in seen:
            continue
        seen.add(candidate)
        filtered.append(candidate)
    return filtered