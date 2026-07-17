import type { ReactNode } from "react";

import { ControlPanels } from "@/components/dashboard/ControlPanels";
import { KpiCard } from "@/components/ui/KpiCard";
import type { DashboardKpiVm, QuickStatVm } from "@/lib/dashboard/types";

interface DashboardMainProps {
  kpis: DashboardKpiVm[];
  quickStats: QuickStatVm[];
  equitySlot: ReactNode;
  statusSlot: ReactNode;
  positionsSlot: ReactNode;
  fillsSlot: ReactNode;
  warnings?: string[];
  staleHeartbeat?: boolean;
}

export function DashboardMain({
  kpis,
  quickStats,
  equitySlot,
  statusSlot,
  positionsSlot,
  fillsSlot,
  warnings = [],
  staleHeartbeat = false,
}: DashboardMainProps) {
  return (
    <div className="dashboard-content" data-testid="dashboard-main">
      {staleHeartbeat || warnings.length > 0 ? (
        <div
          className="mb-3 rounded-[8px] border border-warning/40 bg-warning/10 px-3 py-2 text-[12px] text-warning"
          data-testid="dashboard-warnings"
        >
          {staleHeartbeat ? <p>Heartbeat ist veraltet.</p> : null}
          {warnings.length > 0 ? (
            <ul className="mt-1 list-disc pl-4">
              {warnings.map((w) => (
                <li key={w}>{w}</li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : null}

      <div className="kpi-grid" data-testid="kpi-grid">
        {kpis.map((metric) => (
          <KpiCard key={metric.id} metric={metric} />
        ))}
      </div>

      <div className="chart-grid">
        {equitySlot}
        {statusSlot}
      </div>

      <div className="tables-grid">
        {positionsSlot}
        {fillsSlot}
      </div>

      <ControlPanels quickStats={quickStats} />
    </div>
  );
}
