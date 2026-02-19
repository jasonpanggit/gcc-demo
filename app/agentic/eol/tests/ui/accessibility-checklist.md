# Accessibility Testing Checklist - EOL Agentic Platform

## Overview
This checklist ensures WCAG 2.1 AA compliance for all UI/UX improvements implemented in Tasks #1-9.

**Testing Date:** _____________
**Tester:** _____________
**Browser/Version:** _____________
**Screen Reader:** _____________

---

## 1. Keyboard Navigation Testing

### 1.1 Tab Order & Focus Management
- [ ] **Tab through entire page** - Focus moves in logical reading order (left-to-right, top-to-bottom)
- [ ] **Shift+Tab works** - Reverse tab order functions correctly
- [ ] **Skip to main content link** - First tab reveals skip link at top of page
- [ ] **Skip link functionality** - Activating skip link moves focus to main content
- [ ] **No keyboard traps** - User can tab into and out of all interactive elements
- [ ] **Modal dialogs** - Focus trapped within modal when open, returns to trigger on close
- [ ] **Dropdown menus** - Arrow keys navigate menu items, Escape closes menu
- [ ] **Tab panels** - Arrow keys switch between tabs

### 1.2 Focus Indicators
- [ ] **Visible focus indicators** - All interactive elements show clear focus outline (2px minimum)
- [ ] **Focus color contrast** - Focus indicators have 3:1 contrast ratio against background
- [ ] **Custom focus styles** - Focus indicators use CSS custom properties (--focus-ring-color)
- [ ] **No outline removal** - `outline: none` not used without alternative focus style
- [ ] **Focus on buttons** - All buttons show focus state
- [ ] **Focus on links** - All links show focus state
- [ ] **Focus on form fields** - All inputs, selects, textareas show focus state
- [ ] **Focus on custom controls** - Cards, tabs, accordions show focus state

### 1.3 Keyboard Shortcuts
- [ ] **Enter activates buttons** - Enter key triggers button actions
- [ ] **Space activates buttons** - Space key triggers button actions
- [ ] **Enter activates links** - Enter key follows links
- [ ] **Enter/Space on custom controls** - Custom interactive elements respond to keyboard
- [ ] **Escape closes overlays** - Escape key closes modals, dropdowns, tooltips
- [ ] **Arrow key navigation** - Where applicable (tabs, menus, radio groups)

---

## 2. Screen Reader Testing

### 2.1 NVDA Testing (Windows)
**Download:** https://www.nvaccess.org/download/

#### Basic Navigation
- [ ] **Start NVDA** - NVDA+Ctrl (default)
- [ ] **Browse mode** - Use arrow keys to navigate page content
- [ ] **Headers navigation** - Press H to jump between headings
- [ ] **Landmarks navigation** - Press D to jump between landmarks (nav, main, aside, footer)
- [ ] **Links list** - NVDA+F7 opens links list
- [ ] **Headings list** - NVDA+F7 and switch to headings tab
- [ ] **Forms mode** - NVDA auto-switches to forms mode on form fields

#### Content Verification
- [ ] **Page title announced** - Page title read when page loads
- [ ] **Headings hierarchy** - H1, H2, H3 structure announced correctly
- [ ] **Landmark regions** - Navigation, main, aside, footer announced
- [ ] **Link text** - Links have descriptive text (not "click here")
- [ ] **Button labels** - Buttons have clear, descriptive labels
- [ ] **Form labels** - All form fields have associated labels
- [ ] **Error messages** - Form errors announced and associated with fields
- [ ] **Dynamic content** - Live regions announce updates (aria-live)
- [ ] **Images** - Images have alt text (or alt="" if decorative)
- [ ] **Tables** - Table headers (<th>) and captions announced

### 2.2 VoiceOver Testing (macOS)
**Activation:** Cmd+F5

