import Link from "next/link";

import {
  ResearchApiError,
  ResearchPageHeader,
  rs,
} from "@/components/research/chrome/ResearchPageChrome";
import { Card, PanelHeader } from "@/components/ui/Card";
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
    <ResearchApiError
      testId="research-strategy-detail-error"
      message={message}
    />
  );
}

export function StrategyDetailView({ strategy }: { strategy: StrategyDetailModel }) {
  const paramEntries = Object.entries(strategy.parameter_defaults).filter(
    ([key]) => key !== "strategy_version",
  );

  return (
    <div data-testid="research-strategy-detail" className={rs.page}>
      <ResearchPageHeader
        title={strategy.display_name}
        description={strategy.description}
        backHref="/dashboard/research/strategies"
        backLabel="← Strategien"
        actions={
          <>
            <Link
              href={`/dashboard/research/experiments/new?strategy=${encodeURIComponent(strategy.strategy_id)}`}
              className={rs.btnPrimary}
              data-testid="strategy-new-experiment"
            >
              Neues Experiment
            </Link>
            <Link
              href={`/dashboard/research/experiments/new?strategy=${encodeURIComponent(strategy.strategy_id)}&baseline=1`}
              className={rs.btnSecondary}
              data-testid="strategy-baseline-experiment"
            >
              Baseline-Experiment
            </Link>
          </>
        }
      />

      <Card
        padding="sm"
        className="grid gap-2 text-[12px] sm:grid-cols-2 lg:grid-cols-4"
      >
        <div>
          <div className={rs.label}>Kanonische ID</div>
          <div className="mt-0.5 font-mono" data-testid="strategy-canonical-id">
            {strategy.strategy_id}
          </div>
        </div>
        <div>
          <div className={rs.label}>Version</div>
          <div className="mt-0.5 font-mono">{strategy.strategy_version}</div>
        </div>
        <div>
          <div className={rs.label}>Status</div>
          <div className="mt-0.5">{strategy.lifecycle_status}</div>
        </div>
        <div>
          <div className={rs.label}>Alias</div>
          <div
            className="mt-0.5 font-mono text-[11px]"
            data-testid="strategy-aliases"
          >
            {strategy.aliases.length ? strategy.aliases.join(", ") : "—"}
          </div>
        </div>
      </Card>

      <div className="grid gap-2 lg:grid-cols-2">
        {(
          [
            ["Monatsfilter", strategy.monthly_filter],
            ["Wochenfilter", strategy.weekly_filter],
            ["Tägliche Einstiege", strategy.daily_entries],
            ["Stop-Logik", strategy.stop_logic],
          ] as const
        ).map(([title, body]) => (
          <Card key={title} padding="sm" className="space-y-1">
            <PanelHeader title={title} compact />
            <p className="text-[12px] text-text-secondary">{body}</p>
          </Card>
        ))}
      </div>

      <Card padding="sm" className="space-y-2">
        <PanelHeader
          title="Parameter (eingefrorene Defaults)"
          subtitle="Keine Profitabilitätsbehauptung — Strategy Specification V1."
          compact
        />
        <dl className="grid gap-2 text-[12px] sm:grid-cols-2">
          {paramEntries.map(([key, value]) => (
            <div
              key={key}
              className="rounded-sm border border-border-subtle px-2 py-1.5"
            >
              <dt className="font-mono text-[11px] text-text-muted">{key}</dt>
              <dd className="mt-0.5">{String(value)}</dd>
              {strategy.parameter_descriptions[key] ? (
                <p className="mt-1 text-[11px] text-text-secondary">
                  {strategy.parameter_descriptions[key]}
                </p>
              ) : null}
            </div>
          ))}
        </dl>
      </Card>

      <Card padding="sm" className="space-y-2">
        <PanelHeader title="Reason Codes" compact />
        <ul className="grid gap-1 font-mono text-[11px] text-text-secondary sm:grid-cols-2 lg:grid-cols-3">
          {strategy.reason_codes.map((code) => (
            <li key={code}>{code}</li>
          ))}
        </ul>
      </Card>

      <Card padding="sm" className="space-y-2">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h2 className="text-[12px] font-semibold text-text-primary">
            Vorhandene Experimente
          </h2>
          <span className={rs.muted}>
            {strategy.experiment_count} gesamt
            {strategy.last_run?.status
              ? ` · letzter Status: ${displayValue(strategy.last_run.status)}`
              : ""}
          </span>
        </div>
        {strategy.experiments.length === 0 ? (
          <p className={rs.muted} data-testid="strategy-experiments-empty">
            Noch keine Experimente für diese Strategie. Die Strategie bleibt
            trotzdem auswählbar.
          </p>
        ) : (
          <ul className="space-y-1.5 text-[12px]">
            {strategy.experiments.map((exp) => (
              <li
                key={exp.experiment_id}
                className="flex flex-wrap items-center justify-between gap-2 border-b border-border-subtle pb-1.5"
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
