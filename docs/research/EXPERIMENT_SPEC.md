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
| `time_range` | UTC window |
| `starting_capital` | Initial capital |
| `fee_assumption` / `slippage_assumption` / `funding_assumption` | Cost model |
| `benchmark` | Comparison baseline |
| `random_seed` | Optional reproducibility seed |
| `expected_artifacts` / `notes` / `owner` | Run bookkeeping |

The full `DatasetManifest` is **not** embedded — only a reference (id/path + hash). See `services/market_data/manifest.py`.

## Rules

- Unknown fields are **rejected** (`extra=forbid`).
- Credential-like keys (`api_key`, `password`, `secret`, `token`, …) are **rejected**.
- Serialization is deterministic (stable key order, decimal strings, UTC timestamps).
- Paper/research only — no live trading keys in specs.

## Usage

```python
from research import load_experiment_spec, dumps_canonical

spec = load_experiment_spec("examples/research/btc_eth_sol_experiment.example.json")
payload = dumps_canonical(spec)  # stable bytes
```

Report write-ups still use [`docs/EXPERIMENT_TEMPLATE.md`](../EXPERIMENT_TEMPLATE.md). Fuller research docs land in a later issue (#147).
