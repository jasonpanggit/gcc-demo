# UI/UX Testing Suite - EOL Agentic Platform

## Overview

This directory contains comprehensive UI/UX testing infrastructure for the EOL Agentic Platform, validating all improvements implemented in Tasks #1-9 of the UI/UX revamp.

## Test Coverage

### 1. **Lighthouse CI** (`lighthouse.config.js`)
- Performance audits (target: 90+/100)
- Accessibility audits (target: 100/100)
- Best practices validation
- SEO optimization checks
- Core Web Vitals monitoring

### 2. **Accessibility Testing** (`accessibility-checklist.md`)
- WCAG 2.1 AA compliance
- Keyboard navigation (Tab order, focus management)
- Screen reader compatibility (NVDA, VoiceOver)
- Color contrast validation (4.5:1 for text, 3:1 for UI)
- Semantic HTML structure
- ARIA attributes validation

### 3. **Cross-Browser Testing** (`cross-browser-tests.md`)
- Chrome (latest)
- Firefox (latest)
- Safari (latest)
- Edge (latest)
- Mobile browsers (iOS Safari, Chrome Mobile)
- Responsive design validation

### 4. **Performance Benchmarks** (`performance-benchmarks.md`)
- Page load times (target: < 2s desktop, < 3s mobile)
- Bundle sizes (JS < 500KB, CSS < 100KB)
- Core Web Vitals (LCP < 2.5s, FID < 100ms, CLS < 0.1)
- API response times
- Resource optimization

## Quick Start

### Prerequisites

1. **Node.js 18+** - For Lighthouse and testing tools
   ```bash
   node --version  # Should be v18.x or higher
   ```

2. **Python 3.11+** - For Flask application
   ```bash
   python3 --version  # Should be 3.11 or higher
   ```

3. **Running Application** - Flask app must be running on `http://localhost:5000`
   ```bash
   cd app/agentic/eol
   python3 main.py
   ```

### Running All Tests

```bash
cd app/agentic/eol/tests/ui
./run-ui-tests.sh --all
```

### Running Specific Test Suites

```bash
# Lighthouse audits only
./run-ui-tests.sh --lighthouse

# Accessibility tests only
./run-ui-tests.sh --a11y

# Performance benchmarks only
./run-ui-tests.sh --performance

# CI mode (exit on first failure)
./run-ui-tests.sh --all --ci
```

## Test Files

### Configuration Files

#### `lighthouse.config.js`
Lighthouse CI configuration for automated audits.

**Usage:**
```bash
npx @lhci/cli@0.13.x autorun --config=lighthouse.config.js
```

**Features:**
- Tests 7 key pages (home, agents, inventory, EOL, cache, Azure MCP, Azure AI SRE)
- 3 runs per page (median scores used)
- Desktop preset (1350x940 viewport)
- Performance budget enforcement
- Accessibility assertions (100/100 required)

**Success Criteria:**
- Performance: 90+/100
- Accessibility: 100/100
- Best Practices: 90+/100
- SEO: 90+/100

---

### Manual Testing Checklists

#### `accessibility-checklist.md`
Comprehensive manual accessibility testing checklist.

**Sections:**
1. Keyboard Navigation (Tab order, focus indicators, shortcuts)
2. Screen Reader Testing (NVDA, VoiceOver instructions)
3. Color & Contrast (4.5:1 text, 3:1 UI components)
4. Responsive & Mobile (375px, 768px, 1024px+ viewports)
5. Semantic HTML & ARIA (Landmarks, roles, attributes)
6. Forms Accessibility (Labels, validation, error messages)
7. Interactive Components (Buttons, links, modals, tabs)
8. Images & Media (Alt text, decorative vs. informative)
9. Data Tables (Headers, captions, scope attributes)
10. Page-Level Testing (Document structure, heading hierarchy)

**How to Use:**
1. Print or open checklist
2. Test each item systematically
3. Check boxes as you validate
4. Record issues in Notes section
5. Sign off when complete

---

#### `cross-browser-tests.md`
Browser compatibility testing matrix.

**Browsers Tested:**
- **Tier 1:** Chrome, Firefox, Safari, Edge (latest versions)
- **Tier 2:** Previous major versions, Samsung Internet
- **Mobile:** iOS Safari, Chrome Mobile, Samsung Internet

