#!/usr/bin/env node
/**
 * Layer C probe from paper-trading-dashboard (private Next.js -> FastAPI hop).
 * Issue #101 Railway evidence. Prints JSON to stdout only.
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

const WARMUP = 1;
const WARM = 5;
const TIMEOUT_MS = 15000;

function percentile(values, pct) {
  if (!values.length) return null;
  const ordered = [...values].sort((a, b) => a - b);
  const idx = Math.max(
    0,
    Math.min(ordered.length - 1, Math.round((pct / 100) * (ordered.length - 1))),
  );
  return ordered[idx];
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
      status_code: res.status,
      client_total_ms: clientMs,
      header_total_ms: res.headers.get("x-perf-total-ms"),
      header_db_ms: res.headers.get("x-perf-db-ms"),
      header_query_count: res.headers.get("x-perf-query-count"),
      response_bytes: Buffer.byteLength(bodyText),
      correlation_id: res.headers.get("x-correlation-id"),
      payload_json_bytes: share.payload_bytes,
      payload_json_share: share.share,
    };
  } finally {
    clearTimeout(timer);
  }
}

function summarize(name, path, samples) {
  if (!samples.length) {
    return { name, path, status: "NOT_MEASURED", note: "no samples" };
  }
  const complete = samples.every(
    (s) =>
      s.header_total_ms != null &&
      s.header_db_ms != null &&
      s.header_query_count != null,
  );
  const client = samples.map((s) => s.client_total_ms);
  const totals = samples
    .map((s) => (s.header_total_ms == null ? null : Number(s.header_total_ms)))
    .filter((v) => v != null);
  const dbs = samples
    .map((s) => (s.header_db_ms == null ? null : Number(s.header_db_ms)))
    .filter((v) => v != null);
  const qcs = samples
    .map((s) => (s.header_query_count == null ? null : Number(s.header_query_count)))
    .filter((v) => v != null);
  const sizes = samples.map((s) => s.response_bytes);
  const payloadSizes = samples
    .map((s) => s.payload_json_bytes)
    .filter((v) => v != null);
  const payloadShares = samples
    .map((s) => s.payload_json_share)
    .filter((v) => v != null);
  sizes.sort((a, b) => a - b);
  return {
    name,
    path,
    status: complete ? "MEASURED" : "PARTIAL",
    warm_client_p95_ms: percentile(client, 95),
    warm_header_total_p95_ms: percentile(totals, 95),
    warm_header_db_p95_ms: percentile(dbs, 95),
    warm_query_count_p95: percentile(qcs, 95),
    warm_response_bytes_p50: sizes[Math.floor(sizes.length / 2)],
    warm_response_bytes_max: Math.max(...sizes),
    events_payload_json_bytes_p50: payloadSizes.length
      ? payloadSizes.sort((a, b) => a - b)[Math.floor(payloadSizes.length / 2)]
      : null,
    events_payload_json_share_p50: payloadShares.length
      ? payloadShares.sort((a, b) => a - b)[Math.floor(payloadShares.length / 2)]
      : null,
    note: complete ? "" : "missing one or more X-Perf-* headers",
  };
}

(async () => {
  const routes = [];
  for (const [name, path] of ROUTES) {
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
    issue: 101,
    environment: "railway-production",
    network_path: "paper-trading-dashboard â†’ PRIVATE_PAPER_API_URL â†’ paper-trading-api",
    base_url_host_only: base.replace(/^https?:\/\//, ""),
    region_probe_service: "paper-trading-dashboard",
    warm_runs: WARM,
    warmup_runs: WARMUP,
    measured_at: new Date().toISOString(),
    routes,
  };
  process.stdout.write(`${JSON.stringify(report, null, 2)}\n`);
})().catch((err) => {
  console.error(err);
  process.exit(1);
});
