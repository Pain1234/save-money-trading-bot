import {
  StrategyLabForm,
  type DatasetOption,
  type StrategyOption,
  type StrategySchemaPayload,
} from "@/components/research/StrategyLabForm";
import { fetchPaperApi } from "@/lib/paper-api/client";
import { getResearchErrorMessage } from "@/lib/research-api/client";

export const dynamic = "force-dynamic";

export default async function ResearchNewExperimentPage({
  searchParams,
}: {
  searchParams: Promise<{ strategy?: string; baseline?: string }>;
}) {
  const params = await searchParams;
  const requestedStrategy = params.strategy?.trim() || "trend_v1";
  const baselineMode = params.baseline === "1" || params.baseline === "true";

  try {
    const [strategies, datasets, schema] = await Promise.all([
      fetchPaperApi<{ items: StrategyOption[] }>("/api/v1/research/strategies", {
        noStore: true,
      }),
      fetchPaperApi<{ items: DatasetOption[] }>("/api/v1/research/datasets", {
        noStore: true,
      }),
      fetchPaperApi<StrategySchemaPayload>(
        `/api/v1/research/strategies/${encodeURIComponent(requestedStrategy)}/schema`,
        { noStore: true },
      ).catch(() => null),
    ]);

    const initialStrategyId =
      strategies.items.find((s) => s.strategy_id === requestedStrategy)
        ?.strategy_id ??
      strategies.items[0]?.strategy_id ??
      "trend_v1";

    return (
      <StrategyLabForm
        strategies={strategies.items}
        datasets={datasets.items}
        initialSchema={schema}
        initialStrategyId={initialStrategyId}
        baselineMode={baselineMode}
      />
    );
  } catch (error) {
    return (
      <div
        data-testid="research-lab-error"
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