**Test Categories:**
1. Layout & Responsive Design
2. CSS & Styling (Custom properties, Flexbox, Grid)
3. JavaScript Functionality (ES6+, AJAX, events)
4. Forms & Input (HTML5 types, validation)
5. Accessibility Features
6. Performance (Load times, bundle sizes)
7. Page-by-Page Testing (All 7 pages)

**How to Use:**
1. Open page in target browser
2. Test each category systematically
3. Check boxes in matrix
4. Document browser-specific issues
5. Test workarounds/fallbacks

---

#### `performance-benchmarks.md`
Performance baseline documentation.

**Metrics Tracked:**
- **Core Web Vitals:** LCP, FID, CLS, INP, TTFB, FCP
- **Lighthouse Scores:** Performance, Accessibility, Best Practices, SEO
- **Page-Specific:** Load times, resource sizes, API response times
- **Bundle Analysis:** JS/CSS sizes, code splitting, compression
- **Network:** HTTP/2, caching, compression ratios

**Pages Benchmarked:**
1. Home (/) - Target: < 2.0s load time
2. Agents (/agents) - Target: < 2.5s load time
3. Inventory (/inventory) - Target: < 3.0s load time
4. EOL Management (/eol) - Target: < 2.5s load time
5. Cache (/cache) - Target: < 2.0s load time
6. Azure MCP (/azure-mcp) - Target: < 3.5s load time
7. Azure AI SRE (/azure-ai-sre) - Target: < 3.5s load time

**How to Use:**
1. Run baseline tests before changes
2. Record metrics in "Current" column
3. Make performance optimizations
4. Re-run tests and compare
5. Track improvements over time

---

### Automation Scripts

#### `run-ui-tests.sh`
Master test runner script.

**Features:**
- Auto-starts Flask app if not running
- Runs Lighthouse CI audits
- Runs axe-core accessibility tests
- Runs performance benchmarks
- Generates HTML reports
- Cleanup and summary

**Options:**
```bash
--lighthouse    # Run Lighthouse CI audits only
--a11y          # Run accessibility tests only
--performance   # Run performance benchmarks only
--all           # Run all tests (default)
--ci            # CI mode (non-interactive, exit on failure)
--help          # Show help message
```

**Output:**
- Console summary with color-coded results
- HTML reports (Lighthouse, axe)
- JSON data files (performance metrics)
- Exit code 0 (success) or 1 (failure)

---

## CI/CD Integration

### GitHub Actions Workflow (`.github/workflows/ui-tests.yml`)

**Triggers:**
- Push to `main` or `develop` branches
- Pull requests to `main` or `develop`
- Manual workflow dispatch
- Only runs when UI files change

**Jobs:**

1. **lighthouse-ci**
   - Runs Lighthouse audits on all pages
   - Uploads reports as artifacts
   - Fails if scores below thresholds

2. **accessibility-tests**
   - Runs axe-core on all pages
   - Uploads violation reports
   - Fails if any violations found

3. **performance-benchmarks**
   - Runs Lighthouse performance tests
   - Extracts Core Web Vitals
   - Fails if performance < 90/100

4. **test-summary**
   - Aggregates all test results
   - Posts comment on PR (if applicable)
   - Final pass/fail status

**Artifacts:**
- Lighthouse reports (HTML + JSON)
- axe accessibility reports (JSON)
- Performance benchmark data (JSON)
- Retention: 30 days

**Example PR Comment:**
```
## UI/UX Test Results

| Test Suite | Status |
|------------|--------|
| Lighthouse CI | ✅ success |
| Accessibility Tests | ✅ success |
| Performance Benchmarks | ✅ success |

✅ All UI/UX tests passed!
```

---

## Manual Testing Tools

### Browser Developer Tools

#### Chrome DevTools
```bash
# Open DevTools
Cmd+Option+I (macOS) / Ctrl+Shift+I (Windows)

# Lighthouse
DevTools > Lighthouse tab > Generate report

# Accessibility Tree
DevTools > Elements > Accessibility panel

# Performance Recording
DevTools > Performance > Record
```

#### Firefox DevTools
```bash
# Open DevTools
Cmd+Option+I (macOS) / Ctrl+Shift+I (Windows)

# Accessibility Inspector
DevTools > Accessibility tab

# Responsive Design Mode
Cmd+Option+M (macOS) / Ctrl+Shift+M (Windows)
```

#### Safari Web Inspector
```bash
# Enable Develop menu
Safari > Preferences > Advanced > Show Develop menu

# Open Inspector
Cmd+Option+I

# Responsive Design Mode
Develop > Enter Responsive Design Mode
```

