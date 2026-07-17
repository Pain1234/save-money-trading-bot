import { test, expect, type Browser, type Page } from "@playwright/test";
import * as fs from "node:fs";
import * as path from "node:path";

/**
 * Layer A — Browser / visible content timings (Issue #101 / follow-up #124).
 *
 * Requires:
 *   PAPER_DASHBOARD_BASE_URL, PAPER_DASHBOARD_USER, PAPER_DASHBOARD_PASSWORD
 *
 * Optional:
 *   LAYER_A_WARM_REPEATS — warm_goto + soft_nav sample count (default 5; p95 needs n>=5)
 *   LAYER_A_COLD_REPEATS — cold_goto sample count (default 1; each cold = fresh login)
 *   LAYER_A_COLD_LOGIN_GAP_MS — pause between cold logins (default 7000; rate limit 10/min)
 *
 * Soft gate: writes JSON artifact; does not fail on latency budgets.
 *
 * Success criterion: exact success heading visible AND no error panel / "unavailable" heading.
 * Prefer data-testid=dashboard-page-ready when the deployed UI includes it.
 */

const requiredEnv = [
  "PAPER_DASHBOARD_BASE_URL",
  "PAPER_DASHBOARD_USER",
  "PAPER_DASHBOARD_PASSWORD",
] as const;

const missingEnv = requiredEnv.filter((key) => !process.env[key]);
const canRun = missingEnv.length === 0;

const warmRepeats = Math.max(1, Number(process.env.LAYER_A_WARM_REPEATS ?? "5") || 5);
const coldRepeats = Math.max(1, Number(process.env.LAYER_A_COLD_REPEATS ?? "1") || 1);
/** Gap between cold logins to stay under dashboard rate limit (10/min/IP). */
const coldLoginGapMs = Math.max(
  0,
  Number(process.env.LAYER_A_COLD_LOGIN_GAP_MS ?? "7000") || 7000,
);

/** Exact success headings — must NOT match ErrorPanel titles like "Positions unavailable". */
const routes: ReadonlyArray<{
  path: string;
  heading: RegExp;
  name: string;
  navLabel: string;
}> = [
  { name: "overview", path: "/dashboard", heading: /^Overview$/i, navLabel: "Overview" },
  {
    name: "status",
    path: "/dashboard/status",
    heading: /^Status & Readiness$/i,
    navLabel: "Status",
  },
  {
    name: "positions",
    path: "/dashboard/positions",
    heading: /^Positions$/i,
    navLabel: "Positions",
  },
  { name: "orders", path: "/dashboard/orders", heading: /^Orders$/i, navLabel: "Orders" },
  { name: "fills", path: "/dashboard/fills", heading: /^Fills$/i, navLabel: "Fills" },
  {
    name: "equity",
    path: "/dashboard/equity",
    heading: /^Equity History$/i,
    navLabel: "Equity",
  },
  {
    name: "incidents",
    path: "/dashboard/incidents",
    heading: /^Errors \/ Incidents$/i,
    navLabel: "Incidents",
  },
];

type RouteTiming = {
  name: string;
  path: string;
  mode: "cold_goto" | "warm_goto" | "soft_nav";
  status: "MEASURED" | "NOT_MEASURED";
  sample_index: number;
  nav_to_heading_ms: number | null;
  nav_to_skeleton_ms: number | null;
  skeleton_to_data_ms: number | null;
  lcp_ms: number | null;
  usable_content_ms: number | null;
  success_marker: "exact_heading" | "page_ready" | null;
  note: string;
};

type ModeSummary = {
  name: string;
  path: string;
  mode: RouteTiming["mode"];
  status: "MEASURED" | "NOT_MEASURED";
  sample_count: number;
  usable_content_p95_ms: number | null;
  usable_content_max_ms: number | null;
  usable_content_samples_ms: number[];
  p95_status: "MEASURED" | "NOT_MEASURED";
  p95_note: string;
};

