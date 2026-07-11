import { CONCEPT_LAYERS } from "@/lib/mock-data";
import { Card } from "@/components/ui/Card";
import { BarChart3, Gauge, Shield, TrendingUp } from "lucide-react";

const iconMap = {
  trend: TrendingUp,
  confirmation: BarChart3,
  risk: Shield,
  regime: Gauge,
};

export function ConceptLayers() {
  return (
    <Card padding="xs">
      <h3 className="mb-2 text-[12px] font-semibold tracking-wide text-text-primary">
        Konzept in 4 Schichten
      </h3>
      <div className="space-y-2">
        {CONCEPT_LAYERS.map((layer, i) => {
          const Icon = iconMap[layer.icon];
          return (
            <div key={layer.id} className="flex items-start gap-2.5">
              <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md border border-mint/20 bg-mint/12 text-mint shadow-[0_0_12px_rgb(66_217_139_/_0.12)]">
                <Icon className="h-3.5 w-3.5" strokeWidth={2.25} />
              </div>
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-1.5">
                  <span className="text-[10px] font-semibold text-mint-dim">
                    {i + 1}
                  </span>
                  <p className="text-[12px] font-medium text-text-primary">
                    {layer.title}
                  </p>
                </div>
                <p className="mt-0.5 text-[11px] leading-snug text-text-muted">
                  {layer.description}
                </p>
              </div>
            </div>
          );
        })}
      </div>
    </Card>
  );
}
