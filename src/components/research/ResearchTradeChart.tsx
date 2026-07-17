"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  CandlestickSeries,
  ColorType,
  LineSeries,
  createChart,
  createSeriesMarkers,
  type IChartApi,
  type ISeriesMarkersPluginApi,
  type UTCTimestamp,
} from "lightweight-charts";

import { Card } from "@/components/ui/Card";
import { buildStopSeriesPoints } from "@/lib/research/trade-chart";

interface ChartCandle {
  time: string;
  open: string;
  high: string;
  low: string;
  close: string;
  volume: string;
}

interface TrailingStopSnapshot {
  time: string;
  trail_stop: string;
  effective_stop: string;
}

interface ResearchTrade {
  symbol: string;
  entry_time: string;
  exit_time: string | null;
  entry_fill_price: string;
  exit_fill_price: string | null;
  initial_stop?: string | null;
  net_pnl: string | null;
  exit_reason: string | null;
  strategy_reason_codes?: string[];
  trailing_stop_history?: TrailingStopSnapshot[];
}

interface ChartDataResponse {
  symbol: string;
  timeframe: string;
  candles: ChartCandle[];
  trades: ResearchTrade[];
  integrity?: { ok: boolean; error: string | null };
}

export interface ResearchTradeChartProps {
  experimentId: string;
  symbols: string[];
  integrityOk: boolean;
  integrityError?: string | null;
}

const COLOR_FALLBACKS = {
  mint: "#42d98b",
  negative: "#f05252",
  warning: "#d9a72e",
  bgElevated: "#0a151d",
  textMuted: "#6d7a84",
} as const;

function readCssVar(name: string, fallback: string): string {
  if (typeof window === "undefined") return fallback;
  const value = getComputedStyle(document.documentElement)
    .getPropertyValue(name)
    .trim();
  return value || fallback;
}

function chartColors() {
  return {
    mint: readCssVar("--ds-color-mint", COLOR_FALLBACKS.mint),
    negative: readCssVar("--ds-color-negative", COLOR_FALLBACKS.negative),
    warning: readCssVar("--ds-color-warning", COLOR_FALLBACKS.warning),
    bgElevated: readCssVar("--ds-color-bg-elevated", COLOR_FALLBACKS.bgElevated),
    textMuted: readCssVar("--ds-color-text-muted", COLOR_FALLBACKS.textMuted),
  };
}

function toUtcTimestamp(iso: string): UTCTimestamp {
  return Math.floor(new Date(iso).getTime() / 1000) as UTCTimestamp;
}

function parseNum(value: string | null | undefined): number {
  const n = Number(value);
  return Number.isFinite(n) ? n : 0;
}

function formatTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toISOString().slice(0, 10);
}

