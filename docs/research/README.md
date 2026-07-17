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

## End-to-end CLI example

Prerequisites: Python env with `pip install -e ".[dev]"`. No live exchange network.

```bash
# 1) Validate Spec (schema + required cost/strategy fields)
python -m research validate examples/research/btc_eth_sol_experiment.example.json

# 2) Dry-run identity only (no artifacts written)
python -m research run examples/research/btc_eth_sol_experiment.example.json \
  --bundle path/to/HistoricalDataBundle.json \
  --artifacts-root /tmp/research-out \
  --dry-run

# 3) Execute run → atomic artifacts under artifacts/research/<exp>/<run>/
python -m research run examples/research/btc_eth_sol_experiment.example.json \
  --bundle path/to/HistoricalDataBundle.json \
  --artifacts-root /tmp/research-out

# 4) Inspect metrics / manifest
python -m research inspect /tmp/research-out/artifacts/research/<experiment_id>/<run_id>

# 5) Registry operations
python -m research list --artifacts-root /tmp/research-out
python -m research show <run_id> --artifacts-root /tmp/research-out
python -m research compare <run_a> <run_b> --artifacts-root /tmp/research-out

# 6) Invalidate without mutating RunManifest
python -m research invalidate <run_id> \
  --reason "fixture correction" \
  --actor "you" \
  --artifacts-root /tmp/research-out
```

Offline unit/CI path (no CLI bundle file required):

```bash
python -m pytest tests/research tests/paper_trading/test_backtester_signal_parity.py -q
python -m pytest tests/research/test_double_run_repro.py -v
```

## CLI reference

| Command | Purpose |
|---------|---------|
| `validate <spec>` | Load + JSON-schema validate ExperimentSpec |
| `run <spec> --bundle <json> [--artifacts-root] [--dry-run]` | Execute or identity dry-run; registers on complete |
| `inspect <run_dir>` | Print manifest + metrics + experiment |
| `list [--artifacts-root]` | List registry entries |
| `show <run_id>` | Show one entry (verifies checksums) |
| `compare <run_a> <run_b>` | Compare two runs (compatibility + checksums) |
| `invalidate <run_id> --reason ... [--actor] [--replacement-run-id]` | Sidecar invalidation |

## Docs in this folder

- [EXPERIMENT_SPEC.md](EXPERIMENT_SPEC.md)
- [IDENTITY.md](IDENTITY.md)
- [STRATEGY_INTERFACE.md](STRATEGY_INTERFACE.md)
- [ARTIFACT_FORMAT.md](ARTIFACT_FORMAT.md)
- [METRICS_DEFINITIONS.md](METRICS_DEFINITIONS.md)
- [FUNDING.md](FUNDING.md)
- [REPRODUCIBILITY.md](REPRODUCIBILITY.md)
- [INVALIDATION.md](INVALIDATION.md)
- [P4_ACCEPTANCE.md](P4_ACCEPTANCE.md)
- [BACKTESTER_PAPER_PARITY.md](BACKTESTER_PAPER_PARITY.md)

## Phase boundaries

- **P4:** complete, comparable research artifacts
- **P5:** OOS / walk-forward / cost-stress robustness (not in P4)
- **P6:** promotion / live readiness (not in P4)
- **P7:** multi-asset / instrument identity (not in P4)

No live-trading guide is part of P4 docs. Examples must not contain secrets or exchange credentials.
