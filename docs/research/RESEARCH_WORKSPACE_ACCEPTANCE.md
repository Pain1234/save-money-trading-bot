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
chart, Robustness, Gates (read-only smoke), Validation Studies, double-start
protection, and dataset-integrity fail-closed behavior — everything this
branch stack (`main → #247 → #248 → #249 → #250`) actually ships. Compare
(#246) and durable job ownership/restart-recovery (#245) are **not** on this
stack; see "Explicitly out of scope" below.

## Prerequisites

```powershell
python scripts/prepare_research_lab_local.py
$env:RESEARCH_REPO_ROOT = "<repo-root>"
$env:RESEARCH_ARTIFACTS_ROOT = "<repo-root>"
$env:RESEARCH_DATASET_CATALOG_PATH = "<repo-root>\examples\research\local_lab\catalog.json"
# Keep the git working tree clean — do NOT set RESEARCH_ALLOW_DIRTY_GIT for
# this acceptance pass (that flag is a documented exception for automated
# tests only, per examples/research/README.md).
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

### B. Strategy Lab → Run → Detail (#242 closure)

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
- [ ] **Integrity drill:** manually corrupt one byte of that run's
      `chart_data.json` on disk (outside the UI) and reload the detail page.
      Expected: the chart view shows a clear "Integrität fehlgeschlagen" /
      unavailable state (no candles, no invented markers) while the
      **equity/drawdown panel on the same page keeps working** — restore the
      file afterward. This is the fail-closed property automated in
      `tests/research/test_e2e_acceptance.py`.

### D. Robustness (#247) / Gates (#248, read-only) / Validation Studies (#249)

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

### E. General workspace hygiene

- [ ] No route in this checklist ever offers a live/paper order action.
- [ ] No route accepts a free-form filesystem path (dataset selection is
      catalog-id only, everywhere it appears).
- [ ] Overview (`/dashboard/research`) no longer says "CLI-only" anywhere.
- [ ] Empty / loading / error states render for at least one route each
      (e.g. visit a route before any experiments exist, throttle network in
      devtools once, and request an unknown experiment id).

## Explicitly out of scope on this stack

| Feature | Issue | Status here |
|---------|-------|--------------|
| Compare view (experiment/strategy comparison) | #246 | Not present — separate PR off `main`, not stacked under #249 → #250. `tests/research/test_e2e_acceptance.py::test_compare_surface_not_present_on_this_stack` documents the current 404. |
| Durable job ownership / restart recovery | #245 | Not present — same reason. In-process V1 jobs are marked `failed` on the next status read after a process restart (documented in `services/research/jobs.py`); no dedicated ownership/restart endpoint exists yet. `test_restart_ownership_api_not_present_on_this_stack` documents the current 404. |

Re-run this checklist (sections A–D at minimum) once #245/#246 land on a
branch that includes this stack.

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
| Tampered checksum / dataset mismatch fail-closed | `test_e2e_acceptance.py::test_tampered_checksum_fails_closed_trades_and_chart_hidden` | Section C (integrity drill) |
| Equity/drawdown unaffected by chart integrity failure | `test_e2e_acceptance.py::test_chart_integrity_failure_leaves_equity_drawdown_available` | Section C (integrity drill) |
| Deterministic failed job, no private data | `test_e2e_acceptance.py::test_deterministic_failed_job_without_private_data` | — (no safe manual trigger without a real dataset window mistake) |
| Lab → Run → Detail happy path | `test_e2e_acceptance.py::test_lab_run_detail_happy_path_and_double_start_blocked`, `tests/research/test_research_write_api.py` | Section B |
| Double-start blocked | same test as above | Section B |
| Compare surface | documented absent (#246) | Explicitly out of scope table |
| Robustness / Validation smoke | `test_e2e_acceptance.py::test_robustness_gate_validation_smoke` | Section D |
| Restart/orphan (#245) | documented absent (#245) | Explicitly out of scope table |
| CLI compatibility | `tests/research/test_cli_compat.py` | — (CLI, not UI) |
