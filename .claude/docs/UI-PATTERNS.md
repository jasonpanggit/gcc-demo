# UI Patterns & Anti-Patterns

Version: 1.0.0
Created: 2026-02-19

Table of contents
- Purpose
- Common patterns
  - Layout
  - Navigation
  - Forms
  - Feedback
  - Data tables and lists
  - Empty & loading states
- Anti-patterns (what to avoid)
- Migration examples (legacy -> new)
- Pattern library (component combinations)
- Visual guidance & spacing rules
- Cross references

---

Purpose

This document captures the common UI patterns used across the EOL Agentic Platform and explains why they help users. It also lists anti-patterns to avoid and migration guidance.

Common patterns

Layout
- Use a two-column layout for dashboards: navigation (left) + content (right)
- Use consistent page margins via container classes and tokens
- Keep header and footer height values consistent; responsive collapsing of side nav at tablet breakpoint

Navigation
- Side navigation: collapsible, grouped by domain, use icons + labels
- Breadcrumbs: show context for deep navigation
- Use progressive disclosure for advanced settings (expanders)

Forms
- Group related inputs with fieldsets and legends
- Validate on blur and on submit; show inline errors and summary
- Use stepper pattern for multi-step flows

Feedback
- Use toasts for transient confirmations and alerts for inline issues
- Use color + icon + text for status indications (do not rely on color alone)

Data tables & lists
- Use column sorting, filtering, and pagination for large datasets
- For responsive, collapse columns into stacking cards on small screens

Empty & loading states
- Show skeleton loaders for network latencies
- Provide helpful CTAs in empty states

Anti-patterns
- Inline styles that bypass design tokens
- Overloaded modals (putting too many actions inside a single dialog)
- Using color alone to convey state
- Non-semantic elements with click handlers (divs without role/button)
- Deep nesting of interactive controls that breaks tab order

Migration examples
- Legacy toolbar buttons to new button styles (example replacing inline style with btn-primary)
- Legacy tables to accessible tables (adding caption, scope on th)

Pattern library (component combinations)
- Filter bar + table: persistent filter chip list, active filters count badge
- Chat + sidebar: sticky input, collapsible agent list, message threading
- Dashboard card grid: responsive 3-up on desktop, 1-up on mobile

Visual guidance & spacing rules
- Use 8px spacing scale
- Use consistent border radii (radius-md for controls, radius-lg for cards)
- Use shadows sparingly for elevation cues

Cross references
- Component library: .claude/docs/COMPONENT-LIBRARY.md
- Design tokens: .claude/DESIGN-SYSTEM.md
- Accessibility guide: .claude/docs/ACCESSIBILITY-GUIDE.md

Maintainers: UI Patterns working group
Last updated: 2026-02-19
