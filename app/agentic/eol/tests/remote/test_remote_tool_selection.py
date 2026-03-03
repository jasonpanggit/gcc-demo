"""Remote tool-selection tests using the /api/azure-mcp/inspect-plan endpoint.

These tests exercise Route→Retrieve→Plan (stages 1-3) on a live Container App
instance WITHOUT executing any tools.  Results for every query are written to
``tool-selection-errors.md`` in the workspace root after the session, so that
failures can be reviewed and fixed in bulk.

Usage
-----
Run against the default Container App URL:

    pytest tests/test_remote_tool_selection.py -m remote -v

Or via the helper script:

    ./tests/run-tests.sh test_remote_tool_selection --remote

After the run, open ``tool-selection-errors.md`` to see the full report.

Environment variables
---------------------
    TEST_BASE_URL   Override the Container App URL (default: read from deploy/appsettings.json)
    TEST_TIMEOUT    Per-request timeout in seconds (default: 30)
"""
from __future__ import annotations

import json
import os
import pathlib
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import pytest

try:
    import httpx
    _HTTPX_AVAILABLE = True
except ImportError:
    _HTTPX_AVAILABLE = False


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

_APPSETTINGS_PATH = pathlib.Path(__file__).parent.parent / "deploy" / "appsettings.json"


def _url_from_appsettings() -> str:
    """Read the Container App URL from deploy/appsettings.json."""
    try:
        data = json.loads(_APPSETTINGS_PATH.read_text(encoding="utf-8"))
        url = data["Deployment"]["ContainerApp"]["Url"]
        return url.rstrip("/")
    except Exception:
        return "http://localhost:8000"


_BASE_URL: str = os.getenv("TEST_BASE_URL", _url_from_appsettings()).rstrip("/")
_INSPECT_URL: str = f"{_BASE_URL}/api/azure-mcp/inspect-plan"
_TIMEOUT: int = int(os.getenv("TEST_TIMEOUT", "30"))

# Report is written next to the test file so it's easy to find
_REPORT_PATH = pathlib.Path(__file__).parent / "tool-selection-errors.md"

# ---------------------------------------------------------------------------
# Shared result accumulator — filled by each test, written in session teardown
# ---------------------------------------------------------------------------
_RESULTS: List[Dict[str, Any]] = []


