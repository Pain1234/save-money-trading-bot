import Link from "next/link";

export default function ResearchStrategyNotFound() {
  return (
    <div data-testid="research-strategy-not-found" className="space-y-3">
      <h1 className="text-xl font-semibold">Strategie nicht gefunden</h1>
      <p className="text-sm text-text-muted">
        Unbekannte Strategie-ID. Alias-IDs werden aufgelöst; unbekannte IDs
        bleiben ungültig.
      </p>
      <Link
        href="/dashboard/research/strategies"
        className="text-sm text-mint hover:underline"
      >
        Zurück zum Strategienkatalog
      </Link>
    </div>
  );
}
