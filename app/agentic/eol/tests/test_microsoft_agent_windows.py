"""Tests for Microsoft Windows EOL table parsing."""

import pytest
import requests
from bs4 import BeautifulSoup

from agents.microsoft_agent import MicrosoftEOLAgent


WINDOWS_URL = "https://learn.microsoft.com/en-us/windows/release-health/release-information"
WINDOWS_11_URL = "https://learn.microsoft.com/en-us/windows/release-health/windows11-release-information"


def _fetch_windows_soup() -> BeautifulSoup:
    try:
        response = requests.get(WINDOWS_URL, timeout=15)
        response.raise_for_status()
    except Exception as exc:  # pragma: no cover - network issues
        pytest.skip(f"Unable to fetch Windows release info: {exc}")
    return BeautifulSoup(response.text, "html.parser")


def _fetch_windows_11_soup() -> BeautifulSoup:
    try:
        response = requests.get(WINDOWS_11_URL, timeout=15)
        response.raise_for_status()
    except Exception as exc:  # pragma: no cover - network issues
        pytest.skip(f"Unable to fetch Windows 11 release info: {exc}")
    return BeautifulSoup(response.text, "html.parser")


@pytest.mark.integration
def test_parse_windows_10_ltsc_eol_table() -> None:
    agent = MicrosoftEOLAgent()
    soup = _fetch_windows_soup()

    results = agent._parse_windows_eol(soup, version="2019")

    assert results is not None
    assert results
    matching = [row for row in results if "2019" in row["version"]]
    assert matching
    for row in matching:
        assert row["release"]
        assert row["eol"]


@pytest.mark.integration
def test_parse_windows_10_tables_expected_count() -> None:
    agent = MicrosoftEOLAgent()
    soup = _fetch_windows_soup()

    results = agent._parse_windows_eol(soup)

    assert results is not None
    assert len(results) == 7


@pytest.mark.integration
def test_print_windows_eol_row() -> None:
    agent = MicrosoftEOLAgent()
    soup = _fetch_windows_soup()

    results = agent._parse_windows_eol(soup)

    assert results is not None
    print("\nExtracted Windows EOL rows:")
    for entry in results:
        print(entry)


@pytest.mark.integration
def test_parse_windows_11_release_info() -> None:
    agent = MicrosoftEOLAgent()
    soup = _fetch_windows_11_soup()

    results = agent._parse_windows_eol(soup)

    assert results is not None
    assert results
    allowed_names = {"Windows 11", "Windows 11 Enterprise", "Windows 11 IoT Enterprise"}
    for row in results:
        assert row["software_name"] in allowed_names
        assert row["version"]
        assert row["release"]


@pytest.mark.integration
def test_print_windows_11_eol_rows() -> None:
    agent = MicrosoftEOLAgent()
    soup = _fetch_windows_11_soup()

    results = agent._parse_windows_eol(soup)

    assert results is not None
    print("\nExtracted Windows 11 EOL rows:")
    for entry in results:
        print(entry)
