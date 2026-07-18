"use client";

import { useEffect, useState } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { AnalyticsPanel } from "@/components/research/analytics/AnalyticsPanel";
import type { ResearchSeriesPoint } from "@/lib/research-api/client";

interface EquityVsBenchmarkChartProps {
  equity?: ResearchSeriesPoint[] | null;
  /** Benchmark series when API exposes it — never invent. */
  benchmark?: ResearchSeriesPoint[] | null;
  reason?: string;
}

export function EquityVsBenchmarkChart({
  equity,
  benchmark,
  reason = "Equity/Benchmark-Serien Nicht verfügbar",
}: EquityVsBenchmarkChartProps) {
  const [ready, setReady] = useState(false);
  useEffect(() => {
    setReady(true);
  }, []);

  const equityPts = equity ?? [];
  const benchPts = benchmark ?? [];
  const hasEquity = equityPts.length > 0;
  const hasBench = benchPts.length > 0;

  if (!hasEquity && !hasBench) {
    return (
      <AnalyticsPanel
        id="equity-benchmark"
        title="Equity vs Benchmark"
        unavailable
        unavailableReason={reason}
      />
    );
  }

  const byT = new Map<string, { t: string; equity?: number; benchmark?: number }>();
  for (const p of equityPts) {
    byT.set(p.t, { t: p.t, equity: p.equity, benchmark: undefined });
  }
  for (const p of benchPts) {
    const prev = byT.get(p.t) ?? { t: p.t };
    byT.set(p.t, {
      ...prev,
      benchmark: p.equity,
    });
  }
  const data = [...byT.values()].sort((a, b) => a.t.localeCompare(b.t));

  return (
    <AnalyticsPanel
      id="equity-benchmark"
      title="Equity vs Benchmark"
      subtitle={
        hasBench
          ? undefined
          : "Benchmark-Serie Nicht verfügbar — nur Strategy-Equity"
      }
    >
      {!ready ? (
        <div className="h-[180px] animate-pulse rounded-sm bg-white/5" />
      ) : (
        <div className="h-[200px]" data-testid="equity-benchmark-chart">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={data}>
              <CartesianGrid
                strokeDasharray="3 3"
                stroke="rgba(255,255,255,0.06)"
              />
              <XAxis dataKey="t" hide />
              <YAxis
                tick={{ fill: "#8a8f98", fontSize: 10 }}
                width={52}
                domain={["auto", "auto"]}
              />
              <Tooltip />
              {hasEquity ? (
                <Line
                  type="monotone"
                  dataKey="equity"
                  stroke="#42d98b"
                  dot={false}
                  strokeWidth={1.5}
                  name="Equity"
                />
              ) : null}
              {hasBench ? (
                <Line
                  type="monotone"
                  dataKey="benchmark"
                  stroke="#6d7a84"
                  dot={false}
                  strokeWidth={1.25}
                  strokeDasharray="4 3"
                  name="Benchmark"
                />
              ) : null}
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </AnalyticsPanel>
  );
}
