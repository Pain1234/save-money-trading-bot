import React from "react";
import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";

import { ResearchOverviewView } from "../../src/components/research/ResearchOverviewView";
import {
  buildExecutiveSummary,
  UNAVAILABLE,
} from "../../src/lib/research/executive-summary";
import type {
  GateRunRecord,
  ResearchOverview,
  RobustnessJobSummary,
  ValidationStudyDetail,
} from "../../src/lib/research-api/client";

const EMPTY_OVERVIEW: ResearchOverview = {
  experiment_count: 0,
  completed_count: 0,
  failed_count: 0,
  invalidated_count: 0,
  running_count: null,
  running_available: false,
  strategy_version_count: 0,
  known_strategy_ids: [],
  status_distribution: {},
  recent_experiments: [],
  unavailable: {},
};

const OVERVIEW_WITH_EXPERIMENTS: ResearchOverview = {
  ...EMPTY_OVERVIEW,
  experiment_count: 2,
  completed_count: 1,
  failed_count: 0,
  strategy_version_count: 1,
  known_strategy_ids: ["trend_v1"],
  status_distribution: { complete: 1, running: 1 },
  recent_experiments: [
    {
      experiment_id: "exp_a",
      run_id: "run_a",
      status: "complete",
      strategy_version: "1.0.0",
      strategy_id: "trend_v1",
      dataset_version: "ds1",
      cost_model_version: "c1",
      benchmark_ref: "bh",
      created_at: "2024-01-02T00:00:00Z",
      symbols: ["BTC"],
      time_range_start: null,
      time_range_end: null,
      timeframe: "1h",
      git_commit: "abc",
      duration_seconds: 10,
      net_pnl: "1.0",
      max_drawdown: "-0.1",
      closed_trades: 2,
      hit_rate: null,
      profit_factor: null,
      integrity_ok: true,
      integrity_error: null,
    },
    {
      experiment_id: "exp_b",
      run_id: "run_b",
      status: "complete",
      strategy_version: "1.0.0",
      strategy_id: "trend_v1",
      dataset_version: "ds1",
      cost_model_version: "c1",
      benchmark_ref: "bh",
      created_at: "2024-01-01T00:00:00Z",
      symbols: ["BTC"],
      time_range_start: null,
      time_range_end: null,
      timeframe: "1h",
      git_commit: "def",
      duration_seconds: 10,
      net_pnl: null,
      max_drawdown: null,
      closed_trades: null,
      hit_rate: null,
      profit_factor: null,
      integrity_ok: false,
      integrity_error: "checksum mismatch",
    },
  ],
};

const GATE_PASS: GateRunRecord = {
  schema_version: "1.0",
  gate_run_id: "gate_pass",
  policy_version: "1.0",
  policy_content_hash: "b".repeat(64),
  evaluated_at: "2024-01-03T00:00:00Z",
  run_code_commit: "c".repeat(40),
  evaluation_code_commit: "d".repeat(40),
  experiment_id: "exp_a",
  run_id: "run_a",
  robustness_run_ids: [],
  dataset_id: "ds1",
  dataset_content_hash: "e".repeat(64),
  artifact_checksums: {},
  measurements: {},
  gates: [],
  overall_status: "pass",
  promotion_action: "none",
  status: "active",
  invalidation_reason: null,
};

const GATE_FAIL: GateRunRecord = {
  ...GATE_PASS,
  gate_run_id: "gate_fail",
  overall_status: "fail",
  evaluated_at: "2024-01-04T00:00:00Z",
};

const STUDY_DECIDED: ValidationStudyDetail = {
  schema_version: "1.0",
  study_id: "study_1",
  created_at: "2024-01-05T00:00:00Z",
  name: "Synthetic study",
  strategy_id: "trend_v1",
  strategy_version: "1.0.0",
  experiment_id: "exp_a",
  run_id: "run_a",
  additional_experiment_ids: [],
  robustness_ids: [],
  gate_run_ids: ["gate_pass"],
  notes: "",
  status: "decided",
  decision: {
    outcome: "accept",
    rationale: "fixture",
    decided_by: "reviewer",
    decided_at: "2024-01-05T01:00:00Z",
    evidence_snapshot_id: "snap_1",
  },
  experiments: [],
  robustness: [],
  robustness_by_type: {},
  gates: [],
  progress: {
    experiments: { total: 1, complete: 1 },
    robustness: { total: 0, completed: 0, failed: 0, running: 0 },
    gates: { total: 1, pass: 1, fail: 0 },
  },
  reproducibility: {
    git_commit: null,
    evaluation_code_commit: null,
    dataset_id: null,
    dataset_content_hash: null,
    policy_version: null,
    policy_content_hash: null,
    source: "experiment_run",
  },
};

