export const API_TIMEOUT_MS = 5000;

export const REVALIDATE = {
  /** Status and summary: 1–2s (P2.5 cache policy) */
  STATUS: 2,
  SUMMARY: 2,
  /** Wallet and positions: 3–5s */
  MONITORING: 5,
  /** Orders, fills, equity history: 5–30s */
  TABLES: 5,
  HISTORY: 30,
} as const;

export type DisplayStatus = "READY" | "DEGRADED" | "STOPPED";

export interface Paginated<T> {
  items: T[];
  next_cursor: string | null;
  limit: number;
}

export interface StatusResponse {
  display_status: DisplayStatus;
  heartbeat_age_seconds: number | null;
  stale_heartbeat_threshold_seconds: number;
  hyperliquid_network: string;
  runtime: {
    status: string;
    heartbeat_at: string;
    last_error: string | null;
    kill_switch: boolean;
    paused: boolean;
  } | null;
  readiness: {
    runtime_readiness: boolean;
    reasons: string[];
  };
}

export interface DashboardSummaryResponse {
  display_status: DisplayStatus;
  status: StatusResponse;
  readiness: StatusResponse["readiness"];
  heartbeat_at: string | null;
  wallet: Pick<WalletResponse, "cash" | "total_realized_pnl" | "updated_at"> | null;
  open_position_count: number;
  position_summary: Array<{
    symbol: string;
    status: string;
    quantity: string;
    unrealized_pnl: string;
  }>;
  warnings: string[];
  hyperliquid_network: string;
}

export interface WalletResponse {
  cash: string;
  total_realized_pnl: string;
  total_fees: string;
  updated_at: string;
}

export interface PositionItem {
  position_id: string;
  symbol: string;
  status: string;
  quantity: string;
  average_entry_price: string;
  current_stop: string;
  unrealized_pnl: string;
  opened_at: string;
}

export interface FillItem {
  fill_id: string;
  fill_kind: string;
  symbol: string;
  quantity: string;
  fill_price: string;
  fill_time: string;
}

export interface OrderItem {
  paper_order_id: string;
  symbol: string;
  status: string;
  requested_quantity: string;
  expected_fill_time: string;
}

export interface StopItem {
  stop_event_id: string;
  position_id: string;
  previous_stop: string;
  new_stop: string;
  evaluation_time: string;
  reason: string;
}

export interface SchedulerRunItem {
  run_id: string;
  job_name: string;
  scheduled_for: string;
  status: string;
  error: string | null;
}

export interface EventItem {
  event_id: string;
  event_type: string;
  aggregate_type: string;
  created_at: string;
  payload_json: Record<string, unknown>;
}

export interface EquityPoint {
  evaluation_time: string | null;
  equity: string | null;
  cash: string | null;
}

export class PaperApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "PaperApiError";
  }
}

export class PaperApiTimeoutError extends Error {
  constructor() {
    super("Monitoring API request timed out");
    this.name = "PaperApiTimeoutError";
  }
}

export function getMonitoringErrorMessage(error: unknown): string {
  if (error instanceof PaperApiTimeoutError) {
    return "The monitoring API did not respond within 5 seconds. Refresh the page to retry.";
  }
  if (error instanceof PaperApiError) {
    return `Monitoring API unavailable (${error.status}).`;
  }
  return "Monitoring API unavailable.";
}

function apiBaseUrl(): string {
  const url = process.env.PRIVATE_PAPER_API_URL;
  if (!url) {
    throw new Error("PRIVATE_PAPER_API_URL is required for server-side API access");
  }
  return url.replace(/\/$/, "");
}

export async function fetchPaperApi<T>(
  path: string,
  options: { revalidate?: number; noStore?: boolean },
): Promise<T> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), API_TIMEOUT_MS);

  try {
    const response = await fetch(`${apiBaseUrl()}${path}`, {
      ...(options.noStore
        ? { cache: "no-store" as const }
        : { next: { revalidate: options.revalidate ?? REVALIDATE.MONITORING } }),
      headers: { Accept: "application/json" },
      signal: controller.signal,
    });
    if (!response.ok) {
      throw new PaperApiError(`API request failed: ${path}`, response.status);
    }
    return (await response.json()) as T;
  } catch (error) {
    if (error instanceof Error && error.name === "AbortError") {
      throw new PaperApiTimeoutError();
    }
    throw error;
  } finally {
    clearTimeout(timeoutId);
  }
}

export async function fetchStatus(): Promise<StatusResponse> {
  return fetchPaperApi<StatusResponse>("/api/v1/status", {
    revalidate: REVALIDATE.STATUS,
  });
}

export async function fetchDashboardSummary(): Promise<DashboardSummaryResponse> {
  return fetchPaperApi<DashboardSummaryResponse>("/api/v1/dashboard-summary", {
    revalidate: REVALIDATE.SUMMARY,
  });
}

export async function fetchWallet(): Promise<WalletResponse> {
  return fetchPaperApi<WalletResponse>("/api/v1/wallet", {
    revalidate: REVALIDATE.MONITORING,
  });
}

export async function fetchPositions(): Promise<Paginated<PositionItem>> {
  return fetchPaperApi<Paginated<PositionItem>>("/api/v1/positions?limit=50", {
    revalidate: REVALIDATE.MONITORING,
  });
}

export async function fetchOrders(): Promise<Paginated<OrderItem>> {
  return fetchPaperApi<Paginated<OrderItem>>("/api/v1/orders?limit=50", {
    revalidate: REVALIDATE.TABLES,
  });
}

export async function fetchFills(): Promise<Paginated<FillItem>> {
  return fetchPaperApi<Paginated<FillItem>>("/api/v1/fills?limit=50", {
    revalidate: REVALIDATE.TABLES,
  });
}

export async function fetchStops(): Promise<Paginated<StopItem>> {
  return fetchPaperApi<Paginated<StopItem>>("/api/v1/stops?limit=50", {
    revalidate: REVALIDATE.MONITORING,
  });
}

export async function fetchSchedulerRuns(): Promise<Paginated<SchedulerRunItem>> {
  return fetchPaperApi<Paginated<SchedulerRunItem>>("/api/v1/scheduler-runs?limit=50", {
    revalidate: REVALIDATE.HISTORY,
  });
}

export async function fetchEvents(): Promise<Paginated<EventItem>> {
  return fetchPaperApi<Paginated<EventItem>>("/api/v1/events?limit=50", {
    revalidate: REVALIDATE.HISTORY,
  });
}

export async function fetchEquity(): Promise<Paginated<EquityPoint>> {
  return fetchPaperApi<Paginated<EquityPoint>>("/api/v1/equity?limit=100", {
    revalidate: REVALIDATE.HISTORY,
  });
}

export async function fetchMarketData(): Promise<Record<string, unknown>> {
  return fetchPaperApi<Record<string, unknown>>("/api/v1/market-data", {
    revalidate: REVALIDATE.STATUS,
  });
}
