/** Shared Strategy Lab client-side validation (Issue #242). */

export interface LabDraftInput {
  name: string;
  datasetId: string;
  symbols: string[];
  startDate: string;
  endDate: string;
  capital: string;
  entryFee: string;
  exitFee: string;
  slippageBps: string;
}

export function validateLabDraft(input: LabDraftInput): Record<string, string> {
  const errors: Record<string, string> = {};
  if (!input.name.trim()) errors.name = "Experimentname ist erforderlich";
  if (!input.datasetId) errors.dataset_catalog_id = "Dataset ist erforderlich";
  if (!input.symbols.length) errors.symbols = "Mindestens ein Symbol wählen";
  if (!input.startDate || !input.endDate) {
    errors.time_range = "Zeitraum erforderlich";
  }
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

export function isActiveJobStatus(status: string): boolean {
  return status === "created" || status === "queued" || status === "running";
}
