# Experiment Report Template

Copy this template for each research experiment. Store completed reports under `docs/strategies/` as `EXP-YYYYMMDD-NNN-short-title.md` or attach to the GitHub issue.

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
