import { ResearchOverviewView } from "@/components/research/ResearchOverviewView";
import {
  fetchGateRuns,
  fetchResearchOverview,
  fetchRobustnessJobs,
  fetchValidationStudies,
  getResearchErrorMessage,
} from "@/lib/research-api/client";

export const dynamic = "force-dynamic";

export default async function ResearchOverviewPage() {
  try {
    const [overview, gateRuns, studies, robustnessJobs] = await Promise.all([
      fetchResearchOverview(),
      fetchGateRuns(),
      fetchValidationStudies(),
      fetchRobustnessJobs(),
    ]);

    return (
      <ResearchOverviewView
        overview={overview}
        gateRuns={gateRuns.items}
        studies={studies.items}
        robustnessJobs={robustnessJobs.items}
      />
    );
  } catch (error) {
    return (
      <div
        data-testid="research-overview-error"
        className="rounded-sm border border-red-500/40 bg-red-500/10 p-4"
      >
        <h1 className="text-[16px] font-semibold text-red-300">
          Research API Error
        </h1>
        <p className="mt-2 text-[12px] text-red-200/90">
          {getResearchErrorMessage(error)}
        </p>
      </div>
    );
  }
}
