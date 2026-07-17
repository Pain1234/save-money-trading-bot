"""Issue #121 — FastAPI residual attribution (region experiment).

## 1. Ausgangslage

| Field | Value |
|-------|-------|
| Date | 2026-07-15 |
| main / API deploy SHA | `ad702863c01aaa99f5243228ba258497d0dc3a0e` |
| API region before | `sfo` |
| Dashboard region | `europe-west4-drams3a` |
| Postgres region | `europe-west4-drams3a` |
| Internal API URL | `http://paper-trading-api.railway.internal:8080` |
| Harness | `scripts/railway_layer_c_probe.js` via `scripts/run_railway_layer_c_probe.py` |
| Warm / warmup | 20 / 3 |

Code review (`MEASURED`): `get_db_session` creates and `dispose()`s a SQLAlchemy engine **per request**.

## 2. Hypothesen

| ID | Hypothesis | Status |
|----|------------|--------|
| H1 | API in `sfo` vs Postgres/Dashboard EU drives ~2.13 s residual | **`CONFIRMED`** |
| H2 | Per-request engine/dispose inflates residual | **`FOLLOW_UP_REQUIRED`** (still true after H1; residual ~50 ms) |
| H3 | Serialization / large payloads drive residual | **`REJECTED`** for ~2.13 s (flat across body sizes in #101/#120) |

## 3. Messmethodik

- Private hop only (dashboard SSH → Railway private API).
- Residuals/hops = **p95 of per-sample deltas**.
- Routes: `wallet`, `dashboard_summary`, `status`.
- Single factor between before/after: API region only.

## 4. Service- und Regionslayout

| Phase | API | Dashboard | Postgres |
|-------|-----|-----------|----------|
| Before | `sfo` | `europe-west4-drams3a` | `europe-west4-drams3a` |
| After | `europe-west4-drams3a` | unchanged | unchanged |

Command used:

```bash
railway scale --service paper-trading-api eu-west=1 sfo=0
```

Rollback (documented; **not executed** — improvement held and health stayed green):

```bash
railway scale --service paper-trading-api us-west=1 eu-west=0
# or: railway scale --service paper-trading-api sfo=1 eu-west=0
```

## 5. Instrumentierung

- Before/after attribution used Layer C headers already shipped in #119/#120.
- Opt-in breakdown (this PR): `PAPER_API_PERF_BREAKDOWN=1` exposes
  `X-Perf-Engine-Create-Ms`, `X-Perf-Session-Setup-Ms`, `X-Perf-Pool-Connect-Ms`.
- Breakdown **not required** to confirm H1 (region change alone sufficed).
- Listener attach/detach remains paired; no payload/SQL parameter logging.

## 6. Before-Messwerte (`dashboard-layer-c-before-121.json`)

| Route | total p95 | db p95 | residual p95 | hop p95 | q | bytes |
|-------|----------:|-------:|-------------:|--------:|--:|------:|
| wallet | 2439.3 | 283.2 | **2155.0** | 152.1 | 1 | 238 |
| dashboard_summary | 3162.8 | 993.4 | **2173.7** | 153.1 | 6 | 1175 |
| status | 2885.5 | 717.8 | **2176.2** | 154.1 | 4 | 639 |

All samples HTTP 200. Residual p50 ≈ 2152–2167 ms.

## 7. Ausgeführte Einzeländerung

**Only** `paper-trading-api` region: `sfo` → `europe-west4-drams3a`.
No cache TTL, index, schema, strategy, pooling, or API contract change.

Post-change checks: `/health` 200, `/readiness` 200, `RAILWAY_REPLICA_REGION=europe-west4-drams3a`.

## 8. After-Messwerte (`dashboard-layer-c-after-121.json`)

| Route | total p95 | db p95 | residual p95 | hop p95 | q | bytes |
|-------|----------:|-------:|-------------:|--------:|--:|------:|
| wallet | **53.7** | 5.1 | **49.1** | 4.6 | 1 | 238 |
| dashboard_summary | **71.2** | 15.7 | **53.8** | 4.4 | 6 | 1175 |
| status | **66.0** | 14.2 | **51.8** | 5.5 | 4 | 638 |

All samples HTTP 200.

## 9. Entscheidung Regionshypothese

**`CONFIRMED`**

| Route | residual Δ | residual % | hop Δ | db Δ | total Δ |
|-------|-----------:|-----------:|------:|-----:|--------:|
| wallet | −2105.9 ms | −97.7% | −147.5 | −278.1 | −2385.6 |
| dashboard_summary | −2119.9 ms | −97.5% | −148.7 | −977.7 | −3091.6 |
| status | −2124.4 ms | −97.6% | −148.6 | −703.6 | −2819.5 |

Visible on all three routes; query counts unchanged; response sizes unchanged; no error samples.

API total p95 now **≪ 1.5 s** usable-content budget on the API hop alone.

## 10. Verbleibendes Residual

~**49–54 ms** p95 unattributed (`total − db`) after co-location.
Private hop ~**4–6 ms**.

Likely contributors (not separately proven in this experiment): per-request engine create/dispose (H2), local connect, middleware. Marked `FOLLOW_UP_REQUIRED` — do **not** change pooling in the same before/after window as region.

## 11. Rollbackstatus

Rollback **not applied**. Production API left in `europe-west4-drams3a` after confirmed improvement and healthy readiness.

## 12. Nächste Empfehlung

1. Keep API in EU West with Dashboard/Postgres.
2. Optional follow-up issue: process-scoped engine/pool (H2) targeting remaining ~50 ms — one factor, new before/after.
3. Issue #101: authenticated Layer A/B still required for UX close; credentials via secrets only.
4. No Alembic indexes and no Cache-TTL changes from these results.
