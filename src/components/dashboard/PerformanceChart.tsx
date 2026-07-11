"use client";

import { useEffect, useMemo, useState } from "react";
import { CHART_PERIODS } from "@/lib/mock-data";
import { formatCurrency } from "@/lib/utils";
import { Card } from "@/components/ui/Card";
import { ChevronDown } from "lucide-react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

/** Display-only equity series — organic uptrend with drawdowns & sideways phases */
const CHART_DISPLAY_DATA = [
  { label: "Jan", equity: 2140 },
  { label: "", equity: 2325 },
  { label: "", equity: 2260 },
  { label: "Feb", equity: 2680 },
  { label: "", equity: 2810 },
  { label: "", equity: 2745 },
  { label: "Mär", equity: 3180 },
  { label: "", equity: 3285 },
  { label: "", equity: 3220 },
  { label: "Apr", equity: 3680 },
  { label: "", equity: 3795 },
  { label: "", equity: 3725 },
  { label: "Mai", equity: 4180 },
  { label: "", equity: 4010 },
  { label: "", equity: 4095 },
  { label: "Jun", equity: 4580 },
  { label: "", equity: 4720 },
  { label: "", equity: 4645 },
  { label: "Jul", equity: 5280 },
  { label: "", equity: 5445 },
  { label: "", equity: 5355 },
  { label: "Aug", equity: 5980 },
  { label: "", equity: 6180 },
  { label: "", equity: 6065 },
  { label: "Sep", equity: 6680 },
  { label: "", equity: 6560 },
  { label: "", equity: 6625 },
  { label: "Okt", equity: 7280 },
  { label: "", equity: 7440 },
  { label: "", equity: 7355 },
  { label: "Nov", equity: 8120 },
  { label: "", equity: 7880 },
  { label: "", equity: 8015 },
  { label: "Dez", equity: 8720 },
  { label: "", equity: 9240 },
  { label: "", equity: 8980 },
  { label: "", equity: 9680 },
  { label: "", equity: 10180 },
  { label: "", equity: 10640 },
  { label: "", equity: 11120 },
  { label: "", equity: 11680 },
  { label: "", equity: 12090 },
  { label: "", equity: 12456 },
];

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
        {formatCurrency(payload[0].value)}
      </p>
    </div>
  );
}

export function PerformanceChart() {
  const [activePeriod, setActivePeriod] = useState("30D");
  const [chartReady, setChartReady] = useState(false);

  useEffect(() => {
    setChartReady(true);
  }, []);

  const yDomain = useMemo(() => {
    const values = CHART_DISPLAY_DATA.map((d) => d.equity);
    const min = Math.min(...values);
    const max = Math.max(...values);
    const pad = (max - min) * 0.06;
    return [Math.floor(min - pad), Math.ceil(max + pad)] as [number, number];
  }, []);

  return (
    <Card padding="sm" className="chart-panel flex min-w-0 flex-col">
      <div className="mb-2 flex items-center justify-between gap-2">
        <div>
          <h3 className="text-[13px] font-medium text-text-primary">Performance</h3>
          <button
            type="button"
            className="mt-0.5 flex items-center gap-0.5 text-[11px] text-text-muted hover:text-text-secondary"
          >
            Eigenkapital
            <ChevronDown className="h-3 w-3" />
          </button>
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
        {chartReady ? (
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart
              data={CHART_DISPLAY_DATA}
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
                interval={0}
                tickFormatter={(v) => v || ""}
              />
              <YAxis
                axisLine={false}
                tickLine={false}
                tick={{ fill: "#6d7a84", fontSize: 11 }}
                tickFormatter={(v) =>
                  v >= 1000 ? `$${(v / 1000).toFixed(1)}k` : `$${v}`
                }
                width={42}
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
