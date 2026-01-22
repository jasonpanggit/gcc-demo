"""Tests for Node.js EOL table parsing."""

import pytest
import requests
from bs4 import BeautifulSoup

from agents.nodejs_agent import NodeJSEOLAgent


NODEJS_URL = "https://nodejs.org/en/about/previous-releases"


def _fetch_nodejs_soup() -> BeautifulSoup:
    try:
        response = requests.get(NODEJS_URL, timeout=15)
        response.raise_for_status()
    except Exception as exc:  # pragma: no cover - network issues
        pytest.skip(f"Unable to fetch Node.js release info: {exc}")
    return BeautifulSoup(response.text, "html.parser")


@pytest.mark.integration
def test_parse_nodejs_eol_table_with_version() -> None:
    agent = NodeJSEOLAgent()
    soup = _fetch_nodejs_soup()

    result = agent._parse_nodejs_page(soup, software_name="nodejs", version="20")

    assert result is not None
    assert result["version"] == "20"
    assert result["release"]
    assert result["status"]


@pytest.mark.integration
def test_parse_nodejs_eol_table_default_first_row() -> None:
    agent = NodeJSEOLAgent()
    soup = _fetch_nodejs_soup()

    rows = agent._parse_nodejs_page_all(soup)

    assert rows is not None
    assert rows
    first = rows[0]
    assert first["version"]
    assert first["release"]
    assert first["status"]


@pytest.mark.integration
def test_print_nodejs_eol_rows(capsys) -> None:
    agent = NodeJSEOLAgent()
    soup = _fetch_nodejs_soup()

    rows = agent._parse_nodejs_page_all(soup)

    assert rows, "No Node.js EOL rows extracted"
    with capsys.disabled():
        print("\nExtracted Node.js EOL rows:")
        for entry in rows:
            print(entry)
