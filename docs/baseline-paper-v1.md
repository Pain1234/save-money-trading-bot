# Reproducible Paper-Trading Baseline (P1)

This document is the P1 baseline reference for the paper-trading stack. It records
production-shaped start paths, pinned runtime versions, dependency strategy, test
inventory, and baseline-release criteria. It does **not** change start commands,
strategy parameters, or deployment configuration.

**Related issues:** #7 (start documentation), #8 (runtime versions), #9 (test/CI
inventory), #10 (baseline tag — criteria defined here; tag creation is separate).

**Production deployment detail:** `docs/railway-paper-trading-dashboard-v1.md`

---

## Architecture summary

| Component | Production entry | Local minimum |
|-----------|------------------|---------------|
| Worker | `deploy/scripts/start-worker.sh` | PostgreSQL + `PAPER_TRADING_DATABASE_URL` |
| Read-only API | `deploy/scripts/start-api.sh` | Same database URL |
| Dashboard | `npm ci` → `npm run build` → `npm start` (Node **22+**) | `npm ci` → `npm run dev` (mock data by default) |
| Database | Railway PostgreSQL (production version externally verified/pending verification) | Local PostgreSQL **16** or `docker/docker-compose.paper-test.yml` |

**Dashboard modes (do not conflate):**

| Mode | Command | Data source |
|------|---------|-------------|
| Local UI dev | `npm ci` then `npm run dev` | Mock data unless `PRIVATE_PAPER_API_URL` is set |
| Production / Railway | `npm ci` then `npm run build` then `npm start` | Read-only paper API via `PRIVATE_PAPER_API_URL` (server-side) |
| Build verification | `npm ci` + build env vars (see test) | Requires `node_modules`; `next` missing without `npm ci` |

The paper-trading worker/API path is PostgreSQL-backed and matches Railway
production shape. Dashboard pages under `src/app/dashboard/` use live API data
in production builds; local `npm run dev` is for UI work with mocks.

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

**Production-shaped build (matches Railway / CI intent):**

```bash
npm ci
export SESSION_SECRET="…"                          # min 32 chars
export PRIVATE_PAPER_API_URL="http://127.0.0.1:8080"
export AUTH_USERNAME="monitor"
export AUTH_PASSWORD_HASH="…"                      # bcrypt hash
npm run build
npm start
```

Railway dashboard service uses `deploy/Dockerfile.dashboard` (Node 22, standalone
Next.js output). `npm ci` is **required** before `npm run build` — a fresh clone
without `node_modules` fails with `next: command not found`.

**Local UI development (mock data, no API required):**

```bash
npm ci
npm run dev
```

Open [http://localhost:3000](http://localhost:3000). To point local dev at a
running paper API, set `PRIVATE_PAPER_API_URL` in `.env.local` (see
`.env.example`).

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
- **Production image:** `pip install -e ".[api]"` in Dockerfile.
- **Baseline lock:** `requirements-baseline.txt` — transitive pins from a clean
  venv after `pip install ".[dev]"`. Regenerate with
  `python scripts/export_requirements_baseline.py` (prefer Python **3.12** to
  match `deploy/Dockerfile.paper-python`). Issue #8.
- **Reproducibility:** use the lock file for audit/reinstall; production Docker
  images remain the authoritative runtime artifact until tag gate closes.

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

### CI coverage

| Workflow | Scope |
|----------|-------|
| `.github/workflows/github-governance-setup.yml` | Governance script validation (path-filtered PRs) |
| `.github/workflows/ci.yml` | Mandatory CI: compile, governance tests, ruff, unit pytest, PostgreSQL integration (#53) |

Required status checks (for branch protection after #52): `validate`, `lint`, `test`, `postgres`.
See `docs/default-branch-migration-plan.md` § Branch protection plan.

Dashboard build test (`tests/deploy/test_dashboard_bundle.py`) is excluded from CI until
Node 22 is added to the workflow. Issue #58 closed: failure was missing `npm ci`
prerequisite, not a dashboard source defect.

---

## Baseline release tag (Issue #10)

### Naming

`baseline-paper-v1.0.0` (initial baseline), then `baseline-paper-v1.x` for
documentation-only or test-inventory updates without trading-logic changes.

### Tag criteria (all required)

- [x] This document merged and linked from `README.md`
- [x] P1 issues #7–#9 closed with evidence in PR #55
- [x] Start commands unchanged from `deploy/scripts/` (verified by review)
- [ ] At least one **documented** PostgreSQL test run (`-m postgres`) — CI job exists (`.github/workflows/ci.yml`); local run blocked without Docker on 2026-07-14; record CI run URL or execute locally before tag
- [x] Known failures/flakes recorded and resolved where applicable (dashboard build #58 — missing `npm ci`)
- [x] `CHANGELOG.md` section for the tag
- [x] No strategy-parameter or risk-limit changes in tagged commit range
- [ ] `requirements-baseline.txt` committed and regeneration script documented (Issue #8 follow-up) — added in this PR; regenerate on Python 3.12 before tag
- [x] Dashboard start/build prerequisites documented (local dev vs production; `npm ci` required)

### Tag creation (manual, after criteria met)

```bash
git tag -a baseline-paper-v1.0.0 <commit-sha> -m "P1 reproducible paper baseline"
git push origin baseline-paper-v1.0.0
```

Do not create the tag until exit criteria are agreed and recorded.

---

## P1 exit checklist (ROADMAP)

| Criterion | Status |
|-----------|--------|
| Baseline start documented | This document + README update |
| Versions recorded | Python 3.12 / Node 22 / Postgres 16 (local baseline); Railway Postgres version pending verification |
| Test commands documented | See table above |
| Known failures recorded | Dashboard build test (local) |
| Baseline tag exists | **Open** — prerequisites incomplete (PostgreSQL evidence, Python lock on 3.12, tag checklist above) |
| Full CI for tests | `.github/workflows/ci.yml` (#53) |
