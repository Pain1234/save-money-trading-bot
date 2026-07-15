import { test, expect, type Browser, type Page } from "@playwright/test";
import * as fs from "node:fs";
import * as path from "node:path";

/**
 * Layer A — Browser / visible content timings (Issue #101).
 *
 * Requires:
 *   PAPER_DASHBOARD_BASE_URL, PAPER_DASHBOARD_USER, PAPER_DASHBOARD_PASSWORD
 *
 * Soft gate: writes JSON artifact; does not fail on latency budgets.
 */

const requiredEnv = [
  "PAPER_DASHBOARD_BASE_URL",
  "PAPER_DASHBOARD_USER",
  "PAPER_DASHBOARD_PASSWORD",
] as const;

const missingEnv = requiredEnv.filter((key) => !process.env[key]);
const canRun = missingEnv.length === 0;

const routes: ReadonlyArray<{ path: string; heading: RegExp; name: string; navLabel: string }> =
  [
    { name: "overview", path: "/dashboard", heading: /^Overview$/i, navLabel: "Overview" },
    { name: "status", path: "/dashboard/status", heading: /Status/i, navLabel: "Status" },
    {
      name: "positions",
      path: "/dashboard/positions",
      heading: /^Positions/i,
      navLabel: "Positions",
    },
    { name: "orders", path: "/dashboard/orders", heading: /^Orders/i, navLabel: "Orders" },
    { name: "fills", path: "/dashboard/fills", heading: /^Fills/i, navLabel: "Fills" },
    {
      name: "equity",
      path: "/dashboard/equity",
      heading: /^Equity History$/i,
      navLabel: "Equity",
    },
    {
      name: "incidents",
      path: "/dashboard/incidents",
      heading: /Incidents/i,
      navLabel: "Incidents",
    },
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

/** Install LCP observer before navigation (hard navigations only). */
async function installLcpObserver(page: Page): Promise<void> {
  await page.addInitScript(() => {
    const w = window as unknown as { __dashboardLcpMs: number | null };
    w.__dashboardLcpMs = null;
    try {
      const observer = new PerformanceObserver((list) => {
        const entries = list.getEntries();
        const last = entries[entries.length - 1];
        if (last) {
          w.__dashboardLcpMs = last.startTime;
        }
      });
      observer.observe({
        type: "largest-contentful-paint",
        buffered: true,
      } as PerformanceObserverInit);
    } catch {
      /* LCP unsupported in this browser context */
    }
  });
}

async function readLcp(page: Page): Promise<number | null> {
  return page.evaluate(() => {
    const w = window as unknown as { __dashboardLcpMs?: number | null };
    return w.__dashboardLcpMs ?? null;
  });
}

/**
 * Observe skeleton in parallel with heading. Never await the skeleton timeout
 * before recording headingAt (that previously inflated latency by 2.5–3s).
 */
async function measureVisibleContent(
  page: Page,
  route: (typeof routes)[number],
  startNavigation: () => Promise<unknown>,
  mode: RouteTiming["mode"],
): Promise<RouteTiming> {
  const started = Date.now();
  let skeletonAt: number | null = null;

  const skeletonWatch = page
    .waitForSelector('[data-testid="dashboard-skeleton"]', {
      timeout: 5_000,
      state: "attached",
    })
    .then(() => {
      skeletonAt = Date.now() - started;
      return true;
    })
    .catch(() => false);

  const navResult = await startNavigation();
  await expect(page.getByRole("heading", { name: route.heading })).toBeVisible({
    timeout: 20_000,
  });
  const headingAt = Date.now() - started;

  // Collect skeleton if it already fired; do not block on the remaining timeout.
  await Promise.race([
    skeletonWatch,
    new Promise<boolean>((resolve) => setTimeout(() => resolve(false), 50)),
  ]);

  const isHardNav = mode === "cold_goto" || mode === "warm_goto";
  const lcp = isHardNav ? await readLcp(page) : null;
  const ok =
    mode === "soft_nav"
      ? true
      : Boolean(navResult && typeof navResult === "object" && "ok" in navResult
          ? (navResult as { ok: () => boolean }).ok()
          : navResult);

  let note: string;
  if (mode === "soft_nav") {
    note =
      skeletonAt == null
        ? "Soft nav: skeleton not observed; LCP skipped (same document)."
        : "Soft nav: skeleton observed; LCP skipped (same document).";
  } else if (skeletonAt == null) {
    note =
      "Skeleton not observed on hard navigation (common with force-dynamic SSR).";
  } else {
    note = "Skeleton observed during hard navigation.";
  }

  return {
    name: route.name,
    path: route.path,
    mode,
    status: ok ? "MEASURED" : "NOT_MEASURED",
    nav_to_heading_ms: headingAt,
    nav_to_skeleton_ms: skeletonAt,
    skeleton_to_data_ms: skeletonAt != null ? Math.max(0, headingAt - skeletonAt) : null,
    lcp_ms: lcp,
    usable_content_ms: headingAt,
    note,
  };
}

async function measureColdGoto(
  browser: Browser,
  route: (typeof routes)[number],
): Promise<RouteTiming> {
  // Cold: fresh browser context + login (login may warm shared assets;
  // this is not a zero-cache claim — "fresh authenticated context").
  const context = await browser.newContext();
  const page = await context.newPage();
  try {
    await installLcpObserver(page);
    await login(page);
    return await measureVisibleContent(
      page,
      route,
      () => page.goto(route.path, { waitUntil: "domcontentloaded" }),
      "cold_goto",
    );
  } finally {
    await context.close();
  }
}

async function measureWarmGoto(
  page: Page,
  route: (typeof routes)[number],
): Promise<RouteTiming> {
  return measureVisibleContent(
    page,
    route,
    () => page.goto(route.path, { waitUntil: "domcontentloaded" }),
    "warm_goto",
  );
}

async function measureSoftNav(
  page: Page,
  route: (typeof routes)[number],
): Promise<RouteTiming> {
  // Soft Overview: start from Status (never /dashboard → /dashboard).
  const startPath = route.name === "overview" ? "/dashboard/status" : "/dashboard";
  await page.goto(startPath, { waitUntil: "domcontentloaded" });
  await expect(page.getByRole("heading").first()).toBeVisible({ timeout: 20_000 });

  return measureVisibleContent(
    page,
    route,
    async () => {
      await page.getByRole("link", { name: route.navLabel, exact: true }).first().click();
      return true;
    },
    "soft_nav",
  );
}

test.describe("Issue #101 Layer A browser timings", () => {
  test.skip(!canRun, `Set ${requiredEnv.join(", ")} to run Layer A timings`);

  test("measure cold/warm/soft navigation to visible content", async ({ browser }) => {
    const timings: RouteTiming[] = [];

    // Warm context: login once, reuse for warm_goto + soft_nav.
    const warmContext = await browser.newContext();
    const warmPage = await warmContext.newPage();
    await installLcpObserver(warmPage);
    await login(warmPage);

    for (const route of routes) {
      timings.push(await measureColdGoto(browser, route));
      timings.push(await measureWarmGoto(warmPage, route));
      timings.push(await measureSoftNav(warmPage, route));
    }

    await warmContext.close();

    const outDir = path.join(process.cwd(), "docs", "operations");
    fs.mkdirSync(outDir, { recursive: true });
    const artifact = {
      measurement: "layer_a_browser_visible_content",
      issue: 101,
      status: timings.some((t) => t.status === "MEASURED") ? "MEASURED" : "NOT_MEASURED",
      measured_at: new Date().toISOString(),
      budget_note:
        "ROADMAP 1.5s refers to visible/usable content, not API-only latency.",
      methodology: {
        cold_goto:
          "Fresh authenticated context per route (new browser.newContext() + login). " +
          "Login may warm shared assets; not a zero-HTTP-cache claim.",
        warm_goto: "Same warmed authenticated context, hard navigation.",
        soft_nav:
          "Same warmed context; Overview soft-nav starts from /dashboard/status.",
        skeleton:
          "Observed in parallel with heading; headingAt never waits on skeleton timeout.",
        lcp:
          "PerformanceObserver buffered LCP on hard nav only; soft_nav lcp_ms=null. " +
          "On first Railway run, verify hard-nav LCP is non-null (observer may still " +
          "miss if read before a final candidate).",
      },
      timings,
    };
    const outPath = path.join(outDir, "dashboard-layer-a-browser.json");
    fs.writeFileSync(outPath, `${JSON.stringify(artifact, null, 2)}\n`, "utf-8");
    expect(timings.length).toBe(routes.length * 3);
  });
});
