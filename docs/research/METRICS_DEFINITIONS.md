# Metrics definitions

Schema version: `1.0` (`ResearchMetrics` in `services/research/metrics_contract.py`).

Required comparable fields include start/end capital, gross/net PnL, fees, slippage, funding assumption, trade counts, hit rate, expectancy, profit factor, max drawdown, and benchmark.

## Benchmark contract

- `benchmark_id` + `benchmark_version` required
- Spec field forms: `buy_and_hold_BTC` or `id@version`
- Period / dataset / cost parity flags must be declared
- Missing or incompatible benchmark/cost data fails schema/run validation; report status is `incomplete` or `invalid` (P4 does not make strategy promotion decisions)
