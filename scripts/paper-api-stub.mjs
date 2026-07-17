#!/usr/bin/env node
/**
 * Deterministic Paper API stub for Playwright dashboard tests (Issue #238).
 * Serves read-only JSON fixtures on PORT (default 18080).
 *
 * Scenarios (POST /__test/scenario {"scenario":"..."}):
 * - default
 * - stale          — heartbeat older than threshold
 * - summary_error  — dashboard-summary returns 503
 * - section_error  — fills + events + scheduler return 503
 */
import http from "node:http";

const PORT = Number(process.env.PAPER_API_STUB_PORT || 18080);

/** @type {"default"|"stale"|"summary_error"|"section_error"} */
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

const server = http.createServer(async (req, res) => {
  const url = req.url || "/";
  const method = req.method || "GET";

  if (url.startsWith("/__test/scenario") && method === "POST") {
    try {
      const body = await readBody(req);
      const next = body.scenario || "default";
      const allowed = new Set([
        "default",
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
  if (url.startsWith("/api/v1/positions")) return json(res, positions);

  if (url.startsWith("/api/v1/fills")) {
    if (scenario === "section_error") {
      return json(res, { detail: "fills unavailable" }, 503);
    }
    return json(res, fills);
  }

  if (url.startsWith("/api/v1/equity")) return json(res, equity);
  if (url.startsWith("/api/v1/orders")) return json(res, emptyPage);
  if (url.startsWith("/api/v1/stops")) return json(res, emptyPage);

  if (url.startsWith("/api/v1/scheduler-runs")) {
    if (scenario === "section_error") {
      return json(res, { detail: "scheduler unavailable" }, 503);
    }
    return json(res, emptyPage);
  }

  if (url.startsWith("/api/v1/events")) {
    if (scenario === "section_error") {
      return json(res, { detail: "events unavailable" }, 503);
    }
    return json(res, emptyPage);
  }

  if (url.startsWith("/api/v1/market-data")) {
    return json(res, { market_data_ready: true });
  }
  return json(res, { detail: "not found" }, 404);
});

server.listen(PORT, "127.0.0.1", () => {
  console.log(`paper-api-stub listening on http://127.0.0.1:${PORT}`);
});
