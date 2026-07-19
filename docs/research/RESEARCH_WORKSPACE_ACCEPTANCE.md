# Research Workspace manual UI acceptance (Issue #250 / P4.8)

Manual click-through checklist for the Research Workspace UI. Closes the
remaining "manuelle UI-Abnahme mit gültigem Dataset-Katalog" theme carried by
Issue #242 (Strategy Lab) and required by Issue #250 (E2E / Reproducibility /
UI acceptance). Run this against a **local** dev server with the committed
`examples/research/local_lab/` fixture catalog — never against production
data, and never record private Strategy V1 economic metrics here (see
`docs/research/p5/P5_PUBLIC_PRIVATE_ARTIFACTS.md`).

## Scope

Covers: Strategy catalog, Strategy Lab, Run start/poll/detail, Kurs & Trades
chart, Compare, Robustness, Gates (read-only smoke), Validation Studies,
Scorecard binding (#292 / #357 / #358), Research route densify (#301),
forensics (#302), responsive/a11y (#303), double-start protection,
dataset-integrity fail-closed behavior, and the durable job ownership /
restart-recovery contract exercised in API E2E.

**Final acceptance pass (BOT 3B, 2026-07-19):** recorded against
`origin/main` SHA `1516ddb08efe7fc52452ced9d4c86814db838130` with Railway
production deployment parity (dashboard + API + worker SUCCESS at the same
SHA). Close recommendation for #250 / #295 is for **human** decision — this
doc uses **`Refs #250`** until a human comments `Closes #250`.

## Playwright Research smoke (Issue #250)

Issue #250 requires Playwright + API E2E + documented manual UI acceptance.

**Shipped on `main`:** stub-backed Research **route smoke** + a11y/responsive —

- `tests/visual/research-routes.spec.ts`
- `tests/visual/research-a11y-responsive.spec.ts`
- `tests/visual/research-overview-scorecard.spec.ts` (READY / Legacy / Invalidated)
- Research fixtures in `scripts/paper-api-stub.mjs` (GET/HEAD only; POST → 405)
- Run: `npm run test:research-smoke` (uses `playwright.config.ts` webServers)
- CI: visible non-required job `research-playwright-smoke` in
  `.github/workflows/ci-fast.yml` (runs when `research`, `deploy`, or
  `run_all_fast`; not part of `fast-ci-required`)
- Static wiring: `tests/deploy/test_research_playwright_smoke.py`

What it covers: login → Monitor regression → Overview / Strategien /
Strategy detail (scorecard empty bind) / Experiments empty / Lab ready /
Compare empty / Robustheit empty / Validierung empty — no private metrics;
Overview visual fixtures for READY / Legacy / Invalidated pin states.

What it does **not** cover (API E2E / unit instead):

- Starting a real Lab job against `local_lab` + clean git (API E2E)
- Running / Completed / Failed experiment detail polling (API E2E)
- Compare of two real runs; Robustness / Validation create+detail (API E2E)
- Scorecard evaluate + sealed validation pin (scorecard E2E + overview fixtures)

## Prerequisites

```powershell
python scripts/prepare_research_lab_local.py
$env:RESEARCH_REPO_ROOT = "<repo-root>"
$env:RESEARCH_ARTIFACTS_ROOT = "<repo-root>"
$env:RESEARCH_DATASET_CATALOG_PATH = "<repo-root>\examples\research\local_lab\catalog.json"
# Keep the git working tree clean — do NOT set RESEARCH_ALLOW_DIRTY_GIT for
# this acceptance pass (that flag is a documented exception for automated
# tests only, per examples/research/README.md).
# Note: `tests/research/test_e2e_acceptance.py` isolates provenance to a clean
# `git archive` snapshot of HEAD (and prints ambient `git status --porcelain`
# for CI diagnosis); it still never sets RESEARCH_ALLOW_DIRTY_GIT.
PAPER_API_ENABLED=1 PAPER_API_PORT=8080 python -m paper_trading.api_runner
```

In a second shell: `npm run dev`, then sign in with your local
`AUTH_USERNAME` / `AUTH_PASSWORD_HASH` (see `AGENTS.md` Cursor Cloud section
for the dashboard `.env.local` setup, including the `\$` escaping gotcha).

## Deployment parity (BOT 3B — 2026-07-19)

| Surface | SHA | Source |
|---------|-----|--------|
| `origin/main` / acceptance HEAD | `1516ddb08efe7fc52452ced9d4c86814db838130` | `git rev-parse` |
| Railway `paper-trading-dashboard` (production SUCCESS) | `1516ddb08efe7fc52452ced9d4c86814db838130` | `railway deployment list` meta.commitHash |
| Railway `paper-trading-api` (production SUCCESS) | `1516ddb08efe7fc52452ced9d4c86814db838130` | same |
| Railway `paper-trading-worker` (production SUCCESS) | `1516ddb08efe7fc52452ced9d4c86814db838130` | same |
| In-app public build-SHA debug endpoint | **not present** (by design) | no new public debug route added |

**Verdict:** Deployment is **at parity** with current `main`. Visual
„Nicht verfügbar“ on old studies is therefore Legacy/Not-Pinned honesty, not
deployment lag.

Project: Railway `graceful-compassion` / environment `production`.
Public dashboard: `https://bot.save-money.xyz`.

## Acceptance scenarios

### Scenario 1 — Legacy Evidence (PASS)

Old study **without** scorecard pin:

- Pin status `LEGACY_NO_SCORECARD` / honest empty bind
- No invented scores; Executive cells → **Nicht verfügbar**
- No latest-run registry substitution / no auto backfill

**Evidence:**

- Unit: `tests/dashboard/research-overview-scorecard-bind.test.tsx`
  (`legacy / no scorecard keeps honest pin status…`)
- Visual: `npx playwright test tests/visual/research-overview-scorecard.spec.ts`
  scenarios `legacy` @ 1920×1080 / 1440×900 / mobile
- Screenshots: `docs/visual-regression/research-overview-legacy-*.png`
- Fixture: `overviewFixtureLegacy()` in `src/lib/research/overview-fixtures.ts`

### Scenario 2 — Current-Main READY Evidence (PASS)

Synthetic **public-core** evidence chain (local/test only — no private
Strategy V1, no P5 partition, no holdout):

`Experiment → completed run → Robustness → Gate Run → Scorecard → Validation
Study with sealed scorecard pin`

**Evidence:**

- Composition E2E: `tests/research/test_scorecard_e2e_acceptance.py` (matrix
  #293: sealed layers, no auto-promotion, tamper fail-closed)
- API detail/forensics: `tests/research/test_scorecard_detail.py`,
  `tests/research/test_scorecard_api.py`, `tests/research/test_artifact_content.py`
  (#357 raw artifact content)
- Workspace E2E smoke: `tests/research/test_e2e_acceptance.py`
  (Lab/Compare/Robustness/Gates/Validation/orphan recovery)
- UI READY bind: `overviewFixtureReady()` + vitest + Playwright `ready`
  scenarios; screenshots `docs/visual-regression/research-overview-ready-*.png`

Verified surfaces on READY path (fixture / API detail binding — public-core
labels only):

| Surface | Status |
|---------|--------|
| Executive Gates READY pin | PASS |
| Regime Rows | PASS |
| Confidence | PASS |
| Behaviour | PASS |
| Worst Regime | PASS |
| Transition Risk | PASS |
| Cost Stress boundary | PASS (API detail) |
| Parameter Area (`ISOLATED_PEAK` warning) | PASS |
| Evidence Inputs / Gate Failures inventory | PASS |
| Raw Artifact Link (#357) | PASS (unit + API) |
| Final Decision human / read-only (no Promote) | PASS |

Invalidated / missing evidence: Playwright `invalidated` scenario + vitest
error bind — PASS.

## Checklist

Evidence codes: **A** = API E2E, **U** = dashboard unit, **P** = Playwright,
**V** = visual fixture. Checked items were verified on SHA `1516ddb…`.

### A. Strategy catalog (#265 closure)

- [x] `/dashboard/research/strategies` lists **Trend Strategy V1 exactly
      once** — no `trend_strategy_v1` alias card (**A**+**U**+**P** empty/ready)
- [x] `/dashboard/research/strategies/trend_v1` shows display name,
      description, supported symbols/timeframes, and parameter schema —
      no profitability claims (**A**+**U**+**P**)
- [x] "Neues Experiment" from the strategy detail page opens the Lab
      pre-filled with `trend_v1` (**U** / Lab wiring)

### B. Strategy Lab → Run → Detail (#242 closure — browser residual under #250)

Lab **feature acceptance** for #242 is closed on `main` via PR #243 + follow-up
Lab fixes, API E2E (`tests/research/test_e2e_acceptance.py`), and the Write-Service
smoke protocol on issue #242 (committed `local_lab` catalog; no free client path).

- [x] Lab form shows strategy picker, dataset picker (catalog-id only),
      frozen parameter defaults (**U**+**P** Lab ready)
- [x] Valid Spec → experiment → detail polling `queued`/`running`/`completed`
      with metrics/artifacts (**A** `test_lab_run_detail_happy_path…`)
- [x] Invalid Spec → field/API 422 (**A** / write API tests)
- [x] Second **Start** blocked (`409` / Doppelstartschutz) (**A**)
- [x] Failed job deterministic, no private data leakage (**A**)

### C. Kurs & Trades chart (#266 closure)

- [x] Chart matches bound dataset + `trades.json` (**A**)
- [x] Byte-tamper fail-closed (**A**)
- [x] Chart-scoped semantic mismatch leaves equity/drawdown (**A**)
- [x] Missing reason codes → unavailable, not fabricated (**U**)

### D. Compare (#246 / #277)

- [x] Compatible + incompatible compare with explicit diffs (**A**)
- [x] Compare route empty/ready shell (**P**)

### E. Robustness (#247) / Gates (#248) / Validation Studies (#249)

- [x] Robustness / Gate / Validation smoke chain (**A**)
- [x] List/detail empty shells (**P**); create+detail covered by **A**
- [x] Scorecard READY + Legacy + invalidated (**U**+**P**+ scorecard **A**)

### F. General workspace hygiene

- [x] No live/paper order action from Research (**P** stub POST→405; architecture)
- [x] No free-form filesystem path for datasets (**U** Lab validation)
- [x] Overview not CLI-only (**P** Overview)
- [x] Empty / loading / error / not-found chrome (**U**+**P**)
- [x] Workspace switch Research → Monitor stays green (**P** a11y)

### G. Scorecard detail binding (#292 / #357 / #358)

- [x] Validation Study primary-run snapshot pin only; no registry `run_id`
      fallback (**U**+ Overview Legacy fixture)
- [x] Integrity fail / invalidated / missing → error/unavailable (**U**+**P**)
- [x] Experiment / strategy soft-bind; FAIL / LOW prominent; no Promote (**U**)
- [x] Missing → **Nicht verfügbar**; `ISOLATED_PEAK` warning (**U**+**P** READY)
- [x] Regime rows + Evidence Inputs / Gate Failures / Raw Artifact Refs
      inventory (**U**+ detail **A**)
- [x] Clickable Raw Metric Refs via fail-closed artifact content GET (#357)
      (**U** `research-artifact-content-link` + **A** `test_artifact_content`)
- [x] Research Overview binds pinned scorecard (#358) (**U**+**P**)

### H. Research route densify (#301)

- [x] Dense ResearchPageChrome tokens / shared inputs (**U** chrome tests)
- [x] `ResearchApiError` not document `h1` (**U**)
- [x] Loading / Empty / Error / Not-found shared chrome (**U**+**P**)
- [x] Monitor shell unchanged; no new routes beyond fixtures (**P**)

### I. Residual tracker (non-blocking for #250 close recommendation)

| Gap | Surface | Status | Notes |
|-----|---------|--------|-------|
| Optional live-catalog human click-through in browser | B–E | Non-blocking residual | API E2E + stub Playwright cover matrix; optional human pass with `local_lab` if desired |
| #345 confidence deepening | — | Open follow-up | Non-blocking; do not fold into policy 1.0 |
| #297 Hyperliquid-style epic | — | Remains closed | UI-01…UI-06 accepted |

## Ownership / restart recovery (#245 / #276)

No dedicated ownership/restart HTTP endpoints exist (and inventing them is
not part of acceptance). Recovery is the API lifespan hook calling
`ResearchWriteService.recover_orphans` / `ResearchJobStore.recover_orphans`:

- orphaned `queued` → re-dispatched
- `running` with dead lease → fail-closed (no mid-run resume)

Covered by `tests/research/test_e2e_acceptance.py::test_recover_orphans_redispatches_queued_and_fails_dead_running`
and `tests/research/test_research_job_ownership.py`.

## Evidence recording

Do not record private Strategy V1 metrics values in this file or in any
screenshot taken while completing this checklist. Record only: date, git
commit, pass/fail per section, and any deviations with a linked issue.

| Date | Commit | Sections passed | Deviations |
|------|--------|------------------|------------|
| 2026-07-19 | `96797ed998f6f803081c5d38ae0aed64902d07d2` (post-rebase onto `main` incl. #301) | Playwright `test:research-smoke` (2 passed); API E2E `test_e2e_acceptance.py` (10 passed); `tests/deploy/test_research_playwright_smoke.py` (4 passed); manual A–I **not** closed | #301 on main (§H); #302–#303 then open; browser gaps in §I; **no Closes #250** |
| 2026-07-19 | `1516ddb08efe7fc52452ced9d4c86814db838130` (incl. #357/#358/#359) | **BOT 3B final:** backend 61 passed / 1 skipped; research vitest 132; dashboard vitest 163; research-smoke 10; overview scorecard visual 9; visual suite 28; build OK; CLI compat 4; ruff OK; Legacy+READY scenarios PASS; Railway deploy parity PASS | Optional live-catalog browser click-through residual (non-blocking); #345 follow-up; **recommend human close #250/#295** — leave issues open until human decides |

### BOT 3B run metadata

| Field | Value |
|-------|-------|
| Test date | 2026-07-19 |
| Browser | Playwright Chromium |
| Resolutions | 2048×1152, 1920×1080, 1707×960 (Monitor); 1440×900 / 390×844 (Research shell); 1920×1080 / 1440×900 / 390×844 (Overview scorecard) |
| READY scenario | PASS (synthetic public-core) |
| Legacy scenario | PASS |
| Deployment SHA | `1516ddb…` (parity with main) |
| Known residuals | Optional live `local_lab` human click-through; #345 non-blocking |

## Automated coverage cross-reference

| Matrix item (#250) | Automated | Manual (this doc) |
|---------------------|-----------|--------------------|
| Trend Strategy V1 listed exactly once | `test_e2e_acceptance.py::test_trend_strategy_v1_listed_exactly_once`, `tests/dashboard/research-strategies.test.tsx` | Section A |
| Chart vs bound dataset + trades.json | `test_e2e_acceptance.py::test_chart_matches_bound_dataset_and_trades_json` | Section C |
| Tampered checksum fail-closed (trades/chart) | `test_e2e_acceptance.py::test_tampered_checksum_fails_closed_trades_and_chart_hidden` | Section C (byte-tamper drill) |
| Chart semantic dataset-hash mismatch; equity/drawdown remain | `test_e2e_acceptance.py::test_chart_integrity_failure_leaves_equity_drawdown_available` | Section C (scoped semantic drill) |
| Deterministic failed job, no private data | `test_e2e_acceptance.py::test_deterministic_failed_job_without_private_data` | — |
| Lab → Run → Detail happy path | `test_e2e_acceptance.py::test_lab_run_detail_happy_path_and_double_start_blocked` | Section B |
| Double-start blocked | same test as above | Section B |
| Compare (#246 / #277) | `test_e2e_acceptance.py::test_compare_compatible_and_incompatible_runs` | Section D |
| Robustness / Validation smoke | `test_e2e_acceptance.py::test_robustness_gate_validation_smoke` | Section E |
| Restart/orphan (#245 / #276) | `test_e2e_acceptance.py::test_recover_orphans_redispatches_queued_and_fails_dead_running` | Ownership section |
| CLI compatibility | `tests/research/test_cli_compat.py` | — (CLI, not UI) |
| Scorecard binding (#292/#357/#358) | scorecard API/detail/e2e + dashboard vitest + overview visual | Section G |
| Research route densify (#301) | `tests/dashboard/research-page-chrome.test.tsx` | Section H |
| Playwright Research route smoke | `tests/visual/research-routes.spec.ts` | Shell / empty states |
| Research a11y / responsive (#303) | `tests/visual/research-a11y-responsive.spec.ts` | `RESEARCH_RESPONSIVE_A11Y.md` |
| Monitor visual + number formatting (#359) | `tests/visual/dashboard.spec.ts`, `tests/dashboard/formatters.test.ts` | Monitor boundary |
