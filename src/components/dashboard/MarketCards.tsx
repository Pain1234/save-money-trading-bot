import { Card } from "@/components/ui/Card";
import type { StatusCardVm } from "@/lib/dashboard/types";
import { cn } from "@/lib/utils";

const toneClass: Record<StatusCardVm["tone"], string> = {
  ok: "text-mint",
  warn: "text-warning",
  danger: "text-negative",
  neutral: "text-text-primary",
};

interface MarketCardsProps {
  cards: StatusCardVm[];
  errorMessage?: string | null;
}

/** Status / readiness / scheduler / incidents — replaces mock market gauges. */
export function MarketCards({ cards, errorMessage = null }: MarketCardsProps) {
  if (errorMessage) {
    return (
      <div
        className="chart-panel market-stack flex min-w-0"
        data-testid="status-cards-error"
      >
        <Card padding="sm" className="flex min-w-0 flex-1 flex-col justify-center">
          <p className="text-[12px] text-negative">{errorMessage}</p>
        </Card>
      </div>
    );
  }

  return (
    <div
      className="chart-panel market-stack flex min-w-0"
      data-testid="status-cards"
    >
      {cards.map((card) => (
        <Card
          key={card.id}
          padding="sm"
          className="flex min-w-0 flex-1 flex-col justify-center"
        >
          <p className="text-[11px] uppercase tracking-[0.05em] text-text-muted">
            {card.label}
          </p>
          <p
            className={cn(
              "mt-1 text-[14px] font-medium leading-none",
              toneClass[card.tone],
            )}
          >
            {card.value}
          </p>
          <p className="mt-1 text-[11px] leading-snug text-text-muted">
            {card.detail}
          </p>
        </Card>
      ))}
    </div>
  );
}
