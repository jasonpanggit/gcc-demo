"""Regression tests for Pydantic v2 CVE model configuration."""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from models.cve_models import CVEAffectedProduct, CVEReference, CVSSScore, UnifiedCVE


def test_leaf_cve_models_are_immutable():
    score = CVSSScore(
        version="3.1",
        base_score=9.8,
        base_severity="CRITICAL",
        vector_string="CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H",
    )
    product = CVEAffectedProduct(vendor="microsoft", product="windows_server", version="2022")
    reference = CVEReference(url="https://example.test/advisory", source="microsoft")

    with pytest.raises(ValidationError, match="Instance is frozen"):
        score.base_score = 7.5

    with pytest.raises(ValidationError, match="Instance is frozen"):
        product.version = "2019"

    with pytest.raises(ValidationError, match="Instance is frozen"):
        reference.url = "https://example.test/other"


def test_unified_cve_json_serializes_datetimes_as_iso_strings():
    published = datetime(2026, 3, 27, 6, 30, tzinfo=timezone.utc)
    modified = datetime(2026, 3, 27, 7, 45, tzinfo=timezone.utc)
    synced = datetime(2026, 3, 27, 8, 0, tzinfo=timezone.utc)

    cve = UnifiedCVE(
        cve_id="CVE-2026-0001",
        description="Example CVE",
        published_date=published,
        last_modified_date=modified,
        last_synced=synced,
    )

    payload = cve.model_dump(mode="json")

    assert payload["published_date"] == published.isoformat()
    assert payload["last_modified_date"] == modified.isoformat()
    assert payload["last_synced"] == synced.isoformat()