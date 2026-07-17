import { describe, expect, it } from "vitest";

/** Mirrors StrategyLabForm local validation for unit coverage. */
function validateLabDraft(input: {
  name: string;
  datasetId: string;
  symbols: string[];
  startDate: string;
  endDate: string;
  capital: string;
  entryFee: string;
  exitFee: string;
  slippageBps: string;
}): Record<string, string> {
  const errors: Record<string, string> = {};
  if (!input.name.trim()) errors.name = "Experimentname ist erforderlich";
  if (!input.datasetId) errors.dataset_catalog_id = "Dataset ist erforderlich";
  if (!input.symbols.length) errors.symbols = "Mindestens ein Symbol wählen";
  if (!input.startDate || !input.endDate) errors.time_range = "Zeitraum erforderlich";
  if (input.startDate && input.endDate && input.startDate >= input.endDate) {
    errors.time_range = "Startdatum muss vor Enddatum liegen";
  }
  if (!(Number(input.capital) > 0)) {
    errors.starting_capital = "Startkapital muss positiv sein";
  }
  if (Number(input.entryFee) < 0 || Number(input.exitFee) < 0) {
    errors.fee_assumption = "Gebühren dürfen nicht negativ sein";
  }
  if (Number(input.slippageBps) < 0) {
    errors.slippage_assumption = "Slippage darf nicht negativ sein";
  }
  return errors;
}

describe("strategy lab local validation", () => {
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
