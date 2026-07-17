import { test as base, expect, type Page, type APIRequestContext } from "@playwright/test";
import path from "path";

const AUTH_USERNAME = "monitor";
const AUTH_PASSWORD = "testpass123";
const STUB_URL = process.env.PAPER_API_STUB_URL ?? "http://127.0.0.1:18080";

async function setStubScenario(
  request: APIRequestContext,
  scenario: "default" | "empty" | "stale" | "summary_error" | "section_error",
) {
  const response = await request.post(`${STUB_URL}/__test/scenario`, {
    data: { scenario },
  });
  expect(response.ok()).toBeTruthy();
}

async function login(page: Page) {
  await page.goto("/login");
  await page.getByLabel("Username").fill(AUTH_USERNAME);
  await page.getByLabel("Password").fill(AUTH_PASSWORD);
  await page.getByRole("button", { name: /sign in/i }).click();
  await page.waitForURL(/\/dashboard/, { timeout: 20_000 });
}

const test = base.extend({});

test.beforeEach(async ({ request }) => {
  await setStubScenario(request, "default");
});

const VIEWPORTS = [
  { name: "2048x1152", width: 2048, height: 1152 },
  { name: "1920x1080", width: 1920, height: 1080 },
  { name: "1707x960", width: 1707, height: 960 },
] as const;

const SCREENSHOT_DIR = path.join(process.cwd(), "docs", "visual-regression");

for (const viewport of VIEWPORTS) {
  test(`dashboard reference screenshot @ ${viewport.name}`, async ({
    page,
  }) => {
    await page.setViewportSize({
      width: viewport.width,
      height: viewport.height,
    });

    await login(page);
    await expect(page.getByTestId("dashboard-page-ready")).toBeVisible({
      timeout: 20_000,
    });
    await page.waitForSelector(".chart-panel", { state: "visible" });
    await page.waitForTimeout(800);

    const overflow = await page.evaluate(() => ({
      scrollWidth: document.documentElement.scrollWidth,
      innerWidth: window.innerWidth,
    }));

    expect(overflow.scrollWidth).toBeLessThanOrEqual(overflow.innerWidth);

    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, `dashboard-${viewport.name}.png`),
      fullPage: true,
      animations: "disabled",
    });
  });
}

test("dashboard design elements and read-only controls", async ({ page }) => {
  await login(page);
  await expect(page.getByTestId("dashboard-page-ready")).toBeVisible();
  await expect(page.getByTestId("dashboard-navbar")).toBeVisible();
  await expect(page.getByTestId("dashboard-sidebar")).toBeVisible();
  await expect(page.getByTestId("kpi-grid")).toBeVisible();
  await expect(page.getByTestId("dashboard-main")).toBeVisible();
  await expect(page.getByTestId("session-username")).toHaveText(AUTH_USERNAME);

  await expect(page.getByTestId("bot-start-button")).toBeDisabled();
  await expect(page.getByTestId("bot-pause-button")).toBeDisabled();
  await expect(page.getByTestId("bot-stop-button")).toBeDisabled();
  await expect(page.getByTestId("readonly-banner").first()).toBeVisible();

  await expect(page.getByTestId("positions-table")).toBeVisible();
  await expect(page.getByTestId("fills-table")).toBeVisible();
});

test("logout remains functional", async ({ page }) => {
  await login(page);
  await page.getByRole("button", { name: /logout/i }).click();
  await page.waitForURL(/\/login/, { timeout: 15_000 });
  await page.goto("/dashboard");
  await page.waitForURL(/\/login/, { timeout: 15_000 });
});

test("stale heartbeat remains visible without blanking shell", async ({
  page,
  request,
}) => {
  await setStubScenario(request, "stale");
  await login(page);
  await expect(page.getByTestId("dashboard-navbar")).toBeVisible();
  await expect(page.getByTestId("dashboard-page-ready")).toBeVisible();
  await expect(page.getByTestId("dashboard-warnings")).toBeVisible();
  await expect(page.getByTestId("dashboard-warnings")).toContainText(
    /veraltet|stale/i,
  );
  await expect(page.getByTestId("kpi-grid")).toBeVisible();
});

test("summary API error keeps auth shell and shows error panel", async ({
  page,
  request,
}) => {
  await setStubScenario(request, "summary_error");
  await login(page);
  await expect(page.getByTestId("dashboard-navbar")).toBeVisible();
  await expect(page.getByTestId("dashboard-sidebar")).toBeVisible();
  await expect(page.getByTestId("dashboard-error-panel")).toBeVisible();
  await expect(page.getByTestId("dashboard-page-ready")).toHaveCount(0);
});

test("section endpoint failures keep core KPIs and mark sections unavailable", async ({
  page,
  request,
}) => {
  await setStubScenario(request, "section_error");
  await login(page);
  await expect(page.getByTestId("dashboard-page-ready")).toBeVisible();
  await expect(page.getByTestId("kpi-grid")).toBeVisible();
  await expect(page.getByTestId("fills-table").getByTestId("table-error")).toBeVisible();
  await expect(
    page.getByTestId("positions-table").getByTestId("table-error"),
  ).toBeVisible();
  await expect(page.getByTestId("equity-error")).toBeVisible();
  await expect(page.getByTestId("status-card-scheduler")).toContainText(
    /Nicht verfügbar/i,
  );
  await expect(page.getByTestId("status-card-incidents")).toContainText(
    /Nicht verfügbar/i,
  );
});

test("empty equity positions and fills show empty states without blanking core", async ({
  page,
  request,
}) => {
  await setStubScenario(request, "empty");
  await login(page);
  await expect(page.getByTestId("dashboard-page-ready")).toBeVisible();
  await expect(page.getByTestId("kpi-grid")).toBeVisible();
  await expect(page.getByTestId("equity-empty")).toBeVisible();
  await expect(
    page.getByTestId("positions-table").getByTestId("table-empty"),
  ).toBeVisible();
  await expect(
    page.getByTestId("fills-table").getByTestId("table-empty"),
  ).toBeVisible();
});
