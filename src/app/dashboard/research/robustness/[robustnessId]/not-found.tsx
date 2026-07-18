import Link from "next/link";

export default function ResearchRobustnessNotFound() {
  return (
    <div data-testid="robustness-detail-404" className="space-y-3 p-2">
      <h1 className="text-xl font-semibold">Robustheitstest nicht gefunden</h1>
      <p className="text-sm text-text-muted">
        Die Test-ID ist unbekannt oder wurde noch nicht erstellt.
      </p>
      <Link
        href="/dashboard/research/robustness"
        className="text-sm text-mint hover:underline"
      >
        Zurück zur Robustheits-Übersicht
      </Link>
    </div>
  );
}
