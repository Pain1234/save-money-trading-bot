import { Card } from "@/components/ui/Card";
import { UNAVAILABLE } from "@/lib/research/executive-summary";
import { cn } from "@/lib/utils";

interface AnalyticsPanelProps {
  id: string;
  title: string;
  subtitle?: string;
  children?: React.ReactNode;
  /** When true, ignore children and show an honest empty state. */
  unavailable?: boolean;
  unavailableReason?: string;
  className?: string;
}

/** Dense research analytics panel shell (#300). */
export function AnalyticsPanel({
  id,
  title,
  subtitle,
  children,
  unavailable = false,
  unavailableReason,
  className,
}: AnalyticsPanelProps) {
  return (
    <Card
      padding="sm"
      className={cn("min-h-[140px] space-y-2", className)}
      data-testid={`analytics-panel-${id}`}
    >
      <div>
        <h3 className="text-[12px] font-semibold text-text-primary">{title}</h3>
        {subtitle ? (
          <p className="mt-0.5 text-[11px] text-text-muted">{subtitle}</p>
        ) : null}
      </div>
      {unavailable ? (
        <p
          className="text-[12px] text-text-muted"
          data-testid={`analytics-unavailable-${id}`}
        >
          {unavailableReason ?? UNAVAILABLE}
        </p>
      ) : (
        children
      )}
    </Card>
  );
}
