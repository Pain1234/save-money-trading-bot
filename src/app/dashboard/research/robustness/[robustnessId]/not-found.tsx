import { ResearchNotFound } from "@/components/research/chrome/ResearchPageChrome";

export default function RobustnessNotFound() {
  return (
    <ResearchNotFound
      title="Robustheitstest nicht gefunden"
      backHref="/dashboard/research/robustness"
      backLabel="← Robustheit"
    />
  );
}
