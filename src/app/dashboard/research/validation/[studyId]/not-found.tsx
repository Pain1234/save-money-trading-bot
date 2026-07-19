import { ResearchNotFound } from "@/components/research/chrome/ResearchPageChrome";

export default function ResearchValidationDetailNotFound() {
  return (
    <div data-testid="validation-detail-404">
      <ResearchNotFound
        title="Validierungsstudie nicht gefunden"
        message="Die Studien-ID ist unbekannt oder wurde noch nicht erstellt."
        backHref="/dashboard/research/validation"
        backLabel="Zurück zu den Validierungsstudien"
      />
    </div>
  );
}
