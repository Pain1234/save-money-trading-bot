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
Scorecard binding (#292), Research route densify (#301), double-start
protection, dataset-integrity fail-closed behavior, and the durable job
ownership / restart-recovery contract exercised in API E2E.

**Do not close #250 / mark P4 complete / start P5** until Issues **#302** and
**#303** are merged and this checklist is re-run on that `main` with
screenshots + test evidence recorded below. (#301 is on `main`; densify
checks remain in §H until the final acceptance pass records them.)

## Playwright Research smoke (Issue #250)

Issue #250 requires Playwright + API E2E + documented manual UI acceptance.

**Shipped (this branch):** stub-backed Research **route smoke** —

- `tests/visual/research-routes.spec.ts`
- Research fixtures in `scripts/paper-api-stub.mjs` (GET/HEAD only; POST → 405)
- Run: `npm run test:research-smoke` (uses `playwright.config.ts` webServers)
- CI: visible non-required job `research-playwright-smoke` in
  `.github/workflows/ci-fast.yml` (runs when `research`, `deploy`, or
  `run_all_fast`; not part of `fast-ci-required`)
- Static wiring: `tests/deploy/test_research_playwright_smoke.py`

What it covers: login → Monitor regression → Overview / Strategien /
Strategy detail (scorecard empty bind) / Experiments empty / Lab ready /
Compare empty / Robustheit empty / Validierung empty — no private metrics.

What it does **not** cover (still manual / API E2E):

- Starting a real Lab job against `local_lab` + clean git
- Running / Completed / Failed experiment detail polling
- Compare of two real runs; Robustness / Validation create+detail
- Scorecard **ready** bind on experiment / strategy / validation
- Integrity drill (byte-tamper / semantic mismatch)
- API process restart orphan recovery (covered by API E2E)

**Historical waiver (PR #283):** prior to this smoke, Research Playwright was
explicitly waived with `Refs #250` only. That waiver is **superseded** by the
route smoke above for shell/empty-state coverage. Remaining gaps above are
**not** waived — they stay on the manual checklist and/or API E2E until
#302–#303 land and the final acceptance pass is recorded.

Until the full manual checklist + final evidence table are complete on
post-#302–#303 `main`, PRs for this track must use **`Refs #250` only** —
not `Closes #250`.

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

## Checklist

### A. Strategy catalog (#265 closure)

- [ ] `/dashboard/research/strategies` lists **Trend Strategy V1 exactly
      once** — no `trend_strategy_v1` alias card, even with zero experiments.
- [ ] `/dashboard/research/strategies/trend_v1` shows display name,
      description, supported symbols/timeframes, and parameter schema —
      no profitability claims.
- [ ] "Neues Experiment" from the strategy detail page opens the Lab
      pre-filled with `trend_v1`.

### B. Strategy Lab → Run → Detail (#242 closure — browser residual under #250)

Lab **feature acceptance** for #242 is closed on `main` via PR #243 + follow-up
Lab fixes, API E2E (`tests/research/test_e2e_acceptance.py`), and the Write-Service
smoke protocol on issue #242 (committed `local_lab` catalog; no free client path).

The checkboxes below remain the **human browser** residual and close under
**#250** (not a reopened #242 feature track):

- [ ] `/dashboard/research/experiments/new` shows the strategy picker,
      dataset picker (from the local_lab catalog only — no free-text path
      field anywhere), and parameter form with frozen defaults.
- [ ] Submitting a valid Spec creates an experiment and redirects/links to
      its detail page in `created` status.
- [ ] Starting the experiment shows `queued` → `running` → `completed`
      polling without blocking the page; a completed run shows metrics,
      equity/drawdown chart, and artifacts summary.
- [ ] Submitting an intentionally invalid Spec (e.g. unknown strategy id,
      non-positive starting capital) shows field-level validation errors —
      both before submit (client) and if bypassed, from the API (422).
- [ ] Clicking **Start** a second time on the same experiment is blocked
      (button disabled and/or a clear "läuft bereits" message; matches API
      `409`).

### C. Kurs & Trades chart (#266 closure)

- [ ] On a completed experiment, the "Kurs & Trades" view renders candles
      for the bound dataset, with entry/exit markers and the initial +
      trailing stop line.
- [ ] Switching symbol (if the experiment has more than one) redraws the
      chart from that symbol's own candles/trades — no cross-symbol bleed.
- [ ] The trade table below the chart lists the same trades as the chart
      markers; clicking a row focuses/zooms the chart to that trade's range.
- [ ] No "why traded" text invents a reason not present in stored reason
      codes; empty/missing reason codes show as unavailable, not fabricated.
- [ ] **Integrity drill (whole-artifact byte tamper):** corrupt one byte of
      that run's `trades.json` **or** `chart_data.json` on disk **without**
      resealing registry checksums, then reload the detail page. Expected:
      trades and/or chart fail closed ("Integrität fehlgeschlagen" /
      unavailable — no candles, no invented markers). Do **not** expect
      equity/drawdown to keep working after an unreasealed byte-tamper of
      sealed artifacts: whole-artifact integrity may fail closed for the
      detail surface as well. Restore the file afterward.
- [ ] **Integrity drill (chart-scoped semantic mismatch):** to verify
      equity/drawdown independence as automated in
      `test_chart_integrity_failure_leaves_equity_drawdown_available`, the
      failure must be a **dataset-hash mismatch inside `chart_data.json`
      with checksums resealed** (so registry trust for equity artifacts
      remains valid while chart endpoints that verify chart binding fail).
      Only that scoped case guarantees equity/drawdown stay readable while
      the chart is hidden. A raw unreasealed byte-tamper of `chart_data.json`
      is **not** that case.

### D. Compare (#246 / #277)

- [ ] `/dashboard/research/compare` loads; selecting two completed runs
      shows a compatible or incompatible result with explicit diffs — never
      a silent empty success when Spec fields disagree.
- [ ] From an experiment detail page, a link/action into Compare pre-fills
      at least one run id when the UI provides that affordance.

### E. Robustness (#247) / Gates (#248, read-only) / Validation Studies (#249)

- [ ] `/dashboard/research/robustness` lists jobs; creating a bootstrap
      robustness job against a completed base experiment runs to
      `completed` and shows quantiles — synthetic/local-lab numbers only.
- [ ] `/dashboard/research/robustness/[id]` shows the manifest detail
      (per-fold / per-scenario / per-neighbor results as applicable).
- [ ] `/dashboard/research/validation` lists studies; creating one from a
      completed experiment + robustness result + evaluated gate aggregates
      that evidence (no re-computation, no live/paper promotion action).
- [ ] `/dashboard/research/validation/[id]` shows progress, gates, and
      reproducibility block (dataset hash, policy version/hash) without any
      private Strategy V1 numbers.

### F. General workspace hygiene

- [ ] No route in this checklist ever offers a live/paper order action.
- [ ] No route accepts a free-form filesystem path (dataset selection is
      catalog-id only, everywhere it appears).
- [ ] Overview (`/dashboard/research`) no longer says "CLI-only" anywhere.
- [ ] Empty / loading / error states render for at least one route each
      (e.g. visit a route before any experiments exist, throttle network in
      devtools once, and request an unknown experiment id).

### G. Scorecard detail binding (#292)

- [ ] Validation Study detail shows Scorecard Evidence Profile when a
      **primary-run** scorecard is **snapshot-pinned**; no registry
      `run_id` fallback; additional-run pins alone must not become the profile.
- [ ] `evidence_integrity.ok=false`, pin hash mismatch, missing pin hash,
      or `status=invalidated` → error/unavailable (no ready profile strip).
- [ ] Experiment detail loads scorecards by `run_id`; FAIL / LOW confidence
      remain visually prominent; no Promote button.
- [ ] Strategy detail soft-binds via last experiment → run → scorecard.
- [ ] Missing / `NOT_AVAILABLE` fields render as **Nicht verfügbar**.
- [ ] `ISOLATED_PEAK` is warning-toned in profile strip **and** Parameter panel.
- [ ] Regime table stays unavailable until per-regime rows exist on GET
      (document reason in UI).
- [ ] Rest scope accepted: Evidence Inputs / Gate Failures / Raw Metric Refs
      not yet rendered (documented in UI spec).

### H. Research route densify (#301)

- [ ] Strategies / Experiments / Lab / Compare / Robustness / Validation
      share dense ResearchPageChrome tokens (18px titles, rounded-sm,
      12px body) — no `text-2xl` / `rounded-xl` marketing heroes.
- [ ] Strategy Lab form fields use shared `rs.input` / `rs.select` /
      `rs.fieldLabel` (no legacy `text-sm` / bare `rounded` controls).
- [ ] Embedded `ResearchApiError` is not an `<h1>` (alert title only;
      page header remains sole document h1).
- [ ] Loading / Empty / Error / Not-found states use shared chrome.
- [ ] No new routes; Monitor shell unchanged; API wiring preserved.
- [ ] Missing metrics still render as **Nicht verfügbar**.

### I. Open browser gaps (tracked — do not silently waive)

Recorded during the #250 acceptance pass; re-verify after #302–#303 merge.
(#301 densify is on `main` — checklist §H; residual browser work stays here.)

| Gap | Surface | Status | Notes |
|-----|---------|--------|-------|
| Real Lab start → poll → detail | B | Open browser residual | Stub smoke only loads Lab **ready**; full start needs live API + clean git + `local_lab` |
| Running / Completed / Failed detail panels | B | Open browser residual | API E2E covers job states; human browser pass still required |
| Compare two real runs | D | Open browser residual | Stub smoke = empty selector/hint only |
| Robustness create + detail | E | Open browser residual | Stub smoke = empty list |
| Validation create + detail + scorecard pin | E / G | Open browser residual | Needs completed evidence chain |
| Scorecard **ready** bind (exp/strategy/study) | G | Open browser residual | Stub smoke = `scorecard-bind-empty` on strategy detail |
| Research route densify (#301) | H | On `main` — verify in final pass | Code merged; manual §H checkboxes still open until recorded |
| Forensics / visual acceptance | — | Blocked on #302–#303 | Final #250 close deferred until these merge + re-run |
| Monitor regression after Research nav | F | Covered by Playwright smoke | Direct `/dashboard` load + UI click `workspace-monitor` → `dashboard-page-ready` |

## Ownership / restart recovery (#245 / #276)

No dedicated ownership/restart HTTP endpoints exist (and inventing them is
not part of acceptance). Recovery is the API lifespan hook calling
`ResearchWriteService.recover_orphans` / `ResearchJobStore.recover_orphans`:

- orphaned `queued` → re-dispatched
- `running` with dead lease → fail-closed (no mid-run resume)

Covered by `tests/research/test_e2e_acceptance.py::test_recover_orphans_redispatches_queued_and_fails_dead_running`
and `tests/research/test_research_job_ownership.py`. Manual UI check: after an
API process restart, a previously mid-run experiment should surface as
`failed` with a clear restart/lease reason rather than hanging forever on
`running`.

## Evidence recording

Do not record private Strategy V1 metrics values in this file or in any
screenshot taken while completing this checklist. Record only: date, git
commit, pass/fail per section, and any deviations with a linked issue.

| Date | Commit | Sections passed | Deviations |
|------|--------|------------------|------------|
| 2026-07-19 | `96797ed998f6f803081c5d38ae0aed64902d07d2` (post-rebase onto `main` incl. #301) | Playwright `test:research-smoke` (2 passed); API E2E `test_e2e_acceptance.py` (10 passed); `tests/deploy/test_research_playwright_smoke.py` (4 passed); manual A–I **not** closed | #301 on main (§H); #302–#303 open; browser gaps in §I; **no Closes #250** |
| _fill in after #302–#303_ | _fill in_ | _fill in_ | _fill in_ |

## Automated coverage cross-reference

| Matrix item (#250) | Automated | Manual (this doc) |
|---------------------|-----------|--------------------|
| Trend Strategy V1 listed exactly once | `test_e2e_acceptance.py::test_trend_strategy_v1_listed_exactly_once`, `tests/dashboard/research-strategies.test.tsx` | Section A |
| Chart vs bound dataset + trades.json | `test_e2e_acceptance.py::test_chart_matches_bound_dataset_and_trades_json` | Section C |
| Tampered checksum fail-closed (trades/chart) | `test_e2e_acceptance.py::test_tampered_checksum_fails_closed_trades_and_chart_hidden` | Section C (byte-tamper drill) |
| Chart semantic dataset-hash mismatch; equity/drawdown remain | `test_e2e_acceptance.py::test_chart_integrity_failure_leaves_equity_drawdown_available` | Section C (scoped semantic drill) |
| Deterministic failed job, no private data | `test_e2e_acceptance.py::test_deterministic_failed_job_without_private_data` | — (no safe manual trigger without a real dataset window mistake) |
| Lab → Run → Detail happy path | `test_e2e_acceptance.py::test_lab_run_detail_happy_path_and_double_start_blocked`, `tests/research/test_research_write_api.py` | Section B |
| Double-start blocked | same test as above | Section B |
| Compare (#246 / #277) | `test_e2e_acceptance.py::test_compare_compatible_and_incompatible_runs` | Section D |
| Robustness / Validation smoke | `test_e2e_acceptance.py::test_robustness_gate_validation_smoke` | Section E |
| Restart/orphan (#245 / #276) | `test_e2e_acceptance.py::test_recover_orphans_redispatches_queued_and_fails_dead_running` | Ownership section |
| CLI compatibility | `tests/research/test_cli_compat.py` | — (CLI, not UI) |
| Scorecard binding (#292) | Dashboard scorecard vitest + API scorecard suite | Section G |
| Research route densify (#301) | Dashboard densify vitest (if present) | Section H |
| Playwright Research route smoke | `tests/visual/research-routes.spec.ts` (`npm run test:research-smoke`) | Shell / empty states; §I for residuals |
