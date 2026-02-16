#!/usr/bin/env python3
"""Test script for SRE Orchestrator API endpoints.

Tests all REST API endpoints for the SRE orchestrator.
"""
import requests
import json
import sys

# Base URL (modify for your environment)
BASE_URL = "http://localhost:8000"

def test_health():
    """Test health check endpoint."""
    print("\n" + "=" * 60)
    print("TEST: Health Check")
    print("=" * 60)

    try:
        response = requests.get(f"{BASE_URL}/api/sre-orchestrator/health")
        response.raise_for_status()

        data = response.json()
        print(f"✓ Status code: {response.status_code}")
        print(f"✓ Health status: {data['data']['status']}")
        print(f"✓ Total agents: {data['data']['registry']['total_agents']}")
        print(f"✓ Total tools: {data['data']['registry']['total_tools']}")

        return True
    except Exception as exc:
        print(f"❌ Health check failed: {exc}")
        return False


def test_capabilities():
    """Test capabilities endpoint."""
    print("\n" + "=" * 60)
    print("TEST: Get Capabilities")
    print("=" * 60)

    try:
        response = requests.get(f"{BASE_URL}/api/sre-orchestrator/capabilities")
        response.raise_for_status()

        data = response.json()
        print(f"✓ Status code: {response.status_code}")
        print(f"✓ Orchestrator version: {data['data']['orchestrator_version']}")
        print(f"✓ Total tools: {data['data']['total_tools']}")
        print(f"✓ Total agents: {data['data']['total_agents']}")
        print(f"✓ Categories: {', '.join(data['data']['categories'])}")

        return True
    except Exception as exc:
        print(f"❌ Capabilities test failed: {exc}")
        return False


def test_list_tools():
    """Test list tools endpoint."""
    print("\n" + "=" * 60)
    print("TEST: List Tools")
    print("=" * 60)

    try:
        response = requests.get(f"{BASE_URL}/api/sre-orchestrator/tools")
        response.raise_for_status()

        data = response.json()
        print(f"✓ Status code: {response.status_code}")
        print(f"✓ Total tools: {data['data']['total']}")
        print(f"✓ Sample tools:")
        for tool in data['data']['tools'][:5]:
            print(f"  - {tool['name']} ({tool['agent_type']})")

        return True
    except Exception as exc:
        print(f"❌ List tools test failed: {exc}")
        return False


def test_list_tools_filtered():
    """Test list tools with category filter."""
    print("\n" + "=" * 60)
    print("TEST: List Tools (Filtered)")
    print("=" * 60)

    try:
        response = requests.get(
            f"{BASE_URL}/api/sre-orchestrator/tools",
            params={"category": "health"}
        )
        response.raise_for_status()

        data = response.json()
        print(f"✓ Status code: {response.status_code}")
        print(f"✓ Health tools: {data['data']['total']}")
        for tool in data['data']['tools'][:3]:
            print(f"  - {tool['name']}")

        return True
    except Exception as exc:
        print(f"❌ Filtered tools test failed: {exc}")
        return False


def test_get_tool_details():
    """Test get specific tool details."""
    print("\n" + "=" * 60)
    print("TEST: Get Tool Details")
    print("=" * 60)

    try:
        response = requests.get(
            f"{BASE_URL}/api/sre-orchestrator/tools/describe_capabilities"
        )
        response.raise_for_status()

        data = response.json()
        print(f"✓ Status code: {response.status_code}")
        print(f"✓ Tool name: {data['data']['name']}")
        print(f"✓ Agent ID: {data['data']['agent_id']}")

        return True
    except Exception as exc:
        print(f"❌ Tool details test failed: {exc}")
        return False


def test_list_agents():
    """Test list agents endpoint."""
    print("\n" + "=" * 60)
    print("TEST: List Agents")
    print("=" * 60)

    try:
        response = requests.get(f"{BASE_URL}/api/sre-orchestrator/agents")
        response.raise_for_status()

        data = response.json()
        print(f"✓ Status code: {response.status_code}")
        print(f"✓ Total agents: {data['data']['total']}")
        for agent in data['data']['agents']:
            print(f"  - {agent['agent_id']} ({agent['agent_type']}) - {agent['status']}")

        return True
    except Exception as exc:
        print(f"❌ List agents test failed: {exc}")
        return False


