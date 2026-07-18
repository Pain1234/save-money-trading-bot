import { ResearchOverviewView } from "@/components/research/ResearchOverviewView";
import { selectEvidenceStudy } from "@/lib/research/executive-summary";
import {
  fetchGateRuns,
  fetchResearchExperiment,
  fetchResearchOverview,
  fetchRobustnessJobs,
  fetchValidationStudies,
  getResearchErrorMessage,
  type ResearchSeriesPoint,
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

    let pinnedEquity: ResearchSeriesPoint[] | null = null;
    let pinnedDrawdown: ResearchSeriesPoint[] | null = null;
    const focus = selectEvidenceStudy(studies.items);
    if (focus?.experiment_id) {
      try {
        const detail = await fetchResearchExperiment(focus.experiment_id);
        pinnedEquity = detail.equity;
        pinnedDrawdown = detail.drawdown;
      } catch {
        // Soft-fail: analytics panels stay Nicht verfügbar for series.
      }
    }

    return (
      <ResearchOverviewView
        overview={overview}
        gateRuns={gateRuns.items}
        studies={studies.items}
        robustnessJobs={robustnessJobs.items}
        pinnedEquity={pinnedEquity}
        pinnedDrawdown={pinnedDrawdown}
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
