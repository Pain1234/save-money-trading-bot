/** Static research instrument universe labels — not a live price feed (#298). */
export const RESEARCH_UNIVERSE_SYMBOLS = ["BTC", "ETH", "SOL"] as const;

export type ResearchUniverseSymbol = (typeof RESEARCH_UNIVERSE_SYMBOLS)[number];
