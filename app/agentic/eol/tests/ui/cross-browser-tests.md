# Cross-Browser Testing Plan - EOL Agentic Platform

## Overview
This document outlines the cross-browser testing matrix for the EOL Agentic Platform UI/UX improvements (Tasks #1-9).

**Test Date:** _____________
**Tester:** _____________
**Version:** _____________

---

## Browser Support Matrix

### Tier 1: Primary Support (Full Feature Parity)
These browsers receive priority support and must pass all tests.

| Browser | Version | Platform | Market Share | Priority |
|---------|---------|----------|--------------|----------|
| Chrome | Latest (v121+) | Windows, macOS, Linux | ~65% | HIGH |
| Edge | Latest (v121+) | Windows, macOS | ~12% | HIGH |
| Safari | Latest (v17+) | macOS, iOS | ~18% | HIGH |
| Firefox | Latest (v122+) | Windows, macOS, Linux | ~3% | MEDIUM |

### Tier 2: Secondary Support (Graceful Degradation)
These browsers receive basic support with acceptable fallbacks.

| Browser | Version | Platform | Notes |
|---------|---------|----------|-------|
| Chrome | Previous major version | All platforms | Auto-updates |
| Safari | Previous major version | macOS, iOS | For older macOS users |
| Firefox | ESR (Extended Support) | All platforms | Enterprise users |
| Samsung Internet | Latest | Android | Mobile users |

### Tier 3: Legacy Support (No Active Support)
These browsers may work but are not actively tested.

| Browser | Version | Platform | Notes |
|---------|---------|----------|-------|
| Internet Explorer | 11 | Windows | EOL, not supported |
| Opera | Latest | All platforms | Chromium-based, likely works |

---

## Testing Environments

### Desktop Testing
```
Operating Systems:
- Windows 11 (1920x1080, 125% scaling)
- macOS Sonoma (2560x1440, Retina)
- Ubuntu 22.04 LTS (1920x1080)

Browsers:
- Chrome v121+ (desktop)
- Firefox v122+ (desktop)
- Safari v17+ (macOS only)
- Edge v121+ (Windows/macOS)
```

### Mobile Testing
```
Devices:
- iPhone 14 Pro (iOS 17+, Safari)
- iPhone SE (375x667, iOS 16+)
- Samsung Galaxy S23 (Android 13+, Chrome)
- iPad Pro 11" (iOS 17+, Safari)

Browsers:
- Safari (iOS)
- Chrome (Android)
- Samsung Internet (Android)
```

### Virtual/Cloud Testing
**BrowserStack:** https://www.browserstack.com/
**Sauce Labs:** https://saucelabs.com/
**LambdaTest:** https://www.lambdatest.com/

---

## Test Cases by Browser

## 1. Layout & Responsive Design

### 1.1 Desktop Layout (1920x1080)
**Test:** Page layout renders correctly at desktop resolution.

| Test Step | Chrome | Firefox | Safari | Edge | Notes |
|-----------|--------|---------|--------|------|-------|
| Header layout | ☐ | ☐ | ☐ | ☐ | Logo, nav, user menu aligned |
| Sidebar width | ☐ | ☐ | ☐ | ☐ | 300px width maintained |
| Main content area | ☐ | ☐ | ☐ | ☐ | Proper padding/margins |
| Footer placement | ☐ | ☐ | ☐ | ☐ | Sticky to bottom if short content |
| Grid layouts | ☐ | ☐ | ☐ | ☐ | Cards in proper columns |
| Table layouts | ☐ | ☐ | ☐ | ☐ | Tables display correctly |

### 1.2 Tablet Layout (768px - iPad)
**Test:** Responsive breakpoints work correctly on tablet.

| Test Step | Chrome | Firefox | Safari | Edge | Notes |
|-----------|--------|---------|--------|------|-------|
| Navigation collapses | ☐ | ☐ | ☐ | ☐ | Hamburger menu appears |
| Sidebar stacks/hides | ☐ | ☐ | ☐ | ☐ | Below or hidden on tablet |
| Content reflows | ☐ | ☐ | ☐ | ☐ | No horizontal scroll |
| Touch targets adequate | ☐ | ☐ | ☐ | ☐ | Min 44x44px |
| Tables scroll | ☐ | ☐ | ☐ | ☐ | Horizontal scroll enabled |

### 1.3 Mobile Layout (375px - iPhone SE)
**Test:** Mobile-first design works on smallest supported device.

| Test Step | Chrome | Firefox | Safari | Edge | Notes |
|-----------|--------|---------|--------|------|-------|
| Single column layout | ☐ | ☐ | ☐ | ☐ | Content stacks vertically |
| Navigation menu | ☐ | ☐ | ☐ | ☐ | Full-screen overlay menu |
| Font sizes readable | ☐ | ☐ | ☐ | ☐ | Min 16px for body text |
| Forms usable | ☐ | ☐ | ☐ | ☐ | Inputs large enough to tap |
| Buttons/CTAs visible | ☐ | ☐ | ☐ | ☐ | Min 44x44px touch targets |
| No horizontal scroll | ☐ | ☐ | ☐ | ☐ | Content fits viewport |

### 1.4 Zoom & Scaling (200%)
**Test:** Page usable at 200% browser zoom.

| Test Step | Chrome | Firefox | Safari | Edge | Notes |
|-----------|--------|---------|--------|------|-------|
| Text reflows | ☐ | ☐ | ☐ | ☐ | No horizontal scroll at 1280px |
| No content loss | ☐ | ☐ | ☐ | ☐ | All content accessible |
| Images scale | ☐ | ☐ | ☐ | ☐ | Images don't overflow |
| Modals fit | ☐ | ☐ | ☐ | ☐ | Dialogs don't exceed viewport |

---

## 2. CSS & Styling

### 2.1 CSS Custom Properties (Variables)
**Test:** CSS custom properties work correctly across browsers.

| Test Step | Chrome | Firefox | Safari | Edge | Notes |
|-----------|--------|---------|--------|------|-------|
| Color variables | ☐ | ☐ | ☐ | ☐ | --primary-color applies |
| Spacing variables | ☐ | ☐ | ☐ | ☐ | --spacing-* values work |
| Font variables | ☐ | ☐ | ☐ | ☐ | --font-* values work |
| Dark mode toggle | ☐ | ☐ | ☐ | ☐ | Theme switch updates variables |
| Fallback values | ☐ | ☐ | ☐ | ☐ | Fallbacks for unsupported features |

### 2.2 Flexbox & Grid
**Test:** Modern CSS layout systems render correctly.

| Test Step | Chrome | Firefox | Safari | Edge | Notes |
|-----------|--------|---------|--------|------|-------|
| Flexbox layouts | ☐ | ☐ | ☐ | ☐ | Items align/justify correctly |
| Grid layouts | ☐ | ☐ | ☐ | ☐ | Grid template areas work |
| Gap property | ☐ | ☐ | ☐ | ☐ | Gap applies to flex/grid |
| Nested grids | ☐ | ☐ | ☐ | ☐ | Subgrids render correctly |

### 2.3 Animations & Transitions
**Test:** CSS animations and transitions work smoothly.

| Test Step | Chrome | Firefox | Safari | Edge | Notes |
|-----------|--------|---------|--------|------|-------|
| Hover transitions | ☐ | ☐ | ☐ | ☐ | Smooth color/transform changes |
| Loading spinners | ☐ | ☐ | ☐ | ☐ | Rotate animation smooth |
| Modal fade-in | ☐ | ☐ | ☐ | ☐ | Opacity transition works |
| Slide-in menus | ☐ | ☐ | ☐ | ☐ | Transform animations smooth |
| Reduced motion | ☐ | ☐ | ☐ | ☐ | Respects prefers-reduced-motion |

### 2.4 Typography
**Test:** Fonts render consistently across browsers.

| Test Step | Chrome | Firefox | Safari | Edge | Notes |
|-----------|--------|---------|--------|------|-------|
| System font stack | ☐ | ☐ | ☐ | ☐ | -apple-system, etc. work |
| Font weights | ☐ | ☐ | ☐ | ☐ | 300, 400, 600, 700 render |
| Line heights | ☐ | ☐ | ☐ | ☐ | Text not cramped or spaced |
| Letter spacing | ☐ | ☐ | ☐ | ☐ | Headings have proper spacing |
| Text rendering | ☐ | ☐ | ☐ | ☐ | antialiased/subpixel-antialiased |

---

## 3. JavaScript Functionality

### 3.1 Interactive Components
**Test:** JavaScript-driven components work across browsers.

| Test Step | Chrome | Firefox | Safari | Edge | Notes |
|-----------|--------|---------|--------|------|-------|
| Modal dialogs open/close | ☐ | ☐ | ☐ | ☐ | Click trigger, Escape closes |
| Dropdown menus | ☐ | ☐ | ☐ | ☐ | Open/close on click |
| Tab switching | ☐ | ☐ | ☐ | ☐ | Tabs change content |
| Accordion expand/collapse | ☐ | ☐ | ☐ | ☐ | Sections toggle |
| Form validation | ☐ | ☐ | ☐ | ☐ | Client-side validation runs |
| Loading states | ☐ | ☐ | ☐ | ☐ | Spinners show during async |
| Error handling | ☐ | ☐ | ☐ | ☐ | Errors display correctly |

### 3.2 AJAX / Fetch API
**Test:** Asynchronous requests work correctly.

| Test Step | Chrome | Firefox | Safari | Edge | Notes |
|-----------|--------|---------|--------|------|-------|
| API calls execute | ☐ | ☐ | ☐ | ☐ | Fetch/XMLHttpRequest work |
| JSON parsing | ☐ | ☐ | ☐ | ☐ | Response data parses |
| Error handling | ☐ | ☐ | ☐ | ☐ | Network errors caught |
| Loading indicators | ☐ | ☐ | ☐ | ☐ | Show during request |
| Content updates | ☐ | ☐ | ☐ | ☐ | DOM updates with data |

### 3.3 Event Handling
**Test:** Event listeners work correctly across browsers.

| Test Step | Chrome | Firefox | Safari | Edge | Notes |
|-----------|--------|---------|--------|------|-------|
| Click events | ☐ | ☐ | ☐ | ☐ | Buttons respond to clicks |
| Keyboard events | ☐ | ☐ | ☐ | ☐ | Enter, Escape, arrows work |
| Touch events | ☐ | ☐ | ☐ | ☐ | Mobile: tap, swipe work |
| Form submit | ☐ | ☐ | ☐ | ☐ | preventDefault works |
| Event delegation | ☐ | ☐ | ☐ | ☐ | Dynamic elements receive events |

### 3.4 ES6+ Features
**Test:** Modern JavaScript features work (or are polyfilled).

| Test Step | Chrome | Firefox | Safari | Edge | Notes |
|-----------|--------|---------|--------|------|-------|
| Arrow functions | ☐ | ☐ | ☐ | ☐ | `() => {}` syntax works |
| Template literals | ☐ | ☐ | ☐ | ☐ | Backtick strings work |
| Const/let | ☐ | ☐ | ☐ | ☐ | Block scoping works |
| Destructuring | ☐ | ☐ | ☐ | ☐ | `{a, b} = obj` works |
| Spread operator | ☐ | ☐ | ☐ | ☐ | `...array` works |
| Promises | ☐ | ☐ | ☐ | ☐ | `.then()` chains work |
| Async/await | ☐ | ☐ | ☐ | ☐ | Async functions work |

---

## 4. Forms & Input

### 4.1 Form Controls
**Test:** Form elements render and function correctly.

| Test Step | Chrome | Firefox | Safari | Edge | Notes |
|-----------|--------|---------|--------|------|-------|
| Text inputs | ☐ | ☐ | ☐ | ☐ | Type, style, validate |
| Textareas | ☐ | ☐ | ☐ | ☐ | Multi-line input works |
| Select dropdowns | ☐ | ☐ | ☐ | ☐ | Options selectable |
| Checkboxes | ☐ | ☐ | ☐ | ☐ | Custom styles render |
| Radio buttons | ☐ | ☐ | ☐ | ☐ | Custom styles render |
| File uploads | ☐ | ☐ | ☐ | ☐ | Custom button works |
| Date pickers | ☐ | ☐ | ☐ | ☐ | Native or custom picker |

### 4.2 HTML5 Input Types
**Test:** HTML5 input types work or degrade gracefully.

| Test Step | Chrome | Firefox | Safari | Edge | Notes |
|-----------|--------|---------|--------|------|-------|
| type="email" | ☐ | ☐ | ☐ | ☐ | Email validation |
| type="url" | ☐ | ☐ | ☐ | ☐ | URL validation |
| type="tel" | ☐ | ☐ | ☐ | ☐ | Phone keyboard on mobile |
| type="number" | ☐ | ☐ | ☐ | ☐ | Number input with spinners |
| type="date" | ☐ | ☐ | ☐ | ☐ | Date picker or fallback |
| type="search" | ☐ | ☐ | ☐ | ☐ | Search field styling |

### 4.3 Form Validation
**Test:** Client-side validation works correctly.

| Test Step | Chrome | Firefox | Safari | Edge | Notes |
|-----------|--------|---------|--------|------|-------|
| Required fields | ☐ | ☐ | ☐ | ☐ | "required" attribute works |
| Pattern matching | ☐ | ☐ | ☐ | ☐ | Regex validation works |
| Min/max length | ☐ | ☐ | ☐ | ☐ | Character limits enforced |
| Custom validation | ☐ | ☐ | ☐ | ☐ | JavaScript validation runs |
| Error messages | ☐ | ☐ | ☐ | ☐ | Errors display correctly |
| Submit prevention | ☐ | ☐ | ☐ | ☐ | Invalid forms don't submit |

---

## 5. Accessibility Features

### 5.1 Keyboard Navigation
**Test:** All functionality accessible via keyboard.

| Test Step | Chrome | Firefox | Safari | Edge | Notes |
|-----------|--------|---------|--------|------|-------|
| Tab order logical | ☐ | ☐ | ☐ | ☐ | Top-to-bottom, left-to-right |
| Focus indicators visible | ☐ | ☐ | ☐ | ☐ | Outline or ring on focus |
| Skip to content link | ☐ | ☐ | ☐ | ☐ | First tab, moves to main |
| Modal focus trap | ☐ | ☐ | ☐ | ☐ | Tab stays in modal |
| Dropdown keyboard nav | ☐ | ☐ | ☐ | ☐ | Arrow keys, Enter, Escape |
| No keyboard traps | ☐ | ☐ | ☐ | ☐ | Can tab out of all elements |

### 5.2 ARIA & Semantics
**Test:** ARIA attributes work correctly across browsers.

| Test Step | Chrome | Firefox | Safari | Edge | Notes |
|-----------|--------|---------|--------|------|-------|
| aria-label recognized | ☐ | ☐ | ☐ | ☐ | Screen readers read labels |
| aria-live regions | ☐ | ☐ | ☐ | ☐ | Updates announced |
| role attributes | ☐ | ☐ | ☐ | ☐ | Roles applied correctly |
| aria-expanded | ☐ | ☐ | ☐ | ☐ | Toggles correctly |
| Landmark regions | ☐ | ☐ | ☐ | ☐ | nav, main, aside recognized |

### 5.3 Screen Reader Testing
**Test:** Page works with screen readers on each browser.

| Test Step | Chrome + NVDA | Firefox + NVDA | Safari + VO | Edge + Narrator | Notes |
|-----------|---------------|----------------|-------------|-----------------|-------|
| Page title read | ☐ | ☐ | ☐ | ☐ | Title announced on load |
| Headings navigable | ☐ | ☐ | ☐ | ☐ | H key jumps headings |
| Links descriptive | ☐ | ☐ | ☐ | ☐ | Link text read |
| Buttons labeled | ☐ | ☐ | ☐ | ☐ | Button text/label read |
| Form labels read | ☐ | ☐ | ☐ | ☐ | Labels associated |
| Live regions announce | ☐ | ☐ | ☐ | ☐ | Updates spoken |

---

## 6. Performance

### 6.1 Page Load Performance
**Test:** Pages load quickly across browsers.

| Test Step | Chrome | Firefox | Safari | Edge | Notes |
|-----------|--------|---------|--------|------|-------|
| First paint < 1s | ☐ | ☐ | ☐ | ☐ | Visual content appears |
| DOM ready < 1.5s | ☐ | ☐ | ☐ | ☐ | Page interactive |
| Full load < 2s | ☐ | ☐ | ☐ | ☐ | All resources loaded |
| No render blocking | ☐ | ☐ | ☐ | ☐ | CSS/JS non-blocking |
| No console errors | ☐ | ☐ | ☐ | ☐ | Clean console |

### 6.2 Bundle Size
**Test:** JavaScript/CSS bundles are optimized.

| Test Step | Chrome | Firefox | Safari | Edge | Notes |
|-----------|--------|---------|--------|------|-------|
| JS bundle < 500KB | ☐ | ☐ | ☐ | ☐ | Total script size |
| CSS bundle < 100KB | ☐ | ☐ | ☐ | ☐ | Total style size |
| Gzip/Brotli enabled | ☐ | ☐ | ☐ | ☐ | Compressed transfer |
| Images optimized | ☐ | ☐ | ☐ | ☐ | WebP, compressed |

### 6.3 Runtime Performance
**Test:** Page is responsive during use.

| Test Step | Chrome | Firefox | Safari | Edge | Notes |
|-----------|--------|---------|--------|------|-------|
| Smooth scrolling | ☐ | ☐ | ☐ | ☐ | 60fps scrolling |
| Smooth animations | ☐ | ☐ | ☐ | ☐ | 60fps transitions |
| No memory leaks | ☐ | ☐ | ☐ | ☐ | Extended use stable |
| No layout thrashing | ☐ | ☐ | ☐ | ☐ | No CLS during interactions |

---

## 7. Browser-Specific Issues

### 7.1 Safari-Specific Tests
**Issue:** Safari has unique rendering and compatibility quirks.

| Test Step | Safari macOS | Safari iOS | Status | Notes |
|-----------|--------------|------------|--------|-------|
| Flexbox gap property | ☐ | ☐ | | Use fallback margins if needed |
| Date input styling | ☐ | ☐ | | Custom styling limited |
| Position: sticky | ☐ | ☐ | | Check within flex containers |
| Backdrop blur | ☐ | ☐ | | -webkit-backdrop-filter |
| 100vh on mobile | ☐ | ☐ | | URL bar causes height changes |
| Touch callout | ☐ | ☐ | | -webkit-touch-callout: none |

### 7.2 Firefox-Specific Tests
**Issue:** Firefox has unique DevTools and rendering behavior.

| Test Step | Firefox Desktop | Status | Notes |
|-----------|----------------|--------|-------|
| Scrollbar styling | ☐ | | Use scrollbar-width, scrollbar-color |
| Focus-visible | ☐ | | Firefox shows outline by default |
| Input autofill styling | ☐ | | :-moz-autofill styles |
| Line-clamp | ☐ | | Use -webkit-line-clamp (works in FF) |

### 7.3 Edge-Specific Tests
**Issue:** Edge (Chromium) generally matches Chrome but test for completeness.

| Test Step | Edge Desktop | Status | Notes |
|-----------|-------------|--------|-------|
| Chromium features | ☐ | | Should match Chrome |
| Legacy Edge fallbacks | ☐ | | Not needed (Chromium-based) |
| Windows integration | ☐ | | Native Windows behaviors |

---

## 8. Page-by-Page Testing

### 8.1 Home/Index Page (/)
**Test:** Landing page works across all browsers.

| Feature | Chrome | Firefox | Safari | Edge | Notes |
|---------|--------|---------|--------|------|-------|
| Hero section renders | ☐ | ☐ | ☐ | ☐ | Layout, images, text |
| Navigation menu | ☐ | ☐ | ☐ | ☐ | Links work, dropdown opens |
| Search functionality | ☐ | ☐ | ☐ | ☐ | Search executes |
| Footer links | ☐ | ☐ | ☐ | ☐ | All footer links work |
| Responsive layout | ☐ | ☐ | ☐ | ☐ | Mobile/tablet/desktop |

### 8.2 Agents Page (/agents)
**Test:** Agents listing and management.

| Feature | Chrome | Firefox | Safari | Edge | Notes |
|---------|--------|---------|--------|------|-------|
| Agents list loads | ☐ | ☐ | ☐ | ☐ | API call successful |
| Agent cards render | ☐ | ☐ | ☐ | ☐ | Grid layout, styles |
| Filters work | ☐ | ☐ | ☐ | ☐ | Dropdown filters apply |
| Search agents | ☐ | ☐ | ☐ | ☐ | Search filters list |
| Modal dialogs | ☐ | ☐ | ☐ | ☐ | Agent details modal |
| Loading states | ☐ | ☐ | ☐ | ☐ | Spinner during load |

### 8.3 Inventory Page (/inventory)
**Test:** Inventory dashboard and tables.

| Feature | Chrome | Firefox | Safari | Edge | Notes |
|---------|--------|---------|--------|------|-------|
| Inventory table loads | ☐ | ☐ | ☐ | ☐ | Data fetched and rendered |
| Table sorting | ☐ | ☐ | ☐ | ☐ | Click headers to sort |
| Pagination | ☐ | ☐ | ☐ | ☐ | Page navigation works |
| Filters/facets | ☐ | ☐ | ☐ | ☐ | Filter by category, status |
| Export functionality | ☐ | ☐ | ☐ | ☐ | CSV/Excel export |
| Responsive table | ☐ | ☐ | ☐ | ☐ | Horizontal scroll on mobile |

### 8.4 EOL Management Page (/eol)
**Test:** End-of-life tracking interface.

| Feature | Chrome | Firefox | Safari | Edge | Notes |
|---------|--------|---------|--------|------|-------|
| EOL products list | ☐ | ☐ | ☐ | ☐ | Products with EOL dates |
| Timeline view | ☐ | ☐ | ☐ | ☐ | Visual timeline renders |
| Search EOL products | ☐ | ☐ | ☐ | ☐ | Search functionality |
| Alerts/notifications | ☐ | ☐ | ☐ | ☐ | EOL alerts display |
| Details panel | ☐ | ☐ | ☐ | ☐ | Side panel with details |

### 8.5 Cache Page (/cache)
**Test:** Cache management interface.

| Feature | Chrome | Firefox | Safari | Edge | Notes |
|---------|--------|---------|--------|------|-------|
| Cache stats display | ☐ | ☐ | ☐ | ☐ | Hit rate, size, etc. |
| Clear cache button | ☐ | ☐ | ☐ | ☐ | Confirmation modal |
| Cache entries list | ☐ | ☐ | ☐ | ☐ | Table of cached items |
| Refresh functionality | ☐ | ☐ | ☐ | ☐ | Manual refresh |

### 8.6 Azure MCP Page (/azure-mcp)
**Test:** Azure integration interface.

| Feature | Chrome | Firefox | Safari | Edge | Notes |
|---------|--------|---------|--------|------|-------|
| Connection status | ☐ | ☐ | ☐ | ☐ | Azure connection indicator |
| Resource explorer | ☐ | ☐ | ☐ | ☐ | Tree view of resources |
| Action buttons | ☐ | ☐ | ☐ | ☐ | Deploy, stop, restart |
| Logs viewer | ☐ | ☐ | ☐ | ☐ | Real-time log streaming |

### 8.7 Azure AI SRE Page (/azure-ai-sre)
**Test:** AI-powered SRE interface.

| Feature | Chrome | Firefox | Safari | Edge | Notes |
|---------|--------|---------|--------|------|-------|
| Dashboard loads | ☐ | ☐ | ☐ | ☐ | Metrics, charts render |
| Chart rendering | ☐ | ☐ | ☐ | ☐ | SVG/Canvas charts |
| Real-time updates | ☐ | ☐ | ☐ | ☐ | WebSocket or polling |
| AI recommendations | ☐ | ☐ | ☐ | ☐ | AI suggestions display |
| Interactive controls | ☐ | ☐ | ☐ | ☐ | Filters, date pickers |

---

## 9. Device & Network Testing

### 9.1 Network Conditions
**Test:** Page works under various network speeds.

| Condition | Chrome | Firefox | Safari | Edge | Notes |
|-----------|--------|---------|--------|------|-------|
| Fast 3G (DevTools) | ☐ | ☐ | ☐ | ☐ | Throttle to Fast 3G |
| Slow 3G (DevTools) | ☐ | ☐ | ☐ | ☐ | Throttle to Slow 3G |
| Offline mode | ☐ | ☐ | ☐ | ☐ | Service worker or error page |
| Intermittent connection | ☐ | ☐ | ☐ | ☐ | Toggle online/offline |

### 9.2 Device Pixel Ratios
**Test:** Page renders correctly on high-DPI displays.

| Device | DPR | Chrome | Firefox | Safari | Notes |
|--------|-----|--------|---------|--------|-------|
| Standard Display | 1x | ☐ | ☐ | ☐ | 1920x1080 |
| Retina Display | 2x | ☐ | ☐ | ☐ | MacBook Pro |
| High-DPI Display | 3x | ☐ | ☐ | ☐ | iPhone 14 Pro |

---

## 10. Security & Privacy

### 10.1 HTTPS/Security
**Test:** Security features work correctly.

| Test Step | Chrome | Firefox | Safari | Edge | Notes |
|-----------|--------|---------|--------|------|-------|
| HTTPS enforced | ☐ | ☐ | ☐ | ☐ | HTTP redirects to HTTPS |
| Mixed content blocked | ☐ | ☐ | ☐ | ☐ | No HTTP resources on HTTPS page |
| CSP headers | ☐ | ☐ | ☐ | ☐ | Content Security Policy set |
| Secure cookies | ☐ | ☐ | ☐ | ☐ | SameSite, Secure flags |

### 10.2 Privacy Features
**Test:** Privacy preferences respected.

| Test Step | Chrome | Firefox | Safari | Edge | Notes |
|-----------|--------|---------|--------|------|-------|
| Do Not Track | ☐ | ☐ | ☐ | ☐ | DNT header respected |
| Cookie consent | ☐ | ☐ | ☐ | ☐ | Banner displays, saves choice |
| Local storage limits | ☐ | ☐ | ☐ | ☐ | Graceful degradation if blocked |

---

## 11. Automated Cross-Browser Testing

### 11.1 Playwright Tests
**Script:** `tests/ui/run-ui-tests.sh`

```bash
# Run Playwright tests across all browsers
npm run test:playwright -- --project=chromium --project=firefox --project=webkit
```

| Test Suite | Chromium | Firefox | WebKit | Status |
|------------|----------|---------|--------|--------|
| Homepage | ☐ | ☐ | ☐ | |
| Navigation | ☐ | ☐ | ☐ | |
| Forms | ☐ | ☐ | ☐ | |
| Authentication | ☐ | ☐ | ☐ | |
| Data tables | ☐ | ☐ | ☐ | |

### 11.2 Selenium Grid (Optional)
**Setup:** If using Selenium for cross-browser testing.

```bash
# Run Selenium tests
npm run test:selenium
```

---

## 12. Testing Tools & Commands

### Chrome DevTools
```bash
# Open DevTools
Cmd+Option+I (macOS) / Ctrl+Shift+I (Windows)

# Device emulation
Cmd+Shift+M (macOS) / Ctrl+Shift+M (Windows)

# Lighthouse audit
Cmd+Option+I > Lighthouse tab > Generate report
```

### Firefox DevTools
```bash
# Open DevTools
Cmd+Option+I (macOS) / Ctrl+Shift+I (Windows)

# Responsive design mode
Cmd+Option+M (macOS) / Ctrl+Shift+M (Windows)
```

### Safari Web Inspector
```bash
# Enable Develop menu
Safari > Preferences > Advanced > Show Develop menu

# Open Web Inspector
Cmd+Option+I

# Responsive design mode
Develop > Enter Responsive Design Mode
```

### Edge DevTools
```bash
# Open DevTools
F12 or Cmd+Option+I (macOS) / Ctrl+Shift+I (Windows)

# Same as Chrome (Chromium-based)
```

---

## Known Browser Quirks & Workarounds

### Safari
- **Issue:** `100vh` includes URL bar on mobile, causing content to be hidden
  - **Fix:** Use `100dvh` (dynamic viewport height) or JavaScript calculation

- **Issue:** Date input styling limited
  - **Fix:** Use custom date picker library (e.g., Flatpickr)

- **Issue:** Flex gap not supported in older versions
  - **Fix:** Use margins as fallback

### Firefox
- **Issue:** Custom scrollbar styling uses different properties
  - **Fix:** Use `scrollbar-width` and `scrollbar-color` in addition to WebKit properties

### All Mobile Browsers
- **Issue:** 300ms click delay on touch devices (older devices)
  - **Fix:** `touch-action: manipulation` CSS property

---

## Success Criteria

✅ **All Tier 1 browsers:** 100% test pass rate
✅ **All Tier 2 browsers:** 95%+ test pass rate
✅ **No critical bugs:** No functionality broken in any tier 1 browser
✅ **Visual consistency:** UI looks correct across all browsers (within reason)
✅ **Performance parity:** Load times similar across browsers (±20%)

---

## Bug Reporting Template

```markdown
## Bug Report

**Browser:** Chrome 121 / Firefox 122 / Safari 17 / Edge 121
**OS:** Windows 11 / macOS Sonoma / iOS 17
**Page:** /agents
**Severity:** Critical / High / Medium / Low

**Description:**
[What's broken?]

**Steps to Reproduce:**
1. Navigate to /agents
2. Click on filter dropdown
3. Select "Active" filter
4. [Bug occurs]

**Expected Behavior:**
[What should happen?]

**Actual Behavior:**
[What actually happens?]

**Screenshot/Video:**
[Attach if applicable]

**Console Errors:**
```
[Paste console output]
```

**Workaround:**
[If known]
```

---

## Sign-Off

**Tester:** ___________________________
**Date:** ___________________________
**Result:** ☐ PASS (All Tier 1 browsers)  ☐ CONDITIONAL PASS (Minor issues)  ☐ FAIL (Critical bugs)

**Notes:**
___________________________
___________________________

---

**Last Updated:** 2026-02-19
**Revision:** 1.0
