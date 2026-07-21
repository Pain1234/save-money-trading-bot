# Reproducible Paper-Trading Baseline (P1)

This document is the P1 baseline reference for the paper-trading stack. It records
production-shaped start paths, pinned runtime versions, dependency strategy, test
inventory, and baseline-release criteria. It does **not** change start commands,
strategy parameters, or deployment configuration.

**Related issues:** #7 (start documentation), #8 (runtime versions), #9 (test/CI
inventory), #10 (baseline tag — **released** as `baseline-paper-v1.0.0` at
`daacb627`). Changes in PR #63 are **post-tag artifacts** (not part of v1.0.0);
`baseline-paper-v1.0.1` may follow for doc/lock fixes only.

**Production deployment detail:** `docs/railway-paper-trading-dashboard-v1.md`

---

## Architecture summary

| Component | Production entry | Local minimum |
|-----------|------------------|---------------|
| Worker | `deploy/scripts/start-worker.sh` | PostgreSQL + `PAPER_TRADING_DATABASE_URL` |
| Read-only API | `deploy/scripts/start-api.sh` | Same database URL |
| Dashboard | `npm ci` → `npm run build` → `node server.js` (Node **22+**, standalone) | `npm ci` → `npm run dev` (requires env vars for `/dashboard`) |
| Database | Railway PostgreSQL (production version externally verified/pending verification) | Local PostgreSQL **16** or `docker/docker-compose.paper-test.yml` |

**Dashboard modes (do not conflate):**

| Mode | Command | Runtime | Data source |
|------|---------|---------|-------------|
| Local Next dev | `npm ci` then `npm run dev` | `next dev` | Server routes under `/dashboard` call the paper API and **require** `PRIVATE_PAPER_API_URL` (see `src/lib/paper-api/client.ts` — throws if unset). Marketing/landing components may still use static mock data; monitoring pages do not. |
| Local production build | `npm ci` then `npm run build` then `npm start` | `next start` | Same server-side env as Railway (`PRIVATE_PAPER_API_URL`, auth vars) |
| Railway / Docker | `deploy/Dockerfile.dashboard` | `node server.js` (standalone output) | Read-only paper API via `PRIVATE_PAPER_API_URL` |

The paper-trading worker/API path is PostgreSQL-backed and matches Railway
production shape. Dashboard pages under `src/app/dashboard/` fetch live API data
via server components; they do not use `@/lib/mock-data`.

---

## Minimum environment

### Required for worker or API

| Variable | Purpose |
|----------|---------|
| `PAPER_TRADING_DATABASE_URL` | SQLAlchemy URL (`postgresql+psycopg://…`) |

### Common worker defaults (set in `deploy/scripts/start-worker.sh`)

| Variable | Default | Notes |
|----------|---------|-------|
| `PAPER_API_ENABLED` | `false` | Embedded API in worker process |
| `PAPER_PRODUCTION_MODE` | `true` | Production-shaped runner |
| `PAPER_CONTROL_API_ENABLED` | `false` | Mutating control API off by default |
| `PAPER_SCHEDULER_ENABLED` | `true` | Internal scheduler on |
| `HYPERLIQUID_NETWORK` | `testnet` | Public market-data network |
| `PAPER_FUNDING_ENABLED` | `false` | Funding simulation off by default |

See `.env.example` for Hyperliquid client tuning. Never commit secrets.

### Local PostgreSQL (integration tests / local worker)

**Option A — Docker Compose (recommended for tests):**

```bash
docker compose -f docker/docker-compose.paper-test.yml up -d
export PAPER_TRADING_DATABASE_URL="postgresql+psycopg://postgres:postgres@localhost:5433/paper_trading_test"
```

**Option B — native PostgreSQL 16:** see `services/paper_trading/README.md`.

---

## Start commands (production paths — documentation only)

These are the authoritative production-shaped commands. Do not alter them in P1.

### Worker

```bash
export PAPER_TRADING_DATABASE_URL="postgresql+psycopg://…"
pip install -e ".[api]"
deploy/scripts/start-worker.sh
```

`start-worker.sh` runs, in order:

1. `python -m alembic upgrade head`
2. `python scripts/verify_paper_state.py --database-url-env PAPER_TRADING_DATABASE_URL`
3. `python -m paper_trading`

Railway: `deploy/railway/paper-trading-worker.toml` → same script via Dockerfile.

### Read-only API

```bash
export PAPER_TRADING_DATABASE_URL="postgresql+psycopg://…"
pip install -e ".[api]"
deploy/scripts/start-api.sh
```

Runs `python -m paper_trading.api_runner` on `PAPER_API_HOST`/`PAPER_API_PORT`
(default `0.0.0.0:8080`).

### Dashboard

**Required env vars (local dev and production builds):**

