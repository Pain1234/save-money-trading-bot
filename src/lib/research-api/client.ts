import { fetchPaperApi, PaperApiError, PaperApiTimeoutError } from "@/lib/paper-api/client";

export type ResearchMetricValue = string;

export interface ResearchExperimentSummary {
  experiment_id: string;
  run_id: string;
  status: string;
  strategy_version: string;
  strategy_id?: string | null;
  dataset_version: string;
  cost_model_version: string;
  benchmark_ref: string;
  created_at: string;
  symbols: string[];
  time_range_start: string | null;
  time_range_end: string | null;
  timeframe: string | null;
  git_commit: string | null;
  duration_seconds: number | null;
  net_pnl: string | null;
  max_drawdown: string | null;
  closed_trades: number | null;
  hit_rate: string | null;
  profit_factor: string | null;
  integrity_ok: boolean;
  integrity_error: string | null;
}

export interface ResearchOverview {
  experiment_count: number;
  completed_count: number;
  failed_count: number;
  invalidated_count: number;
  running_count: number | null;
  running_available: boolean;
  strategy_version_count: number;
  known_strategy_ids: string[];
  status_distribution: Record<string, number>;
  recent_experiments: ResearchExperimentSummary[];
  unavailable: Record<string, string>;
}

export interface ResearchExperimentList {
  items: ResearchExperimentSummary[];
  count: number;
}

export interface ResearchSeriesPoint {
  t: string;
  equity?: number;
  drawdown?: number;
}

export interface ResearchExperimentDetail {
  summary: ResearchExperimentSummary;
  metadata: {
    experiment_id: string;
    run_id: string;
    status: string;
    strategy_version: string;
    git_commit: string | null;
    dataset_version: string;
    seed: number | null;
    created_at: string;
    started_at: string | null;
    finalized_at: string | null;
    duration_seconds: number | null;
  };
  config: {
    symbols: string[];
    time_range_start: string | null;
    time_range_end: string | null;
    timeframe: string;
    starting_capital: string | null;
    parameters: Record<string, unknown>;
    fee_assumption: unknown;
    slippage_assumption: unknown;
    funding_assumption: unknown;
    costs: Record<string, unknown> | null;
    in_sample_config: string;
    out_of_sample_config: string;
    benchmark: string;
    hypothesis: string | null;
  };
  metrics: Record<string, ResearchMetricValue>;
  equity: ResearchSeriesPoint[];
  drawdown: ResearchSeriesPoint[];
  artifacts: Record<string, boolean>;
  integrity: { ok: boolean; error: string | null };
  job?: {
    status: string;
    started_at: string | null;
    finished_at: string | null;
    elapsed_seconds: number | null;
    error: string | null;
    error_detail: string | null;
    worker_alive?: boolean;
  } | null;
}

export function getResearchErrorMessage(error: unknown): string {
  if (error instanceof PaperApiTimeoutError) {
    return "Die Research API hat nicht innerhalb von 5 Sekunden geantwortet.";
  }
  if (error instanceof PaperApiError) {
    if (error.status === 404) {
      return "Experiment nicht gefunden.";
    }
    return `Research API nicht verfügbar (${error.status}).`;
  }
  if (error instanceof Error && error.message) {
    return `Research API Fehler: ${error.message}`;
  }
  return "Research API nicht verfügbar.";
}

export async function fetchResearchOverview(): Promise<ResearchOverview> {
  return fetchPaperApi<ResearchOverview>("/api/v1/research/overview", {
    revalidate: 10,
  });
}

export async function fetchResearchExperiments(params?: {
  status?: string;
  strategy_version?: string;
  q?: string;
}): Promise<ResearchExperimentList> {
  const search = new URLSearchParams();
  if (params?.status) search.set("status", params.status);
  if (params?.strategy_version) {
    search.set("strategy_version", params.strategy_version);
  }
  if (params?.q) search.set("q", params.q);
  const qs = search.toString();
  return fetchPaperApi<ResearchExperimentList>(
    `/api/v1/research/experiments${qs ? `?${qs}` : ""}`,
    { revalidate: 10 },
  );
}

