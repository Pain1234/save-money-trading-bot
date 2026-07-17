"use client";

import { useEffect, useState } from "react";

import { Card } from "@/components/ui/Card";
import type { ResearchSeriesPoint } from "@/lib/research-api/client";
import {
  Area,
  AreaChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

interface ResearchChartsProps {
  equity: ResearchSeriesPoint[];
  drawdown: ResearchSeriesPoint[];
}

export function ResearchCharts({ equity, drawdown }: ResearchChartsProps) {
  const [ready, setReady] = useState(false);
  useEffect(() => {
    setReady(true);
  }, []);

  const equityData = equity.map((p) => ({
    t: p.t,
    equity: p.equity ?? 0,
  }));
  const ddData = drawdown.map((p) => ({
    t: p.t,
    drawdown: (p.drawdown ?? 0) * 100,
  }));

  return (
    <div className="grid gap-3 lg:grid-cols-2" data-testid="research-charts">
      <Card padding="sm" className="min-h-[260px]">
        <h2 className="mb-2 text-sm font-medium">Equity Curve</h2>
        {equityData.length === 0 ? (
          <p className="text-sm text-text-muted" data-testid="research-equity-missing">
            Equity-Artefakt nicht verfügbar
          </p>
        ) : !ready ? (
          <div className="h-[200px] animate-pulse rounded bg-white/5" />
        ) : (
          <div className="h-[220px]" data-testid="research-equity-chart">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={equityData}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
                <XAxis dataKey="t" hide />
                <YAxis
                  tick={{ fill: "#8a8f98", fontSize: 10 }}
                  width={56}
                  domain={["auto", "auto"]}
                />
                <Tooltip />
                <Area
                  type="monotone"
                  dataKey="equity"
                  stroke="#5eead4"
                  fill="rgba(94,234,212,0.15)"
                  strokeWidth={1.5}
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        )}
      </Card>

      <Card padding="sm" className="min-h-[260px]">
        <h2 className="mb-2 text-sm font-medium">Drawdown Curve</h2>
        {ddData.length === 0 ? (
          <p className="text-sm text-text-muted" data-testid="research-drawdown-missing">
            Drawdown nicht verfügbar (kein Equity-Artefakt)
          </p>
        ) : !ready ? (
          <div className="h-[200px] animate-pulse rounded bg-white/5" />
        ) : (
          <div className="h-[220px]" data-testid="research-drawdown-chart">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={ddData}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
                <XAxis dataKey="t" hide />
                <YAxis
                  tick={{ fill: "#8a8f98", fontSize: 10 }}
                  width={48}
                  unit="%"
                />
                <Tooltip />
                <Line
                  type="monotone"
                  dataKey="drawdown"
                  stroke="#f87171"
                  strokeWidth={1.5}
                  dot={false}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        )}
      </Card>

      <Card padding="sm" className="lg:col-span-2">
        <h2 className="mb-2 text-sm font-medium">Benchmark-Vergleich</h2>
        <p className="text-sm text-text-muted" data-testid="research-benchmark-missing">
          Noch nicht verfügbar — keine separate Benchmark-Zeitreihe in den Artefakten.
        </p>
      </Card>
    </div>
  );
}
