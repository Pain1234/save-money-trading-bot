import { test, expect, type Page } from "@playwright/test";
import * as fs from "node:fs";
import * as path from "node:path";

/**
 * Layer A — Browser / visible content timings (Issue #101).
 *
 * Requires:
 *   PAPER_DASHBOARD_BASE_URL, PAPER_DASHBOARD_USER, PAPER_DASHBOARD_PASSWORD
 *
 * Soft gate: writes JSON artifact; does not fail on latency budgets.
 * Values are only written when credentials and a live dashboard are available.
 */

const requiredEnv = [
  "PAPER_DASHBOARD_BASE_URL",
  "PAPER_DASHBOARD_USER",
  "PAPER_DASHBOARD_PASSWORD",
] as const;

const missingEnv = requiredEnv.filter((key) => !process.env[key]);
const canRun = missingEnv.length === 0;

const routes: ReadonlyArray<{ path: string; heading: RegExp; name: string }> = [
  { name: "overview", path: "/dashboard", heading: /^Overview$/i },
  { name: "status", path: "/dashboard/status", heading: /Status/i },
  { name: "positions", path: "/dashboard/positions", heading: /^Positions/i },
  { name: "orders", path: "/dashboard/orders", heading: /^Orders/i },
  { name: "fills", path: "/dashboard/fills", heading: /^Fills/i },
  { name: "equity", path: "/dashboard/equity", heading: /^Equity History$/i },
  { name: "incidents", path: "/dashboard/incidents", heading: /Incidents/i },
];

type RouteTiming = {
  name: string;
  path: string;
  mode: "cold_goto" | "warm_goto" | "soft_nav";
  status: "MEASURED" | "NOT_MEASURED";
  nav_to_heading_ms: number | null;
  nav_to_skeleton_ms: number | null;
  skeleton_to_data_ms: number | null;
  lcp_ms: number | null;
  usable_content_ms: number | null;
  note: string;
};

async function login(page: Page): Promise<void> {
  const user = process.env.PAPER_DASHBOARD_USER!;
  const password = process.env.PAPER_DASHBOARD_PASSWORD!;
  await page.goto("/login");
  await page.getByLabel("Username").fill(user);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: /sign in/i }).click();
  await page.waitForURL(/\/dashboard/, { timeout: 20_000 });
}

async function readLcp(page: Page): Promise<number | null> {
  return page.evaluate(() => {
    const entries = performance.getEntriesByType("largest-contentful-paint");
    if (!entries.length) return null;
    return entries[entries.length - 1]?.startTime ?? null;
  });
}

async function measureGoto(
  page: Page,
  route: (typeof routes)[number],
  mode: "cold_goto" | "warm_goto",
): Promise<RouteTiming> {
  const started = Date.now();
  let skeletonAt: number | null = null;
  const skeletonWatch = page
    .waitForSelector('[data-testid="dashboard-skeleton"]', { timeout: 2_500 })
    .then(() => {
      skeletonAt = Date.now() - started;
    })
    .catch(() => {
      /* force-dynamic pages often skip loading UI on hard navigation */
    });

  const response = await page.goto(route.path, { waitUntil: "domcontentloaded" });
  await skeletonWatch;
  await expect(page.getByRole("heading", { name: route.heading })).toBeVisible({
    timeout: 20_000,
  });
  const headingAt = Date.now() - started;
  const lcp = await readLcp(page);
  const skeletonToData =
    skeletonAt != null ? Math.max(0, headingAt - skeletonAt) : null;
  return {
    name: route.name,
    path: route.path,
    mode,
    status: response?.ok() ? "MEASURED" : "NOT_MEASURED",
    nav_to_heading_ms: headingAt,
    nav_to_skeleton_ms: skeletonAt,
    skeleton_to_data_ms: skeletonToData,
    lcp_ms: lcp,
    usable_content_ms: headingAt,
    note:
      skeletonAt == null
        ? "Skeleton not observed on hard navigation (common with force-dynamic SSR)."
        : "Skeleton observed during navigation.",
  };
}

async function measureSoftNav(
  page: Page,
  route: (typeof routes)[number],
): Promise<RouteTiming> {
  // Start from overview so soft navigation through the layout <Link> is possible.
  await page.goto("/dashboard", { waitUntil: "networkidle" });
  const label =
    route.name === "overview"
      ? "Overview"
      : route.name === "incidents"
        ? "Incidents"
        : route.name === "equity"
          ? "Equity"
          : route.name.charAt(0).toUpperCase() + route.name.slice(1);

  const started = Date.now();
  let skeletonAt: number | null = null;
  const skeletonWatch = page
    .waitForSelector('[data-testid="dashboard-skeleton"]', { timeout: 3_000 })
    .then(() => {
      skeletonAt = Date.now() - started;
    })
    .catch(() => undefined);

  await page.getByRole("link", { name: label, exact: true }).first().click();
  await skeletonWatch;
  await expect(page.getByRole("heading", { name: route.heading })).toBeVisible({
    timeout: 20_000,
  });
  const headingAt = Date.now() - started;
  const lcp = await readLcp(page);
  return {
    name: route.name,
    path: route.path,
    mode: "soft_nav",
    status: "MEASURED",
    nav_to_heading_ms: headingAt,
    nav_to_skeleton_ms: skeletonAt,
    skeleton_to_data_ms: skeletonAt != null ? Math.max(0, headingAt - skeletonAt) : null,
    lcp_ms: lcp,
    usable_content_ms: headingAt,
    note:
      skeletonAt == null
        ? "Skeleton not observed on soft navigation."
        : "Skeleton observed on soft navigation.",
  };
}

test.describe("Issue #101 Layer A browser timings", () => {
  test.skip(!canRun, `Set ${requiredEnv.join(", ")} to run Layer A timings`);

  test("measure cold/warm/soft navigation to visible content", async ({ page }) => {
    await login(page);
    const timings: RouteTiming[] = [];

    for (const route of routes) {
      timings.push(await measureGoto(page, route, "cold_goto"));
      timings.push(await measureGoto(page, route, "warm_goto"));
      timings.push(await measureSoftNav(page, route));
    }

    const outDir = path.join(process.cwd(), "docs", "operations");
    fs.mkdirSync(outDir, { recursive: true });
    const artifact = {
      measurement: "layer_a_browser_visible_content",
      issue: 101,
      status: timings.some((t) => t.status === "MEASURED") ? "MEASURED" : "NOT_MEASURED",
      measured_at: new Date().toISOString(),
      budget_note:
        "ROADMAP 1.5s refers to visible/usable content, not API-only latency.",
      timings,
    };
    const outPath = path.join(outDir, "dashboard-layer-a-browser.json");
    fs.writeFileSync(outPath, `${JSON.stringify(artifact, null, 2)}\n`, "utf-8");
    expect(timings.length).toBe(routes.length * 3);
  });
});
