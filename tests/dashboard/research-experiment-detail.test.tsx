import React from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";

const fetchResearchExperiment = vi.fn();

vi.mock("@/lib/research-api/client", async () => {
  const actual = await vi.importActual<
    typeof import("../../src/lib/research-api/client")
  >("../../src/lib/research-api/client");
  return {
    ...actual,
    fetchResearchExperiment: (...args: unknown[]) =>
      fetchResearchExperiment(...args),
  };
});

vi.mock("@/components/research/ExperimentJobPanel", () => ({
  ExperimentJobPanel: () =>
    React.createElement("div", { "data-testid": "job-panel-stub" }, "job"),
}));

vi.mock("@/components/research/ResearchCharts", () => ({
  ResearchCharts: () =>
    React.createElement("div", { "data-testid": "charts-stub" }),
}));

vi.mock("@/components/research/ResearchTradeChart", () => ({
  ResearchTradeChart: () =>
    React.createElement("div", { "data-testid": "trade-chart-stub" }),
}));

import ResearchExperimentDetailPage from "../../src/app/dashboard/research/experiments/[experimentId]/page";

const JOB_ONLY_FAILED_DETAIL = {
  summary: {
    experiment_id: "exp_failed_job_only_001",
    run_id: "run_x",
    status: "failed",
    strategy_version: "trend-v1.0.0",
    strategy_id: "trend_v1",
    dataset_version: "fixture",
    cost_model_version: null,
    benchmark_ref: "buy_and_hold_BTC",
    created_at: "2024-01-01T00:00:00+00:00",
    symbols: ["BTC"],
    time_range_start: "2024-01-01T00:00:00+00:00",
    time_range_end: "2024-01-31T23:59:59+00:00",
    timeframe: null,
    git_commit: null,
    duration_seconds: 1,
    net_pnl: null,
    max_drawdown: null,
    closed_trades: null,
    hit_rate: null,
    profit_factor: null,
    integrity_ok: false,
    integrity_error: "time_range.start is before DatasetManifest.start_timestamp",
  },
  metadata: {
    experiment_id: "exp_failed_job_only_001",
    run_id: "run_x",
    status: "failed",
    strategy_version: "trend-v1.0.0",
    git_commit: null,
    dataset_version: "fixture",
    seed: 7,
    created_at: "2024-01-01T00:00:00+00:00",
    started_at: "2024-01-01T00:00:00+00:00",
    finalized_at: "2024-01-01T00:00:01+00:00",
    duration_seconds: 1,
  },
  config: {
    symbols: ["BTC"],
    time_range_start: "2024-01-01T00:00:00+00:00",
    time_range_end: "2024-01-31T23:59:59+00:00",
    timeframe: "Nicht verfügbar",
    starting_capital: "100000",
    parameters: { strategy_id: "trend_v1" },
    fee_assumption: null,
    slippage_assumption: null,
    funding_assumption: null,
    costs: null,
    in_sample_config: "Nicht verfügbar",
    out_of_sample_config: "Nicht verfügbar",
    benchmark: "buy_and_hold_BTC",
    hypothesis: "failed lab",
  },
  metrics: {},
  equity: [],
  drawdown: [],
  artifacts: {
    has_experiment_spec: true,
    has_run_manifest: false,
    has_metrics: false,
    has_equity: false,
    has_costs: false,
    has_trades: false,
    has_chart_data: false,
  },
  integrity: {
    ok: false,
    error: "time_range.start is before DatasetManifest.start_timestamp",
  },
  job: {
    experiment_id: "exp_failed_job_only_001",
    status: "failed",
    error: "time_range.start is before DatasetManifest.start_timestamp",
  },
};

describe("ResearchExperimentDetailPage job-only failed render (#278)", () => {
  beforeEach(() => {
    fetchResearchExperiment.mockReset();
  });

  it("renders detail for failed job-only payload instead of Research API Error", async () => {
    fetchResearchExperiment.mockResolvedValue(JOB_ONLY_FAILED_DETAIL);

    const element = await ResearchExperimentDetailPage({
      params: Promise.resolve({ experimentId: "exp_failed_job_only_001" }),
    });
    const html = renderToStaticMarkup(element);

    expect(html).toContain('data-testid="research-detail-ready"');
    expect(html).not.toContain('data-testid="research-detail-error"');
    expect(html).not.toContain("Research API Error");
    expect(html).toContain("exp_failed_job_only_001");
    expect(html).toContain("failed");
    expect(html).toContain("Nicht verfügbar");
    expect(html).toContain('data-testid="research-integrity-warning"');
  });

  it("hardens missing config/metrics without crashing into API error", async () => {
    fetchResearchExperiment.mockResolvedValue({
      ...JOB_ONLY_FAILED_DETAIL,
      config: undefined,
      metrics: undefined,
      integrity: { ok: false, error: "failed" },
      job: { status: "failed", error: "boom" },
      metadata: {
        experiment_id: "exp_sparse",
        run_id: null,
        status: "failed",
        strategy_version: null,
        git_commit: null,
        dataset_version: null,
        seed: null,
        created_at: null,
        started_at: null,
        finalized_at: null,
        duration_seconds: null,
      },
    });

    const element = await ResearchExperimentDetailPage({
      params: Promise.resolve({ experimentId: "exp_sparse" }),
    });
    const html = renderToStaticMarkup(element);

    expect(html).toContain('data-testid="research-detail-ready"');
    expect(html).not.toContain("Research API Error");
    expect(html).toContain("Nicht verfügbar");
  });
});
