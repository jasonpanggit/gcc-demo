# CLAUDE.md - Agents

Guide for `app/agentic/eol/agents` (41 Python modules).

---

## Core Files

- **Orchestrators:** `mcp_orchestrator.py`, `eol_orchestrator.py`, `inventory_orchestrator.py`, `sre_orchestrator.py`
- **Base classes:** `base_eol_agent.py`, `base_sre_agent.py`, `domain_sub_agent.py`
- **Domain Sub-Agents:** `sre_sub_agent.py`, `patch_sub_agent.py`, `monitor_agent.py`, `network_agent.py` (extend DomainSubAgent with specialized system prompts and ReAct loops)
- **SRE specialists:** incident, performance, cost, security, health, configuration, SLO, remediation agents
  - `security_compliance_agent.py`: Enhanced with Azure resource compliance audits (network, private endpoints, encryption, public access)
- **Vendor/domain agents:** microsoft, redhat, ubuntu, oracle, vmware, endoflife/eolstatus, and language/runtime specific agents
- **Tool routing:** `tool_router.py`, `router.py` for intelligent tool selection and query routing

---

## Patterns

### Orchestration
- Use iterative reasoning with bounded turns.
- Route tool execution through composite MCP clients.
- Return structured responses with explicit fallback/error messaging.

### EOL Aggregation
- Fan out vendor checks asynchronously.
- Normalize confidence/scoring before selecting best result.
- Preserve source metadata and evidence links in final responses.

### SRE Flow
- Merge params from request + context + environment defaults.
- Ask follow-up questions when required params are missing.
- Support graceful degradation when some tools are unavailable.

### Domain Sub-Agent Pattern
- Extend `DomainSubAgent` base class for domain specialists (SRE, Patch, Monitor).
- Each sub-agent has dedicated system prompt teaching domain workflows.
- Orchestrators delegate via meta-tools (`sre_agent`, `patch_agent`, `monitor_agent`).
- Sub-agents run independent ReAct loops over their specialized tool sets.

---

## Adding an Agent

1. Implement in a new `*_agent.py` module.
2. Reuse base classes where possible (`BaseEOLAgent` / `BaseSREAgent`).
3. Register in the correct orchestrator (`eol_orchestrator.py` or `sre_orchestrator.py`).
4. Update tool metadata/routing if behavior depends on explicit mapping.
5. Add tests under `tests/` and run targeted pytest commands.

---

## Test Commands

```bash
pytest tests/test_eol_orchestrator.py -v
pytest tests/test_sre_*.py -v
pytest tests/test_security_compliance_agent.py -v
pytest -m unit
```

---

**Version:** 2.4 (Updated 2026-02-26)
**Total modules:** 41
**Recent updates:** Post-merge - added NetworkAgent, tool routing agents, expanded domain sub-agents
