# P5 Data Exposure Audit (planning template)

**Status:** PLANNING / TEMPLATE — no final partition lock until human review
**Issue:** [#197](https://github.com/Pain1234/save-money-trading-bot/issues/197) (P5-01)
**Related:** #47, #181

## Rules (binding)

1. A period may be called **untouched OOS / FINAL_HOLDOUT** only if it was **not** used for: strategy development, parameter/filter/threshold choice, performance debugging, visual result judgment, variant comparison, asset selection, or accept/reject threshold derivation.
2. `UNKNOWN_EXPOSURE` must **never** be used as final OOS.
3. A previously viewed period must not be relabeled untouched.
4. Missing history must not be replaced by a false OOS claim.
5. If no genuine final holdout exists, P5 must wait for new time data, define a **forward holdout**, or remain `INCONCLUSIVE`.

## Classification vocabulary

| Class | Meaning | Allowed P5 use |
|-------|---------|----------------|
| `SEEN_DEVELOPMENT` | Used in design / tuning / variant choice | Debug / reproduction only; never OOS |
| `SEEN_DEBUGGING` | Performance viewed while debugging | Debug / reproduction only; never OOS |
| `VALIDATION_ELIGIBLE` | Eligible for walk-forward / validation folds | Fixed-parameter validation only |
| `FINAL_HOLDOUT_ELIGIBLE` | Credible untouched candidate for one-shot OOS | Final OOS **once**, after protocol freeze |
| `UNKNOWN_EXPOSURE` | Insufficient provenance | Not final OOS; prefer exclude or downgrade |
| `NOT_USABLE` | Quality / coverage / contract failure | Exclude |

## Inventory (fill during P5-01; placeholders only)

> Dataset IDs/hashes below are **TBD** until bound to real `DatasetManifest` records. Example/fixture IDs are not production research datasets.

| Period ID | Start | End | Symbols | Dataset-ID | Dataset-Hash | Prior use | Known human/agent exposure | Allowed P5 purpose | Class | Rationale |
|-----------|-------|-----|---------|------------|--------------|-----------|----------------------------|--------------------|-------|-----------|
| `FIX-EXAMPLE-WEEK` | 2024-01-01 | 2024-01-07 | BTC,ETH,SOL | `example` fixture | fixture zero-hash | Unit/integration fixtures | Developers/CI | Tests only | `NOT_USABLE` | Synthetic fixture; not economic evidence |
| `EX-SPEC-2024` | 2024-01-01 | 2024-12-31 | BTC,ETH,SOL | example ref in ExperimentSpec | placeholder `aaaa…` | Documentation example only | Anyone reading example JSON | Docs / schema demos | `UNKNOWN_EXPOSURE` | Example window is not a published research dataset; do not treat as OOS |
| `SPEC-DEV-ERA` | TBD | TBD | BTC,ETH,SOL | TBD | TBD | Spec writing, indicator design, freeze defaults | Likely humans during 2026-07 spec freeze | Development context only | `UNKNOWN_EXPOSURE` → likely `SEEN_DEVELOPMENT` | Calendar overlap with live markets during development is probable; exact candle ranges viewed **not** inventoried in GitHub |
| `PAPER-OPS-LIVE` | TBD (ops start) | ongoing | BTC,ETH,SOL | live/paper feeds | n/a research | Paper trading observation | Operators/dashboard users | Ops only; not research OOS | `SEEN_DEBUGGING` or `UNKNOWN_EXPOSURE` | Live paper candles may contaminate “untouched” claims for overlapping dates |
| `PROD-HIST-CANDIDATE` | TBD | TBD | BTC,ETH,SOL | TBD published | TBD | **None documented** as formal V1 research OOS | UNKNOWN | Candidate validation / holdout **only after** exposure clearance | `UNKNOWN_EXPOSURE` until cleared | No formal OOS report found in repo (Phase A) |
| `FORWARD-HOLDOUT` | TBD (post freeze) | TBD | BTC,ETH,SOL | future publish | TBD | None (by construction after freeze) | None after lock | Final one-shot OOS | `FINAL_HOLDOUT_ELIGIBLE` (planned) | Preferred if historical untouched window cannot be proven |

## Logical partitions (targets; dates TBD in P5-01)

| Partition | Intent | Source classes | Lock rule |
|-----------|--------|----------------|-----------|
| A. Development / Seen | Reproduce, debug | `SEEN_*`, cleared fixtures | Never label as OOS |
| B. Walk-Forward / Validation | Stability under frozen params | `VALIDATION_ELIGIBLE` only | No param optimization from fold results |
| C. Final Untouched Holdout | One-shot gate | `FINAL_HOLDOUT_ELIGIBLE` only | Technically + organizationally sealed until P5-08 |

## Leakage controls (plan)

- Chronological splits only; no random row splits.
- Document purge/embargo if label or position windows overlap fold boundaries (warmup, ATR/EMA lookbacks, open trades spanning folds).
- Embargo length: **TBD** — propose ≥ max indicator lookback in bars (monthly EMA 20 ≈ multi-month) with human approval; do not invent a false “safe” short embargo.

## Missing genuine holdout — forced options

If after audit no `FINAL_HOLDOUT_ELIGIBLE` period exists:

1. Wait for new post-freeze market time and publish a new dataset, or
2. Define an explicit forward holdout with start = freeze timestamp, or
3. Record final decision `INCONCLUSIVE` (no `ACCEPT_FOR_P6`).

## Sign-off

| Role | Name | Date | Notes |
|------|------|------|-------|
| Author (audit) | TBD | TBD | |
| Human approver | TBD | TBD | Required before partition lock |

**Holdout opened?** `NO` (planning document only)
