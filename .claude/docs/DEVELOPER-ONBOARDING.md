# Developer Onboarding - UI/UX

Version: 1.0.0
Created: 2026-02-19

Table of contents
- Quick start (setup)
- Local environment (styles, storybook)
- Running the app and storybook
- Adding a new component (step-by-step)
- Styling guidelines
- Testing and QA (accessibility + visual)
- PR checklist
- Common pitfalls
- Useful commands
- Links and references

---

Quick start (5-minute setup)
1. Clone repository and create venv (see root README):

```bash
git clone <repo>
python -m venv .venv
source .venv/bin/activate
pip install -r app/agentic/eol/requirements.txt
```

2. Install Node dependencies for storybook and frontend tooling (if applicable):

```bash
cd app/agentic/eol/frontend
npm install
```

3. Start storybook:

```bash
npm run storybook
```

4. Start the app backend (for integration):

```bash
cd app/agentic/eol
uvicorn main:app --reload --port 8000
```

Local environment
- Style files live in: .claude/DESIGN-SYSTEM.md references design-tokens.css and common-components.css
- Components: app/agentic/eol/components or frontend/components depending on implementation
- Storybook stories: frontend/stories or components/**/__stories__

Running storybook
- Use storybook to preview components in isolation and run accessibility checks via addon-a11y

Adding a new component (step-by-step)
1. Create new component file in components/ (prefer server-side include or frontend component depending on stack)
2. Add styles using design tokens (no hard-coded colors/spacings)
3. Create storybook story demonstrating states (default, hover, focus, invalid)
4. Add tests: unit tests + jest-axe accessibility test
5. Add documentation in .claude/docs/COMPONENT-LIBRARY.md: code example, accessibility notes, before/after
6. Open PR and include checklist

Styling guidelines
- Use variables from design-tokens.css
- Prefer utility classes for layout and spacing
- Keep CSS specificities low; use BEM or scoped modules if needed

Testing and QA
- Run unit tests and storybook
- Run axe-core and pa11y during CI
- Manually test keyboard and screen reader for new components

PR checklist (required for UI changes)
- [ ] Storybook story added
- [ ] Automated tests passing
- [ ] Accessibility checklist filled
- [ ] Visual review (screenshots or Percy if used)
- [ ] Documentation updated (.claude/docs/COMPONENT-LIBRARY.md)

Common pitfalls
- Hard-coded colors/spacings
- Missing aria-labels on icon-only controls
- Forgetting to trap focus in modals

Useful commands
- Start storybook: npm run storybook
- Run axe against storybook: npx @axe-core/cli "http://localhost:6006"
- Run pa11y: npx pa11y http://localhost:6006/iframe.html?id=components-button--primary

Links
- Design System: .claude/DESIGN-SYSTEM.md
- Component Library: .claude/docs/COMPONENT-LIBRARY.md
- Accessibility guide: .claude/docs/ACCESSIBILITY-GUIDE.md

Maintainers: UI/UX team
Last updated: 2026-02-19
