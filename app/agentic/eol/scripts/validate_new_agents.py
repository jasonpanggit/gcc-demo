#!/usr/bin/env python3
"""Quick validation script for the three new specialist agents.

This script validates that the agents can be imported and have the correct structure
without requiring the full MCP server infrastructure.
"""
import sys
from pathlib import Path
import inspect

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

def validate_agent_structure(agent_class, expected_actions):
    """Validate that an agent has the expected structure."""
    print(f"\nValidating {agent_class.__name__}...")

    # Check inheritance
    from agents.base_sre_agent import BaseSREAgent
    if not issubclass(agent_class, BaseSREAgent):
        print(f"  ❌ Does not inherit from BaseSREAgent")
        return False
    print(f"  ✓ Inherits from BaseSREAgent")

    # Check required methods
    required_methods = ['execute', '_initialize_impl', '_cleanup_impl']
    for method in required_methods:
        if not hasattr(agent_class, method):
            print(f"  ❌ Missing method: {method}")
            return False
    print(f"  ✓ Has all required methods")

    # Check execute method signature
    execute_method = getattr(agent_class, 'execute')
    sig = inspect.signature(execute_method)
    if 'request' not in sig.parameters or 'context' not in sig.parameters:
        print(f"  ❌ execute() method has wrong signature")
        return False
    print(f"  ✓ execute() method has correct signature")

    # Check if agent can be instantiated
    try:
        agent = agent_class()
        print(f"  ✓ Can be instantiated")
        print(f"    - Agent ID: {agent.agent_id}")
        print(f"    - Agent Type: {agent.agent_type}")
    except Exception as e:
        print(f"  ❌ Cannot instantiate: {e}")
        return False

    # Check docstring
    if not agent_class.__doc__:
        print(f"  ⚠️ Missing class docstring")
    else:
        print(f"  ✓ Has class docstring")

    # Verify action handlers exist
    source = inspect.getsource(agent_class)
    missing_actions = []
    for action in expected_actions:
        action_method = f"_{action}"
        if action_method not in source and f'"{action}"' not in source:
            missing_actions.append(action)

    if missing_actions:
        print(f"  ⚠️ Possibly missing actions: {missing_actions}")
    else:
        print(f"  ✓ All expected actions present: {expected_actions}")

    return True


def main():
    """Run validation for all three new agents."""
    print("=" * 60)
    print("Specialist Agent Structure Validation")
    print("=" * 60)

    all_passed = True

    # Test 1: Configuration Management Agent
    print("\n" + "=" * 60)
    print("TEST 1: Configuration Management Agent")
    print("=" * 60)

    try:
        from agents.configuration_management_agent import ConfigurationManagementAgent
        expected_actions = ['scan', 'drift', 'compliance', 'remediate', 'baseline', 'full']
        result = validate_agent_structure(ConfigurationManagementAgent, expected_actions)
        all_passed = all_passed and result

        if result:
            print("\n✅ Configuration Management Agent: VALID")
        else:
            print("\n❌ Configuration Management Agent: INVALID")

    except Exception as e:
        print(f"❌ Failed to import ConfigurationManagementAgent: {e}")
        all_passed = False

    # Test 2: SLO Management Agent
    print("\n" + "=" * 60)
    print("TEST 2: SLO Management Agent")
    print("=" * 60)

    try:
        from agents.slo_management_agent import SLOManagementAgent
        expected_actions = ['track', 'budget', 'alert', 'report', 'forecast', 'full']
        result = validate_agent_structure(SLOManagementAgent, expected_actions)
        all_passed = all_passed and result

        if result:
            print("\n✅ SLO Management Agent: VALID")
        else:
            print("\n❌ SLO Management Agent: INVALID")

    except Exception as e:
        print(f"❌ Failed to import SLOManagementAgent: {e}")
        all_passed = False

    # Test 3: Remediation Agent
    print("\n" + "=" * 60)
    print("TEST 3: Remediation Agent")
    print("=" * 60)

    try:
        from agents.remediation_agent import RemediationAgent
        expected_actions = ['diagnose', 'recommend', 'execute', 'rollback', 'verify', 'full']
        result = validate_agent_structure(RemediationAgent, expected_actions)
        all_passed = all_passed and result

        if result:
            print("\n✅ Remediation Agent: VALID")
        else:
            print("\n❌ Remediation Agent: INVALID")

    except Exception as e:
        print(f"❌ Failed to import RemediationAgent: {e}")
        all_passed = False

    # Summary
    print("\n" + "=" * 60)
    print("Validation Summary")
    print("=" * 60)

    if all_passed:
        print("\n✅ All three agents passed validation!")
        print("\nCapabilities:")
        print("  1. Configuration Management Agent")
        print("     - Scans configuration across resources")
        print("     - Detects configuration drift from baseline")
        print("     - Checks policy compliance")
        print("     - Applies configuration fixes")
        print("     - Manages configuration baselines")
        print("\n  2. SLO Management Agent")
        print("     - Tracks SLO/SLI metrics")
        print("     - Calculates error budget status")
        print("     - Configures SLO-based alerts")
        print("     - Generates compliance reports")
        print("     - Forecasts SLO burn rate")
        print("\n  3. Remediation Agent")
        print("     - Diagnoses resource issues")
        print("     - Recommends remediation actions")
        print("     - Executes remediations with safety checks")
        print("     - Rollback capability for failed remediations")
        print("     - Post-remediation verification")
        print("\n✨ All agents are ready for integration!")
        print("\nNext steps:")
        print("  1. Register agents with the orchestrator")
        print("  2. Create FastAPI endpoints")
        print("  3. Run integration tests with MCP server")
        print("  4. Deploy to Azure Container Apps")
        sys.exit(0)
    else:
        print("\n❌ Some agents failed validation")
        sys.exit(1)


if __name__ == "__main__":
    main()
