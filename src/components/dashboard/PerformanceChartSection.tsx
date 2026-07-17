"use client";

import { Card } from "@/components/ui/Card";
import dynamic from "next/dynamic";
import type { EquityChartPointVm } from "@/lib/dashboard/types";

function PerformanceChartSkeleton() {
  return (
    <Card padding="sm" className="chart-panel flex min-w-0 flex-col" aria-hidden>
      <div className="mb-1.5 h-8" />
      <div className="min-h-0 flex-1 rounded bg-white/[0.02]" />
    </Card>
  );
}

const PerformanceChart = dynamic(
  () =>
    import("@/components/dashboard/PerformanceChart").then(
      (mod) => mod.PerformanceChart,
    ),
  { ssr: false, loading: PerformanceChartSkeleton },
);

interface PerformanceChartSectionProps {
  points: EquityChartPointVm[];
  emptyMessage?: string;
  errorMessage?: string | null;
}

export function PerformanceChartSection({
  points,
  emptyMessage,
  errorMessage,
}: PerformanceChartSectionProps) {
  return (
    <PerformanceChart
      points={points}
      emptyMessage={emptyMessage}
      errorMessage={errorMessage}
    />
  );
}