export function ResearchTradeChart({
  experimentId,
  symbols,
  integrityOk,
  integrityError,
}: ResearchTradeChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const markersRef = useRef<ISeriesMarkersPluginApi<UTCTimestamp> | null>(null);

  const [symbol, setSymbol] = useState(symbols[0] ?? "");
  const [loading, setLoading] = useState(false);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [chartData, setChartData] = useState<ChartDataResponse | null>(null);
  const [selectedTradeIdx, setSelectedTradeIdx] = useState<number | null>(null);

  useEffect(() => {
    setSymbol(symbols[0] ?? "");
  }, [symbols]);

  useEffect(() => {
    if (!integrityOk || !symbol) {
      setChartData(null);
      setFetchError(null);
      setLoading(false);
      return;
    }

    let cancelled = false;
    setLoading(true);
    setFetchError(null);
    setChartData(null);
    setSelectedTradeIdx(null);

    void (async () => {
      try {
        const res = await fetch(
          `/api/research/experiments/${encodeURIComponent(experimentId)}/chart-data?symbol=${encodeURIComponent(symbol)}`,
        );
        if (!res.ok) {
          let detail = res.statusText;
          try {
            const body = (await res.json()) as { detail?: string; error?: string };
            detail = body.detail ?? body.error ?? detail;
          } catch {
            /* ignore */
          }
          if (!cancelled) setFetchError(detail || "Chart-Daten nicht verfügbar");
          return;
        }
        const body = (await res.json()) as ChartDataResponse;
        if (!cancelled) setChartData(body);
      } catch {
        if (!cancelled) setFetchError("Chart-Daten konnten nicht geladen werden.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [experimentId, symbol, integrityOk]);

  const zoomToTrade = useCallback((trade: ResearchTrade) => {
    const chart = chartRef.current;
    if (!chart) return;
    const entry = toUtcTimestamp(trade.entry_time);
    const exit = trade.exit_time ? toUtcTimestamp(trade.exit_time) : entry;
    const from = (Math.min(entry, exit) - 86400 * 3) as UTCTimestamp;
    const to = (Math.max(entry, exit) + 86400 * 3) as UTCTimestamp;
    chart.timeScale().setVisibleRange({ from, to });
  }, []);

  useEffect(() => {
    const container = containerRef.current;
    if (!container || !integrityOk || loading || fetchError || !chartData) {
      return;
    }

    const colors = chartColors();
    const chart = createChart(container, {
      width: container.clientWidth,
      height: 320,
      layout: {
        background: { type: ColorType.Solid, color: colors.bgElevated },
        textColor: colors.textMuted,
      },
      grid: {
        vertLines: { color: "rgba(255,255,255,0.06)" },
        horzLines: { color: "rgba(255,255,255,0.06)" },
      },
      rightPriceScale: { borderColor: "rgba(255,255,255,0.08)" },
      timeScale: { borderColor: "rgba(255,255,255,0.08)" },
    });
    chartRef.current = chart;

    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: colors.mint,
      downColor: colors.negative,
      borderUpColor: colors.mint,
      borderDownColor: colors.negative,
      wickUpColor: colors.mint,
      wickDownColor: colors.negative,
    });

    candleSeries.setData(
      chartData.candles.map((c) => ({
        time: toUtcTimestamp(c.time),
        open: parseNum(c.open),
        high: parseNum(c.high),
        low: parseNum(c.low),
        close: parseNum(c.close),
      })),
    );

    const stopSeries = chart.addSeries(LineSeries, {
      color: colors.warning,
      lineWidth: 1,
      lineStyle: 2,
      priceLineVisible: false,
      lastValueVisible: false,
    });
    const stopData = buildStopSeriesPoints(chartData.trades).map((p) =>
      "value" in p
        ? { time: p.time as UTCTimestamp, value: p.value }
        : { time: p.time as UTCTimestamp },
    );
    if (stopData.length > 0) {
      stopSeries.setData(stopData);
    }

    const markers = chartData.trades.flatMap((trade) => {
      const items = [
        {
          time: toUtcTimestamp(trade.entry_time),
          position: "belowBar" as const,
          color: colors.mint,
          shape: "arrowUp" as const,
        },
      ];
      if (trade.exit_time) {
        items.push({
          time: toUtcTimestamp(trade.exit_time),
          position: "aboveBar" as const,
          color: colors.negative,
          shape: "arrowDown" as const,
        });
      }
      return items;
    });
    markersRef.current = createSeriesMarkers(candleSeries, markers);

    const ro = new ResizeObserver(() => {
      if (container) {
        chart.applyOptions({ width: container.clientWidth });
      }
    });
    ro.observe(container);

    chart.timeScale().fitContent();

    return () => {
      ro.disconnect();
      markersRef.current = null;
      chart.remove();
      chartRef.current = null;
    };
  }, [chartData, fetchError, integrityOk, loading]);

  useEffect(() => {
    if (selectedTradeIdx == null || !chartData) return;
    const trade = chartData.trades[selectedTradeIdx];
    if (trade) zoomToTrade(trade);
  }, [chartData, selectedTradeIdx, zoomToTrade]);

  const selectedTrade =
    selectedTradeIdx != null && chartData
      ? chartData.trades[selectedTradeIdx]
      : null;
  const reasonCodes = selectedTrade?.strategy_reason_codes ?? [];

  if (!integrityOk) {
    return (
      <Card padding="sm" data-testid="research-trade-chart">
        <h2 className="mb-2 text-sm font-medium">Kurs &amp; Trades</h2>
        <p
          className="rounded border border-warning/40 bg-warning/10 px-3 py-2 text-sm text-warning"
          data-testid="research-trade-chart-error"
        >
          Integrität fehlgeschlagen — Kurs &amp; Trades werden nicht angezeigt.{" "}
          {integrityError ?? "Artefakte nicht verifiziert."}
        </p>
      </Card>
    );
  }

  return (
    <Card padding="sm" data-testid="research-trade-chart">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-sm font-medium">Kurs &amp; Trades</h2>
        {symbols.length > 1 ? (
          <select
            value={symbol}
            onChange={(e) => setSymbol(e.target.value)}
            className="rounded border border-border-subtle bg-bg-elevated px-2 py-1 text-xs text-text-primary"
            data-testid="trade-chart-symbol"
          >
            {symbols.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        ) : (
          <span
            className="font-mono text-xs text-text-secondary"
            data-testid="trade-chart-symbol"
          >
            {symbol || "—"}
          </span>
        )}
      </div>

      {loading && (
        <div
          className="h-[320px] animate-pulse rounded bg-white/5"
          data-testid="research-trade-chart-loading"
        />
      )}

      {!loading && fetchError && (
        <p
          className="rounded border border-red-500/40 bg-red-500/10 px-3 py-2 text-sm text-red-300"
          data-testid="research-trade-chart-error"
        >
          {fetchError}
        </p>
      )}

      {!loading && !fetchError && chartData && (
        <>
          <div
            ref={containerRef}
            className="h-[320px] w-full"
            data-testid="research-trade-chart-canvas"
          />

          {chartData.trades.length === 0 ? (
            <p
              className="mt-3 text-sm text-text-muted"
              data-testid="research-trade-chart-no-trades"
            >
              Keine Trades für {chartData.symbol}.
            </p>
          ) : (
            <div className="mt-3 overflow-x-auto">
              <table
                className="w-full min-w-[640px] text-left text-xs"
                data-testid="trade-chart-table"
              >
                <thead>
                  <tr className="border-b border-border-subtle text-text-muted">
                    <th className="px-2 py-1.5 font-medium">Entry</th>
                    <th className="px-2 py-1.5 font-medium">Exit</th>
                    <th className="px-2 py-1.5 font-medium">Entry Px</th>
                    <th className="px-2 py-1.5 font-medium">Exit Px</th>
                    <th className="px-2 py-1.5 font-medium">Net PnL</th>
                    <th className="px-2 py-1.5 font-medium">Exit Reason</th>
                  </tr>
                </thead>
                <tbody>
                  {chartData.trades.map((trade, idx) => (
                    <tr
                      key={`${trade.entry_time}-${idx}`}
                      className={`cursor-pointer border-b border-border-subtle/60 hover:bg-white/5 ${
                        selectedTradeIdx === idx ? "bg-mint/10" : ""
                      }`}
                      onClick={() => setSelectedTradeIdx(idx)}
                    >
                      <td className="px-2 py-1.5 font-mono">
                        {formatTime(trade.entry_time)}
                      </td>
                      <td className="px-2 py-1.5 font-mono">
                        {formatTime(trade.exit_time)}
                      </td>
                      <td className="px-2 py-1.5 font-mono">
                        {trade.entry_fill_price}
                      </td>
                      <td className="px-2 py-1.5 font-mono">
                        {trade.exit_fill_price ?? "—"}
                      </td>
                      <td className="px-2 py-1.5 font-mono">
                        {trade.net_pnl ?? "—"}
                      </td>
                      <td className="px-2 py-1.5 font-mono">
                        {trade.exit_reason ?? "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          <div
            className="mt-3 rounded border border-border-subtle bg-bg-elevated p-3"
            data-testid="trade-reason-panel"
          >
            <h3 className="text-xs font-medium text-text-secondary">
              Strategy Reason Codes
            </h3>
            {selectedTrade == null ? (
              <p className="mt-1 text-xs text-text-muted">
                Trade-Zeile wählen, um gespeicherte Reason Codes anzuzeigen.
              </p>
            ) : reasonCodes.length === 0 ? (
              <p className="mt-1 text-xs text-text-muted">
                Keine gespeicherten strategy_reason_codes für diesen Trade.
              </p>
            ) : (
              <ul className="mt-2 flex flex-wrap gap-1.5">
                {reasonCodes.map((code) => (
                  <li
                    key={code}
                    className="rounded border border-border-subtle bg-bg-card-alt px-2 py-0.5 font-mono text-[11px] text-text-primary"
                  >
                    {code}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </>
      )}
    </Card>
  );
}
