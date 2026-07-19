import Link from "next/link";
import { notFound } from "next/navigation";

import { ScorecardBindSection } from "@/components/research/ScorecardBindSection";
import { ValidationStudyDecisionPanel } from "@/components/research/ValidationStudyDecisionPanel";
import { ValidationStudyDetailView } from "@/components/research/ValidationStudyDetailView";
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
      <div data-testid="validation-detail-page-ready" className="space-y-4">
        <div>
          <Link
            href="/dashboard/research/validation"
            className="text-xs text-text-muted hover:text-mint"
          >
            ← Validierungsstudien
          </Link>
          <h1 className="mt-2 text-xl font-semibold">{study.name}</h1>
          <p className="mt-1 font-mono text-xs text-text-muted">{study.study_id}</p>
        </div>

        <ScorecardBindSection
          bind={scorecardBind}
          evidence={toEvidenceAnchor(study)}
          finalDecision={study.decision}
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
      <div
        data-testid="validation-detail-page-error"
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
