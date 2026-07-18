import { CostStressPanel } from "@/components/research/analytics/CostStressPanel";
import { EquityVsBenchmarkChart } from "@/components/research/analytics/EquityVsBenchmarkChart";
import { EvidenceSummaryPanel } from "@/components/research/analytics/EvidenceSummaryPanel";
import { ParameterPlateauPanel } from "@/components/research/analytics/ParameterPlateauPanel";
import { RegimeScorecardTable } from "@/components/research/analytics/RegimeScorecardTable";
import { TransitionMatrixPanel } from "@/components/research/analytics/TransitionMatrixPanel";
import { UnderwaterDrawdownChart } from "@/components/research/analytics/UnderwaterDrawdownChart";
import type { ExecutiveEvidenceAnchor } from "@/lib/research/executive-summary";
import type { ResearchSeriesPoint } from "@/lib/research-api/client";

export interface ResearchAnalyticsSectionProps {
  evidence?: ExecutiveEvidenceAnchor | null;
  equity?: ResearchSeriesPoint[] | null;
  drawdown?: ResearchSeriesPoint[] | null;
  benchmark?: ResearchSeriesPoint[] | null;
  costStressInventoryDetail?: string | null;
}

/**
 * Reusable Regime / Analytics block for Overview and later detail routes (#300).
 * Scorecard fields stay empty until #291 types are bound (#292) — no fabricated metrics.
 */
export function ResearchAnalyticsSection({
  evidence = null,
  equity = null,
  drawdown = null,
  benchmark = null,
  costStressInventoryDetail = null,
}: ResearchAnalyticsSectionProps) {
  return (
    <section className="space-y-2" data-testid="research-analytics-section">
      <div className="flex flex-wrap items-end justify-between gap-2">
        <div>
          <h2 className="text-[13px] font-semibold text-text-primary">
            Regime & Analytics
          </h2>
          <p className="mt-0.5 text-[11px] text-text-muted">
            Wiederverwendbare Panels (#300). Scorecard-Daten ohne API = Nicht
            verfügbar — Binding folgt in #292.
          </p>
        </div>
      </div>

      <RegimeScorecardTable />

      <div className="grid gap-2 lg:grid-cols-2">
        <EquityVsBenchmarkChart equity={equity} benchmark={benchmark} />
        <UnderwaterDrawdownChart drawdown={drawdown} />
      </div>

      <div className="grid gap-2 lg:grid-cols-2 xl:grid-cols-3">
        <TransitionMatrixPanel />
        <ParameterPlateauPanel />
        <CostStressPanel jobInventoryDetail={costStressInventoryDetail} />
      </div>

      <EvidenceSummaryPanel evidence={evidence} />
    </section>
  );
}
