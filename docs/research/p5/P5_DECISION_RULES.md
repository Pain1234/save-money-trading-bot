# P5 Decision Rules (ACCEPT / REJECT / INCONCLUSIVE)

**Status:** PLANNING / NOT FROZEN
**Issue:** P5-02 / P5-09
**Hard rule:** Freeze before final OOS. No post-hoc threshold changes. Positive return alone never promotes.

## Outcomes

| Code | Promotion? | Meaning |
|------|------------|---------|
| `ACCEPT_FOR_P6` | Opens P6 gate only | Credible evidence under pre-registered rules + human approval |
| `REJECT` | No | Failed hard rules or failed final OOS gate |
| `INCONCLUSIVE` | No | Insufficient or non-decisive evidence |

## Hard REJECT (examples — binding once frozen)

Trigger `REJECT` (invalidate promotion path) when any apply:

- Data leakage or unsealed holdout used for tuning
- Wrong / unreproducible dataset identity
- Post-hoc parameter or filter change on the frozen candidate
- Final OOS fails pre-registered numeric gates
- Intolerable drawdown vs pre-approved limit (limit TBD at freeze)
- Net result fails under realistic **base** costs
- Result unacceptably dependent on few trades (per sufficiency rule)
- Clear walk-forward instability (pre-registered fold aggregation rules)
- Severe backtester / execution inconsistency vs documented parity
- Public leak of private results that compromises process integrity (process stop; decision may be `REJECT` or halt)

## INCONCLUSIVE (examples)

- Too few trades / too short history / inadequate regime coverage
- No genuine untouched holdout and no approved forward holdout yet
- Technical or data uncertainty without clear economic failure
- Contradictory evidence without meeting hard REJECT
- Bootstrap/MC not applicable **and** sample too weak for confidence (document)

Default when sufficiency fails: `INCONCLUSIVE`, not `ACCEPT_FOR_P6`.

## ACCEPT_FOR_P6 (all required)

All must hold:

- [ ] Final OOS gate passed under frozen rules
- [ ] Net result after costs adequate vs frozen benchmark-relative / absolute gates (TBD at freeze)
- [ ] Drawdown within pre-approved bound
- [ ] Walk-forward not driven by a single fold (aggregation rule TBD)
- [ ] Parameter sensitivity not extremely fragile
- [ ] Bootstrap/MC risk acceptable **or** documented N/A with sufficiency still met
- [ ] Sample sufficiency passed
- [ ] No leakage findings
- [ ] Full reproducibility (commit, dataset, manifests, seeds)
- [ ] Human approval recorded in `docs/DECISION_LOG.md`

## Numeric gates (template — fill before freeze)

| Gate | Direction | Proposed | Rationale | Human approval |
|------|-----------|----------|-----------|----------------|
| OOS net PnL vs cash | ≥ | TBD | TBD | TBD |
| OOS excess vs primary benchmark | ≥ / or informational | TBD | TBD | TBD |
| Max drawdown | ≤ | TBD | Risk spec alignment | TBD |
| Min trades (OOS) | ≥ | TBD | Sufficiency | TBD |
| Max top-N trade PnL share | ≤ | TBD | Fragility | TBD |
| Walk-forward fold pass rule | e.g. k of n | TBD | Stability | TBD |
| Cost-stress survival | base + named stresses | TBD | Realism | TBD |

Until filled and approved, execution remains blocked.

## Decision record (P5-09 template)

```text
Decision: ACCEPT_FOR_P6 | REJECT | INCONCLUSIVE
Candidate: strategy_id @ strategy_version @ git_sha
Evidence refs: (private paths + public issue links without metrics)
Deviations: none | ...
Human decider: ...
Date (UTC): ...
Decision log ADR: ...
```

No cherry-picking folds, regimes, or symbols to overturn a failed aggregate.
