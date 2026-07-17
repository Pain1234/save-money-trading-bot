import { describe, expect, it } from "vitest";

import {
  buildStopSeriesPoints,
  isWinningTrade,
  tradeFocusRange,
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
});

describe("isWinningTrade", () => {
  it("distinguishes winners and losers", () => {
    expect(isWinningTrade("10")).toBe(true);
    expect(isWinningTrade("-1")).toBe(false);
    expect(isWinningTrade(null)).toBeNull();
  });
});

describe("tradeFocusRange", () => {
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
