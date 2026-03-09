from unittest.mock import patch

import pytest

from models.cve_models import CVEVendorMetadata
from utils.vendor_feed_client import VendorFeedClient


class _FakeResponse:
    def __init__(self, *, status=200, json_data=None, text_data="", headers=None):
        self.status = status
        self._json_data = json_data
        self._text_data = text_data
        self.headers = headers or {}

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return None

    def raise_for_status(self):
        if self.status >= 400:
            raise RuntimeError(f"HTTP {self.status}")

    async def json(self):
        return self._json_data

    async def text(self):
        return self._text_data


class _FakeSession:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []
        self.closed = False

    def get(self, url, headers=None):
        self.calls.append({"url": url, "headers": headers or {}})
        if not self._responses:
            raise AssertionError("No fake responses remaining")
        return self._responses.pop(0)


def _build_client(fake_session, *, api_key=None):
    client = VendorFeedClient(
        redhat_base_url="https://redhat.example",
        ubuntu_base_url="https://ubuntu.example",
        msrc_base_url="https://api.msrc.microsoft.com/cvrf/v3.0",
        msrc_api_key=api_key,
    )
    client._session = fake_session
    return client


@pytest.mark.asyncio
async def test_fetch_microsoft_cve_uses_keyless_v3_updates_lookup():
    summary_payload = {
        "value": [
            {
                "ID": "2025-Jan",
                "Alias": "2025-Jan",
                "DocumentTitle": "January 2025 Security Updates",
                "CvrfUrl": "https://api.msrc.microsoft.com/cvrf/v3.0/cvrf/2025-Jan",
            }
        ]
    }
    cvrf_xml = """
    <cvrf:cvrfdoc xmlns:cvrf="http://www.icasi.org/CVRF/schema/cvrf/1.1" xmlns:vuln="http://www.icasi.org/CVRF/schema/vuln/1.1">
      <vuln:Vulnerability Ordinal="1">
        <vuln:Title>Windows Kernel Elevation of Privilege Vulnerability</vuln:Title>
        <vuln:Notes>
          <vuln:Note Title="Description" Type="Description" Ordinal="0">Security update for KB5050001 and KB5050002</vuln:Note>
        </vuln:Notes>
        <vuln:CVE>CVE-2025-21333</vuln:CVE>
        <vuln:Threats>
          <vuln:Threat Type="Impact">
            <vuln:Description>Elevation of Privilege</vuln:Description>
          </vuln:Threat>
          <vuln:Threat Type="Severity">
            <vuln:Description>Important</vuln:Description>
          </vuln:Threat>
          <vuln:Threat Type="Exploit Status">
            <vuln:Description>Publicly Disclosed:No;Exploited:Yes;Latest Software Release:Exploitation Detected</vuln:Description>
          </vuln:Threat>
        </vuln:Threats>
        <vuln:Remediations>
          <vuln:Remediation Type="Vendor Fix">
            <vuln:Description>Install KB5050001</vuln:Description>
            <vuln:URL>https://support.microsoft.com/help/KB5050002</vuln:URL>
          </vuln:Remediation>
        </vuln:Remediations>
      </vuln:Vulnerability>
    </cvrf:cvrfdoc>
    """.strip()

    fake_session = _FakeSession([
        _FakeResponse(status=200, json_data=summary_payload, headers={"Content-Type": "application/json"}),
        _FakeResponse(status=200, text_data=cvrf_xml, headers={"Content-Type": "application/xml"}),
    ])
    client = _build_client(fake_session)

    result = await client.fetch_microsoft_cve("CVE-2025-21333")

    assert result is not None
    assert result["cve_id"] == "CVE-2025-21333"
    assert result["description"] == "Security update for KB5050001 and KB5050002"
    assert result["vendor_metadata"]["source"] == "microsoft"
    assert result["vendor_metadata"]["update_id"] == "2025-Jan"
    assert result["vendor_metadata"]["severity"] == "Important"
    assert result["vendor_metadata"]["impact"] == "Elevation of Privilege"
    assert result["vendor_metadata"]["kb_numbers"] == ["KB5050001", "KB5050002"]
    vendor_metadata = CVEVendorMetadata(**result["vendor_metadata"])
    assert vendor_metadata.kb_numbers == ["KB5050001", "KB5050002"]
    assert vendor_metadata.severity == "Important"
    assert vendor_metadata.impact == "Elevation of Privilege"
    assert vendor_metadata.exploitability == "Publicly Disclosed:No;Exploited:Yes;Latest Software Release:Exploitation Detected"
    assert vendor_metadata.document_title == "January 2025 Security Updates"
    assert vendor_metadata.update_id == "2025-Jan"
    assert vendor_metadata.fix_available is True
    assert fake_session.calls[0]["url"].endswith("/updates/CVE-2025-21333")
    assert fake_session.calls[0]["headers"] == {"Accept": "application/json"}
    assert fake_session.calls[1]["headers"] == {"Accept": "application/xml"}


