# P5 Validation Protocol (pre-registration template)

**Status:** PLANNING / NOT FROZEN
**Issue:** [#198](https://github.com/Pain1234/save-money-trading-bot/issues/198) (P5-02)
**Hard rule:** Freeze and human-approve this protocol **before** opening the final OOS dataset. Never change thresholds after seeing results.

## 1. Research question

Under pre-registered costs, benchmarks, partitions, and decision rules, does frozen Strategy V1 (`trend_v1` @ pinned `strategy_version`) produce evidence sufficient for `ACCEPT_FOR_P6`, or must it be `REJECT` / `INCONCLUSIVE`?

## 2. Candidate identity

Reference signed [P5_CANDIDATE_FREEZE.md](P5_CANDIDATE_FREEZE.md) (strategy_id, version, commit, hashes, parameters).

## 3. Data partitions

Reference locked [P5_DATA_EXPOSURE_AUDIT.md](P5_DATA_EXPOSURE_AUDIT.md):

- A Development / Seen
- B Walk-Forward / Validation
- C Final Untouched Holdout (sealed until P5-08)

Purge/embargo: TBD at partition lock (see exposure audit).

## 4. Benchmarks (versioned; P5-03)

Minimum set (same period, dataset, currency, capital base; documented rebalance):

| Benchmark | Purpose |
|-----------|---------|
| Cash / null | Opportunity cost of inactivity |
| Buy-and-hold per symbol | Single-asset reference (P4 `buy_and_hold_<SYMBOL>`) |
| Combined BTC/ETH/SOL reference portfolio | Portfolio parity (weights/rebalance TBD + versioned) |
| Existing P4 benchmark contract | Continuity with research runner |
| Optional exposure-matched | Only if method documented before results |

Unsuitable benchmarks must not be used to flattering the candidate.

## 5. Cost assumptions

- Base: P4 fee/slippage/funding semantics (`COST_MODEL_VERSION` / Spec fields).
- Stress: scenarios from P5-05 plan (base / elevated / extreme; fee, slippage, funding, combined).
- Always report gross and net separately.
- No post-hoc selection of the stress that “just passes”.

## 6. Metrics (decision-relevant set)

**Performance:** gross PnL, net PnL, CAGR/annualized only if methodologically valid, benchmark excess, fees, slippage, funding, turnover.

**Risk:** max drawdown, drawdown duration, volatility, downside risk, loss streaks, tail loss, exposure, time in market, portfolio concentration.

**Trade-level:** signals, closed trades, hit rate, avg win/loss, expectancy, profit factor, median trade, largest wins/losses, share of PnL from few trades.

**Stability:** per symbol, per window, per regime, per walk-forward fold, cost stress, parameter sensitivity, bootstrap/MC distribution.

No single metric alone decides promotion.

## 7. Robustness tests

| Test | Issue | Constraint |
|------|-------|------------|
| Walk-forward (fixed params) | P5-04 | No per-fold optimization |
| Cost / funding stress | P5-05 | Pre-registered scenarios |
| Parameter neighborhood | P5-06 | Diagnostic only; neighbor cannot rescue candidate |
| Bootstrap / Monte Carlo | P5-07 | Time-respecting methods; no IID abuse |

## 8. Sample sufficiency (template — values human-approved)

Do **not** invent final thresholds without rationale. Fill in P5-02:

| Rule | Proposed value | Statistical/practical rationale | Stricter impact | Looser impact | Human approval |
|------|----------------|---------------------------------|-----------------|---------------|----------------|
| Min closed trades (total) | TBD | TBD | More INCONCLUSIVE | Higher false ACCEPT risk | TBD |
| Min closed trades / symbol | TBD | TBD | May drop thin symbols | Mask concentration | TBD |
| Min walk-forward folds | TBD | TBD | Harder pass | Regime blind spots | TBD |
| Min distinct regimes | TBD | TBD | Harder pass | Phase luck | TBD |
| Min OOS duration | TBD | TBD | Wait longer | Weak OOS | TBD |
| Max PnL share from top-N trades | TBD | TBD | Reject fragile edges | Allow lottery wins | TBD |
| Symbols below sample floor | Exclude from ACCEPT; document | — | — | — | TBD |

If sufficiency fails → `INCONCLUSIVE` (not `ACCEPT_FOR_P6`).

## 9. Accept / Reject / Inconclusive

See [P5_DECISION_RULES.md](P5_DECISION_RULES.md). Rules frozen with this protocol.

## 10. Evaluation order (binding)

1. Confirm entry gate + freezes + #181
2. Development reproduction (optional sanity; not decision)
3. Walk-forward on validation partition
4. Cost stress
5. Parameter stability diagnostics
6. Bootstrap/MC on appropriate series
7. Sample-sufficiency check
8. Human pre-OOS approval
9. **One-shot** final OOS
10. Apply decision rules → human final sign-off (P5-09)

## 11. Technical errors

- Fail-closed: abort run; do not patch results in place.
- Invalidation via registry/sidecar only (P4 contract).
- Material runner/strategy bug discovered after OOS open → invalidate results; require new candidate version if fix changes economics; no silent re-run as same V1 OOS.

## 12. Data problems

- Quarantine / quality failure → stop; do not impute to force a pass.
- Gap/duplicate beyond policy → `NOT_USABLE` or invalidate.

## 13. Missing / zero trades

- Zero or below-floor trades on OOS → `INCONCLUSIVE` or `REJECT` per pre-registered rule (default proposal: sufficiency → `INCONCLUSIVE`; catastrophic instability elsewhere may still `REJECT`).

## 14. Multiple hypotheses

- P5 validates **one** frozen candidate.
- Extra hypotheses require separate specs/versions and multiplicity discipline; not used to rescue V1.

## 15. Parameter perturbations

- Diagnostics only (P5-06).
- Successful neighbor **cannot** replace failed frozen candidate.

## 16. OOS results handling

- Private storage only (#181).
- No threshold edits after viewing.
- Failed OOS → `REJECT` or `INCONCLUSIVE` per rules; **no retuning**.

## 17. Public / private classification

See [P5_PUBLIC_PRIVATE_ARTIFACTS.md](P5_PUBLIC_PRIVATE_ARTIFACTS.md).

## 18. Human decision gate

| Gate | Required before |
|------|-----------------|
| Protocol + decision freeze | Any final holdout open |
| Pre-OOS approval | P5-08 execution |
| Final decision sign-off | Closing #47 / P5 milestone |

## Protocol freeze sign-off

| Role | Name | Date |
|------|------|------|
| Author | TBD | TBD |
| Human approver | TBD | TBD |

**Thresholds mutable after freeze?** `NO`
