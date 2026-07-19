import Link from "next/link";

import { Card } from "@/components/ui/Card";
import { ResearchCharts } from "@/components/research/ResearchCharts";
import {
  ResearchApiError,
  ResearchTableFrame,
  rs,
} from "@/components/research/chrome/ResearchPageChrome";
import {
  displayValue,
  type ResearchCompareResult,
  type ResearchCompareRunView,
} from "@/lib/research-api/client";
import { RESEARCH_METRIC_LABELS } from "@/lib/research/metrics";

export interface CompareSelectorItem {
  run_id: string;
  experiment_id: string;
  strategy_version: string;
  status: string;
}

interface CompareSelectorProps {
  items: CompareSelectorItem[];
  runA: string;
  runB: string;
}

function optionLabel(item: CompareSelectorItem): string {
  return `${item.run_id} — ${item.experiment_id} (${item.strategy_version || "?"}, ${item.status})`;
}

export function CompareSelector({ items, runA, runB }: CompareSelectorProps) {
  return (
    <form
      method="get"
      data-testid="research-compare-form"
      className="flex flex-wrap items-end gap-2"
    >
      <div className="min-w-[260px] flex-1">
        <label className={`mb-1 block ${rs.label}`}>Run A</label>
        <select
          name="run_a"
          defaultValue={runA}
          data-testid="research-compare-select-a"
          className={`w-full ${rs.select}`}
        >
          <option value="">— wählen —</option>
          {items.map((item) => (
            <option key={item.run_id} value={item.run_id}>
              {optionLabel(item)}
            </option>
          ))}
        </select>
      </div>
      <div className="min-w-[260px] flex-1">
        <label className={`mb-1 block ${rs.label}`}>Run B</label>
        <select
          name="run_b"
          defaultValue={runB}
          data-testid="research-compare-select-b"
          className={`w-full ${rs.select}`}
        >
          <option value="">— wählen —</option>
          {items.map((item) => (
            <option key={item.run_id} value={item.run_id}>
              {optionLabel(item)}
            </option>
          ))}
        </select>
      </div>
      <button
        type="submit"
        data-testid="research-compare-submit"
        className={rs.btnPrimary}
      >
        Vergleichen
      </button>
    </form>
  );
}

export function CompareEmptyHint() {
  return (
    <p className={rs.muted} data-testid="research-compare-empty">
      Wähle zwei Runs aus, um Kennzahlen, Equity/Drawdown und
      Konfigurationsunterschiede zu vergleichen.
    </p>
  );
}

export function CompareError({ message }: { message: string }) {
  return (
    <ResearchApiError
      testId="research-compare-error"
      title="Vergleich nicht möglich"
      message={message}
    />
  );
}

function formatDiffValue(value: unknown): string {
  if (value === null || value === undefined) return "Nicht verfügbar";
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  try {
    return JSON.stringify(value);
  } catch {
    return "Nicht verfügbar";
  }
}

function RunLabel({ run }: { run: ResearchCompareRunView }) {
  return (
    <div>
      <p className="font-mono text-[12px] text-text-primary">
        {run.metadata.run_id}
      </p>
      <p className="text-[11px] text-text-muted">
        {run.metadata.experiment_id} · {displayValue(run.metadata.status)}
      </p>
    </div>
  );
}

function CompatibilityBanner({ result }: { result: ResearchCompareResult }) {
  const diffCount = Object.keys(result.diffs).length;
  if (result.compatible) {
    return (
      <div
        data-testid="research-compare-compatible"
        className="rounded-sm border border-mint/30 bg-mint/10 px-2 py-1.5 text-[12px] text-mint"
      >
        Kompatibel — identische Spec-/Run-Identität, keine Unterschiede.
      </div>
    );
  }
  return (
    <div
      data-testid="research-compare-incompatible"
      className="rounded-sm border border-warning/40 bg-warning/10 px-2 py-1.5 text-[12px] text-warning"
    >
      Inkompatibel — {diffCount}{" "}
      {diffCount === 1 ? "Unterschied" : "Unterschiede"} zwischen Spec/Run-Identität.
      Kennzahlen werden getrennt angezeigt, nicht gemittelt oder gleichgesetzt.
    </div>
  );
}

