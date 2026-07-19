import { ResearchNotFound } from "@/components/research/chrome/ResearchPageChrome";

export default function ExperimentNotFound() {
  return (
    <ResearchNotFound
      title="Experiment nicht gefunden"
      backHref="/dashboard/research/experiments"
      backLabel="← Experiments"
    />
  );
}