export async function fetchResearchExperiment(
  experimentId: string,
): Promise<ResearchExperimentDetail> {
  return fetchPaperApi<ResearchExperimentDetail>(
    `/api/v1/research/experiments/${encodeURIComponent(experimentId)}`,
    { revalidate: 10 },
  );
}

export type RobustnessTestType =
  | "walk_forward"
  | "cost_stress"
  | "parameter_stability"
  | "bootstrap";

export interface RobustnessJobSummary {
  robustness_id: string;
  base_experiment_id: string;
  test_type: RobustnessTestType | string;
  status: string;
  created_at: string;
  updated_at: string;
  started_at: string | null;
  finished_at: string | null;
  error: string | null;
  error_detail: string | null;
  dataset_catalog_id: string | null;
  config: Record<string, unknown> | null;
}

export interface RobustnessJobList {
  items: RobustnessJobSummary[];
  count: number;
}

export interface RobustnessChildResult {
  child_id: string;
  label: string;
  experiment_id: string | null;
  run_id: string | null;
  status: string;
  net_pnl: string | null;
  max_drawdown: string | null;
  closed_trades: number | null;
  profit_factor: string | null;
  error: string | null;
}

export interface RobustnessManifest {
  schema_version: string;
  robustness_id: string;
  test_type: RobustnessTestType | string;
  base_experiment_id: string;
  base_run_id: string | null;
  dataset_catalog_id: string | null;
  config: Record<string, unknown>;
  created_at: string;
  children: RobustnessChildResult[];
  bootstrap_result: {
    n_simulations: number;
    block_length: number;
    seed: number;
    net_pnl_quantiles: Record<string, number>;
    max_drawdown_quantiles: Record<string, number>;
    mean_net_pnl: number;
    mean_max_drawdown: number;
  } | null;
  summary: {
    n_children: number;
    n_complete: number;
    n_failed: number;
  };
}

export interface RobustnessJobDetail {
  robustness_id: string;
  status: string;
  test_type: string;
  base_experiment_id: string;
  started_at: string | null;
  finished_at: string | null;
  elapsed_seconds: number | null;
  error: string | null;
  error_detail: string | null;
  job: RobustnessJobSummary;
  worker_alive: boolean;
  manifest: RobustnessManifest | null;
}

export async function fetchRobustnessJobs(params?: {
  base_experiment_id?: string;
}): Promise<RobustnessJobList> {
  const search = new URLSearchParams();
  if (params?.base_experiment_id) {
    search.set("base_experiment_id", params.base_experiment_id);
  }
  const qs = search.toString();
  return fetchPaperApi<RobustnessJobList>(
    `/api/v1/research/robustness${qs ? `?${qs}` : ""}`,
    { revalidate: 5 },
  );
}

export async function fetchRobustnessJob(
  robustnessId: string,
): Promise<RobustnessJobDetail> {
  return fetchPaperApi<RobustnessJobDetail>(
    `/api/v1/research/robustness/${encodeURIComponent(robustnessId)}`,
    { revalidate: 5 },
  );
}

// --- Gates (#248) — read-only types, reused by Validation Studies (#249) ---

export interface GateEvaluationResult {
  name: string;
  threshold: string;
  measured_value: string | null;
  passed: boolean;
  reason: string;
  /** Present on newer gate payloads (#248/#350). */
  outcome?: string;
  category?: string;
}

export interface GateRunRecord {
  schema_version: string;
  gate_run_id: string;
  policy_version: string;
  policy_content_hash: string;
  evaluated_at: string;
  run_code_commit: string;
  evaluation_code_commit: string;
  experiment_id: string;
  run_id: string;
  robustness_run_ids: string[];
  dataset_id: string;
  dataset_content_hash: string;
  artifact_checksums: Record<string, string>;
  measurements: Record<string, string>;
  gates: GateEvaluationResult[];
  overall_status: "pass" | "fail";
  promotion_action: "none";
  status: "active" | "invalidated";
  invalidation_reason: string | null;
}

export interface GateRunList {
  items: GateRunRecord[];
  count: number;
}

export async function fetchGateRuns(params?: {
  run_id?: string;
}): Promise<GateRunList> {
  const search = new URLSearchParams();
  if (params?.run_id) search.set("run_id", params.run_id);
  const qs = search.toString();
  return fetchPaperApi<GateRunList>(
    `/api/v1/research/gates${qs ? `?${qs}` : ""}`,
    { revalidate: 5 },
  );
}

