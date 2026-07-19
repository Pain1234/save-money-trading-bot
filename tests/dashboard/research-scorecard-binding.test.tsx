import React from "react";
import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";

import { ScorecardBindSection } from "../../src/components/research/ScorecardBindSection";
import { ScorecardProfileStrip } from "../../src/components/research/ScorecardProfileStrip";
import {
  BACKEND_NOT_AVAILABLE,
  buildScorecardProfileView,
  evaluateScorecardTrust,
  pickScorecardForPrimaryRun,
  resolveStudyScorecardBind,
  scorecardDisplayValue,
  scorecardToneForStatus,
  studyPrimaryRunId,
} from "../../src/lib/research/scorecard-binding";
import { UNAVAILABLE } from "../../src/lib/research/executive-summary";
import type {
  ScorecardRecord,
  ValidationStudyDetail,
} from "../../src/lib/research-api/client";
import { ParameterPlateauPanel } from "../../src/components/research/analytics/ParameterPlateauPanel";

function syntheticScorecard(
  overrides: Partial<ScorecardRecord> = {},
): ScorecardRecord {
  return {
    schema_version: "1.0",
    scorecard_id: "sc_synthetic_test",
    policy_version: "1.0",
    policy_content_hash: "hash_policy",
    evidence_content_hash: "hash_evidence",
    evaluated_at: "2026-01-01T00:00:00Z",
    run_code_commit: "abc",
    evaluation_code_commit: "def",
    experiment_id: "exp_syn",
    run_id: "run_syn",
    gate_run_id: "gate_syn",
    robustness_run_ids: [],
    dataset_id: "ds_syn",
    dataset_content_hash: "hash_ds",
    artifact_checksums: {},
    layer_refs: {},
    global_profile: {
      gates: {
        gate_run_id: "gate_syn",
        integrity_status: "VALID",
        overall_status: "FAIL",
      },
      quality: {
        worst_regime: "trend_down|high_vol",
        strongest_regime: "trend_up|low_vol",
      },
      confidence: {
        overall_label: "LOW",
        source: "derived",
      },
      behaviour: {
        main_weakness: "weak_in_chop",
        main_strength: "trend_follow",
        transition_risk: {
          risk_label: "ELEVATED",
          transition_count: 3,
          mae: BACKEND_NOT_AVAILABLE,
        },
      },
      parameter_area: {
        classification: "ISOLATED_PEAK",
        classification_reason: "no_contiguous_frozen_plateau",
        parameter_area_id: "pa_syn",
      },
    },
    limitations: [],
    decision_binding: false,
    auto_promotion: false,
    promotion_action: "none",
    status: "active",
    invalidation_reason: null,
    evidence_integrity: { ok: true, error: null },
    ...overrides,
  };
}

describe("scorecardDisplayValue", () => {
  it("maps null and NOT_AVAILABLE to Nicht verfügbar", () => {
    expect(scorecardDisplayValue(null)).toBe(UNAVAILABLE);
    expect(scorecardDisplayValue(BACKEND_NOT_AVAILABLE)).toBe(UNAVAILABLE);
    expect(scorecardDisplayValue("FAIL")).toBe("FAIL");
  });
});

describe("pickScorecardForPrimaryRun", () => {
  it("ignores additional-run scorecards even when listed first", () => {
    const additional = syntheticScorecard({
      scorecard_id: "sc_additional",
      run_id: "run_additional",
    });
    const primary = syntheticScorecard({
      scorecard_id: "sc_primary",
      run_id: "run_primary",
    });
    const picked = pickScorecardForPrimaryRun(
      [additional, primary],
      "run_primary",
    );
    expect(picked?.scorecard_id).toBe("sc_primary");
  });

  it("returns null when only additional-run scorecards exist", () => {
    const additional = syntheticScorecard({
      scorecard_id: "sc_additional",
      run_id: "run_additional",
    });
    expect(pickScorecardForPrimaryRun([additional], "run_primary")).toBeNull();
  });
});

