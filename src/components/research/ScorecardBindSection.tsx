import { ResearchAnalyticsSection } from "@/components/research/analytics/ResearchAnalyticsSection";
import { ResearchForensicsSection } from "@/components/research/ResearchForensicsSection";
import { ScorecardProfileStrip } from "@/components/research/ScorecardProfileStrip";
import {
  buildScorecardProfileView,
  type ScorecardBindState,
} from "@/lib/research/scorecard-binding";
import {
  mapCostStressFromDetail,
  mapRegimeRowsFromDetail,
  mapTransitionFromDetail,
} from "@/lib/research/scorecard-detail-binding";
import type { ExecutiveEvidenceAnchor } from "@/lib/research/executive-summary";
import type {
  ResearchSeriesPoint,
  ValidationStudyDecision,
} from "@/lib/research-api/client";
import type { ForensicsExtras } from "@/components/research/ResearchForensicsSection";

interface ScorecardBindSectionProps {
  bind: ScorecardBindState;
  evidence?: ExecutiveEvidenceAnchor | null;
  equity?: ResearchSeriesPoint[] | null;
  drawdown?: ResearchSeriesPoint[] | null;
  benchmark?: ResearchSeriesPoint[] | null;
  costStressInventoryDetail?: string | null;
  finalDecision?: ValidationStudyDecision | null;
  forensicsExtras?: ForensicsExtras | null;
}

/**
 * Scorecard load states + #300 analytics + #302 forensics (#292 rest via detail).
 * Empty/Error keep panels honest (Nicht verfügbar); Ready maps global_profile + detail.
 */
export function ScorecardBindSection({
  bind,
  evidence = null,
  equity = null,
  drawdown = null,
  benchmark = null,
  costStressInventoryDetail = null,
  finalDecision = null,
  forensicsExtras = null,
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
          regimeTableReason="Kein Scorecard — Regime-Zeilen Nicht verfügbar"
        />
        <ResearchForensicsSection extras={forensicsExtras} />
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
        <ResearchForensicsSection
          detailError={bind.message}
          extras={forensicsExtras}
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

  const detail = bind.detail;
  const regimeRows = mapRegimeRowsFromDetail(detail);
  const costStressBound = detail
    ? mapCostStressFromDetail(detail.cost_stress)
    : null;
  const transition = mapTransitionFromDetail(detail);
  const regimeReason = bind.detailError
    ? `Scorecard-Detail-Fehler — Regime-Zeilen Nicht verfügbar (${bind.detailError})`
    : regimeRows.length === 0
      ? "Keine regime_rows im Scorecard-Detail (sealed regime_metrics fehlen oder leer)"
      : undefined;

  return (
    <section className="space-y-3" data-testid="scorecard-bind-ready">
      <ScorecardProfileStrip profile={profile} />
      <ResearchAnalyticsSection
        evidence={evidence}
        equity={equity}
        drawdown={drawdown}
        benchmark={benchmark}
        costStressInventoryDetail={costStressInventoryDetail}
        costStressBound={costStressBound}
        confidenceLabel={profile.confidenceLabel}
        parameterClassification={profile.parameterClassification}
        parameterDetail={profile.parameterDetail}
        transitionRiskLabel={
          transition.riskLabel ?? profile.transitionRiskLabel
        }
        transitionDetail={transition.detail ?? profile.transitionDetail}
        classifierTransitions={transition.transitions}
        classifierTransitionsReason={transition.transitionsReason}
        regimeRows={regimeRows}
        regimeTableReason={regimeReason}
      />
      <ResearchForensicsSection
        detail={detail}
        detailError={bind.detailError}
        transition={transition}
        extras={forensicsExtras}
        audit={{
          scorecardId: bind.scorecard.scorecard_id,
          evaluatedAt: bind.scorecard.evaluated_at,
          policyVersion: bind.scorecard.policy_version,
          policyContentHash: bind.scorecard.policy_content_hash,
          evidenceContentHash: bind.scorecard.evidence_content_hash,
          runCodeCommit: bind.scorecard.run_code_commit,
          evaluationCodeCommit: bind.scorecard.evaluation_code_commit,
          status: String(bind.scorecard.status),
          invalidationReason: bind.scorecard.invalidation_reason,
        }}
      />
    </section>
  );
}
