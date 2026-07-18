import Link from "next/link";

import { Card } from "@/components/ui/Card";
import { ResearchCharts } from "@/components/research/ResearchCharts";
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
        <label className="mb-1 block text-[11px] uppercase tracking-wide text-text-muted">
          Run A
        </label>
        <select
          name="run_a"
          defaultValue={runA}
          data-testid="research-compare-select-a"
          className="w-full rounded border border-border bg-bg-elevated px-2 py-1.5 text-sm"
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
        <label className="mb-1 block text-[11px] uppercase tracking-wide text-text-muted">
          Run B
        </label>
        <select
          name="run_b"
          defaultValue={runB}
          data-testid="research-compare-select-b"
          className="w-full rounded border border-border bg-bg-elevated px-2 py-1.5 text-sm"
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
        className="rounded bg-mint/20 px-3 py-1.5 text-sm text-mint"
      >
        Vergleichen
      </button>
    </form>
  );
}

export function CompareEmptyHint() {
  return (
    <p
      className="text-sm text-text-muted"
      data-testid="research-compare-empty"
    >
      Wähle zwei Runs aus, um Kennzahlen, Equity/Drawdown und
      Konfigurationsunterschiede zu vergleichen.
    </p>
  );
}

export function CompareError({ message }: { message: string }) {
  return (
    <div
      data-testid="research-compare-error"
      className="rounded-xl border border-red-500/40 bg-red-500/10 p-6"
    >
      <h2 className="text-lg font-semibold text-red-300">
        Vergleich nicht möglich
      </h2>
      <p className="mt-2 text-sm text-red-200/90">{message}</p>
    </div>
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
      <p className="font-mono text-sm text-text-primary">
        {run.metadata.run_id}
      </p>
      <p className="text-xs text-text-muted">
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
        className="rounded border border-mint/30 bg-mint/10 px-3 py-2 text-sm text-mint"
      >
        Kompatibel — identische Spec-/Run-Identität, keine Unterschiede.
      </div>
    );
  }
  return (
    <div
      data-testid="research-compare-incompatible"
      className="rounded border border-warning/40 bg-warning/10 px-3 py-2 text-sm text-warning"
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
      <p className="text-sm text-text-muted" data-testid="research-compare-diffs-empty">
        Keine Unterschiede.
      </p>
    );
  }
  return (
    <div className="overflow-x-auto rounded-xl border border-border-subtle" data-testid="research-compare-diffs">
      <table className="min-w-full text-left text-sm">
        <thead className="bg-bg-elevated text-text-muted">
          <tr>
            <th className="px-3 py-2 font-medium">Feld</th>
            <th className="px-3 py-2 font-medium">Run A</th>
            <th className="px-3 py-2 font-medium">Run B</th>
          </tr>
        </thead>
        <tbody>
          {keys.map((key) => {
            const [left, right] = diffs[key] ?? [null, null];
            return (
              <tr key={key} className="border-t border-border-subtle" data-testid={`diff-row-${key}`}>
                <td className="px-3 py-2 font-mono text-xs">{key}</td>
                <td className="max-w-[320px] break-words px-3 py-2 font-mono text-xs text-negative">
                  {formatDiffValue(left)}
                </td>
                <td className="max-w-[320px] break-words px-3 py-2 font-mono text-xs text-negative">
                  {formatDiffValue(right)}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
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
    <div className="overflow-x-auto rounded-xl border border-border-subtle" data-testid="research-compare-metrics">
      <table className="min-w-full text-left text-sm">
        <thead className="bg-bg-elevated text-text-muted">
          <tr>
            <th className="px-3 py-2 font-medium">Kennzahl</th>
            <th className="px-3 py-2 font-medium">Run A</th>
            <th className="px-3 py-2 font-medium">Run B</th>
          </tr>
        </thead>
        <tbody>
          {RESEARCH_METRIC_LABELS.map(({ key, label }) => (
            <tr key={key} className="border-t border-border-subtle" data-testid={`compare-metric-${key}`}>
              <td className="px-3 py-2 text-text-secondary">{label}</td>
              <td className="px-3 py-2 font-mono">{displayValue(a.metrics[key])}</td>
              <td className="px-3 py-2 font-mono">{displayValue(b.metrics[key])}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function RunIntegrityNotice({ run, label }: { run: ResearchCompareRunView; label: string }) {
  if (run.integrity.ok) return null;
  return (
    <p
      className="rounded border border-warning/40 bg-warning/10 px-3 py-2 text-sm text-warning"
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
    <div className="space-y-4" data-testid="research-compare-result">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex gap-6">
          <RunLabel run={a} />
          <RunLabel run={b} />
        </div>
        <div className="flex gap-2">
          <Link
            href={`/dashboard/research/experiments/${encodeURIComponent(a.metadata.experiment_id)}`}
            className="text-xs text-text-muted hover:text-mint"
          >
            Run A Detail →
          </Link>
          <Link
            href={`/dashboard/research/experiments/${encodeURIComponent(b.metadata.experiment_id)}`}
            className="text-xs text-text-muted hover:text-mint"
          >
            Run B Detail →
          </Link>
        </div>
      </div>

      <CompatibilityBanner result={result} />
      <RunIntegrityNotice run={a} label="Run A" />
      <RunIntegrityNotice run={b} label="Run B" />

      <Card padding="sm">
        <h2 className="mb-3 text-sm font-medium">Konfigurations- und Spec-Unterschiede</h2>
        <DiffsTable diffs={result.diffs} />
      </Card>

      <Card padding="sm">
        <h2 className="mb-3 text-sm font-medium">Kennzahlen</h2>
        <MetricsComparisonTable a={a} b={b} />
      </Card>

      <div className="grid gap-3 lg:grid-cols-2">
        <div className="space-y-2">
          <h3 className="text-sm font-medium text-text-secondary">
            Run A — Equity / Drawdown
          </h3>
          <ResearchCharts equity={a.equity} drawdown={a.drawdown} />
        </div>
        <div className="space-y-2">
          <h3 className="text-sm font-medium text-text-secondary">
            Run B — Equity / Drawdown
          </h3>
          <ResearchCharts equity={b.equity} drawdown={b.drawdown} />
        </div>
      </div>
    </div>
  );
}
