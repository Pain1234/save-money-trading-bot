# P5 Execution Checklist

**Status:** ENTRY GATE IN PROGRESS — candidate freeze prepared; human signature required before OOS.

## Entry gate (Phase B)

P5 becomes executable only when all are evidenced:

- [x] P4 complete on current `main`
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
- [ ] Candidate parameters frozen (signed freeze manifest) — **prepared; awaiting human**
- [x] No open critical P4 defect that can falsify P5 (re-check at sign-off)
- [x] Public/private storage defined (#181 / PR #222; private repo seeded)
- [x] Final OOS dataset still unopened

If any item fails: remain PLANNING ONLY; link blocking issue; do not start experiments; do not open OOS.

## Pre-OOS freezes (required before P5-08)

- [ ] Candidate Freeze signed
- [ ] Validation Protocol frozen
- [ ] Dataset partitions locked
- [ ] Benchmarks versioned
- [ ] Metrics set fixed
- [ ] Cost-stress plan fixed
- [ ] Parameter-stability plan fixed
- [ ] Bootstrap/MC plan fixed (or N/A justified)
- [ ] Sample-sufficiency rules approved
- [ ] Decision rules frozen
- [ ] Seeds fixed
- [ ] Software versions pinned
- [ ] Artifact paths classified public/private
- [ ] Human pre-OOS approval recorded

## Final OOS one-shot rules

After holdout open:

- [ ] No parameter changes
- [ ] No new filters / assets / threshold edits
- [ ] No “small bugfix” that changes economics without full invalidation + new candidate version
- [ ] Failed outcome not repaired by retuning

## Walk-forward plan notes (P5-04)

- Chronological folds; frozen params identical across folds
- Clear train/context/eval boundaries; no future peeking
- Same cost logic; deterministic seeds
- Report each fold + aggregate; do not keep only winning folds
- Document gaps; purge/embargo as locked

## Cost stress plan notes (P5-05)

Document per scenario: economic rationale, source/assumption, version, entry/exit/funding application. Include base, elevated, extreme, fee, slippage, funding, combined. No post-hoc scenario shopping.

## Parameter stability notes (P5-06)

Small symmetric neighborhood only; no grid-search promotion; neighbor cannot rescue failed candidate.

## Bootstrap / Monte Carlo notes (P5-07)

Prefer block / stationary bootstrap or sequence-respecting trade resamples. Avoid IID daily-return shuffles and post-hoc seed fishing. Fix method, block length, n_sim, seed, CIs, quantiles, drawdown distribution. MC does not replace missing real evidence.

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
