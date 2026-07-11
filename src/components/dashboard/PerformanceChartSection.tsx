"use client";

import { Card } from "@/components/ui/Card";
import dynamic from "next/dynamic";

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

export function PerformanceChartSection() {
  return <PerformanceChart />;
}
