"use client";

import Link from "next/link";
import { useMemo, useState } from "react";

import {
  ResearchEmpty,
  ResearchPageHeader,
  ResearchTableFrame,
  rs,
} from "@/components/research/chrome/ResearchPageChrome";
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
      <ResearchEmpty
        testId="research-experiments-empty"
        title="Experiments"
        message="Keine Experimente registriert."
      />
    );
  }

  return (
    <div data-testid="research-experiments-ready" className={rs.page}>
      <ResearchPageHeader title="Experiments" />

      <div
        className="flex flex-wrap gap-2"
        data-testid="research-experiments-filters"
      >
        <input
          type="search"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Suche Experiment-ID oder Strategie"
          className={`min-w-[220px] flex-1 ${rs.input}`}
          aria-label="Suche"
        />
        <select
          value={status}
          onChange={(e) => setStatus(e.target.value)}
          className={rs.select}
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
          className={rs.select}
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
        <p className={rs.muted} data-testid="research-experiments-no-match">
          Keine Experimente für die aktuelle Filterung.
        </p>
      ) : (
        <ResearchTableFrame>
          <table className={rs.table}>
            <thead>
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
                  <th key={col} className={`whitespace-nowrap ${rs.th}`}>
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
                  <td className={rs.td}>
                    <Link
                      href={`/dashboard/research/experiments/${encodeURIComponent(item.experiment_id)}`}
                      className="font-mono text-mint hover:underline"
                    >
                      {item.experiment_id}
                    </Link>
                  </td>
                  <td className={rs.td}>
                    {displayValue(item.strategy_version)}
                  </td>
                  <td className={rs.td}>
                    {item.symbols.length
                      ? item.symbols.join(", ")
                      : "Nicht verfügbar"}
                  </td>
                  <td className={`${rs.td} font-mono text-[11px]`}>
                    {item.time_range_start && item.time_range_end
                      ? `${item.time_range_start} → ${item.time_range_end}`
                      : "Nicht verfügbar"}
                  </td>
                  <td className={rs.td}>{displayValue(item.timeframe)}</td>
                  <td className={rs.td}>{displayValue(item.status)}</td>
                  <td className={`${rs.td} font-mono text-[11px]`}>
                    {displayValue(item.created_at)}
                  </td>
                  <td className={rs.td}>
                    {item.duration_seconds == null
                      ? "Nicht verfügbar"
                      : `${item.duration_seconds}s`}
                  </td>
                  <td className={`${rs.td} font-mono text-[11px]`}>
                    {displayValue(item.git_commit)}
                  </td>
                  <td className={rs.td}>
                    {displayValue(item.dataset_version)}
                  </td>
                  <td className={`${rs.td} font-mono`}>
                    {displayValue(item.net_pnl)}
                  </td>
                  <td className={`${rs.td} font-mono`}>
                    {displayValue(item.max_drawdown)}
                  </td>
                  <td className={`${rs.td} font-mono`}>
                    {item.closed_trades == null
                      ? "Nicht verfügbar"
                      : item.closed_trades}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </ResearchTableFrame>
      )}
    </div>
  );
}
