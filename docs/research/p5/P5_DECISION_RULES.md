# P5 Decision Rules (ACCEPT / REJECT / INCONCLUSIVE)

**Contract status:** DECISION RULES FROZEN; final #205 decision not recorded.
Current phase authority: [P5_EXECUTION_STATUS.md](P5_EXECUTION_STATUS.md).
**Issue:** [#198](https://github.com/Pain1234/save-money-trading-bot/issues/198) / [#205](https://github.com/Pain1234/save-money-trading-bot/issues/205)
**Hard rule:** Freeze before final OOS. No post-hoc threshold changes. Positive return alone never promotes.

## Outcomes

| Code | Promotion? | Meaning |
|------|------------|---------|
| `ACCEPT_FOR_P6` | Opens P6 gate only | Credible evidence under pre-registered rules + human approval |
| `REJECT` | No | Failed hard rules or failed final OOS gate |
| `INCONCLUSIVE` | No | Insufficient or non-decisive evidence |

## Hard REJECT (binding once frozen)

- Data leakage or unsealed holdout used for tuning
- Wrong / unreproducible dataset identity
- Post-hoc parameter or filter change on the frozen candidate
- Final OOS fails pre-registered numeric gates
- Max drawdown worse than −25% of starting capital on OOS equity (proposed)
- Net PnL under **base** costs ≤ 0 on OOS (proposed hard floor)
- Top-3 trades contribute > 50% of OOS net PnL
- Walk-forward: fewer than 2 of ≥3 folds with net PnL ≥ 0 under base costs (proposed)
- Cost stress: net PnL < 0 under **`combined_elevated`** on the same window used for the cost-stress pack (proposed)
- Parameter fragility fails the measurable rule below
- Severe backtester / execution inconsistency vs documented parity
- Public leak of private results that compromises process integrity

## INCONCLUSIVE

- Sample sufficiency fails
- Forward holdout shorter than 90 days at evaluation time
- Inadequate regime coverage (< 2 regimes)
- Technical/data uncertainty without clear economic failure
- Bootstrap/MC N/A **and** sample too weak

Default when sufficiency fails: `INCONCLUSIVE`, not `ACCEPT_FOR_P6`.

## ACCEPT_FOR_P6 (all required)

- [ ] Final OOS gate passed under frozen numeric rules
- [ ] OOS net PnL > 0 under base costs
- [ ] OOS max drawdown ≥ −25% bound (not worse)
- [ ] Walk-forward fold rule passed
- [ ] Cost stress: net PnL ≥ 0 under **`combined_elevated`** (required)
- [ ] Parameter sensitivity **not extremely fragile** per measurable rule below
- [ ] Bootstrap/MC: **5% path net-PnL quantile ≥ 0** via `block_bootstrap_paths` **or** documented N/A with sufficiency still met
- [ ] Sample sufficiency passed
- [ ] No leakage findings
- [ ] Full reproducibility
- [ ] Human approval in `docs/DECISION_LOG.md`

Benchmark excess vs `eq_weight_btc_eth_sol@1.0` is **informational** for V1 (not a hard ACCEPT gate) to avoid unsuitable-benchmark flattery; cash/net and drawdown remain hard.

## Parameter fragility (measurable, pre-registered)

Let `N` = number of variants from `symmetric_neighborhood(frozen)` **excluding** the frozen point itself.
On partition B under **base** costs, with identical dataset/window:

- **Pass (not extremely fragile):** at least `ceil(0.5 * N)` neighbors have net PnL ≥ 0.
- **Fail (extremely fragile → hard REJECT):** fewer than `ceil(0.5 * N)` neighbors have net PnL ≥ 0.

Neighbor success still cannot replace a failed frozen candidate (frozen must pass its own gates).

## Numeric gates (proposed — human must approve)

| Gate | Direction | Proposed | Rationale | Human approval |
|------|-----------|----------|-----------|----------------|
| OOS net PnL vs cash | > | 0 | Must beat inactivity after costs | Pending |
| OOS excess vs eq-weight portfolio | informational | — | Avoid forced alpha vs arbitrary weights | Pending |
| Max drawdown | ≥ | −25% of start capital | Risk budget proxy pending risk-spec ADR | Pending |
| Min trades (OOS) | ≥ | 30 | Sufficiency | Pending |
| Max top-3 trade PnL share | ≤ | 50% | Fragility | Pending |
| Walk-forward fold pass | ≥ | 2 of n (n≥3) net≥0 | Stability | Pending |
| Cost-stress survival (`combined_elevated`) | net≥0 | required | Realism; also on Accept checklist | Pending |
| Combined extreme stress | informational / soft | may be <0 | Document; not sole REJECT unless base also fails | Pending |
| Parameter neighborhood | ≥ ceil(0.5×N) neighbors net≥0 | required | Removes “not extremely fragile” discretion | Pending |
| Bootstrap 5% path net-PnL quantile | ≥ | 0 | Path dependence; not mean-of-means | Pending |

Until human comments `DECISION RULES FROZEN` on #198, OOS execution remains blocked.

## Relationship to P4.9 scorecard

Generic P4 gate/scorecard infrastructure ([#248](https://github.com/Pain1234/save-money-trading-bot/issues/248),
Epic [#295](https://github.com/Pain1234/save-money-trading-bot/issues/295)) must **not**
hard-code these proposed Strategy V1 numbers. Binding of frozen scorecard /
classifier / behaviour / confidence policy versions to Strategy V1 is documented in
[P5_SCORECARD_POLICY_BIND.md](P5_SCORECARD_POLICY_BIND.md) /
[#294](https://github.com/Pain1234/save-money-trading-bot/issues/294) (ADR-020;
Human Freeze sign-off pending). A scorecard PASS or high regime quality score
never auto-emits `ACCEPT_FOR_P6`.

## Decision record (P5-09 template)

```text
Decision: ACCEPT_FOR_P6 | REJECT | INCONCLUSIVE
Candidate: trend_v1 @ 1.0.0 @ <git_sha>
Evidence refs: (private paths + public issue links without metrics)
Deviations: none | ...
Human decider: ...
Date (UTC): ...
Decision log ADR: ...
```

No cherry-picking folds, regimes, or symbols to overturn a failed aggregate.
