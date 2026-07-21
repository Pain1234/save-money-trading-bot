# Test Coverage Gaps (Auditor C)

**Issue/SHA:** #371 / `7b78eb9996eb16e6d2ec6a00c2e1908c518682d9`

## Executive assessment

The repository has unusually broad deterministic Python coverage and a successful exact-SHA
Full CI run. The primary risk is not a lack of test quantity; it is a mismatch between what
some tests appear to prove and the production contract. In particular, the Playwright
Research smoke proves a deliberately GET-only stub rejects writes while the production API
deliberately allows Research writes. Green UI smoke must not be cited as evidence that the
Research Workspace is read-only.

## Coverage inventory

| Area | Positive coverage | Negative coverage | Gap status |
|---|---|---|---|
| Paper monitoring methods | GET route tests | POST -> 405 focused test | Good |
| Research read IDs | known records | unknown IDs/traversal/405 | Good |
| Artifact content | active sealed JSON/text | traversal, absolute/encoded path, symlink, tamper, missing, invalidated, media/size | Strong |
| Paper API serialization | Decimal/time/IDs | invalid cursor/limits/errors | Good |
| Dashboard field mapping | missing values, stale status, long overview IDs | several null-vs-zero tests | Good but C-FINDING-07 uncovered |
| Dashboard auth | Playwright happy-path login/logout; static matcher test | little direct negative session/cookie/rate-limit coverage | Gap |
| Research write auth | frontend middleware source assertion | no direct-backend authorization because none exists | Contract gap |
| CORS/CSRF | no permissive CORS in code; SameSite Lax | no Origin/token/header integration tests | Gap |
| Deployment entrypoints | Docker/TOML/script static tests + clean CI build | no runtime SHA/image parity assertion | Gap |
| Execution-owner visibility | lock behavior tested | no Monitor/API owner-observability contract | Gap |
| Incident semantics | status-card empty/error cases | no test forbids normal-event fallback | Gap |
| Secret redaction | wrong control key absent from response | no recursive/alias audit-payload redaction test | Gap |
| Research recovery | lease/orphan service tests | no API lifespan failure -> writes-disabled test | Gap |

## False-assurance analysis

### 1. Research Playwright “read-only” assertion targets a stub

`tests/visual/research-routes.spec.ts:3-9` explicitly says it runs against
`scripts/paper-api-stub.mjs` and does not start real Lab jobs. Lines 81-94 POST directly to
that stub and require 405. Static deploy tests further require the stub to reject all
Research writes (`tests/deploy/test_research_playwright_smoke.py:28-32`).

Production differs by design:

- Next routes export POST handlers (for example
  `src/app/api/research/experiments/route.ts:3-8` and
  `validation/route.ts:3-8`);
- FastAPI declares ten POST route shapes;
- readonly middleware explicitly lets those POSTs through
  (`readonly_api.py:98-109`, `research/api.py:791-812`).

Therefore the test is valid only as fixture-safety evidence. Its name/result must not be
used as production read-only evidence. This gap supports C-FINDING-01.

### 2. Deploy tests prove buildability, not immutable deployment identity

Exact-SHA CI deploy tests passed, but no endpoint or test compares:

- expected Git SHA vs worker/API/dashboard-reported SHA;
- Python dependency lock/image digest vs the Research run;
- worker vs API database fingerprint at runtime;
- declared vs actual Railway replica count/private networking.

Static entrypoint tests only assert that `RAILWAY_GIT_COMMIT_SHA` text is present
(`tests/deploy/test_railway_entrypoints.py:52`). This does not prove Railway injected it or
that a running service exposes it. This gap supports C-FINDING-02/-03.

### 3. Green API tests do not prove authenticated backend writes

FastAPI TestClient tests invoke the Research router without authentication, which matches
current code. Dashboard middleware tests are static/string or browser happy-path tests.
There is no end-to-end test that a direct backend POST is rejected without a service
credential, because the backend has no such credential boundary. This is a missing control,
not merely a missing test.

## Specific missing regression tests

Priority order reflects risk, not implementation authorization. No tests were added in this
audit.

| Priority | Proposed regression | Expected invariant |
|---|---|---|
| P1 | Direct FastAPI Research POST without backend/service credential | rejected; dashboard session alone is not forwarded as backend authority unless explicitly designed |
| P1 | Build same SHA twice from an isolated cache and compare locked dependency manifest/image provenance | dependency identity recorded and stable, or deliberate digest difference explained |
| P1 | Deployment verification endpoint/job for dashboard/API/worker SHA + image digest + DB fingerprint | known same revision/DB or fail closed |
| P2 | Force Research and Robustness startup recovery exceptions, then POST create/start/evaluate/invalidate | reads remain available; all writes return degraded/unavailable until recovery reconciles |
| P2 | `_sanitize_payload` nested dictionaries/lists and key aliases (`token`, `authorization`, `cookie`, `private_key`, URL credentials) | no synthetic marker survives serialization |
| P2 | Validation detail with `n_failed=0` and with missing manifest | render `0 failed` vs “Nicht verfügbar” distinctly |
| P2 | Incidents page with 20 normal events and zero regex matches | empty/no-incidents state; normal events never relabeled as incidents |
| P2 | Read API/Monitor execution owner | actual worker instance and advisory-lock observation are explicit; unknown is not serialized as false |
| P2 | Unauthenticated/malformed/expired session requests to each `/api/research/*` POST proxy | redirect/401 without backend call; method/body preserved only when authenticated |
| P2 | Login rate limit with spoofed/multiple `X-Forwarded-For`, restart and multiple app instances | client identity comes from trusted proxy contract; limit cannot be trivially bypassed |
| P3 | Cookie attributes and session expiry integration | HttpOnly/Secure/SameSite/Max-Age and expiry enforced |
| P3 | CSRF/Origin policy for logout and Research mutations | explicit documented outcome for cross-site POSTs |
| P3 | Artifact proxy headers | preserve `Content-Disposition`, `nosniff`, checksum/path and no-store policy |
| P3 | Public response security headers | HSTS/CSP/frame/referrer/nosniff policy present or explicitly accepted |

## Tests executed and not executed

### Executed locally

1. Focused API/security/artifact/read-write suite: **75 passed, 1 skipped**, pytest
   8.78 s, wall 9.626 s. Skip reason was not re-collected after the interruption and is not
   guessed.
2. Safe resilience/degraded/recovery non-PostgreSQL suite: **24 passed, 14 deselected**,
   pytest 0.44 s, wall 1.256 s.
3. Synthetic sanitizer probe: top-level `api_key` redacted; `token` and nested `secret` not
   redacted.
4. Next build: compilation succeeded; later invalid due shared parent-worktree dependency
   conflict. It is not reported as product pass/fail.

### Exact-SHA remote CI inspected

Full CI run `29695342023` on the audit SHA: `full-quality`, `core-tests`, deploy tests,
PostgreSQL/reporting, Research reproducibility/double-run and aggregate required job all
successful. Per-test totals were not available from the read-only job metadata inspected.

### Not executed by Auditor C

- `npm run test:unit`: Vitest was absent from the local installed dependency set.
- `npm run test:research-smoke`: no clean worktree-local install/build; exact-SHA CI deploy
  build was used only as remote evidence. The smoke is non-required in Fast CI.
- local PostgreSQL suites: no audit DB URL/client available; exact-SHA CI evidence inspected.
- live/network/soak tests: intentionally not run.
- authenticated production browser/API tests, Railway chaos/restart/restore: not authorized
  or not accessible.

No non-executed suite is reported as passing.
