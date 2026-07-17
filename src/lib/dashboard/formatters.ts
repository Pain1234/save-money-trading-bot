const UNAVAILABLE = "—";

/** Format an API decimal string for display without inventing precision. */
export function formatDecimalDisplay(value: string | null | undefined): string {
  if (value == null || value === "") return UNAVAILABLE;
  const trimmed = value.trim();
  if (!trimmed) return UNAVAILABLE;
  // Preserve API string; only add grouping when it is a plain decimal.
  if (!/^-?\d+(\.\d+)?$/.test(trimmed)) return trimmed;
  const negative = trimmed.startsWith("-");
  const unsigned = negative ? trimmed.slice(1) : trimmed;
  const [intPart, fracPart] = unsigned.split(".");
  const grouped = intPart.replace(/\B(?=(\d{3})+(?!\d))/g, ".");
  const body = fracPart != null ? `${grouped},${fracPart}` : grouped;
  return negative ? `-${body}` : body;
}

export function formatMoneyDisplay(value: string | null | undefined): string {
  const body = formatDecimalDisplay(value);
  if (body === UNAVAILABLE) return UNAVAILABLE;
  return body.startsWith("-") ? `-$${body.slice(1)}` : `$${body}`;
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
 * Parse API decimal string to number for chart display only.
 * Returns null when not a finite decimal — never invents values.
 */
export function parseDecimalForChart(
  value: string | null | undefined,
): number | null {
  if (value == null || value === "") return null;
  if (!/^-?\d+(\.\d+)?$/.test(value.trim())) return null;
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

/** Display accent from decimal string sign only (no float accounting). */
export function accentFromSignedDecimal(
  value: string | null | undefined,
): "mint" | "danger" | "default" {
  if (value == null || value === "") return "default";
  const trimmed = value.trim();
  if (!/^-?\d+(\.\d+)?$/.test(trimmed)) return "default";
  if (trimmed.startsWith("-") && !/^[-]?0+(\.0+)?$/.test(trimmed)) {
    return "danger";
  }
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
