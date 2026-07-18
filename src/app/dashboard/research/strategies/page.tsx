import {
  StrategiesCatalogEmpty,
  StrategiesCatalogError,
  StrategiesCatalogView,
  type StrategyListItem,
} from "@/components/research/StrategiesCatalogView";
import { fetchPaperApi } from "@/lib/paper-api/client";
import { getResearchErrorMessage } from "@/lib/research-api/client";

export const dynamic = "force-dynamic";

export default async function ResearchStrategiesPage() {
  try {
    const body = await fetchPaperApi<{ items: StrategyListItem[] }>(
      "/api/v1/research/strategies",
      { noStore: true },
    );

    if (!body.items.length) {
      return <StrategiesCatalogEmpty />;
    }

    return <StrategiesCatalogView items={body.items} />;
  } catch (error) {
    return <StrategiesCatalogError message={getResearchErrorMessage(error)} />;
  }
}
