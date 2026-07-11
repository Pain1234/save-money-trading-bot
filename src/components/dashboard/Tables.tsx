import { OPEN_POSITIONS, RECENT_TRADES } from "@/lib/mock-data";
import { formatCurrency } from "@/lib/utils";
import {
  Badge,
  Card,
  CoinBadge,
  PanelHeader,
  PnlPill,
} from "@/components/ui/Card";
import { ArrowRight } from "lucide-react";

function SideBadge({ side }: { side: "long" | "short" }) {
  return (
    <Badge variant={side === "long" ? "positive" : "negative"}>
      {side === "long" ? "LONG" : "SHORT"}
    </Badge>
  );
}

function formatPrice(value: number): string {
  return formatCurrency(value).replace("US$", "$");
}

export function PositionsTable() {
  return (
    <Card padding="sm" className="min-w-0" id="positionen">
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
            {OPEN_POSITIONS.map((pos) => (
              <tr key={pos.id} className="text-[12px] leading-tight hover:bg-white/[0.015]">
                <td className="py-1 pr-0.5">
                  <CoinBadge coin={pos.coin} color={pos.coinColor} symbol={pos.symbol} />
                </td>
                <td className="py-1 pr-0.5">
                  <SideBadge side={pos.side} />
                </td>
                <td className="py-1 pr-0.5 font-mono text-text-secondary">
                  {pos.size}
                </td>
                <td className="py-1 pr-0.5 font-mono text-[11px] text-text-secondary">
                  {formatPrice(pos.entryPrice)}
                </td>
                <td className="py-1 pr-0.5 font-mono text-[11px] text-text-secondary">
                  {formatPrice(pos.markPrice)}
                </td>
                <td className="py-1 pr-0.5">
                  <PnlPill
                    value={pos.pnl}
                    formatted={`${pos.pnl >= 0 ? "+" : ""}${formatPrice(pos.pnl)}`}
                  />
                </td>
                <td className="py-1 pr-0.5 font-mono text-[11px] text-text-muted">
                  {pos.risk}
                </td>
                <td className="py-1 pr-0.5 font-mono text-[11px] text-text-muted">
                  {formatPrice(pos.stopLoss)}
                </td>
                <td className="py-1 font-mono text-[11px] text-text-muted">
                  {formatPrice(pos.takeProfit)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <a
        href="#positionen"
        className="mt-2 inline-flex items-center gap-1 text-[11px] text-mint-dim hover:text-mint"
      >
        Alle Positionen anzeigen
        <ArrowRight className="h-3 w-3" />
      </a>
    </Card>
  );
}

export function TradesTable() {
  return (
    <Card padding="sm" className="min-w-0" id="trades">
      <PanelHeader title="Letzte Trades" compact />

      <div className="min-w-0 overflow-x-auto">
        <table className="w-full min-w-0 table-fixed text-left">
          <thead>
            <tr className="border-b border-border-subtle text-[11px] uppercase tracking-[0.04em] text-text-muted">
              <th className="w-[24%] pb-1 font-normal">Symbol</th>
              <th className="w-[18%] pb-1 font-normal">Richtung</th>
              <th className="w-[22%] pb-1 font-normal">PnL</th>
              <th className="w-[16%] pb-1 font-normal">R-Multiple</th>
              <th className="w-[20%] pb-1 font-normal">Datum</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border-subtle/80">
            {RECENT_TRADES.map((trade) => (
              <tr key={trade.id} className="text-[12px] leading-tight hover:bg-white/[0.015]">
                <td className="py-1 pr-0.5">
                  <CoinBadge
                    coin={trade.coin}
                    color={trade.coinColor}
                    symbol={trade.symbol}
                  />
                </td>
                <td className="py-1 pr-0.5">
                  <SideBadge side={trade.side} />
                </td>
                <td className="py-1 pr-0.5">
                  <PnlPill
                    value={trade.pnl}
                    formatted={`${trade.pnl >= 0 ? "+" : ""}${formatPrice(trade.pnl)}`}
                  />
                </td>
                <td
                  className={`py-1 pr-0.5 font-mono text-[11px] ${
                    trade.rMultiple.startsWith("+")
                      ? "text-mint-dim"
                      : "text-negative"
                  }`}
                >
                  {trade.rMultiple}
                </td>
                <td className="py-1 font-mono text-[11px] text-text-muted">
                  {trade.date}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <a
        href="#trades"
        className="mt-2 inline-flex items-center gap-1 text-[11px] text-mint-dim hover:text-mint"
      >
        Alle Trades anzeigen
        <ArrowRight className="h-3 w-3" />
      </a>
    </Card>
  );
}
