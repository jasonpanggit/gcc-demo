# Requirements: PostgreSQL Schema & Data Architecture Optimization

**Defined:** 2026-03-16
**Core Value:** Every UI view should be served by a single, fast PostgreSQL query with proper indexes and relationships.

## Discovery Phase (Current Focus)

Before defining implementation requirements, we need to map the current state:

### UI View Discovery
- [ ] **UI-01**: Map all HTML templates and identify unique UI views
- [ ] **UI-02**: For each UI view, document what data is displayed (tables, columns, filters, sorts, aggregations)
- [ ] **UI-03**: Document user interactions (search, filter, pagination, drill-down)
- [ ] **UI-04**: Identify which API endpoints serve each UI view

### Database Schema Discovery
- [x] **DB-01**: Document all PostgreSQL tables (names, columns, data types, constraints)
- [x] **DB-02**: Document existing relationships (foreign keys, indexes)
- [x] **DB-03**: Document materialized views and their dependencies
- [x] **DB-04**: Map which repository classes access which tables

### Current Query Patterns Discovery
- [x] **QRY-01**: For each UI view, capture the actual SQL queries executed
- [ ] **QRY-02**: Document "bad hacking" patterns with specific code examples
- [x] **QRY-03**: Identify performance bottlenecks (slow queries, missing indexes)
- [x] **QRY-04**: Document where multiple queries are used for single UI view

### Remote Data Cache Discovery
- [x] **CACHE-01**: Document what data is cached from LAW (Log Analytics Workspace)
- [x] **CACHE-02**: Document what data is cached from ARG (Azure Resource Graph)
- [x] **CACHE-03**: Document what data is cached from MSRC (Microsoft Security Response Center)
- [x] **CACHE-04**: Document current cache invalidation strategies (or lack thereof)

## Implementation Requirements (TBD)

Implementation requirements will be defined after completing the discovery phase above.

## UI Views Identified

Based on templates found:
1. **cve-dashboard.html** - CVE vulnerability dashboard
2. **cve-database.html** - CVE database view
3. **cve-detail.html** - Individual CVE details
4. **cve_alert_config.html** - CVE alert configuration
5. **cve_alert_history.html** - CVE alert history
6. **patch-management.html** - Patch management view
7. **inventory.html** - VM/resource inventory
8. **resource-inventory.html** - Azure resource inventory
9. **inventory-asst.html** - Inventory assistant
10. **eol.html** - End-of-life tracking
11. **eol-searches.html** - EOL search interface
12. **eol-inventory.html** - EOL inventory view
13. **eol-management.html** - EOL management
14. **azure-mcp.html** - Azure MCP interface
15. **cache.html** - Cache management
16. **routing-analytics.html** - Routing analytics
17. **visualizations.html** - Data visualizations

*Each UI view needs to be analyzed to understand its database requirements.*

## Out of Scope

- Cosmos DB optimization — already deprecated/removed
- Real-time streaming changes — current batch/poll model is sufficient
- Multi-tenancy sharding — single-tenant deployment model
- Full-text search engine (Elasticsearch) — PostgreSQL full-text is sufficient for current scale

## Traceability

*(Will be populated after discovery phase completes and implementation requirements are defined)*

---
*Requirements defined: 2026-03-16*
*Last updated: 2026-03-16 after discovery phase definition*
