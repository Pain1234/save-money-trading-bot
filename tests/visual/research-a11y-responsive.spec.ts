import { test as base, expect, type Page } from "@playwright/test";
import path from "path";

/**
 * Issue #303 — Research Workspace responsive / a11y / visual acceptance.
 *
 * Stub fixtures only. Does not invent scorecard metrics. Monitor path must
 * remain reachable via workspace switch.
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

const BREAKPOINTS = [
  { name: "mobile", width: 390, height: 844 },
  { name: "tablet", width: 768, height: 1024 },
  { name: "laptop", width: 1280, height: 800 },
  { name: "desktop", width: 1440, height: 900 },
] as const;

test("research landmarks and skip link (desktop)", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await login(page);
  await page.goto("/dashboard/research");
  await expect(page.getByTestId("research-shell")).toBeVisible({
    timeout: 20_000,
  });

  await expect(page.getByRole("banner")).toBeVisible();
  await expect(page.getByRole("navigation", { name: "Workspace" })).toBeVisible();
  await expect(page.getByRole("navigation", { name: "Research" })).toBeVisible();
  await expect(page.getByRole("main", { name: "Research content" })).toBeVisible();
  await expect(page.getByRole("contentinfo")).toBeVisible();
  await expect(
    page.getByRole("region", { name: "Research instrument universe" }),
  ).toBeVisible();

  const skip = page.getByTestId("research-skip-link");
  await skip.focus();
  await expect(skip).toBeFocused();
  // Activate like a keyboard user (Enter) after Tab-focus.
  await skip.press("Enter");
  await expect(page.getByTestId("research-main")).toBeFocused();
});

test("research mobile nav toggle and Escape close", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await login(page);
  await page.goto("/dashboard/research");
  await expect(page.getByTestId("research-shell")).toBeVisible({
    timeout: 20_000,
  });

  await expect(page.getByTestId("research-sidebar")).toBeHidden();
  const toggle = page.getByTestId("research-nav-toggle");
  await expect(toggle).toBeVisible();
  await expect(toggle).toHaveAttribute("aria-expanded", "false");

  await toggle.click();
  await expect(toggle).toHaveAttribute("aria-expanded", "true");
  await expect(page.getByTestId("research-nav-mobile-overview")).toBeVisible();

  await page.keyboard.press("Escape");
  await expect(toggle).toHaveAttribute("aria-expanded", "false");
});

test("research keyboard path: workspace switch to Monitor stays green", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await login(page);
  await page.goto("/dashboard/research");
  await expect(page.getByTestId("research-overview-empty")).toBeVisible({
    timeout: 20_000,
  });

  const monitor = page.getByTestId("workspace-monitor");
  await monitor.focus();
  await expect(monitor).toBeFocused();
  await monitor.press("Enter");
  await page.waitForURL(/\/dashboard\/?$/, { timeout: 20_000 });
  await expect(page.getByTestId("dashboard-page-ready")).toBeVisible();
});

for (const bp of BREAKPOINTS) {
  test(`research overview renders @ ${bp.name}`, async ({ page }) => {
    await page.setViewportSize({ width: bp.width, height: bp.height });
    await login(page);
    await page.goto("/dashboard/research");
    await expect(page.getByTestId("research-shell")).toBeVisible({
      timeout: 20_000,
    });
    await expect(page.getByTestId("research-main")).toBeVisible();
    await expect(page.getByTestId("research-overview-empty")).toBeVisible();

    if (bp.width < 1024) {
      await expect(page.getByTestId("research-nav-toggle")).toBeVisible();
      await expect(page.getByTestId("research-sidebar")).toBeHidden();
    } else {
      await expect(page.getByTestId("research-sidebar")).toBeVisible();
    }

    // Horizontal overflow check for shell chrome (tables may scroll internally).
    const shellOverflow = await page.evaluate(() => {
      const shell = document.querySelector('[data-testid="research-shell"]');
      if (!shell) return { ok: false };
      const el = shell as HTMLElement;
      return {
        ok: el.scrollWidth <= el.clientWidth + 2,
        scrollWidth: el.scrollWidth,
        clientWidth: el.clientWidth,
      };
    });
    expect(shellOverflow.ok, JSON.stringify(shellOverflow)).toBe(true);
  });
}

test("research reference screenshots (desktop + mobile)", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await login(page);
  await page.goto("/dashboard/research");
  await expect(page.getByTestId("research-overview-empty")).toBeVisible({
    timeout: 20_000,
  });
  await page.waitForTimeout(400);
  await page.screenshot({
    path: path.join(SCREENSHOT_DIR, "research-shell-desktop.png"),
    fullPage: true,
    animations: "disabled",
  });

  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/dashboard/research");
  await expect(page.getByTestId("research-overview-empty")).toBeVisible({
    timeout: 20_000,
  });
  await page.getByTestId("research-nav-toggle").click();
  await expect(page.getByTestId("research-nav-mobile-overview")).toBeVisible();
  await page.waitForTimeout(200);
  await page.screenshot({
    path: path.join(SCREENSHOT_DIR, "research-shell-mobile.png"),
    fullPage: true,
    animations: "disabled",
  });
});
