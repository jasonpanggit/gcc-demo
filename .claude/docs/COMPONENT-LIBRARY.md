# Component Library

Version: 1.0.0
Created: 2026-02-19

Table of contents
- Introduction
- How to use this library
- Responsive breakpoints (summary)
- Components
  - Buttons
  - Inputs (text, textarea)
  - Selects & Comboboxes
  - Toggles / Checkboxes / Radios
  - Cards
  - Modals (dialogs)
  - Alerts & Toasts
  - Badges
  - Avatars
  - Tables
  - Forms & Validation
  - Tooltips & Popovers
  - Skeletons & Empty States
  - Chat UI (unified chat)
- Theming & tokens
- Accessibility notes per component
- Testing checklist
- Before / After comparisons
- Screenshots (text descriptions)
- Cross references

---

Introduction

This file documents the component-level library built on top of the Design System (.claude/DESIGN-SYSTEM.md). Each component section includes:
- Purpose and when to use
- Code examples (HTML/CSS and minimal JS where required)
- Accessibility considerations
- Responsive usage notes
- Before / After comparison (how to migrate from legacy code)
- Testing checklist

How to use this library

1. Use design tokens and utility classes from design-tokens.css and common-components.css.
2. Prefer the semantic classes (btn-primary, badge-success) instead of inline styles.
3. Keep components small, presentational, and composable. For application logic use the app-level JS modules.

Responsive breakpoints (summary)
- Mobile (default): < 640px
- Tablet: >= 640px and < 1024px
- Desktop: >= 1024px and < 1440px
- Wide: >= 1440px

See .claude/DESIGN-SYSTEM.md for token definitions and full breakpoint rules.

---

Components

Buttons
- Purpose: Primary actions (save, submit), secondary actions, destructive.

Usage (primary / secondary / destructive):

```html
<!-- Primary -->
<button class="btn btn-primary" aria-label="Save">
  <i class="fas fa-save me-1" aria-hidden="true"></i>
  Save
</button>

<!-- Secondary -->
<button class="btn btn-outline-secondary" aria-label="Cancel">Cancel</button>

<!-- Destructive -->
<button class="btn btn-danger" aria-label="Delete">
  <i class="fas fa-trash me-1" aria-hidden="true"></i>
  Delete
</button>
```

Key tokens used:
- padding: var(--spacing-sm / --spacing-md)
- border-radius: var(--radius-md)
- color: var(--color-primary)

Accessibility:
- Ensure aria-label or visible label is provided for icon-only buttons.
- Focus styles should use :focus-visible (outline 2px var(--border-focus)).

Responsive:
- Use block-level full-width on mobile for prominent actions: .btn-block or utility: w-100 d-block d-sm-inline-block

Before / After
- Before (legacy): <button style="background:#0078d4; color:white; padding:8px">Save</button>
- After: use <button class="btn btn-primary">Save</button> (uses tokens)

Testing checklist
- [ ] Color contrast passes 4.5:1
- [ ] Keyboard tab focus visible and usable
- [ ] Screen reader announces role and label

---

Inputs (text, textarea)

Purpose: single-line and multi-line text entry. Use for search, commands, forms.

Example:

```html
<label for="name" class="form-label">Full name</label>
<input id="name" class="form-control" type="text" placeholder="Jane Doe" />

<label for="bio" class="form-label">Bio</label>
<textarea id="bio" class="form-control" rows="4" placeholder="Short bio"></textarea>
```

Validation example (client-side):

```html
<form id="form-contact">
  <div class="mb-3">
    <label for="email" class="form-label">Email</label>
    <input id="email" name="email" type="email" class="form-control" required aria-describedby="emailHelp" />
    <div id="emailHelp" class="form-text">We'll never share your email.</div>
  </div>
</form>
```

Accessibility:
- Use <label> explicitly and for attribute.
- Use aria-invalid on invalid inputs and role="alert" on validation summaries.

Testing checklist
- [ ] Label associated via for/id
- [ ] Screen reader reads placeholder and label
- [ ] Error messages announced (aria-live or role=alert)

---

Selects & Comboboxes

Use native <select> for simple lists. Use ARIA 1.2 combobox pattern for searchable selects.

