import { RobustnessCreateForm } from "@/components/research/RobustnessCreateForm";
import { RobustnessTable } from "@/components/research/RobustnessTable";
import {
  ResearchApiError,
  ResearchPageHeader,
  rs,
} from "@/components/research/chrome/ResearchPageChrome";
import { fetchPaperApi } from "@/lib/paper-api/client";
import {
  fetchResearchExperiments,
  fetchRobustnessJobs,
  getResearchErrorMessage,
} from "@/lib/research-api/client";

export const dynamic = "force-dynamic";

interface DatasetCatalogItem {
  id: string;
  label: string;
}

export default async function ResearchRobustnessPage() {
  try {
    const [experiments, jobs, datasets] = await Promise.all([
      fetchResearchExperiments({ status: "complete" }),
      fetchRobustnessJobs(),
      fetchPaperApi<{ items: DatasetCatalogItem[] }>("/api/v1/research/datasets", {
        noStore: true,
      }),
    ]);

    return (
      <div data-testid="robustness-page-ready" className={rs.page}>
        <ResearchPageHeader
          title="Robustheit"
          description="Orchestriert Walk-Forward, Cost Stress, Parameter Stability und Bootstrap auf Basis abgeschlossener Experimente — dieselbe Runner/Registry/Artefakt-Linie, keine zweite Backtest-Engine."
        />

        <RobustnessCreateForm
          experiments={experiments.items.map((e) => ({
            experiment_id: e.experiment_id,
            strategy_version: e.strategy_version,
            created_at: e.created_at,
          }))}
          datasets={datasets.items}
        />

        <div>
          <h2 className={rs.sectionTitle}>Läufe</h2>
          <RobustnessTable items={jobs.items} />
        </div>
      </div>
    );
  } catch (error) {
    return (
      <ResearchApiError
        testId="robustness-page-error"
        message={getResearchErrorMessage(error)}
      />
    );
  }
}
