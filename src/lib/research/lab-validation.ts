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

/** Inclusive UTC day bounds for Lab payloads (must not exceed DatasetManifest end). */
export function labDayStartUtc(dateYmd: string): string {
  return `${dateYmd}T00:00:00.000000Z`;
}

export function labDayEndUtc(dateYmd: string): string {
  // Whole seconds (.000000), not .999999 — manifests often end at 23:59:59Z.
  return `${dateYmd}T23:59:59.000000Z`;
}

/** Extract YYYY-MM-DD from a catalog/manifest ISO timestamp (Issue #410). */
export function isoTimestampToLabDate(iso: string): string | null {
  const match = /^(\d{4}-\d{2}-\d{2})/.exec(iso.trim());
  return match?.[1] ?? null;
}

export interface DatasetTimeRangeBounds {
  start?: string | null;
  end?: string | null;
}

/**
 * Map catalog ``time_range`` to Lab date inputs. Returns null when bounds are
 * missing or invalid (Max button stays disabled).
 */
export function labDatesFromDatasetTimeRange(
  timeRange: DatasetTimeRangeBounds | null | undefined,
): { startDate: string; endDate: string } | null {
  if (!timeRange?.start || !timeRange?.end) return null;
  const startDate = isoTimestampToLabDate(timeRange.start);
  const endDate = isoTimestampToLabDate(timeRange.end);
  if (!startDate || !endDate || startDate > endDate) return null;
  return { startDate, endDate };
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