Example (native):

```html
<label for="region">Region</label>
<select id="region" class="form-select">
  <option value="us">US</option>
  <option value="eu">EU</option>
</select>
```

Combobox (searchable) minimal pattern note: implement with role="combobox" and aria-expanded, aria-controls, and a visible input.

Accessibility:
- Provide label and aria-describedby for helper text
- When using custom combobox ensure keyboard navigation (up/down, enter, escape)

Testing checklist
- [ ] Keyboard navigation works
- [ ] Screen reader announces expanded/collapsed state

---

Toggles / Checkboxes / Radios

Use semantic native controls when possible.

Checkbox example:

```html
<div class="form-check">
  <input class="form-check-input" type="checkbox" id="subscribe" />
  <label class="form-check-label" for="subscribe">Subscribe to emails</label>
</div>
```

Accessibility:
- Native inputs are preferred. If custom visuals are used, ensure role and keyboard behaviors are preserved.

Testing checklist
- [ ] Toggle is operable via keyboard (space/enter)
- [ ] State announced by screen reader

---

Cards

Usage: Group related content. Prefer a header + body + footer structure.

Example:

```html
<div class="card shadow-sm">
  <div class="card-header bg-primary text-white">
    <h5 class="mb-0"><i class="fas fa-chart-line me-2"></i>Sales</h5>
  </div>
  <div class="card-body">Summary and metric</div>
  <div class="card-footer text-muted">Updated 2h ago</div>
</div>
```

Accessibility:
- Headings should use h2-h6 appropriately for page structure.
- If card is interactive, use role="button" and provide keyboard handlers and tabindex.

Before / After
- Before: inline styles scattered across templates
- After: card component centralizes tokens and spacing

Testing checklist
- [ ] Heading levels consistent
- [ ] Color contrast for header text

---

Modals (dialogs)

Use the native dialog pattern or ARIA dialog with role="dialog" and aria-modal="true".

Example:

```html
<div class="modal" id="confirmDelete" role="dialog" aria-modal="true" aria-labelledby="confirmDeleteTitle">
  <div class="modal-dialog">
    <div class="modal-content">
      <div class="modal-header">
        <h5 id="confirmDeleteTitle" class="modal-title">Confirm delete</h5>
        <button class="btn-close" aria-label="Close"></button>
      </div>
      <div class="modal-body">Are you sure?</div>
      <div class="modal-footer">
        <button class="btn btn-outline-secondary" data-dismiss="modal">Cancel</button>
        <button class="btn btn-danger">Delete</button>
      </div>
    </div>
  </div>
</div>
```

Accessibility:
- Focus trap inside modal
- Return focus to the invoking element on close
- Provide meaningful aria-labelledby and aria-describedby

Testing checklist
- [ ] Focus trap verified
- [ ] Screen reader announces dialog title
- [ ] Escape closes dialog

---

Alerts & Toasts

Alerts (inline messages) and toasts (temporary overlays) use role="status" or role="alert" depending on urgency.

Example alert:

```html
<div class="alert alert-info" role="status">
  <i class="fas fa-info-circle me-2" aria-hidden="true"></i>
  <strong>Info:</strong> Message here
</div>
```

Toast example (aria-live polite):

```html
<div class="toast" role="status" aria-live="polite" aria-atomic="true">
  <div class="toast-body">Saved</div>
</div>
```

Testing checklist
- [ ] Screen reader announces alerts
- [ ] Alert types have appropriate colors and icons

---

Badges

Small labels for status.

Example:

```html
<span class="badge bg-success">Active</span>
```

Accessibility:
- Avoid conveying meaning by color alone; include text.

Testing checklist
- [ ] Contrast for badge background and text

---

Avatars

Use images with alt text and fallback initials.

Example:

```html
<img src="/avatars/jane.jpg" alt="Jane Doe" class="avatar" />

<!-- Fallback -->
<span class="avatar avatar-initials" aria-hidden="true">JD</span>
```

Testing checklist
- [ ] alt text present
- [ ] decorative avatars marked aria-hidden

---

Tables

Use <table> semantics with caption, thead, tbody, and scope attributes on th.

