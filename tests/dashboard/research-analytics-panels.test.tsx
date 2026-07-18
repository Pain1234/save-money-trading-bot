import React from "react";
import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";

import { ResearchAnalyticsSection } from "../../src/components/research/analytics/ResearchAnalyticsSection";
import { RegimeScorecardTable } from "../../src/components/research/analytics/RegimeScorecardTable";
import { UNAVAILABLE } from "../../src/lib/research/executive-summary";

describe("ResearchAnalyticsSection", () => {
  it("renders all panels without fabricating metrics", () => {
    const html = renderToStaticMarkup(
      <ResearchAnalyticsSection evidence={null} />,
    );

    expect(html).toContain('data-testid="research-analytics-section"');
    expect(html).toContain('data-testid="analytics-panel-regime-scorecard"');
    expect(html).toContain('data-testid="analytics-panel-equity-benchmark"');
    expect(html).toContain('data-testid="analytics-panel-underwater-drawdown"');
    expect(html).toContain('data-testid="analytics-panel-transition-matrix"');
    expect(html).toContain('data-testid="analytics-panel-parameter-plateau"');
    expect(html).toContain('data-testid="analytics-panel-cost-stress"');
    expect(html).toContain('data-testid="analytics-panel-evidence-summary"');
    expect(html).toContain(UNAVAILABLE);
    expect(html).not.toMatch(/123\.45|0\.87|demo.?pnl|fabricat/i);
    // No invented regime taxonomy rows without API data.
    expect(html).not.toContain('data-testid="regime-scorecard-table"');
  });

  it("shows evidence anchor without inventing confidence", () => {
    const html = renderToStaticMarkup(
      <ResearchAnalyticsSection
        evidence={{
          studyId: "study_a",
          studyName: "Synthetic",
          experimentId: "exp_a",
          runId: "run_a",
          strategyId: "trend_v1",
          strategyVersion: "1.0.0",
          gateRunIds: [],
          robustnessIds: [],
        }}
      />,
    );
    expect(html).toContain('data-testid="evidence-summary-anchor"');
    expect(html).toContain("study_a");
    expect(html).toContain('data-testid="evidence-confidence-value"');
    expect(html).toContain(UNAVAILABLE);
  });
});

describe("RegimeScorecardTable", () => {
  it("renders provided rows with null cells as Nicht verfügbar", () => {
    const html = renderToStaticMarkup(
      <RegimeScorecardTable
        rows={[
          {
            regime: "trend_up",
            trades: null,
            netPnl: null,
            maxDd: null,
            label: null,
          },
        ]}
      />,
    );
    expect(html).toContain('data-testid="regime-scorecard-table"');
    expect(html).toContain("trend_up");
    expect(html).toContain(UNAVAILABLE);
    expect(html).not.toMatch(/>\s*0\s*</);
  });
});
