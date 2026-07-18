import React from "react";
import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";

import { ResearchAnalyticsSection } from "../../src/components/research/analytics/ResearchAnalyticsSection";
import { RegimeScorecardTable } from "../../src/components/research/analytics/RegimeScorecardTable";
import { UnderwaterDrawdownChart } from "../../src/components/research/analytics/UnderwaterDrawdownChart";
import {
  pinnedRunMatchesDetail,
  sanitizeDrawdownSeries,
  sanitizeEquitySeries,
} from "../../src/lib/research/analytics-series";
import {
  toEvidenceAnchor,
  UNAVAILABLE,
} from "../../src/lib/research/executive-summary";
import type { ValidationStudyDetail } from "../../src/lib/research-api/client";

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

describe("pinnedRunMatchesDetail", () => {
  const evidence = {
    studyId: "study_a",
    studyName: "Synthetic",
    experimentId: "exp_a",
    runId: "run_pinned",
    strategyId: "trend_v1",
    strategyVersion: "1.0.0",
    gateRunIds: [],
    robustnessIds: [],
  };

  it("accepts only the exact pinned run_id", () => {
    expect(
      pinnedRunMatchesDetail(evidence, {
        summary: {
          experiment_id: "exp_a",
          run_id: "run_pinned",
        } as never,
      }),
    ).toBe(true);
  });

  it("rejects a newer registry run for the same experiment", () => {
    expect(
      pinnedRunMatchesDetail(evidence, {
        summary: {
          experiment_id: "exp_a",
          run_id: "run_latest_newer",
        } as never,
      }),
    ).toBe(false);
  });

  it("rejects when evidence has no run pin (no latest-run fallback)", () => {
    expect(
      pinnedRunMatchesDetail(
        { ...evidence, runId: null },
        {
          summary: {
            experiment_id: "exp_a",
            run_id: "run_latest",
          } as never,
        },
      ),
    ).toBe(false);
  });

  it("uses evidence_snapshot primary run from toEvidenceAnchor", () => {
    const study = {
      study_id: "study_snap",
      name: "Snap study",
      experiment_id: "exp_stale",
      run_id: "run_stale",
      strategy_id: "trend_v1",
      strategy_version: "1.0.0",
      gate_run_ids: [],
      robustness_ids: [],
      evidence_snapshot: {
        snapshot_id: "snap_1",
        primary: {
          experiment_id: "exp_a",
          run_id: "run_pinned",
          checksums_digest: "a".repeat(64),
          dataset_id: "ds",
          dataset_content_hash: "b".repeat(64),
          git_commit: "c".repeat(40),
        },
        additional: [],
        robustness: [],
        gates: [],
      },
    } as unknown as ValidationStudyDetail;

    const anchor = toEvidenceAnchor(study);
    expect(anchor.experimentId).toBe("exp_a");
    expect(anchor.runId).toBe("run_pinned");
    expect(
      pinnedRunMatchesDetail(anchor, {
        summary: {
          experiment_id: "exp_a",
          run_id: "run_pinned",
        } as never,
      }),
    ).toBe(true);
    expect(
      pinnedRunMatchesDetail(anchor, {
        summary: {
          experiment_id: "exp_a",
          run_id: "run_stale",
        } as never,
      }),
    ).toBe(false);
  });
});

describe("sanitizeDrawdownSeries", () => {
  it("drops points with missing drawdown instead of inventing 0", () => {
    const cleaned = sanitizeDrawdownSeries([
      { t: "a", drawdown: -0.1 },
      { t: "b" },
      { t: "c", drawdown: undefined },
      { t: "d", equity: 1 },
    ]);
    expect(cleaned).toEqual([{ t: "a", drawdown: -0.1 }]);
  });

  it("returns empty when every point lacks drawdown", () => {
    expect(sanitizeDrawdownSeries([{ t: "a" }, { t: "b", equity: 1 }])).toEqual(
      [],
    );
  });
});

describe("sanitizeEquitySeries", () => {
  it("drops points without equity values", () => {
    expect(
      sanitizeEquitySeries([{ t: "a", equity: 10 }, { t: "b", drawdown: -0.1 }]),
    ).toEqual([{ t: "a", equity: 10 }]);
  });
});

describe("UnderwaterDrawdownChart", () => {
  it("shows Nicht verfügbar when drawdown values are missing (no fake zeros)", () => {
    const html = renderToStaticMarkup(
      <UnderwaterDrawdownChart
        drawdown={[{ t: "2024-01-01" }, { t: "2024-01-02", equity: 100 }]}
      />,
    );
    expect(html).toContain(
      'data-testid="analytics-unavailable-underwater-drawdown"',
    );
    expect(html).not.toContain('data-testid="underwater-drawdown-chart"');
    expect(html).not.toMatch(/drawdown["\s:=]+0/);
  });
});
