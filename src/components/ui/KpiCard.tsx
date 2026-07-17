import { cn } from "@/lib/utils";
import type { KpiMetric } from "@/types";
import { Card } from "./Card";

interface KpiCardProps {
  metric: KpiMetric;
}

export function KpiCard({ metric }: KpiCardProps) {
  const isStatus = metric.id === "status";

  return (
    <Card padding="sm" className="kpi-panel flex min-w-0 flex-col justify-between">
      <span className="text-[11px] uppercase tracking-[0.05em] text-text-muted">
        {metric.label}
      </span>

      <div className="flex items-end justify-between gap-2">
        <div className="min-w-0 flex-1">
          {isStatus ? (
            <p
              className={cn(
                "text-[24px] font-medium leading-none tracking-tight",
                metric.accent === "warning"
                  ? "text-warning"
                  : metric.accent === "danger"
                    ? "text-negative"
                    : "text-mint",
              )}
            >
              {metric.value}
            </p>
          ) : (
            <p
              className={cn(
                "font-mono text-[24px] leading-none tracking-tight",
                metric.accent === "mint"
                  ? "text-mint"
                  : metric.accent === "danger"
                    ? "text-negative"
                    : "text-text-primary",
              )}
              data-testid={metric.id === "pnl" ? "kpi-pnl" : undefined}
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
      </div>
    </Card>
  );
}
