#!/usr/bin/env node
/**
 * Deterministic Paper API stub for Playwright dashboard tests (Issue #238)
 * and Research Workspace route smoke (Issue #250).
 * Serves read-only JSON fixtures on PORT (default 18080).
 *
 * Scenarios (POST /__test/scenario {"scenario":"..."}):
 * - default
 * - empty          — equity/positions/fills empty; summary open_position_count=0
 * - stale          — heartbeat older than threshold
 * - summary_error  — dashboard-summary returns 503
 * - section_error  — equity, positions, fills, events, scheduler return 503
 *
 * Research routes under /api/v1/research/* return empty/synthetic fixtures only
 * (no private Strategy V1 economics).
 */
import http from "node:http";

const PORT = Number(process.env.PAPER_API_STUB_PORT || 18080);

/** @type {"default"|"empty"|"stale"|"summary_error"|"section_error"} */
let scenario = "default";

const baseSummary = {
  display_status: "READY",
  status: {
    display_status: "READY",
    heartbeat_age_seconds: 4,
    stale_heartbeat_threshold_seconds: 30,
    hyperliquid_network: "testnet",
    runtime: {
      status: "READY",
      heartbeat_at: "2026-07-17T12:00:00Z",
      last_error: null,
      kill_switch: false,
      paused: false,
    },
    readiness: { runtime_readiness: true, reasons: [] },
  },
  readiness: { runtime_readiness: true, reasons: [] },
  heartbeat_at: "2026-07-17T12:00:00Z",
  wallet: {
    cash: "100000.00",
    total_realized_pnl: "250.00",
    updated_at: "2026-07-17T12:00:00Z",
  },
  open_position_count: 1,
  position_summary: [
    {
      symbol: "BTC",
      status: "OPEN",
      quantity: "0.10",
      unrealized_pnl: "12.50",
    },
  ],
  warnings: [],
  hyperliquid_network: "testnet",
};

function currentSummary() {
  if (scenario === "stale") {
    return {
      ...baseSummary,
      display_status: "DEGRADED",
      warnings: ["stale_heartbeat"],
      status: {
        ...baseSummary.status,
        display_status: "DEGRADED",
        heartbeat_age_seconds: 120,
        stale_heartbeat_threshold_seconds: 30,
      },
    };
  }
  if (scenario === "empty") {
    return {
      ...baseSummary,
      open_position_count: 0,
      position_summary: [],
    };
  }
  return baseSummary;
}

const positions = {
  items: [
    {
      position_id: "11111111-1111-1111-1111-111111111111",
      symbol: "BTC",
      status: "OPEN",
      quantity: "0.10",
      average_entry_price: "60000.00",
      current_stop: "58000.00",
      unrealized_pnl: "12.50",
      opened_at: "2026-07-16T12:00:00Z",
    },
  ],
  next_cursor: null,
  limit: 50,
};

const fills = {
  items: [
    {
      fill_id: "22222222-2222-2222-2222-222222222222",
      fill_kind: "ENTRY",
      symbol: "BTC",
      quantity: "0.10",
      fill_price: "60000.00",
      fill_time: "2026-07-16T12:00:00Z",
    },
  ],
  next_cursor: null,
  limit: 50,
};

const equity = {
  items: [
    {
      evaluation_time: "2026-07-01T00:00:00Z",
      equity: "99000.00",
      cash: "99000.00",
    },
    {
      evaluation_time: "2026-07-10T00:00:00Z",
      equity: "100000.00",
      cash: "100000.00",
    },
  ],
  next_cursor: null,
  limit: 100,
};

const emptyPage = { items: [], next_cursor: null, limit: 50 };

function json(res, body, status = 200) {
  const data = JSON.stringify(body);
  res.writeHead(status, {
    "Content-Type": "application/json",
    "Content-Length": Buffer.byteLength(data),
  });
  res.end(data);
}

function readBody(req) {
  return new Promise((resolve, reject) => {
    const chunks = [];
    req.on("data", (c) => chunks.push(c));
    req.on("end", () => {
      try {
        const raw = Buffer.concat(chunks).toString("utf8");
        resolve(raw ? JSON.parse(raw) : {});
      } catch (err) {
        reject(err);
      }
    });
    req.on("error", reject);
  });
}

function sectionUnavailable(res, label) {
  return json(res, { detail: `${label} unavailable` }, 503);
}

