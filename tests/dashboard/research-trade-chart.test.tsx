import React from "react";
import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";

import { ResearchTradeChart } from "../../src/components/research/ResearchTradeChart";
import {
  buildStopSeriesPoints,
  buildTradeMarkers,
  ChartDataError,
  isWinningTrade,
  parseCandlesForChart,
  parseFinitePrice,
  pnlClassName,
  tradeFocusRange,
  type TradeChartMarker,
} from "../../src/lib/research/trade-chart";

describe("buildStopSeriesPoints", () => {
  it("includes initial_stop and trailing stops", () => {
    const points = buildStopSeriesPoints([
      {
        entry_time: "2024-01-11T00:00:00Z",
        initial_stop: "40000",
        trailing_stop_history: [
          {
            time: "2024-01-12T00:00:00Z",
            effective_stop: "40500",
          },
        ],
      },
    ]);
    expect(points).toEqual([
      { time: Date.parse("2024-01-11T00:00:00Z") / 1000, value: 40000 },
      { time: Date.parse("2024-01-12T00:00:00Z") / 1000, value: 40500 },
    ]);
  });

  it("inserts whitespace between trades so lines do not connect", () => {
    const points = buildStopSeriesPoints([
      {
        entry_time: "2024-01-11T00:00:00Z",
        initial_stop: "100",
        trailing_stop_history: [],
      },
      {
        entry_time: "2024-02-01T00:00:00Z",
        initial_stop: "200",
        trailing_stop_history: [],
      },
    ]);
    expect(points).toHaveLength(3);
    expect(points[0]).toEqual({
      time: Date.parse("2024-01-11T00:00:00Z") / 1000,
      value: 100,
    });
    expect(points[1]).toEqual({
      time: Date.parse("2024-01-11T00:00:00Z") / 1000 + 1,
    });
    expect(points[2]).toEqual({
      time: Date.parse("2024-02-01T00:00:00Z") / 1000,
      value: 200,
    });
    expect("value" in points[1]!).toBe(false);
  });

  it("supports open trades without exit", () => {
    const points = buildStopSeriesPoints([
      {
        entry_time: "2024-01-11T00:00:00Z",
        exit_time: null,
        initial_stop: "40000",
        trailing_stop_history: [
          { time: "2024-01-12T00:00:00Z", effective_stop: "40100" },
        ],
      },
    ]);
    expect(points).toHaveLength(2);
    expect(points[0]).toMatchObject({ value: 40000 });
  });

  it("fails closed on non-positive stop prices (no invented zeros)", () => {
    expect(() =>
      buildStopSeriesPoints([
        {
          entry_time: "2024-01-11T00:00:00Z",
          initial_stop: "0",
        },
      ]),
    ).toThrow(ChartDataError);
  });
});

describe("parseFinitePrice / parseCandlesForChart", () => {
  it("rejects NaN, zero, and inconsistent OHLC", () => {
    expect(() => parseFinitePrice("NaN")).toThrow(ChartDataError);
    expect(() => parseFinitePrice("0")).toThrow(ChartDataError);
    expect(() =>
      parseCandlesForChart([
        {
          time: "2024-01-11T00:00:00Z",
          open: "10",
          high: "9",
          low: "8",
          close: "9.5",
        },
      ]),
    ).toThrow(/OHLC inconsistent|high < low/);
  });

  it("parses valid candles without inventing zeros", () => {
    const candles = parseCandlesForChart([
      {
        time: "2024-01-11T00:00:00Z",
        open: "41000",
        high: "42500",
        low: "40500",
        close: "42000",
        volume: "10",
      },
    ]);
    expect(candles[0]?.close).toBe(42000);
    expect(candles[0]?.open).toBe(41000);
  });
});

describe("buildTradeMarkers", () => {
  it("types entry belowBar and exit aboveBar in one SeriesMarker array", () => {
    const markers: TradeChartMarker[] = buildTradeMarkers(
      [
        {
          entry_time: "2024-01-11T00:00:00Z",
          exit_time: "2024-01-20T00:00:00Z",
          net_pnl: "10",
          entry_type: "BREAKOUT",
          exit_reason: "RC_EXIT_STOP_TRAILING",
        },
        {
          entry_time: "2024-02-01T00:00:00Z",
          exit_time: "2024-02-10T00:00:00Z",
          net_pnl: "-5",
        },
      ],
      { win: "#0f0", loss: "#f00", neutral: "#888" },
    );
    expect(markers).toHaveLength(4);
    expect(markers[0]?.position).toBe("belowBar");
    expect(markers[1]?.position).toBe("aboveBar");
    expect(markers[0]?.color).toBe("#0f0");
    expect(markers[2]?.color).toBe("#f00");
  });
});

describe("isWinningTrade / pnlClassName / tradeFocusRange", () => {
  it("distinguishes winners and losers", () => {
    expect(isWinningTrade("10")).toBe(true);
    expect(isWinningTrade("-1")).toBe(false);
    expect(isWinningTrade(null)).toBeNull();
    expect(pnlClassName("10")).toBe("text-positive");
    expect(pnlClassName("-1")).toBe("text-negative");
  });

  it("pads entry/exit window for table focus", () => {
    const range = tradeFocusRange({
      entry_time: "2024-01-11T00:00:00Z",
      exit_time: "2024-01-20T00:00:00Z",
    });
    const entry = Date.parse("2024-01-11T00:00:00Z") / 1000;
    const exit = Date.parse("2024-01-20T00:00:00Z") / 1000;
    expect(range.from).toBe(entry - 86400 * 3);
    expect(range.to).toBe(exit + 86400 * 3);
  });
});

describe("ResearchTradeChart (static render)", () => {
  it("renders integrity fail-closed banner", () => {
    const html = renderToStaticMarkup(
      <ResearchTradeChart
        experimentId="exp-1"
        symbols={["BTC"]}
        integrityOk={false}
        integrityError="checksum mismatch"
      />,
    );
    expect(html).toContain("research-trade-chart-error");
    expect(html).toContain("Integrität fehlgeschlagen");
    expect(html).toContain("checksum mismatch");
  });

  it("renders symbol selector options for multi-symbol experiments", () => {
    const html = renderToStaticMarkup(
      <ResearchTradeChart
        experimentId="exp-1"
        symbols={["BTC", "ETH"]}
        integrityOk={true}
      />,
    );
    expect(html).toContain("trade-chart-symbol");
    expect(html).toContain("BTC");
    expect(html).toContain("ETH");
  });
});
