import { ExperimentsTable } from "@/components/research/ExperimentsTable";
import {
  fetchResearchExperiments,
  getResearchErrorMessage,
} from "@/lib/research-api/client";

export const dynamic = "force-dynamic";

export default async function ResearchExperimentsPage() {
  try {
    const data = await fetchResearchExperiments();
    return <ExperimentsTable items={data.items} />;
  } catch (error) {
    return (
      <div
        data-testid="research-experiments-error"
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
