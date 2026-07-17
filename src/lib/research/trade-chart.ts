/** Pure helpers for Research Kurs & Trades chart (#266). */

export interface TrailingStopSnapshot {
  time: string;
  trail_stop?: string;
  effective_stop: string;
}

export interface TradeStopSource {
  entry_time: string;
  exit_time?: string | null;
  initial_stop?: string | null;
  trailing_stop_history?: TrailingStopSnapshot[];
  net_pnl?: string | null;
}

export type StopSeriesPoint =
  | { time: number; value: number }
  | { time: number };

function parseNum(raw: string | number | null | undefined): number | null {
  if (raw == null || raw === "") return null;
  const n = typeof raw === "number" ? raw : Number(raw);
  return Number.isFinite(n) ? n : null;
}

function toEpochSec(iso: string): number {
  return Math.floor(new Date(iso).getTime() / 1000);
}

/**
 * Build stop line points with whitespace gaps between trades.
 * Includes initial_stop at entry_time, then trailing effective stops.
 */
export function buildStopSeriesPoints(
  trades: TradeStopSource[],
): StopSeriesPoint[] {
  const out: StopSeriesPoint[] = [];
  trades.forEach((trade, tradeIdx) => {
    const points: Array<{ time: number; value: number }> = [];
    const initial = parseNum(trade.initial_stop ?? null);
    if (initial != null) {
      points.push({ time: toEpochSec(trade.entry_time), value: initial });
    }
    for (const snap of trade.trailing_stop_history ?? []) {
      const value = parseNum(snap.effective_stop);
      if (value == null) continue;
      points.push({ time: toEpochSec(snap.time), value });
    }
    points.sort((a, b) => a.time - b.time);
    const deduped: Array<{ time: number; value: number }> = [];
    for (const p of points) {
      const prev = deduped[deduped.length - 1];
      if (prev && prev.time === p.time) {
        deduped[deduped.length - 1] = p;
      } else {
        deduped.push(p);
      }
    }
    out.push(...deduped);
    if (tradeIdx < trades.length - 1 && deduped.length > 0) {
      const last = deduped[deduped.length - 1]!;
      out.push({ time: last.time + 1 });
    }
  });
  return out;
}

export function isWinningTrade(netPnl: string | number | null | undefined): boolean | null {
  const n = parseNum(netPnl ?? null);
  if (n == null) return null;
  return n >= 0;
}

export function tradeFocusRange(trade: TradeStopSource): {
  from: number;
  to: number;
} {
  const entry = toEpochSec(trade.entry_time);
  const exit = trade.exit_time ? toEpochSec(trade.exit_time) : entry + 86400 * 5;
  const pad = 86400 * 3;
  return { from: entry - pad, to: exit + pad };
}
