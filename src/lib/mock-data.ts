import type {
  ConceptLayer,
  FilterSetting,
  KpiMetric,
  MarketIndicator,
  PerformancePoint,
  Position,
  QuickStat,
  RiskSetting,
  TechStackIcon,
  Trade,
} from "@/types";

export const NAV_ITEMS: Array<{ label: string; href: string; active?: boolean }> = [
  { label: "Dashboard", href: "#", active: true },
  { label: "Trades", href: "#trades" },
  { label: "Positionen", href: "#positionen" },
  { label: "Backtest", href: "#backtest" },
  { label: "Einstellungen", href: "#einstellungen" },
  { label: "Logs", href: "#logs" },
];

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

export const CHART_PERIODS = ["1D", "7D", "30D", "90D", "1Y", "All"] as const;

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
  {
    id: "2",
    symbol: "ETH",
    coin: "E",
    coinColor: "#627eea",
    side: "long",
    size: 1.8,
    entryPrice: 3480,
    markPrice: 3542,
    pnl: 111.6,
    risk: "0,58%",
    stopLoss: 3380,
    takeProfit: 3680,
  },
  {
    id: "3",
    symbol: "SOL",
    coin: "S",
    coinColor: "#9945ff",
    side: "short",
    size: 38,
    entryPrice: 168.2,
    markPrice: 164.5,
    pnl: 140.6,
    risk: "0,62%",
    stopLoss: 172.5,
    takeProfit: 158.0,
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
  {
    id: "t2",
    symbol: "ETH",
    coin: "E",
    coinColor: "#627eea",
    side: "long",
    pnl: 52.2,
    rMultiple: "+1,2R",
    date: "10.07.2025",
  },
  {
    id: "t3",
    symbol: "SOL",
    coin: "S",
    coinColor: "#9945ff",
    side: "short",
    pnl: -34.8,
    rMultiple: "-0,7R",
    date: "10.07.2025",
  },
  {
    id: "t4",
    symbol: "BTC",
    coin: "B",
    coinColor: "#f7931a",
    side: "short",
    pnl: 64.0,
    rMultiple: "+1,4R",
    date: "09.07.2025",
  },
  {
    id: "t5",
    symbol: "ETH",
    coin: "E",
    coinColor: "#627eea",
    side: "long",
    pnl: -28.5,
    rMultiple: "-0,6R",
    date: "08.07.2025",
  },
];

export const FILTER_SETTINGS: FilterSetting[] = [
  { id: "f1", label: "Volumen Filter", enabled: true },
  { id: "f2", label: "Fear & Greed Filter", enabled: true, value: "≥ 25", hasInput: true },
  { id: "f3", label: "Makro Filter", enabled: false },
];

export const QUICK_STATS: QuickStat[] = [
  { label: "Total Trades", value: "160" },
  { label: "Winning Trades", value: "68" },
  { label: "Losing Trades", value: "92" },
  { label: "Ø Gewinn", value: "2,1R" },
  { label: "Ø Verlust", value: "0,9R" },
  { label: "Max Drawdown", value: "-8,4%" },
  { label: "Sharpe Ratio", value: "1,87" },
];

export const CONCEPT_LAYERS: ConceptLayer[] = [
  {
    id: "trend",
    title: "Trend",
    description: "Richtungserkennung via EMA & ADX",
    icon: "trend",
  },
  {
    id: "confirmation",
    title: "Bestätigung",
    description: "Volumen- und Momentum-Filter",
    icon: "confirmation",
  },
  {
    id: "risk",
    title: "Risikosteuerung",
    description: "Position Sizing & Stop-Loss",
    icon: "risk",
  },
  {
    id: "regime",
    title: "Regime-Filter",
    description: "Fear & Greed & Volatilität",
    icon: "regime",
  },
];

export const ARCHITECTURE_FLOW = [
  { id: "data", label: "Daten" },
  { id: "strategy", label: "Strategie Engine" },
  { id: "risk", label: "Risikomanagement" },
  { id: "execution", label: "Hyperliquid Execution" },
  { id: "dashboard", label: "Web Dashboard" },
];

export const TECH_STACK_ICONS: TechStackIcon[] = [
  { name: "Next.js", abbr: "N", color: "#ffffff" },
  { name: "Tailwind", abbr: "T", color: "#38bdf8" },
  { name: "FastAPI", abbr: "F", color: "#009688" },
  { name: "PostgreSQL", abbr: "P", color: "#336791" },
  { name: "Docker", abbr: "D", color: "#2496ed" },
  { name: "TradingView", abbr: "TV", color: "#2962ff" },
];

export const BOT_CONTROLS = {
  isActive: true,
  tradingMode: "Automatisch",
};

export const RISK_SETTINGS: RiskSetting[] = [
  { id: "r1", label: "Risiko pro Trade", value: "1,0", suffix: "%", type: "input" },
  { id: "r2", label: "Max. Gesamtrisiko", value: "3,0", suffix: "%", type: "input" },
  { id: "r3", label: "Max. Positionen", value: "5", type: "input" },
  { id: "r4", label: "ATR Stop Multiplier", value: "1,5", suffix: "x", type: "input" },
  { id: "r5", label: "ATR Target Multiplier", value: "3,0", suffix: "x", type: "input" },
  { id: "r6", label: "Trailing Stop", type: "toggle", enabled: true },
];

export const SPARKLINE_DATA = [2.1, 2.3, 2.0, 2.4, 2.2, 2.5, 2.3, 2.34];

export const VOLUME_BARS = [40, 65, 55, 80, 70, 90, 85];
