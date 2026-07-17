import Link from "next/link";

import {
  Badge,
  Card,
  CoinBadge,
  PanelHeader,
  PnlPill,
} from "@/components/ui/Card";
import { ArrowRight } from "lucide-react";
import type { FillRowVm, PositionRowVm } from "@/lib/dashboard/types";
import { UNAVAILABLE } from "@/lib/dashboard/formatters";

function SideBadge({ side }: { side: "long" | "short" }) {
  return (
    <Badge variant={side === "long" ? "positive" : "negative"}>
      {side === "long" ? "LONG" : "SHORT"}
    </Badge>
  );
}

function EmptyRow({ colSpan, message }: { colSpan: number; message: string }) {
  return (
    <tr>
      <td
        colSpan={colSpan}
        className="py-4 text-center text-[12px] text-text-muted"
        data-testid="table-empty"
      >
        {message}
      </td>
    </tr>
  );
}

function ErrorRow({ colSpan, message }: { colSpan: number; message: string }) {
  return (
    <tr>
      <td
        colSpan={colSpan}
        className="py-4 text-center text-[12px] text-negative"
        data-testid="table-error"
      >
        {message}
      </td>
    </tr>
  );
}

interface PositionsTableProps {
  rows: PositionRowVm[];
  emptyMessage?: string;
  errorMessage?: string | null;
}

export function PositionsTable({
  rows,
  emptyMessage = "Keine offenen Positionen",
  errorMessage = null,
}: PositionsTableProps) {
  return (
    <Card padding="sm" className="min-w-0" id="positionen" data-testid="positions-table">
      <PanelHeader title="Offene Positionen" compact />

      <div className="min-w-0 overflow-x-auto">
        <table className="w-full min-w-0 table-fixed text-left">
          <thead>
            <tr className="border-b border-border-subtle text-[11px] uppercase tracking-[0.04em] text-text-muted">
              <th className="w-[13%] pb-1 font-normal">Symbol</th>
              <th className="w-[9%] pb-1 font-normal">Richtung</th>
              <th className="w-[7%] pb-1 font-normal">Größe</th>
              <th className="w-[11%] pb-1 font-normal">Einstieg</th>
              <th className="w-[11%] pb-1 font-normal">Preis</th>
              <th className="w-[11%] pb-1 font-normal">PnL</th>
              <th className="w-[8%] pb-1 font-normal">Risiko</th>
              <th className="w-[13%] pb-1 font-normal">Stop Loss</th>
              <th className="w-[17%] pb-1 font-normal">Take Profit</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border-subtle/80">
            {errorMessage ? (
              <ErrorRow colSpan={9} message={errorMessage} />
            ) : rows.length === 0 ? (
              <EmptyRow colSpan={9} message={emptyMessage} />
            ) : (
              rows.map((pos) => (
                <tr
                  key={pos.id}
                  className="text-[12px] leading-tight hover:bg-white/[0.015]"
                >
                  <td className="py-1 pr-0.5">
                    <CoinBadge
                      coin={pos.coin}
                      color={pos.coinColor}
                      symbol={pos.symbol}
                    />
                  </td>
                  <td className="py-1 pr-0.5">
                    <SideBadge side={pos.side} />
                  </td>
                  <td className="py-1 pr-0.5 font-mono text-text-secondary">
                    {pos.sizeDisplay}
                  </td>
                  <td className="py-1 pr-0.5 font-mono text-[11px] text-text-secondary">
                    {pos.entryPriceDisplay}
                  </td>
                  <td className="py-1 pr-0.5 font-mono text-[11px] text-text-secondary">
                    {pos.markPriceDisplay}
                  </td>
                  <td className="py-1 pr-0.5">
                    {pos.pnlDisplay === UNAVAILABLE ? (
                      <span className="font-mono text-[11px] text-text-muted">
                        {UNAVAILABLE}
                      </span>
                    ) : (
                      <PnlPill
                        value={pos.pnlNumericHint ?? 0}
                        formatted={pos.pnlDisplay}
                      />
                    )}
                  </td>
                  <td className="py-1 pr-0.5 font-mono text-[11px] text-text-muted">
                    {pos.riskDisplay}
                  </td>
                  <td className="py-1 pr-0.5 font-mono text-[11px] text-text-muted">
                    {pos.stopLossDisplay}
                  </td>
                  <td className="py-1 font-mono text-[11px] text-text-muted">
                    {pos.takeProfitDisplay}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      <Link
        href="/dashboard/positions"
        className="mt-2 inline-flex items-center gap-1 text-[11px] text-mint-dim hover:text-mint"
      >
        Alle Positionen anzeigen
        <ArrowRight className="h-3 w-3" />
      </Link>
    </Card>
  );
}

interface FillsTableProps {
  rows: FillRowVm[];
  emptyMessage?: string;
  errorMessage?: string | null;
}

export function FillsTable({
  rows,
  emptyMessage = "Keine Fills",
  errorMessage = null,
}: FillsTableProps) {
  return (
    <Card padding="sm" className="min-w-0" id="trades" data-testid="fills-table">
      <PanelHeader title="Letzte Fills" compact />

      <div className="min-w-0 overflow-x-auto">
        <table className="w-full min-w-0 table-fixed text-left">
          <thead>
            <tr className="border-b border-border-subtle text-[11px] uppercase tracking-[0.04em] text-text-muted">
              <th className="w-[22%] pb-1 font-normal">Symbol</th>
              <th className="w-[18%] pb-1 font-normal">Art</th>
              <th className="w-[18%] pb-1 font-normal">Menge</th>
              <th className="w-[20%] pb-1 font-normal">Preis</th>
              <th className="w-[22%] pb-1 font-normal">Zeit</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border-subtle/80">
            {errorMessage ? (
              <ErrorRow colSpan={5} message={errorMessage} />
            ) : rows.length === 0 ? (
              <EmptyRow colSpan={5} message={emptyMessage} />
            ) : (
              rows.map((fill) => (
                <tr
                  key={fill.id}
                  className="text-[12px] leading-tight hover:bg-white/[0.015]"
                >
                  <td className="py-1 pr-0.5">
                    <CoinBadge
                      coin={fill.coin}
                      color={fill.coinColor}
                      symbol={fill.symbol}
                    />
                  </td>
                  <td className="py-1 pr-0.5 font-mono text-[11px] text-text-secondary">
                    {fill.fillKind}
                  </td>
                  <td className="py-1 pr-0.5 font-mono text-[11px] text-text-secondary">
                    {fill.quantityDisplay}
                  </td>
                  <td className="py-1 pr-0.5 font-mono text-[11px] text-text-secondary">
                    {fill.priceDisplay}
                  </td>
                  <td className="py-1 font-mono text-[11px] text-text-muted">
                    {fill.timeDisplay}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      <Link
        href="/dashboard/fills"
        className="mt-2 inline-flex items-center gap-1 text-[11px] text-mint-dim hover:text-mint"
      >
        Alle Fills anzeigen
        <ArrowRight className="h-3 w-3" />
      </Link>
    </Card>
  );
}

/** @deprecated Use FillsTable — kept name alias for older imports */
export const TradesTable = FillsTable;
