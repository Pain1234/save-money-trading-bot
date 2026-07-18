import { AnalyticsPanel } from "@/components/research/analytics/AnalyticsPanel";
import { displayValue } from "@/lib/research-api/client";

interface CostStressPanelProps {
  /** Inventory hint only — never a fabricated stress boundary. */
  jobInventoryDetail?: string | null;
  reason?: string;
}

/**
 * Cost stress scorecard slice (#300).
 * Job inventory may be noted; boundary/score stays Nicht verfügbar until #291.
 */
export function CostStressPanel({
  jobInventoryDetail,
  reason = "Cost-Stress-Scorecard Nicht verfügbar — API (#291)",
}: CostStressPanelProps) {
  return (
    <AnalyticsPanel
      id="cost-stress"
      title="Cost Stress"
      subtitle="Scorecard-Boundary — kein erfundenes Stress-Niveau"
      unavailable
      unavailableReason={
        jobInventoryDetail
          ? `${reason} · Inventar: ${displayValue(jobInventoryDetail)}`
          : reason
      }
    />
  );
}
