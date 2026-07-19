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
double-start protection, dataset-integrity fail-closed behavior, and the
durable job ownership / restart-recovery contract exercised in API E2E —
everything this branch stack
(`main → #245-via-#247 → #246 → #247 → #248 → #249 → #250`) ships.

## Playwright waiver (explicit)

Issue #250 asks for Playwright + API E2E + documented manual UI acceptance.

**Waiver (until a Research Playwright smoke lands or this waiver is
accepted):** there is **no** Research Workspace Playwright coverage in this
PR. Rationale:

- Existing Playwright configs (`playwright.config.ts`,
  `playwright.perf.config.ts`) drive the **paper-trading** dashboard against
  `scripts/paper-api-stub.mjs`, which has **no** research API routes or
  fixtures.
- Adding a credible Research browser smoke would require stubbing Lab /
  experiments / chart / compare / validation surfaces (or standing up a real
  research API + clean git + local_lab catalog in CI) — out of scope for a
  minimal #250 acceptance fix and not yet wired in this repo.
- Substitutes for this PR:
  1. API E2E: `tests/research/test_e2e_acceptance.py` (full Issue #250 matrix,
     including real Compare `#277` and `recover_orphans` ownership `#245/#276`)
  2. CLI compat: `tests/research/test_cli_compat.py`
  3. Frontend unit coverage: vitest (`tests/dashboard/research-*.test.tsx`)
  4. This manual UI checklist (human-run evidence table below)

Until Playwright is added **or** this waiver is explicitly accepted,
PR #283 must use **`Refs #250` only** — not `Closes #250`.

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

- [ ] Validation Study detail shows Scorecard Evidence Profile when
      `scorecard_ids` / snapshot pins / `run_id` resolve; otherwise honest
      empty reason (no invented metrics).
- [ ] Experiment detail loads scorecards by `run_id`; FAIL / LOW confidence
      remain visually prominent; no Promote button.
- [ ] Strategy detail soft-binds via last experiment → run → scorecard.
- [ ] Missing / `NOT_AVAILABLE` fields render as **Nicht verfügbar**.
- [ ] Regime table stays unavailable until per-regime rows exist on GET
      (document reason in UI).

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
| _fill in when run_ | _fill in_ | _fill in_ | _fill in_ |

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
| Playwright Research smoke | **waived** (see Playwright waiver above) | — |
