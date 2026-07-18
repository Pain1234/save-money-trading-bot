import Link from "next/link";

import { ExecutiveGateStrip } from "@/components/research/ExecutiveGateStrip";
import { Card } from "@/components/ui/Card";
import { KpiCard } from "@/components/ui/KpiCard";
import { buildExecutiveSummary } from "@/lib/research/executive-summary";
import {
  displayValue,
  type GateRunRecord,
  type ResearchExperimentSummary,
  type ResearchOverview,
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

interface ResearchOverviewViewProps {
  overview: ResearchOverview;
  gateRuns: GateRunRecord[];
  studies: ValidationStudyDetail[];
  robustnessJobs: RobustnessJobSummary[];
}

export function ResearchOverviewView({
  overview,
  gateRuns,
  studies,
  robustnessJobs,
}: ResearchOverviewViewProps) {
  const executive = buildExecutiveSummary({
    overview,
    gateRuns,
    studies,
    robustnessJobs,
  });

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
      className="space-y-3"
    >
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-[18px] font-semibold tracking-tight text-text-primary">
            Research Overview
          </h1>
          <p className="mt-1 max-w-3xl text-[12px] leading-relaxed text-text-secondary">
            Gate-first Evidence-Konsole. Registry-Zähler und Listen sind
            sekundär — zuerst Integrity, Critical Gates und menschliche
            Decision. Scorecard-Felder ohne API bleiben „Nicht verfügbar“.
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

      {empty ? (
        <p className="text-[12px] text-text-muted">
          Keine Experimente in der Registry. Strategy Lab starten — fehlende
          Scorecard-Felder bleiben trotzdem sichtbar als „Nicht verfügbar“.
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
              <h2 className="mb-2 text-[12px] font-medium text-text-primary">
                Status-Verteilung
              </h2>
              {statusRows.length === 0 ? (
                <p className="text-[12px] text-text-muted">Keine Statusdaten</p>
              ) : (
                <table className="min-w-full text-left text-[12px]">
                  <thead className="text-text-muted">
                    <tr>
                      <th className="py-1 pr-3 font-medium">Status</th>
                      <th className="py-1 font-medium">Anzahl</th>
                    </tr>
                  </thead>
                  <tbody>
                    {statusRows.map((row) => (
                      <tr
                        key={row.Status}
                        className="border-t border-border-subtle"
                      >
                        <td className="py-1.5 pr-3">{row.Status}</td>
                        <td className="py-1.5 font-mono">{row.Anzahl}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </Card>

            <Card padding="sm">
              <h2 className="mb-2 text-[12px] font-medium text-text-primary">
                Registry: noch nicht verfügbar
              </h2>
              <ul className="space-y-1 text-[12px] text-text-muted">
                {Object.entries(overview.unavailable).map(([key, label]) => (
                  <li key={key}>
                    <span className="text-text-secondary">{key}</span>: {label}
                  </li>
                ))}
              </ul>
              {overview.known_strategy_ids.length > 0 ? (
                <p className="mt-3 text-[11px] text-text-muted">
                  Bekannte Strategy-IDs:{" "}
                  <span className="font-mono">
                    {overview.known_strategy_ids.join(", ")}
                  </span>
                </p>
              ) : null}
            </Card>
          </div>

          <Card padding="sm">
            <h2 className="mb-2 text-[12px] font-medium text-text-primary">
              Letzte Experimente
            </h2>
            <div className="overflow-x-auto">
              <table className="min-w-full text-left text-[12px]">
                <thead className="text-text-muted">
                  <tr>
                    {[
                      "Experiment-ID",
                      "Strategie",
                      "Status",
                      "Integrity",
                      "Erstellt",
                      "Net PnL",
                    ].map((col) => (
                      <th key={col} className="px-2 py-1 font-medium">
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
                      <td className="px-2 py-1.5">
                        <Link
                          href={`/dashboard/research/experiments/${encodeURIComponent(row["Experiment-ID"])}`}
                          className="font-mono text-mint hover:underline"
                        >
                          {row["Experiment-ID"]}
                        </Link>
                      </td>
                      <td className="px-2 py-1.5">{row.Strategie}</td>
                      <td className="px-2 py-1.5">{row.Status}</td>
                      <td className="px-2 py-1.5 font-mono">{row.Integrity}</td>
                      <td className="px-2 py-1.5 font-mono text-[11px]">
                        {row.Erstellt}
                      </td>
                      <td className="px-2 py-1.5 font-mono">
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
