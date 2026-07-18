# Experiment Report Template

Copy this template for each research experiment. Store completed reports under `docs/strategies/` as `EXP-YYYYMMDD-NNN-short-title.md` or attach to the GitHub issue.

Before running an experiment, define a machine-validated **ExperimentSpec** (`schema_version: "1.0"`). See [`docs/research/EXPERIMENT_SPEC.md`](research/EXPERIMENT_SPEC.md) and `examples/research/btc_eth_sol_experiment.example.json`.

---

```text
Experiment-ID:
Titel:
Datum:
Status: planned | running | complete | invalidated

Strategieversion:
Git-Commit:
Dataset-ID:
Zeitraum:
Märkte:

Hypothese:
wirtschaftliche Begründung:

Konfiguration:
  (paths to config files or inline YAML/JSON snapshot)

Kostenannahmen:
  fees:
  slippage:
  funding:

Benchmark:

In-Sample-Bereich:
Out-of-Sample-Bereich:
  (OOS must remain untouched until final evaluation)

Ergebnisse:
  metrics:
  charts/artifacts:

Robustheitstests:
  walk-forward:
  cost stress:
  parameter stability:
  bootstrap / Monte Carlo:

Regime Evidence Scorecard (P4.9 — if evaluated; see docs/research/REGIME_SCORECARD.md):
  scorecard_id / policy_version:
  integrity: VALID | INVALID | NOT_VERIFIABLE
  critical_gates: PASS | FAIL | INCONCLUSIVE | NOT_AVAILABLE
  worst_regime / worst_transition:
  evidence_confidence:
  main_weakness:
  (Do not replace accept/reject with a total score. No auto-promotion.)

bekannte Einschränkungen:

Entscheidung: accept | reject | inconclusive

Annahme- oder Ablehnungsgrund:

Folgeexperiment:

GitHub Issue:
Pull Request:
```

---

## Rules

- Assign Experiment-ID before running OOS (e.g. `EXP-20260713-001`).
- Record exact git commit and dataset version **before** viewing OOS results.
- Invalidated experiments: copy report, set `Status: invalidated`, add `Invalidation reason:` section — do not delete original.
- Link from `docs/strategies/README.md` index table.
- Layered scorecard fields (integrity / gates / regime / confidence) must stay separate; never invent missing metrics as zero.
