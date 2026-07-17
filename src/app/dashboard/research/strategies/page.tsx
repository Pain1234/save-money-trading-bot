import { Card } from "@/components/ui/Card";
import { fetchPaperApi } from "@/lib/paper-api/client";
import { getResearchErrorMessage } from "@/lib/research-api/client";
import Link from "next/link";

export const dynamic = "force-dynamic";

interface StrategyListItem {
  strategy_id: string;
  display_name: string;
  description: string;
  strategy_version: string;
  lifecycle_status: string;
  supported_symbols: string[];
  required_timeframes: string[];
  experiment_count: number;
  last_run: {
    experiment_id?: string;
    status?: string;
    created_at?: string;
  } | null;
}

export default async function ResearchStrategiesPage() {
  try {
    const body = await fetchPaperApi<{ items: StrategyListItem[] }>(
      "/api/v1/research/strategies",
      { noStore: true },
    );

    if (!body.items.length) {
      return (
        <div data-testid="research-strategies-empty" className="space-y-4">
          <h1 className="text-2xl font-semibold">Strategien</h1>
          <p className="text-sm text-text-muted">
            Keine Strategien im Resolver-Katalog registriert.
          </p>
        </div>
      );
    }

    return (
      <div data-testid="research-strategies-ready" className="space-y-4">
        <div>
          <h1 className="text-2xl font-semibold">Strategien</h1>
          <p className="mt-1 text-sm text-text-secondary">
            Registrierte Research-Strategien aus dem Strategy Resolver. Sichtbar
            auch ohne ausgeführte Experimente.
          </p>
        </div>

        <div className="grid gap-3">
          {body.items.map((strategy) => (
            <Card
              key={strategy.strategy_id}
              padding="sm"
              className="space-y-3"
              data-testid={`strategy-card-${strategy.strategy_id}`}
            >
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <h2 className="text-lg font-medium text-text-primary">
                    {strategy.display_name}
                  </h2>
                  <p className="mt-1 text-sm text-text-secondary">
                    {strategy.description}
                  </p>
                </div>
                <span className="rounded bg-bg-elevated px-2 py-1 text-xs text-text-muted">
                  {strategy.lifecycle_status}
                </span>
              </div>

              <dl className="grid gap-2 text-sm sm:grid-cols-2 lg:grid-cols-4">
                <div>
                  <dt className="text-text-muted">Version</dt>
                  <dd>{strategy.strategy_version}</dd>
                </div>
                <div>
                  <dt className="text-text-muted">Symbole</dt>
                  <dd>{strategy.supported_symbols.join(", ")}</dd>
                </div>
                <div>
                  <dt className="text-text-muted">Timeframes</dt>
                  <dd>{strategy.required_timeframes.join(", ")}</dd>
                </div>
                <div>
                  <dt className="text-text-muted">Experimente</dt>
                  <dd>{strategy.experiment_count}</dd>
                </div>
              </dl>

              <p className="text-xs text-text-muted">
                Letzter Run:{" "}
                {strategy.last_run?.created_at
                  ? `${strategy.last_run.status ?? "—"} · ${strategy.last_run.created_at}`
                  : "Noch kein Run"}
              </p>

              <div className="flex flex-wrap gap-3">
                <Link
                  href={`/dashboard/research/strategies/${encodeURIComponent(strategy.strategy_id)}`}
                  className="text-sm text-mint hover:underline"
                >
                  Details →
                </Link>
                <Link
                  href={`/dashboard/research/experiments/new?strategy=${encodeURIComponent(strategy.strategy_id)}`}
                  className="rounded bg-mint/20 px-3 py-1.5 text-sm text-mint"
                  data-testid={`create-experiment-${strategy.strategy_id}`}
                >
                  Experiment erstellen
                </Link>
              </div>
            </Card>
          ))}
        </div>
      </div>
    );
  } catch (error) {
    return (
      <div
        data-testid="research-strategies-error"
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
