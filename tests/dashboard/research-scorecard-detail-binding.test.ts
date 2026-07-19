import { describe, expect, it } from "vitest";

import {
  evidenceInputEntries,
  gateFailuresUnavailableReason,
  mapCostStressFromDetail,
  mapRegimeRowsFromDetail,
  mapTransitionFromDetail,
  realGateFailures,
} from "../../src/lib/research/scorecard-detail-binding";
import type { ScorecardDetail } from "../../src/lib/research-api/client";
import { UNAVAILABLE } from "../../src/lib/research/executive-summary";

function detailFixture(
  overrides: Partial<ScorecardDetail> = {},
): ScorecardDetail {
  return {
    scorecard_id: "sc_1",
    status: "active",
    decision_binding: false,
    auto_promotion: false,
    promotion_action: "none",
    regime_rows: [],
    transition_risk: { status: "NOT_AVAILABLE", value: null },
    classifier_transitions: {
      status: "NOT_AVAILABLE",
      value: null,
      reason: "missing",
    },
    cost_stress: { status: "NOT_AVAILABLE", value: null, reason: "no_cs" },
    evidence_inputs: { run_id: "run_1", promotion_action: "none" },
    gate_failures: [{ status: "NOT_AVAILABLE", reason: "no_bound_gate_run" }],
    raw_artifact_refs: [],
    missing_data_semantics: { token: "NOT_AVAILABLE", rule: "x" },
    ...overrides,
  };
}

describe("scorecard-detail-binding", () => {
  it("maps regime rows without inventing missing benchmark delta", () => {
    const rows = mapRegimeRowsFromDetail(
      detailFixture({
        regime_rows: [
          {
            cell_id: "down_high",
            quality: { status: "OK", value: "WEAK" },
            confidence: { status: "OK", value: "MEDIUM", scope: "scorecard_overall" },
            behaviour: {
              status: "OK",
              labels: ["weak_trend"],
              main_weakness: "x",
              main_strength: "y",
            },
            trades: { status: "OK", value: 3 },
            net_pnl: { status: "OK", value: "-1" },
            max_drawdown: { status: "OK", value: "-0.5" },
            costs: { status: "NOT_AVAILABLE", value: null },
            benchmark_delta: { status: "NOT_AVAILABLE", value: null },
          },
        ],
      }),
    );
    expect(rows).toHaveLength(1);
    expect(rows[0]?.regime).toBe("down_high");
    expect(rows[0]?.trades).toBe(3);
    expect(rows[0]?.costs).toBeNull();
    expect(rows[0]?.benchmarkDelta).toBeNull();
  });

  it("maps cost stress OK boundary and NA reason", () => {
    const ok = mapCostStressFromDetail({
      status: "OK",
      robustness_run_id: "rob",
      manifest_content_hash: "h",
      boundary: {
        base_net_pnl: "2",
        combined_elevated_net_pnl: "1",
      },
    });
    expect(ok.available).toBe(true);
    expect(ok.elevatedNetPnl).toBe("1");

    const na = mapCostStressFromDetail({
      status: "NOT_AVAILABLE",
      reason: "missing_children",
    });
    expect(na.available).toBe(false);
    expect(na.reason).toContain("missing_children");
  });

  it("filters gate failure sentinel and lists real failures", () => {
    expect(
      realGateFailures([{ reason: "no_bound_gate_run", status: "NOT_AVAILABLE" }]),
    ).toHaveLength(0);
    expect(
      gateFailuresUnavailableReason([
        { reason: "no_bound_gate_run", status: "NOT_AVAILABLE" },
      ]),
    ).toContain("no_bound_gate_run");

    const real = realGateFailures([
      {
        name: "g1",
        outcome: "FAIL",
        passed: false,
        reason: "x",
      },
    ]);
    expect(real).toHaveLength(1);
    expect(gateFailuresUnavailableReason(real)).toBeNull();
  });

  it("maps transition mae NOT_AVAILABLE honestly", () => {
    const t = mapTransitionFromDetail(
      detailFixture({
        transition_risk: {
          status: "OK",
          value: { risk_label: "LOW", mae: "NOT_AVAILABLE", transition_count: 0 },
        },
      }),
    );
    expect(t.riskLabel).toBe("LOW");
    expect(t.mae).toBeNull();
  });

  it("flattens evidence inputs with Nicht verfügbar for empty", () => {
    const entries = evidenceInputEntries({
      run_id: "r1",
      gate_run_id: null,
      global_profile_summary: { x: 1 },
    });
    expect(entries.find((e) => e.key === "run_id")?.value).toBe("r1");
    expect(entries.find((e) => e.key === "gate_run_id")?.value).toBe(
      UNAVAILABLE,
    );
    expect(entries.some((e) => e.key === "global_profile_summary")).toBe(false);
  });
});
