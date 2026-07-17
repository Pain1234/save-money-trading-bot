"use client";

import Link from "next/link";
import { useMemo, useState } from "react";

import {
  displayValue,
  type ResearchExperimentSummary,
} from "@/lib/research-api/client";

interface ExperimentsTableProps {
  items: ResearchExperimentSummary[];
}

export function ExperimentsTable({ items }: ExperimentsTableProps) {
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("");
  const [strategy, setStrategy] = useState("");

  const strategies = useMemo(
    () =>
      Array.from(new Set(items.map((i) => i.strategy_version).filter(Boolean))).sort(),
    [items],
  );
  const statuses = useMemo(
    () => Array.from(new Set(items.map((i) => i.status).filter(Boolean))).sort(),
    [items],
  );

  const filtered = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return items
      .filter((item) => (status ? item.status === status : true))
      .filter((item) => (strategy ? item.strategy_version === strategy : true))
      .filter((item) => {
        if (!needle) return true;
        return (
          item.experiment_id.toLowerCase().includes(needle) ||
          item.strategy_version.toLowerCase().includes(needle)
        );
      })
      .sort((a, b) => b.created_at.localeCompare(a.created_at));
  }, [items, q, status, strategy]);

  if (items.length === 0) {
    return (
      <div data-testid="research-experiments-empty">
        <h1 className="mb-4 text-2xl font-semibold">Experiments</h1>
        <p className="text-sm text-text-muted">
          Keine Experimente registriert.
        </p>
      </div>
    );
  }

  return (
    <div data-testid="research-experiments-ready" className="space-y-4">
      <h1 className="text-2xl font-semibold">Experiments</h1>

      <div className="flex flex-wrap gap-2" data-testid="research-experiments-filters">
        <input
          type="search"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Suche Experiment-ID oder Strategie"
          className="min-w-[220px] flex-1 rounded border border-border bg-bg-elevated px-3 py-1.5 text-sm text-text-primary"
          aria-label="Suche"
        />
        <select
          value={status}
          onChange={(e) => setStatus(e.target.value)}
          className="rounded border border-border bg-bg-elevated px-2 py-1.5 text-sm"
          aria-label="Status filter"
        >
          <option value="">Alle Status</option>
          {statuses.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
        <select
          value={strategy}
          onChange={(e) => setStrategy(e.target.value)}
          className="rounded border border-border bg-bg-elevated px-2 py-1.5 text-sm"
          aria-label="Strategie filter"
        >
          <option value="">Alle Strategien</option>
          {strategies.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
      </div>

      {filtered.length === 0 ? (
        <p className="text-sm text-text-muted" data-testid="research-experiments-no-match">
          Keine Experimente für die aktuelle Filterung.
        </p>
      ) : (
        <div className="overflow-x-auto rounded-xl border border-border-subtle">
          <table className="min-w-full text-left text-sm">
            <thead className="bg-bg-elevated text-text-muted">
              <tr>
                {[
                  "Experiment-ID",
                  "Strategie",
                  "Symbole",
                  "Zeitraum",
                  "Timeframe",
                  "Status",
                  "Erstellt",
                  "Laufzeit",
                  "Git",
                  "Dataset",
                  "Net PnL",
                  "Max DD",
                  "Trades",
                ].map((col) => (
                  <th key={col} className="whitespace-nowrap px-3 py-2 font-medium">
                    {col}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {filtered.map((item) => (
                <tr
                  key={item.experiment_id}
                  className="border-t border-border-subtle"
                >
                  <td className="px-3 py-2">
                    <Link
                      href={`/dashboard/research/experiments/${encodeURIComponent(item.experiment_id)}`}
                      className="font-mono text-mint hover:underline"
                    >
                      {item.experiment_id}
                    </Link>
                  </td>
                  <td className="px-3 py-2">
                    {displayValue(item.strategy_version)}
                  </td>
                  <td className="px-3 py-2">
                    {item.symbols.length
                      ? item.symbols.join(", ")
                      : "Nicht verfügbar"}
                  </td>
                  <td className="px-3 py-2 font-mono text-xs">
                    {item.time_range_start && item.time_range_end
                      ? `${item.time_range_start} → ${item.time_range_end}`
                      : "Nicht verfügbar"}
                  </td>
                  <td className="px-3 py-2">
                    {displayValue(item.timeframe)}
                  </td>
                  <td className="px-3 py-2">{displayValue(item.status)}</td>
                  <td className="px-3 py-2 font-mono text-xs">
                    {displayValue(item.created_at)}
                  </td>
                  <td className="px-3 py-2">
                    {item.duration_seconds == null
                      ? "Nicht verfügbar"
                      : `${item.duration_seconds}s`}
                  </td>
                  <td className="px-3 py-2 font-mono text-xs">
                    {displayValue(item.git_commit)}
                  </td>
                  <td className="px-3 py-2">
                    {displayValue(item.dataset_version)}
                  </td>
                  <td className="px-3 py-2 font-mono">
                    {displayValue(item.net_pnl)}
                  </td>
                  <td className="px-3 py-2 font-mono">
                    {displayValue(item.max_drawdown)}
                  </td>
                  <td className="px-3 py-2 font-mono">
                    {item.closed_trades == null
                      ? "Nicht verfügbar"
                      : item.closed_trades}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
