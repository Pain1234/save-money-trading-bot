/**
 * Demo / visual-regression fixtures only.
 * Must not be imported by production dashboard pages or live design components.
 */
import type {
  FilterSetting,
  KpiMetric,
  MarketIndicator,
  PerformancePoint,
  Position,
  QuickStat,
  RiskSetting,
  Trade,
} from "@/types";

export const KPI_METRICS: KpiMetric[] = [
  {
    id: "balance",
    label: "Gesamt-Balance",
    value: "$12.456,78",
    trend: "up",
    trendLabel: "+8,47%",
    accent: "default",
  },
  {
    id: "status",
    label: "Bot Status",
    value: "AKTIV",
    subValue: "Seit 02.06.2025 14:32",
    accent: "mint",
    large: true,
  },
  {
    id: "pnl24h",
    label: "24h PnL",
    value: "$356,72",
    trend: "up",
    trendLabel: "+2,94%",
    accent: "mint",
  },
  {
    id: "positions",
    label: "Offene Positionen",
    value: "3",
    subValue: "Gesamt Risiko: 1,82%",
    accent: "default",
  },
  {
    id: "winrate",
    label: "Win Rate",
    value: "42,6%",
    subValue: "68 / 160 Trades",
    accent: "default",
  },
  {
    id: "profitfactor",
    label: "Profit Faktor",
    value: "2,31",
    subValue: "Ø Gewinn: 2,1R · Ø Verlust: 0,9R",
    accent: "default",
  },
];

export const PERFORMANCE_DATA: PerformancePoint[] = [
  { date: "Jan", equity: 2100, pnl: 0 },
  { date: "Feb", equity: 2800, pnl: 700 },
  { date: "Mär", equity: 3200, pnl: 400 },
  { date: "Apr", equity: 4100, pnl: 900 },
  { date: "Mai", equity: 5200, pnl: 1100 },
  { date: "Jun", equity: 6800, pnl: 1600 },
  { date: "Jul", equity: 7900, pnl: 1100 },
  { date: "Aug", equity: 9100, pnl: 1200 },
  { date: "Sep", equity: 9800, pnl: 700 },
  { date: "Okt", equity: 10500, pnl: 700 },
  { date: "Nov", equity: 11800, pnl: 1300 },
  { date: "Dez", equity: 12456, pnl: 656 },
];

export const MARKET_INDICATORS: MarketIndicator[] = [
  {
    id: "regime",
    label: "Markt Regime",
    value: "Gier (68)",
    status: "bullish",
    score: 68,
    positionSize: "75%",
    description: "Position Size",
  },
  {
    id: "volume",
    label: "Volumen Bestätigung",
    value: "STARK",
    status: "bullish",
    volumeRatio: "1.48x",
    description: "Volumen Ratio",
  },
  {
    id: "volatility",
    label: "Volatilität (ATR 14)",
    value: "2,34%",
    status: "neutral",
    atrValue: "2,34%",
  },
];

export const OPEN_POSITIONS: Position[] = [
  {
    id: "1",
    symbol: "BTC",
    coin: "B",
    coinColor: "#f7931a",
    side: "long",
    size: 0.12,
    entryPrice: 67240,
    markPrice: 68420,
    pnl: 141.6,
    risk: "0,62%",
    stopLoss: 65800,
    takeProfit: 70200,
  },
];

export const RECENT_TRADES: Trade[] = [
  {
    id: "t1",
    symbol: "BTC",
    coin: "B",
    coinColor: "#f7931a",
    side: "long",
    pnl: 86.4,
    rMultiple: "+1,8R",
    date: "11.07.2025",
  },
];

export const FILTER_SETTINGS: FilterSetting[] = [
  { id: "f1", label: "Volumen Filter", enabled: true },
];

export const QUICK_STATS: QuickStat[] = [
  { label: "Total Trades", value: "160" },
];

export const BOT_CONTROLS = {
  isActive: true,
  tradingMode: "Automatisch",
};

export const RISK_SETTINGS: RiskSetting[] = [
  { id: "r1", label: "Risiko pro Trade", value: "1,0", suffix: "%", type: "input" },
];

export const SPARKLINE_DATA = [2.1, 2.3, 2.0, 2.4, 2.2, 2.5, 2.3, 2.34];
export const VOLUME_BARS = [40, 65, 55, 80, 70, 90, 85];
