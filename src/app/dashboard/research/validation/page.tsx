import { ValidationStudyCreateForm } from "@/components/research/ValidationStudyCreateForm";
import { ValidationStudiesTable } from "@/components/research/ValidationStudiesTable";
import {
  fetchGateRuns,
  fetchResearchExperiments,
  fetchRobustnessJobs,
  fetchValidationStudies,
  getResearchErrorMessage,
} from "@/lib/research-api/client";

export const dynamic = "force-dynamic";

export default async function ResearchValidationPage() {
  try {
    const [experiments, robustnessJobs, gateRuns, studies] = await Promise.all([
      fetchResearchExperiments({ status: "complete" }),
      fetchRobustnessJobs(),
      fetchGateRuns(),
      fetchValidationStudies(),
    ]);

    return (
      <div data-testid="validation-page-ready" className="space-y-4">
        <div>
          <h1 className="text-2xl font-semibold">Validierungsstudien</h1>
          <p className="mt-1 text-sm text-text-secondary">
            Fasst Experimente, Robustheitstests (#247) und Gate-Ergebnisse
            (#248) zu einer gemeinsamen Studie zusammen — keine zweite
            Backtest-Engine, keine automatische Live/Paper-Promotion.
          </p>
        </div>

        <ValidationStudyCreateForm
          experiments={experiments.items.map((e) => ({
            experiment_id: e.experiment_id,
            strategy_version: e.strategy_version,
            created_at: e.created_at,
          }))}
          robustnessJobs={robustnessJobs.items}
          gateRuns={gateRuns.items}
        />

        <div>
          <h2 className="mb-2 text-lg font-medium">Studien</h2>
          <ValidationStudiesTable items={studies.items} />
        </div>
      </div>
    );
  } catch (error) {
    return (
      <div
        data-testid="validation-page-error"
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
