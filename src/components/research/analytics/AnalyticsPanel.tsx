import { Card } from "@/components/ui/Card";
import { UNAVAILABLE } from "@/lib/research/labels";
import { cn } from "@/lib/utils";

interface AnalyticsPanelProps {
  id: string;
  title: string;
  subtitle?: string;
  children?: React.ReactNode;
  /** When true, ignore children and show an honest empty state. */
  unavailable?: boolean;
  unavailableReason?: string;
  /**
   * Compact empty chrome — no large reserved chart height (#358 Overview).
   * Real data panels keep normal height via children.
   */
  compactEmpty?: boolean;
  /** Optional detail link when empty (Study / Experiment). */
  detailHref?: string | null;
  detailLinkLabel?: string | null;
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
  compactEmpty = false,
  detailHref = null,
  detailLinkLabel = null,
  className,
}: AnalyticsPanelProps) {
  const compact = unavailable && compactEmpty;
  return (
    <Card
      padding="sm"
      className={cn(
        "space-y-2",
        compact ? "min-h-0" : "min-h-[140px]",
        className,
      )}
      data-testid={`analytics-panel-${id}`}
      data-compact-empty={compact ? "true" : undefined}
    >
      <div>
        <h3 className="text-[12px] font-semibold text-text-primary">{title}</h3>
        {subtitle ? (
          <p className="mt-0.5 text-[12px] leading-snug text-text-secondary">
            {subtitle}
          </p>
        ) : null}
      </div>
      {unavailable ? (
        <div className="space-y-1.5">
          <p
            className="text-[12px] leading-snug text-text-secondary"
            data-testid={`analytics-unavailable-${id}`}
          >
            {unavailableReason ?? UNAVAILABLE}
          </p>
          {detailHref ? (
            <a
              href={detailHref}
              className="inline-block text-[12px] text-mint hover:underline"
              data-testid={`analytics-detail-link-${id}`}
            >
              {detailLinkLabel ?? "Details →"}
            </a>
          ) : null}
        </div>
      ) : (
        children
      )}
    </Card>
  );
}
