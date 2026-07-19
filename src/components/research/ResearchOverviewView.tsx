import Link from "next/link";

import { ResearchAnalyticsSection } from "@/components/research/analytics/ResearchAnalyticsSection";
import { ExecutiveGateStrip } from "@/components/research/ExecutiveGateStrip";
import { Card } from "@/components/ui/Card";
import { KpiCard } from "@/components/ui/KpiCard";
import {
  buildExecutiveSummary,
  filterJobsForEvidence,
} from "@/lib/research/executive-summary";
import {
  mapCostStressFromDetail,
  mapRegimeRowsFromDetail,
  mapTransitionFromDetail,
} from "@/lib/research/scorecard-detail-binding";
import {
  buildScorecardProfileView,
  SCORECARD_PIN_STATUS,
  type ScorecardBindState,
} from "@/lib/research/scorecard-binding";
import {
  displayValue,
  type GateRunRecord,
  type ResearchExperimentSummary,
  type ResearchOverview,
  type ResearchSeriesPoint,
  type RobustnessJobSummary,
  type ValidationStudyDetail,
} from "@/lib/research-api/client";
import type { KpiMetric } from "@/types";

function recentRows(items: ResearchExperimentSummary[]) {
  return items.map((item) => ({
    "Experiment-ID": item.experiment_id,
    Strategie: displayValue(item.strategy_version),
    Status: displayValue(item.status),
    Erstellt: displayValue(item.created_at),
    "Net PnL": displayValue(item.net_pnl),
    Integrity: item.integrity_ok ? "ok" : "fail",
  }));
}

export interface ResearchOverviewViewProps {
  overview: ResearchOverview;
  gateRuns: GateRunRecord[];
  studies: ValidationStudyDetail[];
  robustnessJobs: RobustnessJobSummary[];
  /** Sealed pin bind for evidence study — never registry latest (#358). */
  scorecardBind?: ScorecardBindState | null;
  /** Equity for evidence-pinned experiment — optional existing API series. */
  pinnedEquity?: ResearchSeriesPoint[] | null;
  pinnedDrawdown?: ResearchSeriesPoint[] | null;
}

