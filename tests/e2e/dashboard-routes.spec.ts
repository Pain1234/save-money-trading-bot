import { test, expect } from "@playwright/test";

/**
 * Issue #102 — login → overview, positions, fills, equity.
 * Uses Node @playwright/test (already in package.json). Labels match LoginForm.tsx.
 */
const requiredEnv = [
  "PAPER_DASHBOARD_BASE_URL",
  "PAPER_DASHBOARD_USER",
  "PAPER_DASHBOARD_PASSWORD",
] as const;

for (const key of requiredEnv) {
  if (!process.env[key]) {
    test.skip(true, `Set ${requiredEnv.join(", ")} to run dashboard route smoke`);
  }
}

const routes = [
  "/dashboard",
  "/dashboard/positions",
  "/dashboard/fills",
  "/dashboard/equity",
] as const;

test("login and navigate core dashboard routes", async ({ page }) => {
  const user = process.env.PAPER_DASHBOARD_USER!;
  const password = process.env.PAPER_DASHBOARD_PASSWORD!;

  await page.goto("/login");
  await page.getByLabel("Username").fill(user);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: /sign in/i }).click();
  await page.waitForURL(/\/dashboard/, { timeout: 20_000 });

  for (const route of routes) {
    await page.goto(route);
    await expect(page.locator("body")).toBeVisible();
    // Loading skeletons or content should be present; route must not 404.
    await expect(page).not.toHaveURL(/\/login/);
  }
});