describe("studyPrimaryRunId", () => {
  it("prefers evidence_snapshot.primary.run_id", () => {
    const study = {
      run_id: "run_fallback",
      evidence_snapshot: {
        snapshot_id: "snap",
        primary: {
          experiment_id: "exp",
          run_id: "run_primary",
          checksums_digest: "x",
          dataset_id: "d",
          dataset_content_hash: "h",
          git_commit: "c",
        },
        additional: [],
        robustness: [],
        gates: [],
        scorecards: [],
      },
    } as Pick<ValidationStudyDetail, "run_id" | "evidence_snapshot">;
    expect(studyPrimaryRunId(study)).toBe("run_primary");
  });
});

describe("evaluateScorecardTrust", () => {
  it("fail-closes when evidence_integrity.ok is false", () => {
    const trust = evaluateScorecardTrust(
      syntheticScorecard({
        evidence_integrity: { ok: false, error: "checksum mismatch" },
      }),
    );
    expect(trust.ok).toBe(false);
    if (!trust.ok) {
      expect(trust.message).toContain("checksum mismatch");
    }
  });

  it("fail-closes on pinned content_hash mismatch", () => {
    const trust = evaluateScorecardTrust(
      syntheticScorecard({ evidence_content_hash: "hash_evidence" }),
      "hash_other",
    );
    expect(trust.ok).toBe(false);
    if (!trust.ok) {
      expect(trust.message).toMatch(/content_hash mismatch/i);
    }
  });

  it("fail-closes when scorecard is invalidated", () => {
    const trust = evaluateScorecardTrust(
      syntheticScorecard({
        status: "invalidated",
        invalidation_reason: "superseded",
      }),
    );
    expect(trust.ok).toBe(false);
    if (!trust.ok) {
      expect(trust.message).toMatch(/invalidated/);
    }
  });

  it("fail-closes when study requires pin hash but none provided", () => {
    const trust = evaluateScorecardTrust(syntheticScorecard(), null, {
      requirePinHash: true,
    });
    expect(trust.ok).toBe(false);
    if (!trust.ok) {
      expect(trust.message).toMatch(/ungepinnt/i);
    }
  });
});