// --- Validation Studies (#249 / P4.7d) --------------------------------
//
// A Study aggregates already-produced evidence (experiments + robustness
// (#247) + gates (#248)); it runs no second backtest engine and performs no
// live/paper promotion. The final decision is human-owned (see
// ``ValidationStudyDecision``).

export type ValidationStudyStatus = "open" | "decided";
export type ValidationStudyOutcome = "accept" | "reject" | "inconclusive";

export interface ValidationStudyDecision {
  outcome: ValidationStudyOutcome;
  rationale: string;
  decided_by: string;
  decided_at: string;
  evidence_snapshot_id: string;
}

export interface ValidationExperimentRef {
  experiment_id: string;
  run_id?: string;
  status: string;
  strategy_version?: string | null;
  strategy_id?: string | null;
  net_pnl?: string | null;
  max_drawdown?: string | null;
  closed_trades?: number | null;
  created_at?: string;
}

export interface ValidationRobustnessRef {
  robustness_id: string;
  status: string;
  test_type: string;
  base_experiment_id: string;
  manifest: RobustnessManifest | null;
}

export interface ValidationStudyProgress {
  experiments: { total: number; complete: number };
  robustness: {
    total: number;
    completed: number;
    failed: number;
    running: number;
  };
  gates: { total: number; pass: number; fail: number };
}

export interface ValidationStudyReproducibility {
  git_commit: string | null;
  evaluation_code_commit: string | null;
  dataset_id: string | null;
  dataset_content_hash: string | null;
  policy_version: string | null;
  policy_content_hash: string | null;
  source: "gate_run" | "evidence_snapshot" | "experiment_run";
  evidence_snapshot_id?: string;
}

export interface ValidationPinnedRunEvidence {
  experiment_id: string;
  run_id: string;
  checksums_digest: string;
  dataset_id: string;
  dataset_content_hash: string;
  git_commit: string;
}

/** Pinned Layer-5 scorecard (#291 / study schema 1.2). */
export interface ValidationPinnedScorecardEvidence {
  scorecard_id: string;
  content_hash: string;
}

export interface ValidationEvidenceSnapshot {
  snapshot_id: string;
  primary: ValidationPinnedRunEvidence;
  additional: ValidationPinnedRunEvidence[];
  robustness: { robustness_id: string; manifest_hash: string }[];
  gates: { gate_run_id: string; content_hash: string }[];
  scorecards?: ValidationPinnedScorecardEvidence[];
}

export interface ValidationStudySummary {
  schema_version: string;
  study_id: string;
  created_at: string;
  name: string;
  strategy_id: string | null;
  strategy_version: string | null;
  experiment_id: string;
  run_id: string | null;
  additional_experiment_ids: string[];
  additional_run_ids?: string[];
  robustness_ids: string[];
  gate_run_ids: string[];
  /** Optional Layer-5 pins (schema 1.2+). */
  scorecard_ids?: string[];
  evidence_snapshot?: ValidationEvidenceSnapshot;
  notes: string;
  status: ValidationStudyStatus;
  decision: ValidationStudyDecision | null;
}

export interface ValidationStudyDetail extends ValidationStudySummary {
  experiments: ValidationExperimentRef[];
  robustness: ValidationRobustnessRef[];
  robustness_by_type: Record<string, ValidationRobustnessRef[]>;
  gates: GateRunRecord[];
  progress: ValidationStudyProgress;
  reproducibility: ValidationStudyReproducibility;
  evidence_integrity?: {
    ok: boolean;
    error: string | null;
    snapshot_id: string;
  };
}

export interface ValidationStudyList {
  items: ValidationStudyDetail[];
  count: number;
}

export async function fetchValidationStudies(params?: {
  experiment_id?: string;
  status?: ValidationStudyStatus;
}): Promise<ValidationStudyList> {
  const search = new URLSearchParams();
  if (params?.experiment_id) search.set("experiment_id", params.experiment_id);
  if (params?.status) search.set("status", params.status);
  const qs = search.toString();
  return fetchPaperApi<ValidationStudyList>(
    `/api/v1/research/validation${qs ? `?${qs}` : ""}`,
    { revalidate: 5 },
  );
}