@pytest.mark.asyncio
async def test_fetch_microsoft_cve_extracts_legacy_numeric_remediation_ids_as_kbs():
        summary_payload = {
                "value": [
                        {
                                "ID": "2018-Nov",
                                "Alias": "2018-Nov",
                                "DocumentTitle": "November 2018 Security Updates",
                                "CvrfUrl": "https://api.msrc.microsoft.com/cvrf/v3.0/cvrf/2018-Nov",
                        }
                ]
        }
        cvrf_xml = """
        <cvrf:cvrfdoc xmlns:cvrf="http://www.icasi.org/CVRF/schema/cvrf/1.1" xmlns:vuln="http://www.icasi.org/CVRF/schema/vuln/1.1">
            <vuln:Vulnerability Ordinal="1">
                <vuln:Title>Legacy Microsoft CVE</vuln:Title>
                <vuln:Notes>
                    <vuln:Note Title="Description" Type="Description" Ordinal="0">Legacy bulletin entry</vuln:Note>
                </vuln:Notes>
                <vuln:CVE>CVE-2018-8476</vuln:CVE>
                <vuln:Threats>
                    <vuln:Threat Type="Severity">
                        <vuln:Description>Important</vuln:Description>
                    </vuln:Threat>
                </vuln:Threats>
                <vuln:Remediations>
                    <vuln:Remediation Type="Vendor Fix">
                        <vuln:Description>4467702</vuln:Description>
                        <vuln:URL>https://www.microsoft.com/download/details.aspx?familyid=test</vuln:URL>
                        <vuln:SubType>Security Update</vuln:SubType>
                    </vuln:Remediation>
                    <vuln:Remediation Type="Vendor Fix">
                        <vuln:Description>Release Notes</vuln:Description>
                        <vuln:URL>https://github.com/Microsoft/ChakraCore/releases/tag/v1.11.3</vuln:URL>
                        <vuln:SubType>Security Update</vuln:SubType>
                    </vuln:Remediation>
                </vuln:Remediations>
            </vuln:Vulnerability>
        </cvrf:cvrfdoc>
        """.strip()

        fake_session = _FakeSession([
                _FakeResponse(status=200, json_data=summary_payload, headers={"Content-Type": "application/json"}),
                _FakeResponse(status=200, text_data=cvrf_xml, headers={"Content-Type": "application/xml"}),
        ])
        client = _build_client(fake_session)

        result = await client.fetch_microsoft_cve("CVE-2018-8476")

        assert result is not None
        assert result["vendor_metadata"]["kb_numbers"] == ["KB4467702"]
        assert result["vendor_metadata"]["fix_available"] is True


@pytest.mark.asyncio
async def test_fetch_microsoft_cve_returns_none_when_updates_lookup_is_empty():
    fake_session = _FakeSession([
        _FakeResponse(status=200, json_data={"value": []}, headers={"Content-Type": "application/json"}),
    ])
    client = _build_client(fake_session)

    result = await client.fetch_microsoft_cve("CVE-2025-99999")

    assert result is None


