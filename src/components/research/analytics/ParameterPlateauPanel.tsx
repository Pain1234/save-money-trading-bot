import { AnalyticsPanel } from "@/components/research/analytics/AnalyticsPanel";
import { scorecardDisplayValue } from "@/lib/research/scorecard-binding";

interface ParameterPlateauPanelProps {
  classification?: string | null;
  detail?: string | null;
  reason?: string;
}

/** Parameter plateau (#300/#292) — binds classification from scorecard when present. */
export function ParameterPlateauPanel({
  classification = null,
  detail = null,
  reason = "Parameter-Area Nicht verfügbar — Scorecard/Plateau-API (#291/#290)",
}: ParameterPlateauPanelProps) {
  const hasValue =
    classification != null &&
    classification !== "" &&
    classification !== "NOT_AVAILABLE";

  if (!hasValue) {
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

  return (
    <AnalyticsPanel
      id="parameter-plateau"
      title="Parameter Plateau"
      subtitle="Aus global_profile.parameter_area — keine erfundenen Scores"
    >
      <dl className="space-y-1.5 text-[12px]" data-testid="parameter-plateau-bound">
        <div>
          <dt className="text-[10px] uppercase tracking-[0.06em] text-text-muted">
            Classification
          </dt>
          <dd className="font-mono text-mint">
            {scorecardDisplayValue(classification)}
          </dd>
        </div>
        {detail ? (
          <div>
            <dt className="text-[10px] uppercase tracking-[0.06em] text-text-muted">
              Detail
            </dt>
            <dd className="text-text-secondary">{detail}</dd>
          </div>
        ) : null}
      </dl>
    </AnalyticsPanel>
  );
}