| Variable | Purpose |
|----------|---------|
| `PRIVATE_PAPER_API_URL` | Read-only paper API base URL (server-side only) |
| `SESSION_SECRET` | Session encryption (min 32 chars) — required for `npm run build` |
| `AUTH_USERNAME` | Dashboard login username |
| `AUTH_PASSWORD_HASH` | bcrypt hash for dashboard login |

**Production-shaped build (matches Railway / CI):**

```bash
npm ci
export SESSION_SECRET="…"                          # min 32 chars
export PRIVATE_PAPER_API_URL="http://127.0.0.1:8080"
export AUTH_USERNAME="monitor"
export AUTH_PASSWORD_HASH="…"                      # bcrypt hash
npm run build
npm start                                        # next start locally
```

Railway dashboard service uses `deploy/Dockerfile.dashboard` (Node 22, standalone
Next.js output, **`CMD ["node", "server.js"]`** — not `npm start`). `npm ci` is
**required** before `npm run build` — a fresh clone without `node_modules` fails
with `next: command not found`.

**Local Next.js development:**

```bash
npm ci
# .env.local — copy from .env.example
export PRIVATE_PAPER_API_URL="http://127.0.0.1:8080"
export SESSION_SECRET="…"
export AUTH_USERNAME="monitor"
export AUTH_PASSWORD_HASH="…"
npm run dev
```

