const UNAVAILABLE = "—";

/** Inputs accepted by Monitor display formatters (display-only; never mutate API values). */
export type NumericDisplayInput =
  | string
  | number
  | null
  | undefined
  | { toString(): string };

const MONEY_FRACTION_DIGITS = 2;
const DECIMAL_MAX_FRACTION_DIGITS = 8;

/** Plain decimal or scientific notation (optional leading sign). */
const NUMERIC_INPUT_RE =
  /^[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?$/;

function normalizeNegativeZero(n: number): number {
  return Object.is(n, -0) ? 0 : n;
}

/**
 * Parse a display input to a finite number.
 * Accepts scientific notation; rejects NaN/Infinity/invalid strings.
 * Normalizes -0 to 0. Display-only — does not invent missing values.
 */
export function toFiniteNumber(value: NumericDisplayInput): number | null {
  if (value == null) return null;
  if (typeof value === "number") {
    if (!Number.isFinite(value)) return null;
    return normalizeNegativeZero(value);
  }
  const raw =
    typeof value === "string"
      ? value.trim()
      : String(value.toString()).trim();
  if (!raw || !NUMERIC_INPUT_RE.test(raw)) return null;
  const n = Number(raw);
  if (!Number.isFinite(n)) return null;
  return normalizeNegativeZero(n);
}

/** Format a quantity/size for Monitor display (en-US, no currency symbol). */
export function formatDecimalDisplay(value: NumericDisplayInput): string {
  const n = toFiniteNumber(value);
  if (n == null) return UNAVAILABLE;
  return n.toLocaleString("en-US", {
    maximumFractionDigits: DECIMAL_MAX_FRACTION_DIGITS,
  });
}

/** Format a monetary value for Monitor display (en-US: `$100,000.00`). */
export function formatMoneyDisplay(value: NumericDisplayInput): string {
  const n = toFiniteNumber(value);
  if (n == null) return UNAVAILABLE;
  const body = Math.abs(n).toLocaleString("en-US", {
    minimumFractionDigits: MONEY_FRACTION_DIGITS,
    maximumFractionDigits: MONEY_FRACTION_DIGITS,
  });
  return n < 0 ? `-$${body}` : `$${body}`;
}

export function formatHeartbeatAge(seconds: number | null | undefined): string {
  if (seconds == null || Number.isNaN(seconds)) return "unbekannt";
  if (seconds < 60) return `${Math.round(seconds)}s`;
  if (seconds < 3600) return `${Math.round(seconds / 60)}m`;
  return `${Math.round(seconds / 3600)}h`;
}

export function formatIsoDateTime(iso: string | null | undefined): string {
  if (!iso) return UNAVAILABLE;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return new Intl.DateTimeFormat("de-DE", {
    dateStyle: "short",
    timeStyle: "short",
  }).format(d);
}

/**
 * Parse API decimal string/number to a finite number for chart display only.
 * Returns null when not finite — never invents values.
 */
export function parseDecimalForChart(
  value: NumericDisplayInput,
): number | null {
  return toFiniteNumber(value);
}

/** Y-domain for absolute equity charts (padded; flat series get ±1). */
export function computeEquityYDomain(values: number[]): [number, number] {
  if (values.length === 0) return [0, 1];
  const finite = values.filter((v) => Number.isFinite(v));
  if (finite.length === 0) return [0, 1];
  const min = Math.min(...finite);
  const max = Math.max(...finite);
  const pad = (max - min) * 0.06 || 1;
  return [Math.floor(min - pad), Math.ceil(max + pad)];
}

/**
 * Format an absolute-equity Y-axis tick.
 * Tight domains (e.g. ~100k) use full dollar labels so ticks stay distinct;
 * wide domains may use a `k` abbreviation with enough fraction digits.
 */
export function formatEquityAxisTick(
  value: number,
  domain: readonly [number, number],
): string {
  if (!Number.isFinite(value)) return UNAVAILABLE;
  const v = normalizeNegativeZero(value);
  const span = Math.abs(domain[1] - domain[0]);

  // Tight ranges: full dollars so neighbouring ticks do not collapse to `100.0k`.
  if (span < 5000) {
    const fractionDigits = span < 10 ? 2 : span < 100 ? 1 : 0;
    const body = Math.abs(v).toLocaleString("en-US", {
      minimumFractionDigits: fractionDigits,
      maximumFractionDigits: fractionDigits,
    });
    return v < 0 ? `-$${body}` : `$${body}`;
  }

  if (Math.abs(v) >= 1000) {
    const kSpan = span / 1000;
    const decimals = kSpan < 1 ? 3 : kSpan < 10 ? 2 : 1;
    const signed = v < 0 ? "-" : "";
    return `${signed}$${(Math.abs(v) / 1000).toFixed(decimals)}k`;
  }

  return formatMoneyDisplay(v);
}

/** Display accent from numeric sign only (no float accounting). */
export function accentFromSignedDecimal(
  value: NumericDisplayInput,
): "mint" | "danger" | "default" {
  const n = toFiniteNumber(value);
  if (n == null) return "default";
  if (n < 0) return "danger";
  return "mint";
}

export function coinInitial(symbol: string): string {
  const s = symbol.trim();
  return s ? s[0]!.toUpperCase() : "?";
}

export function coinColor(symbol: string): string {
  const key = symbol.trim().toUpperCase();
  const map: Record<string, string> = {
    BTC: "#f7931a",
    ETH: "#627eea",
    SOL: "#9945ff",
  };
  return map[key] ?? "#42d98b";
}

export { UNAVAILABLE };
