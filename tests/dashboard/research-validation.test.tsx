import React from "react";
import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";

import { ValidationStudiesTable } from "../../src/components/research/ValidationStudiesTable";
import { ValidationStudyCreateForm } from "../../src/components/research/ValidationStudyCreateForm";
import { ValidationStudyDecisionPanel } from "../../src/components/research/ValidationStudyDecisionPanel";
import { ValidationStudyDetailView } from "../../src/components/research/ValidationStudyDetailView";
import type {
  GateRunRecord,
  RobustnessJobSummary,
  ValidationStudyDetail,
} from "../../src/lib/research-api/client";

// Synthetic/public fixtures only — no private Strategy V1 numbers (#249 / #181).
const SYNTHETIC_GATE: GateRunRecord = {
  schema_version: "1.0",
  gate_run_id: "gate_synthetic0000000000000000000000000000000000000000000000000000",
  policy_version: "1.0",
  policy_content_hash: "b".repeat(64),
  evaluated_at: "2024-01-01T00:10:00.000000Z",
  run_code_commit: "c".repeat(40),
  evaluation_code_commit: "d".repeat(40),
  experiment_id: "exp_synthetic_base",
  run_id: "run_synthetic_base",
  robustness_run_ids: ["rob_synthetic0000000000000000000000000000000000000000000000000000"],
  dataset_id: "synthetic-btc-fixture",
  dataset_content_hash: "e".repeat(64),
  artifact_checksums: {},
  measurements: { net_pnl: "123.45" },
  gates: [
    {
      name: "net_pnl_non_negative",
      threshold: "0",
      measured_value: "123.45",
      passed: true,
      reason: "pass",
    },
  ],
  overall_status: "pass",
  promotion_action: "none",
  status: "active",
  invalidation_reason: null,
};

const SYNTHETIC_STUDY: ValidationStudyDetail = {
  schema_version: "1.0",
  study_id: "study_synthetic0000000000000000000000000000000000000000000000000",
  created_at: "2024-01-01T00:00:00.000000Z",
  name: "Synthetic BTC trend study",
  strategy_id: "trend_v1",
  strategy_version: "1.0.0",
  experiment_id: "exp_synthetic_base",
  run_id: "run_synthetic_base",
  additional_experiment_ids: [],
  robustness_ids: ["rob_synthetic0000000000000000000000000000000000000000000000000000"],
  gate_run_ids: [SYNTHETIC_GATE.gate_run_id],
  notes: "fixture aggregate",
  status: "open",
  decision: null,
  experiments: [
    {
      experiment_id: "exp_synthetic_base",
      run_id: "run_synthetic_base",
      status: "complete",
      strategy_version: "1.0.0",
      strategy_id: "trend_v1",
      net_pnl: "123.45",
      max_drawdown: "-45.00",
      closed_trades: 3,
      created_at: "2024-01-01T00:00:00.000000Z",
    },
  ],
  robustness: [
    {
      robustness_id: "rob_synthetic0000000000000000000000000000000000000000000000000000",
      status: "completed",
      test_type: "bootstrap",
      base_experiment_id: "exp_synthetic_base",
      manifest: {
        schema_version: "1.0",
        robustness_id: "rob_synthetic0000000000000000000000000000000000000000000000000000",
        test_type: "bootstrap",
        base_experiment_id: "exp_synthetic_base",
        base_run_id: "run_synthetic_base",
        dataset_catalog_id: null,
        config: {},
        created_at: "2024-01-01T00:05:00.000000Z",
        children: [],
        bootstrap_result: null,
        summary: { n_children: 1, n_complete: 1, n_failed: 0 },
      },
    },
  ],
  robustness_by_type: {
    bootstrap: [
      {
        robustness_id: "rob_synthetic0000000000000000000000000000000000000000000000000000",
        status: "completed",
        test_type: "bootstrap",
        base_experiment_id: "exp_synthetic_base",
        manifest: {
          schema_version: "1.0",
          robustness_id: "rob_synthetic0000000000000000000000000000000000000000000000000000",
          test_type: "bootstrap",
          base_experiment_id: "exp_synthetic_base",
          base_run_id: "run_synthetic_base",
          dataset_catalog_id: null,
          config: {},
          created_at: "2024-01-01T00:05:00.000000Z",
          children: [],
          bootstrap_result: null,
          summary: { n_children: 1, n_complete: 1, n_failed: 0 },
        },
      },
    ],
  },
  gates: [SYNTHETIC_GATE],
  progress: {
    experiments: { total: 1, complete: 1 },
    robustness: { total: 1, completed: 1, failed: 0, running: 0 },
    gates: { total: 1, pass: 1, fail: 0 },
  },
  reproducibility: {
    git_commit: "c".repeat(40),
    evaluation_code_commit: "d".repeat(40),
    dataset_id: "synthetic-btc-fixture",
    dataset_content_hash: "e".repeat(64),
    policy_version: "1.0",
    policy_content_hash: "b".repeat(64),
    source: "gate_run",
  },
};

const SYNTHETIC_ROBUSTNESS_JOB: RobustnessJobSummary = {
  robustness_id: "rob_synthetic0000000000000000000000000000000000000000000000000000",
  base_experiment_id: "exp_synthetic_base",
  test_type: "bootstrap",
  status: "completed",
  created_at: "2024-01-01T00:00:00.000000Z",
  updated_at: "2024-01-01T00:05:00.000000Z",
  started_at: "2024-01-01T00:00:05.000000Z",
  finished_at: "2024-01-01T00:05:00.000000Z",
  error: null,
  error_detail: null,
  dataset_catalog_id: null,
  config: {},
};

