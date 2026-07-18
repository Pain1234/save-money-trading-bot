import { AnalyticsPanel } from "@/components/research/analytics/AnalyticsPanel";
import type { ExecutiveEvidenceAnchor } from "@/lib/research/executive-summary";
import { displayValue } from "@/lib/research-api/client";

interface EvidenceSummaryPanelProps {
  evidence?: ExecutiveEvidenceAnchor | null;
  reason?: string;
}

/**
 * Evidence confidence / summary (#300).
 * May show study anchor IDs; confidence labels await #291/#288.
 */
export function EvidenceSummaryPanel({
  evidence,
  reason = "Evidence-Confidence-Profil Nicht verfügbar — Scorecard-API (#291/#288)",
}: EvidenceSummaryPanelProps) {
  if (!evidence) {
    return (
      <AnalyticsPanel
        id="evidence-summary"
        title="Evidence Summary"
        unavailable
        unavailableReason={reason}
      />
    );
  }

  return (
    <AnalyticsPanel
      id="evidence-summary"
      title="Evidence Summary"
      subtitle="Anker gebunden — Confidence-Labels noch ohne Scorecard-API"
    >
      <dl
        className="grid gap-1.5 text-[12px] sm:grid-cols-2"
        data-testid="evidence-summary-anchor"
      >
        <div>
          <dt className="text-[10px] uppercase tracking-[0.06em] text-text-muted">
            Study
          </dt>
          <dd className="font-mono text-mint">{evidence.studyId}</dd>
        </div>
        <div>
          <dt className="text-[10px] uppercase tracking-[0.06em] text-text-muted">
            Experiment / Run
          </dt>
          <dd className="font-mono">
            {evidence.experimentId}
            {evidence.runId ? ` / ${evidence.runId}` : ""}
          </dd>
        </div>
        <div>
          <dt className="text-[10px] uppercase tracking-[0.06em] text-text-muted">
            Confidence
          </dt>
          <dd className="font-mono text-text-muted" data-testid="evidence-confidence-value">
            {displayValue(null)}
          </dd>
        </div>
        <div>
          <dt className="text-[10px] uppercase tracking-[0.06em] text-text-muted">
            Strategy
          </dt>
          <dd className="font-mono">
            {displayValue(evidence.strategyId)} @{" "}
            {displayValue(evidence.strategyVersion)}
          </dd>
        </div>
      </dl>
      <p className="text-[11px] text-text-muted">{reason}</p>
    </AnalyticsPanel>
  );
}
