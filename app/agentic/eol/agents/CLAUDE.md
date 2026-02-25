# CLAUDE.md - Agents

Guide for `app/agentic/eol/agents` (36 Python modules).

---

## Core Files

- **Orchestrators:** `mcp_orchestrator.py`, `eol_orchestrator.py`, `inventory_orchestrator.py`, `sre_orchestrator.py`
- **Base classes:** `base_eol_agent.py`, `base_sre_agent.py`
- **SRE specialists:** incident, performance, cost, security, health, configuration, SLO, remediation agents
  - `security_compliance_agent.py`: Enhanced with Azure resource compliance audits (network, private endpoints, encryption, public access)
- **Vendor/domain agents:** microsoft, redhat, ubuntu, oracle, vmware, endoflife/eolstatus, and language/runtime specific agents

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

**Version:** 2.2 (Updated 2026-02-25)
**Total modules:** 36
**Recent updates:** SecurityComplianceAgent enhanced with Azure resource compliance audits
