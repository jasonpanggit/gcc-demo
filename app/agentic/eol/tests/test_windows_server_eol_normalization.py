from bs4 import BeautifulSoup

from agents.microsoft_agent import MicrosoftEOLAgent
from utils.normalization import normalize_os_name_version, normalize_os_record


def test_normalize_os_name_version_prefers_windows_server_release_from_name():
    normalized_name, normalized_version = normalize_os_name_version(
        "Microsoft Windows Server 2019 Datacenter",
        "10.0",
    )

    assert normalized_name == "windows server"
    assert normalized_version == "2019"


def test_normalize_os_name_version_preserves_windows_server_r2_release():
    normalized_name, normalized_version = normalize_os_name_version(
        "Windows Server 2012 R2 Datacenter",
        "6.3",
    )

    assert normalized_name == "windows server"
    assert normalized_version == "2012 r2"


def test_normalize_os_name_version_maps_windows_server_kernel_via_central_rule():
    normalized_name, normalized_version = normalize_os_name_version(
        "Windows Server Datacenter",
        "6.3",
    )

    assert normalized_name == "windows server"
    assert normalized_version == "2012 r2"


def test_microsoft_agent_normalizes_windows_server_release_from_name_over_kernel_version():
    agent = MicrosoftEOLAgent()

    normalized_name, normalized_version = agent._normalize_windows_server_name(
        "Windows Server 2022 Datacenter",
        "10.0",
    )

    assert normalized_name == "windows server"
    assert normalized_version == "2022"


def test_normalize_os_record_returns_display_and_canonical_windows_server_fields():
    normalized = normalize_os_record(
        "Microsoft Windows Server 2025 Datacenter",
        "10.0",
        "Windows",
    )

    assert normalized["os_name"] == "Windows Server"
    assert normalized["os_version"] == "2025"
    assert normalized["normalized_os_name"] == "windows server"
    assert normalized["normalized_os_version"] == "2025"
    assert normalized["raw_os_name"] == "Microsoft Windows Server 2025 Datacenter"


def test_normalize_os_record_returns_display_and_canonical_linux_fields():
    normalized = normalize_os_record(
        "Ubuntu 22.04 LTS",
        "22.04",
        "Linux",
    )

    assert normalized["os_name"] == "Ubuntu"
    assert normalized["os_version"] == "22.04"
    assert normalized["normalized_os_name"] == "ubuntu"
    assert normalized["os_type"] == "Linux"


def test_parse_windows_server_eol_matches_r2_exactly():
    agent = MicrosoftEOLAgent()
    soup = BeautifulSoup(
        """
        <table>
          <thead>
            <tr>
              <th>Windows Server Version</th>
              <th>Editions</th>
              <th>Availability Date</th>
              <th>Mainstream Support End Date</th>
              <th>Extended Support End Date</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>Windows Server 2012</td>
              <td>Datacenter</td>
              <td>09/04/2012</td>
              <td>10/09/2018</td>
              <td>10/10/2023</td>
            </tr>
            <tr>
              <td>Windows Server 2012 R2</td>
              <td>Datacenter</td>
              <td>11/25/2013</td>
              <td>10/09/2018</td>
              <td>10/10/2023</td>
            </tr>
          </tbody>
        </table>
        """,
        "html.parser",
    )

    results = agent._parse_windows_server_eol(soup, "2012 R2")

    assert results is not None
    assert {item["version"] for item in results} == {"2012 R2 Datacenter"}