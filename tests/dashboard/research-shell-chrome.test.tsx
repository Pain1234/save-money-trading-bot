import React from "react";
import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";

import { DashboardChrome } from "../../src/components/layout/DashboardChrome";
import { __setMockPathname } from "./mocks/next-navigation";

describe("DashboardChrome", () => {
  it("renders ResearchShell exclusively on research paths", () => {
    __setMockPathname("/dashboard/research/experiments");
    const html = renderToStaticMarkup(
      <DashboardChrome username="demo_user">
        <div data-testid="child-slot">child</div>
      </DashboardChrome>,
    );

    expect(html).toContain('data-testid="research-shell"');
    expect(html).toContain('data-testid="research-topbar"');
    expect(html).toContain('data-testid="research-sidebar"');
    expect(html).toContain('data-testid="research-ticker"');
    expect(html).toContain('data-testid="child-slot"');
    expect(html).not.toContain('data-testid="dashboard-navbar"');
    expect(html).not.toContain('data-testid="dashboard-sidebar"');
  });

  it("renders MonitorShell exclusively on monitor paths", () => {
    __setMockPathname("/dashboard");
    const html = renderToStaticMarkup(
      <DashboardChrome username="demo_user">
        <div data-testid="child-slot">child</div>
      </DashboardChrome>,
    );

    expect(html).toContain('data-testid="dashboard-navbar"');
    expect(html).toContain('data-testid="dashboard-sidebar"');
    expect(html).toContain('data-testid="child-slot"');
    expect(html).not.toContain('data-testid="research-shell"');
    expect(html).not.toContain('data-testid="research-topbar"');
    expect(html).not.toContain('data-testid="research-sidebar"');
  });

  it("does not invent ticker prices", () => {
    __setMockPathname("/dashboard/research");
    const html = renderToStaticMarkup(
      <DashboardChrome username="demo_user">
        <span>x</span>
      </DashboardChrome>,
    );

    expect(html).toContain("BTC");
    expect(html).toContain("ETH");
    expect(html).toContain("SOL");
    expect(html).toContain("Nicht verfügbar");
    expect(html).not.toMatch(/BTC[^<]*\d+\.\d+/);
  });
});
