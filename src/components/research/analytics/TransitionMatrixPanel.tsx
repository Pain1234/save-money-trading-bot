import { AnalyticsPanel } from "@/components/research/analytics/AnalyticsPanel";
import { scorecardDisplayValue } from "@/lib/research/scorecard-binding";

interface TransitionMatrixPanelProps {
  riskLabel?: string | null;
  detail?: string | null;
  reason?: string;
}

/**
 * Transition risk summary (#300/#292).
 * Full transition matrix is not in Layer-5 payload — bind risk_label only.
 */
export function TransitionMatrixPanel({
  riskLabel = null,
  detail = null,
  reason = "Transition-Matrix Nicht verfügbar — Scorecard/Transition-API (#291/#289)",
}: TransitionMatrixPanelProps) {
  const hasValue =
    riskLabel != null &&
    riskLabel !== "" &&
    riskLabel !== "NOT_AVAILABLE";

  if (!hasValue) {
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

  return (
    <AnalyticsPanel
      id="transition-matrix"
      title="Transition Risk"
      subtitle="risk_label aus behaviour.transition_risk — keine erfundene Matrix"
    >
      <dl className="space-y-1.5 text-[12px]" data-testid="transition-risk-bound">
        <div>
          <dt className="text-[10px] uppercase tracking-[0.06em] text-text-muted">
            Risk Label
          </dt>
          <dd className="font-mono text-warning">
            {scorecardDisplayValue(riskLabel)}
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
        <p className="text-[10px] text-text-muted">
          Volle Transition-Matrix liegt im Behaviour-Artefakt, nicht in Layer-5
          GET.
        </p>
      </dl>
    </AnalyticsPanel>
  );
}
