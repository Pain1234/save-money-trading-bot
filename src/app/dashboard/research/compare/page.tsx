import {
  CompareEmptyHint,
  CompareError,
  CompareResultView,
  CompareSelector,
  type CompareSelectorItem,
} from "@/components/research/CompareView";
import { PaperApiError } from "@/lib/paper-api/client";
import {
  fetchResearchCompare,
  fetchResearchExperiments,
  getResearchErrorMessage,
  type ResearchCompareResult,
} from "@/lib/research-api/client";

export const dynamic = "force-dynamic";

function toSelectorItems(
  items: Array<{
    run_id: string;
    experiment_id: string;
    strategy_version: string;
    status: string;
  }>,
): CompareSelectorItem[] {
  return items
    .filter((item) => Boolean(item.run_id))
    .map((item) => ({
      run_id: item.run_id,
      experiment_id: item.experiment_id,
      strategy_version: item.strategy_version,
      status: item.status,
    }));
}

export default async function ResearchComparePage({
  searchParams,
}: {
  searchParams: Promise<{ run_a?: string; run_b?: string }>;
}) {
  const params = await searchParams;
  const runA = params.run_a?.trim() || "";
  const runB = params.run_b?.trim() || "";

  let selectorItems: CompareSelectorItem[] = [];
  let listErrorMessage: string | null = null;
  try {
    const experiments = await fetchResearchExperiments();
    selectorItems = toSelectorItems(experiments.items);
  } catch (error) {
    listErrorMessage = getResearchErrorMessage(error);
  }

  let result: ResearchCompareResult | null = null;
  let compareErrorMessage: string | null = null;
  if (runA && runB) {
    try {
      result = await fetchResearchCompare(runA, runB);
    } catch (error) {
      if (error instanceof PaperApiError && error.status === 404) {
        compareErrorMessage = "Ein oder beide Runs wurden nicht gefunden.";
      } else {
        compareErrorMessage = getResearchErrorMessage(error);
      }
    }
  }

  return (
    <div className="space-y-4" data-testid="research-compare-ready">
      <div>
        <h1 className="text-2xl font-semibold">Vergleich</h1>
        <p className="mt-1 text-sm text-text-secondary">
          Vergleicht zwei Runs über die bestehende Registry-Compare-Semantik —
          kein zweites Vergleichs-Engine, kein P7-Ranking.
        </p>
      </div>

      {listErrorMessage && (
        <p
          className="rounded border border-red-500/40 bg-red-500/10 px-3 py-2 text-sm text-red-200/90"
          data-testid="research-compare-list-error"
        >
          {listErrorMessage}
        </p>
      )}

      <CompareSelector items={selectorItems} runA={runA} runB={runB} />

      {!runA || !runB ? (
        <CompareEmptyHint />
      ) : compareErrorMessage ? (
        <CompareError message={compareErrorMessage} />
      ) : result ? (
        <CompareResultView result={result} />
      ) : null}
    </div>
  );
}