# ---------------------------------------------------------------------------
# Test cases
# Each entry: (test_id, query, check_type, expected)
#
# check_type values:
#   "plan_contains"      — expected tool name must appear in plan steps
#   "plan_not_contains"  — expected tool name must NOT appear in plan steps
#   "domain_contains"    — expected domain string must appear in domains list
#   "plan_any_prefix"    — at least one plan step starts with any of the
#                          pipe-separated prefixes in expected
#   "fast_path_true"     — plan must be a fast-path
#   "fast_path_false"    — plan must NOT be a fast-path
# ---------------------------------------------------------------------------
_TEST_CASES: List[Tuple[str, str, str, str]] = [
    # ── Azure resource listing ───────────────────────────────────────────────
    ("list_subscriptions",        "list my subscriptions",                    "plan_contains",     "subscription_list"),
    ("show_subscriptions",        "show all my Azure subscriptions",          "plan_contains",     "subscription_list"),
    ("list_resource_groups",      "list my resource groups",                  "plan_any_prefix",   "group_list|resource_group"),
    ("show_storage_accounts",     "show my storage accounts",                 "plan_contains",     "storage_account_list"),
    ("domain_azure_management",   "list my subscriptions",                    "domain_contains",   "azure_management"),

    # ── Virtual networks ─────────────────────────────────────────────────────
    ("list_vnets",                "list my virtual networks",                 "plan_contains",     "virtual_network_list"),
    ("show_vnets",                "show all VNets",                           "plan_contains",     "virtual_network_list"),
    ("vnets_not_test_conn",       "list my virtual networks",                 "plan_not_contains", "test_network_connectivity"),
    ("vnets_not_check_dns",       "show my virtual networks",                 "plan_not_contains", "check_dns_resolution"),
    ("vnet_domain",               "list my virtual networks",                 "domain_contains",   "network|azure_management"),
    ("list_nsgs",                 "list my network security groups",          "plan_contains",     "nsg_list"),
    ("nsgs_not_assess_posture",   "list my network security groups",          "plan_not_contains", "assess_network_security_posture"),
    ("list_private_endpoints",    "list my private endpoints",                "plan_contains",     "private_endpoint_list"),
    ("show_private_endpoints",    "show all private endpoints in my subscription", "plan_contains", "private_endpoint_list"),

    # ── NSG / routing detail tools ───────────────────────────────────────────
    ("inspect_nsg_rules",         "show rules for my NSG nsg-prod",           "plan_contains",     "inspect_nsg_rules"),
    ("nsg_rules_not_nsg_list",    "show rules for my NSG nsg-prod",           "plan_not_contains", "nsg_list"),
    ("effective_routes",          "show effective routes for my NIC",         "plan_any_prefix",   "get_effective_routes|effective_routes"),

    # ── Application Gateway / VPN / ExpressRoute ─────────────────────────────
    ("appgw_health",              "check Application Gateway health",         "plan_contains",     "inspect_appgw_waf"),
    ("waf_policy",                "show WAF policy for my App Gateway",       "plan_contains",     "inspect_appgw_waf"),
    ("vpn_gateway",               "check VPN gateway status",                 "plan_contains",     "inspect_vpn_expressroute"),
    ("expressroute",              "show ExpressRoute circuit state",           "plan_contains",     "inspect_vpn_expressroute"),

    # ── Network diagnostics (action tools — correct for action queries) ──────
    ("test_connectivity",         "test network connectivity from my VM to the database", "plan_any_prefix", "test_network|connectivity|azure_cli"),
    ("check_dns",                 "check DNS resolution for api.example.com", "plan_any_prefix",   "dns|check_dns|azure_cli"),

    # ── Advanced network capabilities ────────────────────────────────────────
    ("network_inventory",         "inventory my network resources",           "plan_contains",     "inventory_network_resources"),
    ("hub_spoke_validate",        "validate my hub-spoke topology",           "plan_contains",     "validate_hub_spoke_topology"),
    ("hub_spoke_health",          "is my hub-spoke topology healthy",         "plan_any_prefix",   "validate_hub_spoke|hub_spoke|hub"),
    ("connectivity_matrix",       "generate connectivity matrix for my subnets", "plan_any_prefix", "generate_connectivity|connectivity_matrix|connectivity"),
    ("route_path_analysis",       "analyze route path from my subnet to www.microsoft.com", "plan_any_prefix", "analyze_route|route_path|route"),
    ("nsg_flow_simulate",         "simulate NSG flow from my VM to port 443", "plan_any_prefix",   "simulate_nsg|nsg_flow|simulate"),
    ("private_coverage",          "analyze private endpoint coverage for zero-trust", "plan_any_prefix", "analyze_private|private_connect|private_endpoint"),
    ("dns_path",                  "trace DNS resolution path from vnet-prod for api.example.com", "plan_any_prefix", "analyze_dns|dns_resolution_path|dns"),
    ("security_posture",          "assess my network security posture",       "plan_contains",     "assess_network_security_posture"),
    ("posture_not_nsg_list",      "assess my network security posture",       "plan_not_contains", "nsg_list"),
    ("posture_not_fast_path",     "assess my network security posture",       "fast_path_false",   ""),

    # ── VNet / subnet list (regression: was routing to describe_capabilities) ─
    ("list_vnets_and_subnets",    "list my virtual networks and subnets",     "plan_contains",     "virtual_network_list"),
    ("vnets_subnets_not_describe","list my virtual networks and subnets",     "plan_not_contains", "describe_capabilities"),
    ("show_vnets_subnets",        "show my VNets and their subnets",          "plan_contains",     "virtual_network_list"),

    # ── inspect_vnet (detail / peering — different from list) ────────────────
    ("inspect_vnet_peering",      "show VNet peering status",                 "plan_contains",     "inspect_vnet"),
    ("inspect_vnet_address_space","show VNet address space and subnets",      "plan_contains",     "inspect_vnet"),
    ("inspect_vnet_not_list",     "show VNet peering status",                 "plan_not_contains", "virtual_network_list"),

    # ── Conflict inversions for new tools ────────────────────────────────────
    ("simulate_not_nsg_list",     "will traffic from my VM be allowed on port 443", "plan_not_contains", "nsg_list"),
    ("dns_path_not_check_dns",    "trace DNS resolution path from vnet-prod for api.example.com", "plan_not_contains", "check_dns_resolution"),
    ("private_cov_not_list_ep",   "which PaaS services are not using private endpoints", "plan_not_contains", "private_endpoint_list"),

    # ── Fast-path=false for blocked complex analysis tools ───────────────────
    ("connectivity_matrix_no_fp", "generate connectivity matrix for my subnets", "fast_path_false", ""),
    ("simulate_nsg_no_fp",        "simulate NSG flow from my VM to port 443", "fast_path_false",   ""),
    ("route_path_no_fp",          "analyze route path from my subnet to www.microsoft.com", "fast_path_false", ""),
    ("private_cov_no_fp",         "analyze private endpoint coverage for zero-trust", "fast_path_false", ""),
    ("dns_path_no_fp",            "trace DNS resolution path from vnet-prod for api.example.com", "fast_path_false", ""),

    # ── Alternative phrasings for new capabilities ───────────────────────────
    ("network_inventory_unused",  "find unused network resources",            "plan_contains",     "inventory_network_resources"),
    ("network_inventory_cost",    "network resource inventory for cost optimization", "plan_contains", "inventory_network_resources"),
    ("hub_spoke_alt",             "check hub-spoke architecture health",      "plan_any_prefix",   "validate_hub_spoke|hub_spoke"),
    ("expressroute_circuit",      "check ExpressRoute circuit health",        "plan_contains",     "inspect_vpn_expressroute"),
    ("appgw_alt",                 "inspect my Application Gateway WAF",       "plan_contains",     "inspect_appgw_waf"),
    ("security_posture_cis",      "run CIS Azure network compliance check",   "plan_contains",     "assess_network_security_posture"),
    ("security_posture_nist",     "check network compliance against NIST",    "plan_contains",     "assess_network_security_posture"),

    # ── Virtual machines ─────────────────────────────────────────────────────
    ("list_vms",                  "list my virtual machines",                 "plan_contains",     "virtual_machine_list"),
    ("show_vms",                  "show all VMs in my subscription",          "plan_contains",     "virtual_machine_list"),

    # ── OS EOL / inventory ───────────────────────────────────────────────────
    ("os_inventory",              "what OS are my VMs running",               "plan_any_prefix",   "os|inventory|eol|law"),
    ("eol_lookup",                "show end of life software on my servers",  "plan_any_prefix",   "eol|end_of_life|os_eol|law_get_software"),
    ("eol_domain",                "which of my VMs have end-of-life operating systems", "domain_contains", "arc_inventory"),

    # ── SRE / container health ───────────────────────────────────────────────
    ("container_health_domain",   "check health of my container apps",        "domain_contains",   "sre_health|sre_incident|observability"),
    ("container_error_domain",    "why is my container app returning 503 errors", "domain_contains", "sre_health|sre_incident|observability"),

    # ── Fast-path behaviour ──────────────────────────────────────────────────
    ("fast_path_simple",          "list my subscriptions",                    "fast_path_true",    ""),
    ("not_fast_path_complex",     "list my VMs then restart any that are stopped and show me the results", "fast_path_false", ""),

    # ── Retrieved-tool quality ───────────────────────────────────────────────
    # cli_in_retrieved: if the azure_cli MCP server is running its tool appears
    # in retrieved; if not, the plan should still contain a suitable network tool.
    ("cli_in_retrieved_vnets",    "list my virtual networks",                 "plan_any_prefix",   "virtual_network_list|azure_cli"),
    ("action_tools_filtered_vnets", "list my virtual networks",               "plan_no_prefix",    "test_|check_|create_|delete_|restart_"),
    ("action_tools_filtered_subs",  "list my subscriptions",                  "plan_no_prefix",    "test_|check_|create_|delete_|restart_"),
]


