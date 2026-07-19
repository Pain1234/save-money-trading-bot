import Link from "next/link";

import {
  ResearchApiError,
  ResearchEmpty,
  ResearchPageHeader,
  rs,
} from "@/components/research/chrome/ResearchPageChrome";
import { Badge, Card } from "@/components/ui/Card";

export interface StrategyListItem {
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

export function StrategiesCatalogEmpty() {
  return (
    <ResearchEmpty
      testId="research-strategies-empty"
      title="Strategien"
      message="Keine Strategien im Resolver-Katalog registriert."
    />
  );
}

export function StrategiesCatalogError({ message }: { message: string }) {
  return <ResearchApiError testId="research-strategies-error" message={message} />;
}

export function StrategiesCatalogView({
  items,
}: {
  items: StrategyListItem[];
}) {
  return (
    <div data-testid="research-strategies-ready" className={rs.page}>
      <ResearchPageHeader
        title="Strategien"
        description="Registrierte Research-Strategien aus dem Strategy Resolver. Sichtbar auch ohne ausgeführte Experimente."
      />

      <div className="grid gap-2">
        {items.map((strategy) => (
          <Card
            key={strategy.strategy_id}
            padding="sm"
            className="space-y-2"
            data-testid={`strategy-card-${strategy.strategy_id}`}
          >
            <div className="flex flex-wrap items-start justify-between gap-2">
              <div className="min-w-0">
                <h2 className="text-[14px] font-semibold text-text-primary">
                  {strategy.display_name}
                </h2>
                <p className="mt-0.5 text-[12px] text-text-secondary">
                  {strategy.description}
                </p>
              </div>
              <Badge variant="neutral">{strategy.lifecycle_status}</Badge>
            </div>

            <dl className="grid gap-2 text-[12px] sm:grid-cols-2 lg:grid-cols-4">
              <div>
                <dt className={rs.label}>Version</dt>
                <dd className="mt-0.5 font-mono">{strategy.strategy_version}</dd>
              </div>
              <div>
                <dt className={rs.label}>Symbole</dt>
                <dd className="mt-0.5">{strategy.supported_symbols.join(", ")}</dd>
              </div>
              <div>
                <dt className={rs.label}>Timeframes</dt>
                <dd className="mt-0.5">
                  {strategy.required_timeframes.join(", ")}
                </dd>
              </div>
              <div>
                <dt className={rs.label}>Experimente</dt>
                <dd className="mt-0.5 font-mono">{strategy.experiment_count}</dd>
              </div>
            </dl>

            <p className="text-[11px] text-text-muted">
              Letzter Run:{" "}
              {strategy.last_run?.created_at
                ? `${strategy.last_run.status ?? "—"} · ${strategy.last_run.created_at}`
                : "Noch kein Run"}
            </p>

            <div className="flex flex-wrap gap-2">
              <Link
                href={`/dashboard/research/strategies/${encodeURIComponent(strategy.strategy_id)}`}
                className={rs.btnSecondary}
              >
                Details →
              </Link>
              <Link
                href={`/dashboard/research/experiments/new?strategy=${encodeURIComponent(strategy.strategy_id)}`}
                className={rs.btnPrimary}
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
}
