import { ResearchAnalyticsSection } from "@/components/research/analytics/ResearchAnalyticsSection";
import { ScorecardProfileStrip } from "@/components/research/ScorecardProfileStrip";
import {
  buildScorecardProfileView,
  type ScorecardBindState,
} from "@/lib/research/scorecard-binding";
import type { ExecutiveEvidenceAnchor } from "@/lib/research/executive-summary";
import type {
  ResearchSeriesPoint,
  ValidationStudyDecision,
} from "@/lib/research-api/client";

interface ScorecardBindSectionProps {
  bind: ScorecardBindState;
  evidence?: ExecutiveEvidenceAnchor | null;
  equity?: ResearchSeriesPoint[] | null;
  drawdown?: ResearchSeriesPoint[] | null;
  benchmark?: ResearchSeriesPoint[] | null;
  costStressInventoryDetail?: string | null;
  finalDecision?: ValidationStudyDecision | null;
}

/**
 * Scorecard load states + #300 analytics reuse (#292).
 * Empty/Error keep panels honest (Nicht verfügbar); Ready maps global_profile.
 */
export function ScorecardBindSection({
  bind,
  evidence = null,
  equity = null,
  drawdown = null,
  benchmark = null,
  costStressInventoryDetail = null,
  finalDecision = null,
}: ScorecardBindSectionProps) {
  if (bind.kind === "empty") {
    return (
      <section className="space-y-2" data-testid="scorecard-bind-empty">
        <p className="text-[12px] text-text-muted">{bind.reason}</p>
        <ResearchAnalyticsSection
          evidence={evidence}
          equity={equity}
          drawdown={drawdown}
          benchmark={benchmark}
          costStressInventoryDetail={costStressInventoryDetail}
          regimeTableReason="Regime-Zeilen nicht in Scorecard Layer-5 Payload (regime_metrics.json nicht via GET /scorecards exponiert)"
        />
      </section>
    );
  }

  if (bind.kind === "error") {
    return (
      <section className="space-y-2" data-testid="scorecard-bind-error">
        <div className="rounded-sm border border-red-500/40 bg-red-500/10 px-3 py-2 text-[12px] text-red-200">
          Scorecard konnte nicht geladen werden: {bind.message}
        </div>
        <ResearchAnalyticsSection
          evidence={evidence}
          equity={equity}
          drawdown={drawdown}
          benchmark={benchmark}
          costStressInventoryDetail={costStressInventoryDetail}
          regimeTableReason="Scorecard-Fehler — Regime-Tabelle nicht gebunden"
        />
      </section>
    );
  }

  const profile = buildScorecardProfileView(bind.scorecard, {
    warnings: bind.warnings,
    finalDecision: finalDecision
      ? {
          outcome: finalDecision.outcome,
          detail: `${finalDecision.decided_by} · ${finalDecision.decided_at}`,
        }
      : null,
  });

  return (
    <section className="space-y-3" data-testid="scorecard-bind-ready">
      <ScorecardProfileStrip profile={profile} />
      <ResearchAnalyticsSection
        evidence={evidence}
        equity={equity}
        drawdown={drawdown}
        benchmark={benchmark}
        costStressInventoryDetail={costStressInventoryDetail}
        confidenceLabel={profile.confidenceLabel}
        parameterClassification={profile.parameterClassification}
        parameterDetail={profile.parameterDetail}
        transitionRiskLabel={profile.transitionRiskLabel}
        transitionDetail={profile.transitionDetail}
        regimeTableReason="Regime-Zeilen (Quality/Confidence/Behaviour/Trades/…) liegen in regime_metrics.json — nicht in Layer-5 GET Payload"
      />
    </section>
  );
}