export async function fetchValidationStudy(
  studyId: string,
): Promise<ValidationStudyDetail> {
  return fetchPaperApi<ValidationStudyDetail>(
    `/api/v1/research/validation/${encodeURIComponent(studyId)}`,
    { revalidate: 5 }
  );
}

// --- Scorecards (#291 / P4.9 Layer 5) ---------------------------------
//
// Read-only global evidence profile. Status / label strings are backend
// literals (e.g. NOT_AVAILABLE, FAIL) — UI must not invent enums or scores.

export type ScorecardStatus = "active" | "invalidated";

export interface ScorecardLimitation {
  code: string;
  status: string;
  detail: string;
}

export interface ScorecardEvidenceIntegrity {
  ok: boolean;
  error: string | null;
}

/** Nested profile fields use loose typing; values are backend strings. */
export interface ScorecardGlobalProfile {
  auto_promotion?: boolean;
  decision_binding?: boolean;
  behaviour?: {
    behaviour_id?: string | null;
    main_strength?: string | null;
    main_weakness?: string | null;
    transition_risk?: Record<string, unknown> | null;
  };
  confidence?: {
    confidence_id?: string | null;
    overall_label?: string | null;
    source?: string | null;
  };
  gates?: {
    gate_run_id?: string | null;
    integrity_status?: string | null;
    overall_status?: string | null;
  };
  parameter_area?: Record<string, unknown> | null;
  quality?: {
    quality_id?: string | null;
    strongest_regime?: string | null;
    worst_regime?: string | null;
  };
  regime?: {
    classification_id?: string | null;
    classifier_version?: string | null;
  };
  robustness_manifest_hashes?: Record<string, string>;
  robustness_run_ids?: string[];
  [key: string]: unknown;
}

export interface ScorecardRecord {
  schema_version: string;
  scorecard_id: string;
  policy_version: string;
  policy_content_hash: string;
  evidence_content_hash: string;
  evaluated_at: string;
  run_code_commit: string;
  evaluation_code_commit: string;
  experiment_id: string;
  run_id: string;
  gate_run_id: string | null;
  robustness_run_ids: string[];
  dataset_id: string;
  dataset_content_hash: string;
  artifact_checksums: Record<string, string>;
  layer_refs: Record<string, unknown>;
  global_profile: ScorecardGlobalProfile;
  limitations: ScorecardLimitation[];
  decision_binding: boolean;
  auto_promotion: boolean;
  promotion_action: "none" | string;
  status: ScorecardStatus | string;
  invalidation_reason: string | null;
  evidence_integrity?: ScorecardEvidenceIntegrity;
}

export interface ScorecardList {
  items: ScorecardRecord[];
  count: number;
}

export async function fetchScorecards(params?: {
  run_id?: string;
}): Promise<ScorecardList> {
  const search = new URLSearchParams();
  if (params?.run_id) search.set("run_id", params.run_id);
  const qs = search.toString();
  return fetchPaperApi<ScorecardList>(
    `/api/v1/research/scorecards${qs ? `?${qs}` : ""}`,
    { revalidate: 5 },
  );
}

export async function fetchScorecard(
  scorecardId: string,
): Promise<ScorecardRecord> {
  return fetchPaperApi<ScorecardRecord>(
    `/api/v1/research/scorecards/${encodeURIComponent(scorecardId)}`,
    { revalidate: 5 },
  );
}

/** Metric cell from GET …/scorecards/{id}/detail (#350). */
export type ScorecardNaMetric<T> =
  | { status: "OK"; value: T }
  | { status: "NOT_AVAILABLE"; value: null; reason?: string }
  | { status: string; value: T | null; reason?: string };

export interface ScorecardDetailRegimeRow {
  cell_id: string;
  trend?: string | null;
  vol?: string | null;
  quality: ScorecardNaMetric<string | number> & {
    reason?: string;
    score_policy_content_hash?: string | null;
  };
  confidence: {
    status: string;
    value: string | null;
    scope?: string;
  };
  behaviour: {
    status: string;
    main_weakness?: string | null;
    main_strength?: string | null;
    labels?: string[];
  };
  trades: ScorecardNaMetric<number>;
  net_pnl: ScorecardNaMetric<string>;
  max_drawdown: ScorecardNaMetric<string>;
  costs: ScorecardNaMetric<{
    fees?: string;
    slippage_costs?: string;
    funding_costs?: string;
    [key: string]: unknown;
  }>;
  benchmark_delta: ScorecardNaMetric<string>;
  row_status?: string | null;
}

