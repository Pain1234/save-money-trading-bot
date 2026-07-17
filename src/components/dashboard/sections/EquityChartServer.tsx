import { PerformanceChartSection } from "@/components/dashboard/PerformanceChartSection";
import {
  fetchEquity,
  getMonitoringErrorMessage,
} from "@/lib/paper-api/client";
import { buildEquityChartPoints } from "@/lib/dashboard/view-model";

export async function EquityChartServer() {
  try {
    const page = await fetchEquity();
    const points = buildEquityChartPoints(page.items);
    return (
      <PerformanceChartSection
        points={points}
        emptyMessage="Keine Equity-Historie verfügbar"
      />
    );
  } catch (error) {
    return (
      <PerformanceChartSection
        points={[]}
        errorMessage={getMonitoringErrorMessage(error)}
      />
    );
  }
}