const COST_JOB: RobustnessJobSummary = {
  robustness_id: "rob_cost",
  base_experiment_id: "exp_a",
  test_type: "cost_stress",
  status: "completed",
  created_at: "2024-01-02T00:00:00Z",
  updated_at: "2024-01-02T00:00:00Z",
  started_at: null,
  finished_at: null,
  error: null,
  error_detail: null,
  dataset_catalog_id: null,
  config: null,
};

describe("buildExecutiveSummary", () => {
  it("marks scorecard fields unavailable without inventing metrics", () => {
    const summary = buildExecutiveSummary({
      overview: EMPTY_OVERVIEW,
      gateRuns: [],
      studies: [],
      robustnessJobs: [],
    });

    const byId = Object.fromEntries(summary.cells.map((c) => [c.id, c]));
    expect(byId["evidence-confidence"]?.value).toBe(UNAVAILABLE);
    expect(byId["worst-regime"]?.value).toBe(UNAVAILABLE);
    expect(byId["cost-stress"]?.value).toBe(UNAVAILABLE);
    expect(byId["parameter-area"]?.value).toBe(UNAVAILABLE);
    expect(byId.integrity?.value).toBe(UNAVAILABLE);
    expect(byId["critical-gates"]?.value).toBe(UNAVAILABLE);
    expect(byId["final-decision"]?.value).toBe(UNAVAILABLE);
    expect(summary.freezeLabel).toBe(UNAVAILABLE);
    expect(JSON.stringify(summary)).not.toMatch(/123\.45|0\.87|demo.?pnl/i);
  });

  it("derives integrity INVALID and critical FAIL from existing APIs", () => {
    const summary = buildExecutiveSummary({
      overview: OVERVIEW_WITH_EXPERIMENTS,
      gateRuns: [GATE_PASS, GATE_FAIL],
      studies: [STUDY_DECIDED],
      robustnessJobs: [COST_JOB],
    });

    const byId = Object.fromEntries(summary.cells.map((c) => [c.id, c]));
    expect(byId.integrity?.value).toBe("INVALID");
    expect(byId["critical-gates"]?.value).toBe("FAIL");
    expect(byId["final-decision"]?.value).toBe("ACCEPT");
    expect(byId["cost-stress"]?.value).toBe(UNAVAILABLE);
    expect(byId["cost-stress"]?.detail).toMatch(/Jobs 1 complete/);
    expect(summary.strategyId).toBe("trend_v1");
  });

  it("shows pending decision when studies are open", () => {
    const openStudy: ValidationStudyDetail = {
      ...STUDY_DECIDED,
      study_id: "study_open",
      status: "open",
      decision: null,
    };
    const summary = buildExecutiveSummary({
      overview: OVERVIEW_WITH_EXPERIMENTS,
      gateRuns: [GATE_PASS],
      studies: [openStudy],
      robustnessJobs: [],
    });
    expect(
      summary.cells.find((c) => c.id === "final-decision")?.value,
    ).toBe("pending");
  });
});

describe("ResearchOverviewView", () => {
  it("renders gate-first strip above registry KPIs", () => {
    const html = renderToStaticMarkup(
      <ResearchOverviewView
        overview={OVERVIEW_WITH_EXPERIMENTS}
        gateRuns={[GATE_PASS]}
        studies={[STUDY_DECIDED]}
        robustnessJobs={[COST_JOB]}
      />,
    );

    expect(html).toContain('data-testid="executive-gate-strip"');
    expect(html).toContain('data-testid="research-overview-ready"');
    expect(html.indexOf("executive-gate-strip")).toBeLessThan(
      html.indexOf("Status-Verteilung"),
    );
    expect(html).toContain("Nicht verfügbar");
    expect(html).toContain('data-testid="executive-value-evidence-confidence"');
    expect(html).toContain('data-testid="executive-freeze-value"');
  });

  it("keeps executive strip on empty registry", () => {
    const html = renderToStaticMarkup(
      <ResearchOverviewView
        overview={EMPTY_OVERVIEW}
        gateRuns={[]}
        studies={[]}
        robustnessJobs={[]}
      />,
    );
    expect(html).toContain('data-testid="research-overview-empty"');
    expect(html).toContain('data-testid="executive-gate-strip"');
    expect(html).toContain("Nicht verfügbar");
  });
});