# ---------------------------------------------------------------------------
# HTTP fixture
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def http_client():
    if not _HTTPX_AVAILABLE:
        pytest.skip("httpx not installed — run: pip install httpx")
    with httpx.Client(timeout=_TIMEOUT) as client:
        yield client


# ---------------------------------------------------------------------------
# Report writer — runs after the full session
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session", autouse=True)
def write_report():
    """Yield during the session; write the markdown report on teardown."""
    yield
    _write_markdown_report()


def _write_markdown_report() -> None:
    if not _RESULTS:
        return

    passed = [r for r in _RESULTS if r["status"] == "PASS"]
    failed = [r for r in _RESULTS if r["status"] == "FAIL"]
    errored = [r for r in _RESULTS if r["status"] == "ERROR"]

    lines = [
        "# Tool Selection Test Report",
        "",
        f"**Generated:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        f"**Target:** {_BASE_URL}",
        f"**Total:** {len(_RESULTS)}  |  "
        f"✅ Pass: {len(passed)}  |  "
        f"❌ Fail: {len(failed)}  |  "
        f"⚠️ Error: {len(errored)}",
        "",
    ]

    # ── Failures first (most actionable) ─────────────────────────────────────
    if failed or errored:
        lines += [
            "## ❌ Failures / Errors",
            "",
            "| Test | Query | Check | Expected | Plan Tools | Domains | Fast? |",
            "|------|-------|-------|----------|------------|---------|-------|",
        ]
        for r in (failed + errored):
            lines.append(_row(r))
        lines.append("")

    # ── All results ───────────────────────────────────────────────────────────
    lines += [
        "## All Results",
        "",
        "| Status | Test | Query | Check | Expected | Plan Tools | Domains | Fast? |",
        "|--------|------|-------|-------|----------|------------|---------|-------|",
    ]
    for r in _RESULTS:
        icon = "✅" if r["status"] == "PASS" else ("⚠️" if r["status"] == "ERROR" else "❌")
        lines.append(f"| {icon} | " + _row(r))
    lines.append("")

    _REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n📋 Tool-selection report → {_REPORT_PATH}")


