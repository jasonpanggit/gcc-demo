# 🎨 Design System Documentation

**EOL Agentic Platform Design System**
**Version:** 1.0.0
**Created:** 2026-02-19

---

## Overview

The EOL Agentic Platform design system provides a consistent, scalable foundation for UI development across all templates. It establishes design tokens, component patterns, and accessibility standards.

---

## 📦 Core Files

| File | Purpose | Load Order |
|------|---------|------------|
| `design-tokens.css` | CSS custom properties (variables) | 1st - Foundation |
| `common-components.css` | Reusable component styles | 2nd - Components |
| `style.css` | Base/global styles | 3rd - Application |
| Page-specific CSS | Template overrides | 4th - Overrides |

---

## 🎨 Design Tokens

### Colors

#### Primary Palette
```css
--color-primary: #0078d4;        /* Azure Blue */
--color-primary-dark: #005a9e;   /* Darker blue */
--color-primary-light: #50a7ff;  /* Lighter blue */
--color-primary-pale: #e6f3ff;   /* Very light blue */
```

#### Semantic Colors
```css
--color-success: #0a8754;   /* Green */
--color-warning: #f59e0b;   /* Orange */
--color-error: #dc2626;     /* Red */
--color-info: #0891b2;      /* Cyan */
```

#### Neutral Grays (9-level scale)
```css
--gray-900 to --gray-50
/* 900 = darkest, 50 = lightest */
```

### Typography

#### Font Families
```css
--font-family-base: -apple-system, BlinkMacSystemFont, "Segoe UI", ...
--font-family-mono: "SF Mono", Monaco, "Cascadia Code", ...
```

#### Font Sizes (Modular scale 1.25 ratio)
```css
--font-size-xs: 0.75rem     (12px)
--font-size-sm: 0.875rem    (14px)
--font-size-base: 1rem      (16px)
--font-size-md: 1.125rem    (18px)
--font-size-lg: 1.25rem     (20px)
--font-size-xl: 1.5rem      (24px)
--font-size-2xl: 1.875rem   (30px)
--font-size-3xl: 2.25rem    (36px)
--font-size-4xl: 3rem       (48px)
```

### Spacing (8px base unit)
```css
--spacing-xs: 0.5rem    (8px)
--spacing-sm: 0.75rem   (12px)
--spacing-md: 1rem      (16px)
--spacing-lg: 1.5rem    (24px)
--spacing-xl: 2rem      (32px)
--spacing-2xl: 3rem     (48px)
--spacing-3xl: 4rem     (64px)
--spacing-4xl: 6rem     (96px)
```

### Shadows
```css
--shadow-xs   /* Minimal shadow */
--shadow-sm   /* Small shadow */
--shadow-md   /* Medium shadow */
--shadow-lg   /* Large shadow */
--shadow-xl   /* Extra large shadow */
--shadow-2xl  /* Maximum shadow */
```

### Border Radius
```css
--radius-sm: 0.25rem   (4px)
--radius-md: 0.5rem    (8px)
--radius-lg: 0.75rem   (12px)
--radius-xl: 1rem      (16px)
--radius-full: 9999px  (Fully rounded)
```

---

## 🧩 Component Patterns

### Chat Interface

#### Usage
```jinja2
{% from "components/unified_chat.html" import render_chat, render_agent_comms %}

{{ render_chat(mode='mcp') }}
{{ render_agent_comms(mode='mcp') }}
```

#### Available Modes
- `mcp` - MCP Orchestrator with tool selectors
- `sre` - SRE Assistant
- `inventory` - Inventory Assistant
- `eol` - EOL Search

#### Custom Configuration
```jinja2
{{ render_chat(mode='mcp', custom_config={
    'title': 'Custom Title',
    'placeholder': 'Custom placeholder...',
    'show_examples': False
}) }}
```

### Buttons

```html
<!-- Primary action -->
<button class="btn btn-primary">
    <i class="fas fa-save me-1"></i>Save
</button>

<!-- Secondary action -->
<button class="btn btn-outline-secondary">
    Cancel
</button>

<!-- Destructive action -->
<button class="btn btn-danger">
    <i class="fas fa-trash me-1"></i>Delete
</button>
```

### Cards

```html
<div class="card shadow-sm">
    <div class="card-header bg-primary text-white">
        <h5 class="mb-0">
            <i class="fas fa-chart-line me-2"></i>Title
        </h5>
    </div>
    <div class="card-body">
        <!-- Content -->
    </div>
</div>
```

### Badges

```html
<span class="badge bg-success">Active</span>
<span class="badge bg-warning">Warning</span>
<span class="badge bg-danger">Critical</span>
<span class="badge bg-info">Info</span>
```

### Alerts

```html
<div class="alert alert-info">
    <i class="fas fa-info-circle me-2"></i>
    <strong>Information:</strong> Message here
</div>
```

---

## ♿ Accessibility Standards

### WCAG 2.1 AA Compliance

#### Color Contrast
- Normal text: Minimum 4.5:1 contrast ratio
- Large text (18pt+): Minimum 3:1 contrast ratio
- All semantic colors meet these requirements

#### Keyboard Navigation
```css
/* All interactive elements have visible focus */
*:focus-visible {
    outline: 2px solid var(--border-focus);
    outline-offset: 2px;
}
```