def test_list_categories():
    """Test list categories endpoint."""
    print("\n" + "=" * 60)
    print("TEST: List Categories")
    print("=" * 60)

    try:
        response = requests.get(f"{BASE_URL}/api/sre-orchestrator/categories")
        response.raise_for_status()

        data = response.json()
        print(f"✓ Status code: {response.status_code}")
        print(f"✓ Total categories: {data['data']['total_categories']}")
        print(f"✓ Categories with counts:")
        for category, count in data['data']['counts'].items():
            print(f"  - {category}: {count} tools")

        return True
    except Exception as exc:
        print(f"❌ List categories test failed: {exc}")
        return False


def test_execute_query():
    """Test execute SRE query endpoint."""
    print("\n" + "=" * 60)
    print("TEST: Execute SRE Query")
    print("=" * 60)

    try:
        payload = {
            "query": "Check health of container apps",
            "context": {}
        }

        response = requests.post(
            f"{BASE_URL}/api/sre-orchestrator/execute",
            json=payload
        )
        response.raise_for_status()

        data = response.json()
        print(f"✓ Status code: {response.status_code}")
        print(f"✓ Success: {data['success']}")
        print(f"✓ Message: {data['message']}")

        return True
    except Exception as exc:
        print(f"❌ Execute query test failed: {exc}")
        return False


def test_incident_triage():
    """Test incident response endpoint."""
    print("\n" + "=" * 60)
    print("TEST: Incident Triage")
    print("=" * 60)

    try:
        payload = {
            "incident_id": "INC-TEST-001",
            "action": "triage",
            "description": "API gateway errors",
            "severity": "high"
        }

        response = requests.post(
            f"{BASE_URL}/api/sre-orchestrator/incident",
            json=payload
        )
        response.raise_for_status()

        data = response.json()
        print(f"✓ Status code: {response.status_code}")
        print(f"✓ Success: {data['success']}")
        print(f"✓ Message: {data['message']}")

        return True
    except Exception as exc:
        print(f"❌ Incident triage test failed: {exc}")
        return False


def test_metrics():
    """Test metrics endpoint."""
    print("\n" + "=" * 60)
    print("TEST: Get Metrics")
    print("=" * 60)

    try:
        response = requests.get(f"{BASE_URL}/api/sre-orchestrator/metrics")
        response.raise_for_status()

        data = response.json()
        print(f"✓ Status code: {response.status_code}")
        print(f"✓ Agent ID: {data['data']['agent_id']}")
        print(f"✓ Requests handled: {data['data']['requests_handled']}")
        print(f"✓ Success rate: {data['data']['success_rate']:.2%}")

        return True
    except Exception as exc:
        print(f"❌ Metrics test failed: {exc}")
        return False


def main():
    """Run all API tests."""
    print("=" * 60)
    print("SRE Orchestrator API Test Suite")
    print("=" * 60)
    print(f"Base URL: {BASE_URL}")

    results = []

    # Basic endpoints
    results.append(("Health Check", test_health()))
    results.append(("Capabilities", test_capabilities()))
    results.append(("List Tools", test_list_tools()))
    results.append(("List Tools (Filtered)", test_list_tools_filtered()))
    results.append(("Get Tool Details", test_get_tool_details()))
    results.append(("List Agents", test_list_agents()))
    results.append(("List Categories", test_list_categories()))

    # Execution endpoints
    results.append(("Execute Query", test_execute_query()))
    results.append(("Incident Triage", test_incident_triage()))
    results.append(("Get Metrics", test_metrics()))

    # Summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {name}")

    print(f"\nTotal: {passed}/{total} tests passed")

    if passed == total:
        print("\n✅ All API tests passed!")
        print("\nThe SRE Orchestrator API is fully operational!")
        print("\nAvailable endpoints:")
        print(f"  - GET  {BASE_URL}/api/sre-orchestrator/health")
        print(f"  - GET  {BASE_URL}/api/sre-orchestrator/capabilities")
        print(f"  - GET  {BASE_URL}/api/sre-orchestrator/tools")
        print(f"  - GET  {BASE_URL}/api/sre-orchestrator/tools/{{tool_name}}")
        print(f"  - GET  {BASE_URL}/api/sre-orchestrator/agents")
        print(f"  - GET  {BASE_URL}/api/sre-orchestrator/categories")
        print(f"  - GET  {BASE_URL}/api/sre-orchestrator/metrics")
        print(f"  - POST {BASE_URL}/api/sre-orchestrator/execute")
        print(f"  - POST {BASE_URL}/api/sre-orchestrator/incident")
        sys.exit(0)
    else:
        print("\n❌ Some tests failed")
        print("\nMake sure the FastAPI server is running:")
        print("  cd app/agentic/eol")
        print("  uvicorn main:app --reload --port 8000")
        sys.exit(1)


if __name__ == "__main__":
    main()
