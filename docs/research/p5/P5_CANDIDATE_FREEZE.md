# P5 Candidate Freeze Manifest

**Status:** PREPARED — awaiting human signature
**Issue:** [#196](https://github.com/Pain1234/save-money-trading-bot/issues/196) (P5-00)
**Rule:** After human freeze, no parameter change may keep the name Strategy V1 without a new `strategy_version`, new freeze manifest, and new validation chain.

## Identity

| Field | Value | Notes |
|-------|-------|-------|
| `strategy_id` | `trend_v1` | Matches resolver key in P4 docs |
| `strategy_version` | `1.0.0` | Must match code + spec |
| Git commit (freeze pin) | **Set at human sign-off** to public `main` tip SHA | Do not freeze against a dirty worktree |
| Regression evidence SHA | `b51bde6fc186505f4ffb30c5d65665a50a801ed4` | Current `main` tip when entry tests were re-run (2026-07-17) |
| Strategy code hash (SHA-256 of `services/strategy_engine/**/*.py`) | `e96558b9dcae64dd7d4ce92544fb8ed8e715294ed1f49d0114b494ae68e2b43a` | 10 files; posix path + NUL + bytes + NUL |
| Risk code hash (SHA-256 of `services/risk_engine/**/*.py`) | `2b51f5f55eace6369f906472bb2cef10537fcd62fc94c14376777a70cf5b7d28` | 8 files; coupled V1; same hash method |
| Freeze timestamp (UTC) | **Set at human sign-off** | Starts forward holdout clock |
| Human approver | **REQUIRED** | Comment on #196 with SHA + UTC |
| Private Spec path | `Pain1234/save-money-trading-bot-private-research` → `specs/trend_v1_1.0.0/` | Per #181 |

## Entry-gate evidence (#196)

Commands (2026-07-17 UTC, evidence SHA `b51bde6fc186505f4ffb30c5d65665a50a801ed4` = `origin/main` tip):

```text
PYTHONPATH=services python -m pytest tests/research tests/paper_trading/test_backtester_signal_parity.py tests/paper_trading/test_backtester_parity.py -q
# 113 passed

PYTHONPATH=services python -m pytest tests/research/test_double_run_repro.py -q
# 3 passed
```

(Count rose vs earlier “76” prep run because P5 walk-forward / cost-stress / bootstrap / neighborhood tests landed on `main`.)

| Prerequisite | Status | Evidence |
|--------------|--------|----------|
| P4 complete on `main` | Met (docs) | ROADMAP / P4_ACCEPTANCE |
| Material P4 regressions green | **Met on evidence SHA** | commands above (113+3) |
| ExperimentSpec versioned | Met | #141 |
| RunManifest immutable | Met | #142 |
| DatasetManifest binding | Met (contract) | #163 |
| Strategy resolver injects engine | Met | #166 |
| Cost/slippage/funding semantics | Met | FUNDING.md / #164 |
| Registry trust anchor | Met | #165 |
| Compare Spec+Run identity | Met | #167 |
| Backtester/paper parity docs | Met | BACKTESTER_PAPER_PARITY.md |
| Strategy V1 version unique | Met | `1.0.0` |
| Candidate freeze signed | **Pending human** | this file |
| No open critical P4-fix | No open P4-fix found at evidence run | re-check at sign-off |
| Public/private storage | Met (#181 merged) | PR #222 / private repo |
| Final OOS unopened | Met | no P5 OOS artifacts |

## Parameters (Spec Freeze 1.0 / inventory)

Source: `docs/strategy-v1-parameter-inventory.md`, `docs/strategy-specification.md`.

| Parameter | Frozen value |
|-----------|--------------|
| `monthly_ema_period` | 20 |
| `weekly_ema_fast` | 20 |
| `weekly_ema_slow` | 50 |
| `daily_ema_period` | 20 |
| `breakout_lookback` | 20 |
| `atr_period` | 14 |
| `volume_sma_period` | 20 |
| `volume_ratio_min` | `1.00` (**not** the 1.20 backtest variant) |
| `pullback_ema_tolerance` | 0.005 |
| `stop_initial_atr_mult` | 2.5 |
| `trail_atr_mult` | 3.0 |

## Portfolio / risk (coupled Risk V1)

| Field | Frozen value |
|-------|--------------|
| Symbols | BTC, ETH, SOL |
| `risk_per_trade_pct` | 0.005 |
| `max_portfolio_risk_pct` | 0.02 |
| `max_open_positions` | 3 |
| `max_leverage` | 2.0 |
| `risk_rounding_tolerance` | 0.001 |
| Portfolio rules | Per risk + strategy specs (no discretionary overrides) |

## Rules references (not restated here)

| Concern | Source of truth |
|---------|-----------------|
| Entry / exit / stop rules | `docs/strategy-specification.md` |
| Candle timeframes | Daily evaluation; weekly/monthly filters per spec |
| Warmup minima | Daily ≥21, Weekly ≥50, Monthly ≥20 |

## Model / contract versions

| Contract | Version | Doc |
|----------|---------|-----|
| Cost model | `1.1` | `docs/research/FUNDING.md` (`COST_MODEL_VERSION`) |
| Fee / slippage / funding Spec fields | as Spec `model_version` | ExperimentSpec |
| Metrics schema | `1.2` | `docs/research/METRICS_DEFINITIONS.md` (net `benchmark_result` + `gross_return`; Spec cost parity) |
| Report schema | research runner | ARTIFACT_FORMAT |
| Dataset contracts | P3 DatasetManifest + P4 bind | market-data + dataset_binding |
| Random seed (protocol default) | `42` until protocol freeze overrides | Must match protocol |

## Freeze discipline

- After freeze: **no** silent edits to strategy code or parameters under this version.
- Any material change → bump `strategy_version`, new manifest, restart validation chain.
- Failed OOS must not be “fixed” by retuning V1 in place.

## Sign-off

| Role | Name | Date (UTC) | Signature / issue comment |
|------|------|------------|---------------------------|
| Preparer | Cursor agent (P5 execution) | 2026-07-17 | Prepared hashes + regression evidence |
| Human freeze approval | **REQUIRED** | | Comment on #196: `FREEZE APPROVED` + final `main` SHA + UTC |

**Final holdout status at freeze:** **unopened**. Forward holdout clock starts at human approval UTC (#197).
