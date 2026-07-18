import { describe, expect, it } from "vitest";

import { displayValue } from "../../src/lib/research-api/client";
import type { ResearchExperimentSummary } from "../../src/lib/research-api/client";

/** Mirrors ExperimentsTable client-side filter/sort for unit coverage. */
function filterExperiments(
  items: ResearchExperimentSummary[],
  opts: { q: string; status: string; strategy: string },
): ResearchExperimentSummary[] {
  const needle = opts.q.trim().toLowerCase();
  return items
    .filter((item) => (opts.status ? item.status === opts.status : true))
    .filter((item) =>
      opts.strategy ? item.strategy_version === opts.strategy : true,
    )
    .filter((item) => {
      if (!needle) return true;
      return (
        item.experiment_id.toLowerCase().includes(needle) ||
        item.strategy_version.toLowerCase().includes(needle)
      );
    })
    .sort((a, b) => b.created_at.localeCompare(a.created_at));
}

function sample(
  overrides: Partial<ResearchExperimentSummary> = {},
): ResearchExperimentSummary {
  return {
    experiment_id: "exp-1",
    run_id: "run-1",
    status: "complete",
    strategy_version: "trend-v1.0.0",
    strategy_id: "trend_v1",
    dataset_version: "ds-1",
    cost_model_version: "1.0",
    benchmark_ref: "bh",
    created_at: "2024-06-01T12:00:00Z",
    symbols: ["BTC"],
    time_range_start: null,
    time_range_end: null,
    timeframe: null,
    git_commit: null,
    duration_seconds: null,
    net_pnl: null,
    max_drawdown: null,
    closed_trades: null,
    hit_rate: null,
    profit_factor: null,
    integrity_ok: true,
    integrity_error: null,
    ...overrides,
  };
}

describe("research experiment list filters", () => {
  const items = [
    sample({ experiment_id: "exp-alpha", status: "complete", created_at: "2024-01-02T00:00:00Z" }),
    sample({
      experiment_id: "exp-beta",
      status: "failed",
      strategy_version: "other",
      created_at: "2024-01-03T00:00:00Z",
    }),
  ];

  it("filters by status, strategy, and search", () => {
    expect(filterExperiments(items, { q: "alpha", status: "", strategy: "" })).toHaveLength(1);
    expect(filterExperiments(items, { q: "", status: "failed", strategy: "" })[0]?.experiment_id).toBe(
      "exp-beta",
    );
    expect(
      filterExperiments(items, { q: "", status: "", strategy: "other" })[0]?.experiment_id,
    ).toBe("exp-beta");
  });

  it("sorts by created_at descending", () => {
    const sorted = filterExperiments(items, { q: "", status: "", strategy: "" });
    expect(sorted[0]?.experiment_id).toBe("exp-beta");
  });

  it("uses Nicht verfügbar for missing metrics, not 0", () => {
    expect(displayValue(items[0]?.net_pnl)).toBe("Nicht verfügbar");
    expect(displayValue(items[0]?.closed_trades)).toBe("Nicht verfügbar");
  });
});
