import { ValidationStudyCreateForm } from "@/components/research/ValidationStudyCreateForm";
import { ValidationStudiesTable } from "@/components/research/ValidationStudiesTable";
import {
  ResearchApiError,
  ResearchPageHeader,
  rs,
} from "@/components/research/chrome/ResearchPageChrome";
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
      <div data-testid="validation-page-ready" className={rs.page}>
        <ResearchPageHeader
          title="Validierungsstudien"
          description="Fasst Experimente, Robustheitstests (#247) und Gate-Ergebnisse (#248) zu einer gemeinsamen Studie zusammen — keine zweite Backtest-Engine, keine automatische Live/Paper-Promotion."
        />

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
          <h2 className={rs.sectionTitle}>Studien</h2>
          <ValidationStudiesTable items={studies.items} />
        </div>
      </div>
    );
  } catch (error) {
    return (
      <ResearchApiError
        testId="validation-page-error"
        message={getResearchErrorMessage(error)}
      />
    );
  }
}
