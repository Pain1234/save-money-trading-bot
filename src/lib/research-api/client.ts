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
  source: "gate_run" | "experiment_run";
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
  robustness_ids: string[];
  gate_run_ids: string[];
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
    { revalidate: 5 },
  );
}

export function displayValue(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === "") {
    return "Nicht verfügbar";
  }
  return String(value);
}