Open [http://localhost:3000](http://localhost:3000). Without `PRIVATE_PAPER_API_URL`,
server-side dashboard routes error at runtime (`client.ts` throws). Start the
read-only paper API (`deploy/scripts/start-api.sh`) or point at a remote instance.

---

## Runtime and dependency versions

Recorded baseline (from repository artifacts, 2026-07):

| Runtime | Baseline version | Source |
|---------|------------------|--------|
| Python | **3.12** (production images) | `deploy/Dockerfile.paper-python` |
| Python (minimum) | >=3.11 | `pyproject.toml` `requires-python` |
| Node.js | **22** (LTS bookworm-slim) | `deploy/Dockerfile.dashboard` |
| PostgreSQL (local baseline) | **16** | `docker/docker-compose.paper-test.yml` (`postgres:16-alpine`) |
| PostgreSQL (Railway production) | **Pending verification** | Not recorded in repository artifacts; confirm via Railway plugin or service settings |

### Python dependency strategy

- **Declared:** `pyproject.toml` with lower-bound pins (`>=`).
- **Install (dev/tests):** `pip install -e ".[dev]"` or `pip install -e ".[api]"`.
- **Production image:** `deploy/Dockerfile.paper-python` installs
  `requirements-baseline.txt`, then `pip install -e ".[api]" --no-deps`
  (AUD-P1-014 / [#377](https://github.com/Pain1234/save-money-trading-bot/issues/377)).
- **Baseline lock:** `requirements-baseline.txt` — transitive **PyPI** pins from a clean
  venv after `pip install -e ".[dev]"`. Regenerate with
  `py -3.12 scripts/export_requirements_baseline.py` (**Python 3.12 required**,
  matches `deploy/Dockerfile.paper-python`). Local project refs are stripped.
  Issue #8.
- **Reproducibility / promotion evidence:** same Git SHA rebuilds are only comparable when
  the baseline lock content and resulting image digest are recorded. Do not treat a
  rebuilt Python image as promotion evidence without matched digest + baseline hash.

### Node dependency strategy

- **Lock file:** `package-lock.json` — use `npm ci` for reproducible installs.
- **Dashboard build:** requires Node 22+ (matches Docker image).

---

## Database migrations

Alembic revisions **001–009** (latest: `009_soak_run_identity`).

```bash
python -m alembic upgrade head
python scripts/verify_pg_schema.py   # optional schema check
```

Worker pre-deploy on Railway: `deploy/scripts/pre-deploy-migrate.sh`.

---

## Test inventory

Collected tests (2026-07-13, `python -m pytest tests/ --collect-only -q`): **782**.

### Commands

| Scope | Command |
|-------|---------|
| Full suite | `python -m pytest tests/ -v` |
| Paper + PostgreSQL | `python -m pytest tests/paper_trading -m postgres -v` |
| Exclude live network | `python -m pytest tests/ -m "not live" -v` |
| Governance unit tests | `python -m unittest tests/governance/test_github_project_setup.py -v` |
| Lint | `ruff check .` |
| Dashboard visual | `npm run test:visual` (Playwright) |

### Pytest markers (`pyproject.toml`)

| Marker | Meaning |
|--------|---------|
| `postgres` | Requires `PAPER_TRADING_DATABASE_URL` and PostgreSQL |
| `live` | Optional Hyperliquid network smoke tests |
| `soak` | Long-running deterministic soak tests |

### Recorded baseline run (without PostgreSQL)

Environment: Windows, Python 3.14 (local), no `PAPER_TRADING_DATABASE_URL`, no
Docker (PostgreSQL container unavailable).

**PR #55 documented run (2026-07-13):**

```bash
python -m pytest tests/ --ignore=tests/paper_trading --ignore=tests/market_data -q
# Collected subset; result: 262 passed, 1 failed
```

| Test | Outcome | Notes |
|------|---------|-------|
| `tests/deploy/test_dashboard_bundle.py::test_dashboard_build_succeeds` | Failed in PR #55 run | Root cause: **`npm ci` not run`** — `next` missing from PATH. Resolved in Issue #58 (2026-07-14): after `npm ci`, build passes on Node 24 with test env vars. Baseline requires Node **22+** and `npm ci` before any build. |

**Follow-up run (2026-07-14, same machine after `npm ci`):**

```bash
python -m pytest tests/deploy/test_dashboard_bundle.py::test_dashboard_build_succeeds -v
# 1 passed

python -m pytest tests/ --ignore=tests/paper_trading --ignore=tests/market_data -q
# 288 passed
```

### PostgreSQL integration run

**Not executed locally (2026-07-14):** Docker CLI unavailable on baseline Windows
host — `docker compose -f docker/docker-compose.paper-test.yml up -d` could not
run. Required steps when Docker is available:

```bash
docker compose -f docker/docker-compose.paper-test.yml up -d
export PAPER_TRADING_DATABASE_URL="postgresql+psycopg://postgres:postgres@localhost:5433/paper_trading_test"
python -m alembic upgrade head
python -m pytest tests/paper_trading -m postgres -v
```

**CI:** `.github/workflows/ci.yml` job `postgres` runs this gate on GitHub Actions
(Ubuntu + service container). Local or CI evidence required before tag; this
follow-up records the local blocker honestly.

### CI coverage (782 collected total — not all run in CI)

| Workflow job | Approx. scope | Notes |
|--------------|---------------|-------|
| `validate` | compileall, governance unit tests, PR whitespace | Always |
| `lint` | `ruff check .` | Always |
| `test` | ~609 tests: all except `tests/deploy`, excluding `-m postgres`, `-m live`, `-m soak` | Includes `paper_trading` unit tests and non-live `market_data` |
| `test-market-data` | `tests/market_data -m "not live"` | Websocket/regression coverage |
| `test-deploy` | `tests/deploy` (Node 22 + `npm ci`) | Dashboard build + bundle checks |
| `postgres` | `tests/paper_trading -m "postgres and not soak"` | PostgreSQL service container |

**Not in CI:** `-m live` (network smoke), `-m soak` (long-running), and any tests
outside the above jobs. Reconcile counts with `pytest --collect-only` when the
suite changes.

Branch protection with **required** status checks is enforced on `main` via
GitHub **repository rulesets** (Issue #65; classic branch-protection API remains
unavailable on this private free plan — rulesets are the active mechanism).
See `docs/branch-protection.md` for the check list. CI runs on all PRs targeting
`main`.

---

## Baseline release tag (Issue #10)

### Status: **released**

Tag `baseline-paper-v1.0.0` points to `daacb627` (merge of PR #62, 2026-07-14).
Do **not** move or retag this release.

PR #63 and later commits are **post-tag artifacts** (Python 3.12 lock, CI
coverage, dashboard documentation). Optional patch tag `baseline-paper-v1.0.1`
may follow PR #63 merge for documentation/lock fixes only.

### Naming

`baseline-paper-v1.0.0` (initial baseline), then `baseline-paper-v1.x` for
documentation-only or test-inventory updates without trading-logic changes.

### Tag criteria at v1.0.0 (met)

- [x] This document merged and linked from `README.md`
- [x] P1 issues #7–#9 closed with evidence in PR #55
- [x] Start commands unchanged from `deploy/scripts/` (verified by review)
- [x] PostgreSQL test run — CI `postgres` job (`.github/workflows/ci.yml`)
- [x] Known failures/flakes recorded and resolved where applicable (dashboard build #58 — missing `npm ci`)
- [x] `CHANGELOG.md` section for the tag
- [x] No strategy-parameter or risk-limit changes in tagged commit range
- [x] Dashboard start/build prerequisites documented

### Post-tag follow-ups (PR #63, not in v1.0.0)

- [ ] `requirements-baseline.txt` regenerated on Python 3.12 (portable PyPI pins)
- [ ] Extended CI jobs (`test-market-data`, `test-deploy`)
- [ ] Dashboard env-var documentation corrected

---

## P1 exit checklist (ROADMAP)

| Criterion | Status |
|-----------|--------|
| Baseline start documented | This document + README update |
| Versions recorded | Python 3.12 / Node 22 / Postgres 16 (local baseline); Railway Postgres version pending verification |
| Test commands documented | See table above |
| Known failures recorded | Dashboard build test (local) |
| Baseline tag exists | **Released** — `baseline-paper-v1.0.0` at `daacb627` (PR #62) |
| Full CI for tests | `.github/workflows/ci-fast.yml` + `ci-full.yml`; ruleset-required checks on `main` (#65) |
