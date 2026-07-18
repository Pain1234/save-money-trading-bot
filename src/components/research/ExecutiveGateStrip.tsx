import Link from "next/link";

import { Badge, Card } from "@/components/ui/Card";
import type {
  ExecutiveCell,
  ExecutiveSummary,
  ExecutiveTone,
} from "@/lib/research/executive-summary";
import { displayValue } from "@/lib/research-api/client";
import { cn } from "@/lib/utils";

const toneClass: Record<ExecutiveTone, string> = {
  mint: "text-mint",
  danger: "text-negative",
  warning: "text-warning",
  muted: "text-text-muted",
};

const toneBadge: Record<
  ExecutiveTone,
  "mint" | "negative" | "warning" | "neutral"
> = {
  mint: "mint",
  danger: "negative",
  warning: "warning",
  muted: "neutral",
};

function Cell({ cell }: { cell: ExecutiveCell }) {
  const body = (
    <>
      <p className="text-[10px] uppercase tracking-[0.06em] text-text-muted">
        {cell.label}
      </p>
      <p
        className={cn(
          "mt-1 font-mono text-[13px] font-semibold uppercase tracking-tight",
          toneClass[cell.tone],
        )}
        data-testid={`executive-value-${cell.id}`}
      >
        {cell.value}
      </p>
      {cell.detail ? (
        <p className="mt-1 line-clamp-2 text-[11px] leading-snug text-text-secondary">
          {cell.detail}
        </p>
      ) : null}
    </>
  );

  return (
    <div
      className="min-w-0 rounded-sm border border-border bg-bg-base/40 px-2.5 py-2"
      data-testid={`executive-cell-${cell.id}`}
    >
      {cell.href ? (
        <Link
          href={cell.href}
          className="block transition-colors hover:border-mint/30"
        >
          {body}
        </Link>
      ) : (
        body
      )}
    </div>
  );
}

interface ExecutiveGateStripProps {
  summary: ExecutiveSummary;
}

/** Gate-first executive strip for Research Overview (#299). */
export function ExecutiveGateStrip({ summary }: ExecutiveGateStripProps) {
  return (
    <Card
      padding="sm"
      data-testid="executive-gate-strip"
      className="space-y-3"
    >
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h2 className="text-[13px] font-semibold text-text-primary">
            Executive Gates
          </h2>
          <p className="mt-0.5 text-[11px] text-text-muted">
            Integrity → Critical Gates → Evidence → Decision. Fehlende
            Scorecard-Felder bleiben ehrlich „Nicht verfügbar“ — keine
            erfundenen Metriken.
          </p>
        </div>
        <Badge variant="neutral">gate-first</Badge>
      </div>

      <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4 xl:grid-cols-7">
        {summary.cells.map((cell) => (
          <Cell key={cell.id} cell={cell} />
        ))}
      </div>

      <div
        className="grid gap-2 border-t border-border-subtle pt-2 sm:grid-cols-2 lg:grid-cols-3"
        data-testid="executive-strategy-meta"
      >
        <div>
          <p className="text-[10px] uppercase tracking-[0.06em] text-text-muted">
            Strategy
          </p>
          <p className="mt-0.5 font-mono text-[12px] text-text-primary">
            {displayValue(summary.strategyId)}
          </p>
        </div>
        <div>
          <p className="text-[10px] uppercase tracking-[0.06em] text-text-muted">
            Strategy Version
          </p>
          <p className="mt-0.5 font-mono text-[12px] text-text-primary">
            {displayValue(summary.strategyVersion)}
          </p>
        </div>
        <div>
          <p className="text-[10px] uppercase tracking-[0.06em] text-text-muted">
            Freeze Metadata
          </p>
          <p
            className={cn(
              "mt-0.5 font-mono text-[12px]",
              toneClass.muted,
            )}
            data-testid="executive-freeze-value"
          >
            {summary.freezeLabel}
          </p>
          <p className="mt-0.5 text-[11px] text-text-secondary">
            {summary.freezeDetail}
          </p>
        </div>
      </div>

      <ul className="flex flex-wrap gap-x-3 gap-y-1 text-[10px] text-text-muted">
        {summary.cells.map((cell) => (
          <li key={`src-${cell.id}`}>
            <Badge variant={toneBadge[cell.tone]} className="normal-case tracking-normal">
              {cell.label}
            </Badge>{" "}
            <span className="font-mono">{cell.source}</span>
          </li>
        ))}
      </ul>
    </Card>
  );
}
