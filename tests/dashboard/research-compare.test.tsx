import React from "react";
import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";

import {
  CompareEmptyHint,
  CompareError,
  CompareResultView,
  CompareSelector,
} from "../../src/components/research/CompareView";
import type {
  ResearchCompareResult,
  ResearchCompareRunView,
} from "../../src/lib/research-api/client";

function runView(
  overrides: Partial<ResearchCompareRunView> = {},
): ResearchCompareRunView {
  return {
    summary: {
      experiment_id: "exp-a",
      run_id: "run-a",
      status: "complete",
      strategy_version: "trend-v1.0.0",
      strategy_id: "trend_v1",
      dataset_version: "ds-1",
      cost_model_version: "1.0",
      benchmark_ref: "buy_hold_btc",
      created_at: "2024-06-01T12:00:00Z",
      symbols: ["BTC"],
      time_range_start: "2024-01-01T00:00:00Z",
      time_range_end: "2024-03-01T00:00:00Z",
      timeframe: null,
      git_commit: "abc123",
      duration_seconds: null,
      net_pnl: "10000",
      max_drawdown: "0.12",
      closed_trades: 10,
      hit_rate: "0.55",
      profit_factor: "1.4",
      integrity_ok: true,
      integrity_error: null,
    },
    metadata: {
      experiment_id: "exp-a",
      run_id: "run-a",
      status: "complete",
      strategy_version: "trend-v1.0.0",
      git_commit: "abc123",
      dataset_version: "ds-1",
      seed: 7,
      created_at: "2024-06-01T12:00:00Z",
      started_at: null,
      finalized_at: "2024-06-01T12:00:00Z",
      duration_seconds: null,
    },
    config: {
      symbols: ["BTC"],
      time_range_start: "2024-01-01T00:00:00Z",
      time_range_end: "2024-03-01T00:00:00Z",
      timeframe: "Nicht verfügbar",
      starting_capital: "100000",
      parameters: { lookback: 20 },
      fee_assumption: { entry_fee_rate: "0.0005" },
      slippage_assumption: { slippage_bps: "5" },
      funding_assumption: { enabled: false },
      costs: null,
      in_sample_config: "Nicht verfügbar",
      out_of_sample_config: "Nicht verfügbar",
      benchmark: "buy_hold_btc",
      hypothesis: "smoke",
    },
    metrics: {
      total_return: "0.1",
      cagr: "Nicht verfügbar",
      sharpe: "Nicht verfügbar",
      sortino: "Nicht verfügbar",
      max_drawdown: "0.12",
      profit_factor: "1.4",
      win_rate: "0.55",
      trade_count: "10",
      fees: "400",
      slippage_costs: "100",
      funding_costs: "0",
      net_pnl: "10000",
      gross_pnl: "10500",
      expectancy: "100",
      benchmark_result: "0.05",
    },
    equity: [
      { t: "2024-01-01T00:00:00Z", equity: 100000 },
      { t: "2024-03-01T00:00:00Z", equity: 110000 },
    ],
    drawdown: [{ t: "2024-01-01T00:00:00Z", drawdown: 0 }],
    artifacts: {
      has_experiment_spec: true,
      has_run_manifest: true,
      has_metrics: true,
      has_equity: true,
      has_costs: true,
      has_trades: true,
      has_chart_data: true,
    },
    integrity: { ok: true, error: null },
    ...overrides,
  };
}

function compareResult(
  overrides: Partial<ResearchCompareResult> = {},
): ResearchCompareResult {
  return {
    compatible: true,
    run_a: "run-a",
    run_b: "run-b",
    diffs: {},
    runs: {
      a: runView(),
      b: runView({
        summary: { ...runView().summary, run_id: "run-b", experiment_id: "exp-b" },
        metadata: { ...runView().metadata, run_id: "run-b", experiment_id: "exp-b" },
        metrics: { ...runView().metrics, net_pnl: "20000" },
      }),
    },
    ...overrides,
  };
}

describe("CompareSelector", () => {
  it("renders run_a/run_b selects with options", () => {
    const html = renderToStaticMarkup(
      <CompareSelector
        items={[
          { run_id: "run-a", experiment_id: "exp-a", strategy_version: "trend-v1.0.0", status: "complete" },
          { run_id: "run-b", experiment_id: "exp-b", strategy_version: "trend-v1.0.0", status: "complete" },
        ]}
        runA="run-a"
        runB=""
      />,
    );
    expect(html).toContain("research-compare-form");
    expect(html).toContain("research-compare-select-a");
    expect(html).toContain("research-compare-select-b");
    expect(html).toContain("run-a");
    expect(html).toContain("run-b");
    expect(html).toContain("research-compare-submit");
  });
});

describe("CompareEmptyHint / CompareError", () => {
  it("renders empty hint", () => {
    const html = renderToStaticMarkup(<CompareEmptyHint />);
    expect(html).toContain("research-compare-empty");
  });

  it("renders error banner with message, no invented data", () => {
    const html = renderToStaticMarkup(
      <CompareError message="Ein oder beide Runs wurden nicht gefunden." />,
    );
    expect(html).toContain("research-compare-error");
    expect(html).toContain("nicht gefunden");
  });
});

describe("CompareResultView", () => {
  it("renders compatible banner with no diffs", () => {
    const html = renderToStaticMarkup(
      <CompareResultView result={compareResult()} />,
    );
    expect(html).toContain("research-compare-compatible");
    expect(html).not.toContain("research-compare-incompatible");
    expect(html).toContain("research-compare-diffs-empty");
    expect(html).toContain("10000");
    expect(html).toContain("20000");
  });

  it("renders incompatible banner and diffs table, never blending values", () => {
    const html = renderToStaticMarkup(
      <CompareResultView
        result={compareResult({
          compatible: false,
          diffs: {
            "spec.symbols": [["BTC"], ["BTC", "ETH"]],
            status: ["complete", "failed"],
          },
        })}
      />,
    );
    expect(html).toContain("research-compare-incompatible");
    expect(html).not.toContain('data-testid="research-compare-compatible"');
    expect(html).toContain("research-compare-diffs");
    expect(html).toContain("spec.symbols");
    expect(html).toContain("diff-row-status");
  });

  it("shows integrity fail-closed notice per run instead of hiding it", () => {
    const html = renderToStaticMarkup(
      <CompareResultView
        result={compareResult({
          runs: {
            a: runView({ integrity: { ok: false, error: "checksum mismatch" } }),
            b: runView({ summary: { ...runView().summary, run_id: "run-b" } }),
          },
        })}
      />,
    );
    expect(html).toContain("research-compare-integrity-Run A");
    expect(html).toContain("checksum mismatch");
  });
});
