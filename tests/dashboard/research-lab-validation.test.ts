import { describe, expect, it } from "vitest";

import {
  isActiveJobStatus,
  labDayEndUtc,
  labDayStartUtc,
  validateLabDraft,
} from "../../src/lib/research/lab-validation";

describe("labDayStartUtc / labDayEndUtc", () => {
  it("uses whole-second end bounds (not .999999) for manifest-safe windows", () => {
    expect(labDayStartUtc("2024-01-31")).toBe("2024-01-31T00:00:00.000000Z");
    expect(labDayEndUtc("2024-01-31")).toBe("2024-01-31T23:59:59.000000Z");
    expect(labDayEndUtc("2024-01-31")).not.toContain(".999999");
  });
});

describe("validateLabDraft (shared with StrategyLabForm)", () => {
  it("accepts a complete draft", () => {
    expect(
      validateLabDraft({
        name: "test",
        datasetId: "fixture-btc",
        symbols: ["BTC"],
        startDate: "2024-01-01",
        endDate: "2024-02-01",
        capital: "100000",
        entryFee: "0.0005",
        exitFee: "0.0005",
        slippageBps: "5",
      }),
    ).toEqual({});
  });

  it("rejects inverted dates and non-positive capital", () => {
    const errors = validateLabDraft({
      name: "",
      datasetId: "",
      symbols: [],
      startDate: "2024-02-01",
      endDate: "2024-01-01",
      capital: "0",
      entryFee: "-1",
      exitFee: "0",
      slippageBps: "-2",
    });
    expect(errors.name).toBeTruthy();
    expect(errors.dataset_catalog_id).toBeTruthy();
    expect(errors.symbols).toBeTruthy();
    expect(errors.time_range).toMatch(/vor Enddatum/);
    expect(errors.starting_capital).toBeTruthy();
    expect(errors.fee_assumption).toBeTruthy();
    expect(errors.slippage_assumption).toBeTruthy();
  });
});

describe("isActiveJobStatus", () => {
  it("marks lifecycle states that should poll", () => {
    expect(isActiveJobStatus("created")).toBe(true);
    expect(isActiveJobStatus("queued")).toBe(true);
    expect(isActiveJobStatus("running")).toBe(true);
    expect(isActiveJobStatus("completed")).toBe(false);
    expect(isActiveJobStatus("failed")).toBe(false);
  });
});
