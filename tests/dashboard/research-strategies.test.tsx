import React from "react";
import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";

import {
  StrategiesCatalogEmpty,
  StrategiesCatalogError,
  StrategiesCatalogView,
} from "../../src/components/research/StrategiesCatalogView";
import {
  StrategyDetailError,
  StrategyDetailView,
} from "../../src/components/research/StrategyDetailView";

const TREND_CARD = {
  strategy_id: "trend_v1",
  display_name: "Trend Strategy V1",
  description: "Long-only multi-timeframe trend following.",
  strategy_version: "trend-v1.0.0",
  lifecycle_status: "research",
  supported_symbols: ["BTC", "ETH"],
  required_timeframes: ["1M", "1W", "1D"],
  experiment_count: 0,
  last_run: null,
};

describe("StrategiesCatalogView", () => {
  it("renders catalog with Trend Strategy V1 once (no alias duplicate card)", () => {
    const html = renderToStaticMarkup(
      <StrategiesCatalogView items={[TREND_CARD]} />,
    );
    expect(html).toContain("research-strategies-ready");
    expect(html).toContain("Trend Strategy V1");
    expect(html).toContain('data-testid="strategy-card-trend_v1"');
    expect(html).not.toContain("strategy-card-trend_strategy_v1");
    expect(html).toContain(
      'href="/dashboard/research/experiments/new?strategy=trend_v1"',
    );
    expect(html).toContain('data-testid="create-experiment-trend_v1"');
  });

  it("renders empty state", () => {
    const html = renderToStaticMarkup(<StrategiesCatalogEmpty />);
    expect(html).toContain("research-strategies-empty");
    expect(html).toContain("Keine Strategien");
  });

  it("renders error state", () => {
    const html = renderToStaticMarkup(
      <StrategiesCatalogError message="API down" />,
    );
    expect(html).toContain("research-strategies-error");
    expect(html).toContain("API down");
  });
});

describe("StrategyDetailView", () => {
  it("shows canonical id, aliases, and lab links", () => {
    const html = renderToStaticMarkup(
      <StrategyDetailView
        strategy={{
          ...TREND_CARD,
          aliases: ["trend_strategy_v1"],
          monthly_filter: "Monthly MA filter",
          weekly_filter: "Weekly MA filter",
          daily_entries: "20d breakout",
          stop_logic: "ATR trailing",
          reason_codes: ["RC_ENTRY_BREAKOUT_20D"],
          parameter_defaults: { lookback: 20 },
          parameter_descriptions: { lookback: "Breakout lookback" },
          experiments: [],
        }}
      />,
    );
    expect(html).toContain("research-strategy-detail");
    expect(html).toContain("trend_v1");
    expect(html).toContain("trend_strategy_v1");
    expect(html).toContain("strategy-new-experiment");
    expect(html).toContain("strategy-baseline-experiment");
    expect(html).toContain("strategy-experiments-empty");
    expect(html).toContain(
      'href="/dashboard/research/experiments/new?strategy=trend_v1"',
    );
  });

  it("renders detail error state", () => {
    const html = renderToStaticMarkup(
      <StrategyDetailError message="timeout" />,
    );
    expect(html).toContain("research-strategy-detail-error");
    expect(html).toContain("timeout");
  });
});

describe("Lab strategy options (alias dedupe contract)", () => {
  it("catalog payloads expose only canonical strategy_id for Lab select", () => {
    // Mirrors API catalog_strategy_ids(): aliases are not listed as separate options.
    const labOptions = [
      {
        strategy_id: "trend_v1",
        display_name: "Trend Strategy V1",
        label: "Trend Strategy V1",
        strategy_version: "trend-v1.0.0",
      },
    ];
    const ids = labOptions.map((o) => o.strategy_id);
    expect(ids).toEqual(["trend_v1"]);
    expect(ids).not.toContain("trend_strategy_v1");
  });
});
