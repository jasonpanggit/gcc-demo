#!/bin/bash
# Quick verification script for SRE cost/diagnostic workflows

echo "=========================================="
echo "SRE Cost & Diagnostic Workflow Verification"
echo "=========================================="
echo ""

# Check if the file was modified
echo "1. Checking file modifications..."
if git diff main --stat app/agentic/eol/agents/sre_orchestrator.py | grep -q "sre_orchestrator.py"; then
    echo "   ✅ sre_orchestrator.py modified"
    git diff main --stat app/agentic/eol/agents/sre_orchestrator.py
else
    echo "   ❌ File not modified"
fi
echo ""

# Check for new methods
echo "2. Checking new detection methods..."
if grep -q "_is_cost_analysis_query" app/agentic/eol/agents/sre_orchestrator.py; then
    echo "   ✅ _is_cost_analysis_query() found"
else
    echo "   ❌ _is_cost_analysis_query() not found"
fi

if grep -q "_is_diagnostic_logging_query" app/agentic/eol/agents/sre_orchestrator.py; then
    echo "   ✅ _is_diagnostic_logging_query() found"
else
    echo "   ❌ _is_diagnostic_logging_query() not found"
fi
echo ""

# Check for workflow methods
echo "3. Checking workflow implementations..."
if grep -q "_run_cost_analysis_deterministic_workflow" app/agentic/eol/agents/sre_orchestrator.py; then
    echo "   ✅ _run_cost_analysis_deterministic_workflow() found"
else
    echo "   ❌ _run_cost_analysis_deterministic_workflow() not found"
fi

if grep -q "_run_diagnostic_logging_deterministic_workflow" app/agentic/eol/agents/sre_orchestrator.py; then
    echo "   ✅ _run_diagnostic_logging_deterministic_workflow() found"
else
    echo "   ❌ _run_diagnostic_logging_deterministic_workflow() not found"
fi
echo ""

# Check for HTML formatters
echo "4. Checking HTML formatting methods..."
formatter_count=$(grep -c "def _format_" app/agentic/eol/agents/sre_orchestrator.py)
echo "   ✅ Found ${formatter_count} formatting methods"
echo ""

# Check routing logic
echo "5. Checking routing logic updates..."
if grep -q "_is_cost_analysis_query(query)" app/agentic/eol/agents/sre_orchestrator.py; then
    echo "   ✅ Cost analysis routing added"
else
    echo "   ❌ Cost analysis routing not found"
fi

if grep -q "_is_diagnostic_logging_query(query)" app/agentic/eol/agents/sre_orchestrator.py; then
    echo "   ✅ Diagnostic logging routing added"
else
    echo "   ❌ Diagnostic logging routing not found"
fi
echo ""

# Python syntax check
echo "6. Verifying Python syntax..."
if python3 -m py_compile app/agentic/eol/agents/sre_orchestrator.py 2>/dev/null; then
    echo "   ✅ Python syntax valid"
else
    echo "   ❌ Python syntax errors detected"
fi
echo ""

# Count lines changed
echo "7. Code statistics..."
lines_added=$(git diff main app/agentic/eol/agents/sre_orchestrator.py | grep -c "^+[^+]" || echo "0")
lines_removed=$(git diff main app/agentic/eol/agents/sre_orchestrator.py | grep -c "^-[^-]" || echo "0")
echo "   📊 Lines added: ${lines_added}"
echo "   📊 Lines removed: ${lines_removed}"
echo ""

echo "=========================================="
echo "Verification Complete!"
echo "=========================================="
echo ""
echo "Next Steps:"
echo "1. Run manual tests in SRE Assistant UI"
echo "2. Test all cost analysis examples"
echo "3. Test diagnostic logging example"
echo "4. Verify edge cases (empty subscription, no data)"
echo "5. Create PR and request code review"