describe("ValidationStudiesTable (static render, synthetic fixtures)", () => {
  it("renders empty state without any studies", () => {
    const html = renderToStaticMarkup(<ValidationStudiesTable items={[]} />);
    expect(html).toContain("validation-list-empty");
  });

  it("renders a study row linking to its detail page with progress + decision", () => {
    const html = renderToStaticMarkup(
      <ValidationStudiesTable items={[SYNTHETIC_STUDY]} />,
    );
    expect(html).toContain("validation-list-ready");
    expect(html).toContain(
      `href="/dashboard/research/validation/${SYNTHETIC_STUDY.study_id}"`,
    );
    expect(html).toContain("Synthetic BTC trend study");
    expect(html).toContain("Offen");
  });
});

describe("ValidationStudyDetailView (static render, synthetic fixtures)", () => {
  it("renders all required study fields", () => {
    const html = renderToStaticMarkup(
      <ValidationStudyDetailView study={SYNTHETIC_STUDY} />,
    );
    expect(html).toContain("validation-detail-ready");
    // Strategy/version, status, progress, policy version.
    expect(html).toContain("validation-strategy");
    expect(html).toContain("trend_v1");
    expect(html).toContain("validation-status");
    expect(html).toContain("validation-progress");
    // Experiments.
    expect(html).toContain("validation-experiment-exp_synthetic_base");
    // Robustness grouped by test type (walk-forward / cost stress /
    // parameter stability / bootstrap categories from #247).
    expect(html).toContain("validation-robustness-bootstrap");
    expect(html).toContain("Bootstrap / Monte Carlo");
    // Gate results.
    expect(html).toContain(`validation-gate-${SYNTHETIC_GATE.gate_run_id}`);
    // Final decision (pending state here).
    expect(html).toContain("validation-decision-pending");
    // Reproducibility fields.
    expect(html).toContain("validation-reproducibility");
    expect(html).toContain(SYNTHETIC_GATE.dataset_content_hash);
  });

  it("renders a recorded decision instead of the pending state", () => {
    const decided: ValidationStudyDetail = {
      ...SYNTHETIC_STUDY,
      status: "decided",
      decision: {
        outcome: "accept",
        rationale: "synthetic gates passed under fixture policy",
        decided_by: "reviewer",
        decided_at: "2024-01-02T00:00:00.000000Z",
      },
    };
    const html = renderToStaticMarkup(<ValidationStudyDetailView study={decided} />);
    expect(html).not.toContain("validation-decision-pending");
    expect(html).toContain("Akzeptiert");
    expect(html).toContain("synthetic gates passed under fixture policy");
  });

  it("never renders a promotion-trigger affordance for the decision", () => {
    // Leakage/safety-negative: no live/paper promotion UI anywhere on this
    // surface (#249 non-scope), regardless of decision outcome.
    const decided: ValidationStudyDetail = {
      ...SYNTHETIC_STUDY,
      status: "decided",
      decision: {
        outcome: "accept",
        rationale: "synthetic",
        decided_by: "reviewer",
        decided_at: "2024-01-02T00:00:00.000000Z",
      },
    };
    const html = renderToStaticMarkup(<ValidationStudyDetailView study={decided} />);
    expect(html.toLowerCase()).not.toContain("promote");
    expect(html.toLowerCase()).not.toContain("go live");
    expect(html.toLowerCase()).not.toContain("live trading");
  });
});

describe("ValidationStudyCreateForm (static render, synthetic fixtures)", () => {
  it("renders empty state without a completed base experiment", () => {
    const html = renderToStaticMarkup(
      <ValidationStudyCreateForm experiments={[]} robustnessJobs={[]} gateRuns={[]} />,
    );
    expect(html).toContain("validation-create-empty");
  });

  it("renders the form with base-experiment, robustness and gate selectors", () => {
    const html = renderToStaticMarkup(
      <ValidationStudyCreateForm
        experiments={[
          {
            experiment_id: "exp_synthetic_base",
            strategy_version: "1.0.0",
            created_at: "2024-01-01T00:00:00.000000Z",
          },
        ]}
        robustnessJobs={[SYNTHETIC_ROBUSTNESS_JOB]}
        gateRuns={[SYNTHETIC_GATE]}
      />,
    );
    expect(html).toContain("validation-create-form");
    expect(html).toContain("validation-base-experiment-select");
    expect(html).toContain(
      `validation-robustness-option-${SYNTHETIC_ROBUSTNESS_JOB.robustness_id}`,
    );
    expect(html).toContain(`validation-gate-option-${SYNTHETIC_GATE.gate_run_id}`);
    expect(html).toContain("validation-submit");
  });
});

describe("ValidationStudyDecisionPanel (static render, synthetic fixtures)", () => {
  it("renders the decision form while the study is still open", () => {
    const html = renderToStaticMarkup(
      <ValidationStudyDecisionPanel
        studyId={SYNTHETIC_STUDY.study_id}
        status="open"
        decision={null}
      />,
    );
    expect(html).toContain("validation-decision-form");
    expect(html).toContain("validation-decision-outcome-select");
    expect(html).toContain("validation-decision-submit");
  });

  it("renders nothing once a decision has already been recorded", () => {
    const html = renderToStaticMarkup(
      <ValidationStudyDecisionPanel
        studyId={SYNTHETIC_STUDY.study_id}
        status="decided"
        decision={{
          outcome: "reject",
          rationale: "synthetic gate failed",
          decided_by: "reviewer",
          decided_at: "2024-01-02T00:00:00.000000Z",
        }}
      />,
    );
    expect(html).toBe("");
  });
});
