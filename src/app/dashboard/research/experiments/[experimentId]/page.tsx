import Link from "next/link";
import { notFound } from "next/navigation";

import { ResearchCharts } from "@/components/research/ResearchCharts";
import { Card } from "@/components/ui/Card";
import { PaperApiError } from "@/lib/paper-api/client";
import {
  displayValue,
  fetchResearchExperiment,
  getResearchErrorMessage,
} from "@/lib/research-api/client";

export const dynamic = "force-dynamic";

const METRIC_LABELS: Array<{ key: string; label: string }> = [
  { key: "total_return", label: "Total Return" },
  { key: "cagr", label: "CAGR" },
  { key: "sharpe", label: "Sharpe" },
  { key: "sortino", label: "Sortino" },
  { key: "max_drawdown", label: "Maximum Drawdown" },
  { key: "profit_factor", label: "Profit Factor" },
  { key: "win_rate", label: "Win Rate" },
  { key: "trade_count", label: "Trade Count" },
  { key: "fees", label: "Gebühren" },
  { key: "slippage_costs", label: "Slippage" },
  { key: "funding_costs", label: "Funding" },
  { key: "net_pnl", label: "Net PnL" },
  { key: "gross_pnl", label: "Gross PnL" },
  { key: "expectancy", label: "Expectancy" },
  { key: "benchmark_result", label: "Benchmark Result" },
];

function jsonBlock(value: unknown): string {
  if (value == null) return "Nicht verfügbar";
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return "Nicht verfügbar";
  }
}

export default async function ResearchExperimentDetailPage({
  params,
}: {
  params: Promise<{ experimentId: string }>;
}) {
  const { experimentId } = await params;

  try {
    const detail = await fetchResearchExperiment(experimentId);
    const { metadata, config, metrics } = detail;

    return (
      <div data-testid="research-detail-ready" className="space-y-4">
        <div>
          <Link
            href="/dashboard/research/experiments"
            className="text-xs text-text-muted hover:text-mint"
          >
            ← Experiments
          </Link>
          <h1 className="mt-2 font-mono text-xl font-semibold">
            {metadata.experiment_id}
          </h1>
          <p className="mt-1 text-sm text-text-secondary">
            {displayValue(metadata.strategy_version)} · {displayValue(metadata.status)}
          </p>
        </div>

        <Card padding="sm">
          <h2 className="mb-3 text-sm font-medium">Metadaten</h2>
          <dl className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3 text-sm">
            {[
              ["Experiment-ID", metadata.experiment_id],
              ["Run-ID", metadata.run_id],
              ["Strategie", metadata.strategy_version],
              ["Git-Commit", metadata.git_commit],
              ["Dataset-Version", metadata.dataset_version],
              ["Seed", metadata.seed],
              ["Erstellt", metadata.created_at],
              ["Start", metadata.started_at],
              ["Ende", metadata.completed_at],
              [
                "Laufzeit",
                metadata.duration_seconds == null
                  ? null
                  : `${metadata.duration_seconds}s`,
              ],
              ["Status", metadata.status],
            ].map(([label, value]) => (
              <div key={String(label)}>
                <dt className="text-[11px] uppercase tracking-wide text-text-muted">
                  {label}
                </dt>
                <dd className="mt-0.5 font-mono text-text-primary">
                  {displayValue(value as string | number | null)}
                </dd>
              </div>
            ))}
          </dl>
        </Card>

        <Card padding="sm">
          <h2 className="mb-3 text-sm font-medium">Konfiguration</h2>
          <dl className="grid gap-2 sm:grid-cols-2 text-sm">
            <div>
              <dt className="text-[11px] uppercase tracking-wide text-text-muted">
                Symbole
              </dt>
              <dd className="mt-0.5">
                {config.symbols.length
                  ? config.symbols.join(", ")
                  : "Nicht verfügbar"}
              </dd>
            </div>
            <div>
              <dt className="text-[11px] uppercase tracking-wide text-text-muted">
                Zeitraum
              </dt>
              <dd className="mt-0.5 font-mono text-xs">
                {config.time_range_start && config.time_range_end
                  ? `${config.time_range_start} → ${config.time_range_end}`
                  : "Nicht verfügbar"}
              </dd>
            </div>
            <div>
              <dt className="text-[11px] uppercase tracking-wide text-text-muted">
                Timeframe
              </dt>
              <dd className="mt-0.5">{displayValue(config.timeframe)}</dd>
            </div>
            <div>
              <dt className="text-[11px] uppercase tracking-wide text-text-muted">
                Startkapital
              </dt>
              <dd className="mt-0.5 font-mono">
                {displayValue(config.starting_capital)}
              </dd>
            </div>
            <div>
              <dt className="text-[11px] uppercase tracking-wide text-text-muted">
                Benchmark
              </dt>
              <dd className="mt-0.5">{displayValue(config.benchmark)}</dd>
            </div>
            <div>
              <dt className="text-[11px] uppercase tracking-wide text-text-muted">
                IS / OOS
              </dt>
              <dd className="mt-0.5">
                {displayValue(config.in_sample_config)} /{" "}
                {displayValue(config.out_of_sample_config)}
              </dd>
            </div>
          </dl>
          <div className="mt-3 grid gap-3 lg:grid-cols-2">
            <pre className="overflow-x-auto rounded border border-border-subtle bg-bg-elevated p-2 text-xs">
              <p className="mb-1 text-text-muted">Strategieparameter</p>
              {jsonBlock(config.parameters)}
            </pre>
            <pre className="overflow-x-auto rounded border border-border-subtle bg-bg-elevated p-2 text-xs">
              <p className="mb-1 text-text-muted">Kosten / Fees / Slippage</p>
              {jsonBlock({
                fee_assumption: config.fee_assumption,
                slippage_assumption: config.slippage_assumption,
                funding_assumption: config.funding_assumption,
                costs: config.costs,
              })}
            </pre>
          </div>
        </Card>

        <Card padding="sm">
          <h2 className="mb-3 text-sm font-medium">Kennzahlen</h2>
          <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {METRIC_LABELS.map(({ key, label }) => (
              <div
                key={key}
                className="rounded border border-border-subtle px-3 py-2"
                data-testid={`research-metric-${key}`}
              >
                <p className="text-[11px] uppercase tracking-wide text-text-muted">
                  {label}
                </p>
                <p className="mt-1 font-mono text-sm">
                  {displayValue(metrics[key])}
                </p>
              </div>
            ))}
          </div>
        </Card>

        <ResearchCharts equity={detail.equity} drawdown={detail.drawdown} />
      </div>
    );
  } catch (error) {
    if (error instanceof PaperApiError && error.status === 404) {
      notFound();
    }
    return (
      <div
        data-testid="research-detail-error"
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
