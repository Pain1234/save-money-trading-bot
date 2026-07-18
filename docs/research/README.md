# Research workflow (P4)

Offline, reproducible experiment pipeline for BTC/ETH/SOL paper research.

## Binding dependency chain

```text
P3 → #141 → #142 → {#144, #49, #148} → #143 → {#48, #145} → #146 → {#163…#167} → #147 → P4 research done → P5
```

Public-release gates (#176–#180) may remain open on the milestone after research docs (#147).

## Modules

| Module | Role |
|--------|------|
| `experiment_spec` | Versioned ExperimentSpec (#141) |
| `dataset_binding` | P3 DatasetManifest bind + quarantine (#163) |
| `identity` / `run_manifest` | experiment_id / run_id / attempt_id (#142) |
| `strategy_resolver` | Strategy interface + injected engine (#148 / #166) |
| `costs` | Cost field enforcement + backtester mapping (#49 / #164) |
| `metrics_contract` / `benchmark` | metrics.json + report.md + buy-and-hold (#144 / #164) |
| `runner` / `artifacts` | CLI runner + atomic layout (#143) |
| `registry` | Index + semantic compare + trust-anchor verify + invalidation (#145 / #165 / #167) |
| `repro` | Semantic double-run compare (#146) |
| `robustness` / `robustness_service` | Walk-forward / cost-stress / parameter-stability / bootstrap orchestration (#247) |
| `gate_policy` / `gate_evaluator` / `gate_service` | Versioned, evidence-bound gate evaluation + append-only persistence (#248) |
| `validation_study` / `validation_service` | Validation Study aggregate over experiments + robustness + gates, append-only human decision (#249) |
| `regime` | Versioned deterministic regime + transition classifier + sealed `regime_labels.json` (#285) |

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
| `show <run_id>` | Show one entry; verifies files against **registry** checksums (#165) |
| `compare <run_a> <run_b>` | Semantic Spec + RunManifest identity compare (#167); see below |
| `invalidate <run_id> --reason ... [--actor] [--replacement-run-id]` | Sidecar invalidation |

### Compare semantics (#167)

`compare` loads validated `experiment.json` / `run_manifest.json` and diffs:

- every key of `semantic_spec_dict()` as `spec.*` (symbols, time_range, starting_capital, fee/slippage/funding assumptions, parameters, random_seed, cost_scenarios, dataset hash, …)
- every key of `semantic_manifest_payload()` as `manifest.*` (git commit, env/schema/cost pins, …; excludes `attempt_id` / timestamps)
- registry entry status / version fields

Runs are compatible only when both are `complete` and there are **no** diffs. Invalidated runs are incompatible.

### Interpret costs

Read `costs.json` together with `metrics.json`: fee/slippage/funding model versions, `funding_semantics`, and the gross identity `net + fees + slippage + funding_costs`. Funding detail: [FUNDING.md](FUNDING.md). Cost **stress** sweeps are **P5**.

### Analyze failures

Incomplete/invalid runs stay out of “complete” registry status. Use `inspect` on the run directory, check binding errors (dataset/quality), and prefer a new `attempt_id` / corrected Spec over editing sealed artifacts.

### Archive and retention

Completed `(experiment_id, run_id)` directories are immutable. Keep originals; mark bad runs with `invalidate` (registry + sidecar). Do not rewrite `run_manifest.json` or reseal trust by editing only `checksums.json`.

## Docs in this folder

- [EXPERIMENT_SPEC.md](EXPERIMENT_SPEC.md)
- [IDENTITY.md](IDENTITY.md)
- [STRATEGY_INTERFACE.md](STRATEGY_INTERFACE.md)
- [ARTIFACT_FORMAT.md](ARTIFACT_FORMAT.md)
- [METRICS_DEFINITIONS.md](METRICS_DEFINITIONS.md)
- [FUNDING.md](FUNDING.md)
- [REPRODUCIBILITY.md](REPRODUCIBILITY.md)
- [INVALIDATION.md](INVALIDATION.md)
- [GATES.md](GATES.md)
- [VALIDATION_STUDIES.md](VALIDATION_STUDIES.md)
- [REGIME_SCORECARD.md](REGIME_SCORECARD.md) — P4.9 layered evidence scorecard contract (Epic #295 / #284)
- [P4_ACCEPTANCE.md](P4_ACCEPTANCE.md)
- [RESEARCH_WORKSPACE_ACCEPTANCE.md](RESEARCH_WORKSPACE_ACCEPTANCE.md) — Workspace E2E + manual UI acceptance (#250)
- [BACKTESTER_PAPER_PARITY.md](BACKTESTER_PAPER_PARITY.md)

## Phase boundaries

- **P4:** complete, comparable research artifacts + Workspace; P4.9 scorecard extends gates/validation without a parallel system
- **P5:** Honest validation planning and gates — see [`docs/research/p5/`](p5/README.md) (OOS / walk-forward / cost-stress are P5; not pre-empted by P4; scorecard policy bind #294)
- **P6:** promotion / live readiness (not in P4)
- **P7:** multi-asset / instrument identity (not in P4)

No live-trading guide is part of P4 docs. Examples must not contain secrets or exchange credentials.
