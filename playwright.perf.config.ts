import { defineConfig, devices } from "@playwright/test";

/**
 * Dashboard Playwright suite for Issues #102 (route smoke) and #101 (Layer A).
 * Requires a running dashboard + credentials:
 *   PAPER_DASHBOARD_BASE_URL, PAPER_DASHBOARD_USER, PAPER_DASHBOARD_PASSWORD
 *
 * Usage:
 *   npx playwright test -c playwright.perf.config.ts
 *   npm run test:dashboard-perf
 */
const baseURL = process.env.PAPER_DASHBOARD_BASE_URL?.replace(/\/$/, "");

export default defineConfig({
  testDir: "./tests/e2e",
  testMatch: /dashboard-(routes|layer-a-perf)\.spec\.ts/,
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: 0,
  workers: 1,
  reporter: [["list"], ["json", { outputFile: "docs/operations/dashboard-perf-playwright.json" }]],
  use: {
    baseURL: baseURL || "http://127.0.0.1:3000",
    trace: "off",
    screenshot: "only-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
});
