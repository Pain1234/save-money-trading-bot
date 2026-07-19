import { test as base, expect, type Page } from "@playwright/test";
import path from "path";

/**
 * Issue #358 — Research Overview pinned scorecard visual fixtures.
 * Synthetic / public-core only. No private P5 metrics.
 */

const AUTH_USERNAME = "monitor";
const AUTH_PASSWORD = "testpass123";
const SCREENSHOT_DIR = path.join(process.cwd(), "docs", "visual-regression");

async function login(page: Page) {
  await page.goto("/login");
  await page.getByLabel("Username").fill(AUTH_USERNAME);
  await page.getByLabel("Password").fill(AUTH_PASSWORD);
  await page.getByRole("button", { name: /sign in/i }).click();
  await page.waitForURL(/\/dashboard/, { timeout: 20_000 });
}

const test = base.extend({});

const SCENARIOS = ["ready", "legacy", "invalidated"] as const;
const VIEWPORTS = [
  { name: "1920x1080", width: 1920, height: 1080 },
  { name: "1440x900", width: 1440, height: 900 },
  { name: "mobile", width: 390, height: 844 },
] as const;

for (const scenario of SCENARIOS) {
  for (const vp of VIEWPORTS) {
    test(`overview scorecard ${scenario} @ ${vp.name}`, async ({ page }) => {
      await page.setViewportSize({ width: vp.width, height: vp.height });
      await login(page);
      await page.goto(
        `/dashboard/research/visual-fixtures?scenario=${scenario}`,
      );
      await expect(page.getByTestId("research-overview-visual-fixture")).toBeVisible({
        timeout: 20_000,
      });
      await expect(page.getByTestId("research-overview-visual-fixture")).toHaveAttribute(
        "data-scenario",
        scenario,
      );
      await page.waitForTimeout(300);
      await page.screenshot({
        path: path.join(
          SCREENSHOT_DIR,
          `research-overview-${scenario}-${vp.name}.png`,
        ),
        fullPage: true,
        animations: "disabled",
      });
    });
  }
}
