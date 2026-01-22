"""Tests for Microsoft Windows Server EOL table parsing."""

import pytest
import requests
from bs4 import BeautifulSoup

from agents.microsoft_agent import MicrosoftEOLAgent


WINDOWS_SERVER_URL = "https://learn.microsoft.com/en-us/windows/release-health/windows-server-release-info"


def _fetch_windows_server_soup() -> BeautifulSoup:
    try:
        response = requests.get(WINDOWS_SERVER_URL, timeout=15)
        response.raise_for_status()
    except Exception as exc:  # pragma: no cover - network issues
        pytest.skip(f"Unable to fetch Windows Server release info: {exc}")
    return BeautifulSoup(response.text, "html.parser")


@pytest.mark.integration
def test_parse_windows_server_eol_table_with_version() -> None:
    agent = MicrosoftEOLAgent()
    soup = _fetch_windows_server_soup()

    results = agent._parse_windows_server_eol(soup, version="2022")

    assert results is not None
    assert results
    for result in results:
        assert result["version"].startswith("2022")
        assert result["release"]
        assert result["support"]
        assert result["eol"]


@pytest.mark.integration
def test_parse_windows_server_eol_table_default_first_row() -> None:
    agent = MicrosoftEOLAgent()
    soup = _fetch_windows_server_soup()

    results = agent._parse_windows_server_eol(soup)

    assert results is not None
    assert results
    first = results[0]
    assert first["version"]
    assert first["release"]
    assert first["support"]
    assert first["eol"]


@pytest.mark.integration
def test_print_windows_server_eol_rows() -> None:
    agent = MicrosoftEOLAgent()
    soup = _fetch_windows_server_soup()

    results = agent._parse_windows_server_eol(soup)

    assert results, "No Windows Server EOL rows extracted"
    print("\nExtracted Windows Server EOL rows:")
    for entry in results:
        print(entry)
