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

const routes: ReadonlyArray<{ path: string; heading: RegExp }> = [
  { path: "/dashboard", heading: /Paper Trading Monitor/i },
  { path: "/dashboard/positions", heading: /^Positions$/i },
  { path: "/dashboard/fills", heading: /^Fills$/i },
  { path: "/dashboard/equity", heading: /^Equity History$/i },
];

test("login and navigate core dashboard routes", async ({ page }) => {
  const user = process.env.PAPER_DASHBOARD_USER!;
  const password = process.env.PAPER_DASHBOARD_PASSWORD!;

  const loginResponse = await page.goto("/login");
  expect(loginResponse, "login navigation should return a response").not.toBeNull();
  expect(loginResponse!.ok(), `login HTTP ${loginResponse!.status()}`).toBeTruthy();

  await page.getByLabel("Username").fill(user);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: /sign in/i }).click();
  await page.waitForURL(/\/dashboard/, { timeout: 20_000 });

  for (const { path, heading } of routes) {
    const response = await page.goto(path);
    expect(response, `${path} should return a response`).not.toBeNull();
    expect(response!.ok(), `${path} HTTP ${response!.status()}`).toBeTruthy();
    await expect(page).not.toHaveURL(/\/login/);
    if (path === "/dashboard") {
      await expect(page.getByTestId("dashboard-page-ready")).toBeVisible();
      await expect(page.getByRole("heading", { name: heading })).toBeVisible();
    } else {
      await expect(page.getByRole("heading", { name: heading })).toBeVisible();
    }
  }
});