export function ResearchOverviewView({
  overview,
  gateRuns,
  studies,
  robustnessJobs,
  scorecardBind = null,
  pinnedEquity = null,
  pinnedDrawdown = null,
}: ResearchOverviewViewProps) {
  const executive = buildExecutiveSummary({
    overview,
    gateRuns,
    studies,
    robustnessJobs,
    scorecardBind,
  });

  const costJobs = executive.evidence
    ? filterJobsForEvidence(
        robustnessJobs,
        executive.evidence,
        "cost_stress",
      )
    : [];
  const costInventory =
    costJobs.length > 0
      ? `${costJobs.length} gepinnte cost_stress-Jobs`
      : null;

  const pinReady =
    scorecardBind?.kind === "ready" &&
    executive.pin.status === SCORECARD_PIN_STATUS.READY;

  const profile =
    pinReady && scorecardBind?.kind === "ready"
      ? buildScorecardProfileView(scorecardBind.scorecard)
      : null;
  const detail =
    pinReady && scorecardBind?.kind === "ready" ? scorecardBind.detail : null;
  const regimeRows = mapRegimeRowsFromDetail(detail);
  const costStressBound = detail
    ? mapCostStressFromDetail(detail.cost_stress)
    : null;
  const transition = mapTransitionFromDetail(detail);
  const regimeReason =
    pinReady && scorecardBind?.kind === "ready" && scorecardBind.detailError
      ? `Scorecard-Detail-Fehler — Regime-Zeilen Nicht verfügbar (${scorecardBind.detailError})`
      : pinReady && regimeRows.length === 0
        ? "Keine regime_rows im Scorecard-Detail (sealed regime_metrics fehlen oder leer)"
        : undefined;

  const empty = overview.experiment_count === 0;

  const kpis: KpiMetric[] = [
    {
      id: "exp-count",
      label: "Experimente",
      value: String(overview.experiment_count),
    },
    {
      id: "exp-complete",
      label: "Abgeschlossen",
      value: String(overview.completed_count),
      accent: "mint",
    },
    {
      id: "exp-failed",
      label: "Fehlgeschlagen",
      value: String(overview.failed_count),
      accent: overview.failed_count > 0 ? "danger" : undefined,
    },
    {
      id: "exp-running",
      label: "Laufend",
      value: overview.running_available
        ? String(overview.running_count ?? 0)
        : "Nicht verfügbar",
    },
    {
      id: "strategies",
      label: "Strategie-Versionen",
      value: String(overview.strategy_version_count),
    },
  ];

  const statusRows = Object.entries(overview.status_distribution).map(
    ([status, count]) => ({
      Status: status,
      Anzahl: count,
    }),
  );

  return (
    <div
      data-testid={empty ? "research-overview-empty" : "research-overview-ready"}
      data-pin-status={executive.pin.status}
      className="space-y-3"
    >
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="min-w-0">
          <h1 className="text-[18px] font-semibold tracking-tight text-text-primary">
            Research Overview
          </h1>
          <p className="mt-1 max-w-3xl text-[12px] leading-relaxed text-text-secondary">
            Gate-first Evidence-Konsole. Scorecard-Felder nur über Validation
            Study → Primary Run → sealed Pin (scorecard_id + evidence_content_hash).
            Kein Latest-Fallback, Keine Auto-Promotion.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Link
            href="/dashboard/research/experiments/new"
            className="rounded-sm bg-mint/20 px-2.5 py-1 text-[12px] text-mint"
            data-testid="new-experiment-button"
          >
            Neues Experiment
          </Link>
          <Link
            href="/dashboard/research/validation"
            className="rounded-sm border border-border px-2.5 py-1 text-[12px] text-text-secondary hover:text-text-primary"
          >
            Validation →
          </Link>
          <Link
            href="/dashboard/research/experiments"
            className="rounded-sm border border-border px-2.5 py-1 text-[12px] text-text-secondary hover:text-text-primary"
          >
            Experimente →
          </Link>
        </div>
      </div>

      <ExecutiveGateStrip summary={executive} />

      <ResearchAnalyticsSection
        evidence={executive.evidence}
        equity={pinnedEquity}
        drawdown={pinnedDrawdown}
        costStressInventoryDetail={costInventory}
        costStressBound={costStressBound}
        confidenceLabel={profile?.confidenceLabel ?? null}
        parameterClassification={profile?.parameterClassification ?? null}
        parameterDetail={profile?.parameterDetail ?? null}
        transitionRiskLabel={
          transition.riskLabel ?? profile?.transitionRiskLabel ?? null
        }
        transitionDetail={
          transition.detail ?? profile?.transitionDetail ?? null
        }
        classifierTransitions={transition.transitions}
        classifierTransitionsReason={transition.transitionsReason}
        regimeRows={regimeRows}
        regimeTableReason={regimeReason}
        pin={executive.pin}
      />

      {empty ? (
        <p className="text-[12px] text-text-secondary">
          Keine Experimente in der Registry. Strategy Lab starten — fehlende
          Scorecard-Felder bleiben sichtbar als „Nicht verfügbar“.
        </p>
      ) : (
        <>
          <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-5">
            {kpis.map((metric) => (
              <KpiCard key={metric.id} metric={metric} />
            ))}
          </div>

          <div className="grid gap-2 lg:grid-cols-2">
            <Card padding="sm">
              <h2 className="mb-2 text-[13px] font-medium text-text-primary">
                Status-Verteilung
              </h2>
              {statusRows.length === 0 ? (
                <p className="text-[12px] text-text-secondary">Keine Statusdaten</p>
              ) : (
                <table className="min-w-full text-left text-[12px]">
                  <thead className="text-text-secondary">
                    <tr>
                      <th className="py-1.5 pr-3 font-medium">Status</th>
                      <th className="py-1.5 font-medium">Anzahl</th>
                    </tr>
                  </thead>
                  <tbody>
                    {statusRows.map((row) => (
                      <tr
                        key={row.Status}
                        className="border-t border-border-subtle"
                      >
                        <td className="py-2 pr-3">{row.Status}</td>
                        <td className="py-2 font-mono">{row.Anzahl}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </Card>

            <Card padding="sm">
              <h2 className="mb-2 text-[13px] font-medium text-text-primary">
                Registry: noch nicht verfügbar
              </h2>
              <ul className="space-y-1 text-[12px] text-text-secondary">
                {Object.entries(overview.unavailable).map(([key, label]) => (
                  <li key={key}>
                    <span className="text-text-primary">{key}</span>: {label}
                  </li>
                ))}
              </ul>
              {overview.known_strategy_ids.length > 0 ? (
                <p className="mt-3 text-[12px] text-text-secondary">
                  Bekannte Strategy-IDs:{" "}
                  <span className="font-mono">
                    {overview.known_strategy_ids.join(", ")}
                  </span>
                </p>
              ) : null}
            </Card>
          </div>

          <Card padding="sm">
            <h2 className="mb-2 text-[13px] font-medium text-text-primary">
              Letzte Experimente
            </h2>
            <div className="overflow-x-auto">
              <table className="min-w-full text-left text-[12px]">
                <thead className="text-text-secondary">
                  <tr>
                    {[
                      "Experiment-ID",
                      "Strategie",
                      "Status",
                      "Integrity",
                      "Erstellt",
                      "Net PnL",
                    ].map((col) => (
                      <th key={col} className="px-2 py-1.5 font-medium">
                        {col}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {recentRows(overview.recent_experiments).map((row) => (
                    <tr
                      key={row["Experiment-ID"]}
                      className="border-t border-border-subtle"
                    >
                      <td className="px-2 py-2">
                        <Link
                          href={`/dashboard/research/experiments/${encodeURIComponent(row["Experiment-ID"])}`}
                          className="font-mono text-mint hover:underline"
                        >
                          {row["Experiment-ID"]}
                        </Link>
                      </td>
                      <td className="px-2 py-2">{row.Strategie}</td>
                      <td className="px-2 py-2 font-medium">{row.Status}</td>
                      <td className="px-2 py-2 font-mono">{row.Integrity}</td>
                      <td className="px-2 py-2 font-mono text-[12px]">
                        {row.Erstellt}
                      </td>
                      <td className="px-2 py-2 font-mono">
                        {row["Net PnL"]}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        </>
      )}
    </div>
  );
}
