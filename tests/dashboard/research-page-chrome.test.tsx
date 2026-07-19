import React from "react";
import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";

import {
  ResearchApiError,
  ResearchEmpty,
  ResearchLoadingSkeleton,
  ResearchNotFound,
  ResearchPageHeader,
  ResearchTableFrame,
  rs,
} from "../../src/components/research/chrome/ResearchPageChrome";
import { StrategiesCatalogView } from "../../src/components/research/StrategiesCatalogView";
import { UNAVAILABLE } from "../../src/lib/research/executive-summary";

describe("ResearchPageChrome (#301)", () => {
  it("renders dense page header without marketing heroes", () => {
    const html = renderToStaticMarkup(
      <ResearchPageHeader
        title="Experiments"
        description="Dense research list"
        actions={<a className={rs.btnPrimary}>Neues Experiment</a>}
      />,
    );
    expect(html).toContain("Experiments");
    expect(html).toContain("text-[18px]");
    expect(html).not.toContain("text-2xl");
  });

  it("renders fail-closed API error as rounded-sm", () => {
    const html = renderToStaticMarkup(
      <ResearchApiError testId="research-strategies-error" message="API down" />,
    );
    expect(html).toContain("research-strategies-error");
    expect(html).toContain("API down");
    expect(html).toContain("rounded-sm");
    expect(html).not.toContain("rounded-xl");
  });

  it("renders empty, loading, not-found, and table frame", () => {
    expect(
      renderToStaticMarkup(
        <ResearchEmpty testId="e" title="T" message="Keine Daten" />,
      ),
    ).toContain("Keine Daten");
    expect(
      renderToStaticMarkup(<ResearchLoadingSkeleton testId="load" />),
    ).toContain('data-testid="load"');
    expect(
      renderToStaticMarkup(<ResearchLoadingSkeleton />),
    ).toContain('data-testid="research-loading"');
    expect(
      renderToStaticMarkup(
        <ResearchNotFound
          title="Nicht gefunden"
          backHref="/dashboard/research"
          backLabel="Zurück"
        />,
      ),
    ).toContain("Nicht gefunden");
    expect(
      renderToStaticMarkup(
        <ResearchTableFrame>
          <table className={rs.table}>
            <tbody>
              <tr>
                <td className={rs.td}>{UNAVAILABLE}</td>
              </tr>
            </tbody>
          </table>
        </ResearchTableFrame>,
      ),
    ).toContain("rounded-sm");
  });

  it("strategies catalog uses dense chrome tokens", () => {
    const html = renderToStaticMarkup(
      <StrategiesCatalogView
        items={[
          {
            strategy_id: "trend_v1",
            display_name: "Trend Strategy V1",
            description: "Long-only",
            strategy_version: "1.0.0",
            lifecycle_status: "research",
            supported_symbols: ["BTC"],
            required_timeframes: ["1D"],
            experiment_count: 0,
            last_run: null,
          },
        ]}
      />,
    );
    expect(html).toContain("research-strategies-ready");
    expect(html).not.toContain("text-2xl");
    expect(html).toContain("text-[18px]");
  });
});
