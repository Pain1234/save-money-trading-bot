import { fetchPaperApi, PaperApiError, PaperApiTimeoutError } from "@/lib/paper-api/client";

export type ResearchMetricValue = string;

export interface ResearchExperimentSummary {
  experiment_id: string;
  run_id: string;
  status: string;
  strategy_version: string;
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

export function displayValue(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === "") {
    return "Nicht verfügbar";
  }
  return String(value);
}
