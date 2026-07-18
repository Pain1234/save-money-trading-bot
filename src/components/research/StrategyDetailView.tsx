import Link from "next/link";

import { Card } from "@/components/ui/Card";
import { displayValue } from "@/lib/research-api/client";

export interface StrategyDetailModel {
  strategy_id: string;
  display_name: string;
  description: string;
  strategy_version: string;
  aliases: string[];
  lifecycle_status: string;
  supported_symbols: string[];
  required_timeframes: string[];
  monthly_filter: string;
  weekly_filter: string;
  daily_entries: string;
  stop_logic: string;
  reason_codes: string[];
  parameter_defaults: Record<string, unknown>;
  parameter_descriptions: Record<string, string>;
  experiment_count: number;
  last_run: {
    experiment_id?: string;
    status?: string;
    created_at?: string;
  } | null;
  experiments: Array<{
    experiment_id?: string;
    status?: string;
    created_at?: string;
    net_pnl?: string | null;
  }>;
}

export function StrategyDetailError({ message }: { message: string }) {
  return (
    <div
      data-testid="research-strategy-detail-error"
      className="rounded-xl border border-red-500/40 bg-red-500/10 p-6"
    >
      <h1 className="text-xl font-semibold text-red-300">Research API Error</h1>
      <p className="mt-2 text-sm text-red-200/90">{message}</p>
    </div>
  );
}

export function StrategyDetailView({ strategy }: { strategy: StrategyDetailModel }) {
  const paramEntries = Object.entries(strategy.parameter_defaults).filter(
    ([key]) => key !== "strategy_version",
  );

  return (
    <div data-testid="research-strategy-detail" className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-xs text-text-muted">
            <Link
              href="/dashboard/research/strategies"
              className="text-mint hover:underline"
            >
              Strategien
            </Link>
          </p>
          <h1 className="mt-1 text-2xl font-semibold">{strategy.display_name}</h1>
          <p className="mt-1 text-sm text-text-secondary">{strategy.description}</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Link
            href={`/dashboard/research/experiments/new?strategy=${encodeURIComponent(strategy.strategy_id)}`}
            className="rounded bg-mint/20 px-3 py-1.5 text-sm text-mint"
            data-testid="strategy-new-experiment"
          >
            Neues Experiment
          </Link>
          <Link
            href={`/dashboard/research/experiments/new?strategy=${encodeURIComponent(strategy.strategy_id)}&baseline=1`}
            className="rounded border border-border px-3 py-1.5 text-sm text-text-secondary hover:text-mint"
            data-testid="strategy-baseline-experiment"
          >
            Baseline-Experiment erstellen
          </Link>
        </div>
      </div>

      <Card
        padding="sm"
        className="grid gap-3 text-sm sm:grid-cols-2 lg:grid-cols-4"
      >
        <div>
          <div className="text-text-muted">Kanonische ID</div>
          <div className="font-mono" data-testid="strategy-canonical-id">
            {strategy.strategy_id}
          </div>
        </div>
        <div>
          <div className="text-text-muted">Version</div>
          <div>{strategy.strategy_version}</div>
        </div>
        <div>
          <div className="text-text-muted">Status</div>
          <div>{strategy.lifecycle_status}</div>
        </div>
        <div>
          <div className="text-text-muted">Alias (lesbar)</div>
          <div className="font-mono text-xs" data-testid="strategy-aliases">
            {strategy.aliases.length ? strategy.aliases.join(", ") : "—"}
          </div>
        </div>
      </Card>

      <div className="grid gap-3 lg:grid-cols-2">
        <Card padding="sm" className="space-y-2 text-sm">
          <h2 className="font-medium">Monatsfilter</h2>
          <p className="text-text-secondary">{strategy.monthly_filter}</p>
        </Card>
        <Card padding="sm" className="space-y-2 text-sm">
          <h2 className="font-medium">Wochenfilter</h2>
          <p className="text-text-secondary">{strategy.weekly_filter}</p>
        </Card>
        <Card padding="sm" className="space-y-2 text-sm">
          <h2 className="font-medium">Tägliche Einstiege</h2>
          <p className="text-text-secondary">{strategy.daily_entries}</p>
        </Card>
        <Card padding="sm" className="space-y-2 text-sm">
          <h2 className="font-medium">Stop-Logik</h2>
          <p className="text-text-secondary">{strategy.stop_logic}</p>
        </Card>
      </div>

      <Card padding="sm" className="space-y-3">
        <h2 className="font-medium">Parameter (eingefrorene Defaults)</h2>
        <p className="text-xs text-text-muted">
          Keine Profitabilitätsbehauptung. Werte entsprechen Strategy Specification
          V1 / StrategyParameters.
        </p>
        <dl className="grid gap-2 text-sm sm:grid-cols-2">
          {paramEntries.map(([key, value]) => (
            <div key={key} className="rounded border border-border/60 p-2">
              <dt className="font-mono text-xs text-text-muted">{key}</dt>
              <dd className="mt-0.5">{String(value)}</dd>
              {strategy.parameter_descriptions[key] ? (
                <p className="mt-1 text-xs text-text-secondary">
                  {strategy.parameter_descriptions[key]}
                </p>
              ) : null}
            </div>
          ))}
        </dl>
      </Card>

      <Card padding="sm" className="space-y-2">
        <h2 className="font-medium">Reason Codes</h2>
        <ul className="grid gap-1 font-mono text-xs text-text-secondary sm:grid-cols-2 lg:grid-cols-3">
          {strategy.reason_codes.map((code) => (
            <li key={code}>{code}</li>
          ))}
        </ul>
      </Card>

      <Card padding="sm" className="space-y-3">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h2 className="font-medium">Vorhandene Experimente</h2>
          <span className="text-sm text-text-muted">
            {strategy.experiment_count} gesamt
            {strategy.last_run?.status
              ? ` · letzter Status: ${displayValue(strategy.last_run.status)}`
              : ""}
          </span>
        </div>
        {strategy.experiments.length === 0 ? (
          <p
            className="text-sm text-text-muted"
            data-testid="strategy-experiments-empty"
          >
            Noch keine Experimente für diese Strategie. Die Strategie bleibt
            trotzdem auswählbar.
          </p>
        ) : (
          <ul className="space-y-2 text-sm">
            {strategy.experiments.map((exp) => (
              <li
                key={exp.experiment_id}
                className="flex flex-wrap items-center justify-between gap-2 border-b border-border/40 pb-2"
              >
                <Link
                  href={`/dashboard/research/experiments/${encodeURIComponent(exp.experiment_id ?? "")}`}
                  className="font-mono text-mint hover:underline"
                >
                  {exp.experiment_id}
                </Link>
                <span className="text-text-muted">
                  {displayValue(exp.status)} · Net PnL{" "}
                  {displayValue(exp.net_pnl ?? null)}
                </span>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
