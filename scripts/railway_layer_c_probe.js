#!/usr/bin/env node
/**
 * Layer C probe from paper-trading-dashboard (private Next.js -> FastAPI hop).
 * Issue #101 Railway evidence. Prints JSON to stdout only.
 *
 * MEASURED requires: HTTP 2xx (res.ok), finite X-Perf-Total-Ms / Db-Ms / Query-Count.
 * Status codes and correlation IDs are retained on the route summary for validation.
 */
const base = (process.env.PRIVATE_PAPER_API_URL || "").replace(/\/$/, "");
if (!base) {
  console.error(JSON.stringify({ status: "NOT_MEASURED", note: "PRIVATE_PAPER_API_URL missing" }));
  process.exit(1);
}

const ROUTES = [
  ["status", "/api/v1/status"],
  ["dashboard_summary", "/api/v1/dashboard-summary"],
  ["wallet", "/api/v1/wallet"],
  ["positions", "/api/v1/positions?limit=50"],
  ["orders", "/api/v1/orders?limit=50"],
  ["fills", "/api/v1/fills?limit=50"],
  ["equity", "/api/v1/equity?limit=100"],
  ["events", "/api/v1/events?limit=50"],
  ["scheduler_runs", "/api/v1/scheduler-runs?limit=50"],
];

// Match scripts/measure_dashboard_layer_c_api.py defaults (p95 with n=5 ~= max).
const WARMUP = Number(process.env.LAYER_C_WARMUP_RUNS || 3);
const WARM = Number(process.env.LAYER_C_WARM_RUNS || 20);
const TIMEOUT_MS = Number(process.env.LAYER_C_TIMEOUT_MS || 30000);

function percentile(values, pct) {
  if (!values.length) return null;
  const ordered = [...values].sort((a, b) => a - b);
  const idx = Math.max(
    0,
    Math.min(ordered.length - 1, Math.round((pct / 100) * (ordered.length - 1))),
  );
  return ordered[idx];
}

function parseFiniteNumber(raw) {
  if (raw == null || raw === "") return null;
  const n = Number(raw);
  return Number.isFinite(n) ? n : null;
}

function payloadShare(bodyText, path) {
  if (!path.startsWith("/api/v1/events")) return { payload_bytes: null, share: null };
  try {
    const data = JSON.parse(bodyText);
    const items = Array.isArray(data.items) ? data.items : [];
    let payloadBytes = 0;
    for (const item of items) {
      if (item && item.payload_json != null) {
        payloadBytes += Buffer.byteLength(JSON.stringify(item.payload_json));
      }
    }
    const total = Buffer.byteLength(bodyText);
    return {
      payload_bytes: payloadBytes,
      share: total ? payloadBytes / total : null,
    };
  } catch {
    return { payload_bytes: null, share: null };
  }
}

async function sample(path) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
  const started = performance.now();
  try {
    const res = await fetch(`${base}${path}`, {
      headers: { Accept: "application/json", "Cache-Control": "no-cache" },
      signal: controller.signal,
    });
    const bodyText = await res.text();
    const clientMs = performance.now() - started;
    const share = payloadShare(bodyText, path);
    return {
      ok: res.ok,
      status_code: res.status,
      client_total_ms: clientMs,
      header_total_ms: parseFiniteNumber(res.headers.get("x-perf-total-ms")),
      header_db_ms: parseFiniteNumber(res.headers.get("x-perf-db-ms")),
      header_query_count: parseFiniteNumber(res.headers.get("x-perf-query-count")),
      response_bytes: Buffer.byteLength(bodyText),
      correlation_id: res.headers.get("x-correlation-id"),
      payload_json_bytes: share.payload_bytes,
      payload_json_share: share.share,
    };
  } finally {
    clearTimeout(timer);
  }
}

function sampleIsMeasured(s) {
  return (
    s.ok === true &&
    s.status_code >= 200 &&
    s.status_code < 300 &&
    s.header_total_ms != null &&
    s.header_db_ms != null &&
    s.header_query_count != null &&
    Number.isFinite(s.header_total_ms) &&
    Number.isFinite(s.header_db_ms) &&
    Number.isFinite(s.header_query_count)
  );
}

