import Link from "next/link";

export default function ResearchValidationDetailNotFound() {
  return (
    <div data-testid="validation-detail-404" className="space-y-3 p-2">
      <h1 className="text-xl font-semibold">Validierungsstudie nicht gefunden</h1>
      <p className="text-sm text-text-muted">
        Die Studien-ID ist unbekannt oder wurde noch nicht erstellt.
      </p>
      <Link
        href="/dashboard/research/validation"
        className="text-sm text-mint hover:underline"
      >
        Zurück zu den Validierungsstudien
      </Link>
    </div>
  );
}
