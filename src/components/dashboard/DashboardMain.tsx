import { KPI_METRICS } from "@/lib/mock-data";
import { ControlPanels } from "@/components/dashboard/ControlPanels";
import { MarketCards } from "@/components/dashboard/MarketCards";
import { PerformanceChartSection } from "@/components/dashboard/PerformanceChartSection";
import { PositionsTable, TradesTable } from "@/components/dashboard/Tables";
import { KpiCard } from "@/components/ui/KpiCard";

export function DashboardMain() {
  return (
    <div className="dashboard-content">
      <div className="kpi-grid">
        {KPI_METRICS.map((metric) => (
          <KpiCard key={metric.id} metric={metric} />
        ))}
      </div>

      <div className="chart-grid">
        <PerformanceChartSection />
        <MarketCards />
      </div>

      <div className="tables-grid">
        <PositionsTable />
        <TradesTable />
      </div>

      <ControlPanels />
    </div>
  );
}
