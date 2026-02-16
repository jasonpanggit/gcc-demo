#!/bin/bash
# SRE Orchestrator API - cURL Examples
#
# This script provides example cURL commands for testing the SRE Orchestrator API endpoints.
# Make sure the FastAPI server is running: uvicorn main:app --reload --port 8000

BASE_URL="http://localhost:8000"

echo "=========================================="
echo "SRE Orchestrator API - cURL Examples"
echo "=========================================="
echo ""

# 1. Health Check
echo "1. Health Check"
echo "GET $BASE_URL/api/sre-orchestrator/health"
echo ""
curl -s "$BASE_URL/api/sre-orchestrator/health" | jq '.'
echo ""
read -p "Press Enter to continue..."
echo ""

# 2. Get Capabilities
echo "2. Get Capabilities"
echo "GET $BASE_URL/api/sre-orchestrator/capabilities"
echo ""
curl -s "$BASE_URL/api/sre-orchestrator/capabilities" | jq '.data | {version:.orchestrator_version, tools:.total_tools, agents:.total_agents, categories}'
echo ""
read -p "Press Enter to continue..."
echo ""

# 3. List All Tools
echo "3. List All Tools"
echo "GET $BASE_URL/api/sre-orchestrator/tools"
echo ""
curl -s "$BASE_URL/api/sre-orchestrator/tools" | jq '.data | {total, sample_tools: .tools[:3]}'
echo ""
read -p "Press Enter to continue..."
echo ""

# 4. List Tools by Category
echo "4. List Tools by Category (health)"
echo "GET $BASE_URL/api/sre-orchestrator/tools?category=health"
echo ""
curl -s "$BASE_URL/api/sre-orchestrator/tools?category=health" | jq '.data | {total, tools: .tools[].name}'
echo ""
read -p "Press Enter to continue..."
echo ""

# 5. Get Specific Tool Details
echo "5. Get Tool Details"
echo "GET $BASE_URL/api/sre-orchestrator/tools/describe_capabilities"
echo ""
curl -s "$BASE_URL/api/sre-orchestrator/tools/describe_capabilities" | jq '.data | {name, agent_id, agent_type}'
echo ""
read -p "Press Enter to continue..."
echo ""

# 6. List All Agents
echo "6. List All Agents"
echo "GET $BASE_URL/api/sre-orchestrator/agents"
echo ""
curl -s "$BASE_URL/api/sre-orchestrator/agents" | jq '.data | {total, agents: .agents[] | {agent_id, agent_type, status}}'
echo ""
read -p "Press Enter to continue..."
echo ""

# 7. List Categories
echo "7. List Categories"
echo "GET $BASE_URL/api/sre-orchestrator/categories"
echo ""
curl -s "$BASE_URL/api/sre-orchestrator/categories" | jq '.data | {total_categories, counts}'
echo ""
read -p "Press Enter to continue..."
echo ""

# 8. Execute SRE Query - Health Check
echo "8. Execute SRE Query - Health Check"
echo "POST $BASE_URL/api/sre-orchestrator/execute"
echo 'Body: {"query": "Check health of container apps"}'
echo ""
curl -s -X POST "$BASE_URL/api/sre-orchestrator/execute" \
  -H "Content-Type: application/json" \
  -d '{"query": "Check health of container apps"}' | jq '.'
echo ""
read -p "Press Enter to continue..."
echo ""

# 9. Execute SRE Query - Cost Optimization
echo "9. Execute SRE Query - Cost Optimization"
echo "POST $BASE_URL/api/sre-orchestrator/execute"
echo 'Body: {"query": "Find orphaned resources and estimate savings"}'
echo ""
curl -s -X POST "$BASE_URL/api/sre-orchestrator/execute" \
  -H "Content-Type: application/json" \
  -d '{"query": "Find orphaned resources and estimate savings"}' | jq '.'
echo ""
read -p "Press Enter to continue..."
echo ""

# 10. Execute SRE Query - Performance Analysis
echo "10. Execute SRE Query - Performance Analysis"
echo "POST $BASE_URL/api/sre-orchestrator/execute"
echo 'Body: {"query": "Show me performance metrics for the API"}'
echo ""
curl -s -X POST "$BASE_URL/api/sre-orchestrator/execute" \
  -H "Content-Type: application/json" \
  -d '{"query": "Show me performance metrics for the API"}' | jq '.'
echo ""
read -p "Press Enter to continue..."
echo ""

# 11. Incident Response - Triage
echo "11. Incident Response - Triage"
echo "POST $BASE_URL/api/sre-orchestrator/incident"
echo 'Body: {"incident_id": "INC-001", "action": "triage", "description": "API gateway errors", "severity": "high"}'
echo ""
curl -s -X POST "$BASE_URL/api/sre-orchestrator/incident" \
  -H "Content-Type: application/json" \
  -d '{
    "incident_id": "INC-001",
    "action": "triage",
    "description": "API gateway returning 500 errors",
    "severity": "high"
  }' | jq '.'
echo ""
read -p "Press Enter to continue..."
echo ""

# 12. Get Orchestrator Metrics
echo "12. Get Orchestrator Metrics"
echo "GET $BASE_URL/api/sre-orchestrator/metrics"
echo ""
curl -s "$BASE_URL/api/sre-orchestrator/metrics" | jq '.data | {agent_id, agent_type, requests_handled, success_rate}'
echo ""

echo ""
echo "=========================================="
echo "All examples completed!"
echo "=========================================="
echo ""
echo "API Documentation: $BASE_URL/docs"
echo ""