def _row(r: Dict[str, Any]) -> str:
    plan_tools = ", ".join(r.get("plan_tools", [])) or "—"
    domains = ", ".join(r.get("domains", [])) or "—"
    fast = "yes" if r.get("is_fast_path") else "no"
    expected = r.get("expected", "")
    check = r.get("check_type", "")
    return (
        f"{r['test_id']} | "
        f"`{r['query']}` | "
        f"{check} | "
        f"`{expected}` | "
        f"{plan_tools} | "
        f"{domains} | "
        f"{fast} |"
    )


# ---------------------------------------------------------------------------
# Core helpers
# ---------------------------------------------------------------------------

def _plan(http_client: "httpx.Client", message: str) -> Dict[str, Any]:
    resp = http_client.post(_INSPECT_URL, json={"message": message}, timeout=_TIMEOUT)
    assert resp.status_code == 200, (
        f"inspect-plan returned {resp.status_code} for {message!r}:\n{resp.text[:400]}"
    )
    body = resp.json()
    assert body.get("success") is True, f"success=False for {message!r}: {body}"
    data_list = body.get("data") or []
    assert data_list, f"Empty data for {message!r}"
    return data_list[0]


def _check(result: Dict[str, Any], check_type: str, expected: str) -> Tuple[bool, str]:
    """Return (passed, failure_reason)."""
    plan_tools = [s["tool_name"] for s in result.get("plan_steps", [])]
    retrieved_tools = result.get("retrieved_tools", [])
    domains = [d["domain"] for d in result.get("domains", [])]
    is_fast = result.get("is_fast_path", False)

    if check_type == "plan_contains":
        ok = expected in plan_tools
        return ok, f"Expected {expected!r} in plan {plan_tools}" if not ok else ""

    if check_type == "plan_not_contains":
        ok = expected not in plan_tools
        return ok, f"Tool {expected!r} should NOT be in plan but was. Plan: {plan_tools}" if not ok else ""

    if check_type == "domain_contains":
        prefixes = [p.strip() for p in expected.split("|")]
        ok = any(any(d.startswith(p) for p in prefixes) for d in domains)
        return ok, f"Expected domain matching {expected!r} in {domains}" if not ok else ""

    if check_type == "plan_any_prefix":
        prefixes = [p.strip() for p in expected.split("|")]
        ok = any(any(t.startswith(p) or p in t for p in prefixes) for t in plan_tools)
        return ok, f"Expected plan tool matching {expected!r}. Plan: {plan_tools}" if not ok else ""

    if check_type == "retrieved_contains":
        ok = expected in retrieved_tools
        return ok, f"Expected {expected!r} in retrieved_tools {retrieved_tools[:20]}" if not ok else ""

    if check_type == "plan_no_prefix":
        prefixes = [p.strip() for p in expected.split("|")]
        bad = [t for t in plan_tools if any(t.startswith(p) for p in prefixes)]
        ok = not bad
        return ok, f"Action tools {bad} must not appear in plan for list query. Plan: {plan_tools}" if not ok else ""

    if check_type == "fast_path_true":
        return is_fast, f"Expected fast_path=True, got {is_fast}. Plan: {plan_tools}"

    if check_type == "fast_path_false":
        return not is_fast, f"Expected fast_path=False, got {is_fast}. Plan: {plan_tools}"

    if check_type == "plan_contains_all":
        required = [t.strip() for t in expected.split("|")]
        missing = [t for t in required if t not in plan_tools]
        ok = not missing
        return ok, f"Expected ALL of {required} in plan, missing {missing}. Plan: {plan_tools}" if not ok else ""

    if check_type == "plan_step_count_gte":
        min_steps = int(expected)
        ok = len(plan_tools) >= min_steps
        return ok, f"Expected >= {min_steps} plan steps, got {len(plan_tools)}. Plan: {plan_tools}" if not ok else ""

    return False, f"Unknown check_type: {check_type!r}"


