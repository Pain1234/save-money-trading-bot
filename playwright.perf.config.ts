import { defineConfig, devices } from "@playwright/test";

/**
 * Dashboard route smoke for Issue #102 (P2.5).
 * Requires a running dashboard + credentials:
 *   PAPER_DASHBOARD_BASE_URL, PAPER_DASHBOARD_USER, PAPER_DASHBOARD_PASSWORD
 *
 * Usage:
 *   npx playwright test -c playwright.perf.config.ts
 */
const baseURL = process.env.PAPER_DASHBOARD_BASE_URL?.replace(/\/$/, "");

export default defineConfig({
  testDir: "./tests/e2e",
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
