import { describe, expect, it } from "vitest";

import { displayValue } from "../../src/lib/research-api/client";
import { isResearchPath, RESEARCH_NAV, WORKSPACE_NAV } from "../../src/lib/research/navigation";

describe("research navigation", () => {
  it("detects research workspace paths", () => {
    expect(isResearchPath("/dashboard/research")).toBe(true);
    expect(isResearchPath("/dashboard/research/experiments")).toBe(true);
    expect(isResearchPath("/dashboard/research/experiments/exp-1")).toBe(true);
    expect(isResearchPath("/dashboard")).toBe(false);
    expect(isResearchPath("/dashboard/positions")).toBe(false);
  });

  it("exposes Monitor/Research workspace links", () => {
    expect(WORKSPACE_NAV.map((n) => n.label)).toEqual(["Monitor", "Research"]);
    expect(WORKSPACE_NAV[1]?.href).toBe("/dashboard/research");
  });

  it("exposes research section nav", () => {
    expect(RESEARCH_NAV.map((n) => n.href)).toEqual([
      "/dashboard/research",
      "/dashboard/research/strategies",
      "/dashboard/research/experiments",
      "/dashboard/research/experiments/new",
      "/dashboard/research/compare",
    ]);
  });
});

describe("research displayValue", () => {
  it("maps nullish to Nicht verfügbar, not zero", () => {
    expect(displayValue(null)).toBe("Nicht verfügbar");
    expect(displayValue(undefined)).toBe("Nicht verfügbar");
    expect(displayValue("")).toBe("Nicht verfügbar");
    expect(displayValue(0)).toBe("0");
    expect(displayValue("0.12")).toBe("0.12");
  });
});