#### Basic Navigation
- [ ] **Start VoiceOver** - Cmd+F5
- [ ] **VO keys** - Control+Option (VO)
- [ ] **Web rotor** - VO+U opens web rotor (headings, links, landmarks)
- [ ] **Next item** - VO+Right Arrow
- [ ] **Previous item** - VO+Left Arrow
- [ ] **Enter container** - VO+Shift+Down Arrow
- [ ] **Exit container** - VO+Shift+Up Arrow

#### Content Verification
- [ ] **Page title announced** - Page title read when page loads
- [ ] **Headings navigation** - VO+U, then use arrows in Headings list
- [ ] **Landmarks navigation** - VO+U, then use arrows in Landmarks list
- [ ] **Form controls** - VO+U, then use arrows in Form Controls list
- [ ] **Button states** - Buttons announce "button" role and label
- [ ] **Link purpose** - Links announce "link" role and descriptive text
- [ ] **Form field labels** - Labels read before/with form fields
- [ ] **Required fields** - Required state announced
- [ ] **Validation errors** - Error messages read with fields
- [ ] **Live regions** - Updates announced automatically

---

## 3. Color & Contrast Testing

### 3.1 Color Contrast Ratios (WCAG AA)
**Tool:** Use browser DevTools or https://webaim.org/resources/contrastchecker/

- [ ] **Body text (14-18px)** - 4.5:1 contrast ratio minimum
- [ ] **Large text (18px+ or 14px+ bold)** - 3:1 contrast ratio minimum
- [ ] **UI components** - 3:1 contrast ratio (buttons, form borders, icons)
- [ ] **Focus indicators** - 3:1 contrast ratio against background
- [ ] **Link text** - 4.5:1 contrast ratio (or 3:1 if underlined)
- [ ] **Error messages** - 4.5:1 contrast ratio
- [ ] **Placeholder text** - 4.5:1 contrast ratio (or remove placeholders)
- [ ] **Disabled state** - Clearly distinguishable (contrast not required)

### 3.2 Color Independence
- [ ] **No color-only indicators** - Don't rely solely on color for meaning
- [ ] **Error fields** - Errors shown with icons/text, not just red borders
- [ ] **Required fields** - Shown with asterisk/text, not just colored
- [ ] **Status indicators** - Use icons + text, not just colored dots
- [ ] **Charts/graphs** - Include patterns/labels, not just colors
- [ ] **Links in text** - Underlined or have 3:1 contrast with surrounding text

---

## 4. Responsive & Mobile Accessibility

### 4.1 Mobile Viewport (375px - iPhone SE)
- [ ] **No horizontal scroll** - Content fits within viewport
- [ ] **Touch targets 44x44px** - All interactive elements meet minimum size
- [ ] **Text readable** - No text smaller than 16px (or allows zoom)
- [ ] **Forms usable** - Form fields large enough to tap accurately
- [ ] **Spacing adequate** - 8px minimum between interactive elements
- [ ] **Navigation accessible** - Mobile menu keyboard/touch accessible
- [ ] **Modals work** - Dialogs don't overflow viewport
- [ ] **Skip link visible** - Skip link works on mobile

### 4.2 Tablet Viewport (768px - iPad)
- [ ] **No horizontal scroll** - Content adapts to tablet width
- [ ] **Touch targets adequate** - All buttons/links tappable
- [ ] **Tables responsive** - Tables scroll or stack appropriately
- [ ] **Navigation intuitive** - Menu works well on tablet
- [ ] **Text readable** - Font sizes appropriate for tablet

### 4.3 Zoom & Reflow Testing
- [ ] **200% zoom works** - Page usable at 200% zoom (Ctrl/Cmd +)
- [ ] **No horizontal scroll at 200%** - Content reflows at 1280px width, 200% zoom
- [ ] **Text resizes** - Using browser zoom (not just font-size increase)
- [ ] **No content loss** - All content accessible at 200% zoom
- [ ] **No truncation** - Text doesn't get cut off when zoomed

---

## 5. Semantic HTML & ARIA

