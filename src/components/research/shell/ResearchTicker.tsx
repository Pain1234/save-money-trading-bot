import { RESEARCH_UNIVERSE_SYMBOLS } from "@/lib/research/universe";

/**
 * Research universe strip — labels only.
 * Does not invent live prices or production market data (#298).
 */
export function ResearchTicker() {
  return (
    <div
      className="border-b border-border-subtle bg-bg-elevated"
      data-testid="research-ticker"
      role="region"
      aria-label="Research instrument universe"
    >
      <div className="flex items-center gap-3 overflow-x-auto px-[var(--rs-shell-x)] py-1.5">
        <span className="shrink-0 text-[10px] uppercase tracking-[0.06em] text-text-muted">
          Universe
        </span>
        <ul className="flex min-w-0 items-center gap-2">
          {RESEARCH_UNIVERSE_SYMBOLS.map((symbol) => (
            <li
              key={symbol}
              className="flex shrink-0 items-center gap-1.5 rounded-sm border border-border px-2 py-0.5 font-mono text-[11px]"
            >
              <span className="text-mint">{symbol}</span>
              <span className="text-text-muted">Nicht verfügbar</span>
            </li>
          ))}
        </ul>
        <span className="ml-auto hidden shrink-0 text-[10px] text-text-muted sm:inline">
          Kein Live-Ticker — Research-Labels only
        </span>
      </div>
    </div>
  );
}
