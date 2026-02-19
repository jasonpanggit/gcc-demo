# Accessibility Guide

Version: 1.0.0
Created: 2026-02-19

Table of contents
- Introduction
- Goals & Standards (WCAG 2.1 AA)
- Color contrast rules and how to test
- Keyboard navigation requirements
- ARIA usage guidelines
- Screen reader testing steps
- Automated testing (axe, pa11y)
- Manual testing checklist
- Component-specific checks (cross-ref to COMPONENT-LIBRARY)
- Testing workflows for PRs
- Tools & references

---

Introduction

This guide complements .claude/DESIGN-SYSTEM.md and .claude/docs/COMPONENT-LIBRARY.md with practical, repeatable steps to verify accessibility across UI components and pages. Target standard: WCAG 2.1 AA.

Goals & Standards
- Meet WCAG 2.1 AA for all public-facing and internal UI flows
- Ensure keyboard-only operability
- Provide semantic markup and ARIA patterns where necessary
- Ensure error messages and live updates are announced by assistive tech

Color contrast

Rules:
- Normal text: 4.5:1 minimum contrast
- Large text (>= 18pt / 24px normal or 14pt bold): 3:1
- UI components (icons, UI controls): target 3:1 for non-text contrast

How to test:
- Use the browser devtools color contrast analyzer (Chrome Lighthouse, Firefox built-in)
- Use the Contrast Checker (WebAIM) for manual checks
- In CI, run axe-core checks as part of storybook/unit tests

Keyboard navigation

Requirements:
- All interactive elements must be reachable via Tab and Shift+Tab
- Focus order must follow visual order
- All actions must be performable by keyboard (Enter/Space for buttons, arrow keys for comboboxes)
- Visible focus indicator (prefers :focus-visible)

How to test:
1. Disable mouse
2. Tab through the page and ensure focus is visible and logical
3. Activate controls with keyboard and validate outcomes

ARIA usage

Principles:
- Prefer native HTML semantics over ARIA when possible
- When needed, follow WAI-ARIA Authoring Practices (APG)
- Keep ARIA roles and states up-to-date when dynamic content changes

Common patterns:
- role="dialog" + aria-modal="true" for modals
- role="log" + aria-live for chat messages
- role="alert" for important error messages
- aria-describedby for inputs with helper text

Screen reader testing steps

(Use NVDA on Windows, VoiceOver on macOS, and ORCA on Linux where applicable)
1. Enable screen reader
2. Navigate to page and verify headings hierarchy
3. Test forms: labels, errors, and focus
4. Test dynamic content: triggers that update role="status" or aria-live regions
5. Verify modals: announce title, trap focus, return focus on close

Automated testing

- axe-core: Integrate into storybook and CI. Use axe-core/guided fixes.
- pa11y: Run CLI against staging URLs
- jest-axe: For unit tests

Sample CI step (node):

```bash
# Run axe in Storybook or app URL
npx pa11y-ci --config .pa11yci.json
```

Manual testing checklist (pull requests)

For each UI PR, complete the checklist in PR description or link to storybook story:
- [ ] Labels associated with inputs
- [ ] Focus states visible
- [ ] All interactive elements keyboard operable
- [ ] Color contrast verified
- [ ] ARIA roles used correctly for dynamic content
- [ ] Screen reader smoke test completed
- [ ] Automated tests (axe/pa11y) pass

Component-specific checks
- See .claude/docs/COMPONENT-LIBRARY.md for each component's A11y notes

Testing workflows for PRs
1. Developer runs local storybook and runs axe plugin
2. Create PR with checklist filled and link to stories
3. Reviewer runs quick pa11y/axe check on deployed preview
4. Merge only when checklist and automated tests pass

Tools & references
- axe-core: https://github.com/dequelabs/axe-core
- pa11y: https://github.com/pa11y/pa11y
- WebAIM Contrast Checker: https://webaim.org/resources/contrastchecker/
- WAI-ARIA Authoring Practices: https://www.w3.org/TR/wai-aria-practices-1.2/
- WCAG 2.1 quick ref: https://www.w3.org/WAI/WCAG21/quickref/

Screenshots (text descriptions)
- Color contrast example: Side-by-side of label with sufficient contrast (black on white) vs insufficient (light gray on white) with callouts showing ratio values.
- Focus state: Button with visible 2px outline vs button without outline (legacy). Description shows how focus is improved.

Cross references
- Component docs: .claude/docs/COMPONENT-LIBRARY.md
- Design tokens: .claude/DESIGN-SYSTEM.md

Maintainers: Accessibility working group
Last updated: 2026-02-19
