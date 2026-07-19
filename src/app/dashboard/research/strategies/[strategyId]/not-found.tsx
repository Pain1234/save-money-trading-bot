import { ResearchNotFound } from "@/components/research/chrome/ResearchPageChrome";

export default function ResearchStrategyNotFound() {
  return (
    <div data-testid="research-strategy-not-found">
      <ResearchNotFound
        title="Strategie nicht gefunden"
        message="Unbekannte Strategie-ID. Alias-IDs werden aufgelöst; unbekannte IDs bleiben ungültig."
        backHref="/dashboard/research/strategies"
        backLabel="Zurück zum Strategienkatalog"
      />
    </div>
  );
}
