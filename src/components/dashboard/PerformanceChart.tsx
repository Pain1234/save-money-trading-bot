"use client";

import { useEffect, useMemo, useState } from "react";
import { CHART_PERIODS } from "@/lib/dashboard/constants";
import {
  computeEquityYDomain,
  formatEquityAxisTick,
  formatMoneyDisplay,
} from "@/lib/dashboard/formatters";
import { filterEquityByPeriod } from "@/lib/dashboard/view-model";
import type { EquityChartPointVm } from "@/lib/dashboard/types";
import { Card } from "@/components/ui/Card";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

function CustomTooltip({
  active,
  payload,
  label,
}: {
  active?: boolean;
  payload?: Array<{ value: number; payload: { label: string } }>;
  label?: string;
}) {
  if (!active || !payload?.length) return null;
  const pointLabel = payload[0].payload.label || label;

  return (
    <div className="rounded-[6px] border border-border bg-bg-card-alt px-2 py-1">
      {pointLabel && (
        <p className="text-[9px] text-text-muted">{pointLabel}</p>
      )}
      <p className="font-mono text-[10px] text-mint">
        {formatMoneyDisplay(payload[0].value)}
      </p>
    </div>
  );
}

interface PerformanceChartProps {
  points: EquityChartPointVm[];
  emptyMessage?: string;
  errorMessage?: string | null;
}

export function PerformanceChart({
  points,
  emptyMessage = "Keine Equity-Historie verfügbar",
  errorMessage = null,
}: PerformanceChartProps) {
  const [activePeriod, setActivePeriod] = useState("30D");
  const [chartReady, setChartReady] = useState(false);

  useEffect(() => {
    setChartReady(true);
  }, []);

  const filtered = useMemo(
    () => filterEquityByPeriod(points, activePeriod),
    [points, activePeriod],
  );

  const yDomain = useMemo(
    () => computeEquityYDomain(filtered.map((d) => d.equity)),
    [filtered],
  );

  return (
    <Card
      padding="sm"
      className="chart-panel flex min-w-0 flex-col"
      data-testid="performance-chart"
    >
      <div className="mb-2 flex items-center justify-between gap-2">
        <div>
          <h3 className="text-[13px] font-medium text-text-primary">
            Performance
          </h3>
          <p className="mt-0.5 text-[11px] text-text-muted">
            Absolutes Eigenkapital (USD)
          </p>
        </div>
        <div className="flex gap-0.5">
          {CHART_PERIODS.map((period) => (
            <button
              key={period}
              type="button"
              onClick={() => setActivePeriod(period)}
              className={`rounded px-2 py-0.5 text-[11px] transition-colors ${
                activePeriod === period
                  ? "border border-mint/20 bg-mint-glow text-mint"
                  : "text-text-muted hover:text-text-secondary"
              }`}
            >
              {period}
            </button>
          ))}
        </div>
      </div>

      <div className="min-h-0 flex-1">
        {errorMessage ? (
          <div
            className="flex h-full items-center justify-center text-[12px] text-negative"
            data-testid="equity-error"
          >
            {errorMessage}
          </div>
        ) : filtered.length === 0 ? (
          <div
            className="flex h-full items-center justify-center text-[12px] text-text-muted"
            data-testid="equity-empty"
          >
            {emptyMessage}
          </div>
        ) : chartReady ? (
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart
              data={filtered}
              margin={{ top: 2, right: 2, left: -12, bottom: 0 }}
            >
              <defs>
                <linearGradient id="equityGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#42d98b" stopOpacity={0.22} />
                  <stop offset="55%" stopColor="#42d98b" stopOpacity={0.08} />
                  <stop offset="100%" stopColor="#42d98b" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid
                strokeDasharray="2 5"
                stroke="rgb(36 52 64 / 0.55)"
                vertical={false}
              />
              <XAxis
                dataKey="label"
                axisLine={false}
                tickLine={false}
                tick={{ fill: "#6d7a84", fontSize: 11 }}
                dy={4}
                interval="preserveStartEnd"
                tickFormatter={(v) => v || ""}
              />
              <YAxis
                axisLine={false}
                tickLine={false}
                tick={{ fill: "#6d7a84", fontSize: 11 }}
                tickFormatter={(v) => formatEquityAxisTick(v, yDomain)}
                width={64}
                domain={yDomain}
                tickCount={5}
              />
              <Tooltip content={<CustomTooltip />} />
              <Area
                type="monotone"
                dataKey="equity"
                stroke="#42d98b"
                strokeWidth={1.75}
                fill="url(#equityGradient)"
                dot={false}
                activeDot={{
                  r: 3,
                  fill: "#42d98b",
                  stroke: "#060e14",
                  strokeWidth: 1.5,
                }}
              />
            </AreaChart>
          </ResponsiveContainer>
        ) : (
          <div className="h-full w-full" aria-hidden />
        )}
      </div>
    </Card>
  );
}
