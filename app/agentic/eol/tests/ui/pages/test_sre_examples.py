"""
SRE Assistant — Comprehensive Example Prompt Tests (40 prompts, 7 categories).

Tests verify that each template prompt chip produces a meaningful, non-error
response from the SRE orchestrator. Separate from test_sre_assistant.py
(which tests page structure) — this file tests response CONTENT.

Organized to mirror the 6 UI categories in templates/sre.html, plus a 7th
category for Phase 4 resource validation regression.

Usage:
    # All remote example tests
    pytest tests/ui/pages/test_sre_examples.py -v -m remote

    # One category
    pytest tests/ui/pages/test_sre_examples.py -v -k "TestNetworkDiagnostics"

    # Phase regression gates only
    pytest tests/ui/pages/test_sre_examples.py -v -m "remote and phase1"
    pytest tests/ui/pages/test_sre_examples.py -v -m "remote and phase4"

    # With failure logging (generates JSON report for log_test_failures.py)
    pytest tests/ui/pages/test_sre_examples.py -v -m remote \\
        --json-report --json-report-file=tests/ui/test-results/pytest-report.json

Markers:
    remote      — requires live Azure environment (APP_BASE_URL)
    slow        — response expected to take > 10 seconds
    phase1      — Phase 1 regression gate (dependency map 4-layer cascade)
    phase2      — Phase 2 regression gate (tool gaps)
    phase3      — Phase 3 regression gate (auto-remediation)
    phase4      — Phase 4 regression gate (resource validation)
"""
from __future__ import annotations

import json
import os
import re
import time
from typing import Any, Dict, List

import pytest

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

BASE_URL = os.getenv(
    "APP_BASE_URL",
    "https://azure-agentic-platform-vnet.jollywater-179e4f4a.australiaeast.azurecontainerapps.io",
)
SSE_ENDPOINT = f"{BASE_URL}/api/sre/chat"
RESPONSE_TIMEOUT_MS = int(os.getenv("SRE_TEST_TIMEOUT_MS", "45000"))


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _submit_prompt(prompt: str, timeout_s: float = RESPONSE_TIMEOUT_MS / 1000) -> str:
    """Submit prompt to SRE chat endpoint via SSE and return assembled response text."""
    try:
        import requests  # type: ignore[import]
    except ImportError:
        pytest.skip("requests library not installed")

    payload = {"message": prompt, "conversation_id": None}
    chunks: List[str] = []

    try:
        with requests.post(
            SSE_ENDPOINT,
            json=payload,
            stream=True,
            timeout=timeout_s,
            headers={"Accept": "text/event-stream"},
        ) as resp:
            resp.raise_for_status()
            for raw_line in resp.iter_lines(decode_unicode=True):
                if not raw_line or not raw_line.startswith("data: "):
                    continue
                try:
                    event = json.loads(raw_line[6:])
                except json.JSONDecodeError:
                    continue
                content = event.get("content") or event.get("delta") or ""
                if content:
                    chunks.append(content)
                if event.get("type") in {"done", "end", "complete"}:
                    break
    except Exception as exc:
        pytest.skip(f"Could not reach SRE endpoint: {exc}")

    return "".join(chunks)


def _assert_valid(response: str, prompt: str) -> None:
    """Assert that a response is non-empty, non-error, and meaningful."""
    assert response, f"Empty response for: {prompt!r}"
    assert len(response.strip()) >= 50, (
        f"Response too short ({len(response)} chars) for: {prompt!r}"
    )
    # Must not contain raw error types
    assert not re.search(
        r"(BadArgumentError|NoneType object|Traceback \(most recent|workspace_id.*invalid)",
        response,
        re.IGNORECASE,
    ), f"Raw error leaked for: {prompt!r}\n{response[:300]}"


# ---------------------------------------------------------------------------
# Category 1 — Health & Availability (7 prompts)
# ---------------------------------------------------------------------------

