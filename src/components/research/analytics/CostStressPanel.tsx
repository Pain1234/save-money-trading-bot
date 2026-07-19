import { AnalyticsPanel } from "@/components/research/analytics/AnalyticsPanel";
import { displayValue } from "@/lib/research-api/client";
import type { CostStressView } from "@/lib/research/scorecard-detail-binding";

interface CostStressPanelProps {
  /** Inventory hint only — never a fabricated stress boundary. */
  jobInventoryDetail?: string | null;
  /** Bound from GET …/scorecards/{id}/detail (#350/#302). */
  bound?: CostStressView | null;
  reason?: string;
}

/**
 * Cost stress scorecard slice (#300/#302).
 * Boundary only when detail returns sealed base + combined_elevated.
 */
export function CostStressPanel({
  jobInventoryDetail,
  bound = null,
  reason = "Cost-Stress-Boundary Nicht verfügbar",
}: CostStressPanelProps) {
  if (bound?.available) {
    return (
      <AnalyticsPanel
        id="cost-stress"
        title="Cost Stress"
        subtitle="Sealed boundary aus Detail-API (#350) — kein erfundenes Verdict"
      >
        <dl className="space-y-1.5 text-[12px]" data-testid="cost-stress-bound">
          <div>
            <dt className="text-[10px] uppercase tracking-[0.06em] text-text-muted">
              Robustness
            </dt>
            <dd className="font-mono text-[11px]">
              {displayValue(bound.robustnessRunId)}
            </dd>
          </div>
          <div>
            <dt className="text-[10px] uppercase tracking-[0.06em] text-text-muted">
              Base net PnL
            </dt>
            <dd className="font-mono">{displayValue(bound.baseNetPnl)}</dd>
          </div>
          <div>
            <dt className="text-[10px] uppercase tracking-[0.06em] text-text-muted">
              Combined elevated net PnL
            </dt>
            <dd className="font-mono">{displayValue(bound.elevatedNetPnl)}</dd>
          </div>
          <div>
            <dt className="text-[10px] uppercase tracking-[0.06em] text-text-muted">
              Manifest hash
            </dt>
            <dd className="break-all font-mono text-[10px]">
              {displayValue(bound.manifestHash)}
            </dd>
          </div>
        </dl>
      </AnalyticsPanel>
    );
  }

  const unavailableReason = [
    bound?.reason || reason,
    jobInventoryDetail ? `Inventar: ${displayValue(jobInventoryDetail)}` : null,
    bound?.robustnessRunId
      ? `robustness=${bound.robustnessRunId}`
      : null,
  ]
    .filter(Boolean)
    .join(" · ");

  return (
    <AnalyticsPanel
      id="cost-stress"
      title="Cost Stress"
      subtitle="Scorecard-Boundary — kein erfundenes Stress-Niveau"
      unavailable
      unavailableReason={unavailableReason}
    />
  );
}