---

### Browser Extensions

#### Accessibility Testing

**axe DevTools** (Free)
- https://www.deque.com/axe/devtools/
- Install: Chrome, Firefox, Edge
- Features: Automated scans, guided tests, intelligent guided testing

**WAVE** (Free)
- https://wave.webaim.org/extension/
- Install: Chrome, Firefox, Edge
- Features: Visual feedback, color contrast, ARIA validation

**Accessibility Insights for Web** (Free, Microsoft)
- https://accessibilityinsights.io/
- Install: Chrome, Edge
- Features: FastPass, Assessment, Ad hoc tools

#### Performance Testing

**Lighthouse** (Built into Chrome)
- DevTools > Lighthouse tab
- Features: Performance, A11y, Best Practices, SEO

**Web Vitals** (Free, Google)
- https://chrome.google.com/webstore/detail/web-vitals/ahfhijdlegdabablpippeagghigmibma
- Install: Chrome, Edge
- Features: Real-time Core Web Vitals in toolbar

---

### Screen Readers

#### NVDA (Windows - Free)
- **Download:** https://www.nvaccess.org/download/
- **Start:** NVDA+Ctrl (default: Insert+Ctrl)
- **Browse Mode:** Arrow keys to navigate
- **Forms Mode:** Auto-switches on form fields
- **Headings:** Press H to jump between headings
- **Landmarks:** Press D to jump between landmarks
- **Elements List:** NVDA+F7 (links, headings, form fields)

**Testing Steps:**
1. Install NVDA
2. Start NVDA (NVDA+Ctrl)
3. Open application in browser
4. Navigate using arrow keys
5. Verify all content is announced
6. Test interactive elements (Tab, Enter, Space)
7. Check forms (labels, errors, required fields)

#### VoiceOver (macOS - Built-in)
- **Start:** Cmd+F5
- **VO Keys:** Control+Option (VO)
- **Web Rotor:** VO+U (lists headings, links, landmarks)
- **Next Item:** VO+Right Arrow
- **Previous Item:** VO+Left Arrow
- **Enter Container:** VO+Shift+Down Arrow
- **Exit Container:** VO+Shift+Up Arrow

**Testing Steps:**
1. Enable VoiceOver (Cmd+F5)
2. Open application in Safari
3. Use VO+U to open Web Rotor
4. Navigate by headings, links, landmarks
5. Verify all content is announced
6. Test interactive elements
7. Check forms and error messages

#### JAWS (Windows - Paid)
- **Download:** https://www.freedomscientific.com/products/software/jaws/
- **Start:** JAWS automatically starts if installed
- **Similar to NVDA** in most navigation

---

## Performance Testing Tools

### Lighthouse CLI
```bash
# Install globally
npm install -g lighthouse

# Run audit
lighthouse https://localhost:5000 \
  --view \
  --output=html \
  --output-path=./report.html

# Performance only
lighthouse https://localhost:5000 \
  --only-categories=performance \
  --output=json
```

### WebPageTest
- **Website:** https://www.webpagetest.org/
- **Features:** Real device testing, filmstrip view, waterfall charts
- **CLI:**
  ```bash
  npx webpagetest test https://your-app.com \
    --location=Dulles:Chrome \
    --connectivity=4G
  ```

### Chrome DevTools Performance
1. Open DevTools (Cmd+Option+I)
2. Go to Performance tab
3. Click Record (or Cmd+E)
4. Interact with page
5. Stop recording
6. Analyze: FPS, CPU, network, layout

---

## Accessibility Testing with axe-core CLI

### Installation
```bash
npm install -g @axe-core/cli
```

### Usage
```bash
# Test single page
axe http://localhost:5000 --exit

# Test with custom rules
axe http://localhost:5000 \
  --rules=color-contrast,html-has-lang,label \
  --exit

# Generate JSON report
axe http://localhost:5000 \
  --exit \
  --save axe-report.json

# Test all pages
for page in "/" "/agents" "/inventory" "/eol"; do
  axe "http://localhost:5000$page" --exit
done
```

---

## Success Criteria

### Lighthouse Scores
- ✅ **Performance:** 90+/100
- ✅ **Accessibility:** 100/100
- ✅ **Best Practices:** 90+/100
- ✅ **SEO:** 90+/100