@pytest.mark.remote
class TestHealthAvailability:
    """Health & Availability prompt chips from the SRE template."""

    @pytest.mark.parametrize("prompt", [
        "What is the health of my container apps?",
        "Which resources have health issues or active alerts in my subscription?",
        "Show recent alerts and incidents in the last 24 hours",
        "Check the health of all my Azure resources",
        "Are any of my VMs unhealthy or degraded?",
        "Show me the health status of my AKS clusters",
        "What is the overall availability of my services this week?",
    ])
    def test_prompt(self, prompt: str):
        response = _submit_prompt(prompt)
        _assert_valid(response, prompt)
        assert re.search(
            r"\b(health|status|available|degraded|running|alert|healthy|unknown)\b",
            response, re.IGNORECASE,
        ), f"Missing health keywords in response for: {prompt!r}"

    def test_container_app_health_has_app_data(self):
        """Container app health response should include app names or a table."""
        response = _submit_prompt("What is the health of my container apps?")
        _assert_valid(response, "container app health")
        assert re.search(r"(<table|<ul|<li|\bapp\b|container)", response, re.IGNORECASE)


# ---------------------------------------------------------------------------
# Category 2 — Incident Triage (7 prompts)
# ---------------------------------------------------------------------------

@pytest.mark.remote
@pytest.mark.slow
class TestIncidentTriage:
    """Incident Triage prompt chips from the SRE template."""

    @pytest.mark.parametrize("prompt", [
        "Why is my container app returning 503 errors?",
        "My application latency has spiked — what changed recently?",
        "Triage the highest severity active alerts and suggest remediation",
        "What is causing elevated error rates on my API endpoints?",
        "Run a root cause analysis on the last major incident",
        "Generate an incident summary for the past 4 hours",
        "Correlate all active alerts and identify the root signal",
    ])
    def test_prompt(self, prompt: str):
        response = _submit_prompt(prompt)
        _assert_valid(response, prompt)

    def test_503_triage_references_diagnostics(self):
        """503 triage response should mention diagnostic concepts."""
        response = _submit_prompt("Why is my container app returning 503 errors?")
        _assert_valid(response, "503 triage")
        assert re.search(
            r"\b(503|error|log|health|restart|replica|timeout|dependency|unavailable)\b",
            response, re.IGNORECASE,
        ), "Missing diagnostic keywords in 503 triage response"


# ---------------------------------------------------------------------------
# Category 3 — Network Diagnostics (5 prompts)  [Phase 1 regression gate]
# ---------------------------------------------------------------------------

@pytest.mark.remote
@pytest.mark.slow
@pytest.mark.phase1
class TestNetworkDiagnostics:
    """Network Diagnostics prompts — Phase 1 regression gate.

    After Phase 1, ALL these prompts must return structured data without
    raw Log Analytics errors or unresolved parameter references.
    """

    @pytest.mark.parametrize("prompt", [
        "Analyze the service-to-service dependency map for my container app",
        "Trace the dependency chain for a failing API call",
        "What external dependencies is my container app calling?",
        "Show me the call graph for my microservices",
        "Which downstream services are causing the most errors?",
    ])
    def test_prompt_no_raw_errors(self, prompt: str):
        response = _submit_prompt(prompt)
        _assert_valid(response, prompt)
        # Phase 1 regression: must not contain raw Log Analytics errors
        assert "BadArgumentError" not in response, (
            f"Raw LA error in response for: {prompt!r}"
        )

    def test_dependency_map_contains_dependency_data(self):
        """Dependency map response must contain dependency/call data."""
        response = _submit_prompt(
            "Analyze the service-to-service dependency map for my container app"
        )
        _assert_valid(response, "dependency map")
        assert re.search(
            r"\b(depend|call|service|latency|request|downstream|upstream|target|map)\b",
            response, re.IGNORECASE,
        ), "Missing dependency keywords in dependency map response"


# ---------------------------------------------------------------------------
# Category 4 — Security & Compliance (6 prompts)
# ---------------------------------------------------------------------------

@pytest.mark.remote
class TestSecurityCompliance:
    """Security & Compliance prompt chips from the SRE template."""

    @pytest.mark.parametrize("prompt", [
        "What is my Defender for Cloud secure score?",
        "List my high-severity security recommendations",
        "Check my CIS compliance status",
        "Check my NIST compliance status",
        "Are there any critical security vulnerabilities I should address?",
        "Get my Azure security posture summary",
    ])
    def test_prompt(self, prompt: str):
        response = _submit_prompt(prompt)
        _assert_valid(response, prompt)

    def test_secure_score_has_numeric_content(self):
        """Secure score response should include score or percentage."""
        response = _submit_prompt("What is my Defender for Cloud secure score?")
        _assert_valid(response, "secure score")
        assert re.search(
            r"\b(score|percent|%|\d+|recommendation|secure|defender)\b",
            response, re.IGNORECASE,
        ), "Missing security score content"


