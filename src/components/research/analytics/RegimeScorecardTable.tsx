import { AnalyticsPanel } from "@/components/research/analytics/AnalyticsPanel";
import { UNAVAILABLE } from "@/lib/research/executive-summary";
import { displayValue } from "@/lib/research-api/client";

/**
 * Optional regime row. Prefer GET …/scorecards/{id}/detail regime_rows (#350/#302).
 * Columns match #292 AC; empty → Nicht verfügbar.
 */
export interface RegimeScorecardRow {
  regime: string;
  quality: string | number | null;
  confidence: string | number | null;
  behaviour: string | number | null;
  trades: string | number | null;
  netPnl: string | number | null;
  maxDd: string | number | null;
  costs: string | number | null;
  benchmarkDelta: string | number | null;
  /** @deprecated Prefer quality/behaviour; kept for older fixtures. */
  label?: string | null;
}

interface RegimeScorecardTableProps {
  rows?: RegimeScorecardRow[] | null;
  reason?: string;
}

const COLUMNS = [
  "Regime",
  "Quality",
  "Confidence",
  "Behaviour",
  "Trades",
  "Net PnL",
  "Max DD",
  "Costs",
  "Benchmark Δ",
] as const;

/**
 * Regime scorecard table (#300/#292).
 * Does not invent regime metrics — empty/missing → Nicht verfügbar.
 */
export function RegimeScorecardTable({
  rows,
  reason = "Regime-Zeilen nicht in Scorecard Layer-5 Payload",
}: RegimeScorecardTableProps) {
  const hasRows = Array.isArray(rows) && rows.length > 0;

  return (
    <AnalyticsPanel
      id="regime-scorecard"
      title="Regime Scorecard"
      subtitle="Pro Regime — raw metrics only, keine erfundenen Scores"
      unavailable={!hasRows}
      unavailableReason={reason}
    >
      {hasRows ? (
        <div className="overflow-x-auto">
          <table
            className="min-w-full text-left text-[12px]"
            data-testid="regime-scorecard-table"
          >
            <thead className="text-text-muted">
              <tr>
                {COLUMNS.map((col) => (
                  <th key={col} className="px-2 py-1 font-medium">
                    {col}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows!.map((row) => (
                <tr
                  key={row.regime}
                  className="border-t border-border-subtle"
                  data-testid={`regime-row-${row.regime}`}
                >
                  <td className="px-2 py-1.5 font-mono text-mint">{row.regime}</td>
                  <td className="px-2 py-1.5 font-mono">
                    {displayValue(row.quality)}
                  </td>
                  <td className="px-2 py-1.5 font-mono">
                    {displayValue(row.confidence)}
                  </td>
                  <td className="px-2 py-1.5 font-mono">
                    {displayValue(row.behaviour)}
                  </td>
                  <td className="px-2 py-1.5 font-mono">
                    {displayValue(row.trades)}
                  </td>
                  <td className="px-2 py-1.5 font-mono">
                    {displayValue(row.netPnl)}
                  </td>
                  <td className="px-2 py-1.5 font-mono">
                    {displayValue(row.maxDd)}
                  </td>
                  <td className="px-2 py-1.5 font-mono">
                    {displayValue(row.costs)}
                  </td>
                  <td className="px-2 py-1.5 font-mono">
                    {displayValue(row.benchmarkDelta)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
      {hasRows ? (
        <p className="text-[10px] text-text-muted">
          Fehlende Zellen = {UNAVAILABLE} (nie still zu 0).
        </p>
      ) : null}
    </AnalyticsPanel>
  );
}