function summarize(name, path, samples) {
  if (!samples.length) {
    return { name, path, status: "NOT_MEASURED", note: "no samples" };
  }

  const statusCodes = [...new Set(samples.map((s) => s.status_code))];
  const correlationIds = samples
    .map((s) => s.correlation_id)
    .filter((id) => typeof id === "string" && id.length > 0);
  const httpOk = samples.every((s) => s.ok === true);
  const measuredOk = samples.every(sampleIsMeasured);
  const anyHeaders = samples.some(
    (s) =>
      s.header_total_ms != null || s.header_db_ms != null || s.header_query_count != null,
  );

  let status;
  let note = "";
  if (measuredOk) {
    status = "MEASURED";
  } else if (!httpOk) {
    status = "NOT_MEASURED";
    note = `non-2xx HTTP status in samples: ${statusCodes.join(",")}`;
  } else if (anyHeaders) {
    status = "PARTIAL";
    note = "2xx responses but missing/non-finite required X-Perf-* headers";
  } else {
    status = "NOT_MEASURED";
    note = "2xx responses but no usable X-Perf-* headers";
  }

  const client = samples.map((s) => s.client_total_ms);
  const totals = samples.map((s) => s.header_total_ms).filter((v) => v != null);
  const dbs = samples.map((s) => s.header_db_ms).filter((v) => v != null);
  const qcs = samples.map((s) => s.header_query_count).filter((v) => v != null);
  const sizes = samples.map((s) => s.response_bytes).sort((a, b) => a - b);
  const payloadSizes = samples
    .map((s) => s.payload_json_bytes)
    .filter((v) => v != null)
    .sort((a, b) => a - b);
  const payloadShares = samples
    .map((s) => s.payload_json_share)
    .filter((v) => v != null)
    .sort((a, b) => a - b);

  // p95 of per-sample deltas — never p95(total) - p95(db) or client_p95 - total_p95.
  const residuals = samples
    .filter(sampleIsMeasured)
    .map((s) => s.header_total_ms - s.header_db_ms);
  const hops = samples
    .filter(sampleIsMeasured)
    .map((s) => s.client_total_ms - s.header_total_ms);

  return {
    name,
    path,
    status,
    warm_client_p50_ms: percentile(client, 50),
    warm_client_p95_ms: percentile(client, 95),
    warm_header_total_p50_ms: percentile(totals, 50),
    warm_header_total_p95_ms: percentile(totals, 95),
    warm_header_db_p50_ms: percentile(dbs, 50),
    warm_header_db_p95_ms: percentile(dbs, 95),
    warm_unattributed_api_p50_ms: percentile(residuals, 50),
    warm_unattributed_api_ms: percentile(residuals, 95),
    warm_private_hop_p50_ms: percentile(hops, 50),
    warm_private_hop_p95_ms: percentile(hops, 95),
    warm_query_count_p50: percentile(qcs, 50),
    warm_query_count_p95: percentile(qcs, 95),
    warm_response_bytes_p50: sizes[Math.floor(sizes.length / 2)],
    warm_response_bytes_max: Math.max(...sizes),
    events_payload_json_bytes_p50: payloadSizes.length
      ? payloadSizes[Math.floor(payloadSizes.length / 2)]
      : null,
    events_payload_json_share_p50: payloadShares.length
      ? payloadShares[Math.floor(payloadShares.length / 2)]
      : null,
    sample_status_codes: statusCodes,
    sample_correlation_ids: correlationIds.slice(0, 5),
    sample_count: samples.length,
    note,
  };
}

(async () => {
  const allow = (process.env.LAYER_C_ROUTES || '')
    .split(',')
    .map((s) => s.trim())
    .filter(Boolean);
  const selected = allow.length
    ? ROUTES.filter(([name]) => allow.includes(name))
    : ROUTES;
  const routes = [];
  for (const [name, path] of selected) {
    try {
      for (let i = 0; i < WARMUP; i++) await sample(path);
      const samples = [];
      for (let i = 0; i < WARM; i++) samples.push(await sample(path));
      routes.push(summarize(name, path, samples));
    } catch (err) {
      routes.push({
        name,
        path,
        status: "NOT_MEASURED",
        note: `${err && err.name ? err.name : "Error"}: ${err && err.message ? err.message : err}`,
      });
    }
  }
  const report = {
    measurement: "layer_c_fastapi",
    issue: Number(process.env.LAYER_C_ISSUE || 121),
    environment: "railway-production",
    network_path: "paper-trading-dashboard -> PRIVATE_PAPER_API_URL -> paper-trading-api",
    base_url_host_only: base.replace(/^https?:\/\//, ""),
    region_probe_service: "paper-trading-dashboard",
    regions: {
      "paper-trading-dashboard": process.env.LAYER_C_DASHBOARD_REGION || "NOT_MEASURED",
      "paper-trading-api": process.env.LAYER_C_API_REGION || "NOT_MEASURED",
      "paper-trading-postgres": process.env.LAYER_C_POSTGRES_REGION || "NOT_MEASURED",
    },
    public_dashboard_url: "https://bot.save-money.xyz",
    evidence_doc: "docs/operations/dashboard-railway-performance-evidence.md",
    warm_runs: WARM,
    warmup_runs: WARMUP,
    warmup_note:
      "warmup_runs are discarded probes to stabilize the process; p95 uses warm_runs only (default 20/3 matches measure_dashboard_layer_c_api.py).",
    measured_at: new Date().toISOString(),
    routes,
  };
  process.stdout.write(`${JSON.stringify(report, null, 2)}\n`);
})().catch((err) => {
  console.error(err);
  process.exit(1);
});
