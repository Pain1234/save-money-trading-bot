import { AnalyticsPanel } from "@/components/research/analytics/AnalyticsPanel";

interface TransitionMatrixPanelProps {
  reason?: string;
}

/** Transition matrix (#300) — awaits scorecard/transition API (#291/#289). */
export function TransitionMatrixPanel({
  reason = "Transition-Matrix Nicht verfügbar — Scorecard/Transition-API (#291/#289)",
}: TransitionMatrixPanelProps) {
  return (
    <AnalyticsPanel
      id="transition-matrix"
      title="Transition Matrix"
      subtitle="Regime-Übergänge — keine Look-ahead-Labels als Live-Signal"
      unavailable
      unavailableReason={reason}
    />
  );
}
