"""Tests for Microsoft SQL Server lifecycle parsing."""

import pytest
import requests
from bs4 import BeautifulSoup

from agents.microsoft_agent import MicrosoftEOLAgent


SQL_SERVER_URL = "https://learn.microsoft.com/en-us/sql/sql-server/end-of-support/sql-server-end-of-life-overview"


def _fetch_sql_server_soup() -> BeautifulSoup:
    try:
        response = requests.get(SQL_SERVER_URL, timeout=15)
        response.raise_for_status()
    except Exception as exc:  # pragma: no cover - network issues
        pytest.skip(f"Unable to fetch SQL Server lifecycle info: {exc}")
    return BeautifulSoup(response.text, "html.parser")


@pytest.mark.integration
def test_parse_sql_server_eol_table_with_version() -> None:
    agent = MicrosoftEOLAgent()
    soup = _fetch_sql_server_soup()

    results = agent._parse_sql_server_eol(soup, version="2022")

    assert results is not None
    assert results
    for result in results:
        assert "2022" in result["version"]
        assert result["release"]
        assert result["support"]
        assert result["eol"]


@pytest.mark.integration
def test_parse_sql_server_eol_table_default_first_row() -> None:
    agent = MicrosoftEOLAgent()
    soup = _fetch_sql_server_soup()

    results = agent._parse_sql_server_eol(soup)

    assert results is not None
    assert results
    first = results[0]
    assert first["version"]
    assert first["release"]
    assert first["support"]
    assert first["eol"]


@pytest.mark.integration
def test_print_sql_server_eol_rows(capsys) -> None:
    agent = MicrosoftEOLAgent()
    soup = _fetch_sql_server_soup()

    results = agent._parse_sql_server_eol(soup)

    assert results, "No SQL Server EOL rows extracted"
    with capsys.disabled():
        print("\nExtracted SQL Server EOL rows:")
        for entry in results:
            print(entry)
