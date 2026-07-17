import { Suspense } from "react";

import { DashboardMain } from "@/components/dashboard/DashboardMain";
import { SectionFallback } from "@/components/dashboard/SectionFallback";
import { EquityChartServer } from "@/components/dashboard/sections/EquityChartServer";
import { FillsTableServer } from "@/components/dashboard/sections/FillsTableServer";
import { PositionsTableServer } from "@/components/dashboard/sections/PositionsTableServer";
import { StatusCardsServer } from "@/components/dashboard/sections/StatusCardsServer";
import {
  fetchDashboardSummary,
  getMonitoringErrorMessage,
} from "@/lib/paper-api/client";
import { buildSummaryViewModel } from "@/lib/dashboard/view-model";

/**
 * Overview core: only dashboard-summary (Issue #98 latency).
 * Equity, positions, fills, and diagnostic cards stream via Suspense.
 */
export default async function DashboardOverviewPage() {
  try {
    const summary = await fetchDashboardSummary();
    const vm = buildSummaryViewModel(summary);

    return (
      <div data-testid="dashboard-page-ready">
        <DashboardMain
          kpis={vm.kpis}
          quickStats={vm.quickStats}
          warnings={vm.warnings}
          staleHeartbeat={vm.staleHeartbeat}
          equitySlot={
            <Suspense fallback={<SectionFallback label="Equity" />}>
              <EquityChartServer />
            </Suspense>
          }
          statusSlot={
            <Suspense fallback={<SectionFallback label="Status" />}>
              <StatusCardsServer summary={summary} />
            </Suspense>
          }
          positionsSlot={
            <Suspense fallback={<SectionFallback label="Positionen" />}>
              <PositionsTableServer />
            </Suspense>
          }
          fillsSlot={
            <Suspense fallback={<SectionFallback label="Fills" />}>
              <FillsTableServer />
            </Suspense>
          }
        />
      </div>
    );
  } catch (error) {
    return (
      <div
        data-testid="dashboard-error-panel"
        className="rounded-xl border border-red-500/40 bg-red-500/10 p-6"
      >
        <h1 className="text-xl font-semibold text-red-300">API Error</h1>
        <p className="mt-2 text-sm">{getMonitoringErrorMessage(error)}</p>
      </div>
    );
  }
}
