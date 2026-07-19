import { AnalyticsPanel } from "@/components/research/analytics/AnalyticsPanel";
import { scorecardDisplayValue } from "@/lib/research/scorecard-binding";

interface TransitionMatrixPanelProps {
  riskLabel?: string | null;
  detail?: string | null;
  /** Classifier transition refs from detail API (#350). */
  transitions?: Array<{ id: string; from: string; to: string }> | null;
  transitionsReason?: string | null;
  reason?: string;
  compactEmpty?: boolean;
  detailHref?: string | null;
}

/**
 * Transition risk + sealed classifier refs (#300/#302).
 */
export function TransitionMatrixPanel({
  riskLabel = null,
  detail = null,
  transitions = null,
  transitionsReason = null,
  reason = "Transition-Matrix Nicht verfügbar — Scorecard Detail-API",
  compactEmpty = false,
  detailHref = null,
}: TransitionMatrixPanelProps) {
  const hasValue =
    riskLabel != null &&
    riskLabel !== "" &&
    riskLabel !== "NOT_AVAILABLE";
  const hasTransitions = Array.isArray(transitions) && transitions.length > 0;

  if (!hasValue && !hasTransitions) {
    return (
      <AnalyticsPanel
        id="transition-matrix"
        title="Transition Matrix"
        subtitle="Regime-Übergänge — keine Look-ahead-Labels als Live-Signal"
        unavailable
        unavailableReason={transitionsReason ?? reason}
        compactEmpty={compactEmpty}
        detailHref={detailHref}
      />
    );
  }

  return (
    <AnalyticsPanel
      id="transition-matrix"
      title="Transition Risk"
      subtitle="risk_label + sealed classifier transitions (#350)"
    >
      <dl className="space-y-1.5 text-[12px]" data-testid="transition-risk-bound">
        {hasValue ? (
          <div>
            <dt className="text-[10px] uppercase tracking-[0.06em] text-text-muted">
              Risk Label
            </dt>
            <dd className="font-mono text-warning">
              {scorecardDisplayValue(riskLabel)}
            </dd>
          </div>
        ) : null}
        {detail ? (
          <div>
            <dt className="text-[10px] uppercase tracking-[0.06em] text-text-muted">
              Detail
            </dt>
            <dd className="text-text-secondary">{detail}</dd>
          </div>
        ) : null}
        {hasTransitions ? (
          <div>
            <dt className="text-[10px] uppercase tracking-[0.06em] text-text-muted">
              Classifier transitions
            </dt>
            <dd>
              <ul
                className="mt-1 max-h-28 space-y-0.5 overflow-y-auto font-mono text-[11px]"
                data-testid="classifier-transitions-list"
              >
                {transitions!.slice(0, 24).map((t) => (
                  <li key={t.id}>
                    {t.from} → {t.to}
                    <span className="text-text-muted"> · {t.id}</span>
                  </li>
                ))}
              </ul>
              {transitions!.length > 24 ? (
                <p className="mt-1 text-[10px] text-text-muted">
                  +{transitions!.length - 24} weitere
                </p>
              ) : null}
            </dd>
          </div>
        ) : transitionsReason ? (
          <p className="text-[10px] text-text-muted">{transitionsReason}</p>
        ) : null}
      </dl>
    </AnalyticsPanel>
  );
}
