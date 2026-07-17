import Link from "next/link";

export default function ResearchExperimentNotFound() {
  return (
    <div data-testid="research-detail-404" className="space-y-3 p-2">
      <h1 className="text-xl font-semibold">Experiment nicht gefunden</h1>
      <p className="text-sm text-text-muted">
        Die Experiment-ID ist unbekannt oder nicht in der Registry.
      </p>
      <Link
        href="/dashboard/research/experiments"
        className="text-sm text-mint hover:underline"
      >
        Zurück zur Experimentliste
      </Link>
    </div>
  );
}
