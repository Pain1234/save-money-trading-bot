# Metrics definitions

Schema version: `1.1` (`ResearchMetrics` / `METRICS_SCHEMA_VERSION`).

Supported read versions: `1.0` (legacy, no required funding identity), `1.1` (current).

## Comparable fields

Required for `status=complete`:

- Capital: `start_capital`, `end_capital`
- PnL: `gross_pnl`, `net_pnl` (gross/net separated)
- Costs: `fees`, `slippage_costs`, `funding_costs`, `funding_assumption` (non-empty string)
- Counts: `signal_count`, `order_count`, `fill_count`, `closed_trades`
- Optional analytics: hit rate, avg win/loss, expectancy, profit factor, max drawdown, exposure, turnover, time in market
- Benchmark: `benchmark` (`BenchmarkRef`) + `benchmark_result`

Missing or incompatible benchmark/cost data fails validation; report status is `incomplete` or `invalid`. P4 does not make strategy promotion decisions.

## Benchmark contract (#144)

- `benchmark_id` + `benchmark_version` required on every complete report
- Spec field forms: `buy_and_hold_BTC` or `id@version`
- Period / dataset / cost parity flags must be `true` for P4 runs
- Computation (`services/research/benchmark.py`):
  - Supported id pattern: `buy_and_hold_<SYMBOL>`
  - Gross return = `(last_close - first_close) / first_close` over closed daily candles in the same dataset/period as the run
  - Net return applies Spec fee/slippage/funding (same cost model as the strategy; version recorded on `BenchmarkRef.cost_model_version`)
  - `benchmark_result` is **net**; `BenchmarkRef.gross_return` holds the pre-cost price return
  - `cost_parity=true` means benchmark and strategy share Spec cost assumptions (not that costs are zero)
  - Symbol must be in experiment symbols and present in the bundle (fail-closed otherwise)
- Output lands in `metrics.json` and `report.md`

## Costs (#49)

Fee / slippage / funding model versions are required on the Spec (and optional named `cost_scenarios`). Funding `assumed_rate` is applied via `FundingModel` and persisted in `costs.json` / RunManifest cost fields. Cost **stress** (sensitivity sweeps) is **P5**, not P4.
