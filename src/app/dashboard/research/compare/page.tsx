import {
  CompareEmptyHint,
  CompareError,
  CompareResultView,
  CompareSelector,
  type CompareSelectorItem,
} from "@/components/research/CompareView";
import {
  ResearchApiError,
  ResearchPageHeader,
  rs,
} from "@/components/research/chrome/ResearchPageChrome";
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
    <div className={rs.page} data-testid="research-compare-ready">
      <ResearchPageHeader
        title="Vergleich"
        description="Vergleicht zwei Runs über die bestehende Registry-Compare-Semantik — kein zweites Vergleichs-Engine, kein P7-Ranking."
      />

      {listErrorMessage && (
        <ResearchApiError
          testId="research-compare-list-error"
          title="Experimentliste nicht verfügbar"
          message={listErrorMessage}
        />
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
