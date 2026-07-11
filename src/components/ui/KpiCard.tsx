import { cn } from "@/lib/utils";
import type { KpiMetric } from "@/types";
import { Card } from "./Card";

const BALANCE_SPARKLINE = [
  11820, 11910, 11785, 12040, 11980, 12120, 12055, 12210, 12140, 12305, 12260, 12456,
];

function MiniSparkline({ data }: { data: number[] }) {
  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min || 1;
  const linePoints = data
    .map((v, i) => {
      const x = (i / (data.length - 1)) * 100;
      const y = 100 - ((v - min) / range) * 100;
      return `${x},${y}`;
    })
    .join(" ");
  const areaPoints = `0,100 ${linePoints} 100,100`;

  return (
    <svg
      viewBox="0 0 100 28"
      className="h-6 w-16 shrink-0 opacity-90"
      preserveAspectRatio="none"
    >
      <polygon fill="rgba(66,217,139,0.12)" points={areaPoints} />
      <polyline
        fill="none"
        stroke="#42d98b"
        strokeWidth="1.5"
        points={linePoints}
        vectorEffect="non-scaling-stroke"
      />
    </svg>
  );
}

interface KpiCardProps {
  metric: KpiMetric;
}

export function KpiCard({ metric }: KpiCardProps) {
  const isStatus = metric.id === "status";
  const isBalance = metric.id === "balance";

  return (
    <Card padding="sm" className="kpi-panel flex min-w-0 flex-col justify-between">
      <span className="text-[11px] uppercase tracking-[0.05em] text-text-muted">
        {metric.label}
      </span>

      <div className="flex items-end justify-between gap-2">
        <div className="min-w-0 flex-1">
          {isStatus ? (
            <p className="text-[24px] font-medium leading-none tracking-tight text-mint">
              {metric.value}
            </p>
          ) : (
            <p
              className={cn(
                "font-mono text-[24px] leading-none tracking-tight",
                metric.accent === "mint" ? "text-mint" : "text-text-primary",
              )}
            >
              {metric.value}
            </p>
          )}

          {metric.trendLabel && !metric.subValue && (
            <p
              className={cn(
                "mt-1 font-mono text-[11px] leading-none",
                metric.trend === "up" ? "text-mint-dim" : "text-negative",
              )}
            >
              {metric.trendLabel}
            </p>
          )}

          {metric.subValue && (
            <p className="mt-1 text-[11px] leading-snug text-text-muted">
              {metric.subValue}
            </p>
          )}
        </div>

        {isBalance && <MiniSparkline data={BALANCE_SPARKLINE} />}
      </div>
    </Card>
  );
}