@pytest.mark.asyncio
async def test_fetch_microsoft_cve_sends_api_key_when_configured():
    summary_payload = {
        "value": [
            {
                "ID": "2025-Jan",
                "CvrfUrl": "https://api.msrc.microsoft.com/cvrf/v3.0/cvrf/2025-Jan",
            }
        ]
    }
    cvrf_xml = """
    <cvrf:cvrfdoc xmlns:cvrf="http://www.icasi.org/CVRF/schema/cvrf/1.1" xmlns:vuln="http://www.icasi.org/CVRF/schema/vuln/1.1">
      <vuln:Vulnerability Ordinal="1">
        <vuln:CVE>CVE-2025-21333</vuln:CVE>
      </vuln:Vulnerability>
    </cvrf:cvrfdoc>
    """.strip()

    fake_session = _FakeSession([
        _FakeResponse(status=200, json_data=summary_payload, headers={"Content-Type": "application/json"}),
        _FakeResponse(status=200, text_data=cvrf_xml, headers={"Content-Type": "application/xml"}),
    ])
    client = _build_client(fake_session, api_key="secret")

    await client.fetch_microsoft_cve("CVE-2025-21333")

    assert fake_session.calls[0]["headers"] == {"Accept": "application/json", "api-key": "secret"}
    assert fake_session.calls[1]["headers"] == {"Accept": "application/xml", "api-key": "secret"}


@pytest.mark.asyncio
async def test_fetch_microsoft_cves_for_kb_returns_all_matching_cves_from_monthly_bulletin():
        summary_payload = {
                "value": [
                        {
                                "ID": "2026-Feb",
                                "Alias": "2026-Feb",
                                "DocumentTitle": "February 2026 Security Updates",
                                "CvrfUrl": "https://api.msrc.microsoft.com/cvrf/v3.0/cvrf/2026-Feb",
                        }
                ]
        }
        cvrf_xml = """
        <cvrf:cvrfdoc xmlns:cvrf="http://www.icasi.org/CVRF/schema/cvrf/1.1" xmlns:vuln="http://www.icasi.org/CVRF/schema/vuln/1.1">
            <vuln:Vulnerability Ordinal="1">
                <vuln:CVE>CVE-2026-21510</vuln:CVE>
                <vuln:Remediations>
                    <vuln:Remediation Type="Vendor Fix">
                        <vuln:Description>Install KB5075999</vuln:Description>
                        <vuln:SubType>Security Update</vuln:SubType>
                    </vuln:Remediation>
                </vuln:Remediations>
            </vuln:Vulnerability>
            <vuln:Vulnerability Ordinal="2">
                <vuln:CVE>CVE-2026-21513</vuln:CVE>
                <vuln:Remediations>
                    <vuln:Remediation Type="Vendor Fix">
                        <vuln:Description>5075999</vuln:Description>
                        <vuln:SubType>Security Update</vuln:SubType>
                    </vuln:Remediation>
                </vuln:Remediations>
            </vuln:Vulnerability>
            <vuln:Vulnerability Ordinal="3">
                <vuln:CVE>CVE-2026-99999</vuln:CVE>
                <vuln:Remediations>
                    <vuln:Remediation Type="Vendor Fix">
                        <vuln:Description>Install KB0000001</vuln:Description>
                        <vuln:SubType>Security Update</vuln:SubType>
                    </vuln:Remediation>
                </vuln:Remediations>
            </vuln:Vulnerability>
        </cvrf:cvrfdoc>
        """.strip()

        fake_session = _FakeSession([
                _FakeResponse(status=200, json_data=summary_payload, headers={"Content-Type": "application/json"}),
                _FakeResponse(status=200, text_data=cvrf_xml, headers={"Content-Type": "application/xml"}),
        ])
        client = _build_client(fake_session)

        cve_ids = await client.fetch_microsoft_cves_for_kb("KB5075999", update_id="2026-Feb")

        assert cve_ids == ["CVE-2026-21510", "CVE-2026-21513"]


def test_microsoft_vendor_metadata_hydrates_legacy_summary_fields():
    vendor_metadata = CVEVendorMetadata(
        source="microsoft",
        metadata={
            "ID": "2025-Jan",
            "Alias": "2025-Jan",
            "DocumentTitle": "January 2025 Security Updates",
            "CvrfUrl": "https://api.msrc.microsoft.com/cvrf/v3.0/cvrf/2025-Jan",
        },
    )

    assert vendor_metadata.update_id == "2025-Jan"
    assert vendor_metadata.advisory_id == "2025-Jan"
    assert vendor_metadata.document_title == "January 2025 Security Updates"
    assert vendor_metadata.cvrf_url == "https://api.msrc.microsoft.com/cvrf/v3.0/cvrf/2025-Jan"