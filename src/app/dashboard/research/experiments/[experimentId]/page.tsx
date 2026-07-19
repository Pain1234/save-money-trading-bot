import { notFound } from "next/navigation";

import { ExperimentJobPanel } from "@/components/research/ExperimentJobPanel";
import { ResearchCharts } from "@/components/research/ResearchCharts";
import { ResearchTradeChart } from "@/components/research/ResearchTradeChart";
import { ScorecardBindSection } from "@/components/research/ScorecardBindSection";
import {
  ResearchApiError,
  ResearchPageHeader,
  rs,
} from "@/components/research/chrome/ResearchPageChrome";
import { Card } from "@/components/ui/Card";
import { PaperApiError } from "@/lib/paper-api/client";
import {
  displayValue,
  fetchResearchExperiment,
  getResearchErrorMessage,
} from "@/lib/research-api/client";
import { loadScorecardForExperiment } from "@/lib/research/scorecard-binding";
import { RESEARCH_METRIC_LABELS } from "@/lib/research/metrics";

export const dynamic = "force-dynamic";

const METRIC_LABELS = RESEARCH_METRIC_LABELS;

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
    const metadata = detail.metadata;
    const scorecardBind = await loadScorecardForExperiment(metadata.run_id);
    const config = {
      symbols: detail.config?.symbols ?? [],
      time_range_start: detail.config?.time_range_start ?? null,
      time_range_end: detail.config?.time_range_end ?? null,
      timeframe: detail.config?.timeframe ?? "Nicht verfügbar",
      starting_capital: detail.config?.starting_capital ?? null,
      parameters: detail.config?.parameters ?? {},
      fee_assumption: detail.config?.fee_assumption ?? null,
      slippage_assumption: detail.config?.slippage_assumption ?? null,
      funding_assumption: detail.config?.funding_assumption ?? null,
      costs: detail.config?.costs ?? null,
      in_sample_config: detail.config?.in_sample_config ?? "Nicht verfügbar",
      out_of_sample_config:
        detail.config?.out_of_sample_config ?? "Nicht verfügbar",
      benchmark: detail.config?.benchmark ?? "Nicht verfügbar",
      hypothesis: detail.config?.hypothesis ?? null,
    };
    const metrics = detail.metrics ?? {};

    return (
      <div data-testid="research-detail-ready" className={rs.page}>
        <ResearchPageHeader
          title={metadata.experiment_id}
          description={`${displayValue(metadata.strategy_version)} · ${displayValue(detail.job?.status ?? metadata.status)}`}
          backHref="/dashboard/research/experiments"
          backLabel="← Experiments"
          titleMono
        />

        {detail.job && (
          <ExperimentJobPanel
            experimentId={metadata.experiment_id}
            initialJob={detail.job}
          />
        )}

        <Card padding="sm">
          <h2 className={rs.sectionTitle}>Metadaten</h2>
          {!detail.integrity.ok && (
            <p
              className="mb-2 rounded-sm border border-warning/40 bg-warning/10 px-2 py-1.5 text-[12px] text-warning"
              data-testid="research-integrity-warning"
            >
              Integrität fehlgeschlagen — Kennzahlen und Charts werden nicht
              angezeigt. {displayValue(detail.integrity.error)}
            </p>
          )}
          <dl className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3 text-[12px]">
            {[
              ["Experiment-ID", metadata.experiment_id],
              ["Run-ID", metadata.run_id],
              ["Strategie", metadata.strategy_version],
              ["Git-Commit", metadata.git_commit],
              ["Dataset-Version", metadata.dataset_version],
              ["Seed", metadata.seed],
              ["Erstellt (Registry)", metadata.created_at],
              ["Startzeit", metadata.started_at],
              ["Finalisierungszeit (Manifest)", metadata.finalized_at],
              [
                "Laufzeit",
                metadata.duration_seconds == null
                  ? null
                  : `${metadata.duration_seconds}s`,
              ],
              ["Status", metadata.status],
            ].map(([label, value]) => (
              <div key={String(label)}>
                <dt className={rs.label}>{label}</dt>
                <dd className={`mt-0.5 ${rs.mono}`}>
                  {displayValue(value as string | number | null)}
                </dd>
              </div>
            ))}
          </dl>
        </Card>

        <Card padding="sm">
          <h2 className={rs.sectionTitle}>Konfiguration</h2>
          <dl className="grid gap-2 sm:grid-cols-2 text-[12px]">
            <div>
              <dt className={rs.label}>Symbole</dt>
              <dd className="mt-0.5">
                {config.symbols.length
                  ? config.symbols.join(", ")
                  : "Nicht verfügbar"}
              </dd>
            </div>
            <div>
              <dt className={rs.label}>Zeitraum</dt>
              <dd className="mt-0.5 font-mono text-[11px]">
                {config.time_range_start && config.time_range_end
                  ? `${config.time_range_start} → ${config.time_range_end}`
                  : "Nicht verfügbar"}
              </dd>
            </div>
            <div>
              <dt className={rs.label}>Timeframe</dt>
              <dd className="mt-0.5">{displayValue(config.timeframe)}</dd>
            </div>
            <div>
              <dt className={rs.label}>Startkapital</dt>
              <dd className="mt-0.5 font-mono">
                {displayValue(config.starting_capital)}
              </dd>
            </div>
            <div>
              <dt className={rs.label}>Benchmark</dt>
              <dd className="mt-0.5">{displayValue(config.benchmark)}</dd>
            </div>
            <div>
              <dt className={rs.label}>IS / OOS</dt>
              <dd className="mt-0.5">
                {displayValue(config.in_sample_config)} /{" "}
                {displayValue(config.out_of_sample_config)}
              </dd>
            </div>
          </dl>
          <div className="mt-2 grid gap-2 lg:grid-cols-2">
            <pre className="overflow-x-auto rounded-sm border border-border-subtle bg-bg-elevated p-2 text-[11px]">
              <p className="mb-1 text-text-muted">Strategieparameter</p>
              {jsonBlock(config.parameters)}
            </pre>
            <pre className="overflow-x-auto rounded-sm border border-border-subtle bg-bg-elevated p-2 text-[11px]">
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
          <h2 className={rs.sectionTitle}>Kennzahlen</h2>
          <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {METRIC_LABELS.map(({ key, label }) => (
              <div
                key={key}
                className="rounded-sm border border-border-subtle px-2 py-1.5"
                data-testid={`research-metric-${key}`}
              >
                <p className={rs.label}>{label}</p>
                <p className="mt-0.5 font-mono text-[12px]">
                  {displayValue(metrics[key])}
                </p>
              </div>
            ))}
          </div>
        </Card>

        <ResearchCharts equity={detail.equity} drawdown={detail.drawdown} />

        <ScorecardBindSection
          bind={scorecardBind}
          equity={detail.integrity.ok ? detail.equity : null}
          drawdown={detail.integrity.ok ? detail.drawdown : null}
        />

        <ResearchTradeChart
          experimentId={metadata.experiment_id}
          symbols={config.symbols}
          integrityOk={detail.integrity.ok}
          integrityError={detail.integrity.error}
        />
      </div>
    );
  } catch (error) {
    if (error instanceof PaperApiError && error.status === 404) {
      notFound();
    }
    return (
      <ResearchApiError
        testId="research-detail-error"
        message={getResearchErrorMessage(error)}
      />
    );
  }
}
