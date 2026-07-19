import { CostStressPanel } from "@/components/research/analytics/CostStressPanel";
import { EquityVsBenchmarkChart } from "@/components/research/analytics/EquityVsBenchmarkChart";
import { EvidenceSummaryPanel } from "@/components/research/analytics/EvidenceSummaryPanel";
import { ParameterPlateauPanel } from "@/components/research/analytics/ParameterPlateauPanel";
import { RegimeScorecardTable } from "@/components/research/analytics/RegimeScorecardTable";
import { TransitionMatrixPanel } from "@/components/research/analytics/TransitionMatrixPanel";
import { UnderwaterDrawdownChart } from "@/components/research/analytics/UnderwaterDrawdownChart";
import type { ExecutiveEvidenceAnchor } from "@/lib/research/executive-summary";
import type { ResearchSeriesPoint } from "@/lib/research-api/client";
import type { RegimeScorecardRow } from "@/components/research/analytics/RegimeScorecardTable";
import type { CostStressView } from "@/lib/research/scorecard-detail-binding";

export interface ResearchAnalyticsSectionProps {
  evidence?: ExecutiveEvidenceAnchor | null;
  equity?: ResearchSeriesPoint[] | null;
  drawdown?: ResearchSeriesPoint[] | null;
  benchmark?: ResearchSeriesPoint[] | null;
  costStressInventoryDetail?: string | null;
  costStressBound?: CostStressView | null;
  /** Bound from #291 scorecard when available (#292). */
  confidenceLabel?: string | null;
  parameterClassification?: string | null;
  parameterDetail?: string | null;
  transitionRiskLabel?: string | null;
  transitionDetail?: string | null;
  classifierTransitions?: Array<{ id: string; from: string; to: string }> | null;
  classifierTransitionsReason?: string | null;
  regimeRows?: RegimeScorecardRow[] | null;
  regimeTableReason?: string;
}

/**
 * Reusable Regime / Analytics block for Overview and detail routes (#300/#292/#302).
 * Scorecard-bound fields only when callers pass real API values.
 */
export function ResearchAnalyticsSection({
  evidence = null,
  equity = null,
  drawdown = null,
  benchmark = null,
  costStressInventoryDetail = null,
  costStressBound = null,
  confidenceLabel = null,
  parameterClassification = null,
  parameterDetail = null,
  transitionRiskLabel = null,
  transitionDetail = null,
  classifierTransitions = null,
  classifierTransitionsReason = null,
  regimeRows = null,
  regimeTableReason,
}: ResearchAnalyticsSectionProps) {
  return (
    <section className="space-y-2" data-testid="research-analytics-section">
      <div className="flex flex-wrap items-end justify-between gap-2">
        <div>
          <h2 className="text-[13px] font-semibold text-text-primary">
            Regime & Analytics
          </h2>
          <p className="mt-0.5 text-[11px] text-text-muted">
            Wiederverwendbare Panels (#300). Regime-Zeilen und Cost-Stress aus
            Scorecard-Detail (#350/#302) — fehlende Werte = Nicht verfügbar.
          </p>
        </div>
      </div>

      <RegimeScorecardTable rows={regimeRows} reason={regimeTableReason} />

      <div className="grid gap-2 lg:grid-cols-2">
        <EquityVsBenchmarkChart equity={equity} benchmark={benchmark} />
        <UnderwaterDrawdownChart drawdown={drawdown} />
      </div>

      <div className="grid gap-2 lg:grid-cols-2 xl:grid-cols-3">
        <TransitionMatrixPanel
          riskLabel={transitionRiskLabel}
          detail={transitionDetail}
          transitions={classifierTransitions}
          transitionsReason={classifierTransitionsReason}
        />
        <ParameterPlateauPanel
          classification={parameterClassification}
          detail={parameterDetail}
        />
        <CostStressPanel
          jobInventoryDetail={costStressInventoryDetail}
          bound={costStressBound}
        />
      </div>

      <EvidenceSummaryPanel
        evidence={evidence}
        confidenceLabel={confidenceLabel}
      />
    </section>
  );
}
