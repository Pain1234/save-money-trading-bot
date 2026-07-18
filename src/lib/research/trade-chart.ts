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

export interface ChartCandleSource {
  time: string;
  open: string | number;
  high: string | number;
  low: string | number;
  close: string | number;
  volume?: string | number;
}

export type StopSeriesPoint =
  | { time: number; value: number }
  | { time: number };

/** Shared marker shape for lightweight-charts SeriesMarkerBar. */
export type TradeChartMarker = {
  time: number;
  position: "aboveBar" | "belowBar" | "inBar";
  color: string;
  shape: "arrowUp" | "arrowDown" | "circle" | "square";
  text?: string;
};

export class ChartDataError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ChartDataError";
  }
}

export function parseFinitePrice(
  raw: string | number | null | undefined,
  field = "price",
): number {
  if (raw == null || raw === "") {
    throw new ChartDataError(`missing ${field}`);
  }
  const n = typeof raw === "number" ? raw : Number(raw);
  if (!Number.isFinite(n)) {
    throw new ChartDataError(`non-finite ${field}: ${String(raw)}`);
  }
  if (n <= 0) {
    throw new ChartDataError(`${field} must be positive: ${String(raw)}`);
  }
  return n;
}

export function parseFiniteVolume(
  raw: string | number | null | undefined,
  field = "volume",
): number {
  if (raw == null || raw === "") {
    return 0;
  }
  const n = typeof raw === "number" ? raw : Number(raw);
  if (!Number.isFinite(n) || n < 0) {
    throw new ChartDataError(`invalid ${field}: ${String(raw)}`);
  }
  return n;
}

export function parseCandleForChart(candle: ChartCandleSource): {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
} {
  const open = parseFinitePrice(candle.open, "open");
  const high = parseFinitePrice(candle.high, "high");
  const low = parseFinitePrice(candle.low, "low");
  const close = parseFinitePrice(candle.close, "close");
  const volume = parseFiniteVolume(candle.volume, "volume");
  if (high < Math.max(open, close) || low > Math.min(open, close)) {
    throw new ChartDataError(
      `OHLC inconsistent at ${candle.time}: H=${high} L=${low} O=${open} C=${close}`,
    );
  }
  if (high < low) {
    throw new ChartDataError(`high < low at ${candle.time}`);
  }
  const time = toEpochSec(candle.time);
  if (!Number.isFinite(time)) {
    throw new ChartDataError(`invalid candle time: ${candle.time}`);
  }
  return { time, open, high, low, close, volume };
}

export function parseCandlesForChart(candles: ChartCandleSource[]): Array<{
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}> {
  if (!Array.isArray(candles)) {
    throw new ChartDataError("candles must be an array");
  }
  return candles.map((c, idx) => {
    try {
      return parseCandleForChart(c);
    } catch (err) {
      if (err instanceof ChartDataError) {
        throw new ChartDataError(`candle[${idx}]: ${err.message}`);
      }
      throw err;
    }
  });
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
    const initial = trade.initial_stop
      ? parseFinitePrice(trade.initial_stop, "initial_stop")
      : null;
    if (initial != null) {
      points.push({ time: toEpochSec(trade.entry_time), value: initial });
    }
    for (const snap of trade.trailing_stop_history ?? []) {
      const value = parseFinitePrice(snap.effective_stop, "effective_stop");
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

export function isWinningTrade(
  netPnl: string | number | null | undefined,
): boolean | null {
  if (netPnl == null || netPnl === "") return null;
  const n = typeof netPnl === "number" ? netPnl : Number(netPnl);
  if (!Number.isFinite(n)) return null;
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

export function buildTradeMarkers(
  trades: Array<
    TradeStopSource & {
      entry_time: string;
      exit_time?: string | null;
      entry_type?: string | null;
      exit_reason?: string | null;
    }
  >,
  colors: { win: string; loss: string; neutral: string },
): TradeChartMarker[] {
  const markers: TradeChartMarker[] = [];
  for (const trade of trades) {
    const win = isWinningTrade(trade.net_pnl);
    const color =
      win === true ? colors.win : win === false ? colors.loss : colors.neutral;
    markers.push({
      time: toEpochSec(trade.entry_time),
      position: "belowBar",
      color,
      shape: "arrowUp",
      text: trade.entry_type ?? "BUY",
    });
    if (trade.exit_time) {
      markers.push({
        time: toEpochSec(trade.exit_time),
        position: "aboveBar",
        color,
        shape: "arrowDown",
        text: trade.exit_reason ?? "SELL",
      });
    }
  }
  return markers;
}

export function pnlClassName(netPnl: string | number | null | undefined): string {
  const win = isWinningTrade(netPnl);
  if (win === true) return "text-positive";
  if (win === false) return "text-negative";
  return "";
}
