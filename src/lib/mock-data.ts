import type { ConceptLayer, TechStackIcon } from "@/types";

/** Visual / educational sidebar constants (non-financial). */
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

/** @deprecated Use PRIMARY_NAV from @/lib/dashboard/navigation */
export { PRIMARY_NAV as NAV_ITEMS } from "@/lib/dashboard/navigation";

/** @deprecated Use CHART_PERIODS from @/lib/dashboard/constants */
export { CHART_PERIODS } from "@/lib/dashboard/constants";