#### ARIA Labels
```html
<!-- Always provide accessible labels -->
<button aria-label="Clear chat history">
    <i class="fas fa-trash"></i>
</button>

<!-- Use ARIA roles for dynamic content -->
<div role="log" aria-live="polite" id="chat-messages">
    <!-- Live updates announced to screen readers -->
</div>
```

#### Skip Links
```html
<a href="#main-content" class="skip-to-main">
    Skip to main content
</a>
```

#### Screen Reader Only Content
```html
<span class="sr-only">
    Hidden from visual users, read by screen readers
</span>
```

---

## 📱 Responsive Design

### Breakpoints (detailed)

The design system follows a mobile-first approach. Use these breakpoints when writing responsive styles or defining component behaviors.

| Name | Media query (min-width) | Typical use |
|------|-------------------------|-------------|
| Small / Mobile | Default (up to 639px) | Stacked single-column views, full-width controls
| Medium / Tablet | @media (min-width: 640px) | Two-column layouts, compact nav
| Large / Desktop | @media (min-width: 1024px) | Multi-column dashboards, persistent sidebars
| Extra Large / Wide | @media (min-width: 1440px) | Wide dashboards, increased gutter spacing

Add responsive utilities or use the Bootstrap grid breakpoints when building layouts.

### Responsive patterns

- Cards: 1 column on mobile, 2 columns on tablet, 3+ columns on desktop depending on content density.
- Tables: collapse into card rows on small screens; consider horizontal scrolling only as a last resort.
- Navigation: use collapsed hamburger menu at mobile sizes; docked sidebar on large screens.



### Breakpoints
```css
/* Mobile-first approach */
/* Small (mobile): Default, < 640px */
/* Medium (tablet): >= 640px */
/* Large (desktop): >= 1024px */
/* Extra large: >= 1440px */
```

### Grid System
Use Bootstrap 5.3 grid with custom tokens:
```html
<div class="container-fluid">
    <div class="row g-3">  <!-- 3 = var(--spacing-md) -->
        <div class="col-md-6 col-lg-4">
            <!-- Content -->
        </div>
    </div>
</div>
```

---

## 📊 Chart.js Theme

### Standard Configuration
```javascript
const chartConfig = {
    responsive: true,
    maintainAspectRatio: true,
    plugins: {
        legend: {
            labels: {
                font: {
                    family: getComputedStyle(document.documentElement)
                        .getPropertyValue('--font-family-base'),
                    size: 14
                }
            }
        }
    },
    colors: [
        getComputedStyle(document.documentElement)
            .getPropertyValue('--color-primary'),
        getComputedStyle(document.documentElement)
            .getPropertyValue('--color-success'),
        // ... use design tokens
    ]
};
```

---

## 🎯 Best Practices

### Using Design Tokens

#### ✅ DO
```css
.my-component {
    padding: var(--spacing-md);
    color: var(--text-primary);
    border-radius: var(--radius-md);
    box-shadow: var(--shadow-sm);
}
```

#### ❌ DON'T
```css
.my-component {
    padding: 16px;           /* Use --spacing-md instead */
    color: #111827;          /* Use --text-primary instead */
    border-radius: 8px;      /* Use --radius-md instead */
    box-shadow: 0 1px 3px;   /* Use --shadow-sm instead */
}
```

### Component Consistency

#### ✅ DO
- Use unified chat component for all chat interfaces
- Apply semantic color classes (bg-success, text-error)
- Follow established spacing patterns

#### ❌ DON'T
- Create duplicate chat HTML structures
- Use arbitrary colors (#abc123)
- Use inline styles for spacing

### Accessibility

#### ✅ DO
```html
<button aria-label="Send message" onclick="sendMessage()">
    <i class="fas fa-paper-plane"></i>
</button>
```

#### ❌ DON'T
```html
<div onclick="sendMessage()">
    <i class="fas fa-paper-plane"></i>
</div>
```

---

## 🔄 Extending the Design System

### Adding New Colors
```css
/* In design-tokens.css */
:root {
    --color-my-new-color: #abcdef;
}
```

### Adding New Components
1. Create component in `components/` directory
2. Document in this file
3. Add usage examples
4. Test accessibility
5. Add to common-components.css if globally reusable

### Adding New Chat Modes
```python
# In utils/chat_config.py
CHAT_CONFIGS['new_mode'] = {
    'title': 'New Mode',
    'icon': 'fa-star',
    'placeholder': 'Type here...',
    'show_flow': True,
    # ... other options
}
```

---

## 📚 References

- **Bootstrap 5.3:** https://getbootstrap.com/docs/5.3/
- **Font Awesome 6.4:** https://fontawesome.com/icons
- **WCAG 2.1:** https://www.w3.org/WAI/WCAG21/quickref/
- **Chart.js:** https://www.chartjs.org/

---

## ✅ Checklist for New Components

When creating a new component:

- [ ] Uses design tokens (no hardcoded values)
- [ ] Follows spacing scale (8px base)
- [ ] Has keyboard navigation support
- [ ] Includes ARIA labels where needed
- [ ] Meets color contrast requirements
- [ ] Responsive across all breakpoints
- [ ] Documented with code examples
- [ ] Tested with screen reader
- [ ] Follows established patterns

---

**Maintained by:** UI/UX Revamp Project (Task #1)
**Last Updated:** 2026-02-19
**Version:** 1.0.0