function percentile(values: number[], pct: number): number {
  if (values.length === 0) return 0;
  const ordered = [...values].sort((a, b) => a - b);
  const index = Math.max(
    0,
    Math.min(ordered.length - 1, Math.round((pct / 100) * (ordered.length - 1))),
  );
  return ordered[index]!;
}

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
 * Wait until the success heading is visible, error UI is absent, and (when
 * deployed) dashboard-page-ready is present.
 */
async function assertSuccessContent(
  page: Page,
  route: (typeof routes)[number],
): Promise<"exact_heading" | "page_ready"> {
  await expect(page.getByRole("heading", { name: route.heading })).toBeVisible({
    timeout: 20_000,
  });
  await expect(page.getByRole("heading", { name: /unavailable/i })).toHaveCount(0);
  await expect(page.getByTestId("dashboard-error-panel")).toHaveCount(0);

  const ready = page.getByTestId("dashboard-page-ready");
  if ((await ready.count()) > 0) {
    await expect(ready).toBeVisible({ timeout: 5_000 });
    return "page_ready";
  }
  return "exact_heading";
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
  sampleIndex: number,
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
  const successMarker = await assertSuccessContent(page, route);
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
      : Boolean(
          navResult && typeof navResult === "object" && "ok" in navResult
            ? (navResult as { ok: () => boolean }).ok()
            : navResult,
        );

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
  note += ` Success via ${successMarker}; error panel / unavailable heading rejected.`;

  return {
    name: route.name,
    path: route.path,
    mode,
    status: ok ? "MEASURED" : "NOT_MEASURED",
    sample_index: sampleIndex,
    nav_to_heading_ms: headingAt,
    nav_to_skeleton_ms: skeletonAt,
    skeleton_to_data_ms: skeletonAt != null ? Math.max(0, headingAt - skeletonAt) : null,
    lcp_ms: lcp,
    usable_content_ms: headingAt,
    success_marker: successMarker,
    note,
  };
}

async function measureColdGoto(
  browser: Browser,
  route: (typeof routes)[number],
  sampleIndex: number,
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
      sampleIndex,
    );
  } finally {
    await context.close();
  }
}

async function measureWarmGoto(
  page: Page,
  route: (typeof routes)[number],
  sampleIndex: number,
): Promise<RouteTiming> {
  return measureVisibleContent(
    page,
    route,
    () => page.goto(route.path, { waitUntil: "domcontentloaded" }),
    "warm_goto",
    sampleIndex,
  );
}

async function measureSoftNav(
  page: Page,
  route: (typeof routes)[number],
  sampleIndex: number,
): Promise<RouteTiming> {
  // Soft Overview: start from Status (never /dashboard → /dashboard).
  const startRoute =
    route.name === "overview"
      ? routes.find((r) => r.name === "status")!
      : routes.find((r) => r.name === "overview")!;
  await page.goto(startRoute.path, { waitUntil: "domcontentloaded" });
  await assertSuccessContent(page, startRoute);

  return measureVisibleContent(
    page,
    route,
    async () => {
      await page.getByRole("link", { name: route.navLabel, exact: true }).first().click();
      return true;
    },
    "soft_nav",
    sampleIndex,
  );
}

function summarizeMode(samples: RouteTiming[]): ModeSummary {
  const first = samples[0]!;
  const usable = samples
    .map((s) => s.usable_content_ms)
    .filter((v): v is number => v != null && Number.isFinite(v));
  const measured = samples.every((s) => s.status === "MEASURED") && usable.length > 0;
  const p95Ready = usable.length >= 5;
  return {
    name: first.name,
    path: first.path,
    mode: first.mode,
    status: measured ? "MEASURED" : "NOT_MEASURED",
    sample_count: samples.length,
    usable_content_p95_ms: p95Ready ? percentile(usable, 95) : null,
    usable_content_max_ms: usable.length ? Math.max(...usable) : null,
    usable_content_samples_ms: usable,
    p95_status: p95Ready ? "MEASURED" : "NOT_MEASURED",
    p95_note: p95Ready
      ? `p95 from n=${usable.length} samples`
      : `p95 NOT_MEASURED (need n>=5; observed n=${usable.length})`,
  };
}