describe("resolveStudyScorecardBind", () => {
  const primaryPin = {
    scorecard_id: "sc_primary",
    content_hash: "hash_evidence",
  };

  function studyFixture(
    overrides: Partial<ValidationStudyDetail> = {},
  ): Pick<
    ValidationStudyDetail,
    "run_id" | "evidence_snapshot" | "scorecard_ids"
  > {
    return {
      run_id: "run_primary",
      scorecard_ids: ["sc_additional", "sc_primary"],
      evidence_snapshot: {
        snapshot_id: "snap",
        primary: {
          experiment_id: "exp",
          run_id: "run_primary",
          checksums_digest: "x",
          dataset_id: "d",
          dataset_content_hash: "h",
          git_commit: "c",
        },
        additional: [],
        robustness: [],
        gates: [],
        scorecards: [
          { scorecard_id: "sc_additional", content_hash: "hash_add" },
          primaryPin,
        ],
      },
      ...overrides,
    };
  }

  it("binds only the pinned primary-run scorecard", () => {
    const additional = syntheticScorecard({
      scorecard_id: "sc_additional",
      run_id: "run_additional",
      evidence_content_hash: "hash_add",
    });
    const primary = syntheticScorecard({
      scorecard_id: "sc_primary",
      run_id: "run_primary",
      evidence_content_hash: "hash_evidence",
    });
    const bind = resolveStudyScorecardBind(
      [additional, primary],
      studyFixture(),
    );
    expect(bind.kind).toBe("ready");
    if (bind.kind === "ready") {
      expect(bind.scorecard.scorecard_id).toBe("sc_primary");
    }
  });

  it("does not fall back to unpinned registry scorecards for primary run", () => {
    const unpinnedPrimary = syntheticScorecard({
      scorecard_id: "sc_unpinned_primary",
      run_id: "run_primary",
      evidence_content_hash: "hash_other",
    });
    const additionalOnly = syntheticScorecard({
      scorecard_id: "sc_additional",
      run_id: "run_additional",
      evidence_content_hash: "hash_add",
    });
    // Fetched list is only the additional pin — must not invent unpinned primary.
    const bind = resolveStudyScorecardBind(
      [additionalOnly, unpinnedPrimary],
      studyFixture({
        scorecard_ids: ["sc_additional"],
        evidence_snapshot: {
          snapshot_id: "snap",
          primary: {
            experiment_id: "exp",
            run_id: "run_primary",
            checksums_digest: "x",
            dataset_id: "d",
            dataset_content_hash: "h",
            git_commit: "c",
          },
          additional: [],
          robustness: [],
          gates: [],
          scorecards: [
            { scorecard_id: "sc_additional", content_hash: "hash_add" },
          ],
        },
      }),
    );
    expect(bind.kind).toBe("empty");
    if (bind.kind === "empty") {
      expect(bind.reason).toMatch(/ungepinnte Registry/i);
    }
  });

  it("fail-closes when primary match lacks snapshot pin hash", () => {
    const primary = syntheticScorecard({
      scorecard_id: "sc_primary",
      run_id: "run_primary",
    });
    const bind = resolveStudyScorecardBind([primary], {
      run_id: "run_primary",
      scorecard_ids: ["sc_primary"],
      evidence_snapshot: {
        snapshot_id: "snap",
        primary: {
          experiment_id: "exp",
          run_id: "run_primary",
          checksums_digest: "x",
          dataset_id: "d",
          dataset_content_hash: "h",
          git_commit: "c",
        },
        additional: [],
        robustness: [],
        gates: [],
        scorecards: [],
      },
    });
    expect(bind.kind).toBe("error");
    if (bind.kind === "error") {
      expect(bind.message).toMatch(/ungepinnt/i);
    }
  });

  it("stays empty when study has no scorecard pins (no run_id registry fallback)", () => {
    const bind = resolveStudyScorecardBind([], {
      run_id: "run_primary",
      scorecard_ids: [],
      evidence_snapshot: {
        snapshot_id: "snap",
        primary: {
          experiment_id: "exp",
          run_id: "run_primary",
          checksums_digest: "x",
          dataset_id: "d",
          dataset_content_hash: "h",
          git_commit: "c",
        },
        additional: [],
        robustness: [],
        gates: [],
        scorecards: [],
      },
    });
    expect(bind.kind).toBe("empty");
    if (bind.kind === "empty") {
      expect(bind.reason).toMatch(/Registry-Fallback unterdrückt/);
    }
  });
});

describe("scorecardToneForStatus", () => {
  it("marks ISOLATED_PEAK as warning, not mint", () => {
    expect(scorecardToneForStatus("ISOLATED_PEAK")).toBe("warning");
    expect(scorecardToneForStatus("BROAD_PLATEAU")).toBe("mint");
  });
});

describe("ParameterPlateauPanel tone", () => {
  it("does not paint ISOLATED_PEAK mint", () => {
    const html = renderToStaticMarkup(
      <ParameterPlateauPanel classification="ISOLATED_PEAK" />,
    );
    expect(html).toContain('data-tone="warning"');
    expect(html).toContain("text-warning");
    expect(html).not.toMatch(/parameter-plateau-classification[^>]*text-mint/);
  });
});