# ---------------------------------------------------------------------------
# Parametrized test
# ---------------------------------------------------------------------------

@pytest.mark.remote
@pytest.mark.parametrize(
    "test_id,query,check_type,expected",
    _TEST_CASES,
    ids=[c[0] for c in _TEST_CASES],
)
def test_tool_selection(
    http_client: "httpx.Client",
    test_id: str,
    query: str,
    check_type: str,
    expected: str,
) -> None:
    record: Dict[str, Any] = {
        "test_id": test_id,
        "query": query,
        "check_type": check_type,
        "expected": expected,
        "status": "ERROR",
        "plan_tools": [],
        "domains": [],
        "is_fast_path": None,
        "failure_reason": "",
    }

    print(f"\n{'─'*70}")
    print(f"[{test_id}] QUERY : {query!r}")
    print(f"         CHECK : {check_type} == {expected!r}")

    try:
        result = _plan(http_client, query)
        record["plan_tools"] = [s["tool_name"] for s in result.get("plan_steps", [])]
        record["domains"] = [d["domain"] for d in result.get("domains", [])]
        record["is_fast_path"] = result.get("is_fast_path")

        print(f"         DOMAINS    : {record['domains']}")
        print(f"         PLAN TOOLS : {record['plan_tools']}")
        print(f"         FAST PATH  : {record['is_fast_path']}")
        print(f"         RETRIEVED  : {result.get('retrieved_tools', [])[:10]}")
        print(f"         POOL SIZE  : {result.get('pool_size')}")

        passed, reason = _check(result, check_type, expected)
        record["status"] = "PASS" if passed else "FAIL"
        record["failure_reason"] = reason

        if passed:
            print(f"         RESULT     : ✅ PASS")
        else:
            print(f"         RESULT     : ❌ FAIL  — {reason}")
    except Exception as exc:
        record["status"] = "ERROR"
        record["failure_reason"] = str(exc)
        print(f"         RESULT     : ⚠️ ERROR — {exc}")
    finally:
        _RESULTS.append(record)

    assert record["status"] == "PASS", (
        f"[{test_id}] {record['failure_reason']}\n"
        f"  query: {query!r}\n"
        f"  plan_tools: {record['plan_tools']}\n"
        f"  domains: {record['domains']}\n"
        f"  is_fast_path: {record['is_fast_path']}"
    )


# ---------------------------------------------------------------------------
# Smoke — endpoint reachability (not parametrized, runs first)
# ---------------------------------------------------------------------------

@pytest.mark.remote
class TestInspectPlanEndpoint:
    def test_endpoint_is_reachable(self, http_client: "httpx.Client") -> None:
        resp = http_client.post(_INSPECT_URL, json={"message": "hello"}, timeout=_TIMEOUT)
        assert resp.status_code in (200, 503), (
            f"Unexpected status {resp.status_code}: {resp.text[:200]}"
        )

    def test_response_shape(self, http_client: "httpx.Client") -> None:
        result = _plan(http_client, "list my subscriptions")
        for key in ("domains", "retrieved_tools", "plan_steps", "is_fast_path"):
            assert key in result, f"Missing key {key!r} in response: {result}"

