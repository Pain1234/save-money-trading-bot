import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { ResearchForensicsSection } from "@/components/research/ResearchForensicsSection";
import { scorecardArtifactContentHref } from "@/lib/research-api/client";
import type { ScorecardDetail } from "@/lib/research-api/client";

function detailWithRefs(
  refs: ScorecardDetail["raw_artifact_refs"],
): ScorecardDetail {
  return {
    scorecard_id: "sc_forensics_357",
    status: "active",
    decision_binding: false,
    auto_promotion: false,
    promotion_action: "none",
    regime_rows: [],
    transition_risk: { status: "NOT_AVAILABLE", value: null },
    classifier_transitions: { status: "NOT_AVAILABLE", value: null },
    cost_stress: { status: "NOT_AVAILABLE" },
    evidence_inputs: {},
    gate_failures: [],
    raw_artifact_refs: refs,
    missing_data_semantics: { token: "NOT_AVAILABLE", rule: "do not coerce" },
  };
}

describe("scorecardArtifactContentHref (#357)", () => {
  it("returns auth-bound href only when present+OK run path", () => {
    const href = scorecardArtifactContentHref("sc_1", {
      name: "regime_metrics.json",
      relative_path: "regime_metrics.json",
      present: true,
      status: "OK",
      checksum_sha256: "abc",
    });
    expect(href).toBe(
      "/api/research/scorecards/sc_1/artifacts/content?relative_path=regime_metrics.json",
    );
  });

  it("returns null for NOT_AVAILABLE / absent / scorecards path", () => {
    expect(
      scorecardArtifactContentHref("sc_1", {
        name: "missing",
        relative_path: "regime_metrics.json",
        present: false,
        status: "OK",
      }),
    ).toBeNull();
    expect(
      scorecardArtifactContentHref("sc_1", {
        name: "na",
        relative_path: "regime_metrics.json",
        present: true,
        status: "NOT_AVAILABLE",
      }),
    ).toBeNull();
    expect(
      scorecardArtifactContentHref("sc_1", {
        name: "scorecard_record",
        relative_path: "scorecards/sc_1.json",
        present: true,
        status: "OK",
      }),
    ).toBeNull();
  });
});

describe("ResearchForensicsSection artifact links (#357)", () => {
  it("links only when artifact accessible; otherwise Nicht verfügbar", () => {
    const html = renderToStaticMarkup(
      <ResearchForensicsSection
        detail={detailWithRefs([
          {
            name: "regime_metrics.json",
            relative_path: "regime_metrics.json",
            checksum_sha256: "abc",
            present: true,
            status: "OK",
          },
          {
            name: "absent.json",
            relative_path: "absent.json",
            checksum_sha256: null,
            present: false,
            status: "NOT_AVAILABLE",
          },
        ])}
      />,
    );
    expect(html).toContain(
      'data-testid="raw-artifact-content-link-regime_metrics.json"',
    );
    expect(html).toContain(
      "/api/research/scorecards/sc_forensics_357/artifacts/content?relative_path=regime_metrics.json",
    );
    expect(html).toContain(
      'data-testid="raw-artifact-content-unavailable-absent.json"',
    );
    expect(html).toContain("Nicht verfügbar");
    expect(html).not.toContain('href=""');
    expect(html).not.toMatch(/C:\\\\|\/Users\/|artifacts\/research\/exp/);
  });
});