describe("buildScorecardProfileView", () => {
  it("binds backend profile fields without inventing metrics", () => {
    const profile = buildScorecardProfileView(syntheticScorecard(), {
      finalDecision: { outcome: "reject", detail: "human · 2026-01-02" },
    });

    const byId = Object.fromEntries(profile.cells.map((c) => [c.id, c]));
    expect(byId.integrity?.value).toBe("VALID");
    expect(byId["critical-gates"]?.value).toBe("FAIL");
    expect(byId["critical-gates"]?.tone).toBe("danger");
    expect(byId["worst-regime"]?.value).toBe("trend_down|high_vol");
    expect(byId["worst-transition"]?.value).toBe("ELEVATED");
    expect(byId["cost-stress"]?.value).toBe(UNAVAILABLE);
    expect(byId["parameter-area"]?.value).toBe("ISOLATED_PEAK");
    expect(byId["parameter-area"]?.tone).toBe("warning");
    expect(byId["evidence-confidence"]?.value).toBe("LOW");
    expect(byId["main-weakness"]?.value).toBe("weak_in_chop");
    expect(byId["final-decision"]?.value).toBe("reject");
    expect(profile.parameterClassification).toBe("ISOLATED_PEAK");
    expect(profile.confidenceLabel).toBe("LOW");
  });

  it("keeps NOT_AVAILABLE cells as Nicht verfügbar", () => {
    const profile = buildScorecardProfileView(
      syntheticScorecard({
        global_profile: {
          gates: {
            integrity_status: BACKEND_NOT_AVAILABLE,
            overall_status: BACKEND_NOT_AVAILABLE,
          },
          quality: { worst_regime: BACKEND_NOT_AVAILABLE },
          confidence: { overall_label: BACKEND_NOT_AVAILABLE },
          behaviour: {
            main_weakness: BACKEND_NOT_AVAILABLE,
            transition_risk: { risk_label: BACKEND_NOT_AVAILABLE },
          },
          parameter_area: { status: BACKEND_NOT_AVAILABLE },
        },
      }),
    );
    for (const cell of profile.cells) {
      if (cell.id === "final-decision" || cell.id === "cost-stress") continue;
      expect(cell.value).toBe(UNAVAILABLE);
    }
  });
});

describe("ScorecardProfileStrip", () => {
  it("renders profile without promotion controls or demo numbers", () => {
    const profile = buildScorecardProfileView(syntheticScorecard());
    const html = renderToStaticMarkup(
      <ScorecardProfileStrip profile={profile} />,
    );
    expect(html).toContain('data-testid="scorecard-profile-strip"');
    expect(html).toContain("sc_synthetic_test");
    expect(html).toContain('data-testid="scorecard-value-critical-gates"');
    expect(html).toContain("FAIL");
    expect(html).not.toMatch(/Promote|Auto-Promotion|123\.45/i);
  });
});

describe("ScorecardBindSection", () => {
  it("shows empty state without fabricating metrics", () => {
    const html = renderToStaticMarkup(
      <ScorecardBindSection
        bind={{ kind: "empty", reason: "Keine Scorecards" }}
      />,
    );
    expect(html).toContain('data-testid="scorecard-bind-empty"');
    expect(html).toContain("Keine Scorecards");
    expect(html).toContain('data-testid="research-analytics-section"');
    expect(html).toContain(UNAVAILABLE);
  });

  it("shows error state without inventing scores", () => {
    const html = renderToStaticMarkup(
      <ScorecardBindSection
        bind={{ kind: "error", message: "API down" }}
      />,
    );
    expect(html).toContain('data-testid="scorecard-bind-error"');
    expect(html).toContain("API down");
  });

  it("binds ready scorecard into profile + analytics", () => {
    const html = renderToStaticMarkup(
      <ScorecardBindSection
        bind={{
          kind: "ready",
          scorecard: syntheticScorecard(),
          warnings: [],
        }}
      />,
    );
    expect(html).toContain('data-testid="scorecard-bind-ready"');
    expect(html).toContain('data-testid="scorecard-profile-strip"');
    expect(html).toContain('data-testid="parameter-plateau-bound"');
    expect(html).toContain("ISOLATED_PEAK");
    expect(html).toContain('data-tone="warning"');
    expect(html).toContain('data-testid="transition-risk-bound"');
    expect(html).toContain("ELEVATED");
    expect(html).toContain('data-testid="evidence-confidence-value"');
    expect(html).toContain("LOW");
    expect(html).not.toContain('data-testid="regime-scorecard-table"');
  });
});
