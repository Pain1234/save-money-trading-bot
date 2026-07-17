# P5 Data Exposure Audit

**Status:** PARTITION LOCK PROPOSED — awaiting human approval
**Issue:** [#197](https://github.com/Pain1234/save-money-trading-bot/issues/197) (P5-01)
**Related:** #47, #181, #196

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

## Inventory (honest)

> Production DatasetManifest IDs/hashes for published research datasets live in the **private** store (`partitions/`) when sensitive. Public table uses classes and rules only.

| Period ID | Start | End | Symbols | Dataset-ID | Dataset-Hash | Prior use | Known exposure | Allowed P5 purpose | Class | Rationale |
|-----------|-------|-----|---------|------------|--------------|-----------|----------------|--------------------|-------|-----------|
| `FIX-EXAMPLE-WEEK` | 2024-01-01 | 2024-01-07 | BTC,ETH,SOL | fixture example | fixture | Unit/integration | CI/devs | Tests only | `NOT_USABLE` | Synthetic |
| `EX-SPEC-2024` | 2024-01-01 | 2024-12-31 | BTC,ETH,SOL | example Spec ref | placeholder | Docs example | Readers of example JSON | Docs only | `UNKNOWN_EXPOSURE` | Not a published research dataset |
| `SPEC-DEV-ERA` | ≤2026-07-11 | freeze UTC | BTC,ETH,SOL | n/a single ID | n/a | Spec/freeze design | Humans during V1 freeze | Debug/repro only | `SEEN_DEVELOPMENT` | Spec Freeze dated 2026-07-11; treat overlapping history as seen |
| `PAPER-OPS-LIVE` | paper deploy → ongoing | ongoing | BTC,ETH,SOL | live/paper | n/a research | Ops observation | Operators/dashboard | Ops only | `SEEN_DEBUGGING` | Contaminates untouched claims for overlapping dates |
| `HIST-UNKNOWN` | any published hist before freeze | freeze UTC | BTC,ETH,SOL | private catalog | private | Unknown viewing | UNKNOWN | Validation **only if** later cleared with human disclosure | `UNKNOWN_EXPOSURE` | Phase A: no formal OOS report; cannot claim untouched |
| `FORWARD-HOLDOUT` | human freeze UTC | open until #204 | BTC,ETH,SOL | post-freeze DatasetManifest | bind at #204 | None after freeze | None after lock | Final one-shot OOS | `FINAL_HOLDOUT_ELIGIBLE` | **Locked choice** when history cannot be proven untouched |

## Locked logical partitions

| Partition | Intent | Source classes | Lock rule |
|-----------|--------|----------------|-----------|
| A. Development / Seen | Reproduce, debug | `SEEN_*`, fixtures | Never label as OOS |
| B. Walk-Forward / Validation | Stability under frozen params | Only periods later **explicitly cleared** to `VALIDATION_ELIGIBLE` by human disclosure; else synthetic/fixture debug only | No param optimization from fold results |
| C. Final Untouched Holdout | One-shot gate | `FORWARD-HOLDOUT` only | Sealed until #204; start = Candidate Freeze UTC |

**Binding decision:** Do **not** promote `HIST-UNKNOWN` to final OOS. Use forward holdout (option 2).

## Purge / label embargo vs feature warmup (separate)

These must **not** be conflated:

| Control | Proposed value | Purpose | What it is **not** |
|---------|----------------|---------|---------------------|
| **Purge / label embargo** | 90 calendar days | Gap so evaluation labels are not adjacent to prior-fold evaluation / holdout edge | Not feature history for indicators |
| **Feature warmup** | Monthly EMA-20 ⇒ **≥20 fully completed calendar months** in feature context (`walk_forward.count_completed_monthly_candles`; partial edge months do **not** count). Optional calendar-day floor is additive only — **not** a `20×31` day proxy | Indicator state before first eval bar | Not covered by a 90-day embargo; 620 calendar days alone can leave only 19 closed months |

Rules:

- Chronological splits only.
- Apply **label embargo** between fold label-context and eval, and before holdout start.
- **Feature context** may include the embargo calendar window for prices/indicators; **labels must not**.
- First fold must have non-empty feature context spanning warmup; empty context is a hard error.
- Human must approve embargo length **and** acknowledge warmup separately before partition lock is final.

## Missing / short holdout

If at #204 the forward window fails sample-sufficiency (see protocol):

1. Extend forward collection, or
2. Record `INCONCLUSIVE` (no `ACCEPT_FOR_P6`).

Never relabel seen history as untouched to force ACCEPT.

## Sign-off

| Role | Name | Date | Notes |
|------|------|------|-------|
| Author (audit) | Cursor agent (P5 execution) | 2026-07-17 | Forward-holdout lock proposed |
| Human approver | **REQUIRED** | | Comment on #197: `PARTITIONS LOCKED` + embargo days |

**Holdout opened?** `NO`
