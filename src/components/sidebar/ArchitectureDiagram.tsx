import { ARCHITECTURE_FLOW } from "@/lib/mock-data";
import { Card } from "@/components/ui/Card";
import {
  ArrowRight,
  Database,
  LayoutDashboard,
  Shield,
  Workflow,
  Zap,
} from "lucide-react";
import type { ElementType } from "react";

const nodeIcons: Record<string, ElementType> = {
  data: Database,
  strategy: Workflow,
  risk: Shield,
  execution: Zap,
  dashboard: LayoutDashboard,
};

export function ArchitectureDiagram() {
  const topRow = ARCHITECTURE_FLOW.slice(0, 4);
  const bottomNode = ARCHITECTURE_FLOW[4];

  return (
    <Card padding="xs">
      <h3 className="mb-2 text-[12px] font-semibold tracking-wide text-text-primary">
        System Architektur
      </h3>

      <div className="space-y-2.5">
        <div className="flex items-center gap-1">
          {topRow.map((node, i) => {
            const Icon = nodeIcons[node.id] ?? Database;
            return (
              <div key={node.id} className="flex min-w-0 flex-1 items-center gap-1">
                <div className="flex min-w-0 flex-1 flex-col items-center rounded-md border border-border bg-bg-card-alt px-1 py-2 shadow-[inset_0_1px_0_rgb(255_255_255_/_0.04)]">
                  <div className="mb-1 flex h-6 w-6 items-center justify-center rounded border border-mint/15 bg-mint/10">
                    <Icon className="h-3.5 w-3.5 text-mint" strokeWidth={2.25} />
                  </div>
                  <p className="w-full truncate text-center text-[9px] leading-tight text-text-secondary">
                    {node.label}
                  </p>
                </div>
                {i < topRow.length - 1 && (
                  <ArrowRight className="h-3 w-3 shrink-0 text-mint-dim/80" strokeWidth={2} />
                )}
              </div>
            );
          })}
        </div>

        <div className="mx-auto h-px w-[55%] bg-gradient-to-r from-transparent via-border to-transparent" />

        {bottomNode && (
          <div className="flex justify-center">
            <div className="flex w-[48%] flex-col items-center rounded-md border border-mint/25 bg-mint-glow px-2 py-2 shadow-[0_0_16px_rgb(66_217_139_/_0.08)]">
              <div className="mb-1 flex h-6 w-6 items-center justify-center rounded border border-mint/20 bg-mint/12">
                <LayoutDashboard className="h-3.5 w-3.5 text-mint" strokeWidth={2.25} />
              </div>
              <p className="text-[10px] font-medium text-text-primary">{bottomNode.label}</p>
            </div>
          </div>
        )}
      </div>
    </Card>
  );
}
