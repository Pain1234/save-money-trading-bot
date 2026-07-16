# Research workflow (P4)

Offline, reproducible experiment pipeline for BTC/ETH/SOL paper research.

## Binding dependency chain

```text
P3 → #141 → #142 → {#144, #49, #148} → #143 → {#48, #145} → #146 → #147 → P4 done → P5
```

## Modules

| Module | Role |
|--------|------|
| `experiment_spec` | Versioned ExperimentSpec (#141) |
| `identity` / `run_manifest` | experiment_id / run_id / attempt_id (#142) |
| `strategy_resolver` | Strategy interface + Trend V1 resolver (#148) |
| `costs` | Cost field enforcement + backtester mapping (#49) |
| `metrics_contract` / `benchmark` | metrics.json + report.md + buy-and-hold (#144) |
| `runner` / `artifacts` | CLI runner + atomic layout (#143) |
| `registry` | Index + compare + invalidation sidecar (#145) |
| `repro` | Semantic double-run compare (#146) |

## CLI

```bash
python -m research validate <spec.yaml|json>
python -m research run <spec> --bundle <HistoricalDataBundle.json> [--dry-run]
python -m research inspect <run_dir>
python -m research list|show|compare|invalidate ...
```

## Docs in this folder

- [EXPERIMENT_SPEC.md](EXPERIMENT_SPEC.md)
- [IDENTITY.md](IDENTITY.md)
- [STRATEGY_INTERFACE.md](STRATEGY_INTERFACE.md)
- [ARTIFACT_FORMAT.md](ARTIFACT_FORMAT.md)
- [METRICS_DEFINITIONS.md](METRICS_DEFINITIONS.md)
- [REPRODUCIBILITY.md](REPRODUCIBILITY.md)
- [INVALIDATION.md](INVALIDATION.md)
- [P4_ACCEPTANCE.md](P4_ACCEPTANCE.md)
- [BACKTESTER_PAPER_PARITY.md](BACKTESTER_PAPER_PARITY.md)

## Phase boundaries

- **P4:** complete, comparable research artifacts
- **P5:** OOS / walk-forward / cost-stress robustness (not in P4)
- **P7:** multi-asset / instrument identity (not in P4)
