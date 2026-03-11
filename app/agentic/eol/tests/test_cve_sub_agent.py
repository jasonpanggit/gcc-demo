"""Unit tests for CVE Sub-Agent.

Tests CVE vulnerability management workflows including search, scanning,
patch discovery, and remediation with safety checks.

These tests validate:
- CVE search by ID and keyword
- Infrastructure vulnerability scanning
- Patch discovery and mapping
- Remediation safety workflows (dry_run → confirm)
- Multi-VM batch remediation
- HTML formatting in responses
- Out-of-scope query handling
- No-fabrication enforcement
"""
import asyncio
import json
import pytest
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock, patch

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.cve_sub_agent import CVESubAgent, build_cve_meta_tool


# ─────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────

@pytest.fixture
def mock_tool_definitions():
    """Mock CVE tool definitions."""
    return [
        {
            "type": "function",
            "function": {
                "name": "search_cve",
                "description": "Search CVEs by ID, keyword, or filters",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "cve_id": {"type": "string"},
                        "keyword": {"type": "string"},
                        "severity": {"type": "string"},
                        "limit": {"type": "integer"},
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "scan_inventory",
                "description": "Trigger CVE scan on VM inventory",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "subscription_id": {"type": "string"},
                        "resource_group": {"type": "string"},
                        "vm_name": {"type": "string"},
                    },
                    "required": ["subscription_id"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_patches",
                "description": "Get patches that remediate a CVE",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "cve_id": {"type": "string"},
                        "subscription_ids": {"type": "array"},
                    },
                    "required": ["cve_id"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "trigger_remediation",
                "description": "Trigger patch installation to remediate a CVE",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "cve_id": {"type": "string"},
                        "vm_name": {"type": "string"},
                        "subscription_id": {"type": "string"},
                        "resource_group": {"type": "string"},
                        "dry_run": {"type": "boolean"},
                        "confirmed": {"type": "boolean"},
                    },
                    "required": ["cve_id", "vm_name", "subscription_id", "resource_group"],
                },
            },
        },
    ]


