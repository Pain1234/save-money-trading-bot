import React from "react";
import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";

import { ResearchOverviewView } from "../../src/components/research/ResearchOverviewView";
import {
  buildExecutiveSummary,
  selectEvidenceStudy,
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

function experiment(partial: {
  experiment_id: string;
  run_id: string;
  strategy_id?: string;
  strategy_version?: string;
  integrity_ok: boolean;
  integrity_error?: string | null;
  created_at?: string;
}): ResearchOverview["recent_experiments"][number] {
  return {
    experiment_id: partial.experiment_id,
    run_id: partial.run_id,
    status: "complete",
    strategy_version: partial.strategy_version ?? "1.0.0",
    strategy_id: partial.strategy_id ?? "trend_v1",
    dataset_version: "ds1",
    cost_model_version: "c1",
    benchmark_ref: "bh",
    created_at: partial.created_at ?? "2024-01-02T00:00:00Z",
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
    integrity_ok: partial.integrity_ok,
    integrity_error: partial.integrity_error ?? null,
  };
}

const OVERVIEW_MIXED: ResearchOverview = {
  ...EMPTY_OVERVIEW,
  experiment_count: 2,
  completed_count: 2,
  strategy_version_count: 2,
  known_strategy_ids: ["trend_v1", "mean_reversion_x"],
  status_distribution: { complete: 2 },
  recent_experiments: [
    experiment({
      experiment_id: "exp_a",
      run_id: "run_a",
      strategy_id: "trend_v1",
      integrity_ok: true,
      created_at: "2024-01-02T00:00:00Z",
    }),
    experiment({
      experiment_id: "exp_b",
      run_id: "run_b",
      strategy_id: "mean_reversion_x",
      strategy_version: "9.9.9",
      integrity_ok: false,
      integrity_error: "checksum mismatch",
      created_at: "2024-01-01T00:00:00Z",
    }),
  ],
};

const GATE_PASS_A: GateRunRecord = {
  schema_version: "1.0",
  gate_run_id: "gate_pass_a",
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

const GATE_FAIL_OTHER: GateRunRecord = {
  ...GATE_PASS_A,
  gate_run_id: "gate_fail_other",
  experiment_id: "exp_other",
  run_id: "run_other",
  overall_status: "fail",
  evaluated_at: "2024-01-04T00:00:00Z",
};

function study(partial: Partial<ValidationStudyDetail> & {
  study_id: string;
  name: string;
  experiment_id: string;
  status: "open" | "decided";
}): ValidationStudyDetail {
  return {
    schema_version: "1.0",
    created_at: "2024-01-05T00:00:00Z",
    strategy_id: "trend_v1",
    strategy_version: "1.0.0",
    run_id: "run_a",
    additional_experiment_ids: [],
    robustness_ids: [],
    gate_run_ids: ["gate_pass_a"],
    notes: "",
    decision: null,
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
    ...partial,
  };
}

const STUDY_DECIDED_A = study({
  study_id: "study_a",
  name: "Trend study A",
  experiment_id: "exp_a",
  run_id: "run_a",
  status: "decided",
  created_at: "2024-01-05T00:00:00Z",
  robustness_ids: ["rob_cost_a"],
  decision: {
    outcome: "accept",
    rationale: "fixture",
    decided_by: "reviewer",
    decided_at: "2024-01-05T01:00:00Z",
    evidence_snapshot_id: "snap_1",
  },
});

const STUDY_OPEN_OTHER = study({
  study_id: "study_other",
  name: "Other open study",
  experiment_id: "exp_b",
  run_id: "run_b",
  strategy_id: "mean_reversion_x",
  strategy_version: "9.9.9",
  gate_run_ids: ["gate_fail_other"],
  robustness_ids: ["rob_cost_other"],
  status: "open",
  created_at: "2024-01-06T00:00:00Z",
  decision: null,
});

const COST_JOB_A: RobustnessJobSummary = {
  robustness_id: "rob_cost_a",
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

const COST_JOB_OTHER: RobustnessJobSummary = {
  ...COST_JOB_A,
  robustness_id: "rob_cost_other",
  base_experiment_id: "exp_other",
  status: "failed",
};

describe("selectEvidenceStudy", () => {
  it("prefers newest decided study over a newer open study", () => {
    const focus = selectEvidenceStudy([STUDY_OPEN_OTHER, STUDY_DECIDED_A]);
    expect(focus?.study_id).toBe("study_a");
  });
});

describe("buildExecutiveSummary evidence identity", () => {
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
    expect(byId["worst-transition"]?.value).toBe(UNAVAILABLE);
    expect(byId["main-weakness"]?.value).toBe(UNAVAILABLE);
    expect(byId["main-strength"]?.value).toBe(UNAVAILABLE);
    expect(byId["cost-stress"]?.value).toBe(UNAVAILABLE);
    expect(byId["parameter-area"]?.value).toBe(UNAVAILABLE);
    expect(byId.integrity?.value).toBe(UNAVAILABLE);
    expect(byId["critical-gates"]?.value).toBe(UNAVAILABLE);
    expect(byId["final-decision"]?.value).toBe(UNAVAILABLE);
    expect(summary.evidence).toBeNull();
    expect(summary.strategyId).toBeNull();
    expect(summary.freezeLabel).toBe(UNAVAILABLE);
    expect(summary.pin.status).toBe("NO_STUDY");
    expect(JSON.stringify(summary)).not.toMatch(/123\.45|0\.87|demo.?pnl/i);
  });

  it("binds gates, decision, strategy to one decided study (multi-strategy)", () => {
    const summary = buildExecutiveSummary({
      overview: OVERVIEW_MIXED,
      gateRuns: [GATE_PASS_A, GATE_FAIL_OTHER],
      studies: [STUDY_DECIDED_A, STUDY_OPEN_OTHER],
      robustnessJobs: [COST_JOB_A, COST_JOB_OTHER],
    });

    const byId = Object.fromEntries(summary.cells.map((c) => [c.id, c]));

    expect(summary.evidence?.studyId).toBe("study_a");
    expect(summary.strategyId).toBe("trend_v1");
    expect(summary.strategyVersion).toBe("1.0.0");
    expect(summary.strategyId).not.toBe("mean_reversion_x");

    expect(byId["final-decision"]?.value).toBe("ACCEPT");
    expect(byId["final-decision"]?.detail).toContain("study_a");

    // Unrelated FAIL gate must not leak into the focus study strip.
    expect(byId["critical-gates"]?.value).toBe("PASS");
    expect(byId["critical-gates"]?.detail).toContain("study_a");
    expect(byId["critical-gates"]?.detail).not.toMatch(/fail/i);

    expect(byId["cost-stress"]?.detail).toMatch(/Jobs 1 complete \/ 0 failed/);
    expect(byId["cost-stress"]?.detail).toContain("study_a");
  });

  it("scopes integrity to the pinned experiment only", () => {
    const summary = buildExecutiveSummary({
      overview: OVERVIEW_MIXED,
      gateRuns: [GATE_PASS_A],
      studies: [STUDY_DECIDED_A],
      robustnessJobs: [],
    });

    const integrity = summary.cells.find((c) => c.id === "integrity");
    // exp_b is INVALID in recent, but focus pins exp_a → VALID for pinned only.
    expect(integrity?.value).toBe("VALID");
    expect(integrity?.detail).toMatch(/run_a/);
    expect(integrity?.detail).not.toMatch(/2 recent|exp_b/i);
  });

  it("does not claim VALID when pinned experiment is missing from overview", () => {
    const overviewMissingPin: ResearchOverview = {
      ...OVERVIEW_MIXED,
      recent_experiments: [
        experiment({
          experiment_id: "exp_b",
          run_id: "run_b",
          integrity_ok: true,
        }),
      ],
    };
    const summary = buildExecutiveSummary({
      overview: overviewMissingPin,
      gateRuns: [GATE_PASS_A],
      studies: [STUDY_DECIDED_A],
      robustnessJobs: [],
    });
    expect(summary.cells.find((c) => c.id === "integrity")?.value).toBe(
      "NOT_VERIFIABLE",
    );
  });

  it("ignores unpinned gates/jobs that share experiment identity", () => {
    const unpinnedFailSameExp: GateRunRecord = {
      ...GATE_PASS_A,
      gate_run_id: "gate_fail_same_exp_unpinned",
      overall_status: "fail",
      evaluated_at: "2024-01-09T00:00:00Z",
      experiment_id: "exp_a",
      run_id: "run_a",
    };
    const unpinnedCostSameExp: RobustnessJobSummary = {
      ...COST_JOB_A,
      robustness_id: "rob_cost_unpinned",
      base_experiment_id: "exp_a",
      status: "failed",
    };
    const summary = buildExecutiveSummary({
      overview: OVERVIEW_MIXED,
      gateRuns: [GATE_PASS_A, unpinnedFailSameExp],
      studies: [STUDY_DECIDED_A],
      robustnessJobs: [COST_JOB_A, unpinnedCostSameExp],
    });
    const byId = Object.fromEntries(summary.cells.map((c) => [c.id, c]));
    expect(byId["critical-gates"]?.value).toBe("PASS");
    expect(byId["critical-gates"]?.detail).not.toMatch(/fail/i);
    expect(byId["cost-stress"]?.detail).toMatch(/Jobs 1 complete \/ 0 failed/);
  });

  it("does not use a different run of the same experiment for integrity", () => {
    const overviewWrongRun: ResearchOverview = {
      ...OVERVIEW_MIXED,
      recent_experiments: [
        experiment({
          experiment_id: "exp_a",
          run_id: "run_a_later",
          integrity_ok: true,
        }),
      ],
    };
    const summary = buildExecutiveSummary({
      overview: overviewWrongRun,
      gateRuns: [GATE_PASS_A],
      studies: [STUDY_DECIDED_A],
      robustnessJobs: [],
    });
    expect(summary.cells.find((c) => c.id === "integrity")?.value).toBe(
      "NOT_VERIFIABLE",
    );
  });

  it("keeps multi-study open focus consistent without foreign strategy", () => {
    const summary = buildExecutiveSummary({
      overview: OVERVIEW_MIXED,
      gateRuns: [GATE_PASS_A, GATE_FAIL_OTHER],
      studies: [STUDY_OPEN_OTHER],
      robustnessJobs: [COST_JOB_OTHER],
    });

    expect(summary.evidence?.studyId).toBe("study_other");
    expect(summary.strategyId).toBe("mean_reversion_x");
    expect(summary.cells.find((c) => c.id === "final-decision")?.value).toBe(
      "pending",
    );
    expect(summary.cells.find((c) => c.id === "critical-gates")?.value).toBe(
      "FAIL",
    );
    expect(summary.cells.find((c) => c.id === "integrity")?.value).toBe(
      "INVALID",
    );
  });
});

describe("ResearchOverviewView", () => {
  it("renders gate-first strip with evidence anchor above registry KPIs", () => {
    const html = renderToStaticMarkup(
      <ResearchOverviewView
        overview={OVERVIEW_MIXED}
        gateRuns={[GATE_PASS_A]}
        studies={[STUDY_DECIDED_A]}
        robustnessJobs={[COST_JOB_A]}
      />,
    );

    expect(html).toContain('data-testid="executive-gate-strip"');
    expect(html).toContain('data-testid="executive-evidence-anchor"');
    expect(html).toContain("study_a");
    expect(html).toContain('data-testid="research-overview-ready"');
    expect(html.indexOf("executive-gate-strip")).toBeLessThan(
      html.indexOf("Status-Verteilung"),
    );
    expect(html).toContain("Nicht verfügbar");
    expect(html).toContain('data-testid="executive-strategy-id"');
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
    expect(html).toContain("kein Validation Study");
  });
});
