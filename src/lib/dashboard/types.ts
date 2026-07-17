import type { KpiMetric } from "@/types";

export type SectionLoadState =
  | { kind: "ok" }
  | { kind: "empty"; message: string }
  | { kind: "error"; message: string };

export interface EquityChartPointVm {
  /** Display label (time); may be empty for intermediate ticks */
  label: string;
  /** Display-only number for Recharts — never used for accounting */
  equity: number;
  /** Original decimal string from API */
  equityRaw: string;
  evaluationTime: string | null;
}

export interface PositionRowVm {
  id: string;
  symbol: string;
  coin: string;
  coinColor: string;
  /** V1 contract is LONG-only (PaperSide.LONG); never inferred from quantity */
  side: "long";
  sizeDisplay: string;
  entryPriceDisplay: string;
  markPriceDisplay: string;
  pnlDisplay: string;
  pnlNumericHint: number | null;
  riskDisplay: string;
  stopLossDisplay: string;
  takeProfitDisplay: string;
}

export interface FillRowVm {
  id: string;
  symbol: string;
  coin: string;
  coinColor: string;
  fillKind: string;
  quantityDisplay: string;
  priceDisplay: string;
  timeDisplay: string;
}

export interface StatusCardVm {
  id: string;
  label: string;
  value: string;
  detail: string;
  tone: "ok" | "warn" | "danger" | "neutral";
}

export interface QuickStatVm {
  label: string;
  value: string;
}

export type DashboardKpiVm = KpiMetric;

export interface SummaryViewModel {
  kpis: DashboardKpiVm[];
  quickStats: QuickStatVm[];
  staleHeartbeat: boolean;
  warnings: string[];
}
