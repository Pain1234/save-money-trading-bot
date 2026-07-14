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
| Dashboard | `npm run build` / `npm start` (Node) | UI dev uses mock data unless API URL configured |
| Database | Railway PostgreSQL (production version externally verified/pending verification) | Local PostgreSQL **16** or `docker/docker-compose.paper-test.yml` |

The dashboard UI (`npm run dev`) uses mock data for local UI work. The
paper-trading worker/API path is PostgreSQL-backed and matches Railway production
shape.

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

```bash
npm ci
npm run build
npm start
```

Railway dashboard service uses `deploy/Dockerfile.dashboard` (Node 22, standalone
Next.js output). Local UI development:

```bash
npm install
npm run dev
```

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
- **Production image:** `pip install -e ".[api]"` in Dockerfile (no separate lock file).
- **Reproducibility note:** exact transitive versions depend on install time unless
  captured in a built Docker image or a future lock export. P1 records the runtime
  and direct dependency bounds; a full pip freeze is optional for tag notes.

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

Environment: Windows, Python 3.14 (local), no `PAPER_TRADING_DATABASE_URL`.

```bash
python -m pytest tests/ --ignore=tests/paper_trading --ignore=tests/market_data -q
# Result: 262 passed, 1 failed (2026-07-13)
```

Failure:

| Test | Reason |
|------|--------|
| `tests/deploy/test_dashboard_bundle.py::test_dashboard_build_succeeds` | `npm run build` exit code 1 in local environment — **pre-existing** on default branch; unaffected by this docs-only PR; tracked in Issue #58 |

PostgreSQL-marked tests were **not executed** in this run (require database setup).

### CI coverage

| Workflow | Scope |
|----------|-------|
| `.github/workflows/github-governance-setup.yml` | Governance script validation (path-filtered PRs) |
| `.github/workflows/ci.yml` | Mandatory CI: compile, governance tests, ruff, unit pytest, PostgreSQL integration (#53) |

Required status checks (for branch protection after #52): `validate`, `lint`, `test`, `postgres`.
See `docs/default-branch-migration-plan.md` § Branch protection plan.

Dashboard build test (`tests/deploy/test_dashboard_bundle.py`) is excluded from CI until
Node 22 is added to the workflow; known local failure tracked in Issue #58.

---

## Baseline release tag (Issue #10)

### Naming

`baseline-paper-v1.0.0` (initial baseline), then `baseline-paper-v1.x` for
documentation-only or test-inventory updates without trading-logic changes.

### Tag criteria (all required)

- [x] This document merged and linked from `README.md`
- [x] P1 issues #7–#9 closed with evidence in PR #55
- [x] Start commands unchanged from `deploy/scripts/` (verified by review)
- [x] At least one documented test run with PostgreSQL (`-m postgres`) — CI job `postgres` in `.github/workflows/ci.yml` (local run blocked without Docker; see Issue #10 PR)
- [x] Known failures/flakes recorded (see table above; dashboard build #58)
- [x] `CHANGELOG.md` section for the tag
- [x] No strategy-parameter or risk-limit changes in tagged commit range

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
| Baseline tag exists | **Ready** — tag `baseline-paper-v1.0.0` after CI PR merge |
| Full CI for tests | `.github/workflows/ci.yml` (#53) |
