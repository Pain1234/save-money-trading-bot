# API, UI and Deployment Audit (Auditor C)

**Issue:** [#371](https://github.com/Pain1234/save-money-trading-bot/issues/371)
**Audit SHA:** `7b78eb9996eb16e6d2ec6a00c2e1908c518682d9`
**Audit time:** 2026-07-19 (UTC)
**Scope:** paper/research API, Monitor/Research UI, Railway/Docker/CI parity and the
shared execution-owner/API-identity boundaries. No P5 artifacts, production data,
credentials, deployment settings or live/private exchange paths were touched.

## Result

Paper monitoring endpoints are GET-only and their serializers preserve Decimal strings,
UTC timestamps and domain IDs. Artifact content reads have a strong allowlist, traversal,
seal and checksum boundary. The service and product descriptions are nevertheless
materially inaccurate when they call the combined API or Research Workspace read-only:
the same process exposes ten evidence-mutating Research POST route shapes, and the
production backend has no application-level authentication for them. Deployment parity is
also not independently observable, and a rebuild of the Python image is not dependency
reproducible.

Runtime status classifications in this report mean:

- `CODE_VERIFIED`: inspected in source at the audit SHA.
- `TEST_VERIFIED`: exercised by an executed test or exact-SHA CI job.
- `RUNTIME_OBSERVED`: directly observed without authentication or mutation.
- `NOT_VERIFIABLE`: credentials, private Railway state or a runtime SHA was unavailable.

## Endpoint inventory

### Paper monitoring plane

Source: `services/paper_trading/readonly_api.py:212-654`. The route table was also
introspected locally with `paper_trading.readonly_api.app`.

| Method | Path | Principal fields / semantics | Status |
|---|---|---|---|
| GET | `/health` | process liveness | CODE_VERIFIED, TEST_VERIFIED |
| GET | `/readiness` | runtime/entry/database/migration readiness; pause/kill reasons | CODE_VERIFIED, TEST_VERIFIED |
| GET | `/api/v1/status` | display status, runtime record, heartbeat age, network | CODE_VERIFIED, TEST_VERIFIED |
| GET | `/api/v1/dashboard-summary` | status + wallet + open-position aggregate + warnings | CODE_VERIFIED, TEST_VERIFIED |
| GET | `/api/v1/market-data` | heartbeat-derived market-data state | CODE_VERIFIED, TEST_VERIFIED |
| GET | `/api/v1/wallet` | cash, realized PnL, total fees | CODE_VERIFIED, TEST_VERIFIED |
| GET | `/api/v1/positions` | position ID, symbol, status, quantity, entry/stop, unrealized PnL | CODE_VERIFIED, TEST_VERIFIED |
| GET | `/api/v1/orders` | paper-order ID, intent ID, status, requested quantity, fill time | CODE_VERIFIED, TEST_VERIFIED |
| GET | `/api/v1/fills` | fill ID/kind, order/intent IDs, price, fee, deterministic key | CODE_VERIFIED, TEST_VERIFIED |
| GET | `/api/v1/stops` | stop-event/position IDs and old/new/effective stop | CODE_VERIFIED, TEST_VERIFIED |
| GET | `/api/v1/scheduler-runs` | run ID, job, status, error, idempotency key | CODE_VERIFIED, TEST_VERIFIED |
| GET | `/api/v1/events` | IDs/type/time and sanitized audit payload | PARTIALLY_VERIFIED; see C-FINDING-04 |
| GET | `/api/v1/equity` | timestamp, cash, equity | CODE_VERIFIED, TEST_VERIFIED |

The monitoring middleware rejects non-GET/HEAD/OPTIONS with 405 except explicitly
allowlisted Research POSTs (`readonly_api.py:98-109`). Executed negative API tests passed.
No CORS middleware exists; direct cross-origin browser use is therefore not enabled by the
application. Private-network exposure is a Railway setting and was `NOT_VERIFIABLE`.

### Research plane mounted into the same process

Source: `services/research/api.py:26-812`; route table independently introspected from the
router object.

| Group | GET paths | POST paths |
|---|---|---|
| Overview | `/overview` | — |
| Experiments | `/experiments`, `/experiments/compare`, `/{id}`, `/{id}/metrics`, `/{id}/equity`, `/{id}/trades`, `/{id}/chart-data`, `/{id}/artifacts`, `/{id}/status` | `/experiments`, `/experiments/{id}/start` |
| Strategies/datasets | `/strategies`, `/strategies/{id}`, `/strategies/{id}/schema`, `/datasets` | — |
| Robustness | `/robustness`, `/robustness/{id}`, `/robustness/{id}/status` | `/robustness`, `/robustness/{id}/start` |
| Gates | `/gate-policies`, `/gates`, `/gates/{id}` | `/gates/evaluate`, `/gates/{id}/invalidate` |
| Scorecards | `/scorecard-policies`, `/scorecards`, `/scorecards/{id}`, `/scorecards/{id}/detail`, `/scorecards/{id}/artifacts/content` | `/scorecards/evaluate`, `/scorecards/{id}/invalidate` |
| Validation | `/validation`, `/validation/{id}` | `/validation`, `/validation/{id}/decision` |

All paths above are relative to `/api/v1/research`. The exact POST allowlist is duplicated in
`is_research_write_path()` (`services/research/api.py:791-812`). These writes do not send
paper/live orders, but they create/start jobs, append decisions/evaluations, or invalidate
evidence. `services/paper_trading/readonly_api.py:51-85` explicitly says the process starts
serving Research write traffic.

This contradicts the statement “All routes are GET-only. Non-GET requests return 405” in
`docs/railway-paper-trading-dashboard-v1.md` and the broad read-only descriptions in
`services/paper_trading/readonly_api.py:1,89-95`. Architecture text elsewhere partially
acknowledges an allowlisted Research write surface, so the documentation has two competing
contracts rather than a single reliable one.

## ID, traversal and artifact-content checks

| Boundary | Code evidence | Test evidence | Assessment |
|---|---|---|---|
| Unknown experiment/strategy IDs | Service returns 404 | `test_research_read_api.py:299-301`, `test_research_write_api.py:133-143,219-225` | VERIFIED |
| Experiment path traversal | path resolution fails closed | `test_research_read_api.py:424-428` | VERIFIED |
| Artifact relative path | rejects null, `%`, backslash, absolute, drive and `.`/`..` segments | `artifact_content.py:71-100`; negative tests at `test_artifact_content.py:57-75,231-248` | VERIFIED |
| Symlink/junction escape | each component and resolved path constrained below run root | `artifact_content.py:135-169`; targeted tests passed | VERIFIED |
| Artifact identity/seal | active scorecard pin + run manifest + checksum + regular-file + size/media checks | `artifact_content.py:172-351`; targeted tests passed | VERIFIED |
| Browser artifact route ID | rejects empty, slash and `..`; uses `encodeURIComponent` | `src/app/api/research/scorecards/[scorecardId]/artifacts/content/route.ts:13-36` | CODE_VERIFIED |

The backend sets `nosniff`, checksum/path headers and attachment disposition
(`services/research/api.py:631-669`). The Next proxy preserves content type, `nosniff`, path
and checksum but drops `Content-Disposition` (`src/lib/research-api/proxy.ts:37-59`). JSON
and text remain non-executable with `nosniff`; download-vs-inline behavior is only partially
preserved.

## Dashboard field semantics

### Monitor

| UI field | Backend source | Mapping assessment |
|---|---|---|
| Cash | `wallet.cash` | exact Decimal-string formatter |
| Realized PnL | `wallet.total_realized_pnl` | exact; not mislabeled as total/equity PnL |
| Open positions | `open_position_count` | exact summary aggregate |
| Bot status | `display_status` + heartbeat age | stale/degraded/stopped differentiated |
| Position PnL | `position.unrealized_pnl` | exact; LONG-only is explicit |
| Mark, risk, take-profit | no V1 API field | honestly “Nicht verfügbar” (`view-model.ts:149-165`) |
| Win rate / profit factor | no V1 API field | honestly “Nicht verfügbar” (`view-model.ts:101-113`) |
| Funding | disabled and absent from wallet UI contract | not fabricated; N/A for V1 |

The accounting display is therefore semantically sound for its limited field set. It is a
monitor, not an independent reconciliation view: it does not reconstruct cash, fees, PnL or
equity from fills.

### Research and long IDs

Research overview code explicitly maps null/empty/backend `NOT_AVAILABLE` to “Nicht
verfügbar” (`src/lib/research/scorecard-binding.ts:14,227-239`). Long overview IDs are
shortened with beginning/end retained while the full ID stays in accessible text/tooltip;
the dedicated test is `research-overview-scorecard-bind.test.tsx:419-443`. Forensics hashes
use `break-all` (`ResearchForensicsSection.tsx:111-112,432,492`). Tables are horizontally
scrollable, although several full IDs rely on that scroll rather than wrapping.

Two concrete semantic defects remain:

1. `ValidationStudyDetailView.tsx:181-184` treats numeric `n_failed == 0` as false and renders
   “Nicht verfügbar”, confusing a verified zero with missing evidence (C-FINDING-07).
2. `dashboard/incidents/page.tsx:7-15` falls back to ordinary recent events when no regex
   incident matches, while still titling the table “Errors / Incidents” (C-FINDING-06).

## Execution owner and API identity

Exactly-one-worker enforcement is real: the worker acquires a session-scoped PostgreSQL
advisory lock before recovery and runtime start (`paper_trading/lock.py:27-75`,
`paper_trading/application.py:204-222,291-329`). Railway config declares one replica
(`deploy/railway/paper-trading-worker.toml:5-9`). Exact-SHA Full CI passed PostgreSQL lock,
restart and integration suites.

Visibility is incomplete. Worker logs emit `postgres_advisory_lock_acquired` and a redacted
database fingerprint (`application.py:299-326,590-611`; `database_identity.py:23-76`). The
read API returns the runtime `instance_id`, but the frontend `StatusResponse` type omits it
(`src/lib/paper-api/client.ts:22-37`). Worse, read-API readiness always serializes
`advisory_lock_held=False` because the API does not own/inspect the worker lock
(`readonly_api.py:138-148`). The Monitor therefore cannot prove which worker is execution
owner or whether a lock is held (C-FINDING-08).

Paper and Research requests use the same server-only `PRIVATE_PAPER_API_URL`; browser code
does not receive the DB URL. Worker and API log the same host/port/database fingerprint, but
their current production equality was `NOT_VERIFIABLE` without Railway log access.

## Deployment and CI parity

| Component | Repository contract | Observed evidence | Status |
|---|---|---|---|
| Worker | Python 3.12 image; migrate, verify state, start `paper_trading`; one replica | source + deploy tests | CODE/TEST_VERIFIED |
| API | same image; `start-api.sh`; control off; Research commit pin from Railway SHA | source + deploy tests | CODE/TEST_VERIFIED |
| Dashboard | Node 22, `npm ci`, standalone Next, `node server.js` | source + exact-SHA deploy CI | CODE/TEST_VERIFIED |
| Public login | `https://bot.save-money.xyz/login` | HTTP 200 at 2026-07-19T16:58:22Z; Railway/Next headers | RUNTIME_OBSERVED |
| Dashboard/API/worker running SHA | expected deploy revision | no public build metadata; no Railway credentials | NOT_VERIFIABLE |
| Actual replicas/private networking/env | manual Railway state | no Railway visibility | NOT_VERIFIABLE |

The exact audit SHA has successful Full CI run
[`29695342023`](https://github.com/Pain1234/save-money-trading-bot/actions/runs/29695342023):
`full-quality`, `core-tests` (including deploy build/bundle tests),
`postgres-and-reporting`, `research-repro`, and `full-ci-required` all succeeded. The active
`main` ruleset `19091297` strictly requires the seven documented compatibility checks and
has no bypass actor. Classic branch-protection 404 is expected; the ruleset is the actual
enforcement mechanism (`docs/branch-protection.md:5-22,42-83`).

The deployment reproducibility break is in the Python image: it copies `pyproject.toml` and
runs `pip install -e ".[api]"` against lower-bound dependencies
(`deploy/Dockerfile.paper-python:20-28`). It neither copies nor installs the pinned
`requirements-baseline.txt`; the same Git SHA can therefore resolve different dependency
sets on later rebuilds (C-FINDING-02). The dashboard correctly uses lockfile-backed
`npm ci` (`Dockerfile.dashboard:2-12`).

The Python image receives `RAILWAY_GIT_COMMIT_SHA`, but that value is used for Research run
provenance, not exposed as worker/API build metadata; the dashboard image does not embed a
commit at all (`Dockerfile.paper-python:16-18`, `start-api.sh:21-24`,
`Dockerfile.dashboard:1-35`). The deployment runbook validates health and DB fingerprint,
not service/image commit identity (C-FINDING-03).

## Candidate findings

| ID | Severity | Finding / impact | Confidence | Stop criterion |
|---|---|---|---|---|
| C-FINDING-01 | P1 (High) | Combined “read-only” API exposes Research mutations without backend auth; manual network isolation is the only direct-backend boundary. Unauthorized access or network misconfiguration can create jobs, append decisions, or invalidate research evidence. No paper/live order path was found. | High for code; runtime exposure NOT_VERIFIABLE | Keep P5 holdout/final evidence mutations blocked until the intended write-plane/auth contract is explicitly accepted and deployment isolation is verified. Monitoring GETs may continue. |
| C-FINDING-02 | P1 (High) | Python production rebuilds resolve unpinned dependencies, so SHA equality does not imply behavioral equality. Research/paper results may depend on an unrecorded image dependency set. | High | Do not claim reproducible deployment or use a freshly rebuilt image as promotion evidence unless its dependency/image digest is recorded and matched. |
| C-FINDING-03 | P2 (Medium) | Running dashboard/API/worker SHA and image digest are not observable through health/status/UI; deployment drift cannot be independently detected. | High | No global stop; deployment-parity claims remain `NOT_VERIFIABLE`. Stop promotion evidence if evaluator/run SHA cannot be independently tied to the deployed image. |
| C-FINDING-06 | P3 (Low) | Incidents page shows ordinary events as incidents when there are zero regex matches, causing false operational signals. | High | Do not treat that page alone as an incident register. |
| C-FINDING-07 | P2 (Medium) | Validation detail renders zero failed runs as missing evidence, weakening zero-vs-missing integrity. | High | Do not use that cell as acceptance evidence; inspect API/manifest. |
| C-FINDING-08 | P2 (Medium) | Monitor does not expose the actual execution-owner/lock identity; `advisory_lock_held` is always false on read API and frontend omits worker instance ID. Operators cannot prove the single-owner invariant from the UI/API. | High | If logs/DB cannot identify exactly one lock owner, stop additional worker starts and follow the restart/incident runbook. |

## Commands and boundaries

- `python -m pytest ...test_readonly_api.py ...test_api_security.py
  ...test_dashboard_summary_api.py ...test_artifact_content.py
  ...test_research_read_api.py ...test_research_write_api.py -q --tb=short`:
  **75 passed, 1 skipped, 1 warning**, pytest 8.78 s / wall 9.626 s.
- Exact-SHA Full CI inspected via `gh run view 29695342023 --json ...`: all real Full CI
  jobs successful; push-event whitespace step and PR-only aliases skipped as designed.
- Local Next production build: compilation succeeded, then failed during lint/prerender due
  cross-worktree dependency/config conflict (parent `node_modules` and ESLint plugin
  conflict; React `useContext` null). Wall 21.382 s. This is **not** recorded as a product
  failure; clean exact-SHA CI deploy tests passed.
- Authenticated production pages, private API, Railway service revisions/replicas/logs/env,
  Docker digests and DB identity: `NOT_VERIFIABLE`.
