# System Audit Inventory

**Audit issue:** [#371](https://github.com/Pain1234/save-money-trading-bot/issues/371)
**Inventory freeze:** `2026-07-19T16:59:23.3276330Z`
**Audit start:** `2026-07-19T16:52:07.7739084Z`
**Repository:** `Pain1234/save-money-trading-bot`
**Audit branch:** `audit/full-system-behavior-verification`

This file is the pre-audit snapshot. Later runtime observations and test results belong in
the area audit documents, not in retroactive edits to this inventory.

## 1. Git identity and working-tree state

| Item | Frozen value | Evidence command |
|---|---|---|
| Local audit `HEAD` | `7b78eb9996eb16e6d2ec6a00c2e1908c518682d9` | `git rev-parse HEAD` |
| `origin/main` after `git fetch origin --prune` | `7b78eb9996eb16e6d2ec6a00c2e1908c518682d9` | `git rev-parse origin/main` |
| Default branch | `main` | GitHub repository metadata |
| Open pull requests | `0` | `gh pr list --state open --limit 200` |
| Open issues | `35`, including audit issue #371 | `gh issue list --state open --limit 500` |
| Commit combined status | `success`, three reported statuses | GitHub commit status API for the frozen SHA |
| Local branches | `46` | `git for-each-ref refs/heads` |
| `origin/*` refs | `139` including `origin/HEAD` | `git for-each-ref refs/remotes/origin` |

The new worktree reported three modified files immediately after checkout:

- `docs/product-specification.md`
- `docs/risk-specification.md`
- `docs/strategy-specification.md`

This is not content drift. For every file, `git hash-object --no-filters` exactly matched
the `HEAD:<path>` blob, while the filtered hash differed because `.gitattributes` declares
`text eol=lf` and the committed blob contains CRLF. `git diff --ignore-space-at-eol` returned
zero lines. No file was restored, normalized, staged, or discarded. This reproducibility
defect remains visible in `git status` and must not be confused with audit changes.

The original checkout also contained the unrelated untracked worktree directory
`save-money-trading-bot-wt111/`; it was not modified. The audit therefore runs in the
separate `audit-wt371` worktree created from `origin/main`.

### Active linked worktrees

| Branch | HEAD | Worktree |
|---|---|---|
| `audit/full-system-behavior-verification` | `7b78eb9` | `save-money-trading-bot/audit-wt371` |
| `fix/208-benchmark-cost-parity` | `9f50901` | primary checkout |
| `perf/96-rebased-now` | `64bd964` | `save-money-trading-bot-wt111` |
| `chore/ci-actions-optimization` | `0306a56` | `save-money-trading-bot-ci-opt` |
| `main` | `00a5fd9` (359 commits behind `origin/main`) | `save-money-trading-bot-main-wt` |
| `perf/96-rebased` | `0ed4655` | `save-money-trading-bot-p25-rebase` |
| `ops/103-prod-dashboard-acceptance` | `ddff01f` | `save-money-trading-bot-rebase` |
| `test/102-dashboard-perf-regression` | `4839e91` | `save-money-trading-bot-wt115` |

### Last 20 merge commits on `origin/main`

```text
7b78eb9 Merge pull request #370 from Pain1234/p5/204-pre-oos-calendar-blocker
c469b65 Merge pull request #369 from Pain1234/p5/204-pre-oos-gate
0e33637 Merge pull request #368 from Pain1234/p5/196-gate1-complete
8bb39c1 Merge pull request #367 from Pain1234/p5/196-entry-gate-freeze
aa0e232 Merge pull request #366 from Pain1234/fix/363-research-sealed-symbol-constraints-v2
dcd6435 Merge pull request #365 from Pain1234/test/250-p4-final-acceptance-current-main
1516ddb Merge pull request #360 from Pain1234/fix/monitor-number-formatting
c979738 Merge remote-tracking branch 'origin/main' into fix/monitor-number-formatting
c9ee915 Merge pull request #362 from Pain1234/feat/research-overview-scorecard-binding
d6fd17c Merge remote-tracking branch 'origin/main' into fix/monitor-number-formatting
1e83765 Merge remote-tracking branch 'origin/main' into feat/research-overview-scorecard-binding
26dd7aa Merge pull request #361 from Pain1234/feat/357-safe-artifact-content
b76d7bb Merge pull request #356 from Pain1234/feat/303-research-responsive
fa1a998 merge(main): resync #303 after #294 docs landed on main
35b4fa6 Merge pull request #354 from Pain1234/docs/294-p5-scorecard-policy-bind
c3e7aa9 merge(main): sync #303 with forensics #355; keep changelog sections
3f7f652 Merge pull request #355 from Pain1234/feat/302-research-forensics
5cb3a7b Merge pull request #352 from Pain1234/feat/p4-scorecard-detail-api
293f832 Merge pull request #353 from Pain1234/test/250-p4-final-acceptance
2870bc2 Merge pull request #351 from Pain1234/refactor/301-research-routes
```

### Tags

Only three tags existed: `p2.5-production-baseline`, `baseline-paper-v1.0.1`, and
`baseline-paper-v1.0.0`.

## 2. GitHub issues and milestones

### Open issues at freeze

```text
#11  P2   Backup/restore verification
#46  P6   Paper-vs-backtest execution decay
#47  P5   Strategy V1 OOS overfitting controls
#104 #105 #106 #128 #129 #130 #134 #135 #139  P7 planning/identity/portfolio work
#182 P6 public/private soak framework boundary
#183 P7 public/private candidate boundary
#184 P8 isolated private micro-live repository
#185 P9 private controlled-scaling configuration
#196 P5 entry gate and Strategy V1 candidate freeze
#204 P5 final untouched OOS execution (blocked)
#205 P5 final decision
#251 #252 #253 #254 P5 robustness executions (not executed by this audit)
#255 P5 validation-study registration
#256 #257 #258 #259 #260 #261 #262 P6 soak program
#304 #305 P7 timeframe and StrategyIntent planning
#345 Research evidence-confidence follow-up
#371 Full-system behavior and safety audit
```

### Milestone snapshot

| Milestone | Open | Closed | GitHub state |
|---|---:|---:|---|
| P0 – Governance and Scope Freeze | 0 | 14 | open |
| P1 – Reproducible Baseline Release | 0 | 11 | open |
| P2 – Operational Reliability | 1 | 11 | open |
| P3 – Versioned Historical Market Data | 0 | 11 | open |
| P4 – Research Engine | 0 | 54 | open |
| P5 – Honest Validation of Trend Strategy V1 | 9 | 9 | open |
| P6 – Paper Trading Soak | 9 | 0 | open |
| P7 – Multi-Asset and Independent Strategy Candidates | 12 | 3 | open |
| P8 – Separate Micro-Live System | 1 | 0 | open |
| P9 – Controlled Scaling | 1 | 0 | open |
| P2.5 – Dashboard Performance & Responsiveness | 0 | 18 | open |

GitHub milestone objects remain technically `open` even where `ROADMAP.md` describes a
phase as complete. That distinction is preserved for later contract evaluation.

## 3. Runtime and dependency inventory

| Component | Observed locally | Repository/CI contract | Status at freeze |
|---|---|---|---|
| Python | `3.14.5` | CI uses `3.12`; `pyproject.toml` permits `>=3.11` and configures Ruff/Mypy for 3.11 | environment drift; tests not yet run |
| Node.js | `24.16.0` | CI uses Node `22`; local cloud note mentions Node 24 | supportedness not yet verified |
| npm | `11.13.0` | lockfile-based `npm ci` | not yet verified |
| GitHub CLI | `2.96.0` | authenticated as `Pain1234` | available |
| PostgreSQL client | `pg_isready` absent from `PATH` | PostgreSQL 16 in CI/runbooks | local runtime not verifiable at freeze |

### Dependency lock material

| File | SHA-256 |
|---|---|
| `package-lock.json` | `F64B7B25123B498BE9787E2DC51552774E66FA436CF98F486683BCCA764B72A1` |
| `requirements-baseline.txt` | `EBF2E5EBE646A5E927370BDBB8994C6E6FC58433740AE1E655E93C09354B51BA` |

Python project metadata is not a fully pinned lockfile: direct dependencies use lower bounds;
`requirements-baseline.txt` is the exported reproducibility baseline. Node dependencies are
resolved by `package-lock.json`.

## 4. Database and data inventory

- Database implementation: PostgreSQL through SQLAlchemy/psycopg.
- Migration chain present: `001_initial_paper_trading` through
  `011_market_data_raw_fetch_observations`.
- Repository schema head: migration `011`.
- Local applied schema: `NOT_VERIFIABLE` at freeze because no database URL was set and
  PostgreSQL tools were absent from `PATH`.
- Runtime/Railway applied schema: `NOT_VERIFIABLE` at freeze.
- `PAPER_TRADING_DATABASE_URL`, `RAILWAY_ENVIRONMENT`, and `CI` were not set in the audit shell.
- No database was reset, migrated, written, or queried during inventory capture.
- No research run or P5 dataset was opened. No private P5 evidence was read.
- Repository test inputs exist under `tests/**/fixtures`, `examples/research`, and committed
  deterministic operations JSON. No synthetic audit fixture had been created at freeze.

## 5. Services and start paths

Present service packages:

1. `strategy_engine`
2. `risk_engine`
3. `backtester`
4. `market_data`
5. `paper_trading`
6. `research`
7. `trading_constraints`

| Deployable service | Image/config | Start path | Frozen default profile |
|---|---|---|---|
| Paper worker | `deploy/Dockerfile.paper-python`, Railway worker TOML | `deploy/scripts/start-worker.sh` | production-mode paper process; scheduler on; control API off; public API off; Hyperliquid testnet; funding off unless overridden |
| Paper/Research API | same Python image, Railway API TOML | `deploy/scripts/start-api.sh` | read API on configured port; control API off; research roots under `/app`; deploy commit copied from `RAILWAY_GIT_COMMIT_SHA` when present |
| Dashboard | `deploy/Dockerfile.dashboard`, Railway dashboard TOML | `node server.js` | Next.js standalone server; `/login` health check |

Worker deployment declares one Railway replica, but actual replica count, advisory-lock owner,
environment overrides, and running revision were not visible during inventory capture.

## 6. Deployment observation

At `2026-07-19T16:59:23.3276330Z`, a read-only browser navigation to
`https://bot.save-money.xyz/` succeeded and redirected to
`/login?next=%2Fdashboard`. The page title was `SAVE-MONEY BOT — Hyperliquid Trading Bot` and
the visible contract described a read-only paper-trading monitor. No credentials were entered.

The login page exposed hashed Next.js static assets, including CSS
`1a66cb1759d65cad.css` and webpack chunk `12612a7232180e44.js`, but no repository commit SHA.

| Service | Expected SHA | Observed running SHA | Status |
|---|---|---|---|
| Dashboard | frozen `origin/main` SHA unless a separately documented deploy pin says otherwise | not exposed | `NOT_VERIFIABLE` |
| Paper/Research API | frozen `origin/main` SHA unless Railway revision differs | private/not exposed | `NOT_VERIFIABLE` |
| Paper worker | frozen `origin/main` SHA unless Railway revision differs | not exposed | `NOT_VERIFIABLE` |
| Docker image digests | repository build from frozen SHA expected | not exposed | `NOT_VERIFIABLE` |
| Railway revisions | repository deploy config expected | not exposed | `NOT_VERIFIABLE` |

The public endpoint proves only reachability and authentication gating. It does not prove
dashboard/API/worker commit parity, authenticated UI semantics, worker health, or economic
state.

## 7. CI and discovered test commands

Active workflows are `.github/workflows/ci-fast.yml` and `ci-full.yml`; `ci.yml` is a manual
rollback stub. The frozen `origin/main` commit reports overall GitHub status success with three
statuses. Full CI uses Python 3.12, Node 22, and PostgreSQL 16.

Discovered project commands (execution results are recorded later):

- `python -m ruff check .`
- `python -m mypy .`
- `python -m pytest tests/ --ignore=tests/deploy -m "not postgres and not live and not soak and not reporting" -q`
- `python -m pytest tests/market_data -m "not live and not postgres" -q --tb=short`
- `python -m pytest tests/deploy -q --tb=short`
- `python -m pytest tests/paper_trading tests/market_data -m "postgres and not soak" -q --tb=short`
- `python -m pytest tests/research tests/paper_trading/test_backtester_parity.py tests/paper_trading/test_backtester_signal_parity.py -q --tb=short`
- `npm run test:unit`
- `npm run build`
- `npm run test:research-smoke`
- `git diff --check`

## 8. Public/private boundary

The public repository documents a private-edge concept and separate private P5 storage, but
no private repository contents or private repository names were enumerated during inventory.
Only public references in governance documents and issues are in scope. Secrets, private
telemetry, private candidate values, and P5 holdout results are excluded.