Example:

```html
<table class="table" role="table">
  <caption>Active agents</caption>
  <thead>
    <tr>
      <th scope="col">Name</th>
      <th scope="col">Status</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td>Agent A</td>
      <td><span class="badge bg-success">Active</span></td>
    </tr>
  </tbody>
</table>
```

Accessibility:
- Use responsive patterns (stacked rows) on narrow viewports

Testing checklist
- [ ] Column headers announced
- [ ] Table has caption

---

Forms & Validation

Use native validation attributes plus ARIA for richer messaging.

Example error:

```html
<input id="phone" aria-describedby="phone-error" aria-invalid="true" />
<div id="phone-error" role="alert">Please enter a valid phone number</div>
```

Testing checklist
- [ ] Error messages announced
- [ ] Form controls reachable and usable via keyboard

---

Tooltips & Popovers

Use aria-describedby on the target and keep tooltip content in DOM (visibility hidden) so screen readers can reference it; or use aria-hidden toggles carefully.

Example:

```html
<button aria-describedby="tooltip-1">Hover me</button>
<div id="tooltip-1" role="tooltip">Helpful tip</div>
```

Testing checklist
- [ ] Tooltip text readable by screen reader when referenced
- [ ] Tooltip dismisses on escape

---

Skeletons & Empty States

Use skeletons during loading and user-friendly empty states with next steps.

Example skeleton (CSS util):

```html
<div class="skeleton skeleton-line" style="width:60%"></div>
```

Empty state example (call to action):

```html
<div class="empty-state">
  <h3>No data found</h3>
  <p>Try adjusting filters or <button class="btn btn-primary">Create new</button></p>
</div>
```

Testing checklist
- [ ] Empty state heading present
- [ ] Action available and keyboard focusable

---

Chat UI (unified chat)

The platform uses a single chat component across modes. Rendered via server-side include or JS render function.

Example usage (Jinja):

```jinja
{% from "components/unified_chat.html" import render_chat %}
{{ render_chat(mode='mcp') }}
```

Client example (JS initialization):

```javascript
initChat({ selector: '#chat', mode: 'mcp', placeholder: 'Ask the platform...' })
```

Accessibility:
- Use role="log" and aria-live="polite" for message container
- Ensure new messages are announced but not noisy for screen reader users

Testing checklist
- [ ] Messages announced appropriately
- [ ] Input focus and send action keyboard accessible

---

Theming & tokens

All components must use tokens from .claude/DESIGN-SYSTEM.md (colors, spacing, radii). Avoid hard-coded values.

Accessibility notes per component
- See each component section above for specific ARIA and keyboard guidance.

Testing checklist (global)
- [ ] All components use tokens (no hard-coded colors or spacing)
- [ ] Lighthouse accessibility score >= 90 for main pages
- [ ] Axe-core automated tests pass for component stories
- [ ] Keyboard-only navigation of key flows
- [ ] Screen reader smoke test for primary pages

Before / After comparisons

Example - Buttons
- Before: style="background:#0078d4; color:#fff; padding:12px;"
- After: <button class="btn btn-primary"> uses tokens and consistent focus states

Screenshots (text descriptions)
- Buttons: Primary button — blue rounded rectangle with white text; focus shows 2px offset outline in a complementary neutral color.
- Chat UI: Left column with agent list, main area with chat cards, input bar anchored to bottom with placeholder.
- Modal: Centered panel with shadow, title at top, actions aligned right in footer.

Cross references
- Design tokens and global rules: .claude/DESIGN-SYSTEM.md
- Accessibility deep dive: .claude/docs/ACCESSIBILITY-GUIDE.md
- UI patterns & anti-patterns: .claude/docs/UI-PATTERNS.md
- Developer onboarding: .claude/docs/DEVELOPER-ONBOARDING.md

External references
- WCAG 2.1 quick reference: https://www.w3.org/WAI/WCAG21/quickref/
- Bootstrap 5.3 docs: https://getbootstrap.com/docs/5.3/
- ARIA Authoring Practices: https://www.w3.org/TR/wai-aria-practices-1.2/

---

Maintainers: UI/UX team
Last updated: 2026-02-19
