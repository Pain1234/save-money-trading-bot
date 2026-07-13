# Strategy Lifecycle

Every strategy candidate passes through the same gated pipeline. **Rejection at any stage is a valid and expected outcome.**

---

## Pipeline

```text
Hypothese
  → Implementierung
    → In-Sample-Test
      → unangetasteter Out-of-Sample-Test
        → Walk-Forward
          → Kostenstress
            → Parameterstabilität
              → Paper Trading
                → Micro-Live (human approval)
                  → kontrollierte Skalierung (human approval)
```

---

## Stage definitions

| Stage | Purpose | Exit signal |
|-------|---------|-------------|
| Hypothesis | Economic rationale, falsifiable claim | Issue approved for implementation |
| Implementation | Code + tests aligned with specs | Unit/integration tests pass |
| In-Sample | Train/tune only on IS window | Documented IS metrics |
| Out-of-Sample | **Single use** holdout evaluation | Meets pre-defined accept criteria |
| Walk-Forward | Rolling train/test stability | No collapse in recent windows |
| Cost stress | Fees/slippage/funding shocks | Edge survives stress band |
| Parameter stability | Neighbor parameter region | No cliff edges |
| Paper trading | Production-shaped sim ≥ 90 days (P6) | Reconciliation clean; decay bounded |
| Micro-live | Real fills, minimal capital (P8) | Reconciliation vs exchange |
| Controlled scaling | Capital ramps with evidence (P9) | Drawdown rules enforced |

---

## Governance rules

1. **One promotion at a time** — do not activate multiple uncorrelated strategies in paper without ADR.
2. **Frozen parameters** after OOS lock — changes restart pipeline from Implementation.
3. **Correlation check** before P7 candidates — see `ROADMAP.md` P7.
4. **Human approval** before Micro-Live and Scaling (`human-approval-required` label).

---

## Strategy V1 (Trend)

Current state (evidence-based):

| Stage | Status |
|-------|--------|
| Spec | Frozen in `docs/strategy-specification.md` |
| Paper implementation | Internal orchestrator phases 1–9 complete |
| Formal P5 validation | **Not started** (roadmap) |
| Paper soak 90d | **Not started** |

---

## Artifacts

- Experiment reports: `docs/EXPERIMENT_TEMPLATE.md`
- Index: `docs/strategies/README.md`
- Roadmap gates: `ROADMAP.md` P4–P9
