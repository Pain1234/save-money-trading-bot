import { ResearchOverviewView } from "@/components/research/ResearchOverviewView";
import {
  selectEvidenceStudy,
  toEvidenceAnchor,
} from "@/lib/research/executive-summary";
import {
  pinnedRunMatchesDetail,
  sanitizeDrawdownSeries,
  sanitizeEquitySeries,
} from "@/lib/research/analytics-series";
import {
  loadScorecardForStudy,
  type ScorecardBindState,
} from "@/lib/research/scorecard-binding";
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
    let scorecardBind: ScorecardBindState | null = null;

    const focus = selectEvidenceStudy(studies.items);
    const evidence = focus ? toEvidenceAnchor(focus) : null;

    if (focus) {
      // Study → primary run → sealed pin → exact scorecard_id/hash/run_id.
      // Never search scorecards by experiment/strategy "latest".
      scorecardBind = await loadScorecardForStudy(focus);
    }

    if (evidence?.experimentId && evidence.runId) {
      try {
        const detail = await fetchResearchExperiment(evidence.experimentId);
        if (pinnedRunMatchesDetail(evidence, detail)) {
          const equity = sanitizeEquitySeries(detail.equity);
          const drawdown = sanitizeDrawdownSeries(detail.drawdown);
          pinnedEquity = equity.length > 0 ? equity : null;
          pinnedDrawdown = drawdown.length > 0 ? drawdown : null;
        }
        // Run-Mismatch oder fehlender Pin → Serien bleiben null (Nicht verfügbar).
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
        scorecardBind={scorecardBind}
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
