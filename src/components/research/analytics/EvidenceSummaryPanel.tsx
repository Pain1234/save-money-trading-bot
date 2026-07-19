import { AnalyticsPanel } from "@/components/research/analytics/AnalyticsPanel";
import type { ExecutiveEvidenceAnchor } from "@/lib/research/executive-summary";
import { scorecardDisplayValue } from "@/lib/research/scorecard-binding";
import { displayValue } from "@/lib/research-api/client";

interface EvidenceSummaryPanelProps {
  evidence?: ExecutiveEvidenceAnchor | null;
  confidenceLabel?: string | null;
  reason?: string;
  compactEmpty?: boolean;
  detailHref?: string | null;
}

/**
 * Evidence confidence / summary (#300/#292).
 * Confidence label binds from scorecard when provided.
 */
export function EvidenceSummaryPanel({
  evidence,
  confidenceLabel = null,
  reason = "Evidence-Confidence-Profil Nicht verfügbar — Scorecard-API (#291/#288)",
  compactEmpty = false,
  detailHref = null,
}: EvidenceSummaryPanelProps) {
  if (!evidence && confidenceLabel == null) {
    return (
      <AnalyticsPanel
        id="evidence-summary"
        title="Evidence Summary"
        unavailable
        unavailableReason={reason}
        compactEmpty={compactEmpty}
        detailHref={detailHref}
      />
    );
  }

  return (
    <AnalyticsPanel
      id="evidence-summary"
      title="Evidence Summary"
      subtitle={
        confidenceLabel != null && confidenceLabel !== "NOT_AVAILABLE"
          ? "Anker + Confidence aus Scorecard (#292)"
          : "Anker gebunden — Confidence ggf. noch ohne Scorecard"
      }
    >
      <dl
        className="grid gap-1.5 text-[12px] sm:grid-cols-2"
        data-testid="evidence-summary-anchor"
      >
        {evidence ? (
          <>
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
                Strategy
              </dt>
              <dd className="font-mono">
                {displayValue(evidence.strategyId)} @{" "}
                {displayValue(evidence.strategyVersion)}
              </dd>
            </div>
          </>
        ) : null}
        <div>
          <dt className="text-[10px] uppercase tracking-[0.06em] text-text-muted">
            Confidence
          </dt>
          <dd
            className="font-mono"
            data-testid="evidence-confidence-value"
          >
            {scorecardDisplayValue(confidenceLabel)}
          </dd>
        </div>
      </dl>
    </AnalyticsPanel>
  );
}