export interface ScorecardDetailCostStressOk {
  status: "OK";
  robustness_run_id: string;
  manifest_content_hash: string;
  artifact_path?: string;
  boundary: {
    base_net_pnl: string | null;
    combined_elevated_net_pnl: string | null;
    base_child_id?: string;
    combined_elevated_child_id?: string;
  };
}

export interface ScorecardDetailCostStressNa {
  status: "NOT_AVAILABLE";
  value?: null;
  reason?: string;
  robustness_run_id?: string;
}

export type ScorecardDetailCostStress =
  | ScorecardDetailCostStressOk
  | ScorecardDetailCostStressNa
  | { status: string; reason?: string; [key: string]: unknown };

export interface ScorecardDetailClassifierTransitionsOk {
  status: "OK";
  classification_id?: string;
  classifier_version?: string;
  transitions: Array<{
    transition_id?: string;
    from_period_id?: string;
    to_period_id?: string;
    from_trend?: string;
    to_trend?: string;
    from_vol?: string;
    to_vol?: string;
  }>;
  period_labels?: unknown[];
  calendar_gaps?: unknown[];
  day_events?: Array<{
    as_of?: string;
    period_id?: string;
    event?: string;
    transition_id?: string | null;
  }>;
}

export interface ScorecardDetailGateFailure {
  name?: string;
  outcome?: string;
  passed?: boolean;
  threshold?: string;
  measured_value?: string | null;
  reason?: string;
  category?: string;
  status?: string;
}

export interface ScorecardDetailRawArtifactRef {
  name: string;
  relative_path?: string;
  checksum_sha256?: string | null;
  present?: boolean;
  status?: string;
}

/** Read-only forensics payload (#350 / #302). */
export interface ScorecardDetail {
  scorecard_id: string;
  status: ScorecardStatus | string;
  decision_binding: boolean;
  auto_promotion: boolean;
  promotion_action: "none" | string;
  summary?: ScorecardRecord | Record<string, unknown>;
  regime_rows: ScorecardDetailRegimeRow[];
  transition_risk: ScorecardNaMetric<Record<string, unknown>> | {
    status: string;
    value: unknown;
  };
  classifier_transitions:
    | ScorecardDetailClassifierTransitionsOk
    | { status: "NOT_AVAILABLE"; value?: null; reason?: string }
    | { status: string; reason?: string; [key: string]: unknown };
  cost_stress: ScorecardDetailCostStress;
  evidence_inputs: Record<string, unknown>;
  gate_failures: ScorecardDetailGateFailure[];
  raw_artifact_refs: ScorecardDetailRawArtifactRef[];
  missing_data_semantics: { token: string; rule: string };
  evidence_integrity?: ScorecardEvidenceIntegrity;
}

export async function fetchScorecardDetail(
  scorecardId: string,
): Promise<ScorecardDetail> {
  return fetchPaperApi<ScorecardDetail>(
    `/api/v1/research/scorecards/${encodeURIComponent(scorecardId)}/detail`,
    { revalidate: 5 },
  );
}

export type ResearchCompareRunView = Omit<ResearchExperimentDetail, "job">;

export interface ResearchCompareResult {
  compatible: boolean;
  run_a: string;
  run_b: string;
  diffs: Record<string, [unknown, unknown]>;
  runs: {
    a: ResearchCompareRunView;
    b: ResearchCompareRunView;
  };
}

export async function fetchResearchCompare(
  runA: string,
  runB: string,
): Promise<ResearchCompareResult> {
  const params = new URLSearchParams({ run_a: runA, run_b: runB });
  return fetchPaperApi<ResearchCompareResult>(
    `/api/v1/research/experiments/compare?${params.toString()}`,
    { revalidate: 10 }
  );
}

export function displayValue(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === "") {
    return "Nicht verfügbar";
  }
  return String(value);
}
