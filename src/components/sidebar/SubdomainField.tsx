import { Card } from "@/components/ui/Card";
import { Lock } from "lucide-react";

export function SubdomainField() {
  return (
    <Card padding="xs">
      <h3 className="mb-2 text-[12px] font-semibold tracking-wide text-text-primary">
        Subdomain Konzept
      </h3>
      <div className="flex items-center gap-2 rounded-md border border-border bg-bg-card-alt px-2.5 py-1.5">
        <Lock className="h-3.5 w-3.5 shrink-0 text-mint-dim" strokeWidth={2.25} />
        <span className="font-mono text-[11px] text-text-secondary">
          bot.save-money.xyz
        </span>
      </div>
      <p className="mt-1.5 text-[11px] leading-relaxed text-text-muted">
        Isolierte Trading-Oberfläche, getrennt vom Budget-Planer.
      </p>
    </Card>
  );
}
