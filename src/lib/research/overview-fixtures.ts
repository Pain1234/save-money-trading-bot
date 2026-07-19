import type {
  GateRunRecord,
  ResearchOverview,
  ScorecardDetail,
  ScorecardRecord,
  ValidationStudyDetail,
} from "@/lib/research-api/client";
import type { ScorecardBindState } from "@/lib/research/scorecard-binding";

export type OverviewFixture = {
  overview: ResearchOverview;
  gateRuns: GateRunRecord[];
  studies: ValidationStudyDetail[];
  robustnessJobs: [];
  scorecardBind: ScorecardBindState;
};

const HASH = "a".repeat(64);
const STUDY_ID =
  "study_public_fixture_abcdefghijklmnopqrstuvwxyz0123456789";
const EXP_ID = "exp_public_fixture_abcdefghijklmnopqrstuvwxyz012345";
const RUN_ID = "run_public_fixture_abcdefghijklmnopqrstuvwxyz012345";
const SC_ID = "sc_public_fixture_abcdefghijklmnopqrstuvwxyz01234567";

function baseOverview(): ResearchOverview {
  return {
    experiment_count: 1,
    completed_count: 1,
    failed_count: 0,
    invalidated_count: 0,
    running_count: 0,
    running_available: true,
    strategy_version_count: 1,
    known_strategy_ids: ["trend_v1"],
    status_distribution: { complete: 1 },
    recent_experiments: [
      {
        experiment_id: EXP_ID,
        run_id: RUN_ID,
        status: "complete",
        strategy_version: "1.0.0",
        strategy_id: "trend_v1",
        dataset_version: "ds_public",
        cost_model_version: "c1",
        benchmark_ref: "bh",
        created_at: "2026-01-02T00:00:00Z",
        symbols: ["BTC"],
        time_range_start: null,
        time_range_end: null,
        timeframe: "1h",
        git_commit: "abc",
        duration_seconds: 10,
        net_pnl: null,
        max_drawdown: null,
        closed_trades: 2,
        hit_rate: null,
        profit_factor: null,
        integrity_ok: true,
        integrity_error: null,
      },
    ],
    unavailable: {},
  };
}

