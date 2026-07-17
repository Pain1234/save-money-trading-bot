import { Card } from "@/components/ui/Card";
import { KpiCard } from "@/components/ui/KpiCard";
import {
  displayValue,
  fetchResearchOverview,
  getResearchErrorMessage,
  type ResearchExperimentSummary,
} from "@/lib/research-api/client";
import type { KpiMetric } from "@/types";
import Link from "next/link";

export const dynamic = "force-dynamic";

function recentRows(items: ResearchExperimentSummary[]) {
  return items.map((item) => ({
    "Experiment-ID": item.experiment_id,
    Strategie: displayValue(item.strategy_version),
    Status: displayValue(item.status),
    Erstellt: displayValue(item.created_at),
    "Net PnL": displayValue(item.net_pnl),
  }));
}

export default async function ResearchOverviewPage() {
  try {
    const overview = await fetchResearchOverview();

    if (overview.experiment_count === 0) {
      return (
        <div data-testid="research-overview-empty" className="space-y-4">
          <h1 className="text-2xl font-semibold">Research Overview</h1>
          <p className="text-sm text-text-muted">
            Keine Experimente in der Registry. Führen Sie Research-Runs über die
            CLI aus — diese Ansicht zeigt nur echte Registry-Daten.
          </p>
        </div>
      );
    }

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
          : "Noch nicht verfügbar",
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
      <div data-testid="research-overview-ready" className="space-y-4">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h1 className="text-2xl font-semibold">Research Overview</h1>
            <p className="mt-1 text-sm text-text-secondary">
              Daten aus ExperimentRegistry und Run-Artefakten.
            </p>
          </div>
          <Link
            href="/dashboard/research/experiments"
            className="text-sm text-mint hover:underline"
          >
            Alle Experimente →
          </Link>
        </div>

        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
          {kpis.map((metric) => (
            <KpiCard key={metric.id} metric={metric} />
          ))}
        </div>

        <div className="grid gap-3 lg:grid-cols-2">
          <Card padding="sm">
            <h2 className="mb-2 text-sm font-medium text-text-primary">
              Status-Verteilung
            </h2>
            {statusRows.length === 0 ? (
              <p className="text-sm text-text-muted">Keine Statusdaten</p>
            ) : (
              <table className="min-w-full text-left text-sm">
                <thead className="text-text-muted">
                  <tr>
                    <th className="py-1 pr-3 font-medium">Status</th>
                    <th className="py-1 font-medium">Anzahl</th>
                  </tr>
                </thead>
                <tbody>
                  {statusRows.map((row) => (
                    <tr key={row.Status} className="border-t border-border-subtle">
                      <td className="py-1.5 pr-3">{row.Status}</td>
                      <td className="py-1.5 font-mono">{row.Anzahl}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </Card>

          <Card padding="sm">
            <h2 className="mb-2 text-sm font-medium text-text-primary">
              Noch nicht verfügbar
            </h2>
            <ul className="space-y-1 text-sm text-text-muted">
              {Object.entries(overview.unavailable).map(([key, label]) => (
                <li key={key}>
                  <span className="text-text-secondary">{key}</span>: {label}
                </li>
              ))}
            </ul>
            {overview.known_strategy_ids.length > 0 && (
              <p className="mt-3 text-xs text-text-muted">
                Bekannte Strategy-IDs:{" "}
                {overview.known_strategy_ids.join(", ")}
              </p>
            )}
          </Card>
        </div>

        <Card padding="sm">
          <h2 className="mb-3 text-sm font-medium text-text-primary">
            Letzte Experimente
          </h2>
          <div className="overflow-x-auto">
            <table className="min-w-full text-left text-sm">
              <thead className="text-text-muted">
                <tr>
                  {["Experiment-ID", "Strategie", "Status", "Erstellt", "Net PnL"].map(
                    (col) => (
                      <th key={col} className="px-2 py-1 font-medium">
                        {col}
                      </th>
                    ),
                  )}
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
                    <td className="px-2 py-1.5 font-mono text-xs">
                      {row.Erstellt}
                    </td>
                    <td className="px-2 py-1.5 font-mono">{row["Net PnL"]}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      </div>
    );
  } catch (error) {
    return (
      <div
        data-testid="research-overview-error"
        className="rounded-xl border border-red-500/40 bg-red-500/10 p-6"
      >
        <h1 className="text-xl font-semibold text-red-300">Research API Error</h1>
        <p className="mt-2 text-sm text-red-200/90">
          {getResearchErrorMessage(error)}
        </p>
      </div>
    );
  }
}