@pytest.fixture
def mock_tool_invoker():
    """Mock tool invoker that returns sample data."""
    async def invoker(tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        if tool_name == "search_cve":
            if arguments.get("cve_id") == "CVE-2024-1234":
                return {
                    "success": True,
                    "cves": [
                        {
                            "cve_id": "CVE-2024-1234",
                            "severity": "CRITICAL",
                            "cvss_score": 9.8,
                            "description": "Remote code execution vulnerability in Linux kernel",
                            "published": "2024-03-01",
                        }
                    ],
                    "total": 1,
                }
            elif arguments.get("keyword"):
                return {
                    "success": True,
                    "cves": [
                        {"cve_id": "CVE-2024-5678", "severity": "HIGH", "cvss_score": 7.5},
                        {"cve_id": "CVE-2024-9999", "severity": "MEDIUM", "cvss_score": 5.3},
                    ],
                    "total": 2,
                }
        elif tool_name == "scan_inventory":
            return {
                "success": True,
                "scan_id": "scan-abc-123",
                "status": "in_progress",
                "vm_count": 5,
                "cve_count": 12,
                "subscription_id": arguments.get("subscription_id"),
            }
        elif tool_name == "get_patches":
            return {
                "success": True,
                "patches": [
                    {
                        "kb_number": "KB5001234",
                        "package_name": "linux-image-5.15.0-92-generic",
                        "priority": "critical",
                        "reboot_required": True,
                    },
                    {
                        "kb_number": "KB5005678",
                        "package_name": "systemd",
                        "priority": "high",
                        "reboot_required": False,
                    },
                ],
                "affected_vms": ["vm-prod-01", "vm-prod-02"],
            }
        elif tool_name == "trigger_remediation":
            if arguments.get("dry_run"):
                return {
                    "success": True,
                    "dry_run": True,
                    "plan": {
                        "patches": ["KB5001234", "KB5005678"],
                        "reboot_required": True,
                        "estimated_duration": "15-20 minutes",
                    },
                }
            elif arguments.get("confirmed"):
                return {
                    "success": True,
                    "operation_url": "https://management.azure.com/subscriptions/sub-123/operations/op-456",
                    "status": "InProgress",
                }
        return {"success": False, "error": "Unknown tool or arguments"}

    return invoker


@pytest.fixture
def mock_event_callback():
    """Mock SSE event callback."""
    async def callback(event_type: str, content: str, **kwargs):
        pass
    return AsyncMock(side_effect=callback)


@pytest.fixture
def cve_agent(mock_tool_definitions, mock_tool_invoker, mock_event_callback):
    """Create CVE sub-agent instance."""
    return CVESubAgent(
        tool_definitions=mock_tool_definitions,
        tool_invoker=mock_tool_invoker,
        event_callback=mock_event_callback,
    )


# ─────────────────────────────────────────────────────────────
# Test Cases
# ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cve_search_by_id(cve_agent):
    """Test searching for a specific CVE by ID."""
    with patch.object(cve_agent, '_call_llm') as mock_llm:
        # Mock LLM to call search_cve tool, then respond with results
        mock_llm.side_effect = [
            {
                "message": {"role": "assistant", "content": "", "tool_calls": [
                    {"id": "call_1", "type": "function", "function": {
                        "name": "search_cve",
                        "arguments": json.dumps({"cve_id": "CVE-2024-1234"})
                    }}
                ]},
                "tool_calls": [
                    {"id": "call_1", "function": {"name": "search_cve", "arguments": json.dumps({"cve_id": "CVE-2024-1234"})}}
                ]
            },
            {
                "message": {"role": "assistant", "content": "<p>Found CVE-2024-1234 with CRITICAL severity (CVSS 9.8)</p>"},
                "tool_calls": []
            }
        ]

        result = await cve_agent.run("Tell me about CVE-2024-1234")

        assert result["success"] is True
        assert "CVE-2024-1234" in result["response"]
        assert result["tool_calls_made"] == 1


@pytest.mark.asyncio
async def test_cve_search_by_keyword(cve_agent):
    """Test searching CVEs by keyword."""
    with patch.object(cve_agent, '_call_llm') as mock_llm:
        mock_llm.side_effect = [
            {
                "message": {"role": "assistant", "content": "", "tool_calls": [
                    {"id": "call_1", "type": "function", "function": {
                        "name": "search_cve",
                        "arguments": json.dumps({"keyword": "linux kernel", "severity": "CRITICAL", "limit": 10})
                    }}
                ]},
                "tool_calls": [
                    {"id": "call_1", "function": {"name": "search_cve", "arguments": json.dumps({"keyword": "linux kernel"})}}
                ]
            },
            {
                "message": {"role": "assistant", "content": "<p>Found 2 CVEs matching 'linux kernel'</p>"},
                "tool_calls": []
            }
        ]

        result = await cve_agent.run("Find critical Linux kernel CVEs")

        assert result["success"] is True
        assert result["tool_calls_made"] == 1


@pytest.mark.asyncio
async def test_inventory_scan(cve_agent):
    """Test triggering infrastructure vulnerability scan."""
    with patch.object(cve_agent, '_call_llm') as mock_llm:
        mock_llm.side_effect = [
            {
                "message": {"role": "assistant", "content": "", "tool_calls": [
                    {"id": "call_1", "type": "function", "function": {
                        "name": "scan_inventory",
                        "arguments": json.dumps({"subscription_id": "sub-123"})
                    }}
                ]},
                "tool_calls": [
                    {"id": "call_1", "function": {"name": "scan_inventory", "arguments": json.dumps({"subscription_id": "sub-123"})}}
                ]
            },
            {
                "message": {"role": "assistant", "content": "<p>Scan started (ID: scan-abc-123). Found 12 CVEs across 5 VMs.</p>"},
                "tool_calls": []
            }
        ]

        result = await cve_agent.run("Scan my VMs for vulnerabilities in sub-123")

        assert result["success"] is True
        assert "scan-abc-123" in result["response"]
        assert result["tool_calls_made"] == 1


@pytest.mark.asyncio
async def test_patch_discovery(cve_agent):
    """Test discovering patches for a CVE."""
    with patch.object(cve_agent, '_call_llm') as mock_llm:
        mock_llm.side_effect = [
            {
                "message": {"role": "assistant", "content": "", "tool_calls": [
                    {"id": "call_1", "type": "function", "function": {
                        "name": "get_patches",
                        "arguments": json.dumps({"cve_id": "CVE-2024-1234"})
                    }}
                ]},
                "tool_calls": [
                    {"id": "call_1", "function": {"name": "get_patches", "arguments": json.dumps({"cve_id": "CVE-2024-1234"})}}
                ]
            },
            {
                "message": {"role": "assistant", "content": "<p>Found 2 patches: KB5001234, KB5005678</p>"},
                "tool_calls": []
            }
        ]

        result = await cve_agent.run("What patches fix CVE-2024-1234?")

        assert result["success"] is True
        assert "KB5001234" in result["response"]
        assert result["tool_calls_made"] == 1


@pytest.mark.asyncio
async def test_remediation_dry_run(cve_agent):
    """Test remediation dry run safety workflow."""
    with patch.object(cve_agent, '_call_llm') as mock_llm:
        mock_llm.side_effect = [
            {
                "message": {"role": "assistant", "content": "", "tool_calls": [
                    {"id": "call_1", "type": "function", "function": {
                        "name": "trigger_remediation",
                        "arguments": json.dumps({
                            "cve_id": "CVE-2024-1234",
                            "vm_name": "vm-prod-01",
                            "subscription_id": "sub-123",
                            "resource_group": "rg-prod",
                            "dry_run": True
                        })
                    }}
                ]},
                "tool_calls": [
                    {"id": "call_1", "function": {"name": "trigger_remediation", "arguments": json.dumps({"dry_run": True})}}
                ]
            },
            {
                "message": {"role": "assistant", "content": "<div class='alert alert-warning'>Reboot required. Proceed?</div>"},
                "tool_calls": []
            }
        ]

        result = await cve_agent.run("Plan remediation for CVE-2024-1234 on vm-prod-01")

        assert result["success"] is True
        assert "Reboot required" in result["response"] or "KB5001234" in result["response"]
        assert result["tool_calls_made"] == 1


@pytest.mark.asyncio
async def test_remediation_confirmed(cve_agent):
    """Test confirmed remediation execution after approval."""
    with patch.object(cve_agent, '_call_llm') as mock_llm:
        mock_llm.side_effect = [
            {
                "message": {"role": "assistant", "content": "", "tool_calls": [
                    {"id": "call_1", "type": "function", "function": {
                        "name": "trigger_remediation",
                        "arguments": json.dumps({
                            "cve_id": "CVE-2024-1234",
                            "vm_name": "vm-prod-01",
                            "subscription_id": "sub-123",
                            "resource_group": "rg-prod",
                            "confirmed": True
                        })
                    }}
                ]},
                "tool_calls": [
                    {"id": "call_1", "function": {"name": "trigger_remediation", "arguments": json.dumps({"confirmed": True})}}
                ]
            },
            {
                "message": {"role": "assistant", "content": "<p>Installation started. Monitor at operation URL.</p>"},
                "tool_calls": []
            }
        ]

        result = await cve_agent.run("Confirmed: install patches for CVE-2024-1234")

        assert result["success"] is True
        assert result["tool_calls_made"] == 1


@pytest.mark.asyncio
async def test_multi_vm_remediation(cve_agent):
    """Test batch remediation workflow across multiple VMs."""
    with patch.object(cve_agent, '_call_llm') as mock_llm:
        # Multi-step: scan → get_patches → remediate each VM
        mock_llm.side_effect = [
            # Step 1: Scan
            {
                "message": {"role": "assistant", "content": "", "tool_calls": [
                    {"id": "call_1", "type": "function", "function": {
                        "name": "scan_inventory",
                        "arguments": json.dumps({"subscription_id": "sub-123"})
                    }}
                ]},
                "tool_calls": [{"id": "call_1", "function": {"name": "scan_inventory", "arguments": "{}"}}]
            },
            # Step 2: Get patches
            {
                "message": {"role": "assistant", "content": "", "tool_calls": [
                    {"id": "call_2", "type": "function", "function": {
                        "name": "get_patches",
                        "arguments": json.dumps({"cve_id": "CVE-2024-1234"})
                    }}
                ]},
                "tool_calls": [{"id": "call_2", "function": {"name": "get_patches", "arguments": "{}"}}]
            },
            # Final response
            {
                "message": {"role": "assistant", "content": "<p>Found 2 affected VMs. Ready to remediate?</p>"},
                "tool_calls": []
            }
        ]

        result = await cve_agent.run("Fix CVE-2024-1234 on all affected VMs")

        assert result["success"] is True
        assert result["tool_calls_made"] == 2


@pytest.mark.asyncio
async def test_html_formatting(cve_agent):
    """Test that responses use HTML formatting, not markdown."""
    with patch.object(cve_agent, '_call_llm') as mock_llm:
        mock_llm.side_effect = [
            {
                "message": {"role": "assistant", "content": "", "tool_calls": [
                    {"id": "call_1", "type": "function", "function": {
                        "name": "search_cve",
                        "arguments": json.dumps({"cve_id": "CVE-2024-1234"})
                    }}
                ]},
                "tool_calls": [{"id": "call_1", "function": {"name": "search_cve", "arguments": "{}"}}]
            },
            {
                "message": {
                    "role": "assistant",
                    "content": "<p>Found <span class='badge badge-danger'>CRITICAL</span> CVE-2024-1234</p>"
                },
                "tool_calls": []
            }
        ]

        result = await cve_agent.run("Search CVE-2024-1234")

        assert result["success"] is True
        # Check for HTML, not markdown
        assert "<span" in result["response"] or "<p>" in result["response"] or "<div" in result["response"]
        assert "**" not in result["response"]  # No markdown bold
        assert "```" not in result["response"]  # No code fences


@pytest.mark.asyncio
async def test_out_of_scope_redirect(cve_agent):
    """Test graceful handling of out-of-scope queries."""
    with patch.object(cve_agent, '_call_llm') as mock_llm:
        mock_llm.side_effect = [
            {
                "message": {
                    "role": "assistant",
                    "content": "<p>I'm focused on CVE vulnerability management. For general VM inventory, please ask in the main conversation.</p>"
                },
                "tool_calls": []
            }
        ]

        result = await cve_agent.run("List all my VMs")

        assert result["success"] is True
        assert "focused on CVE" in result["response"] or "vulnerability management" in result["response"]
        assert result["tool_calls_made"] == 0  # No tools called for out-of-scope


@pytest.mark.asyncio
async def test_no_fabrication_enforcement(cve_agent):
    """Test that agent calls tools before presenting data (no fabrication)."""
    with patch.object(cve_agent, '_call_llm') as mock_llm:
        # LLM should call search_cve BEFORE presenting CVE details
        mock_llm.side_effect = [
            {
                "message": {"role": "assistant", "content": "", "tool_calls": [
                    {"id": "call_1", "type": "function", "function": {
                        "name": "search_cve",
                        "arguments": json.dumps({"cve_id": "CVE-2024-1234"})
                    }}
                ]},
                "tool_calls": [{"id": "call_1", "function": {"name": "search_cve", "arguments": "{}"}}]
            },
            {
                "message": {"role": "assistant", "content": "<p>CVE-2024-1234 is CRITICAL (9.8)</p>"},
                "tool_calls": []
            }
        ]

        result = await cve_agent.run("Tell me about CVE-2024-1234")

        # Verify tool was called first
        assert result["tool_calls_made"] >= 1
        assert result["success"] is True


# ─────────────────────────────────────────────────────────────
# Meta-tool Tests
# ─────────────────────────────────────────────────────────────

def test_build_cve_meta_tool():
    """Test meta-tool definition generation."""
    meta_tool = build_cve_meta_tool()

    assert meta_tool["type"] == "function"
    assert meta_tool["function"]["name"] == "cve_agent"
    assert "CVE" in meta_tool["function"]["description"]
    assert "request" in meta_tool["function"]["parameters"]["properties"]
    assert "subscription_id" in meta_tool["function"]["parameters"]["properties"]
    assert "request" in meta_tool["function"]["parameters"]["required"]


# ─────────────────────────────────────────────────────────────
# Agent Metadata Tests
# ─────────────────────────────────────────────────────────────

def test_agent_metadata(cve_agent):
    """Test agent metadata and capabilities."""
    assert cve_agent._DOMAIN_NAME == "cve"
    assert cve_agent._MAX_ITERATIONS == 15
    assert cve_agent._TIMEOUT_SECONDS == 45.0

    domains = cve_agent.get_supported_domains()
    assert "cve" in domains
    assert "vulnerability" in domains
    assert "security" in domains

    capabilities = cve_agent.get_capabilities()
    assert len(capabilities) >= 4
    assert any("search" in cap.name.lower() for cap in capabilities)
    assert any("scan" in cap.name.lower() for cap in capabilities)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
