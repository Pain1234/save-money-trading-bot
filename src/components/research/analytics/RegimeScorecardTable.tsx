import { AnalyticsPanel } from "@/components/research/analytics/AnalyticsPanel";
import { UNAVAILABLE } from "@/lib/research/executive-summary";
import { displayValue } from "@/lib/research-api/client";

/** Optional row — all fields displayed via displayValue; null → Nicht verfügbar. */
export interface RegimeScorecardRow {
  regime: string;
  trades: string | number | null;
  netPnl: string | number | null;
  maxDd: string | number | null;
  label: string | null;
}

interface RegimeScorecardTableProps {
  rows?: RegimeScorecardRow[] | null;
  reason?: string;
}

/**
 * Regime scorecard table (#300).
 * Does not invent regime metrics — empty/missing → Nicht verfügbar.
 * Real rows come from #291 scorecard API (bound in #292).
 */
export function RegimeScorecardTable({
  rows,
  reason = "Scorecard-API (#291) noch nicht angebunden — keine Regime-Metriken",
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
                {["Regime", "Trades", "Net PnL", "Max DD", "Label"].map((col) => (
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
                    {displayValue(row.trades)}
                  </td>
                  <td className="px-2 py-1.5 font-mono">
                    {displayValue(row.netPnl)}
                  </td>
                  <td className="px-2 py-1.5 font-mono">
                    {displayValue(row.maxDd)}
                  </td>
                  <td className="px-2 py-1.5 font-mono text-text-secondary">
                    {displayValue(row.label)}
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
