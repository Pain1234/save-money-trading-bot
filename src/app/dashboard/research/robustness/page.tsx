import { RobustnessCreateForm } from "@/components/research/RobustnessCreateForm";
import { RobustnessTable } from "@/components/research/RobustnessTable";
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
      <div data-testid="robustness-page-ready" className="space-y-4">
        <div>
          <h1 className="text-2xl font-semibold">Robustheit</h1>
          <p className="mt-1 text-sm text-text-secondary">
            Orchestriert Walk-Forward, Cost Stress, Parameter Stability und
            Bootstrap auf Basis abgeschlossener Experimente — dieselbe
            Runner/Registry/Artefakt-Linie, keine zweite Backtest-Engine.
          </p>
        </div>

        <RobustnessCreateForm
          experiments={experiments.items.map((e) => ({
            experiment_id: e.experiment_id,
            strategy_version: e.strategy_version,
            created_at: e.created_at,
          }))}
          datasets={datasets.items}
        />

        <div>
          <h2 className="mb-2 text-lg font-medium">Läufe</h2>
          <RobustnessTable items={jobs.items} />
        </div>
      </div>
    );
  } catch (error) {
    return (
      <div
        data-testid="robustness-page-error"
        className="rounded-xl border border-red-500/40 bg-red-500/10 p-6"
      >
        <h1 className="text-xl font-semibold text-red-300">Research API Error</h1>
        <p className="mt-2 text-sm text-red-200/90">
          {getResearchErrorMessage(error)}
        </p>
      </div>
    );
  }
}
