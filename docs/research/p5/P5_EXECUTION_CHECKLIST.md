# P5 Execution Checklist

**Status:** AUDIT-BLOCKED BEFORE OOS.
Current phase authority: [P5_EXECUTION_STATUS.md](P5_EXECUTION_STATUS.md).

## Entry gate (Phase B)

P5 becomes executable only when all are evidenced:

- [ ] P4 complete on current `main` — **acceptance evidence recorded, but human
  closure of #250/#295 remains pending; do not weaken this prerequisite**
- [x] Material P4 regression tests green (commands + log referenced on P5-00 / `P5_CANDIDATE_FREEZE.md`)
- [x] ExperimentSpec versioned
- [x] RunManifest immutable
- [x] DatasetManifest bound to actual inputs
- [x] Strategy resolver executes resolved strategy
- [x] Cost / slippage / funding semantics unambiguous
- [x] Registry checksum trust anchor present
- [x] Compare checks Spec + Run identity
- [x] Backtester/paper parity documented
- [x] Strategy V1 uniquely versioned
- [x] Candidate parameters frozen (`FREEZE APPROVED`, then
  `FREEZE PIN REFRESHED` on [#196](https://github.com/Pain1234/save-money-trading-bot/issues/196))
- [x] No open critical P4 defect that can falsify P5 (re-check at sign-off)
- [x] Public/private storage defined (#181 / PR #222; private repo seeded)
- [x] Final OOS dataset still unopened

If a completed entry item is invalidated: halt, record the blocker, and do not
open OOS. Audit [#371](https://github.com/Pain1234/save-money-trading-bot/issues/371) /
[PR #372](https://github.com/Pain1234/save-money-trading-bot/pull/372)
currently records `BLOCK_P5`; that hard stop must be independently reverified
and explicitly lifted before any further P5 execution. The #204 gates below
remain independently required.

## Pre-OOS freezes (required before P5-08)

Canonical live checklist: [`P5_PRE_OOS_GATE.md`](P5_PRE_OOS_GATE.md).

- [x] Candidate Freeze signed (`FREEZE PIN REFRESHED` on `aa0e232…`)
- [x] Validation Protocol frozen
- [x] Dataset partitions locked
- [x] Benchmarks versioned
- [x] Metrics set fixed
- [x] Cost-stress plan fixed + #252 executed (sealed)
- [x] Parameter-stability plan fixed + #253 executed (sealed)
- [x] Bootstrap/MC plan fixed + #254 executed (sealed)
- [ ] Sample-sufficiency rules confirmed for holdout window at open
  (90d calendar: **NOT MET** as of 2026-07-19; clock `2026-07-19T12:54:01Z`)
- [x] Decision rules frozen
- [x] Seeds fixed
- [x] Software versions pinned (`aa0e232…` + sealed constraints)
- [x] Artifact paths classified public/private
- [ ] Human pre-OOS approval recorded (`PRE-OOS APPROVED` on #204)
## Final OOS one-shot rules

After holdout open:

- [ ] No parameter changes
- [ ] No new filters / assets / threshold edits
- [ ] No “small bugfix” that changes economics without full invalidation + new candidate version
- [ ] Failed outcome not repaired by retuning

## Walk-forward plan notes (P5-04 / execution P5-04E #251)

- Chronological folds; frozen params identical across folds
- Clear train/context/eval boundaries; no future peeking
- Same cost logic; deterministic seeds
- Report each fold + aggregate; do not keep only winning folds
- Document gaps; purge/embargo as locked
- **#200 = plan/helpers only; actual run = [#251](https://github.com/Pain1234/save-money-trading-bot/issues/251)**

## Cost stress plan notes (P5-05 / execution P5-05E #252)

Document per scenario: economic rationale, source/assumption, version, entry/exit/funding application. Include base, elevated, extreme, fee, slippage, funding, combined. No post-hoc scenario shopping. **Actual run = [#252](https://github.com/Pain1234/save-money-trading-bot/issues/252).**

## Parameter stability notes (P5-06 / execution P5-06E #253)

Small symmetric neighborhood only; no grid-search promotion; neighbor cannot rescue failed candidate. **Actual run = [#253](https://github.com/Pain1234/save-money-trading-bot/issues/253).**

## Bootstrap / Monte Carlo notes (P5-07 / execution P5-07E #254)

Prefer block / stationary bootstrap or sequence-respecting trade resamples. Avoid IID daily-return shuffles and post-hoc seed fishing. Fix method, block length, n_sim, seed, CIs, quantiles, drawdown distribution. MC does not replace missing real evidence. **Actual run = [#254](https://github.com/Pain1234/save-money-trading-bot/issues/254).**
## Regime / symbol notes (P5-03 / N)

BTC/ETH/SOL only. Define deterministic regimes **before** seeing results. No post-hoc regime rescue.

## Stop rules (immediate halt)

Stop P5 on: leakage; unclear dataset version; changed V1 code/params under freeze; holdout opened before protocol freeze; unreproducible results; missing cost accounting; public leak of private results; critical P4 defect; attempt to retune after failed OOS.

After stop: no promotion; document cause; invalidate affected results; require human decision.

## Milestone Definition of Done

P5 milestone may close only when:

- [ ] Strategy V1 uniquely frozen
- [ ] Historical exposure fully audited
- [ ] Genuine final holdout exists **or** missing holdout honestly documented
- [ ] Protocol frozen before result viewing
- [ ] Benchmarks defined
- [ ] Sample-sufficiency rules defined
- [ ] Walk-forward completed
- [ ] Cost stress completed
- [ ] Parameter stability completed
- [ ] Bootstrap/MC completed or methodically N/A
- [ ] Final OOS evaluated exactly once
- [ ] No post-hoc parameter change
- [ ] No leakage findings
- [ ] Results reproducible
- [ ] Private artifacts not publicly leaked
- [ ] `ACCEPT_FOR_P6` | `REJECT` | `INCONCLUSIVE` documented
- [ ] Human decision in Decision Log
- [ ] #47 closed
- [ ] #181 satisfied
- [ ] No new strategy developed
- [ ] No new assets activated
- [ ] No paper soak pre-empted
- [ ] No live-trading code added