function DiffsTable({ diffs }: { diffs: ResearchCompareResult["diffs"] }) {
  const keys = Object.keys(diffs).sort();
  if (keys.length === 0) {
    return (
      <p className={rs.muted} data-testid="research-compare-diffs-empty">
        Keine Unterschiede.
      </p>
    );
  }
  return (
    <ResearchTableFrame testId="research-compare-diffs">
      <table className={rs.table}>
        <thead>
          <tr>
            <th className={rs.th}>Feld</th>
            <th className={rs.th}>Run A</th>
            <th className={rs.th}>Run B</th>
          </tr>
        </thead>
        <tbody>
          {keys.map((key) => {
            const [left, right] = diffs[key] ?? [null, null];
            return (
              <tr
                key={key}
                className="border-t border-border-subtle"
                data-testid={`diff-row-${key}`}
              >
                <td className={`${rs.td} font-mono text-[11px]`}>{key}</td>
                <td className={`max-w-[320px] break-words ${rs.td} font-mono text-[11px] text-negative`}>
                  {formatDiffValue(left)}
                </td>
                <td className={`max-w-[320px] break-words ${rs.td} font-mono text-[11px] text-negative`}>
                  {formatDiffValue(right)}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </ResearchTableFrame>
  );
}

function MetricsComparisonTable({
  a,
  b,
}: {
  a: ResearchCompareRunView;
  b: ResearchCompareRunView;
}) {
  return (
    <ResearchTableFrame testId="research-compare-metrics">
      <table className={rs.table}>
        <thead>
          <tr>
            <th className={rs.th}>Kennzahl</th>
            <th className={rs.th}>Run A</th>
            <th className={rs.th}>Run B</th>
          </tr>
        </thead>
        <tbody>
          {RESEARCH_METRIC_LABELS.map(({ key, label }) => (
            <tr
              key={key}
              className="border-t border-border-subtle"
              data-testid={`compare-metric-${key}`}
            >
              <td className={rs.td}>{label}</td>
              <td className={`${rs.td} font-mono`}>
                {displayValue(a.metrics[key])}
              </td>
              <td className={`${rs.td} font-mono`}>
                {displayValue(b.metrics[key])}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </ResearchTableFrame>
  );
}

function RunIntegrityNotice({ run, label }: { run: ResearchCompareRunView; label: string }) {
  if (run.integrity.ok) return null;
  return (
    <p
      className="rounded-sm border border-warning/40 bg-warning/10 px-2 py-1.5 text-[12px] text-warning"
      data-testid={`research-compare-integrity-${label}`}
    >
      {label}: Integrität fehlgeschlagen — Kennzahlen/Charts werden nicht
      angezeigt. {displayValue(run.integrity.error)}
    </p>
  );
}

export function CompareResultView({ result }: { result: ResearchCompareResult }) {
  const { a, b } = result.runs;
  return (
    <div className={rs.page} data-testid="research-compare-result">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="flex gap-4">
          <RunLabel run={a} />
          <RunLabel run={b} />
        </div>
        <div className="flex gap-2">
          <Link
            href={`/dashboard/research/experiments/${encodeURIComponent(a.metadata.experiment_id)}`}
            className={rs.backLink}
          >
            Run A Detail →
          </Link>
          <Link
            href={`/dashboard/research/experiments/${encodeURIComponent(b.metadata.experiment_id)}`}
            className={rs.backLink}
          >
            Run B Detail →
          </Link>
        </div>
      </div>

      <CompatibilityBanner result={result} />
      <RunIntegrityNotice run={a} label="Run A" />
      <RunIntegrityNotice run={b} label="Run B" />

      <Card padding="sm">
        <h2 className={rs.sectionTitle}>
          Konfigurations- und Spec-Unterschiede
        </h2>
        <DiffsTable diffs={result.diffs} />
      </Card>

      <Card padding="sm">
        <h2 className={rs.sectionTitle}>Kennzahlen</h2>
        <MetricsComparisonTable a={a} b={b} />
      </Card>

      <div className="grid gap-2 lg:grid-cols-2">
        <div className="space-y-1">
          <h3 className={rs.sectionTitle}>Run A — Equity / Drawdown</h3>
          <ResearchCharts equity={a.equity} drawdown={a.drawdown} />
        </div>
        <div className="space-y-1">
          <h3 className={rs.sectionTitle}>Run B — Equity / Drawdown</h3>
          <ResearchCharts equity={b.equity} drawdown={b.drawdown} />
        </div>
      </div>
    </div>
  );
}
