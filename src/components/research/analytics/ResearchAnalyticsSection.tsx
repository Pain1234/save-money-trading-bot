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
import type { ScorecardPinClassification } from "@/lib/research/scorecard-binding";
import { SCORECARD_PIN_STATUS } from "@/lib/research/scorecard-binding";

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
  /** Overview pin status — drives compact empty chrome (#358). */
  pin?: ScorecardPinClassification | null;
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
  pin = null,
}: ResearchAnalyticsSectionProps) {
  const pinReady = pin?.status === SCORECARD_PIN_STATUS.READY;
  const compactEmpty = Boolean(pin && !pinReady);
  const emptyReason = pin?.cause;
  const detailHref = pin?.studyHref ?? null;

  return (
    <section className="space-y-2" data-testid="research-analytics-section">
      <div className="flex flex-wrap items-end justify-between gap-2">
        <div>
          <h2 className="text-[13px] font-semibold text-text-primary">
            Regime & Analytics
          </h2>
          <p className="mt-0.5 text-[12px] leading-snug text-text-secondary">
            Wiederverwendbare Panels (#300). Regime-Zeilen und Cost-Stress aus
            Scorecard-Detail (#350/#302) — fehlende Werte = Nicht verfügbar.
          </p>
        </div>
      </div>

      <RegimeScorecardTable
        rows={regimeRows}
        reason={
          regimeTableReason ??
          (compactEmpty
            ? emptyReason
            : "Regime-Zeilen nicht in Scorecard Layer-5 Payload")
        }
        compactEmpty={compactEmpty}
        detailHref={compactEmpty ? detailHref : null}
      />

      <div className="grid gap-2 lg:grid-cols-2">
        <EquityVsBenchmarkChart
          equity={equity}
          benchmark={benchmark}
          reason={
            compactEmpty
              ? emptyReason ?? undefined
              : undefined
          }
          compactEmpty={compactEmpty}
          detailHref={compactEmpty ? detailHref : null}
        />
        <UnderwaterDrawdownChart
          drawdown={drawdown}
          reason={compactEmpty ? emptyReason ?? undefined : undefined}
          compactEmpty={compactEmpty}
          detailHref={compactEmpty ? detailHref : null}
        />
      </div>

      <div className="grid gap-2 lg:grid-cols-2 xl:grid-cols-3">
        <TransitionMatrixPanel
          riskLabel={transitionRiskLabel}
          detail={transitionDetail}
          transitions={classifierTransitions}
          transitionsReason={
            classifierTransitionsReason ??
            (compactEmpty ? emptyReason : undefined)
          }
          compactEmpty={compactEmpty}
          detailHref={compactEmpty ? detailHref : null}
        />
        <ParameterPlateauPanel
          classification={parameterClassification}
          detail={parameterDetail}
          reason={compactEmpty ? emptyReason ?? undefined : undefined}
          compactEmpty={compactEmpty}
          detailHref={compactEmpty ? detailHref : null}
        />
        <CostStressPanel
          jobInventoryDetail={costStressInventoryDetail}
          bound={costStressBound}
          reason={compactEmpty ? emptyReason ?? undefined : undefined}
          compactEmpty={compactEmpty}
          detailHref={compactEmpty ? detailHref : null}
        />
      </div>

      <EvidenceSummaryPanel
        evidence={evidence}
        confidenceLabel={confidenceLabel}
        reason={compactEmpty ? emptyReason ?? undefined : undefined}
        compactEmpty={compactEmpty}
        detailHref={compactEmpty ? detailHref : null}
      />
    </section>
  );
}
