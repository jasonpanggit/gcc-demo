/**
 * Lighthouse CI Configuration for EOL Agentic Platform
 *
 * This configuration sets up automated performance, accessibility,
 * best practices, and SEO audits for the UI/UX improvements.
 *
 * Run with: npx @lhci/cli@0.13.x autorun
 */

module.exports = {
  ci: {
    collect: {
      // URLs to test (adjust based on your local/staging environment)
      url: [
        'http://localhost:5000/',
        'http://localhost:5000/agents',
        'http://localhost:5000/inventory',
        'http://localhost:5000/eol',
        'http://localhost:5000/cache',
        'http://localhost:5000/azure-mcp',
        'http://localhost:5000/azure-ai-sre'
      ],
      // Number of runs per URL (median scores used)
      numberOfRuns: 3,
      // Lighthouse settings
      settings: {
        // Use desktop preset for primary testing
        preset: 'desktop',
        // Custom throttling settings
        throttling: {
          rttMs: 40,
          throughputKbps: 10240,
          cpuSlowdownMultiplier: 1
        },
        // Screen emulation
        screenEmulation: {
          mobile: false,
          width: 1350,
          height: 940,
          deviceScaleFactor: 1,
          disabled: false
        },
        // Form factor
        formFactor: 'desktop',
        // Skip certain audits that may not apply
        skipAudits: [
          'canonical',
          'uses-http2'
        ]
      },
      // Chrome flags
      chromeFlags: [
        '--no-sandbox',
        '--disable-dev-shm-usage',
        '--headless'
      ]
    },

    assert: {
      // Performance budgets and assertions
      assertions: {
        // Categories - minimum scores
        'categories:performance': ['error', { minScore: 0.90 }],
        'categories:accessibility': ['error', { minScore: 1.0 }],
        'categories:best-practices': ['error', { minScore: 0.90 }],
        'categories:seo': ['error', { minScore: 0.90 }],

        // Performance metrics - Core Web Vitals
        'first-contentful-paint': ['warn', { maxNumericValue: 2000 }],
        'largest-contentful-paint': ['warn', { maxNumericValue: 2500 }],
        'cumulative-layout-shift': ['warn', { maxNumericValue: 0.1 }],
        'total-blocking-time': ['warn', { maxNumericValue: 300 }],
        'speed-index': ['warn', { maxNumericValue: 3000 }],
        'interactive': ['warn', { maxNumericValue: 3000 }],

        // Resource budgets
        'resource-summary:document:size': ['warn', { maxNumericValue: 50000 }],
        'resource-summary:script:size': ['error', { maxNumericValue: 512000 }],
        'resource-summary:stylesheet:size': ['warn', { maxNumericValue: 100000 }],
        'resource-summary:image:size': ['warn', { maxNumericValue: 200000 }],
        'resource-summary:font:size': ['warn', { maxNumericValue: 100000 }],

        // Accessibility assertions
        'color-contrast': 'error',
        'document-title': 'error',
        'html-has-lang': 'error',
        'meta-description': 'warn',
        'meta-viewport': 'error',
        'aria-allowed-attr': 'error',
        'aria-hidden-focus': 'error',
        'aria-required-attr': 'error',
        'aria-required-children': 'error',
        'aria-required-parent': 'error',
        'aria-roles': 'error',
        'aria-valid-attr': 'error',
        'aria-valid-attr-value': 'error',
        'button-name': 'error',
        'bypass': 'error',
        'duplicate-id-aria': 'error',
        'form-field-multiple-labels': 'warn',
        'frame-title': 'error',
        'heading-order': 'warn',
        'image-alt': 'error',
        'input-image-alt': 'error',
        'label': 'error',
        'link-name': 'error',
        'list': 'error',
        'listitem': 'error',
        'tabindex': 'warn',
        'td-headers-attr': 'error',
        'valid-lang': 'error',

        // Best practices
        'errors-in-console': 'warn',
        'no-vulnerable-libraries': 'error',
        'uses-https': 'warn',
        'is-on-https': 'warn',

        // SEO
        'viewport': 'error',
        'font-size': 'warn',
        'tap-targets': 'warn'
      }
    },

    upload: {
      // Upload results to temporary public storage (optional)
      target: 'temporary-public-storage'
    },

    // Server configuration (if you need to start a server)
    // Uncomment and adjust if needed
    /*
    server: {
      command: 'python main.py',
      port: 5000,
      awaitTimeout: 30000
    },
    */

    // HTML report configuration
    report: {
      reportFilename: 'lighthouse-report.html'
    }
  }
};