### 5.1 Semantic Structure
- [ ] **Proper HTML5 elements** - `<header>`, `<nav>`, `<main>`, `<aside>`, `<footer>`
- [ ] **One `<main>` landmark** - Page has single `<main>` element
- [ ] **Headings hierarchy** - Logical H1 → H2 → H3 structure (no skipping)
- [ ] **One H1 per page** - Each page has exactly one H1
- [ ] **Lists for lists** - `<ul>`/`<ol>` used for actual lists
- [ ] **Tables for data** - `<table>` only for tabular data (not layout)
- [ ] **Buttons for actions** - `<button>` for actions, `<a>` for navigation
- [ ] **Form elements** - Proper `<label>`, `<input>`, `<select>`, `<textarea>`

### 5.2 ARIA Usage
- [ ] **ARIA only when needed** - Prefer semantic HTML over ARIA
- [ ] **Required ARIA attributes** - `aria-label` on icon-only buttons
- [ ] **`aria-labelledby`** - Used for complex labels (e.g., dialog titles)
- [ ] **`aria-describedby`** - Used for help text, error messages
- [ ] **`aria-live` regions** - For dynamic content updates (polite/assertive)
- [ ] **`aria-expanded`** - On collapsible sections (true/false)
- [ ] **`aria-controls`** - Links trigger to controlled element
- [ ] **`aria-current="page"`** - On current navigation link
- [ ] **`role="status"`** - For status messages
- [ ] **`role="alert"`** - For urgent messages
- [ ] **No ARIA conflicts** - ARIA doesn't override semantic HTML

### 5.3 Landmark Regions
- [ ] **`<nav>` or `role="navigation"`** - For navigation menus
- [ ] **`<main>` or `role="main"`** - For main content
- [ ] **`<aside>` or `role="complementary"`** - For sidebars
- [ ] **`<footer>` or `role="contentinfo"`** - For page footer
- [ ] **`role="banner"`** - For site header (if not `<header>` in `<body>`)
- [ ] **`role="search"`** - For search forms
- [ ] **Multiple landmarks labeled** - Use `aria-label` if multiple same-type landmarks

---

## 6. Forms Accessibility

### 6.1 Form Labels
- [ ] **All inputs have labels** - Every `<input>`, `<select>`, `<textarea>` has associated `<label>`
- [ ] **Explicit association** - Labels use `for` attribute matching input `id`
- [ ] **Label position** - Labels above or to left of inputs (not below)
- [ ] **No placeholder-only labels** - Placeholders supplement, don't replace labels
- [ ] **Group labels** - `<fieldset>` + `<legend>` for radio/checkbox groups

### 6.2 Form Validation
- [ ] **Required fields indicated** - `required` attribute + visual indicator (*)
- [ ] **`aria-required="true"`** - On required fields for screen readers
- [ ] **Error messages visible** - Errors shown near relevant field
- [ ] **`aria-invalid="true"`** - Set on fields with errors
- [ ] **`aria-describedby`** - Links error message to field
- [ ] **Error summary** - List of errors at top of form (optional but helpful)
- [ ] **Success messages** - Confirmation shown in `aria-live` region
- [ ] **Focus on first error** - Focus moves to first error field on submit

### 6.3 Form Usability
- [ ] **Autocomplete attributes** - Use `autocomplete` for common fields (name, email, etc.)
- [ ] **Input types** - Proper `type` (email, tel, url, number, date)
- [ ] **Help text accessible** - Help text linked via `aria-describedby`
- [ ] **Character limits** - Announced to screen readers (`aria-describedby`)
- [ ] **Disabled states** - Clearly distinguishable (grayed out)
- [ ] **Loading states** - `aria-busy="true"` during async operations

---

## 7. Interactive Components

### 7.1 Buttons
- [ ] **Accessible names** - All buttons have text or `aria-label`
- [ ] **Icon-only buttons** - Have `aria-label` (e.g., "Close dialog")
- [ ] **Button states** - Hover, focus, active, disabled states clear
- [ ] **`<button>` element** - Use `<button>`, not `<div role="button">`
- [ ] **Type attribute** - `type="button"` for non-submit buttons