function baseStudy(
  partial: Partial<ValidationStudyDetail> = {},
): ValidationStudyDetail {
  return {
    schema_version: "1.2",
    study_id: STUDY_ID,
    created_at: "2026-01-05T00:00:00Z",
    name: "Public Overview Fixture Study",
    strategy_id: "trend_v1",
    strategy_version: "1.0.0",
    experiment_id: EXP_ID,
    run_id: RUN_ID,
    additional_experiment_ids: [],
    robustness_ids: [],
    gate_run_ids: ["gate_public_a"],
    scorecard_ids: [],
    notes: "synthetic public-core",
    status: "decided",
    decision: {
      outcome: "reject",
      rationale: "fixture",
      decided_by: "reviewer",
      decided_at: "2026-01-05T01:00:00Z",
      evidence_snapshot_id: "snap_public",
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
    ...partial,
  };
}

function readyScorecard(): ScorecardRecord {
  return {
    schema_version: "1.0",
    scorecard_id: SC_ID,
    policy_version: "1.0",
    policy_content_hash: HASH,
    evidence_content_hash: HASH,
    evaluated_at: "2026-01-04T00:00:00Z",
    run_code_commit: "c".repeat(40),
    evaluation_code_commit: "d".repeat(40),
    experiment_id: EXP_ID,
    run_id: RUN_ID,
    gate_run_id: "gate_public_a",
    robustness_run_ids: [],
    dataset_id: "ds_public",
    dataset_content_hash: HASH,
    artifact_checksums: {},
    layer_refs: {},
    global_profile: {
      gates: {
        gate_run_id: "gate_public_a",
        integrity_status: "VALID",
        overall_status: "FAIL",
      },
      quality: {
        worst_regime: "trend_down|high_vol",
        strongest_regime: "trend_up|low_vol",
      },
      confidence: {
        overall_label: "LOW",
        source: "derived",
      },
      behaviour: {
        main_weakness: "weak_in_chop",
        main_strength: "trend_follow",
        transition_risk: {
          risk_label: "ELEVATED",
          transition_count: 2,
        },
      },
      parameter_area: {
        classification: "ISOLATED_PEAK",
        classification_reason: "fixture",
        parameter_area_id: "pa_public",
      },
    },
    limitations: [],
    decision_binding: false,
    auto_promotion: false,
    promotion_action: "none",
    status: "active",
    invalidation_reason: null,
    evidence_integrity: { ok: true, error: null },
  };
}

function readyDetail(): ScorecardDetail {
  return {
    scorecard_id: SC_ID,
    status: "active",
    decision_binding: false,
    auto_promotion: false,
    promotion_action: "none",
    regime_rows: [
      {
        cell_id: "trend_up|low_vol",
        quality: { status: "OK", value: "HIGH" },
        confidence: { status: "OK", value: "MEDIUM" },
        behaviour: {
          status: "OK",
          labels: ["trend"],
          main_weakness: null,
          main_strength: "trend_follow",
        },
        trades: { status: "OK", value: 3 },
        net_pnl: { status: "NOT_AVAILABLE", value: null },
        max_drawdown: { status: "NOT_AVAILABLE", value: null },
        costs: { status: "NOT_AVAILABLE", value: null },
        benchmark_delta: { status: "NOT_AVAILABLE", value: null },
      },
    ],
    cost_stress: { status: "NOT_AVAILABLE", reason: "fixture" },
    transition_risk: {
      status: "OK",
      value: { risk_label: "ELEVATED", transition_count: 2 },
    },
    classifier_transitions: { status: "OK", transitions: [] },
    gate_failures: [],
    evidence_inputs: {},
    raw_artifact_refs: [],
    missing_data_semantics: {
      token: "NOT_AVAILABLE",
      rule: "missing → NOT_AVAILABLE",
    },
  };
}

const GATE: GateRunRecord = {
  schema_version: "1.0",
  gate_run_id: "gate_public_a",
  policy_version: "1.0",
  policy_content_hash: HASH,
  evaluated_at: "2026-01-03T00:00:00Z",
  run_code_commit: "c".repeat(40),
  evaluation_code_commit: "d".repeat(40),
  experiment_id: EXP_ID,
  run_id: RUN_ID,
  robustness_run_ids: [],
  dataset_id: "ds_public",
  dataset_content_hash: HASH,
  artifact_checksums: {},
  measurements: {},
  gates: [],
  overall_status: "pass",
  promotion_action: "none",
  status: "active",
  invalidation_reason: null,
};

export function overviewFixtureReady(): OverviewFixture {
  const study = baseStudy({
    scorecard_ids: [SC_ID],
    evidence_snapshot: {
      snapshot_id: "snap_public",
      primary: {
        experiment_id: EXP_ID,
        run_id: RUN_ID,
        checksums_digest: HASH,
        dataset_id: "ds_public",
        dataset_content_hash: HASH,
        git_commit: "abc",
      },
      additional: [],
      robustness: [],
      gates: [{ gate_run_id: "gate_public_a", content_hash: HASH }],
      scorecards: [{ scorecard_id: SC_ID, content_hash: HASH }],
    },
  });
  return {
    overview: baseOverview(),
    gateRuns: [GATE],
    studies: [study],
    robustnessJobs: [],
    scorecardBind: {
      kind: "ready",
      scorecard: readyScorecard(),
      warnings: [],
      detail: readyDetail(),
      detailError: null,
    },
  };
}

export function overviewFixtureLegacy(): OverviewFixture {
  return {
    overview: baseOverview(),
    gateRuns: [GATE],
    studies: [baseStudy()],
    robustnessJobs: [],
    scorecardBind: {
      kind: "empty",
      reason:
        "Keine Scorecard an Study gepinnt (scorecard_ids / evidence_snapshot.scorecards) — Registry-Fallback unterdrückt",
    },
  };
}

export function overviewFixtureInvalidated(): OverviewFixture {
  const study = baseStudy({
    scorecard_ids: [SC_ID],
    evidence_snapshot: {
      snapshot_id: "snap_public",
      primary: {
        experiment_id: EXP_ID,
        run_id: RUN_ID,
        checksums_digest: HASH,
        dataset_id: "ds_public",
        dataset_content_hash: HASH,
        git_commit: "abc",
      },
      additional: [],
      robustness: [],
      gates: [{ gate_run_id: "gate_public_a", content_hash: HASH }],
      scorecards: [{ scorecard_id: SC_ID, content_hash: HASH }],
    },
  });
  return {
    overview: baseOverview(),
    gateRuns: [GATE],
    studies: [study],
    robustnessJobs: [],
    scorecardBind: {
      kind: "error",
      message: "status=invalidated: policy superseded — Scorecard untrusted",
    },
  };
}

export type OverviewFixtureScenario = "ready" | "legacy" | "invalidated";

export function overviewFixture(
  scenario: OverviewFixtureScenario,
): OverviewFixture {
  if (scenario === "ready") return overviewFixtureReady();
  if (scenario === "invalidated") return overviewFixtureInvalidated();
  return overviewFixtureLegacy();
}