### Core Web Vitals
- ✅ **LCP (Largest Contentful Paint):** < 2.5s
- ✅ **FID (First Input Delay):** < 100ms
- ✅ **CLS (Cumulative Layout Shift):** < 0.1
- ✅ **INP (Interaction to Next Paint):** < 200ms
- ✅ **TTFB (Time to First Byte):** < 600ms
- ✅ **FCP (First Contentful Paint):** < 1.8s

### Accessibility
- ✅ **WCAG 2.1 AA:** No violations
- ✅ **Keyboard Navigation:** All functionality accessible
- ✅ **Screen Readers:** All content announced correctly
- ✅ **Color Contrast:** 4.5:1 (text), 3:1 (UI)
- ✅ **Focus Indicators:** Visible on all interactive elements
- ✅ **Semantic HTML:** Proper landmarks, headings, ARIA

### Performance
- ✅ **Page Load Time:** < 2s (desktop), < 3s (mobile)
- ✅ **JavaScript Bundle:** < 500 KB (gzipped)
- ✅ **CSS Bundle:** < 100 KB (gzipped)
- ✅ **Total Page Weight:** < 1 MB
- ✅ **API Response Time:** < 300ms (P95)
- ✅ **Scroll Performance:** 60 FPS

### Cross-Browser
- ✅ **Chrome (latest):** Full functionality
- ✅ **Firefox (latest):** Full functionality
- ✅ **Safari (latest):** Full functionality
- ✅ **Edge (latest):** Full functionality
- ✅ **Mobile Browsers:** Touch targets 44x44px, no horizontal scroll

---

## Troubleshooting

### Lighthouse CI Fails to Start

**Problem:** Lighthouse can't connect to server

**Solution:**
```bash
# Check if server is running
curl http://localhost:5000

# Start server manually
cd app/agentic/eol
python3 main.py

# Check port 5000 is not in use
lsof -i :5000
```

### axe-core CLI Not Found

**Problem:** `axe: command not found`

**Solution:**
```bash
# Install globally
npm install -g @axe-core/cli

# Or use npx
npx @axe-core/cli http://localhost:5000
```

### Chrome Headless Issues

**Problem:** Lighthouse fails in headless mode

**Solution:**
```bash
# Add Chrome flags to Lighthouse config
--chrome-flags="--headless --no-sandbox --disable-dev-shm-usage"
```

### Performance Scores Vary

**Problem:** Lighthouse scores inconsistent between runs

**Solution:**
- Lighthouse runs 3 times by default (median used)
- Close other applications
- Disable browser extensions
- Use incognito/private mode
- Run on stable network
- Use CI environment for consistency

---

## Additional Resources

### Documentation
- **Lighthouse:** https://developer.chrome.com/docs/lighthouse/
- **axe-core:** https://github.com/dequelabs/axe-core
- **WCAG 2.1:** https://www.w3.org/WAI/WCAG21/quickref/
- **Web Vitals:** https://web.dev/vitals/
- **MDN Accessibility:** https://developer.mozilla.org/en-US/docs/Web/Accessibility

### Testing Guides
- **WebAIM:** https://webaim.org/
- **A11y Project:** https://www.a11yproject.com/
- **Google Web Fundamentals:** https://developers.google.com/web/fundamentals

### Tools
- **Color Contrast Checker:** https://webaim.org/resources/contrastchecker/
- **WAVE:** https://wave.webaim.org/
- **Lighthouse:** https://developers.google.com/web/tools/lighthouse
- **WebPageTest:** https://www.webpagetest.org/
- **Can I Use:** https://caniuse.com/

---

## Maintenance

### Regular Testing Schedule

**Daily (Automated - CI/CD):**
- Lighthouse CI on every PR
- Accessibility tests on every PR
- Performance benchmarks on every PR

**Weekly (Manual):**
- Full accessibility checklist on one page
- Cross-browser testing on new features
- Performance monitoring (trends)

**Monthly (Manual):**
- Full accessibility checklist on all pages
- Cross-browser testing on all browsers
- Performance benchmark review
- Update success criteria if needed

**Quarterly:**
- Review and update test configurations
- Update browser support matrix
- Review WCAG guidelines for updates
- Audit and optimize performance budgets

---

## Contact & Support

For questions or issues with UI/UX testing:

1. **Review this README** first
2. **Check troubleshooting section** above
3. **Consult accessibility checklist** for manual testing guidance
4. **Review CI/CD logs** for automated test failures
5. **Open an issue** with test results attached

---

**Last Updated:** 2026-02-19
**Version:** 1.0
**Maintained by:** EOL Platform Team
