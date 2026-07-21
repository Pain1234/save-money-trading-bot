# ExperimentSpec (P4-01)

Versioned research experiment contract for comparable, reproducible paper runs.

- **Issue:** [#141](https://github.com/Pain1234/save-money-trading-bot/issues/141)
- **Package:** `services/research/`
- **Schema:** `services/research/schema/experiment_spec.schema.json` (`schema_version: "1.0"`)
- **Example:** `examples/research/btc_eth_sol_experiment.example.json` (and `.yaml`)

## What it pins

| Field | Purpose |
| --- | --- |
| `hypothesis` | Stated research claim |
| `strategy_version` | Strategy engine / spec version under test |
| `parameters` | Parameter snapshot (no secrets) |
| `dataset_manifest_ref` | P3 `DatasetManifest` pin: `dataset_id`, `content_hash`, optional `manifest_path` |
| `symbols` | `BTC` / `ETH` / `SOL` only |
| `symbol_constraints` | Sealed per-symbol exchange pins (`quantity_step`, `minimum_quantity`, `minimum_notional`, `price_tick_size`); must cover Spec symbols exactly ([#363](https://github.com/Pain1234/save-money-trading-bot/issues/363)) |
| `time_range` | UTC window |
| `starting_capital` | Initial capital |
| `fee_assumption` / `slippage_assumption` / `funding_assumption` | Cost model |
| `benchmark` | Comparison baseline |
| `random_seed` | Optional reproducibility seed |
| `expected_artifacts` / `notes` / `owner` | Run bookkeeping |

The full `DatasetManifest` is **not** embedded ÔÇö only a reference (id/path + hash). See `services/market_data/manifest.py`.

## Dataset binding at run time (#163)

Before a complete run or registry entry:

1. `dataset_manifest_ref.manifest_path` is **required**
2. P3 `DatasetManifest` is loaded; `INVALID` / `DISCONNECTED` are quarantined;
   `STALE` / `INCOMPLETE` require `allow_quality_warnings=true`
3. Spec `dataset_id` / `content_hash` / symbols / `time_range` Ôèå manifest window
4. Bundle candles for experiment symbols must lie inside the **manifest** window
5. `content_hash` is verified against candles in the **manifest** window (full
   published dataset identity). Funding events are **not** part of this hash.
6. `ExperimentSpec.time_range` is then applied (filter) for the research run

Implementation: `services/research/dataset_binding.py` (called from `runner.run_experiment`).

## Rules

- Unknown fields are **rejected** (`extra=forbid`).
- Unknown or misspelled `parameters` keys are **rejected** before identity/run creation
  (`StrategyParameters` with `extra=forbid`; optional catalog key `strategy_id` allowed).
- Parsed Specs **bind** `parameters` to the effective StrategyParameters snapshot (defaults
  applied), so `experiment_id` / `run_id` reflect executed configuration ([#375](https://github.com/Pain1234/save-money-trading-bot/issues/375) / AUD-P1-002).
- Credential-like keys (`api_key`, `password`, `secret`, `token`, …) are **rejected**.
- Serialization is deterministic (stable key order, decimal strings, UTC timestamps).
- Paper/research only — no live trading keys in specs.

### Migration note (AUD-P1-002)

Specs that previously carried unknown parameter keys now fail validation. Specs that
omitted fields relying on engine defaults will canonicalize those defaults into
`parameters` and therefore may receive a **new** `experiment_id` / `run_id`. Treat
prior IDs from incomplete parameter snapshots as non-comparable; re-seal or invalidate
as needed before P5 evidence use.

## Usage

```python
from research import load_experiment_spec, dumps_canonical

spec = load_experiment_spec("examples/research/btc_eth_sol_experiment.example.json")
payload = dumps_canonical(spec)  # stable bytes
```

Report write-ups still use [`docs/EXPERIMENT_TEMPLATE.md`](../EXPERIMENT_TEMPLATE.md). Workflow and CLI: [`docs/research/README.md`](README.md).
