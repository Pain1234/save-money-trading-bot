export type BotStatus = "running" | "paused" | "stopped" | "error";

export interface KpiMetric {
  id: string;
  label: string;
  value: string;
  subValue?: string;
  trend?: "up" | "down" | "neutral";
  trendLabel?: string;
  accent?: "mint" | "default" | "warning" | "danger";
  large?: boolean;
}

export interface PerformancePoint {
  date: string;
  equity: number;
  pnl: number;
}

export interface Position {
  id: string;
  symbol: string;
  coin: string;
  coinColor: string;
  side: "long" | "short";
  size: number;
  entryPrice: number;
  markPrice: number;
  pnl: number;
  risk: string;
  stopLoss: number;
  takeProfit: number;
}

export interface Trade {
  id: string;
  symbol: string;
  coin: string;
  coinColor: string;
  side: "long" | "short";
  pnl: number;
  rMultiple: string;
  date: string;
}

export interface MarketIndicator {
  id: string;
  label: string;
  value: string;
  subLabel?: string;
  status: "bullish" | "bearish" | "neutral";
  description?: string;
  score?: number;
  positionSize?: string;
  volumeRatio?: string;
  atrValue?: string;
}

export interface FilterSetting {
  id: string;
  label: string;
  enabled: boolean;
  value?: string;
  hasInput?: boolean;
}

export interface QuickStat {
  label: string;
  value: string;
}

export interface ConceptLayer {
  id: string;
  title: string;
  description: string;
  icon: "trend" | "confirmation" | "risk" | "regime";
}

export interface TechStackIcon {
  name: string;
  abbr: string;
  color: string;
}

export interface RiskSetting {
  id: string;
  label: string;
  value?: string;
  suffix?: string;
  type?: "input" | "toggle";
  enabled?: boolean;
}
