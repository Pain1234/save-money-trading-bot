# Strategy Experiments Index

Registry of strategy research experiments. **Append only** — invalidate rather than delete.

---

## Active strategy specs

| Strategy | Spec | Implementation |
|----------|------|----------------|
| Trend V1 | `docs/strategy-specification.md` | `services/strategy_engine/` |

---

## Experiment log

| Experiment-ID | Date | Strategy | Decision | Report | Issue |
|---------------|------|----------|----------|--------|-------|
| — | — | — | — | — | — |

*No formal experiment reports filed yet. Use `docs/EXPERIMENT_TEMPLATE.md` when P4/P5 work begins.*

---

## Filing instructions

1. Create GitHub issue (`research-experiment` template).
2. Copy `docs/EXPERIMENT_TEMPLATE.md` to `docs/strategies/EXP-YYYYMMDD-NNN-slug.md`.
3. Add row to the table above.
4. Link git commit, dataset ID, and PR in the report.

---

## Invalidation

If a bug or data error invalidates results:

1. Set report `Status: invalidated` with reason and date.
2. Add label `status:invalidated` on the issue.
3. Keep the original report; add addendum section `## Invalidation`.
