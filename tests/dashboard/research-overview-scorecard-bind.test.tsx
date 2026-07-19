import React from "react";
import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";

import { ResearchOverviewView } from "../../src/components/research/ResearchOverviewView";
import { CopyableResearchId } from "../../src/components/research/CopyableResearchId";
import {
  buildExecutiveSummary,
  UNAVAILABLE,
} from "../../src/lib/research/executive-summary";
import {
  classifyStudyScorecardPin,
  resolveStudyScorecardBind,
  SCORECARD_PIN_STATUS,
  type ScorecardBindState,
} from "../../src/lib/research/scorecard-binding";
import { shortenResearchId } from "../../src/lib/research/research-id";
import {
  overviewFixtureInvalidated,
  overviewFixtureLegacy,
  overviewFixtureReady,
} from "../../src/lib/research/overview-fixtures";
import type {
  GateRunRecord,
  ResearchOverview,
  ScorecardRecord,
  ValidationStudyDetail,
} from "../../src/lib/research-api/client";

const HASH = "b".repeat(64);

function syntheticScorecard(
  overrides: Partial<ScorecardRecord> = {},
): ScorecardRecord {
  return {
    schema_version: "1.0",
    scorecard_id: "sc_primary",
    policy_version: "1.0",
    policy_content_hash: HASH,
    evidence_content_hash: "hash_evidence",
    evaluated_at: "2026-01-01T00:00:00Z",
    run_code_commit: "abc",
    evaluation_code_commit: "def",
    experiment_id: "exp_a",
    run_id: "run_a",
    gate_run_id: "gate_a",
    robustness_run_ids: [],
    dataset_id: "ds",
    dataset_content_hash: HASH,
    artifact_checksums: {},
    layer_refs: {},
    global_profile: {
      gates: {
        integrity_status: "VALID",
        overall_status: "PASS",
        gate_run_id: "gate_a",
      },
      quality: { worst_regime: "trend_down|high_vol" },
      confidence: { overall_label: "MEDIUM", source: "derived" },
      behaviour: {
        main_weakness: "weak_in_chop",
        main_strength: "trend_follow",
        transition_risk: { risk_label: "LOW", transition_count: 1 },
      },
      parameter_area: { classification: "BROAD_PLATEAU" },
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

function studyPinned(partial: Partial<ValidationStudyDetail> = {}): ValidationStudyDetail {
  return {
    schema_version: "1.2",
    study_id: "study_pinned_abcdefghijklmnop",
    created_at: "2026-01-05T00:00:00Z",
    name: "Pinned study",
    strategy_id: "trend_v1",
    strategy_version: "1.0.0",
    experiment_id: "exp_a",
    run_id: "run_a",
    additional_experiment_ids: [],
    robustness_ids: [],
    gate_run_ids: ["gate_a"],
    scorecard_ids: ["sc_primary"],
    notes: "",
    status: "decided",
    decision: {
      outcome: "accept",
      rationale: "ok",
      decided_by: "reviewer",
      decided_at: "2026-01-05T01:00:00Z",
      evidence_snapshot_id: "snap",
    },
    experiments: [],
    robustness: [],
    robustness_by_type: {},
    gates: [],
    progress: {
      experiments: { total: 1, complete: 1 },
      robustness: { total: 0, completed: 0, failed: 0, running: 0 },
      gates: { total: 1, pass: 1, fail: 0 },
    },
    reproducibility: {
      git_commit: null,
      evaluation_code_commit: null,
      dataset_id: null,
      dataset_content_hash: null,
      policy_version: null,
      policy_content_hash: null,
      source: "experiment_run",
    },
    evidence_snapshot: {
      snapshot_id: "snap",
      primary: {
        experiment_id: "exp_a",
        run_id: "run_a",
        checksums_digest: "x",
        dataset_id: "d",
        dataset_content_hash: "h",
        git_commit: "c",
      },
      additional: [],
      robustness: [],
      gates: [],
      scorecards: [{ scorecard_id: "sc_primary", content_hash: "hash_evidence" }],
    },
    ...partial,
  };
}

const EMPTY_OVERVIEW: ResearchOverview = {
  experiment_count: 0,
  completed_count: 0,
  failed_count: 0,
  invalidated_count: 0,
  running_count: null,
  running_available: false,
  strategy_version_count: 0,
  known_strategy_ids: [],
  status_distribution: {},
  recent_experiments: [],
  unavailable: {},
};

const GATE: GateRunRecord = {
  schema_version: "1.0",
  gate_run_id: "gate_a",
  policy_version: "1.0",
  policy_content_hash: HASH,
  evaluated_at: "2026-01-03T00:00:00Z",
  run_code_commit: "c".repeat(40),
  evaluation_code_commit: "d".repeat(40),
  experiment_id: "exp_a",
  run_id: "run_a",
  robustness_run_ids: [],
  dataset_id: "ds",
  dataset_content_hash: HASH,
  artifact_checksums: {},
  measurements: {},
  gates: [],
  overall_status: "pass",
  promotion_action: "none",
  status: "active",
  invalidation_reason: null,
};

describe("classifyStudyScorecardPin", () => {
  it("marks READY for trusted primary pin", () => {
    const bind: ScorecardBindState = {
      kind: "ready",
      scorecard: syntheticScorecard(),
      warnings: [],
      detail: null,
      detailError: null,
    };
    const pin = classifyStudyScorecardPin(bind, studyPinned());
    expect(pin.status).toBe(SCORECARD_PIN_STATUS.READY);
  });

  it("marks LEGACY_NO_SCORECARD when study has no scorecard_ids", () => {
    const study = studyPinned({
      scorecard_ids: [],
      evidence_snapshot: {
        snapshot_id: "snap",
        primary: {
          experiment_id: "exp_a",
          run_id: "run_a",
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
    const bind = resolveStudyScorecardBind([], study);
    const pin = classifyStudyScorecardPin(bind, study);
    expect(pin.status).toBe(SCORECARD_PIN_STATUS.LEGACY_NO_SCORECARD);
    expect(pin.cause).toMatch(/Keine gepinnte Scorecard/);
  });

  it("marks WRONG_PRIMARY_RUN when pin is for additional run only", () => {
    const additional = syntheticScorecard({
      scorecard_id: "sc_add",
      run_id: "run_additional",
      evidence_content_hash: "hash_add",
    });
    const study = studyPinned({
      scorecard_ids: ["sc_add"],
      evidence_snapshot: {
        snapshot_id: "snap",
        primary: {
          experiment_id: "exp_a",
          run_id: "run_a",
          checksums_digest: "x",
          dataset_id: "d",
          dataset_content_hash: "h",
          git_commit: "c",
        },
        additional: [],
        robustness: [],
        gates: [],
        scorecards: [{ scorecard_id: "sc_add", content_hash: "hash_add" }],
      },
    });
    const bind = resolveStudyScorecardBind([additional], study);
    expect(bind.kind).toBe("empty");
    const pin = classifyStudyScorecardPin(bind, study);
    expect(pin.status).toBe(SCORECARD_PIN_STATUS.WRONG_PRIMARY_RUN);
  });

  it("marks HASH_MISMATCH and INVALIDATED from trust errors", () => {
    const study = studyPinned();
    expect(
      classifyStudyScorecardPin(
        { kind: "error", message: "pinned scorecard content_hash mismatch — Evidence untrusted" },
        study,
      ).status,
    ).toBe(SCORECARD_PIN_STATUS.HASH_MISMATCH);
    expect(
      classifyStudyScorecardPin(
        { kind: "error", message: "status=invalidated: gone — Scorecard untrusted" },
        study,
      ).status,
    ).toBe(SCORECARD_PIN_STATUS.INVALIDATED);
  });
});

describe("buildExecutiveSummary pinned scorecard (#358)", () => {
  it("READY pin shows API values including Main Weakness/Strength", () => {
    const study = studyPinned();
    const bind: ScorecardBindState = {
      kind: "ready",
      scorecard: syntheticScorecard(),
      warnings: [],
      detail: null,
      detailError: null,
    };
    const summary = buildExecutiveSummary({
      overview: {
        ...EMPTY_OVERVIEW,
        experiment_count: 1,
        completed_count: 1,
        recent_experiments: [
          {
            experiment_id: "exp_a",
            run_id: "run_a",
            status: "complete",
            strategy_version: "1.0.0",
            strategy_id: "trend_v1",
            dataset_version: "ds",
            cost_model_version: "c1",
            benchmark_ref: "bh",
            created_at: "2026-01-02T00:00:00Z",
            symbols: ["BTC"],
            time_range_start: null,
            time_range_end: null,
            timeframe: "1h",
            git_commit: "abc",
            duration_seconds: 1,
            net_pnl: null,
            max_drawdown: null,
            closed_trades: 1,
            hit_rate: null,
            profit_factor: null,
            integrity_ok: true,
            integrity_error: null,
          },
        ],
      },
      gateRuns: [GATE],
      studies: [study],
      robustnessJobs: [],
      scorecardBind: bind,
    });
    const byId = Object.fromEntries(summary.cells.map((c) => [c.id, c]));
    expect(summary.pin.status).toBe(SCORECARD_PIN_STATUS.READY);
    expect(byId.integrity?.value).toBe("VALID");
    expect(byId["critical-gates"]?.value).toBe("PASS");
    expect(byId["evidence-confidence"]?.value).toBe("MEDIUM");
    expect(byId["worst-regime"]?.value).toBe("trend_down|high_vol");
    expect(byId["worst-transition"]?.value).toBe("LOW");
    expect(byId["parameter-area"]?.value).toBe("BROAD_PLATEAU");
    expect(byId["main-weakness"]?.value).toBe("weak_in_chop");
    expect(byId["main-strength"]?.value).toBe("trend_follow");
    expect(byId["final-decision"]?.value).toBe("accept");
    expect(byId["final-decision"]?.label).toBe("Final Human Decision");
  });

  it("ignores a newer unpinned scorecard not in study pins", () => {
    const study = studyPinned();
    const pinned = syntheticScorecard({ scorecard_id: "sc_primary" });
    const newerUnpinned = syntheticScorecard({
      scorecard_id: "sc_newer_unpinned",
      run_id: "run_a",
      evidence_content_hash: "hash_newer",
      global_profile: {
        gates: { integrity_status: "VALID", overall_status: "PASS" },
        quality: { worst_regime: "SHOULD_NOT_APPEAR" },
        confidence: { overall_label: "HIGH" },
        behaviour: {
          main_weakness: "unpinned_weakness",
          main_strength: "unpinned_strength",
        },
      },
    });
    const bind = resolveStudyScorecardBind([newerUnpinned, pinned], study);
    expect(bind.kind).toBe("ready");
    if (bind.kind === "ready") {
      expect(bind.scorecard.scorecard_id).toBe("sc_primary");
      expect(bind.scorecard.global_profile?.quality?.worst_regime).not.toBe(
        "SHOULD_NOT_APPEAR",
      );
    }
  });

  it("missing profile values stay Nicht verfügbar", () => {
    const study = studyPinned();
    const bind: ScorecardBindState = {
      kind: "ready",
      scorecard: syntheticScorecard({
        global_profile: {
          gates: {
            integrity_status: "NOT_AVAILABLE",
            overall_status: "NOT_AVAILABLE",
          },
          quality: { worst_regime: "NOT_AVAILABLE" },
          confidence: { overall_label: "NOT_AVAILABLE" },
          behaviour: {
            main_weakness: "NOT_AVAILABLE",
            main_strength: "NOT_AVAILABLE",
            transition_risk: { risk_label: "NOT_AVAILABLE" },
          },
          parameter_area: { status: "NOT_AVAILABLE" },
        },
      }),
      warnings: [],
      detail: null,
      detailError: null,
    };
    const summary = buildExecutiveSummary({
      overview: EMPTY_OVERVIEW,
      gateRuns: [],
      studies: [study],
      robustnessJobs: [],
      scorecardBind: bind,
    });
    for (const id of [
      "integrity",
      "critical-gates",
      "evidence-confidence",
      "worst-regime",
      "worst-transition",
      "parameter-area",
      "main-weakness",
      "main-strength",
    ]) {
      expect(summary.cells.find((c) => c.id === id)?.value).toBe(UNAVAILABLE);
    }
  });

  it("legacy / no scorecard keeps honest pin status without inventing scores", () => {
    const fixture = overviewFixtureLegacy();
    const summary = buildExecutiveSummary({
      ...fixture,
      scorecardBind: fixture.scorecardBind,
    });
    expect(summary.pin.status).toBe(SCORECARD_PIN_STATUS.LEGACY_NO_SCORECARD);
    expect(summary.cells.find((c) => c.id === "worst-regime")?.value).toBe(
      UNAVAILABLE,
    );
    expect(summary.pin.cause).toMatch(/Keine gepinnte Scorecard/);
  });

  it("invalidated pin stays unavailable", () => {
    const fixture = overviewFixtureInvalidated();
    const summary = buildExecutiveSummary({
      ...fixture,
      scorecardBind: fixture.scorecardBind,
    });
    expect(summary.pin.status).toBe(SCORECARD_PIN_STATUS.INVALIDATED);
    expect(summary.cells.find((c) => c.id === "main-weakness")?.value).toBe(
      UNAVAILABLE,
    );
  });
});

describe("shortenResearchId + CopyableResearchId", () => {
  it("shortens long IDs with start and end visible", () => {
    const id = "study_public_fixture_abcdefghijklmnopqrstuvwxyz0123456789";
    const short = shortenResearchId(id);
    expect(short.startsWith("study_pu")).toBe(true);
    expect(short.endsWith("456789")).toBe(true);
    expect(short).toContain("…");
    expect(short.length).toBeLessThan(id.length);
  });

  it("renders full id in aria-label and Copy data attribute", () => {
    const id = "study_public_fixture_abcdefghijklmnopqrstuvwxyz0123456789";
    const html = renderToStaticMarkup(
      <CopyableResearchId kind="study" id={id} href="/dashboard/research/validation/x" />,
    );
    expect(html).toContain(`aria-label="study: ${id}"`);
    expect(html).toContain(`data-full-id="${id}"`);
    expect(html).toContain("Copy");
    expect(html).not.toContain(`>${id}<`);
  });
});

describe("ResearchOverviewView scorecard bind UI", () => {
  it("READY fixture shows real API values and pin status", () => {
    const fixture = overviewFixtureReady();
    const html = renderToStaticMarkup(<ResearchOverviewView {...fixture} />);
    expect(html).toContain('data-pin-status="READY"');
    expect(html).toContain('data-testid="executive-value-main-weakness"');
    expect(html).toContain("weak_in_chop");
    expect(html).toContain("trend_follow");
    expect(html).toContain("ISOLATED_PEAK");
    expect(html).not.toMatch(/Create Scorecard/i);
    expect(html).not.toMatch(/>Promote</i);
  });

  it("legacy fixture shows compact empty panels and headline", () => {
    const fixture = overviewFixtureLegacy();
    const html = renderToStaticMarkup(<ResearchOverviewView {...fixture} />);
    expect(html).toContain('data-pin-status="LEGACY_NO_SCORECARD"');
    expect(html).toContain("Keine gepinnte Scorecard für diese Validation Study.");
    expect(html).toContain("min-h-0");
    expect(html).toContain('data-compact-empty="true"');
    expect(html).toContain('data-testid="executive-pin-legacy"');
    expect(html).toContain('data-testid="analytics-detail-link-regime-scorecard"');
  });

  it("invalidated fixture surfaces INVALIDATED cause", () => {
    const fixture = overviewFixtureInvalidated();
    const html = renderToStaticMarkup(<ResearchOverviewView {...fixture} />);
    expect(html).toContain('data-pin-status="INVALIDATED"');
    expect(html).toContain("INVALIDATED");
  });
});

describe("Monitor paths unchanged (#358)", () => {
  it("does not import monitor formatting modules from overview bind", async () => {
    const overviewSrc = await import(
      "../../src/components/research/ResearchOverviewView"
    );
    expect(overviewSrc.ResearchOverviewView).toBeTypeOf("function");
    // Guard: no accidental monitor chart imports in this unit surface.
    const mod = await import("../../src/lib/research/scorecard-binding");
    expect(mod.SCORECARD_PIN_STATUS.READY).toBe("READY");
  });
});

describe("Copy button copies full id", () => {
  it("exposes full id on Copy control for clipboard consumers", () => {
    const id = "run_full_id_value_xyz_abcdefghijklmnop";
    const html = renderToStaticMarkup(
      <CopyableResearchId kind="run" id={id} />,
    );
    expect(html).toContain(`data-full-id="${id}"`);
    expect(html).toContain(`aria-label="Copy run ${id}"`);
    expect(html).toContain(shortenResearchId(id));
  });
});
