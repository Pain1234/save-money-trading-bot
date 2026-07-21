# Resilience and Operations Audit (Auditor C)

**Issue/SHA:** #371 / `7b78eb9996eb16e6d2ec6a00c2e1908c518682d9`
**Safety:** local deterministic tests and read-only source/runtime observation only. No
production chaos, restart, scaling, DB write, deploy or control action occurred.

## Result

Local degraded-startup/recovery tests and exact-SHA Full CI are green. Worker safety has
substantial code/test coverage: advisory lock, deterministic keys, startup recovery,
heartbeat/readiness, stale-data entry blocking and PostgreSQL failure/restart tests. The
production operational result remains only partially verified because Railway state/logs,
worker ownership, backups and authenticated health were unavailable.

Research job recovery has a separate fail-open availability choice: recovery exceptions
are logged and the API proceeds to serve mutating Research endpoints. That is safe for read
availability but not proven safe for subsequent write ownership (C-FINDING-05).

## Safe tests executed

| Command/suite | Runtime | Result | Skips/deselection |
|---|---:|---|---|
| Focused paper/research API, security, summary, artifact, read/write tests | pytest 8.78 s; wall 9.626 s | 75 passed | 1 skipped; Starlette/httpx deprecation warning |
| `tests/paper_trading/failure` + permanent-config + degraded-startup + runtime-recovery, `-m "not postgres and not live and not soak"` | pytest 0.44 s; wall 1.256 s | 24 passed | 14 tests deselected by the marker expression |
| Local Next production build using parent worktree dependencies | wall 21.382 s | compiled, then failed lint/prerender | invalid cross-worktree dependency/config setup; not a product verdict |

Exact-SHA Full CI run `29695342023` independently passed:

- core non-PostgreSQL tests and deploy build/bundle checks;
- PostgreSQL integration and reporting tests;
- Research reproducibility and double-run gate;
- Ruff/baseline installation and required aggregate gate.

The CI API gives job success, not per-test counts or production-runtime evidence.

## Resilience contract matrix

| Scenario | Code mechanism | Test evidence | Runtime evidence | Status |
|---|---|---|---|---|
| Duplicate worker | session-scoped PostgreSQL advisory lock; one declared replica | PostgreSQL lock/contention tests passed in exact-SHA CI | actual owner/replicas unavailable | PARTIALLY_VERIFIED |
| Restart duplicate intent/fill | deterministic keys + recovery before READY | restart/crash/replay suites in Full CI | no production restart performed | PARTIALLY_VERIFIED |
| DB interruption | transaction boundaries, FAILED/DEGRADED recovery | failure-injection PostgreSQL suite in Full CI | no Railway outage test | PARTIALLY_VERIFIED |
| Stale heartbeat/data | readiness inference and entry gate | focused readiness/degraded tests passed | authenticated runtime unavailable | PARTIALLY_VERIFIED |
| API timeout | paper fetch 5 s; Research proxy 30 s, abort -> typed 504/502 | source/unit coverage partial | not induced in deployment | CODE_VERIFIED |
| Research job orphan | ownership lease/recovery services | job ownership/recovery unit suites in Full CI | volume/process state unavailable | PARTIALLY_VERIFIED |
| Research recovery failure | startup catches exception and continues | no lifespan/write-gate failure-injection test | unavailable | CONTRADICTED for fail-closed writes |
| Kill switch | production procedure stops worker; local control FREEZE only | kill/pause lifecycle tests in Full CI | no production control action | PARTIALLY_VERIFIED |
| Backup/restore | local runbook/drill | historical local evidence | Railway non-prod restore explicitly open | NOT_VERIFIABLE for Railway |
| Reconciliation | independent DB reconstruction script/runbook | PostgreSQL accounting tests in Full CI | production DB not queried | PARTIALLY_VERIFIED |

## Research recovery fail-open detail

During API lifespan, `_recover_research_jobs_on_startup()` attempts Research and Robustness
orphan recovery. Both broad exception handlers log and return; startup continues
(`paper_trading/readonly_api.py:51-85`). The comment says a recovery failure must not stop
the “read-only API”, but the same app immediately mounts and allowlists Research writes
(`readonly_api.py:89-109`). There is no degraded flag checked by POST handlers.

Job services have lease/ownership protections, so duplicate artifact corruption is not
asserted. The untested state is narrower: after recovery itself fails, the process accepts
new mutating requests without proving old ownership state. That can compound an unknown
Research job state or make operator diagnosis harder.

## Observability and incidents

### Available

- worker/API database fingerprint logs without credentials
  (`database_identity.py:23-76`);
- lock acquired/waiting logs (`application.py:291-329`);
- heartbeat and readiness reason fields;
- scheduler status/errors and audit events;
- error sanitization before API responses;
- incident template and one tabletop duplicate-fill incident.

### Gaps

- no API/UI field proves the worker lock owner; frontend omits runtime `instance_id`, while
  read-API `advisory_lock_held` is always false (C-FINDING-08);
- the incidents page is a regex view over recent audit events, not the incident register,
  and falls back to normal events when no match exists (C-FINDING-06);
- worker has no health port; operators depend on DB heartbeat/API/log correlation;
- no alert delivery/SLO paging integration is evidenced;
- production log retention, alert rules, replica count, DB fingerprint equality and current
  readiness are `NOT_VERIFIABLE`;
- Railway non-production restore drill remains open per Roadmap/runbook.

The runbooks correctly distinguish the production kill path (stop/scale worker to zero)
from the disabled control API. No runtime stop/restart was attempted in this audit.

## Candidate findings

| ID | Severity | Impact | Confidence | Stop criterion |
|---|---|---|---|---|
| C-FINDING-05 | P2 (Medium) | Failed Research/Robustness orphan recovery does not degrade or disable later write traffic, so unknown job ownership may be compounded. | High code / runtime occurrence unknown | If startup logs `research_job_recovery_on_startup_failed`, allow monitoring reads only; do not start/evaluate/invalidate Research jobs until ownership is reconciled. |
| C-FINDING-06 | P3 (Low) | Normal audit events can appear under “Errors / Incidents”, causing false incident signals. | High | Use repository incident register and raw event type, not this page alone. |
| C-FINDING-08 | P2 (Medium) | Execution-owner state cannot be proven from Monitor/API, weakening duplicate-worker diagnosis. | High | On ownership ambiguity, stop additional worker starts; inspect DB lock/logs and reconcile before restart. |

## NOT_VERIFIABLE

Production worker/API health, deployment SHA/digests, exact replica count, advisory lock
owner, database identity equality, current incidents, backups/restores, log retention,
alerting and recovery time. Missing access is not treated as a pass or failure.
