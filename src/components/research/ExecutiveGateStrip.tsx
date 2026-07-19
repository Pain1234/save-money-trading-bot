import Link from "next/link";

import { CopyableResearchId } from "@/components/research/CopyableResearchId";
import { Badge, Card } from "@/components/ui/Card";
import type {
  ExecutiveCell,
  ExecutiveSummary,
  ExecutiveTone,
} from "@/lib/research/executive-summary";
import { SCORECARD_PIN_STATUS } from "@/lib/research/scorecard-binding";
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
      <p className="text-[11px] uppercase tracking-[0.06em] text-text-secondary">
        {cell.label}
      </p>
      <p
        className={cn(
          "mt-1 font-mono text-[14px] font-semibold uppercase tracking-tight",
          toneClass[cell.tone],
        )}
        data-testid={`executive-value-${cell.id}`}
      >
        {cell.value}
      </p>
      {cell.detail ? (
        <p className="mt-1 line-clamp-3 text-[12px] leading-snug text-text-secondary">
          {cell.detail}
        </p>
      ) : null}
    </>
  );

  return (
    <div
      className="min-w-0 rounded-sm border border-border bg-bg-base/40 px-2.5 py-2.5"
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

/** Gate-first executive strip for Research Overview (#299 / #358). */
export function ExecutiveGateStrip({ summary }: ExecutiveGateStripProps) {
  const pinReady = summary.pin.status === SCORECARD_PIN_STATUS.READY;

  return (
    <Card
      padding="sm"
      data-testid="executive-gate-strip"
      className="space-y-3"
    >
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <h2 className="text-[13px] font-semibold text-text-primary">
            Executive Gates
          </h2>
          <p className="mt-0.5 text-[12px] leading-snug text-text-secondary">
            Integrity → Critical Gates → Evidence → Decision. Alle gebundenen
            Zellen teilen eine Validation-Study-Evidence-Identität. Scorecard
            nur über sealed Pin.
          </p>
        </div>
        <div className="flex flex-wrap gap-1.5">
          <Badge variant={pinReady ? "mint" : "warning"}>
            pin={summary.pin.status}
          </Badge>
          <Badge variant="neutral">gate-first</Badge>
        </div>
      </div>

      {!pinReady ? (
        <div
          className="rounded-sm border border-warning/40 bg-warning/10 px-2.5 py-2 text-[12px] leading-snug text-warning"
          data-testid="executive-pin-legacy"
        >
          <p className="font-medium text-text-primary">
            Keine gepinnte Scorecard für diese Validation Study.
          </p>
          <p className="mt-1 text-text-secondary">{summary.pin.cause}</p>
          <p className="mt-2 flex flex-wrap gap-3">
            {summary.pin.studyHref ? (
              <Link
                href={summary.pin.studyHref}
                className="text-mint hover:underline"
              >
                Validation Study →
              </Link>
            ) : null}
            {summary.pin.experimentHref ? (
              <Link
                href={summary.pin.experimentHref}
                className="text-mint hover:underline"
              >
                Experiment →
              </Link>
            ) : null}
          </p>
        </div>
      ) : null}

      <div
        className="rounded-sm border border-border-subtle bg-bg-base/30 px-2.5 py-2 text-[12px]"
        data-testid="executive-evidence-anchor"
      >
        {summary.evidence ? (
          <div className="flex min-w-0 flex-col gap-1.5 text-text-secondary sm:flex-row sm:flex-wrap sm:items-center">
            <span className="shrink-0 font-medium text-text-primary">
              Evidence-Anker
            </span>
            <CopyableResearchId
              kind="study"
              id={summary.evidence.studyId}
              href={`/dashboard/research/validation/${encodeURIComponent(summary.evidence.studyId)}`}
            />
            <span className="text-text-muted">· {summary.evidence.studyName}</span>
            <span className="text-text-muted">· exp</span>
            <CopyableResearchId
              kind="experiment"
              id={summary.evidence.experimentId}
              href={`/dashboard/research/experiments/${encodeURIComponent(summary.evidence.experimentId)}`}
            />
            {summary.evidence.runId ? (
              <>
                <span className="text-text-muted">· run</span>
                <CopyableResearchId kind="run" id={summary.evidence.runId} />
              </>
            ) : null}
            {summary.evidence.scorecardId ? (
              <>
                <span className="text-text-muted">· sc</span>
                <CopyableResearchId
                  kind="scorecard"
                  id={summary.evidence.scorecardId}
                />
              </>
            ) : null}
          </div>
        ) : (
          <p className="text-text-secondary">
            Evidence-Anker: Nicht verfügbar — kein Validation Study; Gate,
            Decision und Strategy werden nicht gemischt.
          </p>
        )}
      </div>

      <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
        {summary.cells.map((cell) => (
          <Cell key={cell.id} cell={cell} />
        ))}
      </div>

      <div
        className="grid gap-2 border-t border-border-subtle pt-2 sm:grid-cols-2 lg:grid-cols-3"
        data-testid="executive-strategy-meta"
      >
        <div>
          <p className="text-[11px] uppercase tracking-[0.06em] text-text-secondary">
            Strategy
          </p>
          <p
            className="mt-0.5 font-mono text-[13px] font-medium text-text-primary"
            data-testid="executive-strategy-id"
          >
            {displayValue(summary.strategyId)}
          </p>
        </div>
        <div>
          <p className="text-[11px] uppercase tracking-[0.06em] text-text-secondary">
            Strategy Version
          </p>
          <p
            className="mt-0.5 font-mono text-[13px] font-medium text-text-primary"
            data-testid="executive-strategy-version"
          >
            {displayValue(summary.strategyVersion)}
          </p>
        </div>
        <div>
          <p className="text-[11px] uppercase tracking-[0.06em] text-text-secondary">
            Freeze Metadata
          </p>
          <p
            className={cn(
              "mt-0.5 font-mono text-[13px]",
              toneClass.muted,
            )}
            data-testid="executive-freeze-value"
          >
            {summary.freezeLabel}
          </p>
          <p className="mt-0.5 text-[12px] leading-snug text-text-secondary">
            {summary.freezeDetail}
          </p>
        </div>
      </div>

      <ul className="flex flex-wrap gap-x-3 gap-y-1 text-[11px] text-text-muted">
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
