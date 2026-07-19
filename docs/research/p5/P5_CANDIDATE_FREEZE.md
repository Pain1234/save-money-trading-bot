# P5 Candidate Freeze Manifest

**Status:** PIN REFRESHED — `FREEZE PIN REFRESHED` 2026-07-19T15:47:02Z on #196
**Issue:** [#196](https://github.com/Pain1234/save-money-trading-bot/issues/196) (P5-00)
**Rule:** After human freeze, no parameter change may keep the name Strategy V1 without a new `strategy_version`, new freeze manifest, and new validation chain.

## Identity

| Field | Value | Notes |
|-------|-------|-------|
| `strategy_id` | `trend_v1` | Matches resolver key in P4 docs |
| `strategy_version` | `1.0.0` | Must match code + spec |
| Git commit (freeze pin / public-core SHA) | `aa0e232a6a0ea235a8a10682f8c7c4229b15a4d4` | `main` after #363 (PR #366); pin refreshed 2026-07-19T15:47:02Z |
| Prior human freeze pin | `35b4fa6d0c7d4f74a397a7d1a57437823341237b` | `FREEZE APPROVED` 2026-07-19T12:54:01Z — superseded for Partition B by this refresh |
| Regression evidence SHA | `aa0e232a6a0ea235a8a10682f8c7c4229b15a4d4` | Re-run 2026-07-19 after #363 |
| Strategy code hash (SHA-256 of `services/strategy_engine/**/*.py`) | `866fc2afab516bd024406c05f8816dd7237fc1f4cbb12821cdfb4845e344893c` | 10 files; repo-relative posix path + NUL + bytes + NUL |
| Risk code hash (SHA-256 of `services/risk_engine/**/*.py`) | `e08b66f8e57d31614a9024ec9c41b58a239975cf4abac3a58df54c60961fe61d` | 8 files; coupled V1; same hash method |
| Symbol constraints set | `hl-mainnet-szdecimals-v1` | BTC=5 / ETH=4 / SOL=2 (#363) |
| Symbol constraints content hash | `e5b2254249179eebe89d8d349b2a44566b50fbe79b37b2f32b62dc8d3b364817` | `HYPERLIQUID_MAINNET_V1_CONTENT_HASH` |
| ExperimentSpec schema | `1.0` | `EXPERIMENT_SPEC_SCHEMA_VERSION` |
| Candidate freeze hash | `90214c9031ccc91091a24a171991fbf84032c45845154cd78b4350ed0bfb59d6` | SHA-256 of canonical Gate-1 identity JSON (see below) |
| Freeze timestamp (UTC) | 2026-07-19T15:47:02Z | Pin refresh; does not reopen holdout |
| Human approver | @Pain1234 | `FREEZE PIN REFRESHED` on #196 |
| Private Spec path | `Pain1234/save-money-trading-bot-private-research` → `specs/trend_v1_1.0.0/` | Per #181 |

### Candidate freeze hash payload (canonical)

```json
{"constraint_set_version":"hl-mainnet-szdecimals-v1","experiment_spec_schema_version":"1.0","holdout_status":"SEALED","public_core_sha":"aa0e232a6a0ea235a8a10682f8c7c4229b15a4d4","risk_code_hash":"e08b66f8e57d31614a9024ec9c41b58a239975cf4abac3a58df54c60961fe61d","strategy_code_hash":"866fc2afab516bd024406c05f8816dd7237fc1f4cbb12821cdfb4845e344893c","strategy_id":"trend_v1","strategy_version":"1.0.0","symbol_constraints_hash":"e5b2254249179eebe89d8d349b2a44566b50fbe79b37b2f32b62dc8d3b364817"}
```

## Entry-gate evidence (#196)

Commands (2026-07-19 UTC, evidence SHA `aa0e232a6a0ea235a8a10682f8c7c4229b15a4d4` = `origin/main` tip after #363):

```text
PYTHONPATH=services python -m pytest tests/research tests/paper_trading/test_backtester_signal_parity.py tests/paper_trading/test_backtester_parity.py tests/research/test_double_run_repro.py tests/research/test_symbol_constraints_seal.py -q -m "not postgres and not live and not soak and not reporting"
# 498 passed, 1 skipped
```

Prior prep evidence (historical): SHA `b51bde6…` with 113+3 — superseded by the post-#363 re-run above. Strategy/risk code hashes are unchanged from `b51bde6` through `aa0e232`.

| Prerequisite | Status | Evidence |
|--------------|--------|----------|
| P4 complete on `main` | Met (docs) | ROADMAP / P4_ACCEPTANCE |
| Material P4 regressions green | **Met on evidence SHA** | commands above (498+1) |
| #363 sealed symbol constraints | **Met** | PR #366 merged at `aa0e232` |
| ExperimentSpec versioned | Met | #141 / schema `1.0` |
| RunManifest immutable | Met | #142 |
| DatasetManifest binding | Met (contract) | #163 |
| Strategy resolver injects engine | Met | #166 |
| Cost/slippage/funding semantics | Met | FUNDING.md / #164 |
| Registry trust anchor | Met | #165 |
| Compare Spec+Run identity | Met | #167 |
| Backtester/paper parity docs | Met | BACKTESTER_PAPER_PARITY.md |
| Strategy V1 version unique | Met | `1.0.0` |
| Candidate freeze signed | **Pin refreshed** | `FREEZE PIN REFRESHED` 2026-07-19T15:47:02Z on `aa0e232…` |
| No open critical P4-fix | No open P4-fix found at evidence run | re-check at sign-off |
| Public/private storage | Met (#181 merged) | PR #222 / private repo |
| Final OOS unopened | Met | Holdout `SEALED` / `NO` |

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
| Symbol constraints | `hl-mainnet-szdecimals-v1` | `services/research/symbol_constraints.py` (#363) |
| Random seed (protocol default) | `42` until protocol freeze overrides | Must match protocol |

## Freeze discipline

- After freeze: **no** silent edits to strategy code or parameters under this version.
- Any material change → bump `strategy_version`, new manifest, restart validation chain.
- Failed OOS must not be “fixed” by retuning V1 in place.
- Private Partition B packs from before #363 are **invalidated**; re-run only on this public-core SHA.

## Sign-off

| Role | Name | Date (UTC) | Signature / issue comment |
|------|------|------------|---------------------------|
| Preparer (initial) | Cursor agent (P5 execution) | 2026-07-17 | Prepared hashes + regression evidence |
| Human freeze approval (prior pin) | @Pain1234 | 2026-07-19T12:54:01Z | `FREEZE APPROVED` on `35b4fa6…` |
| Preparer (post-#363 pin refresh) | Cursor agent (Agent 1) | 2026-07-19 | Evidence on `aa0e232…`; Gate-1 handoff |
| Human freeze pin refresh | @Pain1234 | 2026-07-19T15:47:02Z | `FREEZE PIN REFRESHED` + `aa0e232…` |

**Final holdout status at freeze:** **unopened / SEALED**. Forward holdout clock is not reset by this pin refresh; #204 remains blocked until Pre-OOS gate.
