import { test as base, expect, type Page } from "@playwright/test";

/**
 * Issue #250 — Research Workspace Playwright route smoke.
 *
 * Runs against scripts/paper-api-stub.mjs research fixtures (empty/synthetic
 * only — no private Strategy V1 economics). Covers shell navigation and
 * empty/ready states for core Research routes; does NOT start real Lab jobs
 * (write path requires a live research API + clean git + local_lab catalog).
 */

const AUTH_USERNAME = "monitor";
const AUTH_PASSWORD = "testpass123";

async function login(page: Page) {
  await page.goto("/login");
  await page.getByLabel("Username").fill(AUTH_USERNAME);
  await page.getByLabel("Password").fill(AUTH_PASSWORD);
  await page.getByRole("button", { name: /sign in/i }).click();
  await page.waitForURL(/\/dashboard/, { timeout: 20_000 });
}

const test = base.extend({});

test("research workspace core routes render (empty/ready fixtures)", async ({
  page,
}) => {
  await login(page);

  // Monitor regression: paper dashboard still loads after research stub routes.
  await page.goto("/dashboard");
  await expect(page.getByTestId("dashboard-page-ready")).toBeVisible({
    timeout: 20_000,
  });

  await page.goto("/dashboard/research");
  await expect(page.getByTestId("research-overview-empty")).toBeVisible({
    timeout: 20_000,
  });
  await expect(page.getByTestId("new-experiment-button")).toBeVisible();
  await expect(page.getByText(/CLI-only/i)).toHaveCount(0);

  await page.goto("/dashboard/research/strategies");
  await expect(page.getByTestId("research-strategies-ready")).toBeVisible();
  await expect(page.getByTestId("strategy-card-trend_v1")).toBeVisible();

  await page.goto("/dashboard/research/strategies/trend_v1");
  await expect(page.getByTestId("research-strategy-detail")).toBeVisible();
  await expect(page.getByTestId("strategy-canonical-id")).toHaveText("trend_v1");
  await expect(page.getByTestId("scorecard-bind-empty")).toBeVisible();

  await page.goto("/dashboard/research/experiments");
  await expect(page.getByTestId("research-experiments-empty")).toBeVisible();

  await page.goto("/dashboard/research/experiments/new");
  await expect(page.getByTestId("research-lab-ready")).toBeVisible();
  await expect(page.getByTestId("lab-strategy")).toBeVisible();
  await expect(page.getByTestId("lab-dataset")).toBeVisible();
  await expect(page.getByTestId("lab-review")).toBeVisible();

  await page.goto("/dashboard/research/compare");
  await expect(page.getByTestId("research-compare-ready")).toBeVisible();
  await expect(page.getByTestId("research-compare-empty")).toBeVisible();

  await page.goto("/dashboard/research/robustness");
  await expect(page.getByTestId("robustness-page-ready")).toBeVisible();
  await expect(page.getByTestId("robustness-list-empty")).toBeVisible();

  await page.goto("/dashboard/research/validation");
  await expect(page.getByTestId("validation-page-ready")).toBeVisible();
  await expect(page.getByTestId("validation-list-empty")).toBeVisible();

  // Workspace switch back to Monitor must remain functional.
  await page.goto("/dashboard");
  await expect(page.getByTestId("dashboard-page-ready")).toBeVisible();
});
