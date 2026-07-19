import { notFound } from "next/navigation";

import { ScorecardBindSection } from "@/components/research/ScorecardBindSection";
import { ValidationStudyDecisionPanel } from "@/components/research/ValidationStudyDecisionPanel";
import { ValidationStudyDetailView } from "@/components/research/ValidationStudyDetailView";
import {
  ResearchApiError,
  ResearchPageHeader,
  rs,
} from "@/components/research/chrome/ResearchPageChrome";
import { PaperApiError } from "@/lib/paper-api/client";
import {
  fetchValidationStudy,
  getResearchErrorMessage,
} from "@/lib/research-api/client";
import { loadScorecardForStudy } from "@/lib/research/scorecard-binding";
import { toEvidenceAnchor } from "@/lib/research/executive-summary";

export const dynamic = "force-dynamic";

export default async function ResearchValidationDetailPage({
  params,
}: {
  params: Promise<{ studyId: string }>;
}) {
  const { studyId } = await params;

  try {
    const study = await fetchValidationStudy(studyId);
    const scorecardBind = await loadScorecardForStudy(study);

    return (
      <div data-testid="validation-detail-page-ready" className={rs.page}>
        <ResearchPageHeader
          title={study.name}
          backHref="/dashboard/research/validation"
          backLabel="← Validierungsstudien"
        />
        <p className={`${rs.muted} font-mono`}>{study.study_id}</p>

        <ScorecardBindSection
          bind={scorecardBind}
          evidence={toEvidenceAnchor(study)}
          finalDecision={study.decision}
          forensicsExtras={{
            gateHistory: study.gates,
            folds: study.robustness
              .filter((r) => r.test_type === "walk_forward" && r.manifest)
              .flatMap((r) =>
                (r.manifest?.children ?? []).map((child) => ({
                  id: `${r.robustness_id}:${child.child_id}`,
                  label: child.label || child.child_id,
                  netPnl: child.net_pnl ?? null,
                  maxDd: child.max_drawdown ?? null,
                  trades: child.closed_trades ?? null,
                })),
              ),
          }}
        />

        <ValidationStudyDetailView study={study} />

        <ValidationStudyDecisionPanel
          studyId={study.study_id}
          status={study.status}
          decision={study.decision}
        />
      </div>
    );
  } catch (error) {
    if (error instanceof PaperApiError && error.status === 404) {
      notFound();
    }
    return (
      <ResearchApiError
        testId="validation-detail-page-error"
        message={getResearchErrorMessage(error)}
      />
    );
  }
}
