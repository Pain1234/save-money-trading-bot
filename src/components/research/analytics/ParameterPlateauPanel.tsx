import { AnalyticsPanel } from "@/components/research/analytics/AnalyticsPanel";

interface ParameterPlateauPanelProps {
  reason?: string;
}

/** Parameter plateau (#300) — awaits #291 / #290 plateau classification. */
export function ParameterPlateauPanel({
  reason = "Parameter-Area Nicht verfügbar — Scorecard/Plateau-API (#291/#290)",
}: ParameterPlateauPanelProps) {
  return (
    <AnalyticsPanel
      id="parameter-plateau"
      title="Parameter Plateau"
      subtitle="Plateau vs Isolierter Peak — keine erfundenen Stabilitäts-Scores"
      unavailable
      unavailableReason={reason}
    />
  );
}