const server = http.createServer(async (req, res) => {
  const url = req.url || "/";
  const method = req.method || "GET";

  if (url.startsWith("/__test/scenario") && method === "POST") {
    try {
      const body = await readBody(req);
      const next = body.scenario || "default";
      const allowed = new Set([
        "default",
        "empty",
        "stale",
        "summary_error",
        "section_error",
      ]);
      if (!allowed.has(next)) {
        return json(res, { detail: "unknown scenario" }, 400);
      }
      scenario = next;
      return json(res, { ok: true, scenario });
    } catch {
      return json(res, { detail: "invalid json" }, 400);
    }
  }

  if (url.startsWith("/__test/scenario") && method === "GET") {
    return json(res, { scenario });
  }

  if (url.startsWith("/health")) return json(res, { status: "ok" });

  if (url.startsWith("/api/v1/dashboard-summary")) {
    if (scenario === "summary_error") {
      return json(res, { detail: "summary unavailable" }, 503);
    }
    return json(res, currentSummary());
  }

  if (url.startsWith("/api/v1/status")) {
    return json(res, currentSummary().status);
  }
  if (url.startsWith("/api/v1/wallet")) {
    return json(res, currentSummary().wallet);
  }

  if (url.startsWith("/api/v1/positions")) {
    if (scenario === "section_error") {
      return sectionUnavailable(res, "positions");
    }
    if (scenario === "empty") return json(res, emptyPage);
    return json(res, positions);
  }

  if (url.startsWith("/api/v1/fills")) {
    if (scenario === "section_error") {
      return sectionUnavailable(res, "fills");
    }
    if (scenario === "empty") return json(res, emptyPage);
    return json(res, fills);
  }

  if (url.startsWith("/api/v1/equity")) {
    if (scenario === "section_error") {
      return sectionUnavailable(res, "equity");
    }
    if (scenario === "empty") {
      return json(res, { items: [], next_cursor: null, limit: 100 });
    }
    return json(res, equity);
  }

  if (url.startsWith("/api/v1/orders")) return json(res, emptyPage);
  if (url.startsWith("/api/v1/stops")) return json(res, emptyPage);

  if (url.startsWith("/api/v1/scheduler-runs")) {
    if (scenario === "section_error") {
      return sectionUnavailable(res, "scheduler");
    }
    return json(res, emptyPage);
  }

  if (url.startsWith("/api/v1/events")) {
    if (scenario === "section_error") {
      return sectionUnavailable(res, "events");
    }
    return json(res, emptyPage);
  }

  if (url.startsWith("/api/v1/market-data")) {
    return json(res, { market_data_ready: true });
  }

  // --- Research Workspace stubs (#250 Playwright route smoke) ---------------
  // Empty/synthetic fixtures only — no private Strategy V1 economics.
  if (url === "/api/v1/research/overview" || url.startsWith("/api/v1/research/overview?")) {
    return json(res, {
      experiment_count: 0,
      completed_count: 0,
      failed_count: 0,
      invalidated_count: 0,
      running_count: 0,
      running_available: true,
      strategy_version_count: 1,
      known_strategy_ids: ["trend_v1"],
      status_distribution: {},
      recent_experiments: [],
      unavailable: {},
    });
  }
  if (url === "/api/v1/research/strategies" || url.startsWith("/api/v1/research/strategies?")) {
    return json(res, {
      items: [
        {
          strategy_id: "trend_v1",
          strategy_version: "1.0.0",
          label: "Trend Strategy V1",
          display_name: "Trend Strategy V1",
          description: "Public fixture strategy for acceptance smoke.",
          lifecycle_status: "active",
          timeframes: ["1D"],
          timeframe_note: "Daily bars",
          symbols: ["BTC"],
          supported_symbols: ["BTC"],
          required_timeframes: ["1D"],
          experiment_count: 0,
          last_run: null,
        },
      ],
      count: 1,
    });
  }
  if (url.match(/^\/api\/v1\/research\/strategies\/[^/]+\/schema/)) {
    return json(res, {
      strategy_id: "trend_v1",
      display_name: "Trend Strategy V1",
      description: "Public fixture strategy for acceptance smoke.",
      strategy_version: "1.0.0",
      parameter_defaults: { atr_period: 14, daily_ema_period: 20 },
      parameter_descriptions: {},
      parameters_schema: {
        properties: {
          atr_period: { type: "integer", default: 14 },
          daily_ema_period: { type: "integer", default: 20 },
        },
      },
      symbols: ["BTC"],
      timeframes: ["1D"],
    });
  }
  if (url.match(/^\/api\/v1\/research\/strategies\/[^/?]+/)) {
    const match = url.match(/^\/api\/v1\/research\/strategies\/([^/?]+)/);
    const strategyId = match ? decodeURIComponent(match[1]) : "";
    if (strategyId !== "trend_v1") {
      return json(res, { detail: "strategy not found" }, 404);
    }
    return json(res, {
      strategy_id: "trend_v1",
      display_name: "Trend Strategy V1",
      description: "Public fixture strategy for acceptance smoke.",
      strategy_version: "1.0.0",
      aliases: [],
      lifecycle_status: "active",
      supported_symbols: ["BTC"],
      required_timeframes: ["1D"],
      monthly_filter: "Fixture monthly filter note.",
      weekly_filter: "Fixture weekly filter note.",
      daily_entries: "Fixture daily entries note.",
      stop_logic: "Fixture stop logic note.",
      reason_codes: ["ENTRY", "EXIT"],
      parameter_defaults: { atr_period: 14, daily_ema_period: 20 },
      parameter_descriptions: {},
      experiment_count: 0,
      last_run: null,
      experiments: [],
    });
  }
  if (url === "/api/v1/research/datasets" || url.startsWith("/api/v1/research/datasets?")) {
    return json(res, {
      items: [
        {
          id: "local-btc-fixture",
          label: "Local BTC fixture",
          dataset_id: "ds_local_btc_fixture",
          symbols: ["BTC"],
        },
      ],
      count: 1,
    });
  }
  if (
    url === "/api/v1/research/experiments" ||
    url.startsWith("/api/v1/research/experiments?")
  ) {
    return json(res, { items: [], count: 0 });
  }
  if (url.startsWith("/api/v1/research/experiments/compare")) {
    return json(res, { detail: "run_a and run_b required" }, 422);
  }
  if (url === "/api/v1/research/robustness" || url.startsWith("/api/v1/research/robustness?")) {
    return json(res, { items: [], count: 0 });
  }
  if (url === "/api/v1/research/gates" || url.startsWith("/api/v1/research/gates?")) {
    return json(res, { items: [], count: 0 });
  }
  if (url === "/api/v1/research/validation" || url.startsWith("/api/v1/research/validation?")) {
    return json(res, { items: [], count: 0 });
  }
  if (url === "/api/v1/research/scorecards" || url.startsWith("/api/v1/research/scorecards?")) {
    return json(res, { items: [], count: 0 });
  }

  return json(res, { detail: "not found" }, 404);
});

server.listen(PORT, "127.0.0.1", () => {
  console.log(`paper-api-stub listening on http://127.0.0.1:${PORT}`);
});
