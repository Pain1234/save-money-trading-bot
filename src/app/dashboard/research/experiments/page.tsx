import Link from "next/link";

import {
  ResearchApiError,
  rs,
} from "@/components/research/chrome/ResearchPageChrome";
import { ExperimentsTable } from "@/components/research/ExperimentsTable";
import {
  fetchResearchExperiments,
  getResearchErrorMessage,
} from "@/lib/research-api/client";

export const dynamic = "force-dynamic";

export default async function ResearchExperimentsPage() {
  try {
    const data = await fetchResearchExperiments();
    return (
      <div className={rs.page}>
        <div className="flex justify-end">
          <Link
            href="/dashboard/research/experiments/new"
            className={rs.btnPrimary}
            data-testid="new-experiment-button"
          >
            Neues Experiment
          </Link>
        </div>
        <ExperimentsTable items={data.items} />
      </div>
    );
  } catch (error) {
    return (
      <ResearchApiError
        testId="research-experiments-error"
        message={getResearchErrorMessage(error)}
      />
    );
  }
}
