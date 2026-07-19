import React from "react";
import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";

import { ResearchShell } from "../../src/components/research/shell/ResearchShell";

describe("ResearchShell a11y chrome (#303)", () => {
  it("exposes skip link, main landmark id, and footer contentinfo", () => {
    const html = renderToStaticMarkup(
      <ResearchShell username="monitor">
        <p>child</p>
      </ResearchShell>,
    );
    expect(html).toContain('data-testid="research-skip-link"');
    expect(html).toContain('href="#research-main"');
    expect(html).toContain('id="research-main"');
    expect(html).toContain('data-testid="research-main"');
    expect(html).toContain('aria-label="Research content"');
    expect(html).toContain('role="contentinfo"');
    expect(html).not.toMatch(/\bPromote\b|Auto-Promotion|enable live trading/i);
  });
});
