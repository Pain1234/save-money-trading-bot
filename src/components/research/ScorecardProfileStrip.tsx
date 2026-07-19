import Link from "next/link";

import { Badge, Card } from "@/components/ui/Card";
import type { ScorecardProfileViewModel } from "@/lib/research/scorecard-binding";
import type { ExecutiveTone } from "@/lib/research/executive-summary";
import { displayValue } from "@/lib/research-api/client";
import { cn } from "@/lib/utils";

const toneClass: Record<ExecutiveTone, string> = {
  mint: "text-mint",
  danger: "text-negative",
  warning: "text-warning",
  muted: "text-text-muted",
};

function ProfileCell({
  id,
  label,
  value,
  detail,
  tone,
}: {
  id: string;
  label: string;
  value: string;
  detail: string | null;
  tone: ExecutiveTone;
}) {
  return (
    <div
      className="min-w-0 rounded-sm border border-border bg-bg-base/40 px-2.5 py-2"
      data-testid={`scorecard-cell-${id}`}
    >
      <p className="text-[10px] uppercase tracking-[0.06em] text-text-muted">
        {label}
      </p>
      <p
        className={cn(
          "mt-1 font-mono text-[13px] font-semibold uppercase tracking-tight",
          toneClass[tone],
        )}
        data-testid={`scorecard-value-${id}`}
      >
        {value}
      </p>
      {detail ? (
        <p className="mt-1 line-clamp-2 text-[11px] leading-snug text-text-secondary">
          {detail}
        </p>
      ) : null}
    </div>
  );
}

interface ScorecardProfileStripProps {
  profile: ScorecardProfileViewModel;
}

/** Global evidence profile from #291 scorecard API (#292). Read-only. */
export function ScorecardProfileStrip({ profile }: ScorecardProfileStripProps) {
  return (
    <Card
      padding="sm"
      className="space-y-3"
      data-testid="scorecard-profile-strip"
    >
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h2 className="text-[13px] font-semibold text-text-primary">
            Scorecard Evidence Profile
          </h2>
          <p className="mt-0.5 text-[11px] text-text-muted">
            Layer-5 global_profile — keine erfundenen Scores, keine
            Promotion-Aktionen. FAIL / Low Confidence bleiben sichtbar.
          </p>
        </div>
        <Badge variant="neutral">read-only</Badge>
      </div>

      <div
        className="rounded-sm border border-border-subtle bg-bg-base/30 px-2.5 py-1.5 text-[11px] text-text-secondary"
        data-testid="scorecard-identity"
      >
        <span className="font-mono text-mint">{profile.scorecardId}</span>
        <span className="text-text-muted">
          {" "}
          · status={displayValue(profile.status)} · policy=
          {displayValue(profile.policyVersion)} ·{" "}
        </span>
        <Link
          href={`/dashboard/research/experiments/${encodeURIComponent(profile.experimentId)}`}
          className="font-mono text-mint hover:underline"
        >
          {profile.experimentId}
        </Link>
        <span className="text-text-muted">
          {" "}
          / {displayValue(profile.runId)}
        </span>
        {profile.evidenceIntegrityOk === false ? (
          <span className="ml-2 text-warning">· evidence_integrity fail</span>
        ) : null}
      </div>

      {profile.warnings.length > 0 ? (
        <ul
          className="space-y-1 rounded-sm border border-warning/40 bg-warning/10 px-2.5 py-2 text-[11px] text-warning"
          data-testid="scorecard-warnings"
        >
          {profile.warnings.map((warning) => (
            <li key={warning}>{warning}</li>
          ))}
        </ul>
      ) : null}

      <div
        className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5"
        role="list"
        aria-label="Scorecard Evidence Profile"
      >
        {profile.cells.map((cell) => (
          <ProfileCell key={cell.id} {...cell} />
        ))}
      </div>
    </Card>
  );
}
