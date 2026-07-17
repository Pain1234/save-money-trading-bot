export const CHART_PERIODS = ["1D", "7D", "30D", "90D", "1Y", "All"] as const;

export type ChartPeriod = (typeof CHART_PERIODS)[number];

export const READ_ONLY_BANNER =
  "Read-only Monitoring — Bot-Steuerung, Risiko- und Filteränderungen sind nicht verfügbar.";

export const V1_SIDE_LABEL = "LONG";