### 7.2 Links
- [ ] **Descriptive link text** - No "click here" or "read more" without context
- [ ] **External links** - Indicated with icon + screen reader text
- [ ] **New window links** - `target="_blank"` announced to screen readers
- [ ] **Skip links** - "Skip to main content" at top of page
- [ ] **Link purpose clear** - Link text describes destination

### 7.3 Modals/Dialogs
- [ ] **`role="dialog"`** - On modal container
- [ ] **`aria-labelledby`** - References dialog title
- [ ] **`aria-modal="true"`** - Indicates modal behavior
- [ ] **Focus trap** - Tab stays within modal
- [ ] **Initial focus** - Focus moves to modal on open (title or first field)
- [ ] **Close button** - Keyboard accessible (Enter, Escape)
- [ ] **Return focus** - Focus returns to trigger on close
- [ ] **Background inert** - `aria-hidden="true"` on background content

### 7.4 Tabs
- [ ] **`role="tablist"`** - On tab container
- [ ] **`role="tab"`** - On each tab button
- [ ] **`role="tabpanel"`** - On each panel
- [ ] **`aria-selected`** - "true" on active tab, "false" on others
- [ ] **`aria-controls`** - Tab references its panel
- [ ] **Arrow key navigation** - Left/Right arrows switch tabs
- [ ] **Tab + arrow pattern** - Tab to tablist, arrows within tabs

### 7.5 Alerts/Notifications
- [ ] **`role="alert"`** - For urgent messages (auto-announced)
- [ ] **`role="status"`** - For non-urgent messages
- [ ] **`aria-live="polite"`** - For status updates
- [ ] **`aria-live="assertive"`** - For urgent alerts
- [ ] **Dismissible** - Close button keyboard accessible
- [ ] **Timeout announced** - If auto-dismiss, enough time to read (5s minimum)

---

## 8. Images & Media

### 8.1 Images
- [ ] **Informative images** - Have descriptive `alt` text
- [ ] **Decorative images** - Use `alt=""` (empty alt)
- [ ] **Complex images** - Have long description (`aria-describedby` or caption)
- [ ] **Icon images** - Have `alt` describing function (e.g., "Search")
- [ ] **Logo images** - `alt` with organization name
- [ ] **Background images** - Decorative only (important content not in CSS backgrounds)

### 8.2 Icons
- [ ] **Icon-only buttons** - Have `aria-label` or visible text
- [ ] **Decorative icons** - `aria-hidden="true"`
- [ ] **SVG icons** - Have `role="img"` and `<title>` if informative
- [ ] **Font icons** - Parent has `aria-label`, icon has `aria-hidden="true"`

---

## 9. Data Tables

### 9.1 Table Structure
- [ ] **`<table>` element** - Use semantic table, not divs
- [ ] **`<caption>`** - Table has caption or `aria-label`
- [ ] **`<thead>`, `<tbody>`** - Proper table sections
- [ ] **`<th>` headers** - Column/row headers use `<th>`, not `<td>`
- [ ] **`scope` attribute** - `scope="col"` or `scope="row"` on headers
- [ ] **Complex tables** - Use `id` and `headers` attribute if multi-level headers

### 9.2 Table Responsiveness
- [ ] **Horizontal scroll** - Large tables scroll horizontally on mobile
- [ ] **Scroll indicators** - Visual cue that table scrolls
- [ ] **Alternative views** - Consider card view for mobile (optional)

---

## 10. Page-Level Testing

