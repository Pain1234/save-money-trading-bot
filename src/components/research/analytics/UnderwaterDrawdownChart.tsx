"use client";

import { useEffect, useState } from "react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { AnalyticsPanel } from "@/components/research/analytics/AnalyticsPanel";
import type { ResearchSeriesPoint } from "@/lib/research-api/client";

interface UnderwaterDrawdownChartProps {
  drawdown?: ResearchSeriesPoint[] | null;
  reason?: string;
}

export function UnderwaterDrawdownChart({
  drawdown,
  reason = "Drawdown-Serie Nicht verfügbar",
}: UnderwaterDrawdownChartProps) {
  const [ready, setReady] = useState(false);
  useEffect(() => {
    setReady(true);
  }, []);

  const pts = drawdown ?? [];
  if (pts.length === 0) {
    return (
      <AnalyticsPanel
        id="underwater-drawdown"
        title="Underwater Drawdown"
        unavailable
        unavailableReason={reason}
      />
    );
  }

  const data = pts.map((p) => ({
    t: p.t,
    drawdown: (p.drawdown ?? 0) * 100,
  }));

  return (
    <AnalyticsPanel id="underwater-drawdown" title="Underwater Drawdown">
      {!ready ? (
        <div className="h-[180px] animate-pulse rounded-sm bg-white/5" />
      ) : (
        <div className="h-[200px]" data-testid="underwater-drawdown-chart">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={data}>
              <CartesianGrid
                strokeDasharray="3 3"
                stroke="rgba(255,255,255,0.06)"
              />
              <XAxis dataKey="t" hide />
              <YAxis
                tick={{ fill: "#8a8f98", fontSize: 10 }}
                width={52}
                domain={["auto", 0]}
              />
              <Tooltip />
              <Area
                type="monotone"
                dataKey="drawdown"
                stroke="#f05252"
                fill="rgba(240,82,82,0.18)"
                strokeWidth={1.5}
                name="Drawdown %"
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      )}
    </AnalyticsPanel>
  );
}
