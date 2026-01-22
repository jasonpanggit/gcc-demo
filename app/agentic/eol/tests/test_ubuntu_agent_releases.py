"""Tests for Ubuntu releases table parsing."""

import pytest
import requests
from bs4 import BeautifulSoup

from agents.ubuntu_agent import UbuntuEOLAgent


UBUNTU_RELEASES_URL = "https://documentation.ubuntu.com/project/release-team/list-of-releases/"


def _fetch_ubuntu_releases_soup() -> BeautifulSoup:
    try:
        response = requests.get(UBUNTU_RELEASES_URL, timeout=20)
        response.raise_for_status()
    except Exception as exc:  # pragma: no cover - network issues
        pytest.skip(f"Unable to fetch Ubuntu releases page: {exc}")
    return BeautifulSoup(response.text, "html.parser")


def _filter_by_version(agent: UbuntuEOLAgent, results: list[dict], version: str) -> list[dict]:
    version_norm = agent._normalize_version(version)
    return [entry for entry in results if version_norm in (entry.get("cycle") or "")]


@pytest.mark.integration
def test_parse_ubuntu_releases_table_default() -> None:
    agent = UbuntuEOLAgent()
    soup = _fetch_ubuntu_releases_soup()

    results = agent._parse_ubuntu_releases(soup)

    assert results is not None
    assert results
    first = results[0]
    assert first.get("cycle")
    # releaseDate might be None if date parsing fails, but the key should exist
    assert "releaseDate" in first
    assert first.get("codename")
    assert "eol" in first


@pytest.mark.integration
def test_parse_ubuntu_releases_table_with_version() -> None:
    agent = UbuntuEOLAgent()
    soup = _fetch_ubuntu_releases_soup()

    results = agent._parse_ubuntu_releases(soup)
    matches = _filter_by_version(agent, results, "24.04")

    assert matches
    for entry in matches:
        assert entry.get("cycle")
        # releaseDate might be None if date parsing fails, but the key should exist
        assert "releaseDate" in entry
        assert entry.get("eol") or entry.get("support")
        assert entry.get("codename")


@pytest.mark.integration
def test_print_all_ubuntu_eol_records() -> None:
    """Print all extracted Ubuntu EOL records for inspection."""
    agent = UbuntuEOLAgent()
    soup = _fetch_ubuntu_releases_soup()

    results = agent._parse_ubuntu_releases(soup)

    assert results is not None
    assert results

    print(f"\n{'='*80}")
    print(f"UBUNTU EOL RECORDS - Total: {len(results)}")
    print(f"{'='*80}\n")

    for idx, record in enumerate(results, 1):
        print(f"Record {idx}:")
        print(f"  Cycle:        {record.get('cycle', 'N/A')}")
        print(f"  Codename:     {record.get('codename', 'N/A')}")
        print(f"  Release Date: {record.get('releaseDate', 'N/A')}")
        print(f"  Support End:  {record.get('support', 'N/A')}")
        print(f"  EOL Date:     {record.get('eol', 'N/A')}")
        print(f"  LTS:          {record.get('lts', False)}")
        print(f"  Source:       {record.get('source', 'N/A')}")
        print()

    print(f"{'='*80}")
    print(f"LTS Releases: {sum(1 for r in results if r.get('lts', False))}")
    print(f"Non-LTS:      {sum(1 for r in results if not r.get('lts', False))}")
    print(f"{'='*80}\n")


@pytest.mark.integration
def test_print_ubuntu_release_rows() -> None:
    agent = UbuntuEOLAgent()
    soup = _fetch_ubuntu_releases_soup()

    results = agent._parse_ubuntu_releases(soup)

    assert results, "No Ubuntu release rows extracted"
    print("\nExtracted Ubuntu release rows:")
    for entry in results:
        print(entry)