### 10.1 Document Structure
- [ ] **Valid HTML** - No errors in W3C validator (https://validator.w3.org/)
- [ ] **`lang` attribute** - `<html lang="en">` set correctly
- [ ] **`<title>` element** - Descriptive, unique page title
- [ ] **Meta viewport** - `<meta name="viewport" content="width=device-width, initial-scale=1">`
- [ ] **Skip to content** - Skip link before navigation
- [ ] **Logical heading order** - H1 → H2 → H3 (no skipping levels)

### 10.2 Performance & UX
- [ ] **Page loads in < 2s** - Fast initial load
- [ ] **No layout shifts** - CLS < 0.1 (Cumulative Layout Shift)
- [ ] **Loading states** - Spinners/skeletons for async content
- [ ] **Error states** - Clear error messages with recovery steps
- [ ] **Timeout warnings** - Warning before session timeout (if applicable)

---

## 11. Automated Testing

### 11.1 Browser DevTools
- [ ] **Lighthouse audit** - Run Lighthouse in Chrome DevTools (100/100 Accessibility)
- [ ] **Inspect accessibility tree** - Check in Elements > Accessibility panel
- [ ] **Color contrast** - Check in DevTools (Chrome shows contrast ratio)

### 11.2 Browser Extensions
- [ ] **axe DevTools** - Run axe extension (https://www.deque.com/axe/devtools/)
- [ ] **WAVE** - Run WAVE extension (https://wave.webaim.org/extension/)
- [ ] **Accessibility Insights** - Run FastPass (https://accessibilityinsights.io/)

### 11.3 Automated Tests
- [ ] **Lighthouse CI** - Run `npm run test:lighthouse` - All pages pass
- [ ] **Pa11y** - Run `npm run test:a11y` - No errors (if configured)
- [ ] **Axe-core** - Run in test suite - No violations

---

## 12. Browser & Device Testing

### 12.1 Desktop Browsers
- [ ] **Chrome (latest)** - Full functionality
- [ ] **Firefox (latest)** - Full functionality
- [ ] **Safari (latest)** - Full functionality
- [ ] **Edge (latest)** - Full functionality

### 12.2 Mobile Browsers
- [ ] **Chrome Mobile (Android)** - Touch targets, scrolling, zoom
- [ ] **Safari (iOS)** - VoiceOver, touch targets, zoom
- [ ] **Samsung Internet (Android)** - Basic functionality

### 12.3 Screen Readers
- [ ] **NVDA + Chrome (Windows)** - Complete page navigation
- [ ] **JAWS + Chrome (Windows)** - Complete page navigation (if available)
- [ ] **VoiceOver + Safari (macOS)** - Complete page navigation
- [ ] **VoiceOver + Safari (iOS)** - Mobile navigation (if available)
- [ ] **TalkBack + Chrome (Android)** - Mobile navigation (if available)

---

## 13. Additional Checks

### 13.1 Content Accessibility
- [ ] **Plain language** - Content written at 8th grade reading level (where possible)
- [ ] **Abbreviations explained** - First use of acronyms spelled out
- [ ] **Link text unique** - Multiple "Read more" links have context
- [ ] **No content solely in PDFs** - Or PDFs are accessible (tagged)

### 13.2 User Control
- [ ] **No auto-play** - Videos/audio don't auto-play (or have controls)
- [ ] **Animation control** - Respect `prefers-reduced-motion`
- [ ] **Pause/stop** - Carousels have pause button
- [ ] **Sufficient time** - No time limits, or adjustable
- [ ] **No seizure triggers** - No flashing content > 3 times/second

---

## Success Criteria Summary

✅ **Lighthouse Accessibility:** 100/100
✅ **WCAG 2.1 AA:** No violations
✅ **Keyboard Navigation:** All functionality accessible
✅ **Screen Reader:** All content announced correctly
✅ **Color Contrast:** All text meets 4.5:1 or 3:1 ratio
✅ **Mobile:** Touch targets 44x44px, no horizontal scroll
✅ **Cross-Browser:** Works in Chrome, Firefox, Safari, Edge

---

## Notes & Issues

| Issue | Severity | Page/Component | Status | Notes |
|-------|----------|----------------|--------|-------|
|       |          |                |        |       |
|       |          |                |        |       |
|       |          |                |        |       |

---

## Sign-Off

**Tester Name:** ___________________________
**Date:** ___________________________
**Result:** ☐ PASS  ☐ FAIL (see notes)

---

**Last Updated:** 2026-02-19
**Revision:** 1.0