test.describe("Issue #101/#124 Layer A browser timings", () => {
  test.skip(!canRun, `Set ${requiredEnv.join(", ")} to run Layer A timings`);

  test("measure cold/warm/soft navigation to visible content", async ({ browser }) => {
    // Cold repeats with login gaps can take many minutes (rate-limit spacing).
    test.setTimeout(20 * 60 * 1000);
    const timings: RouteTiming[] = [];

    // Warm context: login once, reuse for warm_goto + soft_nav.
    const warmContext = await browser.newContext();
    const warmPage = await warmContext.newPage();
    await installLcpObserver(warmPage);
    await login(warmPage);

    for (const route of routes) {
      for (let i = 0; i < coldRepeats; i += 1) {
        if (i > 0 || timings.some((t) => t.mode === "cold_goto")) {
          // Space cold logins across routes/samples (dashboard auth rate limit).
          await new Promise((resolve) => setTimeout(resolve, coldLoginGapMs));
        }
        timings.push(await measureColdGoto(browser, route, i));
      }
      for (let i = 0; i < warmRepeats; i += 1) {
        timings.push(await measureWarmGoto(warmPage, route, i));
      }
      for (let i = 0; i < warmRepeats; i += 1) {
        timings.push(await measureSoftNav(warmPage, route, i));
      }
    }

    await warmContext.close();

    const summaries: ModeSummary[] = [];
    for (const route of routes) {
      for (const mode of ["cold_goto", "warm_goto", "soft_nav"] as const) {
        const samples = timings.filter((t) => t.name === route.name && t.mode === mode);
        summaries.push(summarizeMode(samples));
      }
    }

    const allObserved = timings
      .map((t) => t.usable_content_ms)
      .filter((v): v is number => v != null);
    const underBudget = allObserved.every((v) => v < 1500);
    const anyP95 = summaries.some((s) => s.p95_status === "MEASURED");

    const outDir = path.join(process.cwd(), "docs", "operations");
    fs.mkdirSync(outDir, { recursive: true });
    const artifact = {
      measurement: "layer_a_browser_visible_content",
      issue: 124,
      related_issues: [101, 124],
      status: timings.some((t) => t.status === "MEASURED") ? "MEASURED" : "NOT_MEASURED",
      measured_at: new Date().toISOString(),
      budget_note:
        "ROADMAP 1.5s is visible/usable content p95. Single samples do not establish p95. " +
        (anyP95
          ? "Modes with n>=5 report usable_content_p95_ms; others remain p95 NOT_MEASURED."
          : "All Layer A p95 values remain NOT_MEASURED until n>=5 per route×mode."),
      observation_budget_check: {
        roadmap_budget_ms: 1500,
        observed_sample_count: allObserved.length,
        observed_max_ms: allObserved.length ? Math.max(...allObserved) : null,
        all_observed_samples_under_budget: underBudget,
        p95_claim_allowed: anyP95,
      },
      repeats: {
        cold_goto: coldRepeats,
        warm_goto: warmRepeats,
        soft_nav: warmRepeats,
        cold_login_gap_ms: coldLoginGapMs,
      },
      methodology: {
        cold_goto:
          "Fresh authenticated context per sample (new browser.newContext() + login). " +
          "Login may warm shared assets; not a zero-HTTP-cache claim.",
        warm_goto: "Same warmed authenticated context, hard navigation.",
        soft_nav:
          "Same warmed context; Overview soft-nav starts from /dashboard/status.",
        success_marker:
          "Exact success heading + absent unavailable heading + absent " +
          "data-testid=dashboard-error-panel; optional dashboard-page-ready when deployed.",
        skeleton:
          "Observed in parallel with heading; headingAt never waits on skeleton timeout.",
        lcp:
          "PerformanceObserver buffered LCP on hard nav only; soft_nav lcp_ms=null.",
      },
      summaries,
      timings,
    };
    const outPath = path.join(outDir, "dashboard-layer-a-browser.json");
    fs.writeFileSync(outPath, `${JSON.stringify(artifact, null, 2)}\n`, "utf-8");
    expect(timings.length).toBe(routes.length * (coldRepeats + warmRepeats * 2));
    expect(underBudget).toBeTruthy();
  });
});
