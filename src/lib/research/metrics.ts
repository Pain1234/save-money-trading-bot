/** Shared metric label list for experiment detail + compare views (Issue #246).
 *
 * Single source of truth so both views render exactly the ResearchMetrics
 * fields the backend produces — never invented/blended values.
 */
export const RESEARCH_METRIC_LABELS: Array<{ key: string; label: string }> = [
  { key: "total_return", label: "Total Return" },
  { key: "cagr", label: "CAGR" },
  { key: "sharpe", label: "Sharpe" },
  { key: "sortino", label: "Sortino" },
  { key: "max_drawdown", label: "Maximum Drawdown" },
  { key: "profit_factor", label: "Profit Factor" },
  { key: "win_rate", label: "Win Rate" },
  { key: "trade_count", label: "Trade Count" },
  { key: "fees", label: "Gebühren" },
  { key: "slippage_costs", label: "Slippage" },
  { key: "funding_costs", label: "Funding" },
  { key: "net_pnl", label: "Net PnL" },
  { key: "gross_pnl", label: "Gross PnL" },
  { key: "expectancy", label: "Expectancy" },
  { key: "benchmark_result", label: "Benchmark Result" },
];