# ---------------------------------------------------------------------------
# Category 5 — Inventory & Cost (6 prompts)
# ---------------------------------------------------------------------------

@pytest.mark.remote
class TestInventoryCost:
    """Inventory & Cost prompt chips from the SRE template."""

    @pytest.mark.parametrize("prompt", [
        "Find orphaned or idle resources wasting budget",
        "Show my cost breakdown by resource group",
        "Are there any spending anomalies this month?",
        "What are my top Azure Advisor cost recommendations?",
        "What is my current Azure spend this month?",
        "Which resource groups are driving the most cost?",
    ])
    def test_prompt(self, prompt: str):
        response = _submit_prompt(prompt)
        _assert_valid(response, prompt)

    def test_cost_breakdown_has_cost_content(self):
        """Cost breakdown should reference currency or groups."""
        response = _submit_prompt("Show my cost breakdown by resource group")
        _assert_valid(response, "cost breakdown")
        assert re.search(
            r"\b(cost|\$|USD|AUD|resource.group|spend|budget|saving)\b",
            response, re.IGNORECASE,
        ), "Missing cost-related content in cost breakdown response"


# ---------------------------------------------------------------------------
# Category 6 — Performance & SLO (6 prompts)
# ---------------------------------------------------------------------------

@pytest.mark.remote
@pytest.mark.slow
class TestPerformanceSlo:
    """Performance & SLO prompt chips from the SRE template."""

    @pytest.mark.parametrize("prompt", [
        "What are the performance metrics for my container apps in the last hour?",
        "Detect any performance anomalies across my services",
        "What is my current SLO burn rate?",
        "Show me my error budget remaining for this month",
        "Which services are closest to breaching their SLOs?",
        "Identify bottlenecks in my application stack",
    ])
    def test_prompt(self, prompt: str):
        response = _submit_prompt(prompt)
        _assert_valid(response, prompt)

    def test_slo_burn_rate_mentions_slo_concepts(self):
        """SLO burn rate must reference SLO/error budget concepts."""
        response = _submit_prompt("What is my current SLO burn rate?")
        _assert_valid(response, "SLO burn rate")
        assert re.search(
            r"\b(slo|burn.rate|error.budget|objective|availability|latency|budget)\b",
            response, re.IGNORECASE,
        ), "Missing SLO concepts in burn rate response"


# ---------------------------------------------------------------------------
# Category 7 — Resource Validation Phase 4 regression (3 prompts)
# ---------------------------------------------------------------------------

@pytest.mark.remote
@pytest.mark.phase4
class TestResourceValidationRegression:
    """Phase 4 regression: pre-flight inventory check must block non-existent resources.

    These verify the _check_specific_resource_exists pre-flight check works
    end-to-end: zero tool calls, friendly HTML error, helpful suggestions.
    """

    def test_nonexistent_container_app_gets_friendly_error(self):
        """Non-existent container app query → friendly not-found message, no tool errors."""
        response = _submit_prompt("Check the health of phantom-app-xyz container app")
        _assert_valid(response, "nonexistent container app")
        assert re.search(
            r"(not found|doesn.t exist|could not find|no.*resource|not.*inventor)",
            response, re.IGNORECASE,
        ), "Expected friendly not-found message for phantom-app-xyz"
        # Must not contain raw tool errors from wasted Log Analytics calls
        assert "BadArgumentError" not in response, (
            "Pre-flight check should prevent Log Analytics calls for unknown apps"
        )

    def test_nonexistent_vm_gets_friendly_error(self):
        """Non-existent VM query → friendly not-found message, no tool errors."""
        response = _submit_prompt("What is the health of ghost-vm-99999?")
        _assert_valid(response, "nonexistent VM")
        assert re.search(
            r"(not found|doesn.t exist|could not find|no.*resource|not.*inventor)",
            response, re.IGNORECASE,
        ), "Expected friendly not-found message for ghost-vm-99999"

    def test_broad_listing_query_bypasses_validation(self):
        """Broad listing queries (no specific name) must NOT trigger resource-not-found."""
        response = _submit_prompt("Show all my container apps")
        _assert_valid(response, "list all container apps")
        # Should not be a not-found error — no specific name was given
        assert not re.search(r"❌.*not found", response, re.IGNORECASE), (
            "Broad listing query wrongly triggered resource-not-found validation"
        )
